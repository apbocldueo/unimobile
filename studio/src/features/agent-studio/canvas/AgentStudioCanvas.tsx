import { useCallback, useEffect, useMemo } from "react";
import {
  addEdge,
  Background,
  BackgroundVariant,
  ConnectionLineType,
  Controls,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  reconnectEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeTypes,
  type IsValidConnection,
  type Node,
  type NodeTypes,
  type OnSelectionChangeFunc,
} from "@xyflow/react";
import { useToastStore } from "@/stores/toastStore";
import { FLOW_COMPONENT_DRAG_MIME, FLOW_NODE_CATALOG, getRegistrySlotIdForFlowStudioCard } from "@/components/flow-studio-cards";
import { createPortsForComponent } from "@/modules/flow-graph/flowPortBlueprint";
import { explainReject, validateConnection } from "@/modules/flow-graph/flowConnection";
import { FlowConnectionLine } from "@/features/agent-studio/canvas/edges/FlowConnectionLine";
import { FlowStudioUiProvider, useFlowStudioUi } from "@/features/agent-studio/context/FlowStudioUiContext";
import { FlowTypedEdge } from "@/features/agent-studio/canvas/edges/FlowTypedEdge";
import { IfElseFlowNode } from "@/features/agent-studio/canvas/nodes/IfElseFlowNode";
import { FlowNodeInspectorPanel } from "@/features/agent-studio/panels/FlowNodeInspectorPanel";
import { StudioPaletteNode } from "@/components/flow-studio-cards/StudioPaletteNode";
import { takeStudioBuilderPendingFlowDocument } from "@/features/agent-studio/studioBuilderPendingFlow";
import { applyFlowDocument } from "@/modules/flow-graph/flowDocument";
import { useAgentStudioFlowStore } from "@/stores/agentStudioFlowStore";
import type { FlowPaletteNodeData } from "@/modules/flow-graph/flowNodeData";

const nodeTypes: NodeTypes = {
  studioPalette: StudioPaletteNode,
  ifElseFlow: IfElseFlowNode,
};

const edgeTypes = {
  flowTyped: FlowTypedEdge,
} as const satisfies EdgeTypes;

