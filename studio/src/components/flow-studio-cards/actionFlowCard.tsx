import { FlowStudioCardHeaderRow, FlowStudioPaletteShell } from "./FlowStudioPaletteShell";
import { actionFlowCardDefinition } from "./actionFlowCard.definition";
import type { FlowStudioPaletteCardProps } from "./types";

export function ActionFlowCard(props: FlowStudioPaletteCardProps) {
  const d = actionFlowCardDefinition;
  return (
    <FlowStudioPaletteShell {...props} portBlueprints={d.portBlueprints}>
      <FlowStudioCardHeaderRow data={props.data} />
    </FlowStudioPaletteShell>
  );
}
