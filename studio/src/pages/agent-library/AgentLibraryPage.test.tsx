import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { AgentLibraryPage } from "./AgentLibraryPage";

type AgentFixture = {
  agentId: string;
  name: string;
  currentRevisionId: string | null;
  createdAt: number;
  updatedAt: number;
};

/** Return one JSON response for a Studio API fixture. */
function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Render the Library and expose its URL after route state changes. */
function renderLibrary(entry = "/agents") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/agents" element={<LibraryRoute />} />
          <Route path="/agents/:agentId/design" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Keep the route observable while the Library remains mounted. */
function LibraryRoute() {
  return <><AgentLibraryPage /><LocationProbe /></>;
}

/** Expose canonical handoff and query-preservation behavior. */
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}{location.search}</output>;
}

/** Install a bounded Agent-list fixture and optional endpoint overrides. */
function stubStudioFetch(agents: AgentFixture[], overrides: (url: string, init?: RequestInit) => Response | undefined = () => undefined) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const override = overrides(url, init);
    if (override) return override;
    if (url.includes("/studio/agents?") && !init?.method) return jsonResponse({ schemaVersion: 1, items: agents, nextCursor: null });
    if (url.endsWith("/studio/flow-templates")) return jsonResponse({ schemaVersion: 1, templates: [{ id: "modular_baseline", name: "Mobile Agent 显式闭环", description: "", path: "formal", schemaVersion: 2 }] });
    throw new Error(`unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Agent Library", () => {
  it("leads an empty workspace with example, blank, and import choices without technical creation detail", async () => {
    const fetchMock = stubStudioFetch([]);

    renderLibrary();

    expect(await screen.findByRole("heading", { name: "你的 Agents" })).not.toBeNull();
    const example = await screen.findByRole("button", { name: "从示例开始" });
    const blank = screen.getByRole("button", { name: "创建空白 Agent" });
    expect(example.dataset.libraryAction).toBe("primary");
    expect(blank.dataset.libraryAction).toBe("secondary");
    expect(screen.getByRole("button", { name: "导入 JSON" })).not.toBeNull();
    expect(screen.queryByLabelText("初始模板")).toBeNull();
    expect(screen.queryByText(/Schema 1/)).toBeNull();
    expect(fetchMock.mock.calls.map(([input]) => String(input))).toEqual([expect.stringContaining("/studio/agents?")]);
  });

  it("preserves blank creation URLs, clears only creation intent, and returns focus on close or Escape", async () => {
    stubStudioFetch([]);
    renderLibrary("/agents?from=home");

    const blankButton = await screen.findByRole("button", { name: "创建空白 Agent" });
    blankButton.focus();
    fireEvent.click(blankButton);
    expect(screen.getByRole("dialog", { name: "创建空白 Agent" })).not.toBeNull();
    expect(screen.getByLabelText("location").textContent).toBe("/agents?from=home&create=blank");
    expect(document.activeElement).toBe(screen.getByLabelText("Agent 名称"));

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByLabelText("location").textContent).toBe("/agents?from=home");
    await waitFor(() => expect(document.activeElement).toBe(blankButton));

    fireEvent.click(blankButton);
    fireEvent.click(screen.getByRole("button", { name: "关闭创建 Agent" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("keeps direct blank and example creation routes deterministic and hands off only after persistence", async () => {
    const document = createEmptyStudioDocument("agent-new", "Research Mobile Agent", "document-new");
    let createAttempts = 0;
    stubStudioFetch([], (url, init) => {
      if (url.endsWith("/studio/flow-templates/modular_baseline/document")) return jsonResponse(document);
      if (url.endsWith("/studio/agents") && init?.method === "POST") {
        createAttempts += 1;
        if (createAttempts === 1) return jsonResponse({ error: { code: "studio.agent.conflict", message: "retry-safe conflict" } }, 409);
        return jsonResponse({
          schemaVersion: 1,
          agent: { agentId: "agent-new", name: "Research Mobile Agent", currentRevisionId: "revision-new", createdAt: 1, updatedAt: 1 },
          currentRevision: { revisionId: "revision-new", agentId: "agent-new", ordinal: 1, parentRevisionId: null, document, compileSnapshot: { status: "invalid", diagnostics: [], sourceMap: [] }, createdAt: 1 },
        }, 201);
      }
      return undefined;
    });

    renderLibrary("/agents?create=blank");
    fireEvent.click(await screen.findByRole("button", { name: "创建并进入设计" }));
    expect((await screen.findByRole("alert")).textContent).toContain("retry-safe conflict");
    fireEvent.click(screen.getByRole("button", { name: "创建并进入设计" }));
    await waitFor(() => expect(screen.getByLabelText("location").textContent).toBe("/agents/agent-new/design"));
    expect(createAttempts).toBe(2);

    cleanup();
    const exampleDocument = createEmptyStudioDocument("template-agent", "Mobile Agent 示例", "template-document");
    stubStudioFetch([], (url, init) => {
      if (url.endsWith("/studio/flow-templates/modular_baseline/document")) return jsonResponse(exampleDocument);
      if (url.endsWith("/studio/agents") && init?.method === "POST") return jsonResponse({
        schemaVersion: 1,
        agent: { agentId: "agent-example", name: "Research Mobile Agent", currentRevisionId: "revision-example", createdAt: 1, updatedAt: 1 },
        currentRevision: { revisionId: "revision-example", agentId: "agent-example", ordinal: 1, parentRevisionId: null, document: exampleDocument, compileSnapshot: { status: "invalid", diagnostics: [], sourceMap: [] }, createdAt: 1 },
      }, 201);
      return undefined;
    });
    renderLibrary("/agents?create=example");
    await screen.findByRole("option", { name: "Mobile Agent 显式闭环" });
    fireEvent.click(screen.getByRole("button", { name: "创建并进入设计" }));
    await waitFor(() => expect(screen.getByLabelText("location").textContent).toBe("/agents/agent-example/design"));
  });

  it("features the newest resumable Agent as the sole populated primary action, keeps it in the complete searchable directory, and distinguishes duplicate names safely", async () => {
    stubStudioFetch([
      { agentId: "agent-old", name: "Research Agent", currentRevisionId: "revision-old", createdAt: 1, updatedAt: 10 },
      { agentId: "agent-latest", name: "Research Agent", currentRevisionId: "revision-latest", createdAt: 2, updatedAt: 30 },
      { agentId: "agent-draft", name: "Other Agent", currentRevisionId: null, createdAt: 3, updatedAt: 20 },
    ]);
    renderLibrary();

    expect(await screen.findByText("继续上次工作")).not.toBeNull();
    expect(screen.getByRole("heading", { name: "Research Agent" })).not.toBeNull();
    const continueButton = screen.getByRole("button", { name: "继续设计" });
    const createButton = screen.getByRole("button", { name: "新建 Agent" });
    expect(continueButton.dataset.libraryAction).toBe("primary");
    expect(createButton.dataset.libraryAction).toBe("secondary");
    expect(screen.getAllByText(/同名 Agent/)).toHaveLength(2);
    expect(screen.getAllByText("Research Agent")).toHaveLength(3);
    expect(screen.queryByText("技术详情")).toBeNull();
    expect(screen.queryByText("agent-latest")).toBeNull();

    fireEvent.change(screen.getByLabelText("搜索 Agent"), { target: { value: "Other" } });
    expect(await screen.findByText("Other Agent")).not.toBeNull();
    expect(screen.getByText("继续上次工作")).not.toBeNull();
    fireEvent.click(screen.getByText("Other Agent"));
    await waitFor(() => expect(screen.getByLabelText("location").textContent).toBe("/agents/agent-draft/design"));
  });

  it("keeps search-empty and list-error states distinct with truthful recovery actions", async () => {
    stubStudioFetch([{ agentId: "agent-a", name: "Research Agent", currentRevisionId: "revision-a", createdAt: 1, updatedAt: 1 }]);
    renderLibrary();
    fireEvent.change(await screen.findByLabelText("搜索 Agent"), { target: { value: "missing" } });
    expect(await screen.findByText("没有匹配的 Agent")).not.toBeNull();

    cleanup();
    let attempts = 0;
    stubStudioFetch([], (url) => {
      if (url.includes("/studio/agents?")) {
        attempts += 1;
        return attempts === 1 ? jsonResponse({ error: { message: "offline" } }, 503) : jsonResponse({ schemaVersion: 1, items: [], nextCursor: null });
      }
      return undefined;
    });
    renderLibrary();
    expect(await screen.findByText("无法读取 Agents")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("先从一个可理解的 Agent 开始")).not.toBeNull();
  });

  it("reveals import migration or parse diagnostics only after import is explicitly selected", async () => {
    const fetchMock = stubStudioFetch([]);
    const view = renderLibrary();
    expect(screen.queryByText(/Schema 1/)).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "导入 JSON" }));
    expect(screen.getByRole("dialog", { name: "导入 Agent JSON" })).not.toBeNull();
    expect(screen.getByText(/Schema 2 会严格校验/)).not.toBeNull();
    const file = { name: "broken.json", type: "application/json", text: async () => "not-json" } as File;
    fireEvent.change(view.container.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [file] } });
    expect((await within(screen.getByRole("dialog")).findByRole("status")).textContent).toMatch(/Unexpected token|JSON/);
    expect(fetchMock.mock.calls.map(([input]) => String(input)).filter((url) => /run|device|secret/i.test(url))).toHaveLength(0);
  });
});
