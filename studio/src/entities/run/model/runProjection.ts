import type {
  EvidenceAvailability,
  ReplayGraphNode,
  ReplayIntegrityState,
  RunResultSummary,
  RunSnapshot,
} from "./run.schema";
import type {
  BenchmarkContext,
} from "@/entities/benchmark";
import type {
  ReplayAction,
  ReplayDiagnostic,
  ReplayEnvelope,
  ReplayMoment,
  ReplayObservation,
} from "@/entities/replay";
import type { JsonValue } from "@/shared/lib";
import {
  parseDebugPayload,
  type DebugPayload,
} from "./liveRun.schema";

export type ActivationStatus = "running" | "success" | "failure" | "skipped";

export type ActivationProjection = {
  activationId: string;
  nodeId: string;
  nodePath: string;
  role: string;
  component: string;
  parentActivationId: string;
  loopPath: string;
  loopIteration: number | null;
  interactionStep: number;
  status: ActivationStatus;
  startCursor: number;
  endCursor: number | null;
  durationMs: number | null;
  payloadHistory: JsonValue[];
};

export type NodeProjection = {
  nodeId: string;
  status: ActivationStatus | "not_observed";
  activationIds: string[];
  executionCount: number;
  feedbackCount: number;
  badges: string[];
};

export type FailureTarget = {
  kind: "activation" | "agent_terminal" | "benchmark_evaluation" | "benchmark_infrastructure";
  cursor: number;
  activationId: string | null;
  nodePath: string | null;
  label: string;
};

export type ReplayProjection = {
  cursor: number;
  accepting: boolean;
  integrityState: ReplayIntegrityState;
  diagnostics: ReplayDiagnostic[];
  processedMoments: Record<string, string>;
  lastSequenceBySource: Record<string, number>;
  lastCausalBySource: Record<string, number>;
  activationsById: Record<string, ActivationProjection>;
  activationOrder: string[];
  nodesById: Record<string, NodeProjection>;
  currentActivationId: string | null;
  currentInteractionStep: number;
  visibleObservationIds: string[];
  currentObservationId: string | null;
  visibleActionIds: string[];
  latestActionId: string | null;
  benchmarkPhases: Record<string, string>;
  benchmarkOutcome: BenchmarkContext["outcome"] | null;
  agentStatus: string;
  failureTargets: FailureTarget[];
  observationsById: Record<string, ReplayObservation>;
  actionsById: Record<string, ReplayAction>;
  debugByActivationId: Record<string, DebugPayload[]>;
  availability: Record<string, EvidenceAvailability>;
};

export type PhoneFrameProjection = {
  state:
    | "available"
    | "stale"
    | "pending"
    | "missing"
    | "not_captured"
    | "corrupt";
  observation: ReplayObservation | null;
  screenshotArtifactId: string | null;
  isHistorical: boolean;
};

export type RunMoment = ReplayMoment & {
  debugPayload?: DebugPayload | null;
};
export type RunObservation = ReplayObservation;
export type RunAction = ReplayAction;
export type RunDiagnostic = ReplayDiagnostic;
export type RunEvidenceProjection = ReplayProjection;

/** Serialize JSON deterministically for idempotence checks. */
function stableJson(value: JsonValue): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableJson(value[key]!)}`)
    .join(",")}}`;
}

/** Build a stable fingerprint for one normalized moment. */
function momentFingerprint(moment: ReplayMoment): string {
  return stableJson(moment as unknown as JsonValue);
}

/** Create an explicit integrity diagnostic without inferring root cause. */
function diagnostic(
  code: string,
  message: string,
  severity: "warning" | "error",
  moment: ReplayMoment,
): ReplayDiagnostic {
  return {
    code,
    message,
    severity,
    source: moment.sourceKind,
    causalIndex: moment.causalIndex,
  };
}

/** Derive one terminal activation state from a formal event kind. */
function terminalStatus(kind: string): ActivationStatus | null {
  if (["fail", "failure", "error"].includes(kind)) return "failure";
  if (kind === "complete") return "success";
  if (kind === "skipped") return "skipped";
  return null;
}

