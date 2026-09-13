import {
  parseBenchmarkArtifactDescriptor,
  type BenchmarkArtifactDescriptor,
} from "@/entities/benchmark-experiment";
import {
  cloneJson,
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
  type JsonValue,
} from "@/shared/lib";

export type BenchmarkOutcome = "pass" | "fail" | "invalid" | "skipped";
export type BenchmarkOutcomeCounts = Record<BenchmarkOutcome, number>;

export type BenchmarkArtifactInventoryItem = {
  schemaVersion: 1;
  descriptor: BenchmarkArtifactDescriptor;
  links: { content: string | null };
};

export type BenchmarkArtifactInventoryPage = {
  schemaVersion: 1;
  experimentId: string;
  items: BenchmarkArtifactInventoryItem[];
  hiddenCount: number;
  nextCursor: string | null;
};

export type BenchmarkRunSummary = {
  coreTaskRunId: string;
  taskId: string;
  agentId: string;
  repeat: number;
  outcome: BenchmarkOutcome;
  reportRef: string;
  trajectoryRef: string;
};

export type BenchmarkAgentMetric = {
  agentId: string;
  counts: BenchmarkOutcomeCounts;
  eligibleCount: number;
  successRateMicro: number | null;
  successRateMacro: number | null;
  durationMeanMs: number | null;
  durationMedianMs: number | null;
  durationSampleVariance: number | null;
  wilsonInterval95: [number, number] | null;
  usageAvailableRuns: number;
};

export type BenchmarkAgentComparison = {
  leftAgentId: string;
  rightAgentId: string;
  paired: boolean;
  matchedCount: number;
  unmatchedEligibleCount: number;
  leftWins: number;
  rightWins: number;
  ties: number;
  significanceClaimed: false;
};

export type BenchmarkExperimentReport = {
  schemaVersion: "1.0";
  kind: "benchmark_experiment_report";
  experimentId: string;
  benchmarkPlanIdentity: string;
  experimentProtocolIdentity: string;
  counts: BenchmarkOutcomeCounts;
  agentMetrics: BenchmarkAgentMetric[];
  comparisons: BenchmarkAgentComparison[];
  runSummaries: BenchmarkRunSummary[];
  fairnessWarnings: string[];
  significanceClaimed: false;
};

export type BenchmarkReportStage = {
  phase: string;
  status: BenchmarkStageStatus;
  durationMs: number;
  errorCode: string;
  message: string;
  evidence: JsonValue;
  artifactRefs: string[];
};

export type BenchmarkEvaluationUsage = {
  availability: "available" | "unavailable";
  promptTokens: number | null;
  completionTokens: number | null;
  totalTokens: number | null;
};

export type BenchmarkEvaluationEvidence = {
  kind: string;
  value: JsonValue;
  artifactRef: string;
  metadata: JsonValue;
};

export type BenchmarkEvaluatorResult = {
  schemaVersion: "2.0";
  evaluatorId: string;
  status: "completed" | "error" | "invalid" | "skipped";
  passed: boolean | null;
  score: number | null;
  reason: string;
  durationMs: number;
  usage: BenchmarkEvaluationUsage;
  evidence: BenchmarkEvaluationEvidence[];
  metadata: JsonValue;
  errorCode: string;
};

export type BenchmarkStageStatus =
  | "pending"
  | "running"
  | "success"
  | "failure"
  | "skipped"
  | "unverified";

export type BenchmarkEvaluationNode = {
  path: string;
  name: string;
  status: BenchmarkStageStatus;
  isPass: boolean | null;
  reason: string;
  token: number | null | "<redacted>";
  score: number | null;
  durationMs: number;
  evidence: JsonValue;
  aggregation: JsonValue;
  evaluatorResult: BenchmarkEvaluatorResult | null;
  shortCircuited: boolean;
  children: BenchmarkEvaluationNode[];
};

export type BenchmarkRunReport = {
  schemaVersion: "1.0";
  kind: "benchmark_run_report";
  coreTaskRunId: string;
  experimentId: string;
  taskId: string;
  agentId: string;
  repeat: number;
  outcome: BenchmarkOutcome;
  identities: {
    agentGraph: string;
    benchmarkPlan: string;
    experimentProtocol: string;
    taskInstance: string;
  };
  stages: BenchmarkReportStage[];
  evaluation: BenchmarkEvaluationNode | null;
  usage: JsonValue;
  artifactNamespace: string;
};

export type BenchmarkRunReportScope = {
  experimentId: string;
  taskRunId: string;
  coreTaskRunId: string;
  taskId: string;
  agentId: string;
  repeat: number;
};

