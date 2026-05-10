import { FlowStudioCardHeaderRow, FlowStudioPaletteShell } from "./FlowStudioPaletteShell";
import { verifierFlowCardDefinition } from "./verifierFlowCard.definition";
import { SlotRegistryAlgorithmSection } from "./SlotRegistryAlgorithmSection";
import type { FlowStudioPaletteCardProps } from "./types";

export function VerifierFlowCard(props: FlowStudioPaletteCardProps) {
  const d = verifierFlowCardDefinition;
  return (
    <FlowStudioPaletteShell {...props} portBlueprints={d.portBlueprints} widenInner>
      <FlowStudioCardHeaderRow data={props.data} />
      <SlotRegistryAlgorithmSection registrySlotId={d.registrySlotId!} data={props.data} />
    </FlowStudioPaletteShell>
  );
}
