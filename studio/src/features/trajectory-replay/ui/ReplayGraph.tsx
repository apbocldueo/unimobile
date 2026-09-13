import { useEffect, useMemo, useRef, useState } from "react";
import {
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import { canvasSafeText } from "@/entities/agent-graph";
import type { RunSnapshot } from "@/entities/run";
import { layoutReplayGraph } from "../lib/dagreLayout";
import { layoutExecutionMap } from "../lib/executionMapLayout";
import {
  presentRunExecutionMap,
  type ExecutionMapRelation,
  type ExecutionMapViewMode,
} from "../model/executionMapPresenter";
import type { ReplayProjection } from "../model/replayProjection";
import styles from "./trajectoryReplay.module.css";

type RunGraphProps = {
  snapshot: RunSnapshot;
  projection: ReplayProjection;
  displayActivationId?: string | null;
  selectedActivationId: string | null;
  failureActivationId?: string | null;
  onSelectActivation: (activationId: string | null) => void;
  ariaLabel?: string;
};

type ReplayNodeData = {
  label: string;
  role: string;
  status: string;
  count: number;
  feedbackCount: number;
  badges: string[];
  current: boolean;
  selected: boolean;
  failed: boolean;
  vertical: boolean;
};

const CARD_WIDTH = 220;
const CARD_HEIGHT = 84;

/** Return a quiet user-facing label for one formal relation kind. */
function relationLabel(kind: string): string {
  const labels: Record<string, string> = {
    data: "数据",
    activation: "触发",
    feedback: "回路",
    termination: "结束连接",
  };
  return labels[kind] ?? canvasSafeText(kind, "关系");
}

/** Return a non-color-only status phrase for one execution-map card. */
function nodeStateLabel(data: ReplayNodeData): string {
  if (data.failed) return "执行异常";
  if (data.current) return "当前执行";
  if (data.status === "success") return "已经过";
  if (data.status === "skipped") return "已跳过";
  return "等待";
}

/** Render one read-only execution-map card with four independent state axes. */
function ReplayNode({ data }: NodeProps<Node<ReplayNodeData>>) {
  const stateLabel = nodeStateLabel(data);
  return (
    <div
      className={`${styles.graphNode} ${styles[`node_${data.status}`] ?? ""} ${
        data.current ? styles.nodeCurrent : ""
      } ${data.selected ? styles.nodeSelected : ""} ${
        data.failed ? styles.nodeFailure : ""
      }`}
      data-current={data.current ? "true" : undefined}
      data-selected={data.selected ? "true" : undefined}
      data-failure={data.failed ? "true" : undefined}
      aria-label={`${data.label}，${stateLabel}`}
    >
      <Handle
        type="target"
        position={data.vertical ? Position.Top : Position.Left}
        isConnectable={false}
        className={styles.readOnlyHandle}
      />
      <div className={styles.nodeTopline}>
        <span>{canvasSafeText(data.role, "能力")}</span>
        <span className={styles.nodeState} data-state={data.failed ? "failure" : data.current ? "current" : "history"}>
          {data.failed ? "! " : data.selected ? "⌖ " : data.status === "success" ? "✓ " : ""}
          {stateLabel}
        </span>
      </div>
      <strong>{canvasSafeText(data.label, "Capability")}</strong>
      <div className={styles.nodeFacts}>
        {data.count > 1 ? <span>运行 ×{data.count}</span> : null}
        {data.feedbackCount > 0 ? <span>迭代 ×{data.feedbackCount}</span> : null}
      </div>
      {data.badges.length > 0 ? (
        <div className={styles.nodeBadges}>
          {data.badges.map((badge) => <span key={badge}>{canvasSafeText(badge)}</span>)}
        </div>
      ) : null}
      <Handle
        type="source"
        position={data.vertical ? Position.Bottom : Position.Right}
        isConnectable={false}
        className={styles.readOnlyHandle}
      />
    </div>
  );
}

const nodeTypes = { replay: ReplayNode };

/** Build an XYFlow edge while keeping the declared relation identity intact. */
function flowEdge(
  relation: ExecutionMapRelation,
  viewMode: ExecutionMapViewMode,
): Edge {
  const kindClass = styles[`edge_${relation.kind}`] ?? styles.edge_data;
  return {
    id: relation.id,
    source: relation.sourceNode,
    target: relation.targetNode,
    type: relation.kind === "feedback" ? "smoothstep" : "default",
    animated: false,
    label: viewMode === "relations" ? relationLabel(relation.kind) : undefined,
    markerEnd: { type: MarkerType.ArrowClosed, width: 13, height: 13 },
    className: `${styles.graphEdge} ${kindClass} ${relation.current ? styles.edgeCurrent : ""}`,
  };
}

/** Report whether the current card is outside the visible XYFlow pane. */
function currentCardIsOutside(
  shell: HTMLElement,
  flow: ReactFlowInstance<Node<ReplayNodeData>, Edge>,
  node: Node<ReplayNodeData>,
): boolean {
  const viewport = flow.getViewport();
  const padding = 30;
  const left = node.position.x * viewport.zoom + viewport.x;
  const top = node.position.y * viewport.zoom + viewport.y;
  const right = left + CARD_WIDTH * viewport.zoom;
  const bottom = top + CARD_HEIGHT * viewport.zoom;
  return left < padding
    || top < padding
    || right > shell.clientWidth - padding
    || bottom > shell.clientHeight - padding;
}

/** Render a snapshot-backed read-only execution map without changing factual projection. */
export function RunGraph({
  snapshot,
  projection,
  displayActivationId,
  selectedActivationId,
  failureActivationId,
  onSelectActivation,
  ariaLabel = "Replay AgentGraph",
}: RunGraphProps) {
  const [viewMode, setViewMode] = useState<ExecutionMapViewMode>("path");
  const [flow, setFlow] = useState<ReactFlowInstance<Node<ReplayNodeData>, Edge> | null>(null);
  const shellRef = useRef<HTMLElement | null>(null);
  const effectiveDisplayActivationId = displayActivationId === undefined
    ? projection.currentActivationId
    : displayActivationId;
  const model = useMemo(() => presentRunExecutionMap({
    snapshot,
    projection,
    displayActivationId: effectiveDisplayActivationId,
    selectedActivationId,
    failureActivationId,
    viewMode,
  }), [
    effectiveDisplayActivationId,
    failureActivationId,
    projection,
    selectedActivationId,
    snapshot,
    viewMode,
  ]);
  const graph = useMemo(() => {
    if (!model) return null;
    const positions = model.verticalFirst
      ? layoutExecutionMap(model.nodes, model.relations)
      : layoutReplayGraph(model.nodes, model.relations);
    const nodes: Node<ReplayNodeData>[] = model.nodes.map((node) => ({
      id: node.id,
      type: "replay",
      position: positions[node.id] ?? { x: 0, y: 0 },
      draggable: false,
      selectable: true,
      data: {
        label: node.label,
        role: node.role,
        status: node.aggregate.status,
        count: node.aggregate.executionCount,
        feedbackCount: node.aggregate.feedbackCount,
        badges: node.aggregate.badges,
        current: node.current,
        selected: node.selected,
        failed: node.failed,
        vertical: model.verticalFirst,
      },
    }));
    return {
      nodes,
      edges: model.visibleRelations.map((relation) => flowEdge(relation, viewMode)),
      aggregates: Object.fromEntries(model.nodes.map((node) => [node.id, node.aggregate])),
    };
  }, [model, viewMode]);

  const focusNode = (nodeId: string | null, duration = 220) => {
    if (!flow || !graph || !nodeId) return;
    const target = graph.nodes.find((node) => node.id === nodeId);
    if (!target) return;
    const reducedMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    void flow.setCenter(
      target.position.x + CARD_WIDTH / 2,
      target.position.y + CARD_HEIGHT / 2,
      {
        zoom: Math.max(0.82, flow.getViewport().zoom),
        duration: reducedMotion ? 0 : duration,
      },
    );
  };

  useEffect(() => {
    if (!flow || !graph || !model?.currentNodeId || !shellRef.current) return;
    const current = graph.nodes.find((node) => node.id === model.currentNodeId);
    if (!current || !currentCardIsOutside(shellRef.current, flow, current)) return;
    const reducedMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const viewport = flow.getViewport();
    void flow.setCenter(
      current.position.x + CARD_WIDTH / 2,
      current.position.y + CARD_HEIGHT / 2,
      {
        zoom: Math.max(0.72, viewport.zoom),
        duration: reducedMotion ? 0 : 220,
      },
    );
  }, [flow, graph, model?.currentNodeId]);

  if (snapshot.graphStatus === "corrupt") {
    return <GraphEmpty ariaLabel={ariaLabel} tone="error" title="graph_snapshot_corrupt" detail="Graph body 未通过完整性验证。" />;
  }
  if (model === null || graph === null) {
    const graphUnavailable = snapshot.graphStatus !== "available";
    return (
      <GraphEmpty
        tone="neutral"
        ariaLabel={ariaLabel}
        title={graphUnavailable ? "graph_snapshot_unavailable" : "capability_projection_unavailable"}
        detail={graphUnavailable
          ? `Graph evidence: ${snapshot.graphStatus}. 不会根据事件名称猜图。`
          : "Graph evidence is available, but its Studio capability mapping is not. 内部运行组件不会被猜测为用户能力。"}
      />
    );
  }
  return (
    <section ref={shellRef} className={`${styles.graphShell} studio-canvas-host`} aria-label={ariaLabel}>
      <div className={styles.graphMode}>
        <span>EXECUTION MAP</span>
        <strong>{model.currentNodeId ? "跟随当前执行" : "等待执行证据"}</strong>
      </div>
      {model.supportsRelationDisclosure ? (
        <div className={styles.graphViewControls} aria-label="执行图视图">
          <button
            type="button"
            disabled={!model.currentNodeId && !model.failureNodeId}
            onClick={() => focusNode(model.currentNodeId ?? model.failureNodeId)}
          >
            聚焦当前
          </button>
          <button
            type="button"
            data-active={viewMode === "path"}
            aria-pressed={viewMode === "path"}
            onClick={() => setViewMode("path")}
          >
            运行路径
          </button>
          <button
            type="button"
            data-active={viewMode === "relations"}
            aria-pressed={viewMode === "relations"}
            onClick={() => setViewMode("relations")}
          >
            关系全图
          </button>
        </div>
      ) : null}
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        fitView
        fitViewOptions={{ padding: 0.24, minZoom: 0.52, maxZoom: 1, duration: 0 }}
        onInit={setFlow}
        minZoom={0.42}
        maxZoom={1.8}
        onNodeClick={(_event, node) => {
          const aggregate = graph.aggregates[node.id];
          onSelectActivation(aggregate?.activationIds.at(-1) ?? null);
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
    </section>
  );
}

/** Render an explicit graph evidence state instead of a guessed topology. */
function GraphEmpty({
  ariaLabel,
  tone,
  title,
  detail,
}: {
  ariaLabel: string;
  tone: "neutral" | "error";
  title: string;
  detail: string;
}) {
  return (
    <div
      aria-label={ariaLabel}
      className={`${styles.graphEmpty} ${tone === "error" ? styles.graphError : ""}`}
    >
      <span>◇</span>
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

export const ReplayGraph = RunGraph;
