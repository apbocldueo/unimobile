import { uiMessage, uiText } from "@/shared/i18n";
import type {
  ComponentCatalog,
  ComponentCatalogItem,
  ContractPort,
} from "@/entities/component-catalog";
import {
  canvasSafeText,
  type StudioCapabilityNode,
  type StudioCapabilityRelation,
  type StudioDiagnostic,
  type StudioFlowDocument,
  type StudioNodeRenderMode,
  type StudioSourceMapEntry,
} from "@/entities/agent-graph";
import type { Edge, Node, XYPosition } from "@xyflow/react";

export const BUILDER_DRAG_MIME = "application/x-zhixing-studio-capability";

export type BuilderPort = ContractPort;
export type BuilderNodeData = {
  label: string;
  description: string;
  kind: "input" | "output" | "capability";
  family?: StudioCapabilityNode["family"];
  componentIdentifier?: string;
  implementationLabel?: string;
  implementationCount?: number;
  ports: BuilderPort[];
  unavailable: boolean;
  diagnosticSeverity?: "error" | "warning";
  diagnosticCount: number;
  renderMode: StudioNodeRenderMode;
  capabilityKind: "core" | "extension" | "boundary";
  connectionFocus?: boolean;
  connectionHandleId?: string;
  connectionCandidateHandles?: string[];
  relationEndpoint?: "source" | "target";
  relationPortId?: string;
  connectedPortIds?: string[];
  [key: string]: unknown;
};

export type BuilderEdgeData = {
  kind: StudioCapabilityRelation["kind"];
  dataType: string;
  diagnosticSeverity?: "error" | "warning";
  diagnosticCount: number;
  semanticLabel?: string;
  feedbackMaxIterations?: number;
  returnLane?: number;
  [key: string]: unknown;
};

export type BuilderFlowNode = Node<BuilderNodeData, "agentBuilder">;
export type BuilderFlowEdge = Edge<BuilderEdgeData, "agentBuilder">;
export type BuilderConnectionKind = "ordinary" | "feedback";

/** Return the conservative feedback policy used for a newly authored edge. */
export function defaultFeedbackPolicy(): NonNullable<StudioCapabilityRelation["feedback"]> {
  return {
    predicate: { field: "terminal_status", operator: "falsy" },
    maxIterations: 3,
    onExhausted: "fail",
  };
}

const INPUT_PORTS: ContractPort[] = [
  { id: "task", direction: "output", dataTypes: ["task_input"], required: false, cardinality: "multiple" },
];
const OUTPUT_PORTS: ContractPort[] = [
  { id: "connection", direction: "input", dataTypes: ["any"], required: false, cardinality: "multiple" },
];
const CORE_FAMILIES = new Set([
  "perception", "planner", "reasoning", "memory", "action_executor", "verifier",
]);

/** Derive a stable XYFlow handle identity from an authoring object and port. */
export function handleId(
  canvasId: string,
  direction: "input" | "output",
  portId: string,
): string {
  return `${canvasId}:${direction}:${portId}`;
}

/** Recover the exact semantic port ID from a deterministic handle identity. */
export function portIdFromHandle(handle: string | null | undefined): string | null {
  if (!handle) return null;
  const parts = handle.split(":");
  return parts.length >= 3 ? parts[parts.length - 1]! : null;
}

/** Resolve the exact Catalog descriptor selected by one capability instance. */
export function componentForNode(
  node: StudioCapabilityNode,
  catalog: ComponentCatalog | null | undefined,
): ComponentCatalogItem | undefined {
  const candidate = node.implementation.candidates[0];
  return catalog?.components.find(
    (item) =>
      item.namespace === candidate?.namespace &&
      item.name === candidate?.name &&
      item.version === candidate?.version,
  );
}

/** Resolve formal visible ports for one capability instance. */
export function portsForNode(
  node: StudioCapabilityNode,
  catalog: ComponentCatalog | null | undefined,
): BuilderPort[] {
  return componentForNode(node, catalog)?.contract.ports ?? [];
}

