import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { RunHistoryPage } from "@/pages/run-history";
import { RunReplayPage } from "@/pages/run-replay";

/** Build one backend-shaped Replay envelope for route integration tests. */
function rawReplay(): Record<string, unknown> {
  return {
    schemaVersion: 1,
    runId: "route-run",
    importedAt: 10,
    provenance: "fake_contract_fixture",
    integrityState: "partial",
    snapshot: {
      agentId: "route-agent",
      revisionId: null,
      contractVersion: "1.1",
      canonicalHash: null,
      graphStatus: "not_captured",
      agentGraph: null,
      presentation: null,
      sourceMap: [],
      providerIdentities: [],
    },
    result: {
      status: "success",
      kernelStatus: "success",
      error: "",
      stepCount: 0,
      activationCount: 0,
      interactionCount: 0,
      usage: {},
    },
    moments: [],
    observations: [],
    actions: [],
    benchmark: {
      experimentId: "experiment-1",
      taskId: "task-1",
      agentId: "route-agent",
      repeat: 0,
      outcome: "fail",
      identities: {},
      phases: [],
      evaluation: { isPass: false },
    },
    artifacts: [],
    availability: {
      agentGraph: { state: "not_captured", reasonCode: "", detail: "" },
      screenshots: { state: "not_captured", reasonCode: "", detail: "" },
      prompt: { state: "excluded", reasonCode: "", detail: "" },
    },
    integrity: [],
  };
}

const canonicalHash = `sha256:${"b".repeat(64)}`;
const createdRunId = `run-${"c".repeat(32)}`;

/** Build an eligible native ordinary Replay without mutating the base fixture. */
function rawNativeReplay(): Record<string, unknown> {
  return {
    ...rawReplay(),
    runId: "route-native",
    provenance: "native_studio_run",
    snapshot: {
      agentId: "route-agent",
      revisionId: "revision-1",
      contractVersion: "1.1",
      canonicalHash,
      graphStatus: "available",
      agentGraph: { nodes: [], edges: [] },
      presentation: null,
      sourceMap: [],
      providerIdentities: [],
    },
    benchmark: null,
  };
}

/** Build the exact valid revision required by fail-closed Replay rerun. */
function revisionResponse(): Record<string, unknown> {
  return {
    schemaVersion: 1,
    revision: {
      revisionId: "revision-1",
      agentId: "route-agent",
      ordinal: 1,
      parentRevisionId: null,
      document: createEmptyStudioDocument("route-agent", "Route Agent", "document-1"),
      compileSnapshot: {
        status: "valid",
        diagnostics: [],
        sourceMap: [],
        agentGraph: { nodes: [], edges: [] },
        canonicalHash,
      },
      createdAt: 1,
    },
  };
}

/** Build one newly accepted Run resource for rerun navigation. */
function createRunResponse(): Record<string, unknown> {
  return {
    schemaVersion: 1,
    runId: createdRunId,
    clientRequestId: "request-rerun",
    agentId: "route-agent",
    revisionId: "revision-1",
    canonicalHash,
    task: { text: "Open another task", metadata: {} },
    deviceProfileId: "local-android",
    lifecycle: "accepted",
    cancellationRequested: false,
    resultAvailability: "not_captured",
    result: null,
    replayAvailability: "not_captured",
    eventHighWaterMark: 0,
    acceptedAt: 20,
    startedAt: null,
    updatedAt: 20,
    terminalAt: null,
    storageWarnings: [],
    created: true,
  };
}

/** Expose push navigation and browser-back behavior to route assertions. */
function NavigationProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <div>
      <output aria-label="location">{`${location.pathname}${location.search}`}</output>
      <button type="button" onClick={() => navigate(-1)}>Back</button>
    </div>
  );
}

