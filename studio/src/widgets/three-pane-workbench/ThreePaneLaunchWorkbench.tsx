import { useMemo } from "react";
import {
  createReplayProjection,
  type CreateStudioRunResponse,
  type RunSnapshot,
} from "@/entities/run";
import { TaskRunBar, type AgentRunTarget } from "@/features/agent-task-run";
import { RunGraph } from "@/features/trajectory-replay";
import { selectDevicePaneState, VirtualPhone } from "@/features/virtual-phone";
import { ThreePaneWorkbenchLayout } from "./ThreePaneWorkbenchLayout";
import { RunWorkspaceDock, WorkbenchAgentTitle } from "./WorkbenchChrome";
import styles from "./launchWorkbench.module.css";

type ThreePaneLaunchWorkbenchProps = {
  agentName: string;
  snapshot: RunSnapshot;
  target: AgentRunTarget;
  onCreated: (run: CreateStudioRunResponse) => void;
};

/** Compose an exact revision into a not-started three-pane ordinary Run workspace. */
export function ThreePaneLaunchWorkbench({
  agentName,
  snapshot,
  target,
  onCreated,
}: ThreePaneLaunchWorkbenchProps) {
  const projection = useMemo(
    () => createReplayProjection(
      snapshot,
      {
        status: "not_started",
        kernelStatus: "not_started",
        error: "",
        stepCount: 0,
        activationCount: 0,
        interactionCount: 0,
        usage: {},
      },
      null,
      [],
      [],
      {},
      "complete",
    ),
    [snapshot],
  );
  return (
    <ThreePaneWorkbenchLayout
      header={<WorkbenchAgentTitle name={agentName} />}
      defaultPanes={{ left: 50, middle: 22, right: 28 }}
      left={(
        <RunGraph
          ariaLabel="Launch AgentGraph"
          snapshot={snapshot}
          projection={projection}
          selectedActivationId={null}
          onSelectActivation={() => undefined}
        />
      )}
      middle={(
        <VirtualPhone
          modeLabel="NOT STARTED"
          deviceState={selectDevicePaneState({
            hasRun: false,
            readinessReady: true,
            frameState: "pending",
            hasObservation: false,
          })}
          compact
          frame={{
            state: "pending",
            observation: null,
            screenshotArtifactId: null,
            isHistorical: false,
          }}
          latestAction={null}
          resolveArtifact={() => null}
          unavailableDetail="提交底部 Task 后才会启动设备并采集正式证据。"
        />
      )}
      right={<LaunchOverview snapshot={snapshot} />}
      footer={(
        <RunWorkspaceDock
          lower={<TaskRunBar target={target} onCreated={onCreated} autoFocus />}
        />
      )}
    />
  );
}

/** Render revision readiness without inventing a Run or execution evidence. */
function LaunchOverview({ snapshot }: { snapshot: RunSnapshot }) {
  return (
    <aside className={styles.overview} aria-label="Run launch overview">
      <p>RUN PREPARATION</p>
      <h2>准备运行这个 Agent</h2>
      <section>
        <strong>Revision 编译已验证</strong>
        <span>Graph validity 已通过；运行环境与 Android topology readiness 由底部 Run Bar 独立检查。</span>
      </section>
      <dl>
        <div><dt>Graph</dt><dd>{snapshot.graphStatus}</dd></div>
        <div><dt>Contract</dt><dd>{snapshot.contractVersion}</dd></div>
        <div><dt>Nodes</dt><dd>{snapshot.graphNodes.length}</dd></div>
      </dl>
      <details>
        <summary>Revision identity</summary>
        <code>{snapshot.revisionId}</code>
        <code>{snapshot.canonicalHash}</code>
      </details>
    </aside>
  );
}