const EXPERIMENT_ID = /^experiment-[a-f0-9]{32}$/;
const CORE_TASK_RUN_ID = /^[a-f0-9]{32}$/;
const HASH = /^sha256:[a-f0-9]{64}$/;
const OUTCOMES = new Set<BenchmarkOutcome>([
  "pass",
  "fail",
  "invalid",
  "skipped",
]);
const STAGE_STATUSES = new Set<BenchmarkStageStatus>([
  "pending",
  "running",
  "success",
  "failure",
  "skipped",
  "unverified",
]);
const EVALUATOR_STATUSES = new Set([
  "completed",
  "error",
  "invalid",
  "skipped",
] as const);
const READABLE_AVAILABILITIES = new Set([
  "available",
  "redacted",
  "truncated",
]);
const MAX_PAGE_ITEMS = 100;
const MAX_REPORT_MEMBERS = 2000;
const MAX_EVALUATION_DEPTH = 32;
const MAX_EVALUATION_NODES = 2000;
const MAX_STAGE_COUNT = 100;
const MAX_CHILDREN = 50;
const MAX_EVIDENCE_ITEMS = 100;
const MAX_TEXT = 1000;
const MAX_REFERENCE = 1024;

/** Require a strict boolean. */
function requireBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${path} must be a boolean`);
  return value;
}

/** Require a non-negative integer. */
function requireNonNegativeInteger(value: unknown, path: string): number {
  const parsed = requireNumber(value, path);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`${path} must be a non-negative integer`);
  }
  return parsed;
}

/** Require a bounded string. */
function requireBoundedString(
  value: unknown,
  path: string,
  maxLength = MAX_TEXT,
  allowEmpty = false,
): string {
  if (typeof value !== "string") {
    throw new Error(`${path} must be a string`);
  }
  const parsed = value;
  if ((!allowEmpty && parsed.length === 0) || parsed.length > maxLength) {
    throw new Error(`${path} has invalid text length`);
  }
  return parsed;
}

/** Parse a nullable finite number with an optional non-negative bound. */
function nullableNumber(
  value: unknown,
  path: string,
  nonNegative = false,
): number | null {
  if (value === null || value === undefined) return null;
  const parsed = requireNumber(value, path);
  if (nonNegative && parsed < 0) {
    throw new Error(`${path} must be non-negative`);
  }
  return parsed;
}

/** Parse a nullable normalized rate. */
function nullableRate(value: unknown, path: string): number | null {
  const parsed = nullableNumber(value, path);
  if (parsed !== null && (parsed < 0 || parsed > 1)) {
    throw new Error(`${path} must be within zero and one`);
  }
  return parsed;
}

/** Parse a Core Evaluation token after authoritative safe export. */
function parseEvaluationToken(
  value: unknown,
  path: string,
): number | null | "<redacted>" {
  if (value === "<redacted>") return value;
  return nullableNumber(value, path);
}

/** Parse a canonical hash without coercion. */
function parseHash(value: unknown, path: string): string {
  const parsed = requireString(value, path);
  if (!HASH.test(parsed)) throw new Error(`${path} must be a SHA-256 identity`);
  return parsed;
}

/** Parse one Benchmark outcome. */
function parseOutcome(value: unknown, path: string): BenchmarkOutcome {
  if (typeof value !== "string" || !OUTCOMES.has(value as BenchmarkOutcome)) {
    throw new Error(`${path} has an unsupported outcome`);
  }
  return value as BenchmarkOutcome;
}

/** Parse one Benchmark stage status. */
function parseStageStatus(value: unknown, path: string): BenchmarkStageStatus {
  if (
    typeof value !== "string"
    || !STAGE_STATUSES.has(value as BenchmarkStageStatus)
  ) {
    throw new Error(`${path} has an unsupported stage status`);
  }
  return value as BenchmarkStageStatus;
}

/** Parse a safe relative Core causal reference, never a URL. */
function parseCausalReference(value: unknown, path: string): string {
  const reference = requireBoundedString(value, path, MAX_REFERENCE);
  if (
    reference.startsWith("/")
    || reference.startsWith("\\")
    || /^[A-Za-z]:[\\/]/.test(reference)
    || reference.includes("\\")
    || reference.split("/").includes("..")
  ) {
    throw new Error(`${path} must be a safe relative causal reference`);
  }
  return reference;
}

/** Require an explicit Studio link to match one exact scoped route. */
function parseExactContentLink(
  value: unknown,
  expected: string,
  path: string,
): string {
  const link = requireString(value, path);
  const normalized = link.startsWith("/api/") ? link.slice(4) : link;
  if (
    normalized !== expected
    || (!link.startsWith("/studio/") && !link.startsWith("/api/studio/"))
  ) {
    throw new Error(
      `${path} does not match the expected artifact scope `
      + `(${normalized} != ${expected})`,
    );
  }
  return link;
}

/** Clone bounded auxiliary JSON without allowing resource exhaustion. */
function boundedJson(
  value: unknown,
  path: string,
  depth = 0,
  budget = { nodes: 0 },
): JsonValue {
  budget.nodes += 1;
  if (budget.nodes > MAX_EVALUATION_NODES || depth > 16) {
    throw new Error(`${path} exceeds bounded JSON complexity`);
  }
  if (typeof value === "string" && value.length > 10_000) {
    throw new Error(`${path} text is too large`);
  }
  if (Array.isArray(value) && value.length > 500) {
    throw new Error(`${path} has too many members`);
  }
  if (isRecord(value) && Object.keys(value).length > 500) {
    throw new Error(`${path} has too many fields`);
  }
  if (Array.isArray(value)) {
    return value.map((item, index) =>
      boundedJson(item, `${path}[${index}]`, depth + 1, budget),
    );
  }
  if (isRecord(value)) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        boundedJson(item, `${path}.${key}`, depth + 1, budget),
      ]),
    );
  }
  return cloneJson(value, path);
}

/** Parse exact PASS/FAIL/INVALID/SKIPPED counts. */
function parseOutcomeCounts(
  value: unknown,
  path: string,
): BenchmarkOutcomeCounts {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["pass", "fail", "invalid", "skipped"], path);
  return {
    pass: requireNonNegativeInteger(value.pass, `${path}.pass`),
    fail: requireNonNegativeInteger(value.fail, `${path}.fail`),
    invalid: requireNonNegativeInteger(value.invalid, `${path}.invalid`),
    skipped: requireNonNegativeInteger(value.skipped, `${path}.skipped`),
  };
}

/** Parse one visible artifact inventory item and exact content capability. */
export function parseBenchmarkArtifactInventoryItem(
  value: unknown,
  experimentId: string,
  path = "artifactItem",
): BenchmarkArtifactInventoryItem {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["schemaVersion", "descriptor", "links"], path);
  if (value.schemaVersion !== 1) {
    throw new Error(`${path}.schemaVersion is unsupported`);
  }
  const descriptor = parseBenchmarkArtifactDescriptor(
    value.descriptor,
    `${path}.descriptor`,
  );
  if (descriptor.experimentId !== experimentId || descriptor.hidden) {
    throw new Error(`${path} contains hidden or cross-Experiment metadata`);
  }
  if (!isRecord(value.links)) throw new Error(`${path}.links must be an object`);
  rejectUnknownKeys(value.links, ["content"], `${path}.links`);
  const readable = READABLE_AVAILABILITIES.has(descriptor.availability);
  const contentValue = value.links.content;
  let content: string | null = null;
  if (contentValue !== null && contentValue !== undefined) {
    const base = `/studio/benchmark-experiments/${experimentId}`;
    const expected = descriptor.taskRunId === null
      ? `${base}/artifacts/${descriptor.artifactId}`
      : `${base}/task-runs/${descriptor.taskRunId}/artifacts/${descriptor.artifactId}`;
    content = parseExactContentLink(contentValue, expected, `${path}.links.content`);
  }
  if (readable !== (content !== null)) {
    throw new Error(`${path}.links.content conflicts with availability`);
  }
  return {
    schemaVersion: 1,
    descriptor,
    links: { content },
  };
}

/** Parse one stable Experiment-scoped artifact inventory page. */
export function parseBenchmarkArtifactInventoryPage(
  value: unknown,
  path = "artifactInventory",
): BenchmarkArtifactInventoryPage {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["schemaVersion", "experimentId", "items", "hiddenCount", "nextCursor"],
    path,
  );
  if (value.schemaVersion !== 1) {
    throw new Error(`${path}.schemaVersion is unsupported`);
  }
  const experimentId = requireString(value.experimentId, `${path}.experimentId`);
  if (!EXPERIMENT_ID.test(experimentId)) {
    throw new Error(`${path}.experimentId is invalid`);
  }
  if (!Array.isArray(value.items) || value.items.length > MAX_PAGE_ITEMS) {
    throw new Error(`${path}.items must be a bounded array`);
  }
  const items = value.items.map((item, index) =>
    parseBenchmarkArtifactInventoryItem(
      item,
      experimentId,
      `${path}.items[${index}]`,
    ),
  );
  for (let index = 1; index < items.length; index += 1) {
    if (
      items[index - 1]!.descriptor.artifactId
      >= items[index]!.descriptor.artifactId
    ) {
      throw new Error(`${path}.items must use stable artifact order`);
    }
  }
  const cursor = value.nextCursor;
  if (cursor !== null && cursor !== undefined && typeof cursor !== "string") {
    throw new Error(`${path}.nextCursor must be a string or null`);
  }
  return {
    schemaVersion: 1,
    experimentId,
    items,
    hiddenCount: requireNonNegativeInteger(
      value.hiddenCount,
      `${path}.hiddenCount`,
    ),
    nextCursor: cursor ?? null,
  };
}

/** Parse one strict Experiment run summary. */
function parseRunSummary(value: unknown, path: string): BenchmarkRunSummary {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "task_run_id",
      "task_id",
      "agent_id",
      "repeat",
      "outcome",
      "report_ref",
      "trajectory_ref",
    ],
    path,
  );
  const coreTaskRunId = requireString(value.task_run_id, `${path}.task_run_id`);
  if (!CORE_TASK_RUN_ID.test(coreTaskRunId)) {
    throw new Error(`${path}.task_run_id is invalid`);
  }
  return {
    coreTaskRunId,
    taskId: requireBoundedString(value.task_id, `${path}.task_id`, 256),
    agentId: requireBoundedString(value.agent_id, `${path}.agent_id`, 256),
    repeat: requireNonNegativeInteger(value.repeat, `${path}.repeat`),
    outcome: parseOutcome(value.outcome, `${path}.outcome`),
    reportRef: parseCausalReference(value.report_ref, `${path}.report_ref`),
    trajectoryRef: parseCausalReference(
      value.trajectory_ref,
      `${path}.trajectory_ref`,
    ),
  };
}

/** Parse one strict per-Agent metric summary. */
function parseAgentMetric(value: unknown, path: string): BenchmarkAgentMetric {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "agent_id",
      "counts",
      "eligible_count",
      "success_rate_micro",
      "success_rate_macro",
      "duration_mean_ms",
      "duration_median_ms",
      "duration_sample_variance",
      "wilson_interval_95",
      "usage_available_runs",
    ],
    path,
  );
  const counts = parseOutcomeCounts(value.counts, `${path}.counts`);
  const eligibleCount = requireNonNegativeInteger(
    value.eligible_count,
    `${path}.eligible_count`,
  );
  if (eligibleCount !== counts.pass + counts.fail) {
    throw new Error(`${path}.eligible_count conflicts with PASS plus FAIL`);
  }
  let wilsonInterval95: [number, number] | null = null;
  if (value.wilson_interval_95 !== null) {
    if (
      !Array.isArray(value.wilson_interval_95)
      || value.wilson_interval_95.length !== 2
    ) {
      throw new Error(`${path}.wilson_interval_95 must be a pair or null`);
    }
    const lower = nullableRate(
      value.wilson_interval_95[0],
      `${path}.wilson_interval_95[0]`,
    );
    const upper = nullableRate(
      value.wilson_interval_95[1],
      `${path}.wilson_interval_95[1]`,
    );
    if (lower === null || upper === null || lower > upper) {
      throw new Error(`${path}.wilson_interval_95 is invalid`);
    }
    wilsonInterval95 = [lower, upper];
  }
  const usageAvailableRuns = requireNonNegativeInteger(
    value.usage_available_runs,
    `${path}.usage_available_runs`,
  );
  if (usageAvailableRuns > eligibleCount) {
    throw new Error(`${path}.usage_available_runs exceeds eligible runs`);
  }
  return {
    agentId: requireBoundedString(value.agent_id, `${path}.agent_id`, 256),
    counts,
    eligibleCount,
    successRateMicro: nullableRate(
      value.success_rate_micro,
      `${path}.success_rate_micro`,
    ),
    successRateMacro: nullableRate(
      value.success_rate_macro,
      `${path}.success_rate_macro`,
    ),
    durationMeanMs: nullableNumber(
      value.duration_mean_ms,
      `${path}.duration_mean_ms`,
      true,
    ),
    durationMedianMs: nullableNumber(
      value.duration_median_ms,
      `${path}.duration_median_ms`,
      true,
    ),
    durationSampleVariance: nullableNumber(
      value.duration_sample_variance,
      `${path}.duration_sample_variance`,
      true,
    ),
    wilsonInterval95,
    usageAvailableRuns,
  };
}

/** Parse one strict descriptive Agent comparison. */
function parseAgentComparison(
  value: unknown,
  path: string,
): BenchmarkAgentComparison {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "left_agent_id",
      "right_agent_id",
      "paired",
      "matched_count",
      "unmatched_eligible_count",
      "left_wins",
      "right_wins",
      "ties",
      "significance_claimed",
    ],
    path,
  );
  const leftAgentId = requireBoundedString(
    value.left_agent_id,
    `${path}.left_agent_id`,
    256,
  );
  const rightAgentId = requireBoundedString(
    value.right_agent_id,
    `${path}.right_agent_id`,
    256,
  );
  if (leftAgentId === rightAgentId) {
    throw new Error(`${path} must compare distinct Agents`);
  }
  const matchedCount = requireNonNegativeInteger(
    value.matched_count,
    `${path}.matched_count`,
  );
  const leftWins = requireNonNegativeInteger(
    value.left_wins,
    `${path}.left_wins`,
  );
  const rightWins = requireNonNegativeInteger(
    value.right_wins,
    `${path}.right_wins`,
  );
  const ties = requireNonNegativeInteger(value.ties, `${path}.ties`);
  if (matchedCount !== leftWins + rightWins + ties) {
    throw new Error(`${path}.matched_count conflicts with pair outcomes`);
  }
  const paired = requireBoolean(value.paired, `${path}.paired`);
  if (paired !== (matchedCount > 0)) {
    throw new Error(`${path}.paired conflicts with matched count`);
  }
  if (value.significance_claimed !== false) {
    throw new Error(`${path} cannot claim significance in schema 1.0`);
  }
  return {
    leftAgentId,
    rightAgentId,
    paired,
    matchedCount,
    unmatchedEligibleCount: requireNonNegativeInteger(
      value.unmatched_eligible_count,
      `${path}.unmatched_eligible_count`,
    ),
    leftWins,
    rightWins,
    ties,
    significanceClaimed: false,
  };
}

/** Parse an authoritative Core Benchmark Experiment report schema 1.0. */
export function parseBenchmarkExperimentReport(
  value: unknown,
  expectedExperimentId?: string,
  path = "experimentReport",
): BenchmarkExperimentReport {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schema_version",
      "kind",
      "experiment_id",
      "benchmark_plan_identity",
      "experiment_protocol_identity",
      "counts",
      "agent_metrics",
      "comparisons",
      "run_summaries",
      "fairness_warnings",
      "significance_claimed",
    ],
    path,
  );
  if (
    value.schema_version !== "1.0"
    || value.kind !== "benchmark_experiment_report"
  ) {
    throw new Error(`${path} uses an unsupported schema or kind`);
  }
  const experimentId = requireString(value.experiment_id, `${path}.experiment_id`);
  if (
    !EXPERIMENT_ID.test(experimentId)
    || (expectedExperimentId !== undefined && experimentId !== expectedExperimentId)
  ) {
    throw new Error(`${path}.experiment_id conflicts with the selected scope`);
  }
  const counts = parseOutcomeCounts(value.counts, `${path}.counts`);
  if (
    !Array.isArray(value.agent_metrics)
    || value.agent_metrics.length > MAX_REPORT_MEMBERS
    || !Array.isArray(value.comparisons)
    || value.comparisons.length > MAX_REPORT_MEMBERS
    || !Array.isArray(value.run_summaries)
    || value.run_summaries.length > MAX_REPORT_MEMBERS
    || !Array.isArray(value.fairness_warnings)
    || value.fairness_warnings.length > 500
  ) {
    throw new Error(`${path} contains an unbounded report collection`);
  }
  const agentMetrics = value.agent_metrics.map((item, index) =>
    parseAgentMetric(item, `${path}.agent_metrics[${index}]`),
  );
  const runSummaries = value.run_summaries.map((item, index) =>
    parseRunSummary(item, `${path}.run_summaries[${index}]`),
  );
  const comparisons = value.comparisons.map((item, index) =>
    parseAgentComparison(item, `${path}.comparisons[${index}]`),
  );
  if (value.significance_claimed !== false) {
    throw new Error(`${path} cannot claim significance in schema 1.0`);
  }
  const metricIds = new Set(agentMetrics.map((metric) => metric.agentId));
  if (metricIds.size !== agentMetrics.length) {
    throw new Error(`${path}.agent_metrics contains duplicate Agents`);
  }
  const runIds = new Set(runSummaries.map((summary) => summary.coreTaskRunId));
  if (runIds.size !== runSummaries.length) {
    throw new Error(`${path}.run_summaries contains duplicate TaskRuns`);
  }
  const observedCounts: BenchmarkOutcomeCounts = {
    pass: 0,
    fail: 0,
    invalid: 0,
    skipped: 0,
  };
  for (const summary of runSummaries) observedCounts[summary.outcome] += 1;
  for (const outcome of OUTCOMES) {
    if (counts[outcome] !== observedCounts[outcome]) {
      throw new Error(`${path}.counts conflicts with run summaries`);
    }
  }
  const byAgent = new Map<string, BenchmarkOutcomeCounts>();
  for (const summary of runSummaries) {
    const current = byAgent.get(summary.agentId) ?? {
      pass: 0,
      fail: 0,
      invalid: 0,
      skipped: 0,
    };
    current[summary.outcome] += 1;
    byAgent.set(summary.agentId, current);
  }
  for (const metric of agentMetrics) {
    const observed = byAgent.get(metric.agentId);
    if (
      observed === undefined
      || [...OUTCOMES].some(
        (outcome) => observed[outcome] !== metric.counts[outcome],
      )
    ) {
      throw new Error(`${path}.agent_metrics conflicts with run summaries`);
    }
  }
  const pairs = new Set<string>();
  for (const comparison of comparisons) {
    if (
      !metricIds.has(comparison.leftAgentId)
      || !metricIds.has(comparison.rightAgentId)
    ) {
      throw new Error(`${path}.comparisons references an unknown Agent`);
    }
    const pair = [comparison.leftAgentId, comparison.rightAgentId].sort().join("\0");
    if (pairs.has(pair)) {
      throw new Error(`${path}.comparisons contains a duplicate Agent pair`);
    }
    pairs.add(pair);
  }
  return {
    schemaVersion: "1.0",
    kind: "benchmark_experiment_report",
    experimentId,
    benchmarkPlanIdentity: parseHash(
      value.benchmark_plan_identity,
      `${path}.benchmark_plan_identity`,
    ),
    experimentProtocolIdentity: parseHash(
      value.experiment_protocol_identity,
      `${path}.experiment_protocol_identity`,
    ),
    counts,
    agentMetrics,
    comparisons,
    runSummaries,
    fairnessWarnings: value.fairness_warnings.map((warning, index) =>
      requireBoundedString(
        warning,
        `${path}.fairness_warnings[${index}]`,
        MAX_TEXT,
        true,
      ),
    ),
    significanceClaimed: false,
  };
}

/** Parse one strict lifecycle stage from a TaskRun report. */
function parseReportStage(value: unknown, path: string): BenchmarkReportStage {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "phase",
      "status",
      "duration_ms",
      "error_code",
      "message",
      "evidence",
      "artifact_refs",
    ],
    path,
  );
  if (!Array.isArray(value.artifact_refs) || value.artifact_refs.length > 50) {
    throw new Error(`${path}.artifact_refs must be a bounded array`);
  }
  return {
    phase: requireBoundedString(value.phase, `${path}.phase`, 128),
    status: parseStageStatus(value.status, `${path}.status`),
    durationMs: nullableNumber(
      value.duration_ms,
      `${path}.duration_ms`,
      true,
    ) ?? 0,
    errorCode: requireBoundedString(
      value.error_code,
      `${path}.error_code`,
      256,
      true,
    ),
    message: requireBoundedString(
      value.message,
      `${path}.message`,
      MAX_TEXT,
      true,
    ),
    evidence: boundedJson(value.evidence, `${path}.evidence`),
    artifactRefs: value.artifact_refs.map((item, index) =>
      parseCausalReference(item, `${path}.artifact_refs[${index}]`),
    ),
  };
}

/** Parse normalized evaluator usage without inventing unavailable counters. */
function parseEvaluationUsage(
  value: unknown,
  path: string,
): BenchmarkEvaluationUsage {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "availability",
      "prompt_tokens",
      "completion_tokens",
      "total_tokens",
    ],
    path,
  );
  if (value.availability !== "available" && value.availability !== "unavailable") {
    throw new Error(`${path}.availability is unsupported`);
  }
  const promptTokens = value.prompt_tokens === null
    ? null
    : requireNonNegativeInteger(value.prompt_tokens, `${path}.prompt_tokens`);
  const completionTokens = value.completion_tokens === null
    ? null
    : requireNonNegativeInteger(
        value.completion_tokens,
        `${path}.completion_tokens`,
      );
  const totalTokens = value.total_tokens === null
    ? null
    : requireNonNegativeInteger(value.total_tokens, `${path}.total_tokens`);
  if (
    value.availability === "unavailable"
    && (promptTokens !== null || completionTokens !== null || totalTokens !== null)
  ) {
    throw new Error(`${path} unavailable usage contains counters`);
  }
  return {
    availability: value.availability,
    promptTokens,
    completionTokens,
    totalTokens,
  };
}

/** Parse one typed bounded evaluator evidence item. */
function parseEvaluationEvidence(
  value: unknown,
  path: string,
): BenchmarkEvaluationEvidence {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["kind", "value", "artifact_ref", "metadata"], path);
  const artifactRef = requireBoundedString(
    value.artifact_ref,
    `${path}.artifact_ref`,
    MAX_REFERENCE,
    true,
  );
  if (artifactRef) parseCausalReference(artifactRef, `${path}.artifact_ref`);
  return {
    kind: requireBoundedString(value.kind, `${path}.kind`, 160),
    value: boundedJson(value.value, `${path}.value`),
    artifactRef,
    metadata: boundedJson(value.metadata, `${path}.metadata`),
  };
}

/** Parse one canonical evaluator result schema 2.0. */
function parseEvaluatorResult(
  value: unknown,
  path: string,
): BenchmarkEvaluatorResult {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schema_version",
      "evaluator_id",
      "status",
      "passed",
      "score",
      "reason",
      "duration_ms",
      "usage",
      "evidence",
      "metadata",
      "error_code",
    ],
    path,
  );
  if (value.schema_version !== "2.0") {
    throw new Error(`${path}.schema_version is unsupported`);
  }
  if (
    typeof value.status !== "string"
    || !EVALUATOR_STATUSES.has(
      value.status as "completed" | "error" | "invalid" | "skipped",
    )
  ) {
    throw new Error(`${path}.status is unsupported`);
  }
  const passed = value.passed === null
    ? null
    : requireBoolean(value.passed, `${path}.passed`);
  if (
    (value.status === "completed" && passed === null)
    || (value.status !== "completed" && passed !== null)
  ) {
    throw new Error(`${path}.passed conflicts with evaluator status`);
  }
  const score = nullableRate(value.score, `${path}.score`);
  if (!Array.isArray(value.evidence) || value.evidence.length > MAX_EVIDENCE_ITEMS) {
    throw new Error(`${path}.evidence must be a bounded array`);
  }
  return {
    schemaVersion: "2.0",
    evaluatorId: requireBoundedString(
      value.evaluator_id,
      `${path}.evaluator_id`,
      256,
    ),
    status: value.status as "completed" | "error" | "invalid" | "skipped",
    passed,
    score,
    reason: requireBoundedString(
      value.reason,
      `${path}.reason`,
      MAX_TEXT,
      true,
    ),
    durationMs: nullableNumber(
      value.duration_ms,
      `${path}.duration_ms`,
      true,
    ) ?? 0,
    usage: parseEvaluationUsage(value.usage, `${path}.usage`),
    evidence: value.evidence.map((item, index) =>
      parseEvaluationEvidence(item, `${path}.evidence[${index}]`),
    ),
    metadata: boundedJson(value.metadata, `${path}.metadata`),
    errorCode: requireBoundedString(
      value.error_code,
      `${path}.error_code`,
      256,
      true,
    ),
  };
}

/** Parse a recursive Evaluation Tree with explicit depth and node budgets. */
function parseEvaluationNode(
  value: unknown,
  path: string,
  depth: number,
  budget: { nodes: number },
): BenchmarkEvaluationNode {
  budget.nodes += 1;
  if (depth > MAX_EVALUATION_DEPTH || budget.nodes > MAX_EVALUATION_NODES) {
    throw new Error(`${path} exceeds Evaluation Tree limits`);
  }
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "path",
      "name",
      "status",
      "is_pass",
      "reason",
      "token",
      "score",
      "duration_ms",
      "evidence",
      "aggregation",
      "evaluator_result",
      "short_circuited",
      "children",
    ],
    path,
  );
  if (!Array.isArray(value.children) || value.children.length > MAX_CHILDREN) {
    throw new Error(`${path}.children must be a bounded array`);
  }
  const isPass = value.is_pass === null
    ? null
    : requireBoolean(value.is_pass, `${path}.is_pass`);
  return {
    path: requireBoundedString(value.path, `${path}.path`, 512),
    name: requireBoundedString(value.name, `${path}.name`, 256),
    status: parseStageStatus(value.status, `${path}.status`),
    isPass,
    reason: requireBoundedString(
      value.reason,
      `${path}.reason`,
      MAX_TEXT,
      true,
    ),
    token: parseEvaluationToken(value.token, `${path}.token`),
    score: nullableRate(value.score, `${path}.score`),
    durationMs: nullableNumber(
      value.duration_ms,
      `${path}.duration_ms`,
      true,
    ) ?? 0,
    evidence: boundedJson(value.evidence, `${path}.evidence`),
    aggregation: boundedJson(value.aggregation, `${path}.aggregation`),
    evaluatorResult: value.evaluator_result === null
      ? null
      : parseEvaluatorResult(
          value.evaluator_result,
          `${path}.evaluator_result`,
        ),
    shortCircuited: requireBoolean(
      value.short_circuited,
      `${path}.short_circuited`,
    ),
    children: value.children.map((child, index) =>
      parseEvaluationNode(
        child,
        `${path}.children[${index}]`,
        depth + 1,
        budget,
      ),
    ),
  };
}

/** Parse one authoritative Core Benchmark TaskRun report schema 1.0. */
export function parseBenchmarkRunReport(
  value: unknown,
  expected?: BenchmarkRunReportScope,
  path = "runReport",
): BenchmarkRunReport {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schema_version",
      "kind",
      "task_run_id",
      "experiment_id",
      "task_id",
      "agent_id",
      "repeat",
      "outcome",
      "identities",
      "stages",
      "evaluation",
      "usage",
      "artifact_namespace",
    ],
    path,
  );
  if (value.schema_version !== "1.0" || value.kind !== "benchmark_run_report") {
    throw new Error(`${path} uses an unsupported schema or kind`);
  }
  const coreTaskRunId = requireString(value.task_run_id, `${path}.task_run_id`);
  const experimentId = requireString(value.experiment_id, `${path}.experiment_id`);
  if (
    !CORE_TASK_RUN_ID.test(coreTaskRunId)
    || !EXPERIMENT_ID.test(experimentId)
  ) {
    throw new Error(`${path} contains an invalid resource identity`);
  }
  const taskId = requireBoundedString(value.task_id, `${path}.task_id`, 256);
  const agentId = requireBoundedString(value.agent_id, `${path}.agent_id`, 256);
  const repeat = requireNonNegativeInteger(value.repeat, `${path}.repeat`);
  if (
    expected !== undefined
    && (
      expected.experimentId !== experimentId
      || expected.coreTaskRunId !== coreTaskRunId
      || expected.taskId !== taskId
      || expected.agentId !== agentId
      || expected.repeat !== repeat
    )
  ) {
    throw new Error(`${path} conflicts with the selected TaskRun scope`);
  }
  if (!isRecord(value.identities)) {
    throw new Error(`${path}.identities must be an object`);
  }
  rejectUnknownKeys(
    value.identities,
    [
      "agent_graph",
      "benchmark_plan",
      "experiment_protocol",
      "task_instance",
    ],
    `${path}.identities`,
  );
  if (!Array.isArray(value.stages) || value.stages.length > MAX_STAGE_COUNT) {
    throw new Error(`${path}.stages must be a bounded array`);
  }
  const artifactNamespace = requireBoundedString(
    value.artifact_namespace,
    `${path}.artifact_namespace`,
    MAX_REFERENCE,
    true,
  );
  if (artifactNamespace) {
    parseCausalReference(artifactNamespace, `${path}.artifact_namespace`);
  }
  return {
    schemaVersion: "1.0",
    kind: "benchmark_run_report",
    coreTaskRunId,
    experimentId,
    taskId,
    agentId,
    repeat,
    outcome: parseOutcome(value.outcome, `${path}.outcome`),
    identities: {
      agentGraph: parseHash(
        value.identities.agent_graph,
        `${path}.identities.agent_graph`,
      ),
      benchmarkPlan: parseHash(
        value.identities.benchmark_plan,
        `${path}.identities.benchmark_plan`,
      ),
      experimentProtocol: parseHash(
        value.identities.experiment_protocol,
        `${path}.identities.experiment_protocol`,
      ),
      taskInstance: parseHash(
        value.identities.task_instance,
        `${path}.identities.task_instance`,
      ),
    },
    stages: value.stages.map((stage, index) =>
      parseReportStage(stage, `${path}.stages[${index}]`),
    ),
    evaluation: value.evaluation === null
      ? null
      : parseEvaluationNode(
          value.evaluation,
          `${path}.evaluation`,
          1,
          { nodes: 0 },
        ),
    usage: boundedJson(value.usage, `${path}.usage`),
    artifactNamespace,
  };
}

/** Match a Core report reference to exactly one same-scope readable artifact. */
export function resolveBenchmarkRunReportArtifact(
  scope: Pick<
    BenchmarkRunReportScope,
    "experimentId" | "taskRunId" | "coreTaskRunId"
  >,
  summary: BenchmarkRunSummary,
  inventory: BenchmarkArtifactInventoryPage,
): BenchmarkArtifactInventoryItem {
  if (
    inventory.experimentId !== scope.experimentId
    || summary.coreTaskRunId !== scope.coreTaskRunId
  ) {
    throw new Error("artifact inventory conflicts with Experiment scope");
  }
  const matches = inventory.items.filter((item) =>
    item.descriptor.experimentId === scope.experimentId
    && item.descriptor.taskRunId === scope.taskRunId
    && item.descriptor.kind === "task_report"
    && item.descriptor.causalIdentity === summary.reportRef
    && item.links.content !== null
  );
  if (matches.length !== 1) {
    throw new Error(
      matches.length === 0
        ? "TaskRun report artifact is unavailable or inconsistent"
        : "TaskRun report causal reference is ambiguous",
    );
  }
  return matches[0]!;
}
