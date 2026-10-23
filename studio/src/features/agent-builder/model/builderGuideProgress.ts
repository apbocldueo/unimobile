import type { StudioFlowDocument } from "@/entities/agent-graph";

/** Describe the smallest mobile-agent topology in terms a Builder can explain. */
export type BuilderGuideProgress = {
  hasCapabilities: boolean;
  hasRelations: boolean;
  hasPerception: boolean;
  hasReasoning: boolean;
  hasMemory: boolean;
  hasActionExecutor: boolean;
  hasInputTask: boolean;
  hasInputMemory: boolean;
  hasMemoryToReasoning: boolean;
  hasPerceptionToReasoning: boolean;
  hasReasoningToAction: boolean;
  hasActionToOutput: boolean;
  hasActionFeedback: boolean;
};

/** Derive onboarding progress from exact authoring identities, never labels or messages. */
export function builderGuideProgress(document: StudioFlowDocument): BuilderGuideProgress {
  const families = new Set(document.capabilities.map((node) => node.family));
  const reasoning = document.capabilities.find((node) => node.family === "reasoning");
  const memory = document.capabilities.find((node) => node.family === "memory");
  const perception = document.capabilities.find((node) => node.family === "perception");
  const action = document.capabilities.find((node) => node.family === "action_executor");
  const hasRelation = (source: string, sourcePort: string, target: string, targetPort?: string) =>
    document.relations.some((relation) =>
      relation.kind !== "feedback" &&
      relation.source.ownerId === source &&
      relation.source.portId === sourcePort &&
      relation.target.ownerId === target &&
      (targetPort === undefined || relation.target.portId === targetPort),
    );
  return {
    hasCapabilities: document.capabilities.length > 0,
    hasRelations: document.relations.length > 0,
    hasPerception: families.has("perception"),
    hasReasoning: families.has("reasoning"),
    hasMemory: families.has("memory"),
    hasActionExecutor: families.has("action_executor"),
    hasInputTask: Boolean(reasoning && hasRelation(document.input.logicalId, "task", reasoning.logicalId, "task")),
    hasInputMemory: Boolean(memory && hasRelation(document.input.logicalId, "task", memory.logicalId, "write")),
    hasMemoryToReasoning: Boolean(memory && reasoning && hasRelation(memory.logicalId, "context", reasoning.logicalId, "memory")),
    hasPerceptionToReasoning: Boolean(
      reasoning && perception &&
      hasRelation(
        perception.logicalId,
        "perception",
        reasoning.logicalId,
        "perception",
      ),
    ),
    hasReasoningToAction: Boolean(
      reasoning && action && hasRelation(reasoning.logicalId, "action", action.logicalId, "action"),
    ),
    hasActionToOutput: Boolean(action && hasRelation(action.logicalId, "result", document.output.logicalId)),
    hasActionFeedback: Boolean(action && memory && document.relations.some((relation) =>
      relation.kind === "feedback" &&
      relation.source.ownerId === action.logicalId &&
      relation.source.portId === "result" &&
      relation.target.ownerId === memory.logicalId &&
      relation.target.portId === "write",
    )),
  };
}
