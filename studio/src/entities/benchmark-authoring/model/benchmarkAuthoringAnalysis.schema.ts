import {
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
} from "@/shared/lib";

export const BENCHMARK_ANALYSIS_MAX_AGENTS = 16;
export const BENCHMARK_ANALYSIS_MAX_TASKS = 100;
export const BENCHMARK_ANALYSIS_MAX_DIAGNOSTICS = 100;
export const BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES = 10_000;

const DRAFT_ID = /^benchmark-draft-[a-f0-9]{32}$/;
const REVISION_ID = /^benchmark-authoring-revision-[a-f0-9]{32}$/;
const STABLE_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/;
const SPLIT = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;
const PACKAGE_PATH = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))(?!.*\\)(?!.*\/\/)[^\0]+$/;

export type BenchmarkValidationRequest = {
  schemaVersion: 1;
  revisionId: string;
  split: string;
};

export type BenchmarkAgentRevisionSelection = {
  agentId: string;
  revisionId: string;
};

export type BenchmarkDryRunRequest = BenchmarkValidationRequest & {
  taskIds: string[];
  agentRevisions: BenchmarkAgentRevisionSelection[];
};

export type BenchmarkAnalysisDiagnostic = {
  code: string;
  message: string;
  severity: "error" | "warning" | "info";
  memberKind: "manifest" | "task" | "protocol" | "resource" | "agent";
  memberPath: string | null;
  fieldPath: Array<string | number>;
  taskId: string | null;
  resourceId: string | null;
  agentId: string | null;
  revisionId: string | null;
};

export type BenchmarkAnalysisIdentities = {
  package: string | null;
  packageContent: string | null;
  benchmarkPlan: string | null;
  experimentProtocol: string | null;
};

export type BenchmarkVerifiedAgentRevision = {
  agentId: string;
  revisionId: string;
  agentGraphIdentity: string;
};

export type BenchmarkDryRunScheduleEntry = {
  repeat: number;
  taskId: string;
  agentId: string;
  seed: number;
  sharedInstanceKey: string;
};

export type BenchmarkDryRunBudget = {
  maxInteractions: number;
  maxActivations: number;
  timeoutSeconds: number;
  tokenLimit: number | null;
  requireObservableTokens: boolean;
};

export type BenchmarkDryRunOutputLayout = {
  experimentReport: "<artifact-root>/<experiment-id>/experiment-report.json";
  runReport: "<artifact-root>/<experiment-id>/runs/<task-run-id>/run-report.json";
  trajectory: "<artifact-root>/<experiment-id>/runs/<task-run-id>/trajectory.jsonl";
  bundle: "<artifact-root>/<experiment-id>/trajectory-bundle.zip";
};

export type BenchmarkValidationResult = {
  schemaVersion: 1;
  mode: "validation";
  draftId: string;
  revisionId: string;
  documentFingerprint: string;
  split: string;
  valid: boolean;
  identities: BenchmarkAnalysisIdentities;
  diagnostics: BenchmarkAnalysisDiagnostic[];
  diagnosticsTruncated: boolean;
  unverifiedChecks: string[];
  executionEvidence: false;
};

export type BenchmarkDryRunResult = {
  schemaVersion: 1;
  mode: "side-effect-free-dry-run";
  draftId: string;
  revisionId: string;
  documentFingerprint: string;
  split: string;
  ok: boolean;
  identities: BenchmarkAnalysisIdentities;
  agentRevisions: BenchmarkVerifiedAgentRevision[];
  schedule: BenchmarkDryRunScheduleEntry[];
  budget: BenchmarkDryRunBudget | null;
  fairnessWarnings: string[];
  outputLayout: BenchmarkDryRunOutputLayout | null;
  unverifiedChecks: string[];
  diagnostics: BenchmarkAnalysisDiagnostic[];
  diagnosticsTruncated: boolean;
  executionEvidence: false;
};

