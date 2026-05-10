import { getBezierPath, type ConnectionLineComponentProps } from "@xyflow/react";
import { FLOW_TYPE_COLORS, type FlowDataType } from "@/modules/flow-graph/flowDataTypes";
import { primaryOutputType } from "@/modules/flow-graph/flowConnection";
import type { FlowPaletteNodeData } from "@/modules/flow-graph/flowNodeData";

export function FlowConnectionLine({
  fromX,
  fromY,
  toX,
  toY,
  fromPosition,
  toPosition,
  connectionStatus,
  fromNode,
  fromHandle,
}: ConnectionLineComponentProps) {
  const [path] = getBezierPath({
    sourceX: fromX,
    sourceY: fromY,
    sourcePosition: fromPosition,
    targetX: toX,
    targetY: toY,
    targetPosition: toPosition,
  });

  const fd = fromNode?.data as FlowPaletteNodeData | undefined;
  const hid = fromHandle?.id ?? "";
  const port = fd?.ports?.find((p) => p.portId === hid);
  const base = port ? FLOW_TYPE_COLORS[primaryOutputType(port) as FlowDataType] ?? "#888" : "#888888";

  const invalid = connectionStatus === "invalid";
  const stroke = invalid ? "#ff4d4f" : base;
  const dash = invalid ? "6 4" : undefined;
  const sw = invalid ? 1 : 1.5;

  return (
    <g>
      <path
        fill="none"
        className="animated"
        d={path}
        stroke={stroke}
        strokeWidth={sw}
        strokeDasharray={dash}
      />
    </g>
  );
}