/** Create the pure projection baseline without timers, network, or React state. */
export function createReplayProjection(
  snapshot: RunSnapshot,
  result: RunResultSummary,
  benchmark: BenchmarkContext | null,
  observations: ReplayObservation[],
  actions: ReplayAction[],
  availability: Record<string, EvidenceAvailability>,
  integrityState: ReplayIntegrityState,
  initialDiagnostics: ReplayDiagnostic[] = [],
): ReplayProjection {
  const nodesById = Object.fromEntries(
    snapshot.graphNodes.map((node: ReplayGraphNode) => [
      node.id,
      {
        nodeId: node.id,
        status: "not_observed" as const,
        activationIds: [],
        executionCount: 0,
        feedbackCount: 0,
        badges: [],
      },
    ]),
  );
  return {
    cursor: -1,
    accepting: true,
    integrityState,
    diagnostics: [...initialDiagnostics],
    processedMoments: {},
    lastSequenceBySource: {},
    lastCausalBySource: {},
    activationsById: {},
    activationOrder: [],
    nodesById,
    currentActivationId: null,
    currentInteractionStep: 0,
    visibleObservationIds: [],
    currentObservationId: null,
    visibleActionIds: [],
    latestActionId: null,
    benchmarkPhases: {},
    benchmarkOutcome: benchmark?.outcome ?? null,
    agentStatus: result.status,
    failureTargets: [],
    observationsById: Object.fromEntries(
      observations.map((item) => [item.observationId, item]),
    ),
    actionsById: Object.fromEntries(actions.map((item) => [item.actionId, item])),
    debugByActivationId: {},
    availability,
  };
}

