import { useCallback, useMemo, useState } from "react";
import { Handle, Position, useNodeId, useReactFlow, type Node, type NodeProps } from "@xyflow/react";
import { FLOW_TYPE_COLORS, FLOW_TYPE_LABELS, WILDCARD_FLOW_TYPE } from "@/modules/flow-graph/flowDataTypes";
import { useFlowStudioUi, useHandleHighlightKey } from "@/features/agent-studio/context/FlowStudioUiContext";
import type { FlowPortInstance } from "@/modules/flow-graph/flowPortBlueprint";
import type { FlowPaletteNodeData, IfElseOperatorValue } from "@/modules/flow-graph/flowNodeData";

export type IfElseFlowNodeType = Node<FlowPaletteNodeData, "ifElseFlow">;

function portStroke(port: FlowPortInstance): string {
  const t = port.dataTypes[0] ?? "plan";
  return FLOW_TYPE_COLORS[t] ?? "#888";
}

/** 右侧 rail：与其它 palette 节点一致，Handle 半幅在卡片边框外；竖直位置与页脚 True/False 行对齐 */
function RailBranchOutputHandle({
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
  const color = portStroke(port);
  const typesLabel =
    port.dataTypes.includes(WILDCARD_FLOW_TYPE) && port.portKind === "output"
      ? "任意"
      : port.dataTypes
          .map((t) => (t === WILDCARD_FLOW_TYPE ? "任意" : FLOW_TYPE_LABELS[t as keyof typeof FLOW_TYPE_LABELS] ?? t))
          .join("，");

  const ring = selectedNode || edgeHl ? "0 0 0 2px rgba(255,255,255,0.95)" : hover ? "0 0 0 1px rgba(255,255,255,0.55)" : "none";

  return (
    <div
      className="flow-ifelse-out-rail-anchor"
      style={{
        opacity: portsVisible ? 1 : 0,
        pointerEvents: portsVisible ? "auto" : "none",
      }}
    >
      <Handle
        type="source"
        position={Position.Right}
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

function InputPort({
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
  const color = portStroke(port);
  const typesLabel = port.dataTypes.map((t) => FLOW_TYPE_LABELS[t as keyof typeof FLOW_TYPE_LABELS] ?? t).join("，");
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
        type="target"
        position={Position.Left}
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

export function IfElseFlowNode({ data, selected }: NodeProps<IfElseFlowNodeType>) {
  const nodeId = useNodeId();
  const { portsVisible } = useFlowStudioUi();
  const { setNodes } = useReactFlow();

  const ports = data.ports ?? [];
  const input = useMemo(() => ports.find((p) => p.portKind === "input"), [ports]);
  const outFalse = useMemo(() => ports.find((p) => p.role === "out_false"), [ports]);
  const outTrue = useMemo(() => ports.find((p) => p.role === "out_true"), [ports]);

  const op = data.operator_value ?? "not_use";

  const onOperatorChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const v = e.target.value as IfElseOperatorValue;
      const nid = nodeId;
      if (!nid) return;
      setNodes((nds) =>
        nds.map((n) => (n.id === nid && n.type === "ifElseFlow" ? { ...n, data: { ...(n.data as FlowPaletteNodeData), operator_value: v } } : n)),
      );
    },
    [nodeId, setNodes],
  );

  return (
    <div className="flow-palette-node-shell flow-ifelse-shell">
      <div className="flow-palette-rail flow-palette-rail--left" aria-hidden={!input}>
        {input && nodeId ? <InputPort nodeId={nodeId} port={input} selectedNode={Boolean(selected)} portsVisible={portsVisible} /> : null}
      </div>
      <div className="flow-ifelse-card">
        <header className="flow-ifelse-section flow-ifelse-header">
          <div className="flow-ifelse-title">If-Else：用于判断是否使用一个组件</div>
        </header>
        <div className="flow-ifelse-divider" role="separator" />
        <section className="flow-ifelse-section flow-ifelse-body">
          <label className="flow-ifelse-operator-label" htmlFor={nodeId ? `ifelse-op-${nodeId}` : undefined}>
            Operator
          </label>
          <select
            id={nodeId ? `ifelse-op-${nodeId}` : undefined}
            className="flow-ifelse-select zx-control zx-body-sm w-full cursor-pointer px-3 py-2 text-[13px] font-medium"
            value={op}
            onChange={onOperatorChange}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <option value="use">使用</option>
            <option value="not_use">不使用</option>
          </select>
        </section>
        <div className="flow-ifelse-divider" role="separator" />
        <footer className="flow-ifelse-section flow-ifelse-footer flow-ifelse-footer-branches">
          <div className="flow-ifelse-branch-row">
            <span className="flow-ifelse-footer-branch-label flow-ifelse-footer-branch-label--true">True</span>
          </div>
          <div className="flow-ifelse-branch-row">
            <span className="flow-ifelse-footer-branch-label flow-ifelse-footer-branch-label--false">False</span>
          </div>
        </footer>
      </div>
      <div className="flow-palette-rail flow-palette-rail--right flow-ifelse-out-rail" aria-hidden={!outFalse || !outTrue}>
        <div className="flow-ifelse-out-rail-stack">
          <div className="flow-ifelse-out-rail-slot">
            {outTrue && nodeId ? (
              <RailBranchOutputHandle nodeId={nodeId} port={outTrue} selectedNode={Boolean(selected)} portsVisible={portsVisible} />
            ) : null}
          </div>
          <div className="flow-ifelse-out-rail-slot">
            {outFalse && nodeId ? (
              <RailBranchOutputHandle nodeId={nodeId} port={outFalse} selectedNode={Boolean(selected)} portsVisible={portsVisible} />
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
