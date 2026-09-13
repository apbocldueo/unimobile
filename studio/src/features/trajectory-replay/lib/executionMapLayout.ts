import dagre from "@dagrejs/dagre";
import type {
  ExecutionMapNode,
  ExecutionMapRelation,
} from "../model/executionMapPresenter";

export type ExecutionMapPosition = { x: number; y: number };

const NODE_WIDTH = 220;
const NODE_HEIGHT = 84;

/** Lay out a capability execution map top-to-bottom without feedback cycles. */
export function layoutExecutionMap(
  nodes: ExecutionMapNode[],
  relations: ExecutionMapRelation[],
): Record<string, ExecutionMapPosition> {
  const graph = new dagre.graphlib.Graph({ multigraph: true });
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "TB",
    nodesep: 48,
    ranksep: 58,
    marginx: 40,
    marginy: 44,
  });
  const orderedNodes = [...nodes].sort((left, right) => left.id.localeCompare(right.id));
  const nonFeedback = [...relations]
    .filter((relation) => relation.kind !== "feedback")
    .sort((left, right) => left.id.localeCompare(right.id));
  const nodeIds = new Set(orderedNodes.map((node) => node.id));
  for (const node of orderedNodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const relation of nonFeedback) {
    if (!nodeIds.has(relation.sourceNode) || !nodeIds.has(relation.targetNode)) continue;
    graph.setEdge(relation.sourceNode, relation.targetNode, {}, relation.id);
  }

  const input = orderedNodes.find((node) => node.kind === "input");
  const output = orderedNodes.find((node) => node.kind === "output");
  if (input) {
    const incoming = new Set(nonFeedback.map((relation) => relation.targetNode));
    for (const node of orderedNodes) {
      if (node.id === input.id || node.id === output?.id || incoming.has(node.id)) continue;
      graph.setEdge(input.id, node.id, {}, `layout:input:${node.id}`);
    }
  }
  if (output) {
    const outgoing = new Set(nonFeedback.map((relation) => relation.sourceNode));
    for (const node of orderedNodes) {
      if (node.id === output.id || node.id === input?.id || outgoing.has(node.id)) continue;
      graph.setEdge(node.id, output.id, {}, `layout:output:${node.id}`);
    }
  }

  dagre.layout(graph);
  return Object.fromEntries(orderedNodes.map((node) => {
    const position = graph.node(node.id) as { x: number; y: number } | undefined;
    return [node.id, {
      x: Math.round((position?.x ?? 0) - NODE_WIDTH / 2),
      y: Math.round((position?.y ?? 0) - NODE_HEIGHT / 2),
    }];
  }));
}
