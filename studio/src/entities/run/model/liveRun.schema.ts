import {
  cloneJson,
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
  type JsonValue,
} from "@/shared/lib";
import {
  parseAvailabilityState,
  type EvidenceAvailabilityState,
} from "./run.schema";

export type StudioRunLifecycle =
  | "accepted"
  | "starting"
  | "running"
  | "cancelling"
  | "terminal";

export type StudioRunTask = {
  text: string;
  metadata: Record<string, JsonValue>;
};

export type StudioRunResult = {
  status: string;
  kernelStatus: string;
  errorCode: string;
  error: string;
  stepCount: number;
  activationCount: number;
  interactionCount: number;
  usage: JsonValue;
  finalOutput: JsonValue;
  artifactNamespace: string;
};

export type StudioRunResource = {
  schemaVersion: 1;
  runId: string;
  clientRequestId: string;
  agentId: string;
  revisionId: string;
  canonicalHash: string;
  task: StudioRunTask;
  deviceProfileId: string;
  lifecycle: StudioRunLifecycle;
  cancellationRequested: boolean;
  resultAvailability: EvidenceAvailabilityState;
  result: StudioRunResult | null;
  replayAvailability: EvidenceAvailabilityState;
  eventHighWaterMark: number;
  acceptedAt: number;
  startedAt: number | null;
  updatedAt: number;
  terminalAt: number | null;
  storageWarnings: string[];
};

export type CreateStudioRunInput = {
  schemaVersion: 1;
  clientRequestId: string;
  agentId: string;
  revisionId: string;
  task: StudioRunTask;
  deviceProfileId: string;
  runtimeKind: "android";
};

export type CreateStudioRunResponse = StudioRunResource & {
  created: boolean;
};

export type StudioRunEventSource =
  | "service"
  | "runtime"
  | "storage"
  | "result"
  | "replay";

export type StudioRunEvent = {
  schemaVersion: 1;
  eventId: string;
  timestamp: number;
  source: StudioRunEventSource;
  kind: string;
  payload: JsonValue;
  runtimeSequence: number | null;
  nodePath: string;
  activationId: string;
  interactionStep: number | null;
  runId: string;
  sequence: number;
  fingerprint: string;
};

export type StudioRunEventPage = {
  schemaVersion: 1;
  runId: string;
  items: StudioRunEvent[];
  nextCursor: number;
  highWaterMark: number;
  terminal: boolean;
};

export type DebugEvidenceReference = {
  schemaVersion: 1;
  kind: string;
  artifactId: string | null;
  availability: EvidenceAvailabilityState;
  contentType: string;
  size: number;
  originalSize: number | null;
  sha256: string | null;
  provenance: string;
  causalIdentity: string;
  hidden: boolean;
};

export type DebugPayload = {
  schemaVersion: 1;
  debugId: string;
  runId: string;
  nodePath: string;
  activationId: string;
  componentIdentity: string;
  role: string;
  stage: "start" | "complete" | "fail";
  task: JsonValue;
  inputSummary: JsonValue;
  outputSummary: JsonValue;
  durationMs: number | null;
  error: string;
  usage: JsonValue;
  artifactIds: string[];
  evidenceRefs: Record<string, DebugEvidenceReference>;
  availability: Record<string, EvidenceAvailabilityState>;
  diagnostics: string[];
};

const LIFECYCLES = new Set<StudioRunLifecycle>([
  "accepted",
  "starting",
  "running",
  "cancelling",
  "terminal",
]);
const EVENT_SOURCES = new Set<StudioRunEventSource>([
  "service",
  "runtime",
  "storage",
  "result",
  "replay",
]);
const READABLE_AVAILABILITY = new Set<EvidenceAvailabilityState>([
  "available",
  "redacted",
  "truncated",
]);
const ARTIFACT_ID = /^artifact-[a-f0-9]{32}$/;
const HASH = /^sha256:[a-f0-9]{64}$/;

/** Require a non-negative integer at one contract path. */
function requireNonNegativeInteger(value: unknown, path: string): number {
  const parsed = requireNumber(value, path);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`${path} must be a non-negative integer`);
  }
  return parsed;
}

/** Require a positive integer at one contract path. */
function requirePositiveInteger(value: unknown, path: string): number {
  const parsed = requireNonNegativeInteger(value, path);
  if (parsed < 1) throw new Error(`${path} must be a positive integer`);
  return parsed;
}

