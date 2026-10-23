import { uiMessage, uiText, useUiLocale } from "@/shared/i18n";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  useStore,
  type EdgeProps,
} from "@xyflow/react";
import type { BuilderFlowEdge } from "../model/flowAdapter";
import { portIdFromHandle } from "../model/flowAdapter";
import { portLabel } from "../model/portPresentation";
import { relationKindLabel } from "../model/relationPresentation";
import { canvasSafeText } from "@/entities/agent-graph";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import styles from "./agentBuilder.module.css";

/** Build a feedback path that travels below the main canvas flow before returning to its target.
 * Args: props contains resolved endpoints and a stable return lane; graphBottom is the lowest measured node boundary.
 * Returns: An SVG path and a readable label position for the feedback edge.
 */
function getFeedbackPath(props: EdgeProps<BuilderFlowEdge>, graphBottom: number): [string, number, number] {
  const lane = props.data?.returnLane ?? 0;
  const clearanceY = Math.max(graphBottom, props.sourceY, props.targetY) + 48 + lane * 36;
  const exitX = props.sourceX + 30 + lane * 12;
  const entryX = props.targetX - 30 - lane * 12;
  const path = `M ${props.sourceX},${props.sourceY} L ${exitX},${props.sourceY} L ${exitX},${clearanceY} L ${entryX},${clearanceY} L ${entryX},${props.targetY} L ${props.targetX},${props.targetY}`;
  return [path, (props.sourceX + props.targetX) / 2, clearanceY - 18];
}

/** Render one typed semantic edge with feedback and diagnostics affordances. */
export function AgentBuilderEdge(props: EdgeProps<BuilderFlowEdge>) {
  useUiLocale();
  const selectEdge = useAgentBuilderDocumentStore((state) => state.selectEdge);
  const feedback = props.data?.kind === "feedback";
  const graphBottom = useStore((state) => feedback
    ? Math.max(0, ...state.nodes.map((node) => node.position.y + (node.measured?.height ?? 0))) : 0);
  const [path, labelX, labelY] = feedback ? getFeedbackPath(props, graphBottom)
    : getSmoothStepPath({ ...props, borderRadius: 12, offset: 24 });
  const label = canvasSafeText(props.data?.semanticLabel) || (props.selected && props.data
    ? `${relationKindLabel(props.data.kind)} · ${portLabel(portIdFromHandle(props.sourceHandleId) ?? uiText("输出"))} → ${portLabel(portIdFromHandle(props.targetHandleId) ?? uiText("输入"))}` : "");
  const tone =
    props.data?.diagnosticSeverity === "error"
      ? "var(--zx-status-danger)"
      : props.data?.diagnosticSeverity === "warning"
        ? "var(--zx-status-warning)"
        : props.selected || feedback
          ? "var(--zx-primary)"
          : "var(--zx-text-muted)";
  return (
    <>
      <BaseEdge
        id={props.id}
        path={path}
        markerEnd={props.markerEnd}
        interactionWidth={22}
        style={{
          opacity: props.style?.opacity,
          stroke: tone,
          strokeWidth: props.selected || feedback ? 2.5 : 1.8,
          strokeDasharray: props.data?.kind === "feedback" ? "7 5" : undefined,
        }}
      />
      {label || (props.data?.diagnosticCount ?? 0) > 0 ? <EdgeLabelRenderer>
        <button
          type="button"
          onClick={() => selectEdge(props.id)}
          aria-label={feedback ? uiText("查看下一轮反馈策略") : uiText("查看连接详情")}
          className={`${styles.edgeLabel} ${styles.edgeLabelButton} nodrag nopan ${feedback ? styles.feedbackLabel : ""}`}
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
        >
          {feedback ? "↻ " : ""}{label}
          {feedback && props.data?.feedbackMaxIterations !== undefined ? uiMessage` · 最多 ${props.data.feedbackMaxIterations} 轮` : ""}
          {(props.data?.diagnosticCount ?? 0) > 0
            ? uiMessage` · ${props.data?.diagnosticCount} 条诊断`
            : ""}
        </button>
      </EdgeLabelRenderer> : null}
    </>
  );
}