function diagnosticSummary(
  diagnostics: StudioDiagnostic[],
  sourceMap: StudioSourceMapEntry[],
  canvasId: string,
  relation: boolean,
): { severity?: "error" | "warning"; count: number } {
  const sourceIds = new Set(
    sourceMap
      .filter((item) =>
        relation ? item.canvasEdgeId === canvasId : item.canvasNodeId === canvasId,
      )
      .flatMap((item) => (item.sourceId ? [item.sourceId] : [])),
  );
  const matching = diagnostics.filter(
    (item) =>
      item.sourceId?.includes(`${relation ? "relation" : "capability"}:${canvasId}`) ||
      (item.sourceId !== undefined && sourceIds.has(item.sourceId)),
  );
  if (matching.some((item) => item.severity === "error")) return { severity: "error", count: matching.length };
  if (matching.some((item) => item.severity === "warning")) return { severity: "warning", count: matching.length };
  return { count: 0 };
}

/** Project only Input, Output and user capability instances into XYFlow.
 * Args: document owns semantics; catalog, diagnostics and sourceMap supply display facts.
 * Returns: Canvas nodes with safe implementation summaries and edges with exact connection identities.
 */
export function documentToFlow(
  document: StudioFlowDocument,
  catalog: ComponentCatalog | null | undefined,
  diagnostics: StudioDiagnostic[] = [],
  sourceMap: StudioSourceMapEntry[] = [],
): { nodes: BuilderFlowNode[]; edges: BuilderFlowEdge[] } {
  const boundaries = [document.input, document.output] as const;
  const boundaryNodes: BuilderFlowNode[] = boundaries.map((boundary) => {
    const presentation = document.presentation.nodes[boundary.canvasId] ?? { x: 0, y: 0 };
    const label = boundary.kind === "input" ? "Input" : "Output";
    const diagnostic = diagnosticSummary(diagnostics, sourceMap, boundary.canvasId, false);
    return {
      id: boundary.canvasId,
      type: "agentBuilder",
      position: { x: presentation.x, y: presentation.y },
      data: {
        label,
        description:
          boundary.kind === "input"
            ? "Agent task enters here"
            : "A connected capability may end the Agent here",
        kind: boundary.kind,
        ports: boundary.kind === "input" ? INPUT_PORTS : OUTPUT_PORTS,
        unavailable: false,
        ...(diagnostic.severity ? { diagnosticSeverity: diagnostic.severity } : {}),
        diagnosticCount: diagnostic.count,
        renderMode: "boundary",
        capabilityKind: "boundary",
      },
    };
  });
  const capabilityNodes: BuilderFlowNode[] = document.capabilities.map((node) => {
    const presentation = document.presentation.nodes[node.canvasId] ?? { x: 0, y: 0 };
    const component = componentForNode(node, catalog);
    const diagnostic = diagnosticSummary(diagnostics, sourceMap, node.canvasId, false);
    const fallback = node.family.replaceAll("_", " ");
    return {
      id: node.canvasId,
      type: "agentBuilder",
      position: { x: presentation.x, y: presentation.y },
      data: {
        label: canvasSafeText(presentation.label, fallback),
        description: canvasSafeText(
          presentation.description,
          component?.identifier ?? `${node.family} capability`,
        ),
        kind: "capability",
        family: node.family,
        ...(component ? { componentIdentifier: component.identifier, implementationLabel: canvasSafeText(component.display.label, component.identifier) } : {}),
        implementationCount: node.implementation.candidates.length,
        ports: portsForNode(node, catalog),
        connectedPortIds: document.relations.flatMap((relation) => [
          ...(relation.source.ownerId === node.logicalId ? [relation.source.portId] : []),
          ...(relation.target.ownerId === node.logicalId ? [relation.target.portId] : []),
        ]),
        unavailable:
          !component ||
          component.placement !== "agent_capability" ||
          component.capabilityFamily !== node.family ||
          !component.availability.available,
        ...(diagnostic.severity ? { diagnosticSeverity: diagnostic.severity } : {}),
        diagnosticCount: diagnostic.count,
        renderMode: "card",
        capabilityKind: CORE_FAMILIES.has(node.family) ? "core" : "extension",
      },
    };
  });
  const objects = [document.input, document.output, ...document.capabilities];
  const canvasByLogical = new Map(objects.map((item) => [item.logicalId, item.canvasId]));
  const nodeByLogical = new Map(document.capabilities.map((item) => [item.logicalId, item]));
  const returnLanes = new Map(document.relations.filter((relation) => relation.kind === "feedback")
    .map((relation) => relation.canvasId).sort().map((id, index) => [id, index]));
  const edges: BuilderFlowEdge[] = document.relations.flatMap((relation) => {
    const sourceCanvas = canvasByLogical.get(relation.source.ownerId);
    const targetCanvas = canvasByLogical.get(relation.target.ownerId);
    if (!sourceCanvas || !targetCanvas) return [];
    const sourceNode = nodeByLogical.get(relation.source.ownerId);
    const sourcePort = sourceNode
      ? portsForNode(sourceNode, catalog).find((item) => item.id === relation.source.portId)
      : INPUT_PORTS.find((item) => item.id === relation.source.portId);
    const diagnostic = diagnosticSummary(diagnostics, sourceMap, relation.canvasId, true);
    const targetPort = relation.kind === "termination" ? "connection" : relation.target.portId;
    return [{
      id: relation.canvasId,
      type: "agentBuilder" as const,
      source: sourceCanvas,
      sourceHandle: handleId(sourceCanvas, "output", relation.source.portId),
      target: targetCanvas,
      targetHandle: handleId(targetCanvas, "input", targetPort),
      data: {
        kind: relation.kind,
        dataType: sourcePort?.dataTypes[0] ?? "unknown",
        ...(diagnostic.severity ? { diagnosticSeverity: diagnostic.severity } : {}),
        diagnosticCount: diagnostic.count,
        ...(relation.kind === "feedback" ? { semanticLabel: uiText("下一轮反馈"), feedbackMaxIterations: relation.feedback?.maxIterations, returnLane: returnLanes.get(relation.canvasId) } : {}),
      },
    }];
  });
  return { nodes: [...boundaryNodes, ...capabilityNodes], edges };
}