/** Require one strict schema-version-one response object. */
function analysisObject(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value) || value.schemaVersion !== 1) {
    throw new Error(`${path} must be a schemaVersion 1 object`);
  }
  return value;
}

/** Require one finite integer within an inclusive lower bound. */
function integerAtLeast(value: unknown, minimum: number, path: string): number {
  const parsed = requireNumber(value, path);
  if (!Number.isSafeInteger(parsed) || parsed < minimum) {
    throw new Error(`${path} must be an integer >= ${minimum}`);
  }
  return parsed;
}

/** Require a string that matches a bounded identity contract. */
function matchingString(
  value: unknown,
  pattern: RegExp,
  path: string,
): string {
  const parsed = requireString(value, path);
  if (!pattern.test(parsed)) throw new Error(`${path} is malformed`);
  return parsed;
}

/** Parse a missing-or-null optional string through one contract. */
function optionalMatchingString(
  value: unknown,
  pattern: RegExp,
  path: string,
): string | null {
  if (value === undefined || value === null) return null;
  return matchingString(value, pattern, path);
}

/** Parse one bounded safe string collection without accepting duplicates. */
function boundedStrings(
  value: unknown,
  path: string,
  maximum: number,
  itemMaximum = 500,
): string[] {
  if (!Array.isArray(value) || value.length > maximum) {
    throw new Error(`${path} must be an array with at most ${maximum} items`);
  }
  const parsed = value.map((item, index) => {
    const text = requireString(item, `${path}[${index}]`);
    if (text.length === 0 || text.length > itemMaximum || /[\r\n\0]/.test(text)) {
      throw new Error(`${path}[${index}] is not bounded safe text`);
    }
    return text;
  });
  if (new Set(parsed).size !== parsed.length) {
    throw new Error(`${path} must not contain duplicates`);
  }
  return parsed;
}

/** Parse independently gated validation identities. */
export function parseBenchmarkAnalysisIdentities(
  value: unknown,
  path: string,
): BenchmarkAnalysisIdentities {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["package", "packageContent", "benchmarkPlan", "experimentProtocol"],
    path,
  );
  const packageIdentity =
    value.package === undefined || value.package === null
      ? null
      : requireString(value.package, `${path}.package`);
  if (packageIdentity !== null && (packageIdentity.length === 0 || packageIdentity.length > 384)) {
    throw new Error(`${path}.package is not bounded`);
  }
  return {
    package: packageIdentity,
    packageContent: optionalMatchingString(
      value.packageContent,
      DIGEST,
      `${path}.packageContent`,
    ),
    benchmarkPlan: optionalMatchingString(
      value.benchmarkPlan,
      DIGEST,
      `${path}.benchmarkPlan`,
    ),
    experimentProtocol: optionalMatchingString(
      value.experimentProtocol,
      DIGEST,
      `${path}.experimentProtocol`,
    ),
  };
}

/** Parse one bounded diagnostic field path. */
function parseFieldPath(value: unknown, path: string): Array<string | number> {
  if (!Array.isArray(value) || value.length > 16) {
    throw new Error(`${path} must contain at most 16 segments`);
  }
  return value.map((segment, index) => {
    if (typeof segment === "string") {
      if (segment.length > 160 || /[\r\n\0]/.test(segment)) {
        throw new Error(`${path}[${index}] is unsafe`);
      }
      return segment;
    }
    if (
      typeof segment !== "number"
      || !Number.isSafeInteger(segment)
      || segment < 0
    ) {
      throw new Error(`${path}[${index}] must be a non-negative integer or string`);
    }
    return segment;
  });
}

