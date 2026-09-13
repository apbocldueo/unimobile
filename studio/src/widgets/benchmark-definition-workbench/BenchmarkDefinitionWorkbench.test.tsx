import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Link, MemoryRouter } from "react-router-dom";
import {
  benchmarkAuthoringKeys,
  benchmarkAuthoringContentCommandFixture,
  benchmarkAuthoringRevisionFixture,
  benchmarkContractProfilePageFixture,
  benchmarkAgentFixtureId,
  benchmarkAgentRevisionFixtureId,
  benchmarkDraftDetailFixture,
  benchmarkDraftFixtureId,
  benchmarkLaterRevisionFixtureId,
  benchmarkNextRevisionFixtureId,
  benchmarkPackageRevisionPageFixture,
  benchmarkValidationResultFixture,
  type BenchmarkDraftCommandResponse,
  type BenchmarkDraftDetail,
} from "@/entities/benchmark-authoring";
import {
  benchmarkDefinitionEditorStatus,
  useBenchmarkDefinitionEditorStore,
} from "@/features/benchmark-definition-editor";
import { BenchmarkDefinitionWorkbench } from "./BenchmarkDefinitionWorkbench";

beforeEach(() => {
  useBenchmarkDefinitionEditorStore.getState().clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Return a fresh JSON response for one fake Studio HTTP exchange. */
function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Build one valid ordinal-two response from the submitted full document. */
function savedResponse(document: unknown): BenchmarkDraftCommandResponse {
  const initial = benchmarkAuthoringRevisionFixture();
  const revision = {
    ...benchmarkAuthoringRevisionFixture("edit"),
    revisionId: benchmarkNextRevisionFixtureId,
    ordinal: 2,
    parentRevisionId: initial.revisionId,
    document: document as ReturnType<
      typeof benchmarkAuthoringRevisionFixture
    >["document"],
    createdAt: initial.createdAt + 1,
  };
  return {
    schemaVersion: 1,
    created: true,
    draft: {
      ...benchmarkDraftDetailFixture().draft,
      currentRevisionId: revision.revisionId,
      updatedAt: revision.createdAt,
    },
    revision,
  };
}

/** Install GET detail plus configurable save behavior. */
function installBackend(
  mode:
    | "success"
    | "conflict"
    | "content-success"
    | "content-conflict"
    | "content-historical" = "success",
) {
  let contentSubmitted = false;
  const historical = benchmarkAuthoringContentCommandFixture("replace", true);
  const laterRevision = {
    ...historical.revision,
    revisionId: benchmarkLaterRevisionFixtureId,
    ordinal: historical.revision.ordinal + 1,
    parentRevisionId: historical.revision.revisionId,
    createdAt: historical.revision.createdAt + 1,
  };
  const laterDetail: BenchmarkDraftDetail = {
    schemaVersion: 1,
    draft: {
      ...historical.draft,
      currentRevisionId: laterRevision.revisionId,
      updatedAt: laterRevision.createdAt,
    },
    currentRevision: laterRevision,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((request: string, init?: RequestInit) => {
      const url = String(request);
      if (url.endsWith("/studio/benchmark-authoring/contract-test-profiles") && (!init?.method || init.method === "GET")) {
        return Promise.resolve(jsonResponse(benchmarkContractProfilePageFixture()));
      }
      if (url.includes("/studio/agents?") && (!init?.method || init.method === "GET")) {
        return Promise.resolve(jsonResponse({
          schemaVersion: 1,
          items: [{
            agentId: benchmarkAgentFixtureId,
            name: "Analysis Agent",
            currentRevisionId: benchmarkAgentRevisionFixtureId,
            createdAt: 1,
            updatedAt: 1,
          }],
          nextCursor: null,
        }));
      }
      if (url.endsWith("/validate") && init?.method === "POST") {
        return Promise.resolve(jsonResponse(benchmarkValidationResultFixture()));
      }
      if (url.includes("/package-revisions?") && (!init?.method || init.method === "GET")) {
        return Promise.resolve(jsonResponse(benchmarkPackageRevisionPageFixture()));
      }
      if (
        url.endsWith(
          `/studio/benchmark-authoring/drafts/${benchmarkDraftFixtureId}`,
        )
        && (!init?.method || init.method === "GET")
      ) {
        return Promise.resolve(jsonResponse(
          mode === "content-historical" && contentSubmitted
            ? laterDetail
            : benchmarkDraftDetailFixture(),
        ));
      }
      if (init?.method === "HEAD") {
        const resource = benchmarkDraftDetailFixture().currentRevision.document.resources
          .find((item) => url.includes(encodeURIComponent(item.id)));
        if (!resource) return Promise.resolve(new Response(null, { status: 404 }));
        return Promise.resolve(new Response(null, {
          status: 200,
          headers: {
            "Content-Type": resource.mediaType,
            "Content-Length": String(resource.size),
            "Content-Disposition": `attachment; filename="${resource.id}.bin"`,
          },
        }));
      }
      if (url.endsWith("/revisions") && init?.method === "POST") {
        if (mode === "conflict") {
          return Promise.resolve(
            jsonResponse(
              {
                schemaVersion: 1,
                error: {
                  code: "benchmark.authoring.revision_conflict",
                  message: "Current revision changed",
                  currentRevisionId: benchmarkNextRevisionFixtureId,
                },
              },
              409,
            ),
          );
        }
        const body = JSON.parse(String(init.body)) as { document: unknown };
        return Promise.resolve(jsonResponse(savedResponse(body.document), 201));
      }
      if (url.includes("/resources/fixture-asset/replace?") && init?.method === "POST") {
        contentSubmitted = true;
        if (mode === "content-conflict") {
          return Promise.resolve(jsonResponse({
            schemaVersion: 1,
            error: {
              code: "benchmark.authoring.content_conflict",
              message: "Current revision changed",
              currentRevisionId: benchmarkNextRevisionFixtureId,
            },
          }, 409));
        }
        return Promise.resolve(jsonResponse(
          mode === "content-historical"
            ? historical
            : benchmarkAuthoringContentCommandFixture("replace"),
          201,
        ));
      }
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
}

/** Render one workbench and return its isolated Query cache. */
function renderWorkbench(initialEntry = "/benchmark-drafts/edit") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[initialEntry]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Link to="/elsewhere">leave editor</Link>
        <BenchmarkDefinitionWorkbench draftId={benchmarkDraftFixtureId} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

/** Mutate the structured title after the authoritative draft has loaded. */
async function editTitle(title: string) {
  const input = await screen.findByLabelText("Title");
  fireEvent.change(input, { target: { value: title } });
}

describe("Benchmark definition workbench", () => {
  it("owns five bounded authoring modes in the URL with safe fallback", async () => {
    installBackend();
    renderWorkbench("/benchmark-drafts/edit?mode=resources");
    expect(await screen.findByText("Managed resources")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Resources" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Definition" }));
    expect(await screen.findByLabelText("Title")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Contract Tests" }));
    expect(await screen.findByText("Contract Test inputs")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run Contract Tests" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Release" }));
    expect(await screen.findByText("Immutable Package revisions")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Release" }).getAttribute("aria-pressed"))
      .toBe("true");
    cleanup();
    useBenchmarkDefinitionEditorStore.getState().clear();
    installBackend();
    renderWorkbench("/benchmark-drafts/edit?mode=unsupported");
    expect(await screen.findByLabelText("Title")).toBeTruthy();
    expect(screen.queryByText("Managed resources")).toBeNull();
    cleanup();
    useBenchmarkDefinitionEditorStore.getState().clear();
    installBackend();
    renderWorkbench("/benchmark-drafts/edit?mode=validation&keep=1");
    expect(await screen.findByText("Analysis inputs")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Validation" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText(/Not run\. Validation only starts/)).toBeTruthy();
    expect(screen.getByText("executionEvidence = false")).toBeTruthy();
  });

  it("routes a validation diagnostic to the exact definition member and breadcrumb", async () => {
    installBackend();
    renderWorkbench("/benchmark-drafts/edit?mode=validation");
    await screen.findByText("Analysis inputs");
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText("Definition invalid")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Navigate" }));
    expect(await screen.findByLabelText("Task JSON tasks/test.json")).toBeTruthy();
    expect(screen.getByText("[0].id")).toBeTruthy();
    const state = useBenchmarkDefinitionEditorStore.getState();
    expect(state.selectedMember).toBe("task:tasks/test.json");
    expect(state.focusedFieldPath).toEqual([0, "id"]);
  });

  it("rebuilds transient validation inputs after an explicit Reload Remote", async () => {
    installBackend();
    renderWorkbench("/benchmark-drafts/edit?mode=validation");
    const split = await screen.findByLabelText("Explicit split") as HTMLInputElement;
    fireEvent.change(split, { target: { value: "stale-local" } });
    expect(split.value).toBe("stale-local");
    fireEvent.click(screen.getByRole("button", { name: "Reload Remote" }));
    await waitFor(() => {
      expect((screen.getByLabelText("Explicit split") as HTMLInputElement).value).toBe("test");
    });
    expect(screen.getByText(/Not run\. Validation only starts/)).toBeTruthy();
  });

  it("marks remote-newer without overwriting dirty local state", async () => {
    installBackend();
    const client = renderWorkbench();
    await editTitle("Local title");
    const initial = benchmarkDraftDetailFixture();
    const newerRevision = {
      ...benchmarkAuthoringRevisionFixture("edit"),
      revisionId: benchmarkNextRevisionFixtureId,
      ordinal: 2,
      parentRevisionId: initial.currentRevision.revisionId,
    };
    const newer: BenchmarkDraftDetail = {
      schemaVersion: 1,
      draft: {
        ...initial.draft,
        currentRevisionId: newerRevision.revisionId,
      },
      currentRevision: newerRevision,
    };
    client.setQueryData(benchmarkAuthoringKeys.detail(benchmarkDraftFixtureId), newer);
    expect(
      await screen.findByText(/远端可能更新/),
    ).toBeTruthy();
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe(
      "Local title",
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Reload Remote" }));
    await waitFor(() => {
      expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe(
        "Authoring Fixture",
      );
    });
  });

  it("resets only locally and guards dirty in-app navigation", async () => {
    installBackend();
    renderWorkbench();
    await editTitle("Local title");
    const unload = new Event("beforeunload", { cancelable: true });
    expect(window.dispatchEvent(unload)).toBe(false);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByRole("link", { name: "leave editor" }));
    expect(confirm).toHaveBeenCalled();
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe(
      "Local title",
    );
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe(
      "Authoring Fixture",
    );
  });

  it("adopts the exact returned immutable revision after save", async () => {
    installBackend();
    renderWorkbench();
    await editTitle("Saved title");
    fireEvent.click(screen.getByRole("button", { name: "Save revision" }));
    expect(await screen.findByText(/Revision 2 已保存/)).toBeTruthy();
    const state = useBenchmarkDefinitionEditorStore.getState();
    expect(state.baselineRevision?.revisionId).toBe(
      benchmarkNextRevisionFixtureId,
    );
    expect(benchmarkDefinitionEditorStatus(state).dirty).toBe(false);
  });

  it("rehydrates the shared definition session after an aligned content result", async () => {
    installBackend("content-success");
    renderWorkbench("/benchmark-drafts/edit?mode=resources");
    await screen.findByText("Managed resources");
    const file = new File(["new bytes"], "screen.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Replacement file"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Replace in new revision" }));
    expect(await screen.findByText(/replace 已创建 immutable Revision 2/)).toBeTruthy();
    expect(useBenchmarkDefinitionEditorStore.getState().baselineRevision?.revisionId).toBe(
      benchmarkNextRevisionFixtureId,
    );
    expect(benchmarkDefinitionEditorStatus(
      useBenchmarkDefinitionEditorStore.getState(),
    ).dirty).toBe(false);
  });

  it("refetches current before adopting a historical exact retry", async () => {
    installBackend("content-historical");
    renderWorkbench("/benchmark-drafts/edit?mode=resources");
    await screen.findByText("Managed resources");
    fireEvent.change(screen.getByLabelText("Replacement file"), {
      target: { files: [new File(["retry"], "screen.png", { type: "image/png" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Replace in new revision" }));
    expect(await screen.findByText(/已确认较早的 replace 命令/)).toBeTruthy();
    expect(useBenchmarkDefinitionEditorStore.getState().baselineRevision?.revisionId).toBe(
      benchmarkLaterRevisionFixtureId,
    );
    expect(useBenchmarkDefinitionEditorStore.getState().baselineRevision?.revisionId).not.toBe(
      benchmarkNextRevisionFixtureId,
    );
  });

  it("preserves selected content and requires Reload Remote after content conflict", async () => {
    installBackend("content-conflict");
    renderWorkbench("/benchmark-drafts/edit?mode=resources");
    await screen.findByText("Managed resources");
    const file = new File(["keep me"], "screen.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Replacement file"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Replace in new revision" }));
    await waitFor(() => {
      expect(screen.getAllByText(/Revision conflict/).length).toBeGreaterThan(0);
    });
    expect(useBenchmarkDefinitionEditorStore.getState().conflictRevisionId).toBe(
      benchmarkNextRevisionFixtureId,
    );
    expect(screen.getByText(/screen.png · 7 bytes/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Replace in new revision" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("preserves local content and disables blind save after a safe conflict", async () => {
    installBackend("conflict");
    renderWorkbench();
    await editTitle("Keep local");
    fireEvent.click(screen.getByRole("button", { name: "Save revision" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    await waitFor(() => {
      expect(
        useBenchmarkDefinitionEditorStore.getState().conflictRevisionId,
      ).toBe(benchmarkNextRevisionFixtureId);
    });
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe(
      "Keep local",
    );
    expect(
      (screen.getByRole("button", { name: "Save blocked" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});
