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
import type {
  RunSnapshot,
  StudioRunResource,
} from "@/entities/run";
import { ThreePaneLiveRunWorkbench } from "./ThreePaneLiveRunWorkbench";

const runId = `run-${"a".repeat(32)}`;
const hash = `sha256:${"b".repeat(64)}`;

class BrowserEventSource {
  static instances: BrowserEventSource[] = [];
  readonly url: string;
  closed = false;
  private listeners = new Map<string, Array<(event: { data?: string }) => void>>();

  constructor(url: string) {
    this.url = url;
    BrowserEventSource.instances.push(this);
  }

  /** Register one browser-compatible test listener. */
  addEventListener(
    type: string,
    listener: (event: { data?: string }) => void,
  ): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  /** Close this deterministic source. */
  close(): void {
    this.closed = true;
  }

  /** Deliver one named SSE frame. */
  emit(type: string, data?: string): void {
    for (const listener of this.listeners.get(type) ?? []) listener({ data });
  }
}

/** Build one running resource for the live widget. */
function run(): StudioRunResource {
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
    eventHighWaterMark: 1,
    acceptedAt: 1,
    startedAt: 2,
    updatedAt: 2,
    terminalAt: null,
    storageWarnings: [],
  };
}

/** Build the exact verified graph shown by Live. */
function snapshot(): RunSnapshot {
  return {
    agentId: "agent-1",
    revisionId: "revision-1",
    contractVersion: "1.1",
    canonicalHash: hash,
    graphStatus: "available",
    agentGraph: {
      nodes: [
        {
          id: "reasoning",
          kind: "component",
          role: "zhixing.role.reasoning",
          lifecycle: "per_step",
          primary: false,
        },
      ],
      edges: [],
    },
    graphNodes: [
      {
        id: "reasoning",
        kind: "component",
        role: "zhixing.role.reasoning",
        lifecycle: "per_step",
        primary: false,
      },
    ],
    graphEdges: [],
    presentation: null,
    sourceMap: [],
    providerIdentities: [],
  };
}

/** Build one journal event JSON object. */
function event(sequence: number, kind: string) {
  return {
    schemaVersion: 1,
    eventId: `event-${sequence}`,
    timestamp: sequence,
    source: "runtime",
    kind,
    payload: {
      phase: "graph_kernel",
      role: "zhixing.role.reasoning",
      component: "fixture:reasoner@1.0.0",
      node_id: "reasoning",
      task: "Open Settings",
    },
    runtimeSequence: sequence,
    nodePath: "reasoning",
    activationId: "activation-1",
    interactionStep: 0,
    runId,
    sequence,
    fingerprint: `sha256:${String(sequence).padStart(64, "0")}`,
  };
}

/** Render with a real Query cache and mocked transport boundaries. */
function renderLive(resource = run()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ThreePaneLiveRunWorkbench run={resource} snapshot={snapshot()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    },
  );
});

afterEach(() => {
  cleanup();
  BrowserEventSource.instances = [];
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ThreePaneLiveRunWorkbench", () => {
  it("follows live facts while allowing a historical Inspector lock", async () => {
    vi.stubGlobal("EventSource", BrowserEventSource);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            schemaVersion: 1,
            runId,
            items: [
              {
                ...event(1, "run.accepted"),
                source: "service",
                nodePath: "",
                activationId: "",
                payload: {},
              },
            ],
            nextCursor: 1,
            highWaterMark: 1,
            terminal: false,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    renderLive();
    await waitFor(() => expect(BrowserEventSource.instances).toHaveLength(1));
    act(() => {
      BrowserEventSource.instances[0]?.emit("open");
      BrowserEventSource.instances[0]?.emit(
        "journal",
        JSON.stringify(event(2, "start")),
      );
      BrowserEventSource.instances[0]?.emit(
        "journal",
        JSON.stringify(event(3, "complete")),
      );
    });
    expect(screen.queryByText("activation-1")).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: /选择下一步行动/ }));
    expect(screen.getByText("回到当前")).not.toBeNull();
    expect(screen.getByLabelText("Virtual Phone")).not.toBeNull();
    expect(screen.queryByText(/Pause|Retry node|Checkpoint/)).toBeNull();
  });

  it("sends only the real cooperative Cancel command", async () => {
    vi.stubGlobal("EventSource", BrowserEventSource);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
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
      return new Response(
        JSON.stringify({
          ...run(),
          lifecycle: "cancelling",
          cancellationRequested: true,
        }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderLive();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/runs/${runId}/cancel`),
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining("协作式取消"),
    );
  });

  it("renders graph contract errors and both themes without hiding evidence panes", () => {
    vi.stubGlobal("EventSource", BrowserEventSource);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            schemaVersion: 1,
            runId,
            items: [],
            nextCursor: 0,
            highWaterMark: 0,
            terminal: false,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    document.documentElement.dataset.zxTheme = "light";
    const rendered = render(
      <QueryClientProvider client={new QueryClient()}>
        <ThreePaneLiveRunWorkbench
          run={run()}
          snapshot={{ ...snapshot(), graphStatus: "corrupt" }}
          graphError="canonical hash mismatch"
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Graph 不可验证/)).not.toBeNull();
    expect(screen.getByLabelText("Virtual Phone")).not.toBeNull();
    document.documentElement.dataset.zxTheme = "dark";
    rendered.rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ThreePaneLiveRunWorkbench
          run={run()}
          snapshot={{ ...snapshot(), graphStatus: "corrupt" }}
          graphError="canonical hash mismatch"
        />
      </QueryClientProvider>,
    );
    expect(screen.getByLabelText("Run Inspector")).not.toBeNull();
  });
});
