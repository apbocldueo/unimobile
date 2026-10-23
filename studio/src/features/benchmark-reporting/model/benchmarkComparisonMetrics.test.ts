import { describe, expect, it } from "vitest";
import {
  benchmarkDefinitionFixture,
  benchmarkExperimentFixture,
  parseBenchmarkExperimentResource,
} from "@/entities/benchmark-experiment";
import {
  comparisonMetricsExperimentReportFixture,
  multiAgentExperimentReportFixture,
  parseBenchmarkExperimentReport,
  reportHash,
} from "@/entities/benchmark-report";
import {
  BENCHMARK_RESULTS_MAX_PAGE_SIZE,
  BENCHMARK_SIGNIFICANCE_BOUNDARY,
  describeBenchmarkFairnessWarning,
  formatBenchmarkDuration,
  formatBenchmarkRate,
  formatBenchmarkUsageCoverage,
  formatBenchmarkVariance,
  formatBenchmarkWilsonInterval,
  paginateBenchmarkResults,
  projectBenchmarkExperimentResults,
} from "./benchmarkComparisonMetrics";

/** Build an immutable Experiment resource matching the formal report fixtures. */
function matchingExperiment() {
  const fixture = benchmarkExperimentFixture();
  const definition = benchmarkDefinitionFixture();
  definition.source.benchmarkPlanIdentity = reportHash;
  definition.source.experimentProtocolIdentity = reportHash;
  return parseBenchmarkExperimentResource({ ...fixture, definition });
}

describe("Benchmark comparison metrics", () => {
  it("projects formal outcome and per-Agent facts without deriving totals", () => {
    const report = parseBenchmarkExperimentReport(
      comparisonMetricsExperimentReportFixture(),
    );
    const projection = projectBenchmarkExperimentResults(
      matchingExperiment(),
      report,
    );
    expect(projection.outcomes.map((item) => [item.label, item.count])).toEqual([
      ["PASS", 1],
      ["FAIL", 1],
      ["INVALID", 1],
      ["SKIPPED", 1],
    ]);
    expect(projection).not.toHaveProperty("eligibleCount");
    expect(projection.agentMetrics[0]).toMatchObject({
      agentId: "agent-1",
      eligibleCount: 1,
      successRateMicro: 1,
      durationMeanMs: 0,
      durationSampleVariance: 0,
    });
    expect(projection.agentMetrics[2]).toMatchObject({
      agentId: "agent-3",
      eligibleCount: 0,
      successRateMicro: null,
      successRateMacro: null,
    });
  });

  it("formats zero and unavailable as distinct report facts", () => {
    expect(formatBenchmarkRate(0)).toBe("0.0%");
    expect(formatBenchmarkRate(null)).toBe("Unavailable");
    expect(formatBenchmarkDuration(0)).toBe("0 ms");
    expect(formatBenchmarkDuration(null)).toBe("Unavailable");
    expect(formatBenchmarkVariance(0)).toBe("0 ms²");
    expect(formatBenchmarkVariance(null)).toBe("Unavailable");
    expect(formatBenchmarkWilsonInterval([0, 0.8])).toBe("[0.0%, 80.0%]");
    expect(formatBenchmarkWilsonInterval(null)).toBe("Unavailable");
    expect(formatBenchmarkUsageCoverage(0, 1)).toBe("0 / 1 eligible");
  });

  it("keeps full, partial, and absent matched scopes descriptive", () => {
    const full = projectBenchmarkExperimentResults(
      matchingExperiment(),
      parseBenchmarkExperimentReport(multiAgentExperimentReportFixture()),
    );
    const edge = projectBenchmarkExperimentResults(
      matchingExperiment(),
      parseBenchmarkExperimentReport(
        comparisonMetricsExperimentReportFixture(),
      ),
    );
    expect(full.comparisons[0]).toMatchObject({
      scope: "full",
      matchedCount: 1,
      unmatchedEligibleCount: 0,
      significanceClaimed: false,
    });
    expect(edge.comparisons.map((item) => item.scope)).toEqual([
      "partial",
      "none",
    ]);
    expect(edge.significanceBoundary).toBe(BENCHMARK_SIGNIFICANCE_BOUNDARY);
    expect(edge).not.toHaveProperty("winner");
  });

  it("describes known fairness warnings and safely retains unknown codes", () => {
    expect(
      describeBenchmarkFairnessWarning(
        "benchmark.protocol.unpaired_materialization",
      ),
    ).toMatchObject({ known: true });
    expect(
      describeBenchmarkFairnessWarning(
        "benchmark.protocol.synthetic_unknown_warning",
      ),
    ).toEqual({
      code: "benchmark.protocol.synthetic_unknown_warning",
      description: "Description unavailable for this report warning code.",
      known: false,
    });
  });

  it("bounds mounted rows and preserves the original collection order", () => {
    const rows = Array.from({ length: 125 }, (_, index) => `agent-${index}`);
    const first = paginateBenchmarkResults(rows, 1, 500);
    const third = paginateBenchmarkResults(rows, 3, 500);
    expect(first.pageSize).toBe(BENCHMARK_RESULTS_MAX_PAGE_SIZE);
    expect(first.items).toEqual(rows.slice(0, 50));
    expect(third.items).toEqual(rows.slice(100, 125));
    expect(third).toMatchObject({
      page: 3,
      pageCount: 3,
      start: 101,
      end: 125,
      total: 125,
    });
    expect(paginateBenchmarkResults(rows, 99, 25).page).toBe(5);
    expect(paginateBenchmarkResults([], 3)).toMatchObject({
      page: 1,
      pageCount: 1,
      start: 0,
      end: 0,
    });
  });

  it("fails closed when the report conflicts with immutable identities", () => {
    const report = parseBenchmarkExperimentReport(
      comparisonMetricsExperimentReportFixture(),
    );
    const experiment = matchingExperiment();
    experiment.definition.source.benchmarkPlanIdentity =
      `sha256:${"f".repeat(64)}`;
    expect(() =>
      projectBenchmarkExperimentResults(experiment, report),
    ).toThrow(/immutable definition/);
  });
});
