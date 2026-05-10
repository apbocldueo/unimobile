import type { StudioAgentRegistryModularDTO } from "@/domain/agent/agentRegistryTypes";

export type SlotAlgorithmOption = { id: string; title: string };

/** 某槽位可选算法：仅来自 ZhiXing 注册表该槽对应命名空间（如 agent.verifier），不会混入 perception 插件。 */
export function getSlotAlgorithmOptions(
  slotId: string,
  modular: StudioAgentRegistryModularDTO | null | undefined,
): SlotAlgorithmOption[] {
  const list = modular?.pluginsBySlot?.[slotId];
  if (!list?.length) return [];
  return list.map((p) => ({
    id: p.id,
    title: p.title?.trim() || p.className || p.id,
  }));
}