/** Validate a prospective typed capability relation against the exact Catalog.
 * Args: input contains current document/Catalog and endpoint identities; ignoreEdgeId excludes a reconnection's old relation.
 * Returns: The permitted relation kind or a safe user-facing rejection reason.
 */
export function validateBuilderConnection(input: {
  document: StudioFlowDocument;
  catalog: ComponentCatalog | null | undefined;
  sourceCanvasId: string;
  sourcePortId: string;
  targetCanvasId: string;
  targetPortId: string;
  ignoreEdgeId?: string;
  requestedKind?: BuilderConnectionKind;
}): { ok: true; kind: StudioCapabilityRelation["kind"] } | { ok: false; reason: string } {
  if (!input.catalog) return { ok: false, reason: uiText("Catalog 未加载，无法确认端口语义") };
  if (input.sourceCanvasId === input.targetCanvasId) return { ok: false, reason: uiText("不能连接节点自身") };
  const sourceBoundary = input.document.input.canvasId === input.sourceCanvasId;
  const targetOutput = input.document.output.canvasId === input.targetCanvasId;
  const sourceNode = input.document.capabilities.find((item) => item.canvasId === input.sourceCanvasId);
  const targetNode = input.document.capabilities.find((item) => item.canvasId === input.targetCanvasId);
  if ((!sourceBoundary && !sourceNode) || (!targetOutput && !targetNode)) {
    return { ok: false, reason: uiText("连线引用了未知或方向错误的对象") };
  }
  if (input.requestedKind === "feedback" && (sourceBoundary || targetOutput)) {
    return { ok: false, reason: uiText("下一轮反馈只能连接两个能力节点，不能连接 Input 或 Output。") };
  }
  const sourcePort = sourceBoundary
    ? INPUT_PORTS.find((port) => port.id === input.sourcePortId)
    : portsForNode(sourceNode!, input.catalog).find(
        (port) => port.id === input.sourcePortId && port.direction === "output",
      );
  if (!sourcePort) return { ok: false, reason: uiText("输出端口不正确") };
  if (targetOutput) {
    const descriptor = sourceNode ? componentForNode(sourceNode, input.catalog) : undefined;
    if (!descriptor?.termination) {
      return { ok: false, reason: uiText("Reasoning 不能直接结束 Agent。请添加 Action Executor，将 Reasoning.action 连到它，再把 Action Executor.result 连到 Output。") };
    }
    return { ok: true, kind: "termination" };
  }
  const targetPort = portsForNode(targetNode!, input.catalog).find(
    (port) => port.id === input.targetPortId && port.direction === "input",
  );
  if (!targetPort) return { ok: false, reason: uiText("输入端口不正确") };
  const compatible =
    sourcePort.dataTypes.includes("any") ||
    targetPort.dataTypes.includes("any") ||
    sourcePort.dataTypes.some((type) => targetPort.dataTypes.includes(type));
  if (!compatible) {
    return { ok: false, reason: uiMessage`类型不兼容：${sourcePort.dataTypes.join("|")} → ${targetPort.dataTypes.join("|")}` };
  }
  if (input.requestedKind === "feedback") {
    if (!sourceNode || !targetNode) {
      return { ok: false, reason: uiText("下一轮反馈只能连接两个能力节点，不能连接 Input 或 Output。") };
    }
    if (input.document.relations.some(
      (relation) =>
        relation.canvasId !== input.ignoreEdgeId &&
        relation.kind === "feedback" &&
        relation.source.ownerId === sourceNode.logicalId &&
        relation.source.portId === input.sourcePortId &&
        relation.target.ownerId === targetNode.logicalId &&
        relation.target.portId === input.targetPortId,
    )) {
      return { ok: false, reason: uiText("这条下一轮反馈已经存在。") };
    }
    if (!hasOrdinaryReturnPath(input.document, targetNode.logicalId, sourceNode.logicalId, input.ignoreEdgeId)) {
      return {
        ok: false,
        reason: uiText("下一轮反馈需要目标节点能通过普通连线回到来源节点；请先搭好前向流程。"),
      };
    }
    return { ok: true, kind: "feedback" };
  }
  const targetLogical = targetNode!.logicalId;
  if (
    targetPort.cardinality === "single" &&
    input.document.relations.some(
      (relation) =>
        relation.canvasId !== input.ignoreEdgeId &&
        relation.target.ownerId === targetLogical &&
        relation.target.portId === input.targetPortId,
    )
  ) return { ok: false, reason: uiText("该输入端口已有连线。请先移除原连线，或改连其他输入端口。") };
  const kind = sourcePort.dataTypes.includes("control") && targetPort.dataTypes.includes("control")
    ? "activation"
    : "data";
  return { ok: true, kind };
}