/** Parse a nullable finite number. */
function nullableNumber(value: unknown, path: string): number | null {
  return value === null || value === undefined ? null : requireNumber(value, path);
}

/** Parse an optional string as an empty-safe field. */
function optionalString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Parse an array of strings without accepting implicit coercion. */
function parseStrings(value: unknown, path: string): string[] {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw new Error(`${path} must be an array`);
  return value.map((item, index) => requireString(item, `${path}[${index}]`));
}

/** Parse one ordinary, non-Benchmark Run task. */
export function parseStudioRunTask(
  value: unknown,
  path = "task",
): StudioRunTask {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["text", "metadata"], path);
  const metadata = cloneJson(value.metadata ?? {}, `${path}.metadata`);
  if (!isRecord(metadata)) throw new Error(`${path}.metadata must be an object`);
  return {
    text: requireString(value.text, `${path}.text`),
    metadata,
  };
}

/** Parse one terminal Run result independently from Benchmark evaluation. */
export function parseStudioRunResult(
  value: unknown,
  path = "result",
): StudioRunResult {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "status",
      "kernelStatus",
      "errorCode",
      "error",
      "stepCount",
      "activationCount",
      "interactionCount",
      "usage",
      "finalOutput",
      "artifactNamespace",
    ],
    path,
  );
  return {
    status: requireString(value.status, `${path}.status`),
    kernelStatus: optionalString(value.kernelStatus),
    errorCode: optionalString(value.errorCode),
    error: optionalString(value.error),
    stepCount: requireNonNegativeInteger(value.stepCount, `${path}.stepCount`),
    activationCount: requireNonNegativeInteger(
      value.activationCount,
      `${path}.activationCount`,
    ),
    interactionCount: requireNonNegativeInteger(
      value.interactionCount,
      `${path}.interactionCount`,
    ),
    usage: cloneJson(value.usage ?? {}, `${path}.usage`),
    finalOutput: cloneJson(value.finalOutput ?? null, `${path}.finalOutput`),
    artifactNamespace: optionalString(value.artifactNamespace),
  };
}

/** Parse a strict public Run resource and enforce lifecycle/result invariants. */
export function parseStudioRunResource(
  value: unknown,
  path = "run",
): StudioRunResource {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "runId",
      "clientRequestId",
      "agentId",
      "revisionId",
      "canonicalHash",
      "task",
      "deviceProfileId",
      "lifecycle",
      "cancellationRequested",
      "resultAvailability",
      "result",
      "replayAvailability",
      "eventHighWaterMark",
      "acceptedAt",
      "startedAt",
      "updatedAt",
      "terminalAt",
      "storageWarnings",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const lifecycle = requireString(value.lifecycle, `${path}.lifecycle`);
  if (!LIFECYCLES.has(lifecycle as StudioRunLifecycle)) {
    throw new Error(`${path}.lifecycle is unsupported`);
  }
  if (typeof value.cancellationRequested !== "boolean") {
    throw new Error(`${path}.cancellationRequested must be a boolean`);
  }
  const terminalAt = nullableNumber(value.terminalAt, `${path}.terminalAt`);
  const hasResult = value.result !== null && value.result !== undefined;
  if (lifecycle === "terminal" && (!hasResult || terminalAt === null)) {
    throw new Error(`${path} terminal lifecycle requires result and terminalAt`);
  }
  if (lifecycle !== "terminal" && (hasResult || terminalAt !== null)) {
    throw new Error(`${path} nonterminal lifecycle cannot contain terminal result`);
  }
  return {
    schemaVersion: 1,
    runId: requireString(value.runId, `${path}.runId`),
    clientRequestId: requireString(value.clientRequestId, `${path}.clientRequestId`),
    agentId: requireString(value.agentId, `${path}.agentId`),
    revisionId: requireString(value.revisionId, `${path}.revisionId`),
    canonicalHash: requireString(value.canonicalHash, `${path}.canonicalHash`),
    task: parseStudioRunTask(value.task, `${path}.task`),
    deviceProfileId: requireString(value.deviceProfileId, `${path}.deviceProfileId`),
    lifecycle: lifecycle as StudioRunLifecycle,
    cancellationRequested: value.cancellationRequested,
    resultAvailability: parseAvailabilityState(
      value.resultAvailability,
      `${path}.resultAvailability`,
    ),
    result: hasResult ? parseStudioRunResult(value.result, `${path}.result`) : null,
    replayAvailability: parseAvailabilityState(
      value.replayAvailability,
      `${path}.replayAvailability`,
    ),
    eventHighWaterMark: requireNonNegativeInteger(
      value.eventHighWaterMark,
      `${path}.eventHighWaterMark`,
    ),
    acceptedAt: requireNonNegativeInteger(value.acceptedAt, `${path}.acceptedAt`),
    startedAt: nullableNumber(value.startedAt, `${path}.startedAt`),
    updatedAt: requireNonNegativeInteger(value.updatedAt, `${path}.updatedAt`),
    terminalAt,
    storageWarnings: parseStrings(value.storageWarnings, `${path}.storageWarnings`),
  };
}