/** Parse one safe field-addressable analysis diagnostic. */
export function parseBenchmarkAnalysisDiagnostic(
  value: unknown,
  path: string,
): BenchmarkAnalysisDiagnostic {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "code",
      "message",
      "severity",
      "memberKind",
      "memberPath",
      "fieldPath",
      "taskId",
      "resourceId",
      "agentId",
      "revisionId",
    ],
    path,
  );
  const code = requireString(value.code, `${path}.code`);
  const message = requireString(value.message, `${path}.message`);
  if (
    code.length === 0
    || code.length > 160
    || message.length === 0
    || message.length > 500
    || /[\r\n\0]/.test(message)
  ) {
    throw new Error(`${path} contains unbounded diagnostic text`);
  }
  if (
    value.severity !== "error"
    && value.severity !== "warning"
    && value.severity !== "info"
  ) {
    throw new Error(`${path}.severity is unsupported`);
  }
  if (
    value.memberKind !== "manifest"
    && value.memberKind !== "task"
    && value.memberKind !== "protocol"
    && value.memberKind !== "resource"
    && value.memberKind !== "agent"
  ) {
    throw new Error(`${path}.memberKind is unsupported`);
  }
  const memberPath =
    value.memberPath === undefined || value.memberPath === null
      ? null
      : matchingString(value.memberPath, PACKAGE_PATH, `${path}.memberPath`);
  return {
    code,
    message,
    severity: value.severity,
    memberKind: value.memberKind,
    memberPath,
    fieldPath: parseFieldPath(value.fieldPath ?? [], `${path}.fieldPath`),
    taskId:
      value.taskId === undefined || value.taskId === null
        ? null
        : requireString(value.taskId, `${path}.taskId`),
    resourceId: optionalMatchingString(
      value.resourceId,
      STABLE_ID,
      `${path}.resourceId`,
    ),
    agentId: optionalMatchingString(value.agentId, STABLE_ID, `${path}.agentId`),
    revisionId: optionalMatchingString(
      value.revisionId,
      STABLE_ID,
      `${path}.revisionId`,
    ),
  };
}

/** Parse a bounded diagnostic collection and preserve server ordering. */
function parseDiagnostics(value: unknown, path: string): BenchmarkAnalysisDiagnostic[] {
  if (!Array.isArray(value) || value.length > BENCHMARK_ANALYSIS_MAX_DIAGNOSTICS) {
    throw new Error(`${path} exceeds the public diagnostic bound`);
  }
  return value.map((item, index) => parseBenchmarkAnalysisDiagnostic(item, `${path}[${index}]`));
}

/** Parse one verified immutable Agent revision fact. */
function parseVerifiedAgent(
  value: unknown,
  path: string,
): BenchmarkVerifiedAgentRevision {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["agentId", "revisionId", "agentGraphIdentity"],
    path,
  );
  return {
    agentId: matchingString(value.agentId, STABLE_ID, `${path}.agentId`),
    revisionId: matchingString(value.revisionId, STABLE_ID, `${path}.revisionId`),
    agentGraphIdentity: matchingString(
      value.agentGraphIdentity,
      DIGEST,
      `${path}.agentGraphIdentity`,
    ),
  };
}

/** Parse one complete deterministic schedule row. */
function parseScheduleEntry(
  value: unknown,
  path: string,
): BenchmarkDryRunScheduleEntry {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["repeat", "taskId", "agentId", "seed", "sharedInstanceKey"],
    path,
  );
  const taskId = requireString(value.taskId, `${path}.taskId`);
  const sharedInstanceKey = requireString(
    value.sharedInstanceKey,
    `${path}.sharedInstanceKey`,
  );
  if (
    taskId.length === 0
    || taskId.length > 256
    || sharedInstanceKey.length === 0
    || sharedInstanceKey.length > 768
  ) {
    throw new Error(`${path} contains an unbounded schedule identity`);
  }
  return {
    repeat: integerAtLeast(value.repeat, 0, `${path}.repeat`),
    taskId,
    agentId: matchingString(value.agentId, STABLE_ID, `${path}.agentId`),
    seed: integerAtLeast(value.seed, 0, `${path}.seed`),
    sharedInstanceKey,
  };
}

