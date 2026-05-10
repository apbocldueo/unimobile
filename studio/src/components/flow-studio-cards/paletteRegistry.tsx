import type { ComponentType } from "react";
import { ActionFlowCard } from "./actionFlowCard";
import { getFlowStudioCardDefinition } from "./blueprintIndex";
import { FlowStudioCardHeaderRow, FlowStudioPaletteShell } from "./FlowStudioPaletteShell";
import { InputFlowCard } from "./inputFlowCard";
import { MemoryFlowCard } from "./memoryFlowCard";
import { OutputFlowCard } from "./outputFlowCard";
import { PerceptionFlowCard } from "./perceptionFlowCard";
import { PlannerFlowCard } from "./plannerFlowCard";
import { ReasoningFlowCard } from "./reasoningFlowCard";
import type { FlowStudioPaletteCardProps } from "./types";
import { VerifierFlowCard } from "./verifierFlowCard";

/** `studioPalette` 节点：按 `componentId` 路由到对应卡片实现。 */
export const STUDIO_PALETTE_CARD_COMPONENTS: Record<string, ComponentType<FlowStudioPaletteCardProps>> = {
  planner: PlannerFlowCard,
  verifier: VerifierFlowCard,
  memory: MemoryFlowCard,
  reasoning: ReasoningFlowCard,
  perception: PerceptionFlowCard,
  action: ActionFlowCard,
  input: InputFlowCard,
  output: OutputFlowCard,
};

export function DefaultStudioPaletteFlowCard(props: FlowStudioPaletteCardProps) {
  const bp = getFlowStudioCardDefinition(props.data.componentId)?.portBlueprints ?? [];
  return (
    <FlowStudioPaletteShell {...props} portBlueprints={bp}>
      <FlowStudioCardHeaderRow data={props.data} />
    </FlowStudioPaletteShell>
  );
}
