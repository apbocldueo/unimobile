import { useCallback, useState } from "react";
import { applyNodeChanges, type NodeChange } from "@xyflow/react";
import type { BuilderFlowNode } from "./flowAdapter";

/** Own transient geometry for one projection, never semantic or undo state.
 * @param projection Authoritative nodes rebuilt after document/selection changes.
 * @returns Display nodes and a handler for XYFlow position/dimension feedback.
 */
export function useCanvasNodes(projection: BuilderFlowNode[]) {
  const [draft, setDraft] = useState({ owner: projection, nodes: projection });
  const nodes = draft.owner === projection ? draft.nodes : projection;
  const onNodesChange = useCallback((changes: NodeChange<BuilderFlowNode>[]) => {
    // Selection and deletion are explicit Builder commands, not geometry edits.
    const geometry = changes.filter((change) => change.type === "position" || change.type === "dimensions");
    if (!geometry.length) return;
    setDraft((previous) => ({ owner: projection, nodes: applyNodeChanges(geometry,
      previous.owner === projection ? previous.nodes : projection) }));
  }, [projection]);
  return { nodes, onNodesChange };
}