/** Check the ordinary forward path required by one explicit feedback edge.
 * Args: document is the current authoring graph; start/end are logical capability IDs;
 * ignoreEdgeId excludes the relation being reconnected.
 * Returns: True when ordinary data/activation edges connect start to end.
 */
export function hasOrdinaryReturnPath(
  document: StudioFlowDocument,
  start: string,
  end: string,
  ignoreEdgeId?: string,
): boolean {
  const adjacency = new Map<string, string[]>();
  for (const relation of document.relations) {
    if (relation.canvasId === ignoreEdgeId || !["data", "activation"].includes(relation.kind)) continue;
    const targets = adjacency.get(relation.source.ownerId) ?? [];
    targets.push(relation.target.ownerId);
    adjacency.set(relation.source.ownerId, targets);
  }
  const queue = [start];
  const visited = new Set([start]);
  while (queue.length) {
    const current = queue.shift()!;
    if (current === end) return true;
    for (const next of adjacency.get(current) ?? []) {
      if (!visited.has(next)) {
        visited.add(next);
        queue.push(next);
      }
    }
  }
  return false;
}

/** Return a collision-free deterministic identity. */
export function nextStableId(prefix: string, existing: Iterable<string>): string {
  const occupied = new Set(existing);
  if (!occupied.has(prefix)) return prefix;
  let index = 2;
  while (occupied.has(`${prefix}_${index}`)) index += 1;
  return `${prefix}_${index}`;
}

/** Return a readable deterministic placement for one appended capability. */
export function nextNodePosition(count: number): XYPosition {
  return { x: 80 + (count % 3) * 300, y: 100 + Math.floor(count / 3) * 220 };
}
