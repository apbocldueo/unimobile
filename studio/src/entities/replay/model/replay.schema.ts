import {
  cloneJson,
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
  type JsonValue,
} from "@/shared/lib";
import type { ExecutionEvidenceOrigin } from "@/entities/evidence-origin";
import {
  parseEvidenceAvailability,
  parseReplayListItem,
  parseRunResult,
  parseRunSnapshot,
  type EvidenceAvailability,
  type ReplayIntegrityState,
  type ReplayListItem,
  type RunResultSummary,
  type RunSnapshot,
} from "@/entities/run";
import {
  parseReplayArtifact,
  type ReplayArtifact,
} from "@/entities/artifact";
import {
  parseBenchmarkContext,
  type BenchmarkContext,
} from "@/entities/benchmark";

export type ReplaySourceKind =
  | "benchmark_lifecycle"
  | "agent_graph"
  | "observation"
  | "action"
  | "run_result";

export type ReplayMoment = {
  momentId: string;
  causalIndex: number;
  sourceKind: ReplaySourceKind;
  sourceSequence: number | null;
  timestamp: number | null;
  phase: string;
  kind: string;
  role: string;
  component: string;
  nodeId: string;
  nodePath: string;
  activationId: string;
  parentActivationId: string;
  loopPath: string;
  loopIteration: number | null;
  interactionStep: number;
  durationMs: number | null;
  payload: JsonValue;
  observationId: string | null;
  actionId: string | null;
  artifactIds: string[];
};

export type ReplayObservation = {
  observationId: string;
  sequence: number;
  interactionStep: number;
  screenshotArtifactId: string | null;
  uiArtifactId: string | null;
  width: number;
  height: number;
  platform: string;
  deviceId: string;
  overlay: JsonValue[];
};

export type ReplayAction = {
  actionId: string;
  sequence: number;
  interactionStep: number;
  status: string;
  actionType: string;
  effectPerformed: boolean;
  effectKind: string;
  terminalStatus: string | null;
  message: string;
  error: string;
  artifactId: string | null;
};

export type ReplayDiagnostic = {
  code: string;
  message: string;
  severity: "warning" | "error";
  source: string;
  causalIndex: number | null;
};

export type ReplayEnvelope = {
  schemaVersion: 1;
  runId: string;
  importedAt: number;
  provenance: ReplayListItem["provenance"];
  evidenceOrigin: ExecutionEvidenceOrigin;
  integrityState: ReplayIntegrityState;
  snapshot: RunSnapshot;
  result: RunResultSummary;
  moments: ReplayMoment[];
  observations: ReplayObservation[];
  actions: ReplayAction[];
  benchmark: BenchmarkContext | null;
  artifacts: ReplayArtifact[];
  availability: Record<string, EvidenceAvailability>;
  integrity: ReplayDiagnostic[];
};

export type ReplayPage = {
  items: ReplayListItem[];
  nextCursor: string | null;
};

const SOURCE_KINDS = new Set<ReplaySourceKind>([
  "benchmark_lifecycle",
  "agent_graph",
  "observation",
  "action",
  "run_result",
]);

/** Parse one nullable finite number. */
function optionalNumber(value: unknown, path: string): number | null {
  return value === null || value === undefined ? null : requireNumber(value, path);
}

