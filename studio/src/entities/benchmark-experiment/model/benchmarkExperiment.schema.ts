import type {
  ExperimentPreviewRequest,
  ExperimentProtocol,
} from "@/entities/experiment-preview";
import { parseRunSnapshot, type RunSnapshot } from "@/entities/run";
import {
  cloneJson,
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
  type JsonValue,
} from "@/shared/lib";
import {
  parseExecutionEvidenceOrigin,
  type ExecutionEvidenceOrigin,
} from "@/entities/evidence-origin";

export type BenchmarkExperimentLifecycle =
  | "accepted"
  | "starting"
  | "running"
  | "cancelling"
  | "finalizing"
  | "terminal";

export type BenchmarkExperimentTerminalReason =
  | "completed"
  | "cancelled"
  | "failed"
  | "interrupted";

export type BenchmarkTaskRunLifecycle =
  | "scheduled"
  | "preparing"
  | "evaluating"
  | "cleaning_up"
  | "starting"
  | "running"
  | "cancelling"
  | "terminal";

export type BenchmarkTaskRunTerminalReason =
  | "completed"
  | "cancelled_before_start"
  | "cancelled"
  | "failed"
  | "interrupted";

export type BenchmarkAvailability =
  | "pending"
  | "not_produced"
  | "available"
  | "failed";

export type BenchmarkArtifactAvailability =
  | BenchmarkAvailability
  | "excluded"
  | "hidden"
  | "missing"
  | "corrupt"
  | "redacted"
  | "truncated";

export type BenchmarkPublicationDiagnostic = {
  code: string;
  message: string;
  component: string;
  retryable: boolean;
};

export type BenchmarkArtifactDescriptor = {
  schemaVersion: 1;
  artifactId: string;
  experimentId: string;
  taskRunId: string | null;
  kind: string;
  availability: BenchmarkArtifactAvailability;
  contentType: string;
  size: number;
  sha256: string | null;
  provenance: string;
  causalIdentity: string;
  hidden: boolean;
};

export type BenchmarkTaskPhase = {
  phase: string;
  status: string;
  durationMs: number;
  errorCode: string;
  message: string;
  evidence: Record<string, JsonValue>;
  artifactRefs: string[];
};

export type BenchmarkAgentSnapshot = {
  schemaVersion: 1;
  agentId: string;
  revisionId: string;
  contractVersion: string;
  compileContractVersion: string;
  canonicalHash: string;
  agentGraph: JsonValue;
  presentation: JsonValue;
  sourceMap: JsonValue[];
  providerIdentities: string[];
  runSnapshot: RunSnapshot;
};

export type BenchmarkDefinitionSnapshot = {
  schemaVersion: 1;
  previewFingerprint: string;
  snapshotFingerprint: string;
  source: {
    sourceId: string;
    sourceKind: "package" | "catalog" | "installed";
    relativeKey: string;
    catalogEntryId: string;
    packageIdentity: string;
    packageContentIdentity: string;
    benchmarkPlanIdentity: string;
    experimentProtocolIdentity: string;
  };
  agentSnapshots: BenchmarkAgentSnapshot[];
  benchmarkPlan: JsonValue;
  protocol: ExperimentProtocol;
  split: string;
  taskIds: string[];
  schedule: Array<{
    plannedEntryId: string;
    agentId: string;
    revisionId: string;
    taskId: string;
    repeat: number;
    order: number;
    derivedSeed: number;
    taskInstance: JsonValue;
  }>;
  deviceProfileId: string;
  executionLimits: {
    maxAgents: number;
    maxSelectedTasks: number;
    maxRepeats: number;
    multiAgentComparison: boolean;
  };
};

export type BenchmarkExperimentCapabilities = {
  executes: boolean;
  cancelAccepted: true;
  cancelActive: boolean;
  eventStream: boolean;
  replay: boolean;
  reports: boolean;
};

export type BenchmarkExperimentResource = {
  schemaVersion: 1;
  experimentId: string;
  clientRequestId: string;
  definition: BenchmarkDefinitionSnapshot;
  lifecycle: BenchmarkExperimentLifecycle;
  terminalReason: BenchmarkExperimentTerminalReason | null;
  cancellation: {
    schemaVersion: 1;
    clientRequestId: string;
    requestedAt: number;
    reasonCode: "user_requested";
  } | null;
  outcomeAvailability: BenchmarkAvailability;
  reportAvailability: BenchmarkAvailability;
  replayAvailability: BenchmarkAvailability;
  trajectoryAvailability: BenchmarkAvailability;
  bundleAvailability: BenchmarkAvailability;
  publicationDiagnostics: BenchmarkPublicationDiagnostic[];
  eventHighWaterMark: number;
  acceptedAt: number;
  updatedAt: number;
  terminalAt: number | null;
  capabilities: BenchmarkExperimentCapabilities;
  links: {
    self: string;
    cancel: string | null;
    taskRuns: string;
    artifacts: string | null;
    events: string | null;
    eventStream: string | null;
    report: string | null;
    bundle: string | null;
  };
};

export type CreateBenchmarkExperimentInput = {
  schemaVersion: 1;
  clientRequestId: string;
  previewFingerprint: string;
  definition: ExperimentPreviewRequest;
};

export type CreateBenchmarkExperimentResponse = {
  schemaVersion: 1;
  created: boolean;
  experiment: BenchmarkExperimentResource;
};

export type CancelBenchmarkExperimentInput = {
  experimentId: string;
  clientRequestId: string;
};

export type BenchmarkTaskRun = {
  schemaVersion: 1;
  taskRunId: string;
  experimentId: string;
  plannedEntryId: string;
  order: number;
  agentId: string;
  revisionId: string;
  taskId: string;
  repeat: number;
  derivedSeed: number;
  lifecycle: BenchmarkTaskRunLifecycle;
  terminalReason: BenchmarkTaskRunTerminalReason | null;
  processOwnerId: string;
  coreTaskRunId: string | null;
  agentRunId: string | null;
  taskInstanceIdentity: string | null;
  phases: BenchmarkTaskPhase[];
  agentStatus: string | null;
  benchmarkOutcome: string | null;
  evaluation: JsonValue | null;
  taskInstanceAvailability: BenchmarkAvailability;
  phaseAvailability: BenchmarkAvailability;
  agentStatusAvailability: BenchmarkAvailability;
  outcomeAvailability: BenchmarkAvailability;
  resultAvailability: BenchmarkAvailability;
  evaluationAvailability: BenchmarkAvailability;
  replayAvailability: BenchmarkAvailability;
  reportAvailability: BenchmarkAvailability;
  trajectoryAvailability: BenchmarkAvailability;
  bundleAvailability: BenchmarkAvailability;
  replayId: string | null;
  artifacts: BenchmarkArtifactDescriptor[];
  publicationDiagnostics: BenchmarkPublicationDiagnostic[];
  links: {
    self: string;
    artifacts: string | null;
    replay: string | null;
  } | null;
  result: BenchmarkTaskResult | null;
  resultFingerprint: string | null;
  createdAt: number;
  updatedAt: number;
  startedAt: number | null;
  evaluatingAt: number | null;
  cleaningUpAt: number | null;
  terminalAt: number | null;
};

