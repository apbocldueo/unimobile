import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import type { BuilderFlowEdge } from "../model/flowAdapter";
import { canvasSafeText } from "@/entities/agent-graph";
import styles from "./agentBuilder.module.css";

/** Render one typed semantic edge with feedback and diagnostics affordances. */
export function AgentBuilderEdge(props: EdgeProps<BuilderFlowEdge>) {
  const [path, labelX, labelY] = getBezierPath(props);
  const label = canvasSafeText(props.data?.semanticLabel);
  const tone =
    props.data?.diagnosticSeverity === "error"
      ? "var(--zx-status-danger)"
      : props.data?.diagnosticSeverity === "warning"
        ? "var(--zx-status-warning)"
        : props.selected
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
          stroke: tone,
          strokeWidth: props.selected ? 2.5 : 1.8,
          strokeDasharray: props.data?.kind === "feedback" ? "7 5" : undefined,
        }}
      />
      {label || (props.data?.diagnosticCount ?? 0) > 0 ? <EdgeLabelRenderer>
        <span
          className={styles.edgeLabel}
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
        >
          {label}
          {(props.data?.diagnosticCount ?? 0) > 0
            ? ` · ${props.data?.diagnosticCount} 条诊断`
            : ""}
        </span>
      </EdgeLabelRenderer> : null}
    </>
  );
}
