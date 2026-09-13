import { useEffect, useMemo, useRef } from "react";
import { loadRunArtifactText, runArtifactUrl } from "@/entities/artifact";
import {
  selectPhoneFrame,
  type RunSnapshot,
  type StudioRunResource,
} from "@/entities/run";
import {
  useLiveRunSession,
  useLiveRunUiStore,
} from "@/features/live-run-session";
import { RunInspector } from "@/features/run-inspector";
import { RunGraph } from "@/features/trajectory-replay";
import { selectDevicePaneState, VirtualPhone } from "@/features/virtual-phone";
import { ActiveRunBar } from "@/features/agent-task-run";
import { ThreePaneWorkbenchLayout } from "./ThreePaneWorkbenchLayout";
import { RunWorkspaceDock, WorkbenchAgentTitle } from "./WorkbenchChrome";
import styles from "./threePaneReplayWorkbench.module.css";

type ThreePaneLiveRunWorkbenchProps = {
  agentName?: string;
  run: StudioRunResource;
  snapshot: RunSnapshot;
  graphError?: string | null;
  onTerminal?: (event: import("@/entities/run").StudioRunEvent) => void;
  onOpenReplay?: (event: import("@/entities/run").StudioRunEvent) => void;
};

/** Compose the durable Live Run session into the shared three-pane workbench. */
export function ThreePaneLiveRunWorkbench({
  agentName,
  run,
  snapshot,
  graphError = null,
  onTerminal,
  onOpenReplay,
}: ThreePaneLiveRunWorkbenchProps) {
  const { session, projection } = useLiveRunSession({ run, snapshot });
  const selectedActivationId = useLiveRunUiStore(
    (state) => state.selectedActivationId,
  );
  const visualActivationId = useLiveRunUiStore(
    (state) => state.visualActivationId,
  );
  const failureActivationId = useLiveRunUiStore(
    (state) => state.failureActivationId,
  );
  const lockActivation = useLiveRunUiStore((state) => state.lockActivation);
  const returnToCurrent = useLiveRunUiStore((state) => state.returnToCurrent);
  const terminalNotified = useRef(false);
  const terminalEvent = session.events.find(
    (event) => event.kind === "run.terminal",
  ) ?? null;
  const frame = selectPhoneFrame(projection);
  const latestAction = projection.latestActionId
    ? projection.actionsById[projection.latestActionId] ?? null
    : null;
  const deviceState = selectDevicePaneState({
    hasRun: true,
    lifecycle: run.lifecycle,
    errorCode: run.result?.errorCode ?? "",
    frameState: frame.state,
    hasObservation: frame.observation !== null,
  });
  const availability = useMemo(
    () => ({
      modelResponse: { state: "not_captured" },
      debugPayload: { state: "not_captured" },
      prompt: { state: "not_captured" },
    }),
    [],
  );

  useEffect(() => {
    if (
      session.connection === "terminal"
      && terminalEvent
      && !terminalNotified.current
    ) {
      terminalNotified.current = true;
      onTerminal?.(terminalEvent);
    }
  }, [onTerminal, session.connection, terminalEvent]);

  const banner = session.connection === "integrity-error" ? (
    <div className={styles.integrityBanner} data-state="corrupt">
      Journal 完整性错误：{session.integrityError}。已冻结最后验证前缀。
    </div>
  ) : graphError ? (
    <div className={styles.integrityBanner}>
      Graph 不可验证：{graphError}。Phone、Inspector 与 journal 仍可检查。
    </div>
  ) : session.connection === "reconnecting" || session.connection === "stale" ? (
    <div className={styles.integrityBanner}>
      连接状态为 {session.connection}；正在从 cursor {session.cursor} 恢复。
    </div>
  ) : session.connection === "terminal" ? (
    <div className={styles.integrityBanner}>
      {run.replayAvailability === "available"
        ? "运行已结束，最后过程已保留。完整回放已经准备好。"
        : `运行已结束，最后过程已保留。Replay 当前为 ${run.replayAvailability}。`}
      {run.replayAvailability === "available" && terminalEvent && onOpenReplay ? (
        <button type="button" onClick={() => onOpenReplay(terminalEvent)}>
          打开完整回放
        </button>
      ) : (
        <button
          type="button"
          onClick={() => {
            if (terminalEvent) onTerminal?.(terminalEvent);
          }}
        >
          重新检查 Replay
        </button>
      )}
    </div>
  ) : failureActivationId ? (
    <div className={styles.integrityBanner} data-state="corrupt">
      新的 activation failure 已到达。
      <button
        type="button"
        onClick={() => {
          lockActivation(failureActivationId);
          returnToCurrent();
          lockActivation(failureActivationId);
        }}
      >
        定位失败
      </button>
    </div>
  ) : null;

  return (
    <ThreePaneWorkbenchLayout
      header={<WorkbenchAgentTitle name={agentName ?? snapshot.agentId ?? run.agentId} />}
      banner={banner}
      left={
        <RunGraph
          ariaLabel="Live AgentGraph"
          snapshot={snapshot}
          projection={projection}
          displayActivationId={visualActivationId}
          selectedActivationId={selectedActivationId}
          failureActivationId={failureActivationId}
          onSelectActivation={lockActivation}
        />
      }
      middle={
        <VirtualPhone
          modeLabel="LIVE · READ ONLY"
          deviceState={deviceState}
          frame={frame}
          latestAction={latestAction}
          resolveArtifact={(artifactId) => ({
            url: runArtifactUrl(run.runId, artifactId),
            availability: "available",
          })}
        />
      }
      right={
        <RunInspector
          viewModel={{
            runId: run.runId,
            snapshot,
            projection,
            provenance: "native_studio_run",
            agentStatus: run.result?.status ?? run.lifecycle,
            kernelStatus: run.result?.kernelStatus ?? "",
            benchmarkOutcome: null,
            resultError: run.result?.error ?? "",
            availability,
            artifactUrl: (artifactId) => runArtifactUrl(run.runId, artifactId),
            loadArtifactText: (artifactId) =>
              loadRunArtifactText(run.runId, artifactId),
            readOnlyLabel: `只读 Live · ${session.connection}`,
            terminalVisible: session.connection === "terminal" || run.lifecycle === "terminal",
          }}
          selectedActivationId={selectedActivationId}
          onSelectActivation={lockActivation}
        />
      }
      footer={<RunWorkspaceDock lower={<ActiveRunBar run={run} />} />}
    />
  );
}
