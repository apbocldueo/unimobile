import {
  type BenchmarkAgentSnapshot,
  type BenchmarkAvailability,
  type BenchmarkExperimentResource,
  type BenchmarkTaskRun,
} from "@/entities/benchmark-experiment";
import {
  createReplayProjection,
  selectPhoneFrame,
  type PhoneFrameProjection,
  type ReplayProjection,
  type RunSnapshot,
} from "@/entities/run";

export type BenchmarkTaskRunSelection = {
  selectedTaskRunId: string | null;
  locked: boolean;
};

export type BenchmarkTaskRunRailItem = {
  taskRunId: string;
  order: number;
  label: string;
  lifecycle: BenchmarkTaskRun["lifecycle"];
  terminalReason: BenchmarkTaskRun["terminalReason"];
  outcome: string | null;
  outcomeAvailability: BenchmarkAvailability;
  replayAvailability: BenchmarkAvailability;
  isCurrent: boolean;
  isSelected: boolean;
};

export type BenchmarkTaskRunViewModel = {
  experiment: BenchmarkExperimentResource;
  taskRun: BenchmarkTaskRun | null;
  agentSnapshot: BenchmarkAgentSnapshot | null;
  snapshot: RunSnapshot | null;
  projection: ReplayProjection | null;
  phoneFrame: PhoneFrameProjection;
  replayId: string | null;
  liveNodeActivationAvailable: false;
  screenshotAvailability: "not_captured";
  uiXmlAvailability: "not_captured";
};

const EMPTY_PHONE_FRAME: PhoneFrameProjection = {
  state: "not_captured",
  observation: null,
  screenshotArtifactId: null,
  isHistorical: false,
};

/** Sort TaskRuns by immutable planned order with identity as a tie-breaker. */
export function orderBenchmarkTaskRuns(
  taskRuns: BenchmarkTaskRun[],
): BenchmarkTaskRun[] {
  return [...taskRuns].sort(
    (left, right) =>
      left.order - right.order
      || left.taskRunId.localeCompare(right.taskRunId),
  );
}

/** Resolve the factual current item without depending on arrival order.
 *
 * The first non-terminal planned item is current. Once every item is terminal,
 * the final planned item remains current for deterministic refresh recovery.
 */
export function currentBenchmarkTaskRun(
  taskRuns: BenchmarkTaskRun[],
): BenchmarkTaskRun | null {
  const ordered = orderBenchmarkTaskRuns(taskRuns);
  return (
    ordered.find((item) => item.lifecycle !== "terminal")
    ?? ordered.at(-1)
    ?? null
  );
}

/** Reconcile follow/lock selection after an authoritative TaskRun refresh. */
export function reconcileBenchmarkTaskRunSelection(
  taskRuns: BenchmarkTaskRun[],
  selection: BenchmarkTaskRunSelection,
): BenchmarkTaskRunSelection {
  const current = currentBenchmarkTaskRun(taskRuns);
  if (!current) return { selectedTaskRunId: null, locked: false };
  if (
    selection.locked
    && taskRuns.some(
      (item) => item.taskRunId === selection.selectedTaskRunId,
    )
  ) {
    return selection;
  }
  return { selectedTaskRunId: current.taskRunId, locked: false };
}

/** Turn an explicit rail click into historical lock or current follow mode. */
export function selectBenchmarkTaskRun(
  taskRuns: BenchmarkTaskRun[],
  taskRunId: string,
): BenchmarkTaskRunSelection {
  const current = currentBenchmarkTaskRun(taskRuns);
  return {
    selectedTaskRunId: taskRunId,
    locked: current?.taskRunId !== taskRunId,
  };
}

/** Build plural rail summaries without inferring outcome from free-form text. */
export function projectBenchmarkTaskRunRail(
  taskRuns: BenchmarkTaskRun[],
  selection: BenchmarkTaskRunSelection,
): BenchmarkTaskRunRailItem[] {
  const current = currentBenchmarkTaskRun(taskRuns);
  return orderBenchmarkTaskRuns(taskRuns).map((item) => ({
    taskRunId: item.taskRunId,
    order: item.order,
    label: `${item.taskId} · repeat ${item.repeat + 1}`,
    lifecycle: item.lifecycle,
    terminalReason: item.terminalReason,
    outcome: item.benchmarkOutcome,
    outcomeAvailability: item.outcomeAvailability,
    replayAvailability: item.replayAvailability,
    isCurrent: item.taskRunId === current?.taskRunId,
    isSelected: item.taskRunId === selection.selectedTaskRunId,
  }));
}

/** Resolve the immutable Agent snapshot selected by one TaskRun identity. */
function resolveAgentSnapshot(
  experiment: BenchmarkExperimentResource,
  taskRun: BenchmarkTaskRun | null,
): BenchmarkAgentSnapshot | null {
  if (!taskRun) return experiment.definition.agentSnapshots[0] ?? null;
  return (
    experiment.definition.agentSnapshots.find(
      (item) =>
        item.agentId === taskRun.agentId
        && item.revisionId === taskRun.revisionId,
    )
    ?? null
  );
}

/** Build a static Graph and explicit absent-evidence Phone projection.
 *
 * Benchmark lifecycle and phase facts intentionally do not become Agent node
 * activations. Native Replay remains the only surface that consumes committed
 * nested Agent evidence.
 */
export function projectBenchmarkTaskRunView(
  experiment: BenchmarkExperimentResource,
  taskRuns: BenchmarkTaskRun[],
  selection: BenchmarkTaskRunSelection,
): BenchmarkTaskRunViewModel {
  const taskRun =
    taskRuns.find((item) => item.taskRunId === selection.selectedTaskRunId)
    ?? currentBenchmarkTaskRun(taskRuns);
  const agentSnapshot = resolveAgentSnapshot(experiment, taskRun);
  const snapshot = agentSnapshot?.runSnapshot ?? null;
  const projection = snapshot
    ? createReplayProjection(
        snapshot,
        {
          status: taskRun?.agentStatus ?? taskRun?.lifecycle ?? experiment.lifecycle,
          kernelStatus: "",
          error: "",
          stepCount: 0,
          activationCount: 0,
          interactionCount: 0,
          usage: {},
        },
        null,
        [],
        [],
        {
          screenshots: {
            state: "not_captured",
            reasonCode: "benchmark.live_evidence_unavailable",
            detail:
              "The Benchmark event contract does not expose live screenshots.",
          },
          uiXml: {
            state: "not_captured",
            reasonCode: "benchmark.live_evidence_unavailable",
            detail:
              "The Benchmark event contract does not expose live UI XML.",
          },
          nodeActivations: {
            state: "not_captured",
            reasonCode: "benchmark.live_evidence_unavailable",
            detail:
              "Benchmark phase events are not nested Agent node activations.",
          },
        },
        "partial",
      )
    : null;
  const replayId =
    taskRun?.lifecycle === "terminal"
    && taskRun.replayAvailability === "available"
    && taskRun.replayId
    && taskRun.links?.replay
      ? taskRun.replayId
      : null;
  return {
    experiment,
    taskRun,
    agentSnapshot,
    snapshot,
    projection,
    phoneFrame: projection ? selectPhoneFrame(projection) : EMPTY_PHONE_FRAME,
    replayId,
    liveNodeActivationAvailable: false,
    screenshotAvailability: "not_captured",
    uiXmlAvailability: "not_captured",
  };
}
