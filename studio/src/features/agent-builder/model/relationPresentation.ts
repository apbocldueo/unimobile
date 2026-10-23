import { uiText } from "@/shared/i18n";
import type { StudioFlowDocument, StudioCapabilityRelation } from "@/entities/agent-graph";

export type RelationEndpointRole = "source" | "target";
export type RelationEndpointFocus = {
  role: RelationEndpointRole;
  portId: string;
};

/** Resolve the selected relation's endpoint for one canvas node.
 * Args: document is the current Agent document; canvasId is the projected node identity; relationId is the selected edge identity.
 * Returns: The source/target role and rendered port ID when the node belongs to the selected relation, otherwise undefined.
 */
export function relationEndpointFocus(
  document: StudioFlowDocument,
  canvasId: string,
  relationId: string | null,
): RelationEndpointFocus | undefined {
  if (!relationId) return undefined;
  const relation = document.relations.find((item) => item.canvasId === relationId);
  if (!relation) return undefined;
  const objects = [document.input, ...document.capabilities, document.output];
  const source = objects.find((item) => item.logicalId === relation.source.ownerId);
  const target = objects.find((item) => item.logicalId === relation.target.ownerId);
  if (source?.canvasId === canvasId) return { role: "source", portId: relation.source.portId };
  if (target?.canvasId === canvasId) {
    return { role: "target", portId: relation.kind === "termination" ? "connection" : relation.target.portId };
  }
  return undefined;
}

/** Return a concise Chinese relation kind label for the relation inspector.
 * Args: kind is the persisted semantic relation kind.
 * Returns: A user-facing label that preserves the original kind in technical details.
 */
export function relationKindLabel(kind: StudioCapabilityRelation["kind"]): string {
  return {
    data: uiText("数据传递"),
    activation: uiText("触发执行"),
    feedback: uiText("下一轮反馈"),
    termination: uiText("结束连接"),
  }[kind];
}
