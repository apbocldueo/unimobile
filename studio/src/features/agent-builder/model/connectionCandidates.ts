import type { ComponentCatalog } from "@/entities/component-catalog";
import type { StudioFlowDocument } from "@/entities/agent-graph";
import {
  handleId,
  portIdFromHandle,
  validateBuilderConnection,
  type BuilderConnectionKind,
  type BuilderFlowNode,
} from "./flowAdapter";

export type ConnectionFocus = {
  nodeId: string;
  handleId: string;
  handleType: "source" | "target";
  kind: BuilderConnectionKind;
  ignoreEdgeId?: string;
};

/** Find the exact handles that can complete an in-progress connection.
 * Args: document and catalog provide semantic graph constraints; nodes provide visible ports;
 * focus identifies the handle currently being dragged or click-selected.
 * Returns: Stable XYFlow handle IDs that should remain visually active.
 */
export function connectionCandidateHandleIds(input: {
  document: StudioFlowDocument;
  catalog: ComponentCatalog | null | undefined;
  nodes: BuilderFlowNode[];
  focus: ConnectionFocus | null;
}): string[] {
  const { document, catalog, nodes, focus } = input;
  if (!catalog || !focus) return [];
  const focusedPortId = portIdFromHandle(focus.handleId);
  if (!focusedPortId) return [];
  const candidates: string[] = [];
  for (const node of nodes) {
    if (node.id === focus.nodeId) continue;
    const ports = node.data.ports.filter((port) =>
      focus.handleType === "source" ? port.direction === "input" : port.direction === "output",
    );
    for (const port of ports) {
      const connection = focus.handleType === "source"
        ? {
            sourceCanvasId: focus.nodeId,
            sourcePortId: focusedPortId,
            targetCanvasId: node.id,
            targetPortId: port.id,
          }
        : {
            sourceCanvasId: node.id,
            sourcePortId: port.id,
            targetCanvasId: focus.nodeId,
            targetPortId: focusedPortId,
          };
      const result = validateBuilderConnection({
        document,
        catalog,
        ...connection,
        ignoreEdgeId: focus.ignoreEdgeId,
        requestedKind: focus.kind,
      });
      if (result.ok) {
        candidates.push(handleId(node.id, focus.handleType === "source" ? "input" : "output", port.id));
      }
    }
  }
  return candidates;
}
