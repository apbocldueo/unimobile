/** 槽位在 UI 上的中文名 / 英文名（与 modular 骨架 role 对齐）。图标由 `SlotGlyph` 统一渲染。 */
export const SLOT_META: Record<string, { labelZh: string; titleEn: string }> = {
  planner: { labelZh: "规划", titleEn: "Planner" },
  verifier: { labelZh: "校验", titleEn: "Verifier" },
  perception: { labelZh: "感知", titleEn: "Perception" },
  reasoning: { labelZh: "推理", titleEn: "Reasoning" },
  memory: { labelZh: "记忆", titleEn: "Memory" },
};

export function getSlotMeta(slotId: string) {
  return (
    SLOT_META[slotId] ?? {
      labelZh: slotId,
      titleEn: slotId,
    }
  );
}
