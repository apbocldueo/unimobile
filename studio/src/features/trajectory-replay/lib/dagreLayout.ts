import dagre from "@dagrejs/dagre";
import type { ReplayGraphEdge, ReplayGraphNode } from "@/entities/run";

export type ReplayNodePosition = {
  x: number;
  y: number;
};

/** Deterministically lay out a read-only graph without mutating semantic data. */
export function layoutReplayGraph(
  nodes: ReplayGraphNode[],
  edges: ReplayGraphEdge[],
): Record<string, ReplayNodePosition> {
  const graph = new dagre.graphlib.Graph({ multigraph: true });
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "TB",
    nodesep: 72,
    ranksep: 78,
    marginx: 32,
    marginy: 32,
  });
  for (const node of [...nodes].sort((left, right) => left.id.localeCompare(right.id))) {
    graph.setNode(node.id, { width: 188, height: 72 });
  }
  for (const edge of [...edges].sort((left, right) => left.id.localeCompare(right.id))) {
    graph.setEdge(edge.sourceNode, edge.targetNode, {}, edge.id);
  }
  dagre.layout(graph);
  return Object.fromEntries(
    [...nodes]
      .sort((left, right) => left.id.localeCompare(right.id))
      .map((node) => {
        const position = graph.node(node.id) as { x: number; y: number } | undefined;
        return [
          node.id,
          {
            x: Math.round((position?.x ?? 0) - 94),
            y: Math.round((position?.y ?? 0) - 36),
          },
        ];
      }),
  );
}
