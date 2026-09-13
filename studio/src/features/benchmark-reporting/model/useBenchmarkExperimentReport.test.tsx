import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkDefinitionFixture,
  benchmarkExperimentFixture,
  benchmarkTaskRunFixture,
} from "@/entities/benchmark-experiment";
import {
  benchmarkExperimentReportFixture,
  benchmarkReportInventoryFixture,
  benchmarkRunReportFixture,
  reportCoreTaskRunId,
  reportExperimentId,
} from "@/entities/benchmark-report";
import { useBenchmarkExperimentReport } from "./useBenchmarkExperimentReport";

type ReportBackend = {
  taskRunsFail?: boolean;
  runReportCorrupt?: boolean;
  experimentReportCorrupt?: boolean;
  nullEvaluation?: boolean;
  inventoryPages?: Array<Record<string, unknown>>;
};

/** Build a terminal Experiment whose immutable identities match publication. */
function reportExperimentFixture() {
  const fixture = benchmarkExperimentFixture();
  const definition = benchmarkDefinitionFixture();
  const hash = benchmarkRunReportFixture().identities.benchmark_plan;
  definition.source.benchmarkPlanIdentity = hash;
  definition.source.experimentProtocolIdentity = hash;
  definition.agentSnapshots[0]!.canonicalHash = hash;
  return {
    ...fixture,
    definition,
    lifecycle: "terminal",
    terminalReason: "completed",
    terminalAt: 9,
    reportAvailability: "available",
    capabilities: { ...fixture.capabilities, cancelActive: false },
    links: {
      ...fixture.links,
      cancel: null,
      artifacts:
        `/studio/benchmark-experiments/${reportExperimentId}/artifacts`,
      report:
        `/studio/benchmark-experiments/${reportExperimentId}/report`,
    },
  };
}

/** Build a terminal Studio TaskRun joined to the published Core run. */
function reportTaskRunFixture() {
  const fixture = benchmarkTaskRunFixture();
  const replayId = `benchmark-replay-${"d".repeat(32)}`;
  return {
    ...fixture,
    lifecycle: "terminal",
    terminalReason: "completed",
    terminalAt: 9,
    coreTaskRunId: reportCoreTaskRunId,
    taskInstanceIdentity: benchmarkRunReportFixture().identities.task_instance,
    agentStatus: "success",
    benchmarkOutcome: "pass",
    outcomeAvailability: "available",
    reportAvailability: "available",
    replayAvailability: "available",
    replayId,
    links: {
      ...fixture.links,
      artifacts: "/studio/artifacts",
      replay: `/studio/replays/${replayId}`,
    },
  };
}

/** Return one JSON response for the deterministic report backend. */
function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Install a fetch backend with independently failing report dependencies. */
function installReportBackend(state: ReportBackend) {
  const requests: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url.includes("/task-runs?") || url.endsWith("/task-runs")) {
        if (state.taskRunsFail) {
          return response(
            { error: { code: "task-runs.failed", message: "failed" } },
            503,
          );
        }
        return response({
          schemaVersion: 1,
          experimentId: reportExperimentId,
          items: [reportTaskRunFixture()],
          nextCursor: null,
        });
      }
      if (url.includes("/task-runs/") && url.includes("/artifacts/")) {
        if (state.runReportCorrupt) {
          return response(
            {
              error: {
                code: "benchmark.artifact.corrupt",
                message: "corrupt",
              },
            },
            409,
          );
        }
        const runReport = benchmarkRunReportFixture();
        return response({
          ...runReport,
          evaluation: state.nullEvaluation ? null : runReport.evaluation,
        });
      }
      if (url.includes("/artifacts?")) {
        const cursor = new URL(url, "http://studio.test").searchParams.get(
          "cursor",
        );
        const pageIndex = cursor === null ? 0 : Number(cursor);
        return response(
          state.inventoryPages?.[pageIndex]
          ?? benchmarkReportInventoryFixture(),
        );
      }
      if (url.endsWith("/report")) {
        if (state.experimentReportCorrupt) {
          return response(
            {
              error: {
                code: "benchmark.artifact.corrupt",
                message: "corrupt",
              },
            },
            409,
          );
        }
        return response(benchmarkExperimentReportFixture());
      }
      return response(reportExperimentFixture());
    }),
  );
  return requests;
}

