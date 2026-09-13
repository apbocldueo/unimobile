import { useCallback, useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  useReactFlow,
  type Connection,
  type EdgeTypes,
  type NodeTypes,
} from "@xyflow/react";
import type { ComponentCatalog } from "@/entities/component-catalog";
import type { StudioCapabilityRelation } from "@/entities/agent-graph";
import type { CapabilityFamily } from "@/entities/component-catalog";
import { useToastStore } from "@/stores/toastStore";
import {
  BUILDER_DRAG_MIME,
  documentToFlow,
  nextNodePosition,
  nextStableId,
  portIdFromHandle,
  validateBuilderConnection,
} from "../model/flowAdapter";
import { createCapabilityNode } from "../model/nodeFactory";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { AgentBuilderEdge } from "./AgentBuilderEdge";
import { AgentBuilderNode } from "./AgentBuilderNode";
import styles from "./agentBuilder.module.css";

const nodeTypes = { agentBuilder: AgentBuilderNode } satisfies NodeTypes;
const edgeTypes = { agentBuilder: AgentBuilderEdge } satisfies EdgeTypes;

type BuilderCanvasProps = {
  catalog: ComponentCatalog | null;
};

/** Read the exact nested document currently owned by the Builder store. */
function visibleDocument() {
  const state = useAgentBuilderDocumentStore.getState();
  return state.document;
}