/** Apply one normalized moment as an immutable transport-independent reduction. */
export function reduceReplayMoment(
  previous: ReplayProjection,
  moment: RunMoment,
): ReplayProjection {
  if (!previous.accepting) return previous;
  const fingerprint = momentFingerprint(moment);
  const existing = previous.processedMoments[moment.momentId];
  if (existing === fingerprint) return previous;
  if (existing !== undefined) {
    return {
      ...previous,
      accepting: false,
      integrityState: "corrupt",
      diagnostics: [
        ...previous.diagnostics,
        diagnostic(
          "studio.replay.moment_identity_conflict",
          "Moment identity was reused with different content",
          "error",
          moment,
        ),
      ],
    };
  }
  if (moment.causalIndex <= previous.cursor) {
    return {
      ...previous,
      accepting: false,
      integrityState: "corrupt",
      diagnostics: [
        ...previous.diagnostics,
        diagnostic(
          "studio.replay.causal_order_invalid",
          "Moment causal index moved backwards",
          "error",
          moment,
        ),
      ],
    };
  }
  const lastSequence = moment.sourceSequence === null
    ? undefined
    : previous.lastSequenceBySource[moment.sourceKind];
  const lastCausal = previous.lastCausalBySource[moment.sourceKind];
  if (
    lastSequence !== undefined
    && lastCausal !== undefined
    && moment.sourceSequence !== null
    && moment.sourceSequence - lastSequence > moment.causalIndex - lastCausal
  ) {
    return {
      ...previous,
      accepting: false,
      integrityState: previous.integrityState === "corrupt" ? "corrupt" : "partial",
      diagnostics: [
        ...previous.diagnostics,
        diagnostic(
          "studio.replay.sequence_gap",
          "Source-local sequence has an unverified gap",
          "warning",
          moment,
        ),
      ],
    };
  }
  if (
    lastSequence !== undefined
    && moment.sourceSequence !== null
    && moment.sourceSequence <= lastSequence
  ) {
    return {
      ...previous,
      accepting: false,
      integrityState: "corrupt",
      diagnostics: [
        ...previous.diagnostics,
        diagnostic(
          "studio.replay.sequence_order",
          "Source-local sequence repeated or moved backwards",
          "error",
          moment,
        ),
      ],
    };
  }

  const next: ReplayProjection = {
    ...previous,
    cursor: moment.causalIndex,
    processedMoments: {
      ...previous.processedMoments,
      [moment.momentId]: fingerprint,
    },
    lastSequenceBySource:
      moment.sourceSequence === null
        ? previous.lastSequenceBySource
        : {
            ...previous.lastSequenceBySource,
            [moment.sourceKind]: moment.sourceSequence,
          },
    lastCausalBySource:
      moment.sourceSequence === null
        ? previous.lastCausalBySource
        : {
            ...previous.lastCausalBySource,
            [moment.sourceKind]: moment.causalIndex,
          },
    currentInteractionStep: moment.interactionStep,
    activationsById: { ...previous.activationsById },
    activationOrder: [...previous.activationOrder],
    nodesById: { ...previous.nodesById },
    debugByActivationId: { ...previous.debugByActivationId },
    visibleObservationIds: [...previous.visibleObservationIds],
    visibleActionIds: [...previous.visibleActionIds],
    benchmarkPhases: { ...previous.benchmarkPhases },
    failureTargets: [...previous.failureTargets],
    diagnostics: [...previous.diagnostics],
  };

  if (moment.sourceKind === "benchmark_lifecycle" && moment.phase) {
    next.benchmarkPhases[moment.phase] = moment.kind;
    if (
      ["fail", "failure", "error"].includes(moment.kind)
      && moment.phase !== "evaluation"
    ) {
      next.failureTargets.push({
        kind: "benchmark_infrastructure",
        cursor: moment.causalIndex,
        activationId: null,
        nodePath: null,
        label: `Benchmark ${moment.phase} ${moment.kind}`,
      });
    }
  }

  if (moment.activationId) {
    const current = next.activationsById[moment.activationId];
    if (moment.kind === "start") {
      if (current) {
        next.accepting = false;
        next.integrityState = "corrupt";
        next.diagnostics.push(
          diagnostic(
            "studio.replay.activation_duplicate_start",
            "Activation received more than one start event",
            "error",
            moment,
          ),
        );
        return next;
      }
      const activation: ActivationProjection = {
        activationId: moment.activationId,
        nodeId: moment.nodeId,
        nodePath: moment.nodePath,
        role: moment.role,
        component: moment.component,
        parentActivationId: moment.parentActivationId,
        loopPath: moment.loopPath,
        loopIteration: moment.loopIteration,
        interactionStep: moment.interactionStep,
        status: "running",
        startCursor: moment.causalIndex,
        endCursor: null,
        durationMs: null,
        payloadHistory: [moment.payload],
      };
      next.activationsById[moment.activationId] = activation;
      next.activationOrder.push(moment.activationId);
      next.currentActivationId = moment.activationId;
      const aggregate = next.nodesById[moment.nodeId] ?? {
        nodeId: moment.nodeId,
        status: "not_observed",
        activationIds: [],
        executionCount: 0,
        feedbackCount: 0,
        badges: [],
      };
      next.nodesById[moment.nodeId] = {
        ...aggregate,
        status: "running",
        activationIds: [...aggregate.activationIds, moment.activationId],
        executionCount: aggregate.executionCount + 1,
      };
    } else {
      const terminal = terminalStatus(moment.kind);
      if (terminal !== null) {
        if (!current) {
          next.accepting = false;
          next.integrityState = "corrupt";
          next.diagnostics.push(
            diagnostic(
              "studio.replay.activation_start_missing",
              "Activation terminal event has no observed start",
              "error",
              moment,
            ),
          );
          return next;
        }
        const activation = {
          ...current,
          status: terminal,
          endCursor: moment.causalIndex,
          durationMs: moment.durationMs,
          payloadHistory: [...current.payloadHistory, moment.payload],
        };
        next.activationsById[moment.activationId] = activation;
        next.currentActivationId = moment.activationId;
        const aggregate = next.nodesById[current.nodeId]!;
        next.nodesById[current.nodeId] = { ...aggregate, status: terminal };
        if (terminal === "failure") {
          next.failureTargets.push({
            kind: "activation",
            cursor: moment.causalIndex,
            activationId: moment.activationId,
            nodePath: moment.nodePath,
            label: `${moment.nodePath || moment.nodeId} failed`,
          });
        }
      }
    }
  }

  if (moment.kind === "feedback_latched" && moment.nodeId) {
    const aggregate = next.nodesById[moment.nodeId] ?? {
      nodeId: moment.nodeId,
      status: "not_observed",
      activationIds: [],
      executionCount: 0,
      feedbackCount: 0,
      badges: [],
    };
    next.nodesById[moment.nodeId] = {
      ...aggregate,
      feedbackCount: aggregate.feedbackCount + 1,
      badges: Array.from(new Set([...aggregate.badges, "feedback"])),
    };
  }
  if (
    ["router_selected", "condition_evaluated", "loop_exhausted"].includes(moment.kind)
    && moment.nodeId
  ) {
    const aggregate = next.nodesById[moment.nodeId] ?? {
      nodeId: moment.nodeId,
      status: "not_observed",
      activationIds: [],
      executionCount: 0,
      feedbackCount: 0,
      badges: [],
    };
    next.nodesById[moment.nodeId] = {
      ...aggregate,
      badges: Array.from(new Set([...aggregate.badges, moment.kind])),
    };
  }

  if (
    moment.observationId
    && next.observationsById[moment.observationId]
    && !next.visibleObservationIds.includes(moment.observationId)
  ) {
    next.visibleObservationIds.push(moment.observationId);
    next.currentObservationId = moment.observationId;
  }
  if (
    moment.actionId
    && next.actionsById[moment.actionId]
    && !next.visibleActionIds.includes(moment.actionId)
  ) {
    next.visibleActionIds.push(moment.actionId);
    next.latestActionId = moment.actionId;
  }
  let debugPayload = moment.debugPayload ?? null;
  if (debugPayload === null && moment.kind.startsWith("component.debug.")) {
    try {
      debugPayload = parseDebugPayload(moment.payload);
    } catch {
      debugPayload = null;
    }
  }
  if (debugPayload && moment.activationId) {
    next.debugByActivationId[moment.activationId] = [
      ...(next.debugByActivationId[moment.activationId] ?? []),
      debugPayload,
    ];
  }
  return next;
}