/** Parse an idempotent create response without weakening the Run resource. */
export function parseCreateStudioRunResponse(
  value: unknown,
): CreateStudioRunResponse {
  if (!isRecord(value) || typeof value.created !== "boolean") {
    throw new Error("createRun.created must be a boolean");
  }
  const { created, ...resource } = value;
  return { ...parseStudioRunResource(resource, "createRun"), created };
}

/** Parse one safe typed evidence reference; legacy ordinals are never inferred. */
export function parseDebugEvidenceReference(
  value: unknown,
  path = "evidenceRef",
): DebugEvidenceReference {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "kind",
      "artifactId",
      "availability",
      "contentType",
      "size",
      "originalSize",
      "sha256",
      "provenance",
      "causalIdentity",
      "hidden",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const availability = parseAvailabilityState(value.availability, `${path}.availability`);
  const artifactId = value.artifactId == null
    ? null
    : requireString(value.artifactId, `${path}.artifactId`);
  const hidden = value.hidden === true;
  const contentType = optionalString(value.contentType);
  const sha256 = value.sha256 == null ? null : requireString(value.sha256, `${path}.sha256`);
  if (artifactId !== null && !ARTIFACT_ID.test(artifactId)) {
    throw new Error(`${path}.artifactId must be opaque`);
  }
  if (sha256 !== null && !HASH.test(sha256)) {
    throw new Error(`${path}.sha256 is invalid`);
  }
  if (
    READABLE_AVAILABILITY.has(availability)
    && (hidden || artifactId === null || !contentType || sha256 === null)
  ) {
    throw new Error(`${path} readable evidence metadata is incomplete`);
  }
  if (availability === "hidden" && (!hidden || artifactId !== null)) {
    throw new Error(`${path} hidden evidence cannot be browser-addressable`);
  }
  return {
    schemaVersion: 1,
    kind: requireString(value.kind, `${path}.kind`),
    artifactId,
    availability,
    contentType,
    size: requireNonNegativeInteger(value.size ?? 0, `${path}.size`),
    originalSize:
      value.originalSize == null
        ? null
        : requireNonNegativeInteger(value.originalSize, `${path}.originalSize`),
    sha256,
    provenance: optionalString(value.provenance),
    causalIdentity: optionalString(value.causalIdentity),
    hidden,
  };
}

/** Parse one activation-scoped Debug Payload with explicit legacy degradation. */
export function parseDebugPayload(
  value: unknown,
  path = "debugPayload",
): DebugPayload {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "debugId",
      "runId",
      "nodePath",
      "activationId",
      "componentIdentity",
      "role",
      "stage",
      "task",
      "inputSummary",
      "outputSummary",
      "durationMs",
      "error",
      "usage",
      "artifactIds",
      "evidenceRefs",
      "availability",
      "diagnostics",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const stage = requireString(value.stage, `${path}.stage`);
  if (!["start", "complete", "fail"].includes(stage)) {
    throw new Error(`${path}.stage is unsupported`);
  }
  const evidenceRefs: Record<string, DebugEvidenceReference> = {};
  if (value.evidenceRefs !== undefined) {
    if (!isRecord(value.evidenceRefs)) throw new Error(`${path}.evidenceRefs must be an object`);
    for (const [key, reference] of Object.entries(value.evidenceRefs)) {
      evidenceRefs[key] = parseDebugEvidenceReference(
        reference,
        `${path}.evidenceRefs.${key}`,
      );
    }
  }
  const availability: Record<string, EvidenceAvailabilityState> = {};
  if (value.availability !== undefined) {
    if (!isRecord(value.availability)) throw new Error(`${path}.availability must be an object`);
    for (const [key, state] of Object.entries(value.availability)) {
      availability[key] = parseAvailabilityState(
        state,
        `${path}.availability.${key}`,
      );
    }
  }
  return {
    schemaVersion: 1,
    debugId: requireString(value.debugId, `${path}.debugId`),
    runId: requireString(value.runId, `${path}.runId`),
    nodePath: optionalString(value.nodePath),
    activationId: optionalString(value.activationId),
    componentIdentity: optionalString(value.componentIdentity),
    role: optionalString(value.role),
    stage: stage as DebugPayload["stage"],
    task: cloneJson(value.task ?? null, `${path}.task`),
    inputSummary: cloneJson(value.inputSummary ?? null, `${path}.inputSummary`),
    outputSummary: cloneJson(value.outputSummary ?? null, `${path}.outputSummary`),
    durationMs: nullableNumber(value.durationMs, `${path}.durationMs`),
    error: optionalString(value.error),
    usage: cloneJson(value.usage ?? {}, `${path}.usage`),
    artifactIds: parseStrings(value.artifactIds, `${path}.artifactIds`),
    evidenceRefs,
    availability,
    diagnostics: parseStrings(value.diagnostics, `${path}.diagnostics`),
  };
}