/** Parse one positive declared budget projection. */
function parseBudget(value: unknown, path: string): BenchmarkDryRunBudget {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "maxInteractions",
      "maxActivations",
      "timeoutSeconds",
      "tokenLimit",
      "requireObservableTokens",
    ],
    path,
  );
  if (typeof value.requireObservableTokens !== "boolean") {
    throw new Error(`${path}.requireObservableTokens must be boolean`);
  }
  return {
    maxInteractions: integerAtLeast(value.maxInteractions, 1, `${path}.maxInteractions`),
    maxActivations: integerAtLeast(value.maxActivations, 1, `${path}.maxActivations`),
    timeoutSeconds: integerAtLeast(value.timeoutSeconds, 1, `${path}.timeoutSeconds`),
    tokenLimit:
      value.tokenLimit === undefined || value.tokenLimit === null
        ? null
        : integerAtLeast(value.tokenLimit, 1, `${path}.tokenLimit`),
    requireObservableTokens: value.requireObservableTokens,
  };
}

/** Parse the fixed safe relative output-layout projection. */
function parseOutputLayout(value: unknown, path: string): BenchmarkDryRunOutputLayout {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["experimentReport", "runReport", "trajectory", "bundle"],
    path,
  );
  const expected = {
    experimentReport: "<artifact-root>/<experiment-id>/experiment-report.json",
    runReport: "<artifact-root>/<experiment-id>/runs/<task-run-id>/run-report.json",
    trajectory: "<artifact-root>/<experiment-id>/runs/<task-run-id>/trajectory.jsonl",
    bundle: "<artifact-root>/<experiment-id>/trajectory-bundle.zip",
  } as const;
  for (const [key, expectedValue] of Object.entries(expected)) {
    if (value[key] !== expectedValue) throw new Error(`${path}.${key} is unsupported`);
  }
  return expected;
}

/**
 * Parse one revision-bound schema-1 validation result.
 *
 * Args:
 *   value: Untrusted JSON returned by the Studio analysis endpoint.
 *
 * Returns:
 *   A closed, bounded validation result with `executionEvidence=false`.
 *
 * Raises:
 *   Error: The envelope, ownership, identity, path, capacity, or evidence facts
 *   violate the public schema-1 contract.
 */
export function parseBenchmarkValidationResult(
  value: unknown,
): BenchmarkValidationResult {
  const object = analysisObject(value, "validationResult");
  rejectUnknownKeys(
    object,
    [
      "schemaVersion",
      "mode",
      "draftId",
      "revisionId",
      "documentFingerprint",
      "split",
      "valid",
      "identities",
      "diagnostics",
      "diagnosticsTruncated",
      "unverifiedChecks",
      "executionEvidence",
    ],
    "validationResult",
  );
  if (object.mode !== "validation" || typeof object.valid !== "boolean") {
    throw new Error("validationResult mode or valid fact is unsupported");
  }
  if (
    typeof object.diagnosticsTruncated !== "boolean"
    || object.executionEvidence !== false
  ) {
    throw new Error("validationResult evidence facts are invalid");
  }
  return {
    schemaVersion: 1,
    mode: "validation",
    draftId: matchingString(object.draftId, DRAFT_ID, "validationResult.draftId"),
    revisionId: matchingString(
      object.revisionId,
      REVISION_ID,
      "validationResult.revisionId",
    ),
    documentFingerprint: matchingString(
      object.documentFingerprint,
      DIGEST,
      "validationResult.documentFingerprint",
    ),
    split: matchingString(object.split, SPLIT, "validationResult.split"),
    valid: object.valid,
    identities: parseBenchmarkAnalysisIdentities(object.identities, "validationResult.identities"),
    diagnostics: parseDiagnostics(
      object.diagnostics ?? [],
      "validationResult.diagnostics",
    ),
    diagnosticsTruncated: object.diagnosticsTruncated,
    unverifiedChecks: boundedStrings(
      object.unverifiedChecks ?? [],
      "validationResult.unverifiedChecks",
      BENCHMARK_ANALYSIS_MAX_DIAGNOSTICS,
    ),
    executionEvidence: false,
  };
}

