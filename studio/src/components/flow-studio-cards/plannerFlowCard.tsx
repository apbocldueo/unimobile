import { FlowStudioCardHeaderRow, FlowStudioPaletteShell } from "./FlowStudioPaletteShell";
import { plannerFlowCardDefinition } from "./plannerFlowCard.definition";
import { SlotRegistryAlgorithmSection } from "./SlotRegistryAlgorithmSection";
import type { FlowStudioPaletteCardProps } from "./types";

export function PlannerFlowCard(props: FlowStudioPaletteCardProps) {
  const d = plannerFlowCardDefinition;
  return (
    <FlowStudioPaletteShell {...props} portBlueprints={d.portBlueprints} widenInner>
      <FlowStudioCardHeaderRow data={props.data} />
      <SlotRegistryAlgorithmSection registrySlotId={d.registrySlotId!} data={props.data} />
    </FlowStudioPaletteShell>
  );
}
