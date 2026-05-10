import { FlowStudioCardHeaderRow, FlowStudioPaletteShell } from "./FlowStudioPaletteShell";
import { memoryFlowCardDefinition } from "./memoryFlowCard.definition";
import { SlotRegistryAlgorithmSection } from "./SlotRegistryAlgorithmSection";
import type { FlowStudioPaletteCardProps } from "./types";

export function MemoryFlowCard(props: FlowStudioPaletteCardProps) {
  const d = memoryFlowCardDefinition;
  return (
    <FlowStudioPaletteShell {...props} portBlueprints={d.portBlueprints} widenInner>
      <FlowStudioCardHeaderRow data={props.data} />
      <SlotRegistryAlgorithmSection registrySlotId={d.registrySlotId!} data={props.data} />
    </FlowStudioPaletteShell>
  );
}
