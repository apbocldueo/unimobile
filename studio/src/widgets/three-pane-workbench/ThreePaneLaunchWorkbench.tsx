import { uiMessage, uiText, useUiLocale } from "@/shared/i18n";
import { useMemo } from "react";
import {
  createReplayProjection,
  launchSummary,
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
  const uiLocale = useUiLocale();
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
    [snapshot, uiLocale],
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
          unavailableDetail={uiText("提交底部 Task 后才会启动设备并采集正式证据。")}
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
  useUiLocale();
  const summary = launchSummary(snapshot);
  return (
    <aside className={styles.overview} aria-label="Run launch overview">
      <p>{uiText("运行前确认")}</p>
      <h2>{uiText("准备运行这个 Agent")}</h2>
      <section>
        <strong>{uiText("已保存版本通过图校验")}</strong>
        <span>{uiText("核对下方模型、停止上限和底部设备选择，再输入任务。提交时会重新检查配置。")}</span>
      </section>
      <dl>
        <div><dt>{uiText("模型")}</dt><dd>{summary.models.length ? summary.models.map((model) => <p key={model}>{model}</p>) : uiText("此版本未提供可展示的模型配置")}</dd></div>
        <div><dt>{uiText("步骤上限")}</dt><dd>{summary.maxSteps ?? uiText("未提供")}</dd></div>
        <div><dt>{uiText("反馈上限")}</dt><dd>{summary.maxFeedbackIterations == null ? uiText("未提供") : uiMessage`${summary.maxFeedbackIterations} 轮反馈`}</dd></div>
        <div><dt>{uiText("停止条件")}</dt><dd>{uiText("任务声明结束、达到上限或运行出错时停止。具体条件由此版本的流程决定。")}</dd></div>
      </dl>
      <details>
        <summary>{uiText("版本与技术信息")}</summary>
        <p>{uiText("图：")}{snapshot.graphStatus} {" "}{uiText("· 合同：")}{snapshot.contractVersion} · {snapshot.graphNodes.length} {" "}{uiText("个节点")}</p>
        <code>{snapshot.revisionId}</code>
        <code>{snapshot.canonicalHash}</code>
      </details>
    </aside>
  );
}