/** Render History and Replay routes with an isolated Query client. */
function renderRoutes(initialPath: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[initialPath]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/history" element={<RunHistoryPage />} />
          <Route path="/runs/:runId/replay" element={<RunReplayPage />} />
          <Route path="/agents/:agentId/run" element={<p>Live Run route</p>} />
        </Routes>
        <NavigationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("History and Replay routes", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("hands off a real History row to a stable deep Replay route", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/studio/replays?")) {
          return new Response(
            JSON.stringify({
              schemaVersion: 1,
              items: [
                {
                  runId: "route-run",
                  agentId: "route-agent",
                  agentStatus: "success",
                  benchmarkOutcome: "fail",
                  provenance: "fake_contract_fixture",
                  integrityState: "partial",
                  evidenceCompleteness: 40,
                  importedAt: 10,
                },
              ],
              nextCursor: null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(JSON.stringify(rawReplay()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderRoutes("/history?q=route");
    const replayLink = await screen.findByRole("link", { name: "Replay" });
    expect(replayLink.getAttribute("href")).toBe("/runs/route-run/replay");
    const bundleLink = screen.getByRole("link", { name: "Bundle" });
    expect(bundleLink.getAttribute("href")).toContain(
      "/api/studio/replays/route-run/bundle",
    );
    expect(screen.getAllByText("success").length).toBeGreaterThan(0);
    expect(screen.getAllByText("fail").length).toBeGreaterThan(0);
    fireEvent.click(replayLink);
    expect(await screen.findByRole("heading", { name: /route-agent/ })).not.toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "技术详情" }));
    fireEvent.click(screen.getByText("运行计数与证据状态"));
    expect(screen.getAllByText("partial").length).toBeGreaterThan(0);
  });

  it("renders an explicit not-found deep-link state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            schemaVersion: 1,
            error: { code: "studio.replay.not_found", message: "not found" },
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    renderRoutes("/runs/missing/replay");
    expect(await screen.findByText("Replay 不存在")).not.toBeNull();
    expect(screen.getByText("没有找到 missing")).not.toBeNull();
  });

  it("creates a distinct Run from an eligible Replay and browser-back preserves the old Replay", async () => {
    const requests: Array<{ url: string; method: string; body: unknown }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        requests.push({
          url,
          method,
          body: init?.body ? JSON.parse(String(init.body)) : null,
        });
        if (url.endsWith("/studio/replays/route-native")) {
          return new Response(JSON.stringify(rawNativeReplay()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/studio/agents/route-agent")) {
          return new Response(JSON.stringify({
            schemaVersion: 1,
            agent: {
              agentId: "route-agent",
              name: "Readable Route Agent",
              currentRevisionId: "revision-1",
              createdAt: 1,
              updatedAt: 2,
            },
            currentRevision: null,
          }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/studio/device-profiles")) {
          return new Response(JSON.stringify({
            schemaVersion: 1,
            items: [{
              deviceProfileId: "local-android",
              label: "Local Android",
              platform: "android",
              availability: "configured",
            }],
          }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/run-readiness")) {
          return new Response(JSON.stringify({
            schemaVersion: 1,
            agentId: "route-agent",
            revisionId: "revision-1",
            canonicalHash,
            deviceProfileId: "local-android",
            ready: true,
            diagnostics: [],
          }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/revisions/revision-1")) {
          return new Response(JSON.stringify(revisionResponse()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/studio/runs") && method === "POST") {
          return new Response(JSON.stringify(createRunResponse()), {
            status: 202,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response("not found", { status: 404 });
      }),
    );

    renderRoutes("/runs/route-native/replay");
    expect(
      await screen.findByRole("heading", { name: "Readable Route Agent" }),
    ).not.toBeNull();
    fireEvent.change(await screen.findByLabelText("Task"), {
      target: { value: "Open another task" },
    });
    await screen.findByText("Local Android");
    await waitFor(() => {
      expect((screen.getByRole("button", { name: "运行" }) as HTMLButtonElement).disabled).toBe(false);
    });
    fireEvent.click(screen.getByRole("button", { name: "运行" }));
    expect(await screen.findByText("Live Run route")).not.toBeNull();
    expect(screen.getByLabelText("location").textContent).toBe(
      `/agents/route-agent/run?runId=${createdRunId}`,
    );
    const createRequest = requests.find(({ method }) => method === "POST");
    expect(createRequest?.body).toMatchObject({
      agentId: "route-agent",
      revisionId: "revision-1",
      task: { text: "Open another task", metadata: {} },
    });

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(
      await screen.findByRole("heading", { name: "Readable Route Agent" }),
    ).not.toBeNull();
    expect(screen.getByLabelText("location").textContent).toBe(
      "/runs/route-native/replay",
    );
    fireEvent.click(screen.getByRole("tab", { name: "技术详情" }));
    fireEvent.click(screen.getByText("运行身份与完整性"));
    expect(screen.getAllByText("route-native").length).toBeGreaterThan(0);
  });

  it("keeps imported Benchmark Replay read-only without querying a revision or creating a Run", async () => {
    const requests: Array<{ url: string; method: string }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, method: init?.method ?? "GET" });
        return new Response(JSON.stringify(rawReplay()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderRoutes("/runs/route-run/replay");
    expect(await screen.findByText(/不是本地普通 Agent Run/)).not.toBeNull();
    expect(screen.queryByLabelText("Task")).toBeNull();
    expect(requests.some(({ url }) => url.includes("/revisions/"))).toBe(false);
    expect(requests.some(({ method }) => method === "POST")).toBe(false);
  });
});
