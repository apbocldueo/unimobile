import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { AgentRunPage } from "./AgentRunPage";
import { parseAgentRunSearch } from "./model/agentRunRoute";

const runId = `run-${"a".repeat(32)}`;
const hash = `sha256:${"b".repeat(64)}`;

/** Build one valid immutable revision response. */
function revisionResponse() {
  return {
    schemaVersion: 1,
    revision: {
      revisionId: "revision-1",
      agentId: "agent-1",
      ordinal: 1,
      parentRevisionId: null,
      document: createEmptyStudioDocument("agent-1", "Agent", "document-1"),
      compileSnapshot: {
        status: "valid",
        diagnostics: [],
        sourceMap: [],
        agentGraph: { nodes: [], edges: [] },
        canonicalHash: hash,
      },
      createdAt: 1,
    },
  };
}

/** Build one human-readable Agent metadata response. */
function agentResponse() {
  return {
    schemaVersion: 1,
    agent: {
      agentId: "agent-1",
      name: "Research Agent",
      currentRevisionId: "revision-1",
      createdAt: 1,
      updatedAt: 2,
    },
    currentRevision: null,
  };
}

/** Build one accepted Run resource response. */
function runResponse() {
  return {
    schemaVersion: 1,
    runId,
    clientRequestId: "request-1",
    agentId: "agent-1",
    revisionId: "revision-1",
    canonicalHash: hash,
    task: { text: "Open Settings", metadata: {} },
    deviceProfileId: "local-android",
    lifecycle: "running",
    cancellationRequested: false,
    resultAvailability: "not_captured",
    result: null,
    replayAvailability: "not_captured",
    eventHighWaterMark: 0,
    acceptedAt: 1,
    startedAt: 2,
    updatedAt: 2,
    terminalAt: null,
    storageWarnings: [],
    created: true,
  };
}

/** Build one terminal Run resource for explicit Replay handoff tests. */
function terminalRunResponse(
  status: string,
  replayAvailability: "available" | "not_captured" | "missing" | "corrupt" = "available",
) {
  const { created: _created, ...resource } = runResponse();
  return {
    ...resource,
    lifecycle: "terminal",
    cancellationRequested: status === "cancelled",
    resultAvailability: "available",
    result: {
      status,
      kernelStatus: status,
      errorCode: status === "success" ? "" : `runtime.${status}`,
      error: status === "success" ? "" : status,
      stepCount: 1,
      activationCount: 0,
      interactionCount: 1,
      usage: {},
      finalOutput: null,
      artifactNamespace: "",
    },
    replayAvailability,
    eventHighWaterMark: 1,
    updatedAt: 4,
    terminalAt: 4,
  };
}

/** Build one backend-shaped terminal journal event. */
function terminalEventResponse(status: string) {
  return {
    schemaVersion: 1,
    eventId: "event-terminal",
    timestamp: 4,
    source: "result",
    kind: "run.terminal",
    payload: { result: { status }, replayAvailability: "available" },
    runtimeSequence: 1,
    nodePath: "",
    activationId: "",
    interactionStep: 1,
    runId,
    sequence: 1,
    fingerprint: hash,
  };
}

/** Build the Run-owned safe Device Profile directory response. */
function deviceProfilesResponse() {
  return {
    schemaVersion: 1,
    items: [{
      deviceProfileId: "local-android",
      label: "Local Android",
      platform: "android",
      availability: "configured",
    }],
  };
}

/** Build exact static readiness for the immutable launch target. */
function readinessResponse() {
  return {
    schemaVersion: 1,
    agentId: "agent-1",
    revisionId: "revision-1",
    canonicalHash: hash,
    deviceProfileId: "local-android",
    ready: true,
    diagnostics: [],
  };
}

/** Expose current location for replace-navigation assertions. */
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{`${location.pathname}${location.search}`}</output>;
}