/** Parse one durable journal event from HTTP or SSE transport. */
export function parseStudioRunEvent(
  value: unknown,
  path = "event",
): StudioRunEvent {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "eventId",
      "timestamp",
      "source",
      "kind",
      "payload",
      "runtimeSequence",
      "nodePath",
      "activationId",
      "interactionStep",
      "runId",
      "sequence",
      "fingerprint",
    ],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  const source = requireString(value.source, `${path}.source`);
  if (!EVENT_SOURCES.has(source as StudioRunEventSource)) {
    throw new Error(`${path}.source is unsupported`);
  }
  const fingerprint = requireString(value.fingerprint, `${path}.fingerprint`);
  if (!HASH.test(fingerprint)) throw new Error(`${path}.fingerprint is invalid`);
  return {
    schemaVersion: 1,
    eventId: requireString(value.eventId, `${path}.eventId`),
    timestamp: requireNumber(value.timestamp, `${path}.timestamp`),
    source: source as StudioRunEventSource,
    kind: requireString(value.kind, `${path}.kind`),
    payload: cloneJson(value.payload ?? {}, `${path}.payload`),
    runtimeSequence:
      value.runtimeSequence == null
        ? null
        : requirePositiveInteger(value.runtimeSequence, `${path}.runtimeSequence`),
    nodePath: optionalString(value.nodePath),
    activationId: optionalString(value.activationId),
    interactionStep:
      value.interactionStep == null
        ? null
        : requireNonNegativeInteger(value.interactionStep, `${path}.interactionStep`),
    runId: requireString(value.runId, `${path}.runId`),
    sequence: requirePositiveInteger(value.sequence, `${path}.sequence`),
    fingerprint,
  };
}

/** Parse one bounded event page and require continuous local ordering. */
export function parseStudioRunEventPage(
  value: unknown,
  path = "events",
): StudioRunEventPage {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["schemaVersion", "runId", "items", "nextCursor", "highWaterMark", "terminal"],
    path,
  );
  if (value.schemaVersion !== 1) throw new Error(`${path}.schemaVersion is unsupported`);
  if (!Array.isArray(value.items)) throw new Error(`${path}.items must be an array`);
  if (typeof value.terminal !== "boolean") throw new Error(`${path}.terminal must be a boolean`);
  const runId = requireString(value.runId, `${path}.runId`);
  const items = value.items.map((item, index) =>
    parseStudioRunEvent(item, `${path}.items[${index}]`),
  );
  items.forEach((item, index) => {
    if (item.runId !== runId) throw new Error(`${path}.items[${index}].runId mismatches page`);
    if (index > 0 && item.sequence !== items[index - 1].sequence + 1) {
      throw new Error(`${path}.items are not continuous`);
    }
  });
  const nextCursor = requireNonNegativeInteger(value.nextCursor, `${path}.nextCursor`);
  const highWaterMark = requireNonNegativeInteger(
    value.highWaterMark,
    `${path}.highWaterMark`,
  );
  if (nextCursor > highWaterMark) throw new Error(`${path}.nextCursor exceeds highWaterMark`);
  if (items.length > 0 && items.at(-1)?.sequence !== nextCursor) {
    throw new Error(`${path}.nextCursor does not match the last event`);
  }
  return {
    schemaVersion: 1,
    runId,
    items,
    nextCursor,
    highWaterMark,
    terminal: value.terminal,
  };
}
