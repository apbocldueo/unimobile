import type { BenchmarkExperimentResource } from "@/entities/benchmark-experiment";
import type {
  BenchmarkAgentComparison,
  BenchmarkAgentMetric,
  BenchmarkExperimentReport,
  BenchmarkOutcome,
} from "@/entities/benchmark-report";

export const BENCHMARK_RESULTS_DEFAULT_PAGE_SIZE = 25;
export const BENCHMARK_RESULTS_MAX_PAGE_SIZE = 50;
export const BENCHMARK_SIGNIFICANCE_BOUNDARY =
  "Descriptive results only. No statistical significance is claimed.";

export const BENCHMARK_METRIC_DEFINITIONS = Object.freeze({
  micro:
    "Micro success is the PASS share across eligible TaskRuns reported by Core.",
  macro:
    "Macro success is the mean of per-Task success rates reported by Core.",
  duration:
    "Durations aggregate observable stage time for eligible TaskRuns.",
  variance:
    "Duration variance is the reported sample variance in milliseconds squared.",
  wilson:
    "Wilson 95% is the reported interval for eligible PASS/FAIL outcomes.",
  usage:
    "Usage coverage is the number of eligible runs with reported usage.",
});

export type BenchmarkOutcomeResult = {
  outcome: BenchmarkOutcome;
  label: string;
  count: number;
};

export type BenchmarkAgentMetricResult = {
  agentId: string;
  counts: BenchmarkAgentMetric["counts"];
  eligibleCount: number;
  successRateMicro: number | null;
  successRateMacro: number | null;
  durationMeanMs: number | null;
  durationMedianMs: number | null;
  durationSampleVariance: number | null;
  wilsonInterval95: [number, number] | null;
  usageAvailableRuns: number;
};

export type BenchmarkComparisonScope = "none" | "full" | "partial";

export type BenchmarkAgentComparisonResult = {
  leftAgentId: string;
  rightAgentId: string;
  paired: boolean;
  scope: BenchmarkComparisonScope;
  scopeLabel: string;
  matchedCount: number;
  unmatchedEligibleCount: number;
  leftWins: number;
  rightWins: number;
  ties: number;
  significanceClaimed: false;
};

export type BenchmarkFairnessWarningResult = {
  code: string;
  description: string;
  known: boolean;
};

export type BenchmarkExperimentResultsProjection = {
  identity: string;
  experimentId: string;
  schemaVersion: "1.0";
  outcomes: BenchmarkOutcomeResult[];
  agentMetrics: BenchmarkAgentMetricResult[];
  comparisons: BenchmarkAgentComparisonResult[];
  fairnessWarnings: BenchmarkFairnessWarningResult[];
  significanceClaimed: false;
  significanceBoundary: string;
};

export type BenchmarkResultsPage<T> = {
  items: T[];
  page: number;
  pageSize: number;
  pageCount: number;
  total: number;
  start: number;
  end: number;
};

const OUTCOME_LABELS: Readonly<Record<BenchmarkOutcome, string>> = Object.freeze({
  pass: "PASS",
  fail: "FAIL",
  invalid: "INVALID",
  skipped: "SKIPPED",
});

const FAIRNESS_DESCRIPTIONS: Readonly<Record<string, string>> = Object.freeze({
  "benchmark.protocol.unpaired_materialization":
    "Agents did not reuse the same TaskInstance materialization.",
  "benchmark.protocol.shared_device_state_across_agents":
    "Device state may have been shared across Agents.",
});

