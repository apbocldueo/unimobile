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
  ports: BuilderPort[];
  unavailable: boolean;
  diagnosticSeverity?: "error" | "warning";
  diagnosticCount: number;
  renderMode: StudioNodeRenderMode;
  capabilityKind: "core" | "extension" | "boundary";
  [key: string]: unknown;
};

export type BuilderEdgeData = {
  kind: StudioCapabilityRelation["kind"];
  dataType: string;
  diagnosticSeverity?: "error" | "warning";
  diagnosticCount: number;
  semanticLabel?: string;
  [key: string]: unknown;
};

export type BuilderFlowNode = Node<BuilderNodeData, "agentBuilder">;
export type BuilderFlowEdge = Edge<BuilderEdgeData, "agentBuilder">;

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

/** Project only Input, Output and user capability instances into XYFlow. */
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
        ...(component ? { componentIdentifier: component.identifier } : {}),
        ports: portsForNode(node, catalog),
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
        ...(relation.kind === "feedback" ? { semanticLabel: "下一轮" } : {}),
      },
    }];
  });
  return { nodes: [...boundaryNodes, ...capabilityNodes], edges };
}

/** Validate a prospective typed capability relation against the exact Catalog. */
export function validateBuilderConnection(input: {
  document: StudioFlowDocument;
  catalog: ComponentCatalog | null | undefined;
  sourceCanvasId: string;
  sourcePortId: string;
  targetCanvasId: string;
  targetPortId: string;
  ignoreEdgeId?: string;
}): { ok: true; kind: StudioCapabilityRelation["kind"] } | { ok: false; reason: string } {
  if (!input.catalog) return { ok: false, reason: "Catalog 未加载，无法确认端口语义" };
  if (input.sourceCanvasId === input.targetCanvasId) return { ok: false, reason: "不能连接节点自身" };
  const sourceBoundary = input.document.input.canvasId === input.sourceCanvasId;
  const targetOutput = input.document.output.canvasId === input.targetCanvasId;
  const sourceNode = input.document.capabilities.find((item) => item.canvasId === input.sourceCanvasId);
  const targetNode = input.document.capabilities.find((item) => item.canvasId === input.targetCanvasId);
  if ((!sourceBoundary && !sourceNode) || (!targetOutput && !targetNode)) {
    return { ok: false, reason: "连线引用了未知或方向错误的对象" };
  }
  const sourcePort = sourceBoundary
    ? INPUT_PORTS.find((port) => port.id === input.sourcePortId)
    : portsForNode(sourceNode!, input.catalog).find(
        (port) => port.id === input.sourcePortId && port.direction === "output",
      );
  if (!sourcePort) return { ok: false, reason: "输出端口不正确" };
  if (targetOutput) {
    const descriptor = sourceNode ? componentForNode(sourceNode, input.catalog) : undefined;
    if (!descriptor?.termination) {
      return { ok: false, reason: "该能力没有声明可结束 Agent 的正式语义" };
    }
    return { ok: true, kind: "termination" };
  }
  const targetPort = portsForNode(targetNode!, input.catalog).find(
    (port) => port.id === input.targetPortId && port.direction === "input",
  );
  if (!targetPort) return { ok: false, reason: "输入端口不正确" };
  const compatible =
    sourcePort.dataTypes.includes("any") ||
    targetPort.dataTypes.includes("any") ||
    sourcePort.dataTypes.some((type) => targetPort.dataTypes.includes(type));
  if (!compatible) {
    return { ok: false, reason: `类型不兼容：${sourcePort.dataTypes.join("|")} → ${targetPort.dataTypes.join("|")}` };
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
  ) return { ok: false, reason: "该输入端口只允许一条连线" };
  const kind = sourcePort.dataTypes.includes("control") && targetPort.dataTypes.includes("control")
    ? "activation"
    : "data";
  return { ok: true, kind };
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
