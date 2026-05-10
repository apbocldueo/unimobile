import type { PortBlueprint } from "@/modules/flow-graph/flowPortBlueprint";
import { plannerFlowCardDefinition } from "./plannerFlowCard.definition";
import { verifierFlowCardDefinition } from "./verifierFlowCard.definition";
import { memoryFlowCardDefinition } from "./memoryFlowCard.definition";
import { reasoningFlowCardDefinition } from "./reasoningFlowCard.definition";
import { perceptionFlowCardDefinition } from "./perceptionFlowCard.definition";
import { actionFlowCardDefinition } from "./actionFlowCard.definition";
import { inputFlowCardDefinition } from "./inputFlowCard.definition";
import { outputFlowCardDefinition } from "./outputFlowCard.definition";
import { ifElseFlowCardDefinition } from "./ifElseFlowCard.definition";
import type { FlowComponentDef, FlowComponentGroup, FlowStudioCardDefinition } from "./types";

/** 侧栏顺序 + 端口 / 元数据单一来源（由各 `*.definition.ts` 组成）。 */
export const FLOW_STUDIO_CARD_DEFINITIONS: FlowStudioCardDefinition[] = [
  plannerFlowCardDefinition,
  verifierFlowCardDefinition,
  memoryFlowCardDefinition,
  reasoningFlowCardDefinition,
  perceptionFlowCardDefinition,
  actionFlowCardDefinition,
  inputFlowCardDefinition,
  outputFlowCardDefinition,
  ifElseFlowCardDefinition,
];

const DEF_BY_ID: Record<string, FlowStudioCardDefinition> = Object.fromEntries(
  FLOW_STUDIO_CARD_DEFINITIONS.map((d) => [d.id, d]),
);

export const FLOW_STUDIO_PORT_BLUEPRINTS_BY_ID: Record<string, PortBlueprint[]> = Object.fromEntries(
  FLOW_STUDIO_CARD_DEFINITIONS.map((d) => [d.id, d.portBlueprints]),
);

export function getFlowStudioCardDefinition(id: string): FlowStudioCardDefinition | undefined {
  return DEF_BY_ID[id];
}

export function getRegistrySlotIdForFlowStudioCard(componentId: string): string | undefined {
  return getFlowStudioCardDefinition(componentId)?.registrySlotId;
}

export const FLOW_NODE_GROUP_LABELS: Record<FlowComponentGroup, string> = {
  core: "核心组件",
  io: "输入输出组件",
  flow: "流程控制 (Flow Control)",
};

export const FLOW_COMPONENT_DRAG_MIME = "application/zhixing-studio-component-id";

function buildCatalog(): Record<FlowComponentGroup, FlowComponentDef[]> {
  const out: Record<FlowComponentGroup, FlowComponentDef[]> = { core: [], io: [], flow: [] };
  for (const d of FLOW_STUDIO_CARD_DEFINITIONS) {
    out[d.group].push({ id: d.id, label: d.label, desc: d.desc, icon: d.icon });
  }
  return out;
}

export const FLOW_NODE_CATALOG: Record<FlowComponentGroup, FlowComponentDef[]> = buildCatalog();
