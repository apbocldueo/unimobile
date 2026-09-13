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
import { MemoryRouter, Route, Routes } from "react-router-dom";
import {
  benchmarkEventFixture,
  benchmarkExperimentFixture,
  benchmarkExperimentId,
  benchmarkTaskRunFixture,
} from "@/entities/benchmark-experiment";
import { ExperimentMonitorPage } from "./ExperimentMonitorPage";

class BrowserEventSource {
  static instances: BrowserEventSource[] = [];
  readonly url: string;
  closed = false;
  private listeners = new Map<
    string,
    Array<(event: { data?: string }) => void>
  >();

  constructor(url: string) {
    this.url = url;
    BrowserEventSource.instances.push(this);
  }

  /** Register one browser-compatible named SSE test listener. */
  addEventListener(
    type: string,
    listener: (event: { data?: string }) => void,
  ): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  /** Record manual transport disposal by the Monitor session. */
  close(): void {
    this.closed = true;
  }

  /** Deliver one named browser frame to registered listeners. */
  emit(type: string, data?: string): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data });
    }
  }
}

type BackendState = {
  experiment: Record<string, unknown>;
  taskRuns: Array<Record<string, unknown>>;
  events: Array<Record<string, unknown>>;
  taskRunsFail?: boolean;
  notFound?: boolean;
};

/** Return one strict JSON response for the fake Monitor backend. */
function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Install a stateful fake for Experiment, TaskRun, event, and cancel routes. */
function installMonitorBackend(state: BackendState) {
  const requests: Array<{ url: string; method: string; body: unknown }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      requests.push({ url, method, body });
      if (state.notFound) {
        return jsonResponse(
          {
            schemaVersion: 1,
            error: {
              code: "studio.benchmark_experiment.not_found",
              message: "not found",
            },
          },
          404,
        );
      }
      if (url.endsWith("/cancel") && method === "POST") {
        state.experiment = {
          ...state.experiment,
          lifecycle: "terminal",
          terminalReason: "cancelled",
          terminalAt: 20,
          updatedAt: 20,
          links: {
            ...(state.experiment.links as Record<string, unknown>),
            cancel: null,
          },
        };
        return jsonResponse(state.experiment, 202);
      }
      if (url.includes("/events?")) {
        const parsed = new URL(url, "http://studio.test");
        const after = Number(parsed.searchParams.get("after") ?? "0");
        const items = state.events.filter(
          (item) => Number(item.sequence) > after,
        );
        const highWaterMark = Number(state.events.at(-1)?.sequence ?? 0);
        return jsonResponse({
          schemaVersion: 1,
          experimentId: benchmarkExperimentId,
          items,
          nextCursor: Number(items.at(-1)?.sequence ?? after),
          highWaterMark,
          terminal:
            state.experiment.lifecycle === "terminal"
            && Number(items.at(-1)?.sequence ?? after) >= highWaterMark,
        });
      }
      if (url.includes("/task-runs")) {
        if (state.taskRunsFail) {
          return jsonResponse(
            {
              schemaVersion: 1,
              error: {
                code: "studio.task_runs.unavailable",
                message: "task runs unavailable",
              },
            },
            503,
          );
        }
        return jsonResponse({
          schemaVersion: 1,
          experimentId: benchmarkExperimentId,
          items: state.taskRuns,
          nextCursor: null,
        });
      }
      return jsonResponse(state.experiment);
    }),
  );
  return requests;
}

