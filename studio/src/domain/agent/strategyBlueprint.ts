import type { Edge, Node } from "@xyflow/react";
import type { BuilderStrategyId } from "@/domain/agent/builderStrategies";
import type { SlotNodeData } from "@/domain/agent/types";
import { compactInitialEdges, compactInitialNodes } from "@/domain/agent/templates/compactTemplate";
import {
  MODULAR_PLUGIN_SLOT_IDS,
  modularArchitectureEdges,
  modularArchitectureNodes,
} from "@/domain/agent/templates/modularArchitectureGraph";

export function getStrategyBlueprint(id: BuilderStrategyId): {
  nodes: Node[];
  edges: Edge[];
} {
  switch (id) {
    case "compact":
      return { nodes: compactInitialNodes as Node[], edges: compactInitialEdges };
    case "modular":
    default:
      /** 概念拓扑固定由前端维护；插件目录仍来自 ZhiXing ``agent-registry``。 */
      return {
        nodes: modularArchitectureNodes.map((n) => ({ ...n })),
        edges: modularArchitectureEdges.map((e) => ({ ...e })),
      };
  }
}

export function getStrategySlotIds(id: BuilderStrategyId): string[] {
  if (id === "modular") return [...MODULAR_PLUGIN_SLOT_IDS];
  return getStrategyBlueprint(id)
    .nodes.filter((n): n is Node<SlotNodeData, "slot"> => n.type === "slot")
    .map((n) => n.data.slotId);
}
