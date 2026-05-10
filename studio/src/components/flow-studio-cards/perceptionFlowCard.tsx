import { FlowStudioCardHeaderRow, FlowStudioPaletteShell } from "./FlowStudioPaletteShell";
import { perceptionFlowCardDefinition } from "./perceptionFlowCard.definition";
import { SlotRegistryAlgorithmSection } from "./SlotRegistryAlgorithmSection";
import type { FlowStudioPaletteCardProps } from "./types";

export function PerceptionFlowCard(props: FlowStudioPaletteCardProps) {
  const d = perceptionFlowCardDefinition;
  return (
    <FlowStudioPaletteShell {...props} portBlueprints={d.portBlueprints} widenInner>
      <FlowStudioCardHeaderRow data={props.data} />
      <SlotRegistryAlgorithmSection registrySlotId={d.registrySlotId!} data={props.data} />
    </FlowStudioPaletteShell>
  );
}
