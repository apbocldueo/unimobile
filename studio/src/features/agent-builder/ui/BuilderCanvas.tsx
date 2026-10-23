import { uiMessage, uiText, useUiLocale } from "@/shared/i18n";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  ReactFlow,
  useReactFlow,
  useNodesInitialized,
  useStoreApi,
  useStore,
  type Connection,
  type FinalConnectionState,
  type EdgeTypes,
  type NodeTypes,
} from "@xyflow/react";
import type { ComponentCatalog } from "@/entities/component-catalog";
import type { StudioCapabilityRelation } from "@/entities/agent-graph";
import type { CapabilityFamily } from "@/entities/component-catalog";
import { useToastStore } from "@/stores/toastStore";
import {
  BUILDER_DRAG_MIME,
  defaultFeedbackPolicy,
  documentToFlow,
  nextNodePosition,
  nextStableId,
  portIdFromHandle,
  type BuilderConnectionKind,
  type BuilderFlowNode,
  type BuilderFlowEdge,
  validateBuilderConnection,
} from "../model/flowAdapter";
import { endedConnection, type AttemptHandle } from "../model/connectionAttempt";
import { createCapabilityNode } from "../model/nodeFactory";
import { useCanvasInteractionStore } from "../model/canvasInteraction.store";
import { autoLayoutPositions } from "../model/canvasLayout";
import { useCanvasNodes } from "../model/useCanvasNodes";
import { visiblePlacement } from "../model/visiblePlacement";
import { builderGuideProgress } from "../model/builderGuideProgress";
import { connectionCandidateHandleIds, type ConnectionFocus } from "../model/connectionCandidates";
import { portLabel } from "../model/portPresentation";
import { relationEndpointFocus } from "../model/relationPresentation";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { AgentBuilderEdge } from "./AgentBuilderEdge";
import { BuilderGuide } from "./BuilderGuide";
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
  const uiLocale = useUiLocale();
  const { screenToFlowPosition, getViewport, setViewport: moveCamera, getNodes, fitBounds, zoomTo } = useReactFlow<BuilderFlowNode, BuilderFlowEdge>();
  const flowStore = useStoreApi();
  const canvasWidth = useStore((state) => state.width);
  const canvasHeight = useStore((state) => state.height);
  const canvas = useRef<HTMLElement>(null);
  const reconnectingEdge = useRef<string | undefined>(undefined);
  const clickStart = useRef<AttemptHandle | undefined>(undefined);
  const userCameraCommand = useRef(false);
  const pendingReveal = useRef<{ sessionId: number; canvasId: string } | null>(null);
  const pendingFit = useRef(false);
  const nodesInitialized = useNodesInitialized();
  const [expandedSession, setExpandedSession] = useState<number | null>(null);
  const [connectionFocus, setConnectionFocus] = useState<ConnectionFocus | null>(null);
  const connectionKind: BuilderConnectionKind = connectionFocus?.kind ?? "ordinary";
  const [draggingCanvasId, setDraggingCanvasId] = useState<string | null>(null);
  const sessionId = useAgentBuilderDocumentStore((state) => state.sessionId);
  const root = useAgentBuilderDocumentStore((state) => state.document);
  const selectedCanvasId = useAgentBuilderDocumentStore((state) => state.selectedCanvasId);
  const selectedEdgeId = useAgentBuilderDocumentStore((state) => state.selectedEdgeId);
  const compileResult = useAgentBuilderDocumentStore((state) => state.compileResult);
  const addNode = useAgentBuilderDocumentStore((state) => state.addNode);
  const addEdge = useAgentBuilderDocumentStore((state) => state.addEdge);
  const updateEdge = useAgentBuilderDocumentStore((state) => state.updateEdge);
  const removeElements = useAgentBuilderDocumentStore((state) => state.removeElements);
  const cameraViewport = useAgentBuilderDocumentStore((state) => state.cameraViewport);
  const setNodePositions = useAgentBuilderDocumentStore((state) => state.setNodePositions);
  const setViewport = useAgentBuilderDocumentStore((state) => state.setViewport);
  const selectNode = useAgentBuilderDocumentStore((state) => state.selectNode);
  const selectEdge = useAgentBuilderDocumentStore((state) => state.selectEdge);
  const pushToast = useToastStore((state) => state.pushToast);
  const document = root;
  useEffect(() => {
    /** Read finite current geometry, leaving space for the bottom canvas controls. */
    const geometry = () => {
      const rect = canvas.current?.getBoundingClientRect();
      if (!rect || rect.width <= 0 || rect.height <= 0) return null;
      const start = screenToFlowPosition({ x: rect.left + 16, y: rect.top + 48 });
      const end = screenToFlowPosition({ x: rect.right - 16, y: rect.bottom - 60 });
      return { x: start.x, y: start.y, width: end.x - start.x, height: end.y - start.y };
    };
    userCameraCommand.current = false;
    clickStart.current = undefined;
    reconnectingEdge.current = undefined;
    setConnectionFocus(null);
    const unregister = useCanvasInteractionStore.getState().register({
      sessionId,
      /** Read the latest document, including nodes added before the next render. */
      placement: () => {
        const state = useAgentBuilderDocumentStore.getState();
        const visible = geometry();
        if (state.sessionId !== sessionId || !state.document || !visible) return null;
        const measured = new Map(getNodes().map((node) => [node.id, node.measured]));
        return visiblePlacement(visible, { width: 220, height: 160 },
          Object.entries(state.document.presentation.nodes).map(([id, position]) => ({
            x: position.x, y: position.y,
            width: measured.get(id)?.width ?? 220, height: measured.get(id)?.height ?? 160,
          })));
      },
      /** Reveal synchronously without a timer or a persisted camera mutation. */
      reveal: (canvasId) => {
        const state = useAgentBuilderDocumentStore.getState();
        const relation = state.document?.relations.find((item) => item.canvasId === canvasId);
        const objects = state.document ? [state.document.input, ...state.document.capabilities, state.document.output] : [];
        // A relation focuses its target endpoint; this remains object-level,
        // not a claim that the entire potentially off-screen edge is visible.
        const targetId = relation ? objects.find((item) => item.logicalId === relation.target.ownerId)?.canvasId : canvasId;
        const position = targetId ? state.document?.presentation.nodes[targetId] : undefined;
        const visible = geometry();
        if (state.sessionId !== sessionId || !position || !visible) return;
        const node = getNodes().find((item) => item.id === targetId);
        // Newly added nodes are estimated once, then corrected after XYFlow has
        // measured them. The request belongs to this session, never a timer.
        pendingReveal.current = node?.measured?.width && node.measured.height
          ? null : { sessionId, canvasId };
        const width = node?.measured?.width ?? 220;
        const height = node?.measured?.height ?? 160;
        const dx = position.x < visible.x ? visible.x - position.x
          : position.x + width > visible.x + visible.width ? visible.x + Math.max(0, visible.width - width) - position.x : 0;
        const dy = position.y < visible.y ? visible.y - position.y
          : position.y + height > visible.y + visible.height ? visible.y + Math.max(0, visible.height - height) - position.y : 0;
        if (!dx && !dy) return;
        userCameraCommand.current = false;
        const current = getViewport();
        // Zero-duration commands have no delayed animation able to steal a later
        // gesture or session; XYFlow reports programmatic movement with null event.
        void moveCamera({ ...current, x: current.x + dx * current.zoom, y: current.y + dy * current.zoom }, { duration: 0 });
      },
    });
    return () => {
      userCameraCommand.current = false;
      pendingReveal.current = null;
      setDraggingCanvasId(null);
      unregister();
    };
  }, [getNodes, getViewport, moveCamera, screenToFlowPosition, sessionId]);
  useEffect(() => {
    const pending = pendingReveal.current;
    if (!pending || !nodesInitialized) return;
    pendingReveal.current = null;
    const port = useCanvasInteractionStore.getState().port;
    if (pending.sessionId === sessionId && port?.sessionId === sessionId) port.reveal(pending.canvasId);
  }, [nodesInitialized, root, sessionId]);
  const flow = useMemo(() => {
    if (!document) return { nodes: [], edges: [] };
    const projected = documentToFlow(
      document,
      catalog,
      compileResult?.diagnostics ?? [],
      compileResult?.sourceMap ?? [],
    );
    const candidateHandles = connectionCandidateHandleIds({ document, catalog, nodes: projected.nodes, focus: connectionFocus });
    return {
      nodes: projected.nodes.map((node) => {
        const endpoint = relationEndpointFocus(document, node.id, selectedEdgeId);
        return {
          ...node,
          selected: node.id === selectedCanvasId,
          data: {
          ...node.data,
          connectionFocus: Boolean(connectionFocus),
          connectionHandleId: connectionFocus?.handleId,
          connectionCandidateHandles: candidateHandles,
          ...(endpoint
            ? {
                relationEndpoint: endpoint.role,
                relationPortId: endpoint.portId,
              }
            : { relationEndpoint: undefined, relationPortId: undefined }),
          },
        };
      }),
      edges: projected.edges.map((edge) => ({
        ...edge,
        selected: edge.id === selectedEdgeId,
        style: { opacity: edge.data?.diagnosticCount ? 1 : selectedEdgeId
          ? edge.id === selectedEdgeId ? 1 : 0.22
          : selectedCanvasId && edge.source !== selectedCanvasId && edge.target !== selectedCanvasId ? 0.22 : 1 },
        markerEnd: { type: MarkerType.ArrowClosed, color: edge.data?.kind === "feedback" ? "var(--zx-primary)" : "var(--zx-text-muted)" },
      })),
    };
  }, [catalog, compileResult, connectionFocus, document, selectedCanvasId, selectedEdgeId, uiLocale]);
  const canvasNodes = useCanvasNodes(flow.nodes);

  /** Frame measured cards and return lanes with headroom for the panel controls.
   * Returns: Nothing; only the display viewport changes, never node positions.
   */
  const fitCanvas = useCallback(() => {
    const nodes = getNodes();
    if (!nodes.length) return;
    const returns = visibleDocument()?.relations.filter((relation) => relation.kind === "feedback").length ?? 0;
    const sideMargin = returns ? 50 + Math.max(0, returns - 1) * 12 : 40;
    const x = Math.min(...nodes.map((node) => node.position.x)) - sideMargin;
    const y = Math.min(...nodes.map((node) => node.position.y)) - 100;
    const right = Math.max(...nodes.map((node) => node.position.x + (node.measured?.width ?? 250))) + sideMargin;
    const bottom = Math.max(...nodes.map((node) => node.position.y + (node.measured?.height ?? 200)));
    void fitBounds({ x, y, width: right - x, height: bottom - y + (returns ? 64 + returns * 36 : 0) },
      { duration: 0, padding: 0.12 });
  }, [fitBounds, getNodes]);
  useEffect(() => {
    if (!pendingFit.current) return;
    pendingFit.current = false;
    fitCanvas();
  }, [fitCanvas, flow, canvasWidth, canvasHeight]);

  /** Cancel both click and drag connection state without editing the graph. */
  const cancelConnection = useCallback(() => {
    flowStore.getState().cancelConnection();
    flowStore.setState({ connectionClickStartHandle: null });
    clickStart.current = undefined;
    setConnectionFocus(null);
  }, [flowStore]);

  /** Arrange the current graph without changing its semantic nodes or relations. */
  const onAutoLayout = useCallback(() => {
    const current = visibleDocument();
    if (!current) return;
    const dimensions = Object.fromEntries(getNodes().map((node) => [node.id, {
      width: Math.max(node.measured?.width ?? 0, node.data.kind === "capability" ? 250 : 100),
      height: Math.max(node.measured?.height ?? 0, node.data.kind === "capability"
        ? 110 + 30 * Math.max(node.data.ports.filter((port: { direction: string }) => port.direction === "input").length,
          node.data.ports.filter((port: { direction: string }) => port.direction === "output").length) : 50),
    }]));
    const positions = autoLayoutPositions(current, dimensions);
    const changed = Object.entries(positions).some(([canvasId, position]) => {
      const previous = current.presentation.nodes[canvasId];
      return previous?.x !== position.x || previous?.y !== position.y;
    });
    if (!changed) return;
    pendingFit.current = true;
    setNodePositions(positions);
  }, [getNodes, setNodePositions]);

  const validate = useCallback(
    (connection: Connection, ignoreEdgeId?: string, requestedKind: BuilderConnectionKind = connectionKind) => {
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
        return { ok: false as const, reason: uiText("连线端点不完整") };
      }
      return validateBuilderConnection({
        document: current,
        catalog,
        sourceCanvasId: connection.source,
        sourcePortId,
        targetCanvasId: connection.target,
        targetPortId,
        ignoreEdgeId,
        requestedKind,
      });
    },
    [catalog, connectionKind],
  );

  /** Explain rejected drag/click/reconnect attempts without creating a relation.
   * Args: event/state identify ports; ignoreEdgeId excludes a moved edge; clicked supplies a click-only start.
   * Returns: Nothing; dropping on empty canvas quietly cancels the gesture.
   */
  const explainConnectionEnd = useCallback((event: MouseEvent | TouchEvent, state: FinalConnectionState, ignoreEdgeId?: string, clicked?: AttemptHandle, requestedKind: BuilderConnectionKind = connectionKind) => {
    if (state.isValid) return;
    const attempt = endedConnection(event, state, clicked);
    if (!attempt) return;
    const reason = typeof attempt === "string" ? attempt : (() => {
      const result = validate(attempt, ignoreEdgeId, requestedKind);
      return result.ok ? null : result.reason;
    })();
    if (reason) pushToast({ message: uiMessage`无法连接：${reason}`, tone: "warning", durationMs: 6500 });
  }, [connectionKind, pushToast, validate]);

  /** Commit one validated typed relation and end any successful click attempt. */
  const onConnect = useCallback(
    (connection: Connection) => {
      const current = visibleDocument();
      const result = validate(connection, undefined, connectionKind);
      if (!current || !result.ok || !connection.source || !connection.target) {
        pushToast({
          message: result.ok ? uiText("连线端点不完整") : result.reason,
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
        ...(result.kind === "feedback" ? { feedback: defaultFeedbackPolicy() } : {}),
      };
      addEdge(edge);
      clickStart.current = undefined;
      setConnectionFocus(null);
    },
    [addEdge, connectionKind, pushToast, validate],
  );

  /** Replace endpoints only after validating against all other existing relations. */
  const onReconnect = useCallback(
    (oldEdge: { id: string }, connection: Connection) => {
      const current = visibleDocument();
      const previous = current?.relations.find((relation) => relation.canvasId === oldEdge.id);
      const requestedKind: BuilderConnectionKind = previous?.kind === "feedback" ? "feedback" : "ordinary";
      const result = validate(connection, oldEdge.id, requestedKind);
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
          message: result.ok ? uiText("连线端点不完整") : result.reason,
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
        feedback: result.kind === "feedback" ? edge.feedback ?? defaultFeedbackPolicy() : undefined,
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
        pushToast({ message: cause instanceof Error ? cause.message : uiText("能力当前不可用"), tone: "warning" });
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

  const candidateCount = flow.nodes[0]?.data.connectionCandidateHandles?.length ?? 0;

  if (!document) return <div className={styles.emptyState}>{uiText("正在加载 Agent document…")}</div>;

  return (
    <main
      ref={canvas}
      className={`${styles.canvas} ${expandedSession === sessionId ? styles.expandedCanvas : ""} ${draggingCanvasId ? styles.canvasDragging : ""}`}
      data-dragging-node={draggingCanvasId ?? undefined}
      aria-label={uiText("AgentGraph 画布")}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          if (!connectionFocus) setExpandedSession(null);
          cancelConnection();
        }
      }}
      onClickCapture={(event) => {
        // Explicit toolbar camera commands also produce null XYFlow events.
        if ((event.target as Element).closest(".react-flow__controls")) {
          pendingReveal.current = null;
          userCameraCommand.current = true;
        }
      }}>
      <div className={styles.canvasActions}>
        <button type="button" className={styles.button} onClick={fitCanvas}>{uiText("显示全图")}</button>
        <details className={styles.canvasTools}>
          <summary className={styles.button}>{uiText("画布工具")}</summary>
          <div className={styles.canvasToolsMenu}>
        <button type="button" className={styles.button} onClick={() => void zoomTo(1, { duration: 0 })} title={uiText("恢复实际字号；拖动空白处平移画布")}>100%</button>
        <button type="button" className={styles.button} onClick={onAutoLayout} title={uiText("按输入 → 主流程 → 输出整理节点；反馈回路走外围")}>
          {uiText("自动整理")}</button>
        <button type="button" className={`${styles.button} ${styles.expandCanvasButton}`}
          aria-pressed={expandedSession === sessionId}
          onClick={() => { pendingFit.current = true; setExpandedSession(expandedSession === sessionId ? null : sessionId); }}>
          {expandedSession === sessionId ? uiText("退出专注") : uiText("专注画布")}
        </button>
          </div>
        </details>
      </div>
      {!connectionFocus ? null : (
        <div className={`${styles.connectionHint} nodrag nopan`} aria-label={uiText("本次连线")}>
          <strong>{flow.nodes.find((node) => node.id === connectionFocus.nodeId)?.data.label} · {portLabel(portIdFromHandle(connectionFocus.handleId) ?? "")}</strong>
          {!connectionFocus.ignoreEdgeId ? (
            <div role="group" aria-label={uiText("本次连线类型")} className={styles.connectionChoices}>
              <button type="button" className={`${styles.modeButton} ${connectionKind === "ordinary" ? styles.activeModeButton : ""}`}
                aria-pressed={connectionKind === "ordinary"}
                onClick={() => setConnectionFocus((focus) => focus ? { ...focus, kind: "ordinary" } : null)}>{uiText("普通连接")}</button>
              <button type="button" className={`${styles.modeButton} ${connectionKind === "feedback" ? styles.activeModeButton : ""}`}
                aria-pressed={connectionKind === "feedback"}
                onClick={() => setConnectionFocus((focus) => focus ? { ...focus, kind: "feedback" } : null)}>{uiText("↻ 下一轮反馈")}</button>
            </div>
          ) : <span>{uiText("正在重连：保留")}{connectionKind === "feedback" ? uiText("下一轮反馈") : uiText("普通连接")}{uiText("类型")}</span>}
          <span>{connectionKind === "feedback" ? uiText("满足条件时，把结果送回前面的节点，开始下一轮。") : uiText("将输出传给目标输入。创建反馈请先点击圆点，再选择“下一轮反馈”。")}</span>
          <span role="status">{candidateCount > 0 ? uiMessage`有 ${candidateCount} 个可连接端口，点击高亮目标完成连接。` : connectionKind === "feedback" ? uiText("没有可反馈的目标：请先连好前向流程；已有相同反馈或类型不兼容的端口不会高亮。") : uiText("当前没有可连接端口。请检查目标类型或已有连接。")}</span>
          <button type="button" className={styles.modeButton} onClick={cancelConnection}>{uiText("取消连线（Esc）")}</button>
        </div>
      )}
      <BuilderGuide
        hasCapabilities={document.capabilities.length > 0}
        hasRelations={document.relations.length > 0}
        hasSelection={Boolean(selectedCanvasId || selectedEdgeId)}
        progress={builderGuideProgress(document)}
      />
      <div className={styles.canvasLegend} aria-label={uiText("画布图例")}>
        <span><i className={styles.legendNode} aria-hidden />{uiText("能力")}</span>
        <span><i className={styles.legendBoundary} aria-hidden />{uiText("边界")}</span>
        <span><i className={styles.legendLine} aria-hidden />{uiText("普通关系")}</span>
        <span><i className={`${styles.legendLine} ${styles.legendFeedback}`} aria-hidden />{uiText("↻ 反馈回路")}</span>
      </div>
      <ReactFlow
        key={`${document.documentId}:${sessionId}`}
        nodes={canvasNodes.nodes}
        onNodesChange={canvasNodes.onNodesChange}
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
        connectionLineStyle={{ stroke: connectionKind === "feedback" ? "var(--zx-primary)" : "var(--zx-text-muted)", strokeDasharray: connectionKind === "feedback" ? "7 5" : undefined }}
        onConnectStart={(_, params) => {
          if (clickStart.current) return;
          if (params.nodeId && params.handleId && params.handleType) {
            setConnectionFocus({ nodeId: params.nodeId, handleId: params.handleId, handleType: params.handleType, kind: reconnectingEdge.current ? (visibleDocument()?.relations.find((edge) => edge.canvasId === reconnectingEdge.current)?.kind === "feedback" ? "feedback" : "ordinary") : connectionKind, ignoreEdgeId: reconnectingEdge.current });
          }
        }}
        onConnectEnd={(event, state) => {
          if (clickStart.current) return;
          if (!reconnectingEdge.current) explainConnectionEnd(event, state, undefined, undefined);
          setConnectionFocus(null);
        }}
        onClickConnectStart={(_, params) => {
          if (params.nodeId && params.handleType) {
            clickStart.current = { nodeId: params.nodeId, id: params.handleId, type: params.handleType };
            if (params.handleId) setConnectionFocus({ nodeId: params.nodeId, handleId: params.handleId, handleType: params.handleType, kind: "ordinary" });
          }
        }}
        onClickConnectEnd={(event, state) => {
          const clicked = clickStart.current;
          clickStart.current = undefined;
          if (clicked) explainConnectionEnd(event, state, undefined, clicked);
          setConnectionFocus(null);
        }}
        onReconnectStart={(_, edge) => { reconnectingEdge.current = edge.id; }}
        onReconnectEnd={(event, edge, _handleType, state) => {
          const relation = visibleDocument()?.relations.find((item) => item.canvasId === edge.id);
          const requestedKind = relation?.kind === "feedback" ? "feedback" : "ordinary";
          explainConnectionEnd(event, state, edge.id, undefined, requestedKind);
          reconnectingEdge.current = undefined;
          setConnectionFocus(null);
        }}
        isValidConnection={(connection) =>
          validate({
            source: connection.source,
            target: connection.target,
            sourceHandle: connection.sourceHandle ?? null,
            targetHandle: connection.targetHandle ?? null,
          }, reconnectingEdge.current, reconnectingEdge.current
            ? (visibleDocument()?.relations.find((item) => item.canvasId === reconnectingEdge.current)?.kind === "feedback" ? "feedback" : "ordinary")
            : connectionKind).ok
        }
        onNodeDragStart={(_, node) => setDraggingCanvasId(node.id)}
        onNodeDragStop={(_, node, movedNodes) => {
          if (useAgentBuilderDocumentStore.getState().sessionId !== sessionId) return;
          setNodePositions(Object.fromEntries((movedNodes.length ? movedNodes : [node])
            .map((moved) => [moved.id, moved.position])));
          setDraggingCanvasId(null);
        }}
        onDelete={({ nodes, edges }) => removeElements(nodes.map((node) => node.id), edges.map((edge) => edge.id))}
        onNodeClick={(_, node) => selectNode(node.id)}
        onEdgeClick={(_, edge) => selectEdge(edge.id)}
        onPaneClick={() => {
          cancelConnection();
          selectNode(null);
          selectEdge(null);
        }}
        onMoveEnd={(event, viewport) => {
          if (event || userCameraCommand.current) setViewport(viewport.x, viewport.y, viewport.zoom);
          userCameraCommand.current = false;
        }}
        onMoveStart={(event) => { if (event) pendingReveal.current = null; }}
        defaultViewport={cameraViewport ?? document.presentation.viewport}
        minZoom={0.2}
        connectionRadius={28}
        maxZoom={2}
        deleteKeyCode={["Backspace", "Delete"]}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} color="var(--zx-grid-dot)" />
        <Controls showInteractive={false} showFitView={false} />
      </ReactFlow>
    </main>
  );
}
