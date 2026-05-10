import { FlowStudioCardHeaderRow, FlowStudioPaletteShell } from "./FlowStudioPaletteShell";
import { inputFlowCardDefinition } from "./inputFlowCard.definition";
import type { FlowStudioPaletteCardProps } from "./types";

export function InputFlowCard(props: FlowStudioPaletteCardProps) {
  const d = inputFlowCardDefinition;
  return (
    <FlowStudioPaletteShell {...props} portBlueprints={d.portBlueprints}>
      <FlowStudioCardHeaderRow data={props.data} />
    </FlowStudioPaletteShell>
  );
}
