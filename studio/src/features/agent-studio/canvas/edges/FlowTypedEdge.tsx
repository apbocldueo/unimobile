import { useState } from "react";
import { BaseEdge, EdgeLabelRenderer, getBezierPath, useReactFlow, type EdgeProps } from "@xyflow/react";
import { FLOW_TYPE_COLORS, FLOW_TYPE_LABELS, WILDCARD_FLOW_TYPE, type FlowDataType } from "@/modules/flow-graph/flowDataTypes";

export type FlowTypedEdgeData = {
  dataType: FlowDataType;
};

function darken(hex: string, amount = 0.2): string {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!m) return hex;
  const r = Math.max(0, Math.min(255, Math.round(parseInt(m[1]!, 16) * (1 - amount))));
  const g = Math.max(0, Math.min(255, Math.round(parseInt(m[2]!, 16) * (1 - amount))));
  const b = Math.max(0, Math.min(255, Math.round(parseInt(m[3]!, 16) * (1 - amount))));
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
}

export function FlowTypedEdge(props: EdgeProps) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, selected, data } = props;
  const [hover, setHover] = useState(false);
  const { getNode } = useReactFlow();

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const dtype = (data?.dataType ?? "plan") as FlowDataType;
  const base = FLOW_TYPE_COLORS[dtype] ?? "#888888";
  const stroke = selected || hover ? darken(base, 0.22) : base;
  const sw = selected ? 3 : 2;

  const label =
    dtype === WILDCARD_FLOW_TYPE ? "任意" : (FLOW_TYPE_LABELS[dtype as keyof typeof FLOW_TYPE_LABELS] ?? dtype);
  const src = getNode(props.source)?.data as { label?: string } | undefined;
  const tgt = getNode(props.target)?.data as { label?: string } | undefined;
  const title = `${label} · ${src?.label ?? props.source} → ${tgt?.label ?? props.target}`;

  return (
    <>
      <path
        d={edgePath}
        fill="none"
        className="react-flow__edge-path"
        style={{
          stroke: "transparent",
          strokeWidth: 16,
          cursor: "pointer",
        }}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      />
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        interactionWidth={20}
        style={{
          strokeLinecap: "round",
          strokeLinejoin: "round",
          stroke: stroke,
          strokeWidth: sw,
          filter: selected ? "drop-shadow(0 1px 3px rgba(0,0,0,0.45))" : undefined,
          ...style,
        }}
      />
      <circle cx={sourceX} cy={sourceY} r={3} fill={stroke} pointerEvents="none" />
      <circle cx={targetX} cy={targetY} r={3} fill={stroke} pointerEvents="none" />
      {(hover || selected) && (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan flow-edge-label"
            title={title}
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: "none",
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