/** Parse one nullable string. */
function optionalString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** Parse one normalized causal Replay moment. */
function parseReplayMoment(value: unknown, path: string): ReplayMoment {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "momentId",
      "causalIndex",
      "sourceKind",
      "sourceSequence",
      "timestamp",
      "phase",
      "kind",
      "role",
      "component",
      "nodeId",
      "nodePath",
      "activationId",
      "parentActivationId",
      "loopPath",
      "loopIteration",
      "interactionStep",
      "durationMs",
      "payload",
      "observationId",
      "actionId",
      "artifactIds",
    ],
    path,
  );
  const sourceKind = requireString(value.sourceKind, `${path}.sourceKind`);
  if (!SOURCE_KINDS.has(sourceKind as ReplaySourceKind)) {
    throw new Error(`${path}.sourceKind is unsupported`);
  }
  return {
    momentId: requireString(value.momentId, `${path}.momentId`),
    causalIndex: requireNumber(value.causalIndex, `${path}.causalIndex`),
    sourceKind: sourceKind as ReplaySourceKind,
    sourceSequence: optionalNumber(value.sourceSequence, `${path}.sourceSequence`),
    timestamp: optionalNumber(value.timestamp, `${path}.timestamp`),
    phase: typeof value.phase === "string" ? value.phase : "",
    kind: requireString(value.kind, `${path}.kind`),
    role: typeof value.role === "string" ? value.role : "",
    component: typeof value.component === "string" ? value.component : "",
    nodeId: typeof value.nodeId === "string" ? value.nodeId : "",
    nodePath: typeof value.nodePath === "string" ? value.nodePath : "",
    activationId: typeof value.activationId === "string" ? value.activationId : "",
    parentActivationId:
      typeof value.parentActivationId === "string" ? value.parentActivationId : "",
    loopPath: typeof value.loopPath === "string" ? value.loopPath : "",
    loopIteration: optionalNumber(value.loopIteration, `${path}.loopIteration`),
    interactionStep: requireNumber(value.interactionStep, `${path}.interactionStep`),
    durationMs: optionalNumber(value.durationMs, `${path}.durationMs`),
    payload: cloneJson(value.payload ?? {}, `${path}.payload`),
    observationId: optionalString(value.observationId),
    actionId: optionalString(value.actionId),
    artifactIds: Array.isArray(value.artifactIds)
      ? value.artifactIds.map((item, index) =>
          requireString(item, `${path}.artifactIds[${index}]`),
        )
      : [],
  };
}

/** Parse one correlated Replay observation. */
function parseReplayObservation(value: unknown, path: string): ReplayObservation {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "observationId",
      "sequence",
      "interactionStep",
      "screenshotArtifactId",
      "uiArtifactId",
      "width",
      "height",
      "platform",
      "deviceId",
      "overlay",
    ],
    path,
  );
  return {
    observationId: requireString(value.observationId, `${path}.observationId`),
    sequence: requireNumber(value.sequence, `${path}.sequence`),
    interactionStep: requireNumber(value.interactionStep, `${path}.interactionStep`),
    screenshotArtifactId: optionalString(value.screenshotArtifactId),
    uiArtifactId: optionalString(value.uiArtifactId),
    width: requireNumber(value.width, `${path}.width`),
    height: requireNumber(value.height, `${path}.height`),
    platform: typeof value.platform === "string" ? value.platform : "",
    deviceId: typeof value.deviceId === "string" ? value.deviceId : "",
    overlay: Array.isArray(value.overlay)
      ? value.overlay.map((item, index) => cloneJson(item, `${path}.overlay[${index}]`))
      : [],
  };
}

/** Parse one correlated Replay action result. */
function parseReplayAction(value: unknown, path: string): ReplayAction {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "actionId",
      "sequence",
      "interactionStep",
      "status",
      "actionType",
      "effectPerformed",
      "effectKind",
      "terminalStatus",
      "message",
      "error",
      "artifactId",
    ],
    path,
  );
  return {
    actionId: requireString(value.actionId, `${path}.actionId`),
    sequence: requireNumber(value.sequence, `${path}.sequence`),
    interactionStep: requireNumber(value.interactionStep, `${path}.interactionStep`),
    status: requireString(value.status, `${path}.status`),
    actionType: requireString(value.actionType, `${path}.actionType`),
    effectPerformed: value.effectPerformed === true,
    effectKind: typeof value.effectKind === "string" ? value.effectKind : "",
    terminalStatus: optionalString(value.terminalStatus),
    message: typeof value.message === "string" ? value.message : "",
    error: typeof value.error === "string" ? value.error : "",
    artifactId: optionalString(value.artifactId),
  };
}

