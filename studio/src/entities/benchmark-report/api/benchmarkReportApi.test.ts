import { afterEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkExperimentReportFixture,
  benchmarkReportInventoryFixture,
  benchmarkRunReportFixture,
  reportArtifactId,
  reportCoreTaskRunId,
  reportExperimentId,
  reportTaskRunId,
} from "../testing/benchmarkReport.fixtures";
import {
  BENCHMARK_REPORT_MAX_BYTES,
  getBenchmarkExperimentReport,
  getBenchmarkRunReport,
  listBenchmarkArtifactInventory,
} from "./benchmarkReportApi";
import { benchmarkReportKeys } from "./benchmarkReport.queries";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Benchmark reporting API", () => {
  it("loads inventory from an explicit reconstructible link", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        urls.push(String(input));
        return new Response(JSON.stringify(benchmarkReportInventoryFixture()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    const link = `/studio/benchmark-experiments/${reportExperimentId}/artifacts`;
    const inventory = await listBenchmarkArtifactInventory(
      reportExperimentId,
      link,
      "opaque-cursor",
      25,
    );
    expect(inventory.items).toHaveLength(1);
    expect(urls[0]).toContain("limit=25&cursor=opaque-cursor");
    expect(
      benchmarkReportKeys.inventory(
        reportExperimentId,
        link,
        25,
        "opaque-cursor",
      ),
    ).not.toEqual(
      benchmarkReportKeys.inventory(reportExperimentId, link, 25, null),
    );
  });

  it("follows explicit report links and preserves Core report authority", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const document = url.endsWith("/report")
          ? benchmarkExperimentReportFixture()
          : benchmarkRunReportFixture();
        return new Response(JSON.stringify(document), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    const experiment = await getBenchmarkExperimentReport(
      reportExperimentId,
      `/studio/benchmark-experiments/${reportExperimentId}/report`,
    );
    const run = await getBenchmarkRunReport(
      {
        experimentId: reportExperimentId,
        taskRunId: reportTaskRunId,
        coreTaskRunId: reportCoreTaskRunId,
        taskId: "task-1",
        agentId: "agent-1",
        repeat: 0,
      },
      `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
        + `${reportTaskRunId}/artifacts/${reportArtifactId}`,
    );
    expect(experiment.counts.pass).toBe(1);
    expect(run.evaluation?.children[0]?.evaluatorResult?.passed).toBe(true);
  });

  it("rejects declared and actual bodies beyond the 2 MiB limit", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("{}", {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Content-Length": String(BENCHMARK_REPORT_MAX_BYTES + 1),
          },
        }),
      ),
    );
    await expect(
      getBenchmarkExperimentReport(
        reportExperimentId,
        `/studio/benchmark-experiments/${reportExperimentId}/report`,
      ),
    ).rejects.toThrow(/browser text limit/);

    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(`"${"x".repeat(BENCHMARK_REPORT_MAX_BYTES)}"`, {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(
      getBenchmarkExperimentReport(
        reportExperimentId,
        `/studio/benchmark-experiments/${reportExperimentId}/report`,
      ),
    ).rejects.toThrow(/browser text limit/);
  });

  it("rejects safe-looking links with the wrong resource scope", async () => {
    await expect(
      getBenchmarkExperimentReport(
        reportExperimentId,
        `/studio/benchmark-experiments/${"f".repeat(32)}/report`,
      ),
    ).rejects.toThrow(/selected scope/);
    await expect(
      listBenchmarkArtifactInventory(
        reportExperimentId,
        `/studio/benchmark-experiments/${"f".repeat(32)}/artifacts`,
      ),
    ).rejects.toThrow(/Experiment scope/);
    await expect(
      getBenchmarkRunReport(
        {
          experimentId: reportExperimentId,
          taskRunId: reportTaskRunId,
          coreTaskRunId: reportCoreTaskRunId,
          taskId: "task-1",
          agentId: "agent-1",
          repeat: 0,
        },
        `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
          + `${reportTaskRunId}/artifacts/not-an-artifact`,
      ),
    ).rejects.toThrow(/selected scope/);
  });
});