/**
 * Parse one complete bounded revision-bound dry-run result.
 *
 * Args:
 *   value: Untrusted JSON returned by the Studio dry-run endpoint.
 *
 * Returns:
 *   A closed dry-run projection whose complete schedule is bounded at 10,000.
 *
 * Raises:
 *   Error: The response is malformed, contradictory, over capacity, unsafe, or
 *   attempts to claim execution evidence.
 */
export function parseBenchmarkDryRunResult(value: unknown): BenchmarkDryRunResult {
  const object = analysisObject(value, "dryRunResult");
  rejectUnknownKeys(
    object,
    [
      "schemaVersion",
      "mode",
      "draftId",
      "revisionId",
      "documentFingerprint",
      "split",
      "ok",
      "identities",
      "agentRevisions",
      "schedule",
      "budget",
      "fairnessWarnings",
      "outputLayout",
      "unverifiedChecks",
      "diagnostics",
      "diagnosticsTruncated",
      "executionEvidence",
    ],
    "dryRunResult",
  );
  if (
    object.mode !== "side-effect-free-dry-run"
    || typeof object.ok !== "boolean"
    || typeof object.diagnosticsTruncated !== "boolean"
    || object.executionEvidence !== false
  ) {
    throw new Error("dryRunResult mode or evidence facts are invalid");
  }
  if (!Array.isArray(object.agentRevisions) || object.agentRevisions.length > BENCHMARK_ANALYSIS_MAX_AGENTS) {
    throw new Error("dryRunResult.agentRevisions exceeds the public bound");
  }
  if (!Array.isArray(object.schedule) || object.schedule.length > BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES) {
    throw new Error("dryRunResult.schedule exceeds the public bound");
  }
  const schedule = object.schedule.map((item, index) =>
    parseScheduleEntry(item, `dryRunResult.schedule[${index}]`));
  const budget =
    object.budget === undefined || object.budget === null
      ? null
      : parseBudget(object.budget, "dryRunResult.budget");
  const outputLayout =
    object.outputLayout === undefined || object.outputLayout === null
      ? null
      : parseOutputLayout(object.outputLayout, "dryRunResult.outputLayout");
  if (!object.ok && (schedule.length > 0 || budget !== null || outputLayout !== null)) {
    throw new Error("failed dryRunResult cannot contain partial planning facts");
  }
  return {
    schemaVersion: 1,
    mode: "side-effect-free-dry-run",
    draftId: matchingString(object.draftId, DRAFT_ID, "dryRunResult.draftId"),
    revisionId: matchingString(object.revisionId, REVISION_ID, "dryRunResult.revisionId"),
    documentFingerprint: matchingString(
      object.documentFingerprint,
      DIGEST,
      "dryRunResult.documentFingerprint",
    ),
    split: matchingString(object.split, SPLIT, "dryRunResult.split"),
    ok: object.ok,
    identities: parseBenchmarkAnalysisIdentities(object.identities, "dryRunResult.identities"),
    agentRevisions: object.agentRevisions.map((item, index) =>
      parseVerifiedAgent(item, `dryRunResult.agentRevisions[${index}]`)),
    schedule,
    budget,
    fairnessWarnings: boundedStrings(
      object.fairnessWarnings ?? [],
      "dryRunResult.fairnessWarnings",
      BENCHMARK_ANALYSIS_MAX_DIAGNOSTICS,
    ),
    outputLayout,
    unverifiedChecks: boundedStrings(
      object.unverifiedChecks ?? [],
      "dryRunResult.unverifiedChecks",
      BENCHMARK_ANALYSIS_MAX_DIAGNOSTICS,
    ),
    diagnostics: parseDiagnostics(object.diagnostics ?? [], "dryRunResult.diagnostics"),
    diagnosticsTruncated: object.diagnosticsTruncated,
    executionEvidence: false,
  };
}