function generateNodeId(): string {
  return `node_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function newEdgeId(): string {
  return `edge_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function findComponentById(id: string) {
  const flat = Object.values(FLOW_NODE_CATALOG).flat();
  return flat.find((c) => c.id === id);
}

function AgentStudioCanvasInner() {
  const [nodes, setNodes, onNodesChange] = useNodesState([] as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([] as Edge[]);
  const { screenToFlowPosition, getNodes, getEdges, getNode, fitView } = useReactFlow();
  const { portsVisible, setHighlightedHandleKeys } = useFlowStudioUi();
  const pushToast = useToastStore((s) => s.pushToast);
  const selectedNodeIds = useAgentStudioFlowStore((s) => s.selectedNodeIds);

  useEffect(() => {
    const doc = takeStudioBuilderPendingFlowDocument();
    if (!doc) return;
    const res = applyFlowDocument(doc);
    setNodes(res.nodes);
    setEdges(res.edges);
    requestAnimationFrame(() => {
      try {
        fitView({ padding: 0.2 });
      } catch {
        /* */
      }
    });
  }, [setNodes, setEdges, fitView]);

  const showNodeInspector = useMemo(() => {
    if (selectedNodeIds.length !== 1) return false;
    const n = getNode(selectedNodeIds[0]!);
    return Boolean(n && n.type === "ifElseFlow");
  }, [getNode, selectedNodeIds, nodes]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const componentId = e.dataTransfer.getData(FLOW_COMPONENT_DRAG_MIME);
      if (!componentId) return;

      const comp = findComponentById(componentId);
      if (!comp) return;

      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      const id = generateNodeId();
      const ports = createPortsForComponent(comp.id, id);
      const isIfElse = comp.id === "ifelse";
      const registrySlotId = getRegistrySlotIdForFlowStudioCard(comp.id);

      const baseData: FlowPaletteNodeData = {
        componentId: comp.id,
        label: comp.label,
        icon: comp.icon,
        desc: comp.desc,
        ports,
        ...(isIfElse ? { operator_value: "not_use" as const, condition_note: "" } : {}),
        ...(!isIfElse && registrySlotId
          ? {
              registrySlotId,
              selectedPluginId: null,
              selectedPluginTitle: null,
              pluginParamValues: {},
            }
          : {}),
      };

      const newNode: Node = {
        id,
        type: isIfElse ? "ifElseFlow" : "studioPalette",
        position,
        data: baseData,
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [screenToFlowPosition, setNodes],
  );

  const isValidConnection = useCallback<IsValidConnection>((obj) => {
    const c: Connection = {
      source: obj.source,
      target: obj.target,
      sourceHandle: obj.sourceHandle ?? null,
      targetHandle: obj.targetHandle ?? null,
    };
    if (!c.sourceHandle || !c.targetHandle) return false;
    return validateConnection(getNodes(), c).ok;
  }, [getNodes]);

  const onConnect = useCallback(
    (connection: Connection) => {
      const nList = getNodes();
      const v = validateConnection(nList, connection);
      if (!v.ok) return;
      const trimmed = getEdges().filter((e) => !(e.target === connection.target && e.targetHandle === connection.targetHandle));
      const sn = nList.find((n) => n.id === connection.source);
      const sp =
        sn?.type === "studioPalette" || sn?.type === "ifElseFlow"
          ? (sn.data as FlowPaletteNodeData).ports?.find((p) => p.portId === connection.sourceHandle)
          : undefined;
      const dtype = sp?.dataTypes?.[0] ?? "plan";
      setEdges(addEdge({ ...connection, id: newEdgeId(), type: "flowTyped", data: { dataType: dtype } }, trimmed));
    },
    [getEdges, getNodes, setEdges],
  );

  const onConnectEnd = useCallback(
    (_ev: MouseEvent | TouchEvent, state: { isValid?: boolean | null; fromNode?: { id: string } | null; toNode?: { id: string } | null; fromHandle?: { id?: string | null } | null; toHandle?: { id?: string | null } | null }) => {
      if (state.isValid !== false || !state.toNode) return;
      const c: Connection = {
        source: state.fromNode?.id ?? "",
        target: state.toNode.id,
        sourceHandle: state.fromHandle?.id ?? null,
        targetHandle: state.toHandle?.id ?? null,
      };
      const msg = explainReject(getNodes(), c);
      if (msg) pushToast({ message: msg, tone: "warning", durationMs: 4200 });
    },
    [getNodes, pushToast],
  );

  const onReconnect = useCallback(
    (oldEdge: Edge, newConnection: Connection) => {
      if (!validateConnection(getNodes(), newConnection).ok) return;
      setEdges((eds) => reconnectEdge(oldEdge, newConnection, eds));
    },
    [getNodes, setEdges],
  );

  const onSelectionChange: OnSelectionChangeFunc = useCallback(
    ({ nodes: selNodes, edges: selEdges }) => {
      useAgentStudioFlowStore.getState().setSelectedNodeIds(selNodes.map((n) => n.id));
      const next = new Set<string>();
      for (const e of selEdges) {
        if (e.sourceHandle) next.add(`${e.source}:${e.sourceHandle}`);
        if (e.targetHandle) next.add(`${e.target}:${e.targetHandle}`);
      }
      setHighlightedHandleKeys(next);
    },
    [setHighlightedHandleKeys],
  );

  const defaultViewport = useMemo(() => ({ x: 0, y: 0, zoom: 1 }), []);

  const defaultEdgeOptions = useMemo(
    () => ({
      type: "flowTyped" as const,
      animated: false,
      interactionWidth: 22,
    }),
    [],
  );

  return (
    <div className="flow-canvas-wrap relative flex min-h-0 flex-1 flex-col">
      <ReactFlow
        className="h-full min-h-0 flex-1"
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onSelectionChange={onSelectionChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onConnect={onConnect}
        onConnectEnd={onConnectEnd}
        onReconnect={onReconnect}
        isValidConnection={isValidConnection}
        connectionLineComponent={FlowConnectionLine}
        connectionLineType={ConnectionLineType.Bezier}
        defaultViewport={defaultViewport}
        nodesConnectable={portsVisible}
        connectOnClick
        edgesReconnectable
        reconnectRadius={12}
        elementsSelectable
        nodesDraggable
        deleteKeyCode={["Backspace", "Delete"]}
        zoomOnScroll
        zoomOnPinch
        panOnScroll={false}
        panOnDrag={[1, 2]}
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
        maxZoom={2}
        snapToGrid
        snapGrid={[24, 24]}
        connectionRadius={22}
        elevateEdgesOnSelect
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1.5} color="var(--zx-grid-dot)" />
        <Controls className="[&_button]:!border-0" showInteractive={false} />
        <Panel position="top-left" className="flow-canvas-hint m-2 max-w-[220px] rounded-lg border border-[color:var(--zx-border-light)] bg-[color:var(--zx-panel)] px-3 py-2 text-[11px] leading-snug text-[color:var(--zx-text-muted)] shadow-[var(--zx-shadow-soft)]">
          拖拽输出端口连线到输入；或点击输出再点击输入。Ctrl 多选连线。中键/右键平移。
        </Panel>
        {showNodeInspector ? (
          <Panel position="top-right" className="flow-node-inspector-panel-wrap z-10 m-2 max-w-[calc(100vw-16px)]">
            <FlowNodeInspectorPanel />
          </Panel>
        ) : null}
      </ReactFlow>
    </div>
  );
}

export function AgentStudioCanvas() {
  return (
    <ReactFlowProvider>
      <FlowStudioUiProvider>
        <AgentStudioCanvasInner />
      </FlowStudioUiProvider>
    </ReactFlowProvider>
  );
}