/** Render the document-store projection and translate gestures into semantic edits. */
export function BuilderCanvas({ catalog }: BuilderCanvasProps) {
  const { screenToFlowPosition } = useReactFlow();
  const root = useAgentBuilderDocumentStore((state) => state.document);
  const selectedCanvasId = useAgentBuilderDocumentStore((state) => state.selectedCanvasId);
  const selectedEdgeId = useAgentBuilderDocumentStore((state) => state.selectedEdgeId);
  const compileResult = useAgentBuilderDocumentStore((state) => state.compileResult);
  const addNode = useAgentBuilderDocumentStore((state) => state.addNode);
  const addEdge = useAgentBuilderDocumentStore((state) => state.addEdge);
  const updateEdge = useAgentBuilderDocumentStore((state) => state.updateEdge);
  const removeNodes = useAgentBuilderDocumentStore((state) => state.removeNodes);
  const removeEdges = useAgentBuilderDocumentStore((state) => state.removeEdges);
  const setNodePosition = useAgentBuilderDocumentStore((state) => state.setNodePosition);
  const setViewport = useAgentBuilderDocumentStore((state) => state.setViewport);
  const selectNode = useAgentBuilderDocumentStore((state) => state.selectNode);
  const selectEdge = useAgentBuilderDocumentStore((state) => state.selectEdge);
  const pushToast = useToastStore((state) => state.pushToast);
  const document = root;
  const flow = useMemo(() => {
    if (!document) return { nodes: [], edges: [] };
    const projected = documentToFlow(
      document,
      catalog,
      compileResult?.diagnostics ?? [],
      compileResult?.sourceMap ?? [],
    );
    return {
      nodes: projected.nodes.map((node) => ({
        ...node,
        selected: node.id === selectedCanvasId,
      })),
      edges: projected.edges.map((edge) => ({
        ...edge,
        selected: edge.id === selectedEdgeId,
        markerEnd: { type: MarkerType.ArrowClosed, color: "var(--zx-text-muted)" },
      })),
    };
  }, [catalog, compileResult, document, selectedCanvasId, selectedEdgeId]);

  const validate = useCallback(
    (connection: Connection, ignoreEdgeId?: string) => {
      const current = visibleDocument();
      const sourcePortId = portIdFromHandle(connection.sourceHandle);
      const targetPortId = portIdFromHandle(connection.targetHandle);
      if (
        !current ||
        !connection.source ||
        !connection.target ||
        !sourcePortId ||
        !targetPortId
      ) {
        return { ok: false as const, reason: "连线端点不完整" };
      }
      return validateBuilderConnection({
        document: current,
        catalog,
        sourceCanvasId: connection.source,
        sourcePortId,
        targetCanvasId: connection.target,
        targetPortId,
        ignoreEdgeId,
      });
    },
    [catalog],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const current = visibleDocument();
      const result = validate(connection);
      if (!current || !result.ok || !connection.source || !connection.target) {
        pushToast({
          message: result.ok ? "连线端点不完整" : result.reason,
          tone: "warning",
          durationMs: 4200,
        });
        return;
      }
      const sourcePortId = portIdFromHandle(connection.sourceHandle);
      const targetPortId = portIdFromHandle(connection.targetHandle);
      if (!sourcePortId || !targetPortId) return;
      const sourceObject = [current.input, ...current.capabilities].find(
        (item) => item.canvasId === connection.source,
      );
      const targetObject = [current.output, ...current.capabilities].find(
        (item) => item.canvasId === connection.target,
      );
      if (!sourceObject || !targetObject) return;
      const edge: StudioCapabilityRelation = {
        canvasId: nextStableId(
          "relation",
          current.relations.map((item) => item.canvasId),
        ),
        source: { ownerId: sourceObject.logicalId, portId: sourcePortId },
        target: {
          ownerId: targetObject.logicalId,
          portId: result.kind === "termination" ? "terminal" : targetPortId,
        },
        kind: result.kind,
      };
      addEdge(edge);
    },
    [addEdge, pushToast, validate],
  );

  const onReconnect = useCallback(
    (oldEdge: { id: string }, connection: Connection) => {
      const result = validate(connection, oldEdge.id);
      const sourcePortId = portIdFromHandle(connection.sourceHandle);
      const targetPortId = portIdFromHandle(connection.targetHandle);
      if (
        !result.ok ||
        !connection.source ||
        !connection.target ||
        !sourcePortId ||
        !targetPortId
      ) {
        pushToast({
          message: result.ok ? "连线端点不完整" : result.reason,
          tone: "warning",
          durationMs: 4200,
        });
        return;
      }
      updateEdge(oldEdge.id, (edge) => ({
        ...edge,
        source: {
          ownerId: visibleDocument()!.capabilities.find((item) => item.canvasId === connection.source)?.logicalId
            ?? visibleDocument()!.input.logicalId,
          portId: sourcePortId,
        },
        target: {
          ownerId: visibleDocument()!.capabilities.find((item) => item.canvasId === connection.target)?.logicalId
            ?? visibleDocument()!.output.logicalId,
          portId: result.kind === "termination" ? "terminal" : targetPortId,
        },
        kind: result.kind,
        feedback: result.kind === "feedback" ? edge.feedback : undefined,
      }));
    },
    [pushToast, updateEdge, validate],
  );

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const current = visibleDocument();
      if (!current) return;
      let payload: unknown;
      try {
        payload = JSON.parse(event.dataTransfer.getData(BUILDER_DRAG_MIME)) as unknown;
      } catch {
        return;
      }
      if (!payload || typeof payload !== "object") return;
      const raw = payload as { type?: unknown; family?: unknown };
      if (raw.type !== "capability" || typeof raw.family !== "string" || !catalog) {
        return;
      }
      let node;
      try {
        node = createCapabilityNode(raw.family as CapabilityFamily, catalog, current);
      } catch (cause) {
        pushToast({ message: cause instanceof Error ? cause.message : "能力当前不可用", tone: "warning" });
        return;
      }
      const family = catalog.capabilityFamilies?.find((item) => item.family === node.family);
      const fallback = nextNodePosition(current.capabilities.length + 2);
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      addNode(node, {
        x: Number.isFinite(position.x) ? position.x : fallback.x,
        y: Number.isFinite(position.y) ? position.y : fallback.y,
        label: family?.label ?? node.family,
        description: `${node.family} capability`,
        icon: "",
        collapsed: false,
        renderMode: "card",
      });
      selectNode(node.canvasId);
    },
    [addNode, catalog, pushToast, screenToFlowPosition, selectNode],
  );

  if (!document) return <div className={styles.emptyState}>正在加载 Agent document…</div>;

  return (
    <main className={styles.canvas} aria-label="AgentGraph 画布">
      <ReactFlow
        key={document.documentId}
        nodes={flow.nodes}
        edges={flow.edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
        }}
        onDrop={onDrop}
        onConnect={onConnect}
        onReconnect={onReconnect}
        isValidConnection={(connection) =>
          validate({
            source: connection.source,
            target: connection.target,
            sourceHandle: connection.sourceHandle ?? null,
            targetHandle: connection.targetHandle ?? null,
          }).ok
        }
        onNodeDragStop={(_, node) => setNodePosition(node.id, node.position.x, node.position.y)}
        onNodesDelete={(nodes) => removeNodes(nodes.filter((node) => node.data.kind === "capability").map((node) => node.id))}
        onEdgesDelete={(edges) => removeEdges(edges.map((edge) => edge.id))}
        onNodeClick={(_, node) => selectNode(node.id)}
        onEdgeClick={(_, edge) => selectEdge(edge.id)}
        onPaneClick={() => {
          selectNode(null);
          selectEdge(null);
        }}
        onMoveEnd={(_, viewport) => setViewport(viewport.x, viewport.y, viewport.zoom)}
        defaultViewport={document.presentation.viewport}
        minZoom={0.2}
        maxZoom={2}
        snapToGrid
        snapGrid={[20, 20]}
        deleteKeyCode={["Backspace", "Delete"]}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} color="var(--zx-grid-dot)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </main>
  );
}
