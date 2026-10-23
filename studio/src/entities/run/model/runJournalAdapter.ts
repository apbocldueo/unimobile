import { isRecord, type JsonValue } from "@/shared/lib";
import type {
  ReplayAction,
  ReplayObservation,
  ReplaySourceKind,
} from "@/entities/replay";
import {
  parseDebugPayload,
  type StudioRunEvent,
} from "./liveRun.schema";
import type { RunMoment } from "./runProjection";

export type RunJournalEvidence = {
  moments: RunMoment[];
  observations: ReplayObservation[];
  actions: ReplayAction[];
};

const ARTIFACT_ID = /^artifact-[a-f0-9]{32}$/;
const DEVICE_OBSERVE_CONTRACT = "zhixing.service.device_observe";
const ACTION_EXECUTOR_CONTRACT = "zhixing.service.action_executor";

/** Find the first exact key within bounded persisted JSON. */
function nestedValue(value: JsonValue, key: string): JsonValue | undefined {
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = nestedValue(item, key);
      if (found !== undefined) return found;
    }
    return undefined;
  }
  if (isRecord(value)) {
    if (key in value) return value[key] as JsonValue;
    for (const item of Object.values(value)) {
      const found = nestedValue(item as JsonValue, key);
      if (found !== undefined) return found;
    }
  }
  return undefined;
}

/** Read one field from the formal Kernel activation output summary. */
function activationOutputValue(
  payload: JsonValue,
  outputName: string,
  key: string,
): JsonValue | undefined {
  if (isRecord(payload)) {
    const runtimePayload = payload.payload;
    for (const candidate of [runtimePayload, payload]) {
      if (!isRecord(candidate)) continue;
      const outputs = candidate.outputs;
      if (!isRecord(outputs)) continue;
      const values = outputs.values;
      if (isRecord(values)) {
        const output = values[outputName];
        if (isRecord(output) && key in output) {
          return output[key] as JsonValue;
        }
      }
      const output = outputs[outputName];
      if (isRecord(output) && key in output) {
        return output[key] as JsonValue;
      }
    }
  }
  return nestedValue(payload, key);
}

/** Return bounded scalar text using the native Replay finalizer semantics. */
function scalarText(value: JsonValue | undefined, fallback = ""): string {
  if (value === undefined || value === null || typeof value === "object") {
    return fallback;
  }
  return String(value).replaceAll("\n", " ").slice(0, 1000);
}

/** Return one non-negative integer using the native finalizer fallback. */
function nonNegativeInteger(
  value: JsonValue | undefined,
  fallback = 0,
): number {
  if (
    typeof value === "boolean"
    || typeof value === "object"
    || value === undefined
  ) {
    return fallback;
  }
  const parsed = typeof value === "number" ? Math.trunc(value) : Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : fallback;
}

/** Collect first-seen opaque artifact identities from safe event JSON. */
function artifactIds(value: JsonValue): string[] {
  const found: string[] = [];
  const visit = (item: JsonValue): void => {
    if (typeof item === "string" && ARTIFACT_ID.test(item)) {
      if (!found.includes(item)) found.push(item);
    } else if (Array.isArray(item)) {
      item.forEach(visit);
    } else if (isRecord(item)) {
      Object.values(item).forEach((nested) => visit(nested as JsonValue));
    }
  };
  visit(value);
  return found;
}

/** Map one journal event to the native Replay source vocabulary. */
function sourceKind(event: StudioRunEvent): ReplaySourceKind {
  const role = scalarText(nestedValue(event.payload, "role")).toLowerCase();
  if (role === DEVICE_OBSERVE_CONTRACT) return "observation";
  if (role === ACTION_EXECUTOR_CONTRACT) return "action";
  if (event.source === "result" || event.kind === "run.terminal") {
    return "run_result";
  }
  return "agent_graph";
}

