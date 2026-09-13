import { useMemo } from "react";
import type { ReplayEnvelope } from "@/entities/replay";
import {
  loadReplayArtifactText,
  replayArtifactUrl,
} from "@/entities/artifact";
import {
  projectReplay,
  ReplayGraph,
  ReplayTimeline,
  selectReplayOverview,
  selectPhoneFrame,
  useReplayPlaybackStore,
} from "@/features/trajectory-replay";
import { RunInspector } from "@/features/run-inspector";
import { selectDevicePaneState, VirtualPhone } from "@/features/virtual-phone";
import { ThreePaneWorkbenchLayout } from "./ThreePaneWorkbenchLayout";
import {
  ReadOnlyRunReason,
  RunWorkspaceDock,
  WorkbenchAgentTitle,
} from "./WorkbenchChrome";

type ThreePaneReplayWorkbenchProps = {
  envelope: ReplayEnvelope;
  agentName?: string;
  taskControl?: React.ReactNode;
};

/** Compose Graph, Virtual Phone, Inspector, and two-lane playback. */
export function ThreePaneReplayWorkbench({
  envelope,
  agentName = envelope.snapshot.agentId || "Agent 名称不可用",
  taskControl = <ReadOnlyRunReason reason="该 Replay 未验证为可运行的本地普通 revision。" />,
}: ThreePaneReplayWorkbenchProps) {
  const cursor = useReplayPlaybackStore((state) => state.cursor);
  const selectedActivationId = useReplayPlaybackStore(
    (state) => state.lockedActivationId,
  );
  const lockActivation = useReplayPlaybackStore((state) => state.lockActivation);
  const seek = useReplayPlaybackStore((state) => state.seek);
  const projection = useMemo(
    () => projectReplay(envelope, cursor),
    [cursor, envelope],
  );
  const completedProjection = useMemo(
    () => projectReplay(envelope),
    [envelope],
  );
  const frame = selectPhoneFrame(projection);
  const artifactsById = useMemo(
    () => Object.fromEntries(envelope.artifacts.map((item) => [item.artifactId, item])),
    [envelope.artifacts],
  );
  const latestAction = projection.latestActionId
    ? projection.actionsById[projection.latestActionId] ?? null
    : null;
  const overview = useMemo(
    () => selectReplayOverview(envelope, completedProjection),
    [completedProjection, envelope],
  );
  const failureActivationId = projection.failureTargets.at(-1)?.activationId ?? null;
  const compactPhone = frame.state !== "available" && frame.state !== "stale";
  const deviceState = selectDevicePaneState({
    hasRun: true,
    lifecycle: "terminal",
    frameState: frame.state,
    hasObservation: frame.observation !== null,
  });

  /** Move the factual cursor to the formal failure target without diagnosing it. */
  const jumpToFailure = () => {
    const target = overview.failureTarget;
    if (!target) return;
    seek(target.cursor);
    lockActivation(target.activationId);
  };

  return (
    <ThreePaneWorkbenchLayout
      defaultPanes={{ left: 50, middle: 30, right: 20 }}
      compactMiddle={compactPhone}
      header={<WorkbenchAgentTitle name={agentName} />}
      left={
        <ReplayGraph
          snapshot={envelope.snapshot}
          projection={projection}
          displayActivationId={projection.currentActivationId}
          selectedActivationId={selectedActivationId}
          failureActivationId={failureActivationId}
          onSelectActivation={lockActivation}
        />
      }
      middle={
        <VirtualPhone
          frame={frame}
          deviceState={deviceState}
          latestAction={latestAction}
          compact={compactPhone}
          resolveArtifact={(artifactId) => {
            const artifact = artifactsById[artifactId];
            return artifact
              ? {
                  url: replayArtifactUrl(envelope.runId, artifactId),
                  availability: artifact.availability,
                }
              : null;
          }}
        />
      }
      right={
        <RunInspector
          viewModel={{
            runId: envelope.runId,
            snapshot: envelope.snapshot,
            projection,
            provenance: envelope.provenance,
            agentStatus: envelope.result.status,
            kernelStatus: envelope.result.kernelStatus,
            benchmarkOutcome: envelope.benchmark?.outcome ?? null,
            resultError: envelope.result.error,
            availability: envelope.availability,
            artifactUrl: (artifactId) =>
              replayArtifactUrl(envelope.runId, artifactId),
            loadArtifactText: (artifactId) =>
              loadReplayArtifactText(envelope.runId, artifactId),
            readOnlyLabel: "只读 Replay",
            terminalVisible: cursor >= envelope.moments.length - 1,
            overview,
            evidenceOrigin: envelope.evidenceOrigin,
          }}
          selectedActivationId={selectedActivationId}
          onSelectActivation={lockActivation}
          onJumpToFailure={jumpToFailure}
          onJumpToMoment={(momentCursor, activationId) => {
            seek(momentCursor);
            lockActivation(activationId);
          }}
        />
      }
      footer={(
        <RunWorkspaceDock
          upper={<ReplayTimeline envelope={envelope} projection={projection} />}
          lower={taskControl}
        />
      )}
    />
  );
}
