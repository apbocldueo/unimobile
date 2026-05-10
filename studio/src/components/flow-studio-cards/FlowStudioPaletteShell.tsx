import { useMemo, useState } from "react";
import { Handle, Position, useNodeId } from "@xyflow/react";
import { FLOW_TYPE_COLORS, FLOW_TYPE_LABELS, WILDCARD_FLOW_TYPE } from "@/modules/flow-graph/flowDataTypes";
import { useFlowStudioUi, useHandleHighlightKey } from "@/features/agent-studio/context/FlowStudioUiContext";
import type { FlowPortInstance, PortBlueprint } from "@/modules/flow-graph/flowPortBlueprint";
import { instantiateBlueprints } from "@/modules/flow-graph/flowPortBlueprint";
import type { FlowStudioPaletteCardProps } from "./types";

function portStroke(port: FlowPortInstance): string {
  const t = port.dataTypes[0] ?? "plan";
  return FLOW_TYPE_COLORS[t] ?? "#888";
}

function PortHandle({
  nodeId,
  port,
  selectedNode,
  portsVisible,
}: {
  nodeId: string;
  port: FlowPortInstance;
  selectedNode: boolean;
  portsVisible: boolean;
}) {
  const [hover, setHover] = useState(false);
  const edgeHl = useHandleHighlightKey(nodeId, port.portId);
  const isOut = port.portKind === "output";
  const color = portStroke(port);
  const typesLabel =
    port.dataTypes.includes(WILDCARD_FLOW_TYPE) && port.portKind === "output"
      ? "任意"
      : port.dataTypes
          .map((t) => (t === WILDCARD_FLOW_TYPE ? "任意" : FLOW_TYPE_LABELS[t as Exclude<typeof t, typeof WILDCARD_FLOW_TYPE>] ?? t))
          .join("，");

  const ring = selectedNode || edgeHl ? "0 0 0 2px rgba(255,255,255,0.95)" : hover ? "0 0 0 1px rgba(255,255,255,0.55)" : "none";

  return (
    <div
      className="flow-port-anchor"
      style={{
        top: `${port.slot * 100}%`,
        opacity: portsVisible ? 1 : 0,
        pointerEvents: portsVisible ? "auto" : "none",
      }}
    >
      <Handle
        type={isOut ? "source" : "target"}
        position={isOut ? Position.Right : Position.Left}
        id={port.portId}
        isConnectable={portsVisible}
        className="flow-port-handle nodrag"
        style={{
          background: color,
          border: "1px solid #444444",
          width: 8,
          height: 8,
          opacity: hover || selectedNode || edgeHl ? 1 : 0.45,
          boxShadow: ring,
        }}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      />
      {hover && portsVisible ? (
        <div className="flow-port-tooltip" role="tooltip">
          <div className="flow-port-tooltip-name">{port.portName}</div>
          <div className="flow-port-tooltip-types">{typesLabel}</div>
        </div>
      ) : null}
    </div>
  );
}

export function FlowStudioCardHeaderRow({ data }: Pick<FlowStudioPaletteCardProps, "data">) {
  return (
    <div className="flow-palette-node-row">
      <span className="flow-palette-node-icon" aria-hidden>
        {data.icon}
      </span>
      <div className="flow-palette-node-text">
        <div className="flow-palette-node-label">{data.label}</div>
        <div className="flow-palette-node-desc">{data.desc}</div>
      </div>
    </div>
  );
}

export type FlowStudioPaletteShellProps = FlowStudioPaletteCardProps & {
  portBlueprints: PortBlueprint[];
  widenInner?: boolean;
  children: React.ReactNode;
};

export function FlowStudioPaletteShell({ data, selected, portBlueprints, widenInner, children }: FlowStudioPaletteShellProps) {
  const nodeId = useNodeId();
  const { portsVisible } = useFlowStudioUi();

  const ports = useMemo(() => {
    if (data.ports?.length) return data.ports;
    if (!nodeId) return [];
    return instantiateBlueprints(portBlueprints, nodeId);
  }, [data.ports, portBlueprints, nodeId]);

  const inputs = useMemo(() => ports.filter((p) => p.portKind === "input"), [ports]);
  const outputs = useMemo(() => ports.filter((p) => p.portKind === "output"), [ports]);

  const innerClass = ["flow-palette-node-inner", widenInner ? "flow-palette-node-inner--config" : ""].filter(Boolean).join(" ");

  return (
    <div className="flow-palette-node-shell">
      <div className="flow-palette-rail flow-palette-rail--left" aria-hidden={!inputs.length}>
        {inputs.map((p) => (
          <PortHandle key={p.portId} nodeId={nodeId ?? ""} port={p} selectedNode={Boolean(selected)} portsVisible={portsVisible} />
        ))}
      </div>
      <div className={innerClass}>{children}</div>
      <div className="flow-palette-rail flow-palette-rail--right" aria-hidden={!outputs.length}>
        {outputs.map((p) => (
          <PortHandle key={p.portId} nodeId={nodeId ?? ""} port={p} selectedNode={Boolean(selected)} portsVisible={portsVisible} />
        ))}
      </div>
    </div>
  );
}