/** Render the Agent Run route with an isolated server-state cache. */
function renderRun(path: string) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/agents/:agentId/run" element={<AgentRunPage />} />
          <Route path="/runs/:runId/replay" element={<div>Replay route</div>} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Agent Run launch route", () => {
  it("strictly separates revision launch and run binding identities", () => {
    expect(parseAgentRunSearch("")).toEqual({ mode: "current" });
    expect(parseAgentRunSearch("?revisionId=revision-1")).toEqual({
      mode: "launch",
      revisionId: "revision-1",
    });
    expect(parseAgentRunSearch("?runId=run-1")).toEqual({
      mode: "live",
      runId: "run-1",
    });
    expect(parseAgentRunSearch("?revisionId=x&runId=y").mode).toBe("invalid");
    expect(parseAgentRunSearch("?revisionId=x&task=secret").mode).toBe(
      "invalid",
    );
  });

  it("retains retry identity and regenerates it after semantic form changes", async () => {
    const posted: Array<Record<string, unknown>> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/studio/agents/agent-1")) {
          return new Response(JSON.stringify(agentResponse()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/studio/device-profiles")) {
          return new Response(JSON.stringify(deviceProfilesResponse()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/run-readiness")) {
          return new Response(JSON.stringify(readinessResponse()), {
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
        posted.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return new Response(
          JSON.stringify({
            error: { code: "studio.http.unreachable", message: "offline" },
          }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    renderRun("/agents/agent-1/run");
    fireEvent.change(await screen.findByLabelText("Task"), {
      target: { value: "Open Settings" },
    });
    expect(screen.getByRole("heading", { name: "Research Agent" })).not.toBeNull();
    await waitFor(() => {
      expect((screen.getByRole("button", { name: "运行" }) as HTMLButtonElement).disabled).toBe(false);
    });
    fireEvent.click(screen.getByRole("button", { name: "运行" }));
    await screen.findByText(/Run 创建失败/);
    fireEvent.click(screen.getByRole("button", { name: "运行" }));
    await waitFor(() => expect(posted).toHaveLength(2));
    expect(posted[0]?.clientRequestId).toBe(posted[1]?.clientRequestId);

    fireEvent.change(screen.getByLabelText("Task"), {
      target: { value: "Open Display settings" },
    });
    fireEvent.click(screen.getByRole("button", { name: "运行" }));
    await waitFor(() => expect(posted).toHaveLength(3));
    expect(posted[2]?.clientRequestId).not.toBe(posted[1]?.clientRequestId);
  });

  it("validates metadata and replace-binds an accepted Run", async () => {
    vi.stubGlobal(
      "EventSource",
      class {
        addEventListener(): void {}
        close(): void {}
      },
    );
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/studio/agents/agent-1")) {
          return new Response(JSON.stringify(agentResponse()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/studio/device-profiles")) {
          return new Response(JSON.stringify(deviceProfilesResponse()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/run-readiness")) {
          return new Response(JSON.stringify(readinessResponse()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/revisions/")) {
          return new Response(JSON.stringify(revisionResponse()), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (init?.method === "POST") {
          return new Response(JSON.stringify(runResponse()), {
            status: 202,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/events?")) {
          return new Response(
            JSON.stringify({
              schemaVersion: 1,
              runId,
              items: [],
              nextCursor: 0,
              highWaterMark: 0,
              terminal: false,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        const { created: _created, ...resource } = runResponse();
        return new Response(JSON.stringify(resource), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    renderRun("/agents/agent-1/run?revisionId=revision-1");
    fireEvent.change(await screen.findByLabelText("Task"), {
      target: { value: "Open Settings" },
    });
    await waitFor(() => {
      expect((screen.getByRole("button", { name: "运行" }) as HTMLButtonElement).disabled).toBe(false);
    });
    fireEvent.click(
      screen.getByRole("button", { name: "metadata" }),
    );
    fireEvent.change(screen.getByLabelText("metadata JSON"), {
      target: { value: "[]" },
    });
    fireEvent.click(screen.getByRole("button", { name: "运行" }));
    expect(await screen.findByText(/根必须是对象/)).not.toBeNull();
    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === "POST"),
    ).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("metadata JSON"), {
      target: { value: '{"research":"fixture"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "运行" }));
    await waitFor(() => {
      expect(screen.getByLabelText("location").textContent).toBe(
        `/agents/agent-1/run?runId=${runId}`,
      );
    });
    expect((await screen.findAllByText("running")).length).toBeGreaterThan(0);
  });

  it("recovers an active Run directly from its durable runId route", async () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe(): void {}
        unobserve(): void {}
        disconnect(): void {}
      },
    );
    vi.stubGlobal(
      "EventSource",
      class {
        addEventListener(): void {}
        close(): void {}
      },
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/studio/agents/agent-1")) {
          return new Response(JSON.stringify(agentResponse()), {
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
        if (url.includes("/events?")) {
          return new Response(JSON.stringify({
            schemaVersion: 1,
            runId,
            items: [],
            nextCursor: 0,
            highWaterMark: 0,
            terminal: false,
          }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        const { created: _created, ...resource } = runResponse();
        return new Response(JSON.stringify(resource), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    renderRun(`/agents/agent-1/run?runId=${runId}`);
    expect(
      await screen.findByRole("heading", { name: "Research Agent" }),
    ).not.toBeNull();
    expect(screen.getByText("Open Settings")).not.toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it.each(["success", "failure", "cancelled"])(
    "retains the %s terminal story until the user explicitly opens Replay",
    async (status) => {
      vi.stubGlobal(
        "ResizeObserver",
        class {
          observe(): void {}
          unobserve(): void {}
          disconnect(): void {}
        },
      );
      const terminalRun = terminalRunResponse(status);
      vi.stubGlobal(
        "fetch",
        vi.fn(async (input: RequestInfo | URL) => {
          const url = String(input);
          if (url.endsWith("/studio/agents/agent-1")) {
            return new Response(JSON.stringify(agentResponse()), {
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
          if (url.includes("/events?")) {
            return new Response(JSON.stringify({
              schemaVersion: 1,
              runId,
              items: [terminalEventResponse(status)],
              nextCursor: 1,
              highWaterMark: 1,
              terminal: true,
            }), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            });
          }
          return new Response(JSON.stringify(terminalRun), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }),
      );

      renderRun(`/agents/agent-1/run?runId=${runId}`);
      const openReplay = await screen.findByRole("button", { name: "打开完整回放" });
      expect(screen.getByLabelText("location").textContent).toBe(
        `/agents/agent-1/run?runId=${runId}`,
      );
      expect(
        within(screen.getByLabelText("Run Inspector")).getByText(/运行.*结束/),
      ).not.toBeNull();
      fireEvent.click(openReplay);
      await waitFor(() => {
        expect(screen.getByLabelText("location").textContent).toBe(
          `/runs/${runId}/replay`,
        );
      });
    },
  );

  it("keeps a terminal Run inspectable while Replay is missing", async () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe(): void {}
        unobserve(): void {}
        disconnect(): void {}
      },
    );
    const terminalRun = terminalRunResponse("failure", "missing");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/studio/agents/agent-1")) {
          return new Response(JSON.stringify(agentResponse()), {
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
        if (url.includes("/events?")) {
          return new Response(JSON.stringify({
            schemaVersion: 1,
            runId,
            items: [terminalEventResponse("failure")],
            nextCursor: 1,
            highWaterMark: 1,
            terminal: true,
          }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(JSON.stringify(terminalRun), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    renderRun(`/agents/agent-1/run?runId=${runId}`);
    expect(await screen.findByText(/Replay 当前为 missing/)).not.toBeNull();
    expect(screen.queryByRole("button", { name: "打开完整回放" })).toBeNull();
    expect(screen.getByRole("button", { name: "重新检查 Replay" })).not.toBeNull();
    expect(screen.getByLabelText("location").textContent).toBe(
      `/agents/agent-1/run?runId=${runId}`,
    );
  });
});