export type BenchmarkTaskResult = Record<string, JsonValue> & {
  evidenceOrigin: ExecutionEvidenceOrigin;
};

/** Parse a TaskResult while retaining all versioned payload fields. */
function parseBenchmarkTaskResult(value: unknown, path: string): BenchmarkTaskResult {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  const cloned = cloneJson(value, path);
  if (!isRecord(cloned)) throw new Error(`${path} must be an object`);
  return {
    ...cloned,
    evidenceOrigin: parseExecutionEvidenceOrigin(
      value.evidenceOrigin,
      `${path}.evidenceOrigin`,
    ),
  };
}

export type BenchmarkTaskRunPage = {
  schemaVersion: 1;
  experimentId: string;
  items: BenchmarkTaskRun[];
  nextCursor: string | null;
};

export type BenchmarkExperimentHistoryItem = {
  schemaVersion: 1;
  experimentId: string;
  lifecycle: BenchmarkExperimentLifecycle;
  terminalReason: BenchmarkExperimentTerminalReason | null;
  source: {
    catalogEntryId: string;
    packageIdentity: string;
    split: string;
  };
  agents: Array<{ agentId: string; revisionId: string }>;
  plannedTaskRunCount: number;
  outcomeAvailability: BenchmarkAvailability;
  reportAvailability: BenchmarkAvailability;
  replayAvailability: BenchmarkAvailability;
  trajectoryAvailability: BenchmarkAvailability;
  bundleAvailability: BenchmarkAvailability;
  acceptedAt: number;
  updatedAt: number;
  terminalAt: number | null;
  links: {
    self: string;
    taskRuns: string;
    artifacts: string | null;
    report: string | null;
    bundle: string | null;
  };
};

export type BenchmarkExperimentHistoryPage = {
  schemaVersion: 1;
  items: BenchmarkExperimentHistoryItem[];
  nextCursor: string | null;
};

export type BenchmarkExperimentHistoryFilters = Readonly<{
  lifecycle?: BenchmarkExperimentLifecycle;
  catalogEntryId?: string;
  agentId?: string;
  acceptedFrom?: number;
  acceptedBefore?: number;
}>;

export type BenchmarkEventSource = "service" | "worker" | "core" | "agent";

export type BenchmarkExperimentEvent = {
  schemaVersion: 1;
  eventId: string;
  timestamp: number;
  source: BenchmarkEventSource;
  kind: string;
  taskRunId: string | null;
  sourceSequence: number | null;
  phase: string;
  payload: Record<string, JsonValue>;
  experimentId: string;
  sequence: number;
  fingerprint: string;
};

export type BenchmarkExperimentEventPage = {
  schemaVersion: 1;
  experimentId: string;
  items: BenchmarkExperimentEvent[];
  nextCursor: number;
  highWaterMark: number;
  terminal: boolean;
};

const EXPERIMENT_ID = /^experiment-[a-f0-9]{32}$/;
const TASK_RUN_ID = /^task-run-[a-f0-9]{32}$/;
const EVENT_ID = /^benchmark-event-[a-f0-9]{32}$/;
const REPLAY_ID = /^benchmark-replay-[a-f0-9]{32}$/;
const ARTIFACT_ID = /^artifact-[a-f0-9]{32}$/;
const HASH = /^sha256:[a-f0-9]{64}$/;
const LIFECYCLES = new Set<BenchmarkExperimentLifecycle>([
  "accepted",
  "starting",
  "running",
  "cancelling",
  "finalizing",
  "terminal",
]);
const TERMINAL_REASONS = new Set<BenchmarkExperimentTerminalReason>([
  "completed",
  "cancelled",
  "failed",
  "interrupted",
]);
const TASK_LIFECYCLES = new Set<BenchmarkTaskRunLifecycle>([
  "scheduled",
  "preparing",
  "evaluating",
  "cleaning_up",
  "starting",
  "running",
  "cancelling",
  "terminal",
]);
const TASK_TERMINAL_REASONS = new Set<BenchmarkTaskRunTerminalReason>([
  "completed",
  "cancelled_before_start",
  "cancelled",
  "failed",
  "interrupted",
]);
const AVAILABILITIES = new Set<BenchmarkAvailability>([
  "pending",
  "not_produced",
  "available",
  "failed",
]);
const ARTIFACT_AVAILABILITIES = new Set<BenchmarkArtifactAvailability>([
  ...AVAILABILITIES,
  "excluded",
  "hidden",
  "missing",
  "corrupt",
  "redacted",
  "truncated",
]);
const EVENT_SOURCES = new Set<BenchmarkEventSource>([
  "service",
  "worker",
  "core",
  "agent",
]);

/** Require a non-negative integer without accepting coercion. */
function requireNonNegativeInteger(value: unknown, path: string): number {
  const parsed = requireNumber(value, path);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`${path} must be a non-negative integer`);
  }
  return parsed;
}

/** Require a positive integer without accepting coercion. */
function requirePositiveInteger(value: unknown, path: string): number {
  const parsed = requireNonNegativeInteger(value, path);
  if (parsed < 1) {
    throw new Error(`${path} must be a positive integer`);
  }
  return parsed;
}

/** Require one nullable non-negative timestamp. */
function nullableTimestamp(value: unknown, path: string): number | null {
  return value === null || value === undefined
    ? null
    : requireNonNegativeInteger(value, path);
}