/** Project one envelope from zero through the requested causal cursor. */
export function projectReplay(
  envelope: ReplayEnvelope,
  cursor = envelope.moments.length - 1,
): ReplayProjection {
  let projection = createReplayProjection(
    envelope.snapshot,
    envelope.result,
    envelope.benchmark,
    envelope.observations,
    envelope.actions,
    envelope.availability,
    envelope.integrityState,
    envelope.integrity,
  );
  for (const moment of envelope.moments) {
    if (moment.causalIndex > cursor || !projection.accepting) break;
    projection = reduceReplayMoment(projection, moment);
  }
  if (cursor >= envelope.moments.length - 1) {
    projection = finalizeRunEvidenceProjection(
      projection,
      envelope.result,
      envelope.benchmark,
    );
  }
  return projection;
}

/** Apply authoritative terminal outcome facts without changing event history. */
export function finalizeRunEvidenceProjection(
  previous: ReplayProjection,
  result: RunResultSummary,
  benchmark: BenchmarkContext | null,
): ReplayProjection {
  let projection = { ...previous, agentStatus: result.status };
  if (
    result.status !== "success"
    && !projection.failureTargets.some(
      (item) => item.kind === "activation" || item.kind === "agent_terminal",
    )
  ) {
    projection = {
      ...projection,
      failureTargets: [
        ...projection.failureTargets,
        {
          kind: "agent_terminal",
          cursor: Math.max(projection.cursor, 0),
          activationId: null,
          nodePath: null,
          label: result.error || `Agent ${result.status}`,
        },
      ],
    };
  }
  if (
    benchmark?.outcome === "fail"
    && !projection.failureTargets.some(
      (item) => item.kind === "benchmark_evaluation",
    )
  ) {
    projection = {
      ...projection,
      failureTargets: [
        ...projection.failureTargets,
        {
          kind: "benchmark_evaluation",
          cursor: Math.max(projection.cursor, 0),
          activationId: null,
          nodePath: null,
          label: "Benchmark evaluation failed",
        },
      ],
    };
  }
  return projection;
}

/** Select the latest causally visible phone frame without inventing evidence. */
export function selectPhoneFrame(
  projection: ReplayProjection,
): PhoneFrameProjection {
  const observation = projection.currentObservationId
    ? projection.observationsById[projection.currentObservationId] ?? null
    : null;
  if (observation === null) {
    const state = projection.availability.screenshots?.state;
    return {
      state:
        state === "available"
          ? "pending"
          : state === "corrupt"
            ? "corrupt"
            : state === "missing"
              ? "missing"
              : "not_captured",
      observation: null,
      screenshotArtifactId: null,
      isHistorical: false,
    };
  }
  const isHistorical = observation.interactionStep < projection.currentInteractionStep;
  if (observation.screenshotArtifactId === null) {
    return {
      state: "missing",
      observation,
      screenshotArtifactId: null,
      isHistorical,
    };
  }
  return {
    state: isHistorical ? "stale" : "available",
    observation,
    screenshotArtifactId: observation.screenshotArtifactId,
    isHistorical,
  };
}

/** Return stable failure targets in the required evidence priority order. */
export function selectFailureTargets(
  projection: ReplayProjection,
): FailureTarget[] {
  const priority: Record<FailureTarget["kind"], number> = {
    activation: 0,
    agent_terminal: 1,
    benchmark_evaluation: 2,
    benchmark_infrastructure: 3,
  };
  return [...projection.failureTargets].sort(
    (left, right) =>
      priority[left.kind] - priority[right.kind] || left.cursor - right.cursor,
  );
}

/** Return semantic execution milestones while leaving exact journal events available separately. */
export function replayMilestoneCursors(moments: ReplayMoment[]): number[] {
  return moments
    .filter(
      (moment) =>
        moment.kind === "start"
        || terminalStatus(moment.kind) !== null
        || ["feedback_latched", "router_selected", "loop_exhausted"].includes(moment.kind)
        || moment.sourceKind === "observation"
        || moment.sourceKind === "action"
        || moment.sourceKind === "benchmark_lifecycle",
    )
    .map((moment) => moment.causalIndex);
}