/** Parse one safe integrity diagnostic. */
function parseReplayDiagnostic(value: unknown, path: string): ReplayDiagnostic {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["code", "message", "severity", "source", "causalIndex"], path);
  const severity = requireString(value.severity, `${path}.severity`);
  if (severity !== "warning" && severity !== "error") {
    throw new Error(`${path}.severity is unsupported`);
  }
  return {
    code: requireString(value.code, `${path}.code`),
    message: requireString(value.message, `${path}.message`),
    severity,
    source: typeof value.source === "string" ? value.source : "",
    causalIndex: optionalNumber(value.causalIndex, `${path}.causalIndex`),
  };
}

/** Strictly parse a complete persisted Replay resource. */
export function parseReplayEnvelope(value: unknown): ReplayEnvelope {
  if (!isRecord(value)) throw new Error("Replay response must be an object");
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "runId",
      "importedAt",
      "provenance",
      "evidenceOrigin",
      "integrityState",
      "snapshot",
      "result",
      "moments",
      "observations",
      "actions",
      "benchmark",
      "artifacts",
      "availability",
      "integrity",
    ],
    "replay",
  );
  if (value.schemaVersion !== 1) throw new Error("Replay schemaVersion is unsupported");
  const summary = parseReplayListItem(
    {
      runId: value.runId,
      agentId: isRecord(value.snapshot) ? value.snapshot.agentId : "",
      agentStatus: isRecord(value.result) ? value.result.status : "",
      benchmarkOutcome: isRecord(value.benchmark) ? value.benchmark.outcome : null,
      provenance: value.provenance,
      evidenceOrigin: value.evidenceOrigin,
      integrityState: value.integrityState,
      evidenceCompleteness: 0,
      importedAt: value.importedAt,
    },
    "replay.summary",
  );
  if (!isRecord(value.availability)) {
    throw new Error("replay.availability must be an object");
  }
  const moments = Array.isArray(value.moments)
    ? value.moments.map((item, index) => parseReplayMoment(item, `replay.moments[${index}]`))
    : [];
  for (let index = 1; index < moments.length; index += 1) {
    if (moments[index]!.causalIndex < moments[index - 1]!.causalIndex) {
      throw new Error("Replay moments must be ordered by causalIndex");
    }
  }
  return {
    schemaVersion: 1,
    runId: summary.runId,
    importedAt: summary.importedAt,
    provenance: summary.provenance,
    evidenceOrigin: summary.evidenceOrigin,
    integrityState: summary.integrityState,
    snapshot: parseRunSnapshot(value.snapshot),
    result: parseRunResult(value.result),
    moments,
    observations: Array.isArray(value.observations)
      ? value.observations.map((item, index) =>
          parseReplayObservation(item, `replay.observations[${index}]`),
        )
      : [],
    actions: Array.isArray(value.actions)
      ? value.actions.map((item, index) =>
          parseReplayAction(item, `replay.actions[${index}]`),
        )
      : [],
    benchmark: parseBenchmarkContext(value.benchmark),
    artifacts: Array.isArray(value.artifacts)
      ? value.artifacts.map((item, index) =>
          parseReplayArtifact(item, `replay.artifacts[${index}]`),
        )
      : [],
    availability: Object.fromEntries(
      Object.entries(value.availability).map(([key, item]) => [
        key,
        parseEvidenceAvailability(item, `replay.availability.${key}`),
      ]),
    ),
    integrity: Array.isArray(value.integrity)
      ? value.integrity.map((item, index) =>
          parseReplayDiagnostic(item, `replay.integrity[${index}]`),
        )
      : [],
  };
}

/** Strictly parse one bounded Replay History page. */
export function parseReplayPage(value: unknown): ReplayPage {
  if (!isRecord(value)) throw new Error("Replay page must be an object");
  rejectUnknownKeys(value, ["schemaVersion", "items", "nextCursor"], "replayPage");
  if (value.schemaVersion !== 1 || !Array.isArray(value.items)) {
    throw new Error("Replay page contract is invalid");
  }
  return {
    items: value.items.map((item, index) =>
      parseReplayListItem(item, `replayPage.items[${index}]`),
    ),
    nextCursor: typeof value.nextCursor === "string" ? value.nextCursor : null,
  };
}