/** Require one strict boolean. */
function requireBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${path} must be a boolean`);
  return value;
}

/** Require one optional nullable string without coercion. */
function nullableString(value: unknown, path: string): string | null {
  return value === null || value === undefined
    ? null
    : requireString(value, path);
}

/** Parse one optional string that may intentionally be empty. */
function stringOrEmpty(value: unknown, path: string): string {
  if (value === undefined || value === null) return "";
  if (typeof value !== "string") throw new Error(`${path} must be a string`);
  return value;
}

/** Parse a string array and preserve supplied order. */
function parseStrings(value: unknown, path: string): string[] {
  if (!Array.isArray(value)) throw new Error(`${path} must be an array`);
  return value.map((item, index) => requireString(item, `${path}[${index}]`));
}

/** Parse one Stage 5 component availability fact. */
export function parseBenchmarkAvailability(
  value: unknown,
  path: string,
): BenchmarkAvailability {
  if (
    typeof value !== "string"
    || !AVAILABILITIES.has(value as BenchmarkAvailability)
  ) {
    throw new Error(`${path} has an unsupported availability`);
  }
  return value as BenchmarkAvailability;
}

/** Parse the complete managed Benchmark artifact availability vocabulary. */
export function parseBenchmarkArtifactAvailability(
  value: unknown,
  path: string,
): BenchmarkArtifactAvailability {
  if (
    typeof value !== "string"
    || !ARTIFACT_AVAILABILITIES.has(value as BenchmarkArtifactAvailability)
  ) {
    throw new Error(`${path} has an unsupported artifact availability`);
  }
  return value as BenchmarkArtifactAvailability;
}

/** Require one safe same-service path rather than an arbitrary URL. */
function parseSafeLink(value: unknown, path: string): string {
  const link = requireString(value, path);
  if (
    (!link.startsWith("/studio/") && !link.startsWith("/api/studio/"))
    || link.startsWith("//")
    || link.includes("\\")
    || link.split("/").includes("..")
  ) {
    throw new Error(`${path} must be a safe Studio path`);
  }
  return link;
}

/** Parse one optional safe Studio path. */
function optionalSafeLink(value: unknown, path: string): string | null {
  return value === null || value === undefined ? null : parseSafeLink(value, path);
}

/** Require a same-service link to match the exact expected resource scope. */
function parseExactLink(
  value: unknown,
  expected: string,
  path: string,
): string {
  const link = parseSafeLink(value, path);
  const normalized = link.startsWith("/api/") ? link.slice(4) : link;
  if (normalized !== expected) {
    throw new Error(`${path} does not match the expected resource scope`);
  }
  return link;
}

/** Parse an optional exact same-service link. */
function optionalExactLink(
  value: unknown,
  expected: string,
  path: string,
): string | null {
  return value === null || value === undefined
    ? null
    : parseExactLink(value, expected, path);
}

/** Parse a canonical SHA-256 identity. */
function parseHash(value: unknown, path: string): string {
  const hash = requireString(value, path);
  if (!HASH.test(hash)) throw new Error(`${path} must be a SHA-256 identity`);
  return hash;
}

/** Parse one safe publication diagnostic. */
export function parseBenchmarkPublicationDiagnostic(
  value: unknown,
  path: string,
): BenchmarkPublicationDiagnostic {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["code", "message", "component", "retryable"], path);
  return {
    code: requireString(value.code, `${path}.code`),
    message: requireString(value.message, `${path}.message`),
    component: stringOrEmpty(value.component, `${path}.component`),
    retryable: requireBoolean(value.retryable ?? false, `${path}.retryable`),
  };
}

/** Parse one managed Benchmark artifact descriptor. */
export function parseBenchmarkArtifactDescriptor(
  value: unknown,
  path: string,
): BenchmarkArtifactDescriptor {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "artifactId",
      "experimentId",
      "taskRunId",
      "kind",
      "availability",
      "contentType",
      "size",
      "sha256",
      "provenance",
      "causalIdentity",
      "hidden",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const artifactId = requireString(value.artifactId, `${path}.artifactId`);
  if (!ARTIFACT_ID.test(artifactId)) throw new Error(`${path}.artifactId is invalid`);
  const experimentId = requireString(value.experimentId, `${path}.experimentId`);
  if (!EXPERIMENT_ID.test(experimentId)) throw new Error(`${path}.experimentId is invalid`);
  const taskRunId = nullableString(value.taskRunId, `${path}.taskRunId`);
  if (taskRunId !== null && !TASK_RUN_ID.test(taskRunId)) {
    throw new Error(`${path}.taskRunId is invalid`);
  }
  const sha256 = nullableString(value.sha256, `${path}.sha256`);
  if (sha256 !== null && !HASH.test(sha256)) throw new Error(`${path}.sha256 is invalid`);
  const availability = parseBenchmarkArtifactAvailability(
    value.availability,
    `${path}.availability`,
  );
  const contentType = stringOrEmpty(value.contentType, `${path}.contentType`);
  const size = requireNonNegativeInteger(value.size ?? 0, `${path}.size`);
  const hidden = requireBoolean(value.hidden ?? false, `${path}.hidden`);
  const readable = ["available", "redacted", "truncated"].includes(availability);
  if (readable && (!contentType || sha256 === null)) {
    throw new Error(`${path} readable artifact requires content type and hash`);
  }
  if ((availability === "hidden") !== hidden) {
    throw new Error(`${path} hidden metadata conflicts with availability`);
  }
  if (hidden && (contentType !== "" || size !== 0 || sha256 !== null)) {
    throw new Error(`${path} hidden artifact exposes readable metadata`);
  }
  return {
    schemaVersion: 1,
    artifactId,
    experimentId,
    taskRunId,
    kind: requireString(value.kind, `${path}.kind`),
    availability,
    contentType,
    size,
    sha256,
    provenance: stringOrEmpty(value.provenance, `${path}.provenance`),
    causalIdentity: stringOrEmpty(value.causalIdentity, `${path}.causalIdentity`),
    hidden,
  };
}

/** Parse one immutable Agent snapshot and derive the shared read-only graph. */
export function parseBenchmarkAgentSnapshot(
  value: unknown,
  path: string,
): BenchmarkAgentSnapshot {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "agentId",
      "revisionId",
      "contractVersion",
      "compileContractVersion",
      "canonicalHash",
      "agentGraph",
      "presentation",
      "sourceMap",
      "providerIdentities",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const agentId = requireString(value.agentId, `${path}.agentId`);
  const revisionId = requireString(value.revisionId, `${path}.revisionId`);
  const contractVersion = requireString(
    value.contractVersion,
    `${path}.contractVersion`,
  );
  const canonicalHash = parseHash(value.canonicalHash, `${path}.canonicalHash`);
  const agentGraph = cloneJson(value.agentGraph, `${path}.agentGraph`);
  const presentation = cloneJson(value.presentation ?? {}, `${path}.presentation`);
  const sourceMap = Array.isArray(value.sourceMap)
    ? value.sourceMap.map((item, index) =>
        cloneJson(item, `${path}.sourceMap[${index}]`),
      )
    : (() => {
        throw new Error(`${path}.sourceMap must be an array`);
      })();
  const providerIdentities = parseStrings(
    value.providerIdentities ?? [],
    `${path}.providerIdentities`,
  );
  return {
    schemaVersion: 1,
    agentId,
    revisionId,
    contractVersion,
    compileContractVersion: requireString(
      value.compileContractVersion,
      `${path}.compileContractVersion`,
    ),
    canonicalHash,
    agentGraph,
    presentation,
    sourceMap,
    providerIdentities,
    runSnapshot: parseRunSnapshot(
      {
        agentId,
        revisionId,
        contractVersion,
        canonicalHash,
        graphStatus: "available",
        agentGraph,
        presentation,
        sourceMap,
        providerIdentities,
      },
      `${path}.runSnapshot`,
    ),
  };
}

/** Parse the immutable Experiment definition needed by Monitor and Graph. */
export function parseBenchmarkDefinitionSnapshot(
  value: unknown,
  path: string,
): BenchmarkDefinitionSnapshot {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "previewFingerprint",
      "snapshotFingerprint",
      "source",
      "agentSnapshots",
      "benchmarkPlan",
      "protocol",
      "split",
      "taskIds",
      "schedule",
      "deviceProfileId",
      "executionLimits",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  if (!isRecord(value.source)) throw new Error(`${path}.source must be an object`);
  rejectUnknownKeys(
    value.source,
    [
      "sourceId",
      "sourceKind",
      "relativeKey",
      "catalogEntryId",
      "packageIdentity",
      "packageContentIdentity",
      "benchmarkPlanIdentity",
      "experimentProtocolIdentity",
    ],
    `${path}.source`,
  );
  const sourceKind = requireString(value.source.sourceKind, `${path}.source.sourceKind`);
  if (!["package", "catalog", "installed"].includes(sourceKind)) {
    throw new Error(`${path}.source.sourceKind is unsupported`);
  }
  if (!Array.isArray(value.agentSnapshots) || value.agentSnapshots.length === 0) {
    throw new Error(`${path}.agentSnapshots must be a non-empty array`);
  }
  if (!Array.isArray(value.schedule) || value.schedule.length === 0) {
    throw new Error(`${path}.schedule must be a non-empty array`);
  }
  if (!isRecord(value.executionLimits)) {
    throw new Error(`${path}.executionLimits must be an object`);
  }
  rejectUnknownKeys(
    value.executionLimits,
    ["maxAgents", "maxSelectedTasks", "maxRepeats", "multiAgentComparison"],
    `${path}.executionLimits`,
  );
  return {
    schemaVersion: 1,
    previewFingerprint: parseHash(
      value.previewFingerprint,
      `${path}.previewFingerprint`,
    ),
    snapshotFingerprint: parseHash(
      value.snapshotFingerprint,
      `${path}.snapshotFingerprint`,
    ),
    source: {
      sourceId: requireString(value.source.sourceId, `${path}.source.sourceId`),
      sourceKind: sourceKind as "package" | "catalog" | "installed",
      relativeKey: requireString(
        value.source.relativeKey,
        `${path}.source.relativeKey`,
      ),
      catalogEntryId: requireString(
        value.source.catalogEntryId,
        `${path}.source.catalogEntryId`,
      ),
      packageIdentity: requireString(
        value.source.packageIdentity,
        `${path}.source.packageIdentity`,
      ),
      packageContentIdentity: parseHash(
        value.source.packageContentIdentity,
        `${path}.source.packageContentIdentity`,
      ),
      benchmarkPlanIdentity: parseHash(
        value.source.benchmarkPlanIdentity,
        `${path}.source.benchmarkPlanIdentity`,
      ),
      experimentProtocolIdentity: parseHash(
        value.source.experimentProtocolIdentity,
        `${path}.source.experimentProtocolIdentity`,
      ),
    },
    agentSnapshots: value.agentSnapshots.map((item, index) =>
      parseBenchmarkAgentSnapshot(item, `${path}.agentSnapshots[${index}]`),
    ),
    benchmarkPlan: cloneJson(value.benchmarkPlan, `${path}.benchmarkPlan`),
    protocol: cloneJson(value.protocol, `${path}.protocol`) as ExperimentProtocol,
    split: requireString(value.split, `${path}.split`),
    taskIds: parseStrings(value.taskIds, `${path}.taskIds`),
    schedule: value.schedule.map((item, index) => {
      const itemPath = `${path}.schedule[${index}]`;
      if (!isRecord(item)) throw new Error(`${itemPath} must be an object`);
      rejectUnknownKeys(
        item,
        [
          "plannedEntryId",
          "agentId",
          "revisionId",
          "taskId",
          "repeat",
          "order",
          "derivedSeed",
          "taskInstance",
        ],
        itemPath,
      );
      return {
        plannedEntryId: requireString(item.plannedEntryId, `${itemPath}.plannedEntryId`),
        agentId: requireString(item.agentId, `${itemPath}.agentId`),
        revisionId: requireString(item.revisionId, `${itemPath}.revisionId`),
        taskId: requireString(item.taskId, `${itemPath}.taskId`),
        repeat: requireNonNegativeInteger(item.repeat, `${itemPath}.repeat`),
        order: requireNonNegativeInteger(item.order, `${itemPath}.order`),
        derivedSeed: requireNumber(item.derivedSeed, `${itemPath}.derivedSeed`),
        taskInstance: cloneJson(item.taskInstance, `${itemPath}.taskInstance`),
      };
    }),
    deviceProfileId: requireString(
      value.deviceProfileId,
      `${path}.deviceProfileId`,
    ),
    executionLimits: {
      maxAgents: requireNonNegativeInteger(
        value.executionLimits.maxAgents,
        `${path}.executionLimits.maxAgents`,
      ),
      maxSelectedTasks: requireNonNegativeInteger(
        value.executionLimits.maxSelectedTasks,
        `${path}.executionLimits.maxSelectedTasks`,
      ),
      maxRepeats: requireNonNegativeInteger(
        value.executionLimits.maxRepeats,
        `${path}.executionLimits.maxRepeats`,
      ),
      multiAgentComparison: requireBoolean(
        value.executionLimits.multiAgentComparison,
        `${path}.executionLimits.multiAgentComparison`,
      ),
    },
  };
}

/** Parse one persisted Benchmark lifecycle phase. */
export function parseBenchmarkTaskPhase(
  value: unknown,
  path: string,
): BenchmarkTaskPhase {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["phase", "status", "durationMs", "errorCode", "message", "evidence", "artifactRefs"],
    path,
  );
  const evidence = cloneJson(value.evidence ?? {}, `${path}.evidence`);
  if (!isRecord(evidence)) throw new Error(`${path}.evidence must be an object`);
  return {
    phase: requireString(value.phase, `${path}.phase`),
    status: requireString(value.status, `${path}.status`),
    durationMs: requireNumber(value.durationMs ?? 0, `${path}.durationMs`),
    errorCode: stringOrEmpty(value.errorCode, `${path}.errorCode`),
    message: stringOrEmpty(value.message, `${path}.message`),
    evidence,
    artifactRefs: parseStrings(value.artifactRefs ?? [], `${path}.artifactRefs`),
  };
}

/** Parse a strict Benchmark TaskRun and its explicit availability facts. */
export function parseBenchmarkTaskRun(
  value: unknown,
  path = "taskRun",
): BenchmarkTaskRun {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "taskRunId",
      "experimentId",
      "plannedEntryId",
      "order",
      "agentId",
      "revisionId",
      "taskId",
      "repeat",
      "derivedSeed",
      "lifecycle",
      "terminalReason",
      "processOwnerId",
      "coreTaskRunId",
      "agentRunId",
      "taskInstanceIdentity",
      "phases",
      "agentStatus",
      "benchmarkOutcome",
      "evaluation",
      "taskInstanceAvailability",
      "phaseAvailability",
      "agentStatusAvailability",
      "outcomeAvailability",
      "resultAvailability",
      "evaluationAvailability",
      "replayAvailability",
      "reportAvailability",
      "trajectoryAvailability",
      "bundleAvailability",
      "replayId",
      "artifacts",
      "publicationDiagnostics",
      "links",
      "result",
      "resultFingerprint",
      "createdAt",
      "updatedAt",
      "startedAt",
      "evaluatingAt",
      "cleaningUpAt",
      "terminalAt",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const taskRunId = requireString(value.taskRunId, `${path}.taskRunId`);
  const experimentId = requireString(value.experimentId, `${path}.experimentId`);
  if (!TASK_RUN_ID.test(taskRunId)) throw new Error(`${path}.taskRunId is invalid`);
  if (!EXPERIMENT_ID.test(experimentId)) throw new Error(`${path}.experimentId is invalid`);
  const lifecycle = requireString(value.lifecycle, `${path}.lifecycle`);
  if (!TASK_LIFECYCLES.has(lifecycle as BenchmarkTaskRunLifecycle)) {
    throw new Error(`${path}.lifecycle is unsupported`);
  }
  const terminalReason = nullableString(value.terminalReason, `${path}.terminalReason`);
  if (
    terminalReason !== null
    && !TASK_TERMINAL_REASONS.has(terminalReason as BenchmarkTaskRunTerminalReason)
  ) {
    throw new Error(`${path}.terminalReason is unsupported`);
  }
  const terminalAt = nullableTimestamp(value.terminalAt, `${path}.terminalAt`);
  if (lifecycle === "terminal" ? terminalReason === null || terminalAt === null : terminalReason !== null || terminalAt !== null) {
    throw new Error(`${path} terminal fields conflict with lifecycle`);
  }
  const replayAvailability = parseBenchmarkAvailability(
    value.replayAvailability,
    `${path}.replayAvailability`,
  );
  const replayId = nullableString(value.replayId, `${path}.replayId`);
  if (
    (replayAvailability === "available") !== (replayId !== null)
    || (replayId !== null && !REPLAY_ID.test(replayId))
  ) {
    throw new Error(`${path} Replay identity conflicts with availability`);
  }
  let links: BenchmarkTaskRun["links"] = null;
  if (value.links !== null && value.links !== undefined) {
    if (!isRecord(value.links)) throw new Error(`${path}.links must be an object`);
    rejectUnknownKeys(value.links, ["self", "artifacts", "replay"], `${path}.links`);
    links = {
      self: parseSafeLink(value.links.self, `${path}.links.self`),
      artifacts: optionalSafeLink(value.links.artifacts, `${path}.links.artifacts`),
      replay: optionalSafeLink(value.links.replay, `${path}.links.replay`),
    };
  }
  return {
    schemaVersion: 1,
    taskRunId,
    experimentId,
    plannedEntryId: requireString(value.plannedEntryId, `${path}.plannedEntryId`),
    order: requireNonNegativeInteger(value.order, `${path}.order`),
    agentId: requireString(value.agentId, `${path}.agentId`),
    revisionId: requireString(value.revisionId, `${path}.revisionId`),
    taskId: requireString(value.taskId, `${path}.taskId`),
    repeat: requireNonNegativeInteger(value.repeat, `${path}.repeat`),
    derivedSeed: requireNumber(value.derivedSeed, `${path}.derivedSeed`),
    lifecycle: lifecycle as BenchmarkTaskRunLifecycle,
    terminalReason: terminalReason as BenchmarkTaskRunTerminalReason | null,
    processOwnerId: stringOrEmpty(value.processOwnerId, `${path}.processOwnerId`),
    coreTaskRunId: nullableString(value.coreTaskRunId, `${path}.coreTaskRunId`),
    agentRunId: nullableString(value.agentRunId, `${path}.agentRunId`),
    taskInstanceIdentity: nullableString(
      value.taskInstanceIdentity,
      `${path}.taskInstanceIdentity`,
    ),
    phases: Array.isArray(value.phases)
      ? value.phases.map((item, index) =>
          parseBenchmarkTaskPhase(item, `${path}.phases[${index}]`),
        )
      : (() => {
          throw new Error(`${path}.phases must be an array`);
        })(),
    agentStatus: nullableString(value.agentStatus, `${path}.agentStatus`),
    benchmarkOutcome: nullableString(
      value.benchmarkOutcome,
      `${path}.benchmarkOutcome`,
    ),
    evaluation:
      value.evaluation === null || value.evaluation === undefined
        ? null
        : cloneJson(value.evaluation, `${path}.evaluation`),
    taskInstanceAvailability: parseBenchmarkAvailability(
      value.taskInstanceAvailability,
      `${path}.taskInstanceAvailability`,
    ),
    phaseAvailability: parseBenchmarkAvailability(
      value.phaseAvailability,
      `${path}.phaseAvailability`,
    ),
    agentStatusAvailability: parseBenchmarkAvailability(
      value.agentStatusAvailability,
      `${path}.agentStatusAvailability`,
    ),
    outcomeAvailability: parseBenchmarkAvailability(
      value.outcomeAvailability,
      `${path}.outcomeAvailability`,
    ),
    resultAvailability: parseBenchmarkAvailability(
      value.resultAvailability,
      `${path}.resultAvailability`,
    ),
    evaluationAvailability: parseBenchmarkAvailability(
      value.evaluationAvailability,
      `${path}.evaluationAvailability`,
    ),
    replayAvailability,
    reportAvailability: parseBenchmarkAvailability(
      value.reportAvailability,
      `${path}.reportAvailability`,
    ),
    trajectoryAvailability: parseBenchmarkAvailability(
      value.trajectoryAvailability,
      `${path}.trajectoryAvailability`,
    ),
    bundleAvailability: parseBenchmarkAvailability(
      value.bundleAvailability,
      `${path}.bundleAvailability`,
    ),
    replayId,
    artifacts: Array.isArray(value.artifacts)
      ? value.artifacts.map((item, index) =>
          parseBenchmarkArtifactDescriptor(item, `${path}.artifacts[${index}]`),
        )
      : (() => {
          throw new Error(`${path}.artifacts must be an array`);
        })(),
    publicationDiagnostics: Array.isArray(value.publicationDiagnostics)
      ? value.publicationDiagnostics.map((item, index) =>
          parseBenchmarkPublicationDiagnostic(
            item,
            `${path}.publicationDiagnostics[${index}]`,
          ),
        )
      : (() => {
          throw new Error(`${path}.publicationDiagnostics must be an array`);
        })(),
    links,
    result:
      value.result === null || value.result === undefined
        ? null
        : parseBenchmarkTaskResult(value.result, `${path}.result`),
    resultFingerprint: nullableString(
      value.resultFingerprint,
      `${path}.resultFingerprint`,
    ),
    createdAt: requireNonNegativeInteger(value.createdAt, `${path}.createdAt`),
    updatedAt: requireNonNegativeInteger(value.updatedAt, `${path}.updatedAt`),
    startedAt: nullableTimestamp(value.startedAt, `${path}.startedAt`),
    evaluatingAt: nullableTimestamp(value.evaluatingAt, `${path}.evaluatingAt`),
    cleaningUpAt: nullableTimestamp(
      value.cleaningUpAt,
      `${path}.cleaningUpAt`,
    ),
    terminalAt,
  };
}

/** Parse a bounded TaskRun page and enforce Experiment scoping and order. */
export function parseBenchmarkTaskRunPage(
  value: unknown,
  path = "taskRunPage",
): BenchmarkTaskRunPage {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["schemaVersion", "experimentId", "items", "nextCursor"], path);
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const experimentId = requireString(value.experimentId, `${path}.experimentId`);
  if (!EXPERIMENT_ID.test(experimentId)) throw new Error(`${path}.experimentId is invalid`);
  if (!Array.isArray(value.items)) throw new Error(`${path}.items must be an array`);
  const items = value.items.map((item, index) =>
    parseBenchmarkTaskRun(item, `${path}.items[${index}]`),
  );
  if (items.some((item) => item.experimentId !== experimentId)) {
    throw new Error(`${path} contains a cross-Experiment TaskRun`);
  }
  for (let index = 1; index < items.length; index += 1) {
    if (items[index - 1]!.order > items[index]!.order) {
      throw new Error(`${path}.items must preserve planned order`);
    }
  }
  return {
    schemaVersion: 1,
    experimentId,
    items,
    nextCursor: nullableString(value.nextCursor, `${path}.nextCursor`),
  };
}

/** Parse one compact immutable Experiment history summary. */
export function parseBenchmarkExperimentHistoryItem(
  value: unknown,
  path = "historyItem",
): BenchmarkExperimentHistoryItem {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "experimentId",
      "lifecycle",
      "terminalReason",
      "source",
      "agents",
      "plannedTaskRunCount",
      "outcomeAvailability",
      "reportAvailability",
      "replayAvailability",
      "trajectoryAvailability",
      "bundleAvailability",
      "acceptedAt",
      "updatedAt",
      "terminalAt",
      "links",
    ],
    path,
  );
  if (value.schemaVersion !== 1) {
    throw new Error(`${path}.schemaVersion is unsupported`);
  }
  const experimentId = requireString(value.experimentId, `${path}.experimentId`);
  if (!EXPERIMENT_ID.test(experimentId)) {
    throw new Error(`${path}.experimentId is invalid`);
  }
  const lifecycle = requireString(value.lifecycle, `${path}.lifecycle`);
  if (!LIFECYCLES.has(lifecycle as BenchmarkExperimentLifecycle)) {
    throw new Error(`${path}.lifecycle is unsupported`);
  }
  const terminalReason = nullableString(value.terminalReason, `${path}.terminalReason`);
  if (
    terminalReason !== null
    && !TERMINAL_REASONS.has(terminalReason as BenchmarkExperimentTerminalReason)
  ) {
    throw new Error(`${path}.terminalReason is unsupported`);
  }
  const acceptedAt = requireNonNegativeInteger(value.acceptedAt, `${path}.acceptedAt`);
  const updatedAt = requireNonNegativeInteger(value.updatedAt, `${path}.updatedAt`);
  const terminalAt = nullableTimestamp(value.terminalAt, `${path}.terminalAt`);
  if (
    lifecycle === "terminal"
      ? terminalReason === null || terminalAt === null
      : terminalReason !== null || terminalAt !== null
  ) {
    throw new Error(`${path} terminal fields conflict with lifecycle`);
  }
  if (
    updatedAt < acceptedAt
    || (terminalAt !== null && terminalAt < acceptedAt)
  ) {
    throw new Error(`${path} timestamps are inconsistent`);
  }
  if (!isRecord(value.source)) throw new Error(`${path}.source must be an object`);
  rejectUnknownKeys(
    value.source,
    ["catalogEntryId", "packageIdentity", "split"],
    `${path}.source`,
  );
  if (!Array.isArray(value.agents) || value.agents.length === 0 || value.agents.length > 100) {
    throw new Error(`${path}.agents must be a bounded non-empty array`);
  }
  const agents = value.agents.map((agent, index) => {
    const agentPath = `${path}.agents[${index}]`;
    if (!isRecord(agent)) throw new Error(`${agentPath} must be an object`);
    rejectUnknownKeys(agent, ["agentId", "revisionId"], agentPath);
    return {
      agentId: requireString(agent.agentId, `${agentPath}.agentId`),
      revisionId: requireString(agent.revisionId, `${agentPath}.revisionId`),
    };
  });
  if (
    new Set(agents.map((agent) => `${agent.agentId}\0${agent.revisionId}`)).size
    !== agents.length
  ) {
    throw new Error(`${path}.agents contains duplicate identities`);
  }
  const reportAvailability = parseBenchmarkAvailability(
    value.reportAvailability,
    `${path}.reportAvailability`,
  );
  const bundleAvailability = parseBenchmarkAvailability(
    value.bundleAvailability,
    `${path}.bundleAvailability`,
  );
  if (!isRecord(value.links)) throw new Error(`${path}.links must be an object`);
  rejectUnknownKeys(
    value.links,
    ["self", "taskRuns", "artifacts", "report", "bundle"],
    `${path}.links`,
  );
  const base = `/studio/benchmark-experiments/${experimentId}`;
  const report = optionalExactLink(
    value.links.report,
    `${base}/report`,
    `${path}.links.report`,
  );
  const bundle = optionalExactLink(
    value.links.bundle,
    `${base}/bundle`,
    `${path}.links.bundle`,
  );
  if (report !== null && reportAvailability !== "available") {
    throw new Error(`${path}.links.report conflicts with availability`);
  }
  if (bundle !== null && bundleAvailability !== "available") {
    throw new Error(`${path}.links.bundle conflicts with availability`);
  }
  return {
    schemaVersion: 1,
    experimentId,
    lifecycle: lifecycle as BenchmarkExperimentLifecycle,
    terminalReason: terminalReason as BenchmarkExperimentTerminalReason | null,
    source: {
      catalogEntryId: requireString(
        value.source.catalogEntryId,
        `${path}.source.catalogEntryId`,
      ),
      packageIdentity: requireString(
        value.source.packageIdentity,
        `${path}.source.packageIdentity`,
      ),
      split: requireString(value.source.split, `${path}.source.split`),
    },
    agents,
    plannedTaskRunCount: requirePositiveInteger(
      value.plannedTaskRunCount,
      `${path}.plannedTaskRunCount`,
    ),
    outcomeAvailability: parseBenchmarkAvailability(
      value.outcomeAvailability,
      `${path}.outcomeAvailability`,
    ),
    reportAvailability,
    replayAvailability: parseBenchmarkAvailability(
      value.replayAvailability,
      `${path}.replayAvailability`,
    ),
    trajectoryAvailability: parseBenchmarkAvailability(
      value.trajectoryAvailability,
      `${path}.trajectoryAvailability`,
    ),
    bundleAvailability,
    acceptedAt,
    updatedAt,
    terminalAt,
    links: {
      self: parseExactLink(value.links.self, base, `${path}.links.self`),
      taskRuns: parseExactLink(
        value.links.taskRuns,
        `${base}/task-runs`,
        `${path}.links.taskRuns`,
      ),
      artifacts: optionalExactLink(
        value.links.artifacts,
        `${base}/artifacts`,
        `${path}.links.artifacts`,
      ),
      report,
      bundle,
    },
  };
}

/** Parse a bounded newest-first Experiment history page. */
export function parseBenchmarkExperimentHistoryPage(
  value: unknown,
  path = "historyPage",
): BenchmarkExperimentHistoryPage {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["schemaVersion", "items", "nextCursor"], path);
  if (value.schemaVersion !== 1) {
    throw new Error(`${path}.schemaVersion is unsupported`);
  }
  if (!Array.isArray(value.items) || value.items.length > 100) {
    throw new Error(`${path}.items must be a bounded array`);
  }
  const items = value.items.map((item, index) =>
    parseBenchmarkExperimentHistoryItem(item, `${path}.items[${index}]`),
  );
  const identities = new Set<string>();
  for (let index = 0; index < items.length; index += 1) {
    const current = items[index]!;
    if (identities.has(current.experimentId)) {
      throw new Error(`${path}.items contains duplicate Experiments`);
    }
    identities.add(current.experimentId);
    const previous = items[index - 1];
    if (
      previous !== undefined
      && (
        previous.acceptedAt < current.acceptedAt
        || (
          previous.acceptedAt === current.acceptedAt
          && previous.experimentId < current.experimentId
        )
      )
    ) {
      throw new Error(`${path}.items must be newest first`);
    }
  }
  return {
    schemaVersion: 1,
    items,
    nextCursor: nullableString(value.nextCursor, `${path}.nextCursor`),
  };
}

/** Parse a safe public Benchmark Experiment resource and lifecycle invariants. */
export function parseBenchmarkExperimentResource(
  value: unknown,
  path = "experiment",
): BenchmarkExperimentResource {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "experimentId",
      "clientRequestId",
      "definition",
      "lifecycle",
      "terminalReason",
      "cancellation",
      "outcomeAvailability",
      "reportAvailability",
      "replayAvailability",
      "trajectoryAvailability",
      "bundleAvailability",
      "publicationDiagnostics",
      "eventHighWaterMark",
      "acceptedAt",
      "updatedAt",
      "terminalAt",
      "capabilities",
      "links",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const experimentId = requireString(value.experimentId, `${path}.experimentId`);
  if (!EXPERIMENT_ID.test(experimentId)) throw new Error(`${path}.experimentId is invalid`);
  const lifecycle = requireString(value.lifecycle, `${path}.lifecycle`);
  if (!LIFECYCLES.has(lifecycle as BenchmarkExperimentLifecycle)) {
    throw new Error(`${path}.lifecycle is unsupported`);
  }
  const terminalReason = nullableString(value.terminalReason, `${path}.terminalReason`);
  if (
    terminalReason !== null
    && !TERMINAL_REASONS.has(terminalReason as BenchmarkExperimentTerminalReason)
  ) {
    throw new Error(`${path}.terminalReason is unsupported`);
  }
  const terminalAt = nullableTimestamp(value.terminalAt, `${path}.terminalAt`);
  if (lifecycle === "terminal" ? terminalReason === null || terminalAt === null : terminalReason !== null || terminalAt !== null) {
    throw new Error(`${path} terminal fields conflict with lifecycle`);
  }
  let cancellation: BenchmarkExperimentResource["cancellation"] = null;
  if (value.cancellation !== null && value.cancellation !== undefined) {
    if (!isRecord(value.cancellation)) {
      throw new Error(`${path}.cancellation must be an object`);
    }
    rejectUnknownKeys(
      value.cancellation,
      ["schemaVersion", "clientRequestId", "requestedAt", "reasonCode"],
      `${path}.cancellation`,
    );
    if (
      value.cancellation.schemaVersion !== 1
      || value.cancellation.reasonCode !== "user_requested"
    ) {
      throw new Error(`${path}.cancellation is unsupported`);
    }
    cancellation = {
      schemaVersion: 1,
      clientRequestId: requireString(
        value.cancellation.clientRequestId,
        `${path}.cancellation.clientRequestId`,
      ),
      requestedAt: requireNonNegativeInteger(
        value.cancellation.requestedAt,
        `${path}.cancellation.requestedAt`,
      ),
      reasonCode: "user_requested",
    };
  }
  if (!isRecord(value.capabilities)) {
    throw new Error(`${path}.capabilities must be an object`);
  }
  rejectUnknownKeys(
    value.capabilities,
    ["executes", "cancelAccepted", "cancelActive", "eventStream", "replay", "reports"],
    `${path}.capabilities`,
  );
  if (value.capabilities.cancelAccepted !== true) {
    throw new Error(`${path}.capabilities.cancelAccepted must be true`);
  }
  if (!isRecord(value.links)) throw new Error(`${path}.links must be an object`);
  rejectUnknownKeys(
    value.links,
    [
      "self",
      "cancel",
      "taskRuns",
      "artifacts",
      "events",
      "eventStream",
      "report",
      "bundle",
    ],
    `${path}.links`,
  );
  const base = `/studio/benchmark-experiments/${experimentId}`;
  const cancelLink = optionalExactLink(
    value.links.cancel,
    `${base}/cancel`,
    `${path}.links.cancel`,
  );
  if ((lifecycle === "terminal") === (cancelLink !== null)) {
    throw new Error(`${path}.links.cancel conflicts with lifecycle`);
  }
  const reportAvailability = parseBenchmarkAvailability(
    value.reportAvailability,
    `${path}.reportAvailability`,
  );
  const bundleAvailability = parseBenchmarkAvailability(
    value.bundleAvailability,
    `${path}.bundleAvailability`,
  );
  const reports = requireBoolean(
    value.capabilities.reports,
    `${path}.capabilities.reports`,
  );
  const reportLink = optionalExactLink(
    value.links.report,
    `${base}/report`,
    `${path}.links.report`,
  );
  const bundleLink = optionalExactLink(
    value.links.bundle,
    `${base}/bundle`,
    `${path}.links.bundle`,
  );
  const artifactsLink = optionalExactLink(
    value.links.artifacts,
    `${base}/artifacts`,
    `${path}.links.artifacts`,
  );
  if (reportLink !== null && reportAvailability !== "available") {
    throw new Error(`${path}.links.report conflicts with availability`);
  }
  if (bundleLink !== null && bundleAvailability !== "available") {
    throw new Error(`${path}.links.bundle conflicts with availability`);
  }
  if (!reports && (reportLink !== null || bundleLink !== null || artifactsLink !== null)) {
    throw new Error(`${path}.links reporting capabilities are unavailable`);
  }
  return {
    schemaVersion: 1,
    experimentId,
    clientRequestId: requireString(
      value.clientRequestId,
      `${path}.clientRequestId`,
    ),
    definition: parseBenchmarkDefinitionSnapshot(
      value.definition,
      `${path}.definition`,
    ),
    lifecycle: lifecycle as BenchmarkExperimentLifecycle,
    terminalReason: terminalReason as BenchmarkExperimentTerminalReason | null,
    cancellation,
    outcomeAvailability: parseBenchmarkAvailability(
      value.outcomeAvailability,
      `${path}.outcomeAvailability`,
    ),
    reportAvailability,
    replayAvailability: parseBenchmarkAvailability(
      value.replayAvailability,
      `${path}.replayAvailability`,
    ),
    trajectoryAvailability: parseBenchmarkAvailability(
      value.trajectoryAvailability,
      `${path}.trajectoryAvailability`,
    ),
    bundleAvailability,
    publicationDiagnostics: Array.isArray(value.publicationDiagnostics)
      ? value.publicationDiagnostics.map((item, index) =>
          parseBenchmarkPublicationDiagnostic(
            item,
            `${path}.publicationDiagnostics[${index}]`,
          ),
        )
      : (() => {
          throw new Error(`${path}.publicationDiagnostics must be an array`);
        })(),
    eventHighWaterMark: requireNonNegativeInteger(
      value.eventHighWaterMark,
      `${path}.eventHighWaterMark`,
    ),
    acceptedAt: requireNonNegativeInteger(value.acceptedAt, `${path}.acceptedAt`),
    updatedAt: requireNonNegativeInteger(value.updatedAt, `${path}.updatedAt`),
    terminalAt,
    capabilities: {
      executes: requireBoolean(
        value.capabilities.executes,
        `${path}.capabilities.executes`,
      ),
      cancelAccepted: true,
      cancelActive: requireBoolean(
        value.capabilities.cancelActive,
        `${path}.capabilities.cancelActive`,
      ),
      eventStream: requireBoolean(
        value.capabilities.eventStream,
        `${path}.capabilities.eventStream`,
      ),
      replay: requireBoolean(
        value.capabilities.replay,
        `${path}.capabilities.replay`,
      ),
      reports,
    },
    links: {
      self: parseExactLink(value.links.self, base, `${path}.links.self`),
      cancel: cancelLink,
      taskRuns: parseExactLink(
        value.links.taskRuns,
        `${base}/task-runs`,
        `${path}.links.taskRuns`,
      ),
      artifacts: artifactsLink,
      events: optionalExactLink(
        value.links.events,
        `${base}/events`,
        `${path}.links.events`,
      ),
      eventStream: optionalExactLink(
        value.links.eventStream,
        `${base}/events/stream`,
        `${path}.links.eventStream`,
      ),
      report: reportLink,
      bundle: bundleLink,
    },
  };
}

/** Parse one idempotent create wrapper without weakening its Experiment. */
export function parseCreateBenchmarkExperimentResponse(
  value: unknown,
): CreateBenchmarkExperimentResponse {
  if (!isRecord(value)) throw new Error("createExperiment must be an object");
  rejectUnknownKeys(value, ["schemaVersion", "created", "experiment"], "createExperiment");
  if (value.schemaVersion !== 1) {
    throw new Error("createExperiment.schemaVersion is unsupported");
  }
  return {
    schemaVersion: 1,
    created: requireBoolean(value.created, "createExperiment.created"),
    experiment: parseBenchmarkExperimentResource(
      value.experiment,
      "createExperiment.experiment",
    ),
  };
}

/** Parse one committed Benchmark journal envelope, including future kinds. */
export function parseBenchmarkExperimentEvent(
  value: unknown,
  path = "benchmarkEvent",
): BenchmarkExperimentEvent {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "eventId",
      "timestamp",
      "source",
      "kind",
      "taskRunId",
      "sourceSequence",
      "phase",
      "payload",
      "experimentId",
      "sequence",
      "fingerprint",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const eventId = requireString(value.eventId, `${path}.eventId`);
  const experimentId = requireString(value.experimentId, `${path}.experimentId`);
  const source = requireString(value.source, `${path}.source`);
  if (!EVENT_ID.test(eventId)) throw new Error(`${path}.eventId is invalid`);
  if (!EXPERIMENT_ID.test(experimentId)) throw new Error(`${path}.experimentId is invalid`);
  if (!EVENT_SOURCES.has(source as BenchmarkEventSource)) {
    throw new Error(`${path}.source is unsupported`);
  }
  const taskRunId = nullableString(value.taskRunId, `${path}.taskRunId`);
  if (taskRunId !== null && !TASK_RUN_ID.test(taskRunId)) {
    throw new Error(`${path}.taskRunId is invalid`);
  }
  const payload = cloneJson(value.payload ?? {}, `${path}.payload`);
  if (!isRecord(payload)) throw new Error(`${path}.payload must be an object`);
  return {
    schemaVersion: 1,
    eventId,
    timestamp: requireNonNegativeInteger(value.timestamp, `${path}.timestamp`),
    source: source as BenchmarkEventSource,
    kind: requireString(value.kind, `${path}.kind`),
    taskRunId,
    sourceSequence:
      value.sourceSequence === null || value.sourceSequence === undefined
        ? null
        : requireNonNegativeInteger(value.sourceSequence, `${path}.sourceSequence`),
    phase: stringOrEmpty(value.phase, `${path}.phase`),
    payload,
    experimentId,
    sequence: requireNonNegativeInteger(value.sequence, `${path}.sequence`),
    fingerprint: parseHash(value.fingerprint, `${path}.fingerprint`),
  };
}

/** Parse a bounded continuous event page and validate its internal ordering. */
export function parseBenchmarkExperimentEventPage(
  value: unknown,
  path = "benchmarkEventPage",
): BenchmarkExperimentEventPage {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["schemaVersion", "experimentId", "items", "nextCursor", "highWaterMark", "terminal"],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const experimentId = requireString(value.experimentId, `${path}.experimentId`);
  if (!EXPERIMENT_ID.test(experimentId)) throw new Error(`${path}.experimentId is invalid`);
  if (!Array.isArray(value.items)) throw new Error(`${path}.items must be an array`);
  const items = value.items.map((item, index) =>
    parseBenchmarkExperimentEvent(item, `${path}.items[${index}]`),
  );
  if (items.some((item) => item.experimentId !== experimentId)) {
    throw new Error(`${path} contains a cross-Experiment event`);
  }
  for (let index = 1; index < items.length; index += 1) {
    if (items[index]!.sequence !== items[index - 1]!.sequence + 1) {
      throw new Error(`${path}.items are not continuous`);
    }
  }
  const nextCursor = requireNonNegativeInteger(
    value.nextCursor,
    `${path}.nextCursor`,
  );
  const highWaterMark = requireNonNegativeInteger(
    value.highWaterMark,
    `${path}.highWaterMark`,
  );
  if (nextCursor > highWaterMark) {
    throw new Error(`${path}.nextCursor exceeds highWaterMark`);
  }
  if (items.length > 0 && items.at(-1)!.sequence !== nextCursor) {
    throw new Error(`${path}.nextCursor does not match the final item`);
  }
  return {
    schemaVersion: 1,
    experimentId,
    items,
    nextCursor,
    highWaterMark,
    terminal: requireBoolean(value.terminal, `${path}.terminal`),
  };
}
