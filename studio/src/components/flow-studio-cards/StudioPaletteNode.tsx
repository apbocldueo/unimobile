import type { FlowStudioPaletteCardProps, FlowStudioPaletteReactFlowNode } from "./types";
import { DefaultStudioPaletteFlowCard, STUDIO_PALETTE_CARD_COMPONENTS } from "./paletteRegistry";

export type StudioPaletteNode = FlowStudioPaletteReactFlowNode;

export function StudioPaletteNode(props: FlowStudioPaletteCardProps) {
  const Cmp = STUDIO_PALETTE_CARD_COMPONENTS[props.data.componentId] ?? DefaultStudioPaletteFlowCard;
  return <Cmp {...props} />;
}
