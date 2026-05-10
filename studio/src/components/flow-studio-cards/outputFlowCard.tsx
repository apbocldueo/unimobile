import { FlowStudioCardHeaderRow, FlowStudioPaletteShell } from "./FlowStudioPaletteShell";
import { outputFlowCardDefinition } from "./outputFlowCard.definition";
import type { FlowStudioPaletteCardProps } from "./types";

export function OutputFlowCard(props: FlowStudioPaletteCardProps) {
  const d = outputFlowCardDefinition;
  return (
    <FlowStudioPaletteShell {...props} portBlueprints={d.portBlueprints}>
      <FlowStudioCardHeaderRow data={props.data} />
    </FlowStudioPaletteShell>
  );
}