/** Adapt the verified journal prefix exactly once into shared Run evidence. */
export function adaptRunJournal(
  events: StudioRunEvent[],
): RunJournalEvidence {
  const moments: RunMoment[] = [];
  const observations: ReplayObservation[] = [];
  const actions: ReplayAction[] = [];
  events.forEach((event, causalIndex) => {
    const mappedSource = sourceKind(event);
    const ids = artifactIds(event.payload);
    let observationId: string | null = null;
    let actionId: string | null = null;
    if (mappedSource === "observation" && event.kind === "complete") {
      observationId = `observation-${String(event.sequence).padStart(8, "0")}`;
      observations.push({
        observationId,
        sequence: nonNegativeInteger(
          activationOutputValue(event.payload, "observation", "sequence"),
          observations.length,
        ),
        interactionStep: event.interactionStep ?? 0,
        screenshotArtifactId:
          scalarText(
            activationOutputValue(
              event.payload,
              "observation",
              "screenshot_artifact",
            ),
          ) || null,
        uiArtifactId:
          scalarText(
            activationOutputValue(event.payload, "observation", "ui_artifact"),
          ) || null,
        width: nonNegativeInteger(
          activationOutputValue(event.payload, "observation", "width"),
        ),
        height: nonNegativeInteger(
          activationOutputValue(event.payload, "observation", "height"),
        ),
        platform: scalarText(
          activationOutputValue(event.payload, "observation", "platform"),
        ),
        deviceId: scalarText(
          activationOutputValue(event.payload, "observation", "device_id"),
        ),
        overlay: [],
      });
    } else if (mappedSource === "action" && event.kind === "complete") {
      actionId = `action-${String(event.sequence).padStart(8, "0")}`;
      actions.push({
        actionId,
        sequence: actions.length,
        interactionStep: event.interactionStep ?? 0,
        status: scalarText(
          activationOutputValue(event.payload, "result", "status"),
          "unknown",
        ),
        actionType: scalarText(
          activationOutputValue(event.payload, "result", "action_type"),
          "unknown",
        ),
        effectPerformed:
          activationOutputValue(event.payload, "result", "effect_performed") === true,
        effectKind: scalarText(
          activationOutputValue(event.payload, "result", "effect_kind"),
        ),
        terminalStatus:
          scalarText(
            activationOutputValue(event.payload, "result", "terminal_status"),
          ) || null,
        message: scalarText(
          activationOutputValue(event.payload, "result", "message"),
        ),
        error: scalarText(
          activationOutputValue(event.payload, "result", "error"),
        ),
        artifactId: ids[0] ?? null,
      });
    }
    let debugPayload = null;
    if (event.kind.startsWith("component.debug.")) {
      debugPayload = parseDebugPayload(event.payload, `event.${event.sequence}.payload`);
    }
    moments.push({
      momentId: `moment-${String(event.sequence).padStart(8, "0")}`,
      causalIndex,
      sourceKind: mappedSource,
      sourceSequence: event.sequence,
      timestamp: event.timestamp,
      phase: scalarText(nestedValue(event.payload, "phase")),
      kind: event.kind,
      role: scalarText(nestedValue(event.payload, "role")),
      component: scalarText(nestedValue(event.payload, "component")),
      nodeId: scalarText(nestedValue(event.payload, "node_id")),
      nodePath: event.nodePath,
      activationId: event.activationId,
      parentActivationId: scalarText(
        nestedValue(event.payload, "parent_activation_id"),
      ),
      loopPath: scalarText(nestedValue(event.payload, "loop_path")),
      loopIteration:
        nestedValue(event.payload, "loop_iteration") === undefined
          ? null
          : nonNegativeInteger(nestedValue(event.payload, "loop_iteration")),
      interactionStep: event.interactionStep ?? 0,
      durationMs:
        typeof nestedValue(event.payload, "duration_ms") === "number"
          ? (nestedValue(event.payload, "duration_ms") as number)
          : null,
      payload: event.payload,
      observationId,
      actionId,
      artifactIds: ids,
      ...(debugPayload === null ? {} : { debugPayload }),
    });
  });
  return { moments, observations, actions };
}