/** Render the Monitor and a durable Replay handoff target. */
function renderMonitor(
  path = `/experiments/${benchmarkExperimentId}`,
) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
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
          <Route
            path="/experiments/:experimentId"
            element={<ExperimentMonitorPage />}
          />
          <Route
            path="/experiments/:experimentId/report"
            element={<output>Durable Report route</output>}
          />
          <Route
            path="/runs/:runId/replay"
            element={<output>Durable Replay route</output>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  BrowserEventSource.instances = [];
  vi.stubGlobal("EventSource", BrowserEventSource);
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
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ExperimentMonitorPage", () => {
  it("offers Report navigation only from authoritative available publication", async () => {
    const fixture = benchmarkExperimentFixture();
    const state: BackendState = {
      experiment: {
        ...fixture,
        lifecycle: "terminal",
        terminalReason: "completed",
        terminalAt: 20,
        reportAvailability: "available",
        capabilities: {
          ...fixture.capabilities,
          cancelActive: false,
        },
        links: {
          ...fixture.links,
          cancel: null,
          report:
            `/studio/benchmark-experiments/${benchmarkExperimentId}/report`,
        },
      },
      taskRuns: [],
      events: [],
    };
    installMonitorBackend(state);
    renderMonitor();
    const report = await screen.findByRole("button", {
      name: "Open Report",
    });
    fireEvent.click(report);
    expect(await screen.findByText("Durable Report route")).not.toBeNull();
  });

  it("reconstructs plural facts, preserves historical selection, and renders no fake live evidence", async () => {
    const first = {
      ...benchmarkTaskRunFixture(0),
      lifecycle: "terminal",
      terminalReason: "completed",
      terminalAt: 8,
    };
    const second = benchmarkTaskRunFixture(1);
    const state: BackendState = {
      experiment: benchmarkExperimentFixture(),
      taskRuns: [first, second],
      events: [benchmarkEventFixture(1)],
    };
    const requests = installMonitorBackend(state);
    renderMonitor();

    expect(await screen.findByText("android-world")).not.toBeNull();
    expect(await screen.findByRole("button", { name: /task-1/ })).not.toBeNull();
    expect(screen.getByRole("button", { name: /task-2/ })).not.toBeNull();
    expect(screen.getByText(/live node activation unavailable/)).not.toBeNull();
    expect(screen.getAllByText("未采集截图").length).toBeGreaterThan(0);
    expect(screen.queryByText(/mock frame/i)).toBeNull();

    const historical = screen.getByRole("button", { name: /task-1/ });
    fireEvent.click(historical);
    expect(historical.getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(BrowserEventSource.instances).toHaveLength(1));
    act(() => {
      BrowserEventSource.instances[0]?.emit("open");
      BrowserEventSource.instances[0]?.emit(
        "journal",
        JSON.stringify(benchmarkEventFixture(2)),
      );
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /task-1/ }).getAttribute(
        "aria-pressed",
      )).toBe("true"),
    );
    expect(screen.getByRole("button", { name: "回到当前 TaskRun" })).not.toBeNull();
    expect(
      requests.some((item) => item.url.includes("/studio/runs")),
    ).toBe(false);
  });

  it("keeps a TaskRun query failure local and offers resource retry", async () => {
    installMonitorBackend({
      experiment: benchmarkExperimentFixture(),
      taskRuns: [],
      events: [],
      taskRunsFail: true,
    });
    renderMonitor();
    expect(await screen.findByText("android-world")).not.toBeNull();
    expect(await screen.findByText("task runs unavailable")).not.toBeNull();
    expect(screen.getByText("尚无 authoritative TaskRun。")).not.toBeNull();
    expect(
      screen.getByRole("button", { name: "重试 TaskRun 查询" }),
    ).not.toBeNull();
  });

  it("sends cancel only after confirmation and trusts the returned terminal resource", async () => {
    const accepted = {
      ...benchmarkExperimentFixture(),
      lifecycle: "accepted",
    };
    const requests = installMonitorBackend({
      experiment: accepted,
      taskRuns: [
        {
          ...benchmarkTaskRunFixture(0),
          lifecycle: "scheduled",
          startedAt: null,
        },
      ],
      events: [],
    });
    renderMonitor();
    const cancel = await screen.findByRole("button", {
      name: "Cancel Experiment",
    });
    fireEvent.click(cancel);
    expect(
      screen.getByRole("dialog", { name: "取消 accepted Experiment？" }),
    ).not.toBeNull();
    expect(
      requests.filter((item) => item.url.endsWith("/cancel")),
    ).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "确认取消" }));
    await waitFor(() =>
      expect(
        requests.filter((item) => item.url.endsWith("/cancel")),
      ).toHaveLength(1),
    );
    expect(
      requests.find((item) => item.url.endsWith("/cancel"))?.body,
    ).toMatchObject({ reasonCode: "user_requested" });
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Cancel Experiment" }),
      ).toBeNull(),
    );
    expect(screen.getAllByText("terminal").length).toBeGreaterThan(0);
  });

  it("never cancels on unmount and freezes a discontinuous durable prefix", async () => {
    const requests = installMonitorBackend({
      experiment: {
        ...benchmarkExperimentFixture(),
        lifecycle: "accepted",
      },
      taskRuns: [
        {
          ...benchmarkTaskRunFixture(0),
          lifecycle: "scheduled",
          startedAt: null,
        },
      ],
      events: [benchmarkEventFixture(2)],
    });
    const rendered = renderMonitor();
    expect(
      await screen.findByText(/最后验证前缀已冻结/),
    ).not.toBeNull();
    expect(
      screen.getByRole("button", { name: "显式重试" }),
    ).not.toBeNull();
    rendered.unmount();
    expect(
      requests.some((item) => item.url.endsWith("/cancel")),
    ).toBe(false);
    expect(BrowserEventSource.instances.every((source) => source.closed)).toBe(
      true,
    );
  });

  it("shows terminal Replay only from the TaskRun resource and navigates explicitly", async () => {
    const replayId = `benchmark-replay-${"d".repeat(32)}`;
    const terminalExperiment = {
      ...benchmarkExperimentFixture(),
      lifecycle: "terminal",
      terminalReason: "completed",
      terminalAt: 12,
      links: {
        ...benchmarkExperimentFixture().links,
        cancel: null,
      },
    };
    const terminalTask = {
      ...benchmarkTaskRunFixture(0),
      lifecycle: "terminal",
      terminalReason: "completed",
      terminalAt: 11,
      replayAvailability: "available",
      resultAvailability: "available",
      result: {
        schemaVersion: 1,
        evidenceOrigin: {
          schemaVersion: 1,
          acquisition: "contract_fixture",
          environment: "fake_device",
          deviceProfileId: "acceptance-fake",
          deviceChecks: [],
          realDeviceEvidence: false,
        },
      },
      replayId,
      links: {
        ...benchmarkTaskRunFixture(0).links,
        replay: `/studio/replays/${replayId}`,
      },
    };
    installMonitorBackend({
      experiment: terminalExperiment,
      taskRuns: [terminalTask],
      events: [
        {
          ...benchmarkEventFixture(1),
          kind: "experiment.terminal",
          source: "service",
        },
      ],
    });
    renderMonitor();
    const openReplay = await screen.findByRole("button", {
      name: "打开持久 Replay",
    });
    expect(screen.getByText("Supporting fake-device fixture")).not.toBeNull();
    expect(screen.getByText("fake_device")).not.toBeNull();
    expect(screen.queryByText("Durable Replay route")).toBeNull();
    fireEvent.click(openReplay);
    expect(await screen.findByText("Durable Replay route")).not.toBeNull();
  });

  it("renders invalid and not-found deep links without constructing Monitor state", async () => {
    renderMonitor("/experiments/not-an-experiment");
    expect(await screen.findByText("无效 Experiment 地址")).not.toBeNull();
    cleanup();

    installMonitorBackend({
      experiment: benchmarkExperimentFixture(),
      taskRuns: [],
      events: [],
      notFound: true,
    });
    renderMonitor();
    expect(await screen.findByText("Experiment 不存在")).not.toBeNull();
  });
});
