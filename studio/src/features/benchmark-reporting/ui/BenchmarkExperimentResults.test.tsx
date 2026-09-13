import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  benchmarkDefinitionFixture,
  benchmarkExperimentFixture,
  parseBenchmarkExperimentResource,
} from "@/entities/benchmark-experiment";
import {
  benchmarkExperimentReportFixture,
  comparisonMetricsExperimentReportFixture,
  parseBenchmarkExperimentReport,
  reportHash,
} from "@/entities/benchmark-report";
import {
  projectBenchmarkExperimentResults,
  type BenchmarkExperimentResultsProjection,
} from "../model/benchmarkComparisonMetrics";
import { benchmarkReportState } from "../model/benchmarkReportState";
import { BenchmarkExperimentResults as BenchmarkExperimentResultsView } from "./BenchmarkExperimentResults";

/** Build an immutable Experiment resource matching formal report fixtures. */
function matchingExperiment() {
  const fixture = benchmarkExperimentFixture();
  const definition = benchmarkDefinitionFixture();
  definition.source.benchmarkPlanIdentity = reportHash;
  definition.source.experimentProtocolIdentity = reportHash;
  return parseBenchmarkExperimentResource({ ...fixture, definition });
}

/** Project one synthetic aggregate report through the production model. */
function edgeResults(): BenchmarkExperimentResultsProjection {
  return projectBenchmarkExperimentResults(
    matchingExperiment(),
    parseBenchmarkExperimentReport(
      comparisonMetricsExperimentReportFixture(),
    ),
  );
}

/** Render one available Experiment Results region. */
function renderResults(results = edgeResults()) {
  return render(
    <BenchmarkExperimentResultsView
      results={results}
      state={benchmarkReportState("available", "available")}
      onRetry={() => undefined}
    />,
  );
}

afterEach(cleanup);

describe("BenchmarkExperimentResults", () => {
  it("renders zero, null, paired scope, fairness, and inference boundaries", () => {
    const { container } = renderResults();
    expect(screen.getByText("PASS")).not.toBeNull();
    expect(screen.getByText("SKIPPED")).not.toBeNull();
    expect(screen.getAllByText("0.0%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Partially matched eligible samples"),
    ).not.toBeNull();
    expect(screen.getByText("No matched TaskInstance samples")).not.toBeNull();
    expect(
      screen.getByText("benchmark.protocol.unpaired_materialization"),
    ).not.toBeNull();
    expect(
      screen.getByText("benchmark.protocol.synthetic_unknown_warning"),
    ).not.toBeNull();
    expect(
      screen.getByText(
        "Descriptive results only. No statistical significance is claimed.",
      ),
    ).not.toBeNull();
    expect(container.textContent?.toLowerCase()).not.toContain("leaderboard");
    expect(container.textContent?.toLowerCase()).not.toContain("winner");
    expect(container.textContent?.toLowerCase()).not.toContain("is better");
  });

  it("treats an empty single-Agent comparison as valid report data", () => {
    const results = projectBenchmarkExperimentResults(
      matchingExperiment(),
      parseBenchmarkExperimentReport(benchmarkExperimentReportFixture()),
    );
    renderResults(results);
    expect(
      screen.getByText("No Agent pair is available to compare in this report."),
    ).not.toBeNull();
    expect(screen.queryByRole("table", {
      name: "Pairwise comparisons",
    })).toBeNull();
  });

  it("keeps the significance boundary visible when details collapse", () => {
    renderResults();
    fireEvent.click(screen.getByRole("button", { name: "Collapse details" }));
    expect(screen.queryByRole("table", { name: "Per-Agent metrics" })).toBeNull();
    expect(
      screen.getByText(
        "Descriptive results only. No statistical significance is claimed.",
      ),
    ).not.toBeNull();
    expect(
      screen.getByRole("button", { name: "Expand details" })
        .getAttribute("aria-expanded"),
    ).toBe("false");
  });

  it("paginates metrics and comparisons independently and resets on identity", () => {
    const base = edgeResults();
    const large: BenchmarkExperimentResultsProjection = {
      ...base,
      identity: `${base.identity}:large-a`,
      agentMetrics: Array.from({ length: 60 }, (_, index) => ({
        ...base.agentMetrics[0]!,
        agentId: `agent-metric-${index.toString().padStart(2, "0")}`,
      })),
      comparisons: Array.from({ length: 60 }, (_, index) => ({
        ...base.comparisons[0]!,
        leftAgentId: `agent-left-${index.toString().padStart(2, "0")}`,
        rightAgentId: `agent-right-${index.toString().padStart(2, "0")}`,
      })),
    };
    const view = renderResults(large);
    const metricTable = screen.getByRole("table", { name: "Per-Agent metrics" });
    expect(within(metricTable).getAllByRole("row")).toHaveLength(26);
    expect(screen.getByText("agent-metric-00")).not.toBeNull();
    expect(screen.queryByText("agent-metric-25")).toBeNull();

    fireEvent.click(screen.getByRole("button", {
      name: "Next Agent metrics page",
    }));
    expect(screen.getByText("agent-metric-25")).not.toBeNull();
    expect(
      within(
        screen.getByRole("navigation", {
          name: "Pairwise comparisons pagination",
        }),
      ).getByText("1/3"),
    ).not.toBeNull();

    fireEvent.click(screen.getByRole("button", {
      name: "Next Pairwise comparisons page",
    }));
    expect(screen.getByText("agent-left-25")).not.toBeNull();

    view.rerender(
      <BenchmarkExperimentResultsView
        results={{ ...large, identity: `${base.identity}:large-b` }}
        state={benchmarkReportState("available", "available")}
        onRetry={() => undefined}
      />,
    );
    expect(screen.getByText("agent-metric-00")).not.toBeNull();
    expect(screen.queryByText("agent-metric-25")).toBeNull();
    expect(screen.getByText("agent-left-00")).not.toBeNull();
    expect(screen.queryByText("agent-left-25")).toBeNull();
  });

  it("renders local unavailable state without stale result rows", () => {
    render(
      <BenchmarkExperimentResultsView
        results={edgeResults()}
        state={benchmarkReportState(
          "corrupt",
          "Published evidence failed its integrity check.",
          true,
        )}
        onRetry={() => undefined}
      />,
    );
    expect(
      screen.getByText("Published evidence failed its integrity check."),
    ).not.toBeNull();
    expect(screen.queryByRole("table", { name: "Per-Agent metrics" })).toBeNull();
    expect(
      screen.getByRole("button", { name: "Retry Experiment report" }),
    ).not.toBeNull();
  });
});