/** Format a finite display number without changing its source value. */
function formatFiniteNumber(value: number): string {
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

/** Format one nullable report rate as a deterministic percentage. */
export function formatBenchmarkRate(value: number | null): string {
  return value === null ? "Unavailable" : `${(value * 100).toFixed(1)}%`;
}

/** Format one nullable report duration in milliseconds. */
export function formatBenchmarkDuration(value: number | null): string {
  return value === null ? "Unavailable" : `${formatFiniteNumber(value)} ms`;
}

/** Format one nullable report sample variance in milliseconds squared. */
export function formatBenchmarkVariance(value: number | null): string {
  return value === null ? "Unavailable" : `${formatFiniteNumber(value)} ms²`;
}

/** Format one nullable backend-provided Wilson interval without recomputing it. */
export function formatBenchmarkWilsonInterval(
  value: [number, number] | null,
): string {
  return value === null
    ? "Unavailable"
    : `[${formatBenchmarkRate(value[0])}, ${formatBenchmarkRate(value[1])}]`;
}

/** Format reported usage coverage against the explicit eligible denominator. */
export function formatBenchmarkUsageCoverage(
  usageAvailableRuns: number,
  eligibleCount: number,
): string {
  return `${usageAvailableRuns} / ${eligibleCount} eligible`;
}

/** Classify only the matched scope already represented by a comparison row. */
export function classifyBenchmarkComparisonScope(
  comparison: BenchmarkAgentComparison,
): BenchmarkComparisonScope {
  if (comparison.matchedCount === 0) return "none";
  return comparison.unmatchedEligibleCount === 0 ? "full" : "partial";
}

/** Return a neutral reader label for a literal matched comparison scope. */
export function benchmarkComparisonScopeLabel(
  scope: BenchmarkComparisonScope,
): string {
  if (scope === "full") return "Fully matched eligible samples";
  if (scope === "partial") return "Partially matched eligible samples";
  return "No matched TaskInstance samples";
}

/** Attach schema-1.0 help text while retaining every original warning code. */
export function describeBenchmarkFairnessWarning(
  code: string,
): BenchmarkFairnessWarningResult {
  const description = FAIRNESS_DESCRIPTIONS[code];
  return {
    code,
    description:
      description ?? "Description unavailable for this report warning code.",
    known: description !== undefined,
  };
}

/** Project authoritative Experiment report facts into a presentation-only model. */
export function projectBenchmarkExperimentResults(
  experiment: BenchmarkExperimentResource,
  report: BenchmarkExperimentReport,
): BenchmarkExperimentResultsProjection {
  if (
    report.experimentId !== experiment.experimentId
    || report.benchmarkPlanIdentity
      !== experiment.definition.source.benchmarkPlanIdentity
    || report.experimentProtocolIdentity
      !== experiment.definition.source.experimentProtocolIdentity
  ) {
    throw new Error("Experiment results conflict with immutable definition");
  }
  const outcomes = (Object.keys(OUTCOME_LABELS) as BenchmarkOutcome[]).map(
    (outcome): BenchmarkOutcomeResult => ({
      outcome,
      label: OUTCOME_LABELS[outcome],
      count: report.counts[outcome],
    }),
  );
  const comparisons = report.comparisons.map(
    (comparison): BenchmarkAgentComparisonResult => {
      const scope = classifyBenchmarkComparisonScope(comparison);
      return {
        ...comparison,
        scope,
        scopeLabel: benchmarkComparisonScopeLabel(scope),
      };
    },
  );
  return {
    identity: [
      report.experimentId,
      report.benchmarkPlanIdentity,
      report.experimentProtocolIdentity,
    ].join(":"),
    experimentId: report.experimentId,
    schemaVersion: report.schemaVersion,
    outcomes,
    agentMetrics: report.agentMetrics.map((metric) => ({ ...metric })),
    comparisons,
    fairnessWarnings: report.fairnessWarnings.map(
      describeBenchmarkFairnessWarning,
    ),
    significanceClaimed: report.significanceClaimed,
    significanceBoundary: BENCHMARK_SIGNIFICANCE_BOUNDARY,
  };
}

/** Page a stable report collection with a hard mounted-row upper bound. */
export function paginateBenchmarkResults<T>(
  items: readonly T[],
  requestedPage: number,
  requestedPageSize = BENCHMARK_RESULTS_DEFAULT_PAGE_SIZE,
): BenchmarkResultsPage<T> {
  const pageSize =
    Number.isInteger(requestedPageSize) && requestedPageSize > 0
      ? Math.min(requestedPageSize, BENCHMARK_RESULTS_MAX_PAGE_SIZE)
      : BENCHMARK_RESULTS_DEFAULT_PAGE_SIZE;
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const page =
    Number.isInteger(requestedPage) && requestedPage > 0
      ? Math.min(requestedPage, pageCount)
      : 1;
  const start = (page - 1) * pageSize;
  const end = Math.min(start + pageSize, items.length);
  return {
    items: items.slice(start, end),
    page,
    pageSize,
    pageCount,
    total: items.length,
    start: items.length === 0 ? 0 : start + 1,
    end,
  };
}
