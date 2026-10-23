import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import {
  createEmptyStudioDocument,
  type StudioFlowDocument,
} from "@/entities/agent-graph";
import type { AgentRevision } from "@/entities/agent-revision";
import { runtimeReadinessKeys } from "@/entities/runtime-readiness";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { BuilderToolbar } from "./BuilderToolbar";
import { useUiLocaleStore } from "@/shared/i18n";

const hash = `sha256:${"a".repeat(64)}`;

/** Build one Builder revision with explicit compile status. */
function revision(status: "valid" | "invalid" = "valid"): AgentRevision {
  return {
    revisionId: "revision-1",
    agentId: "agent-1",
    ordinal: 1,
    parentRevisionId: null,
    document: createEmptyStudioDocument("agent-1", "Research Agent", "document-1"),
    compileSnapshot: {
      status,
      diagnostics:
        status === "valid"
          ? []
          : [
              {
                code: "studio.graph.invalid",
                message: "invalid",
                severity: "error",
                path: [],
              },
            ],
      sourceMap: [],
      ...(status === "valid"
        ? {
            canonicalHash: hash,
            agentGraph: { nodes: [], edges: [] },
          }
        : {}),
    },
    createdAt: 1,
  };
}

/** Expose navigation from the toolbar without mounting the full Builder. */
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{`${location.pathname}${location.search}`}</output>;
}

/** Render the toolbar with an isolated Query client and route. */
function renderToolbar() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  client.setQueryData(runtimeReadinessKeys.process, {
    schemaVersion: 1,
    ready: true,
    providers: [],
    secrets: [],
    deviceProfiles: [],
    diagnostics: [],
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/agents/agent-1/design"]}
      >
        <BuilderToolbar
          agentName="Research Agent"
          catalogVersion="catalog-1"
          onReload={vi.fn()}
        />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useUiLocaleStore.getState().setLocale("zh-CN");
  useAgentBuilderDocumentStore.getState().clear();
});

afterEach(() => {
  cleanup();
  useUiLocaleStore.getState().setLocale("zh-CN");
  vi.unstubAllGlobals();
});

describe("Builder Run commands", () => {
  it("keeps the exact dirty document and invalid JSON buffer when language changes", () => {
    const store = useAgentBuilderDocumentStore.getState();
    store.hydrate(revision());
    store.addNode({
      canvasId: "reason", logicalId: "reason", family: "reasoning", lifecycle: "per_step",
      implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "universal_reasoning", version: "1", params: { note: "保留原文" }, dependencies: {} }] },
    }, { x: 10, y: 20, label: "用户节点" });
    store.editRaw({ canvasId: "reason", candidate: 0, implementation: '["agent.reasoning","universal_reasoning","1"]', property: "params" }, '{"未完成":');
    renderToolbar();
    const before = useAgentBuilderDocumentStore.getState();
    act(() => useUiLocaleStore.getState().setLocale("en"));
    expect(screen.getByRole("button", { name: "Validate" })).toBeTruthy();
    const after = useAgentBuilderDocumentStore.getState();
    expect(after.document).toBe(before.document);
    expect(after.rawFields).toBe(before.rawFields);
    expect(after.baseline).toBe(before.baseline);
    expect(after.sessionId).toBe(before.sessionId);
    expect(after.generation).toBe(before.generation);
    expect(after.dirty).toBe(true);
    expect(Object.values(after.rawFields)[0]?.text).toBe('{"未完成":');
    expect(after.document?.presentation.nodes.reason.label).toBe("用户节点");
  });
  it("keeps document/version commands in an accessible secondary menu", () => {
    useAgentBuilderDocumentStore.getState().hydrate(revision());
    renderToolbar();
    const summary = screen.getByText("更多操作");
    expect((summary.parentElement as HTMLDetailsElement).open).toBe(false);
    fireEvent.click(summary);
    expect((summary.parentElement as HTMLDetailsElement).open).toBe(true);
    expect(screen.getByRole("button", { name: "另存为" }).getAttribute("data-command-priority")).toBe("secondary");
    expect(screen.getByRole("button", { name: "试跑" }).getAttribute("data-command-priority")).toBe("primary");
    expect(screen.getByText("技术详情")).not.toBeNull();
  });

  it("labels an unvalidated graph as pending instead of implying an unexplained block", () => {
    useAgentBuilderDocumentStore.getState().replaceDocument(
      createEmptyStudioDocument("agent-1", "Research Agent", "document-1"),
      "revision-1",
    );
    renderToolbar();
    expect(screen.queryByText("流程待检查")).toBeNull();
    expect(screen.getByRole("button", { name: "检查流程" })).not.toBeNull();
  });

  it("opens Run directly for a clean valid immutable revision", () => {
    useAgentBuilderDocumentStore.getState().hydrate(revision());
    renderToolbar();
    fireEvent.click(screen.getByRole("button", { name: "试跑" }));
    expect(screen.getByLabelText("location").textContent).toBe(
      "/agents/agent-1/run?revisionId=revision-1",
    );
  });

  it("saves a dirty draft once and opens only the returned valid revision", async () => {
    useAgentBuilderDocumentStore.getState().hydrate(revision());
    useAgentBuilderDocumentStore.getState().addNode(
      {
        canvasId: "canvas-memory",
        logicalId: "memory",
        family: "memory",
        lifecycle: "stateful",
        implementation: {
          policy: "single",
          candidates: [{
            namespace: "agent.memory",
            name: "sliding_window_memory",
            version: "1",
            params: {},
            dependencies: {},
          }],
        },
      },
      { x: 0, y: 0 },
    );
    const savedDocument = useAgentBuilderDocumentStore.getState()
      .document as StudioFlowDocument;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            schemaVersion: 1,
            agent: {
              agentId: "agent-1",
              name: "Research Agent",
              currentRevisionId: "revision-2",
              createdAt: 1,
              updatedAt: 2,
            },
            revision: {
              ...revision(),
              revisionId: "revision-2",
              ordinal: 2,
              parentRevisionId: "revision-1",
              document: savedDocument,
              createdAt: 2,
            },
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    renderToolbar();
    fireEvent.click(screen.getByRole("button", { name: "保存并试跑" }));
    await waitFor(() => {
      expect(screen.getByLabelText("location").textContent).toBe(
        "/agents/agent-1/run?revisionId=revision-2",
      );
    });
    expect(useAgentBuilderDocumentStore.getState().dirty).toBe(false);
  });

  it("keeps invalid and conflicted drafts in Builder without navigation", async () => {
    useAgentBuilderDocumentStore.getState().hydrate(revision("invalid"));
    renderToolbar();
    expect(
      (screen.getByRole("button", { name: "试跑" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    cleanup();

    useAgentBuilderDocumentStore.getState().hydrate(revision());
    useAgentBuilderDocumentStore.getState().addNode(
      {
        canvasId: "canvas-memory-conflict",
        logicalId: "memory_conflict",
        family: "memory",
        lifecycle: "stateful",
        implementation: {
          policy: "single",
          candidates: [{
            namespace: "agent.memory",
            name: "sliding_window_memory",
            version: "1",
            params: {},
            dependencies: {},
          }],
        },
      },
      { x: 0, y: 0 },
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            error: {
              code: "studio.agent.revision_conflict",
              message: "conflict",
              currentRevisionId: "revision-remote",
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    renderToolbar();
    fireEvent.click(screen.getByRole("button", { name: "保存并试跑" }));
    expect(await screen.findByText(/远端已到 revision-rem/)).not.toBeNull();
    expect(screen.getByLabelText("location").textContent).toBe(
      "/agents/agent-1/design",
    );
  });
});
