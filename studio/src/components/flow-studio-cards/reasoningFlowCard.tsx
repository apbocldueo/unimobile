import { FlowStudioCardHeaderRow, FlowStudioPaletteShell } from "./FlowStudioPaletteShell";
import { reasoningFlowCardDefinition } from "./reasoningFlowCard.definition";
import { SlotRegistryAlgorithmSection } from "./SlotRegistryAlgorithmSection";
import type { FlowStudioPaletteCardProps } from "./types";

export function ReasoningFlowCard(props: FlowStudioPaletteCardProps) {
  const d = reasoningFlowCardDefinition;
  return (
    <FlowStudioPaletteShell {...props} portBlueprints={d.portBlueprints} widenInner>
      <FlowStudioCardHeaderRow data={props.data} />
      <SlotRegistryAlgorithmSection registrySlotId={d.registrySlotId!} data={props.data} />
    </FlowStudioPaletteShell>
  );
}