/** Create an isolated Query client wrapper for one hook reconstruction. */
function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function ReportQueryWrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useBenchmarkExperimentReport", () => {
  it("reconstructs an available report and native Replay from durable resources", async () => {
    const requests = installReportBackend({});
    const { result } = renderHook(
      () => useBenchmarkExperimentReport(reportExperimentId, null),
      { wrapper: wrapper() },
    );
    await waitFor(() => {
      expect(result.current.states.runReport.kind).toBe("available");
    });
    expect(result.current.selection?.selectedTaskRunId).toBe(
      reportTaskRunFixture().taskRunId,
    );
    expect(result.current.states.evaluation.kind).toBe("available");
    expect(result.current.states.replay.kind).toBe("available");
    expect(result.current.states.aggregate.kind).toBe("available");
    expect(result.current.aggregate?.data?.agentMetrics).toHaveLength(1);
    expect(requests.some((url) => url.includes("/events"))).toBe(false);
  });

  it("preserves Experiment report summaries when the TaskRun page fails", async () => {
    installReportBackend({ taskRunsFail: true });
    const { result } = renderHook(
      () => useBenchmarkExperimentReport(reportExperimentId, null),
      { wrapper: wrapper() },
    );
    await waitFor(() => {
      expect(result.current.states.publication.kind).toBe("available");
    });
    expect(result.current.states.taskRuns.kind).toBe("failed");
    expect(result.current.runProjection?.data?.[0]?.taskRun).toBeNull();
    expect(result.current.states.aggregate.kind).toBe("available");
    expect(result.current.aggregate?.data?.outcomes[0]?.count).toBe(1);
    expect(result.current.states.replay.kind).toBe("unavailable");
  });

  it("rejects stale TaskRun report content after an integrity failure", async () => {
    const state: ReportBackend = {};
    installReportBackend(state);
    const { result } = renderHook(
      () => useBenchmarkExperimentReport(reportExperimentId, null),
      { wrapper: wrapper() },
    );
    await waitFor(() => {
      expect(result.current.states.runReport.kind).toBe("available");
    });
    state.runReportCorrupt = true;
    await result.current.runReport.refetch();
    await waitFor(() => {
      expect(result.current.states.runReport.kind).toBe("corrupt");
    });
    expect(result.current.runDetail).toBeNull();
    expect(result.current.states.aggregate.kind).toBe("available");
    expect(result.current.aggregate?.data?.agentMetrics).toHaveLength(1);
  });

  it("keeps aggregate facts independent of TaskRun selection and null Evaluation", async () => {
    installReportBackend({ nullEvaluation: true });
    const { result, rerender } = renderHook(
      ({ selected }: { selected: string | null }) =>
        useBenchmarkExperimentReport(reportExperimentId, selected),
      {
        initialProps: { selected: null as string | null },
        wrapper: wrapper(),
      },
    );
    await waitFor(() => {
      expect(result.current.states.aggregate.kind).toBe("available");
      expect(result.current.states.evaluation.kind).toBe("unavailable");
    });
    const aggregate = result.current.aggregate?.data;
    rerender({ selected: reportTaskRunFixture().taskRunId });
    expect(result.current.aggregate?.data).toBe(aggregate);
    expect(result.current.states.aggregate.kind).toBe("available");
  });

  it("removes stale aggregate facts after Experiment report integrity failure", async () => {
    const state: ReportBackend = {};
    installReportBackend(state);
    const { result } = renderHook(
      () => useBenchmarkExperimentReport(reportExperimentId, null),
      { wrapper: wrapper() },
    );
    await waitFor(() => {
      expect(result.current.states.aggregate.kind).toBe("available");
    });
    state.experimentReportCorrupt = true;
    await result.current.experimentReport.refetch();
    await waitFor(() => {
      expect(result.current.states.aggregate.kind).toBe("corrupt");
    });
    expect(result.current.aggregate).toBeNull();
    expect(result.current.states.experiment.kind).toBe("available");
  });
});
