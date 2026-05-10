/** 画布内可切换的流程策略 id（与模板蓝图一一对应，可继续扩展）。 */
export const BUILDER_STRATEGY_IDS = ["modular", "compact"] as const;

export type BuilderStrategyId = (typeof BUILDER_STRATEGY_IDS)[number];

export const STRATEGY_LABELS: Record<BuilderStrategyId, string> = {
  modular: "Modular 策略",
  compact: "紧凑三槽（示例）",
};

/** 画布顶栏进度文案「当前策略：X」中的短名（与下拉选项区分展示） */
export const STRATEGY_PROGRESS_SHORT: Record<BuilderStrategyId, string> = {
  modular: "Modular",
  compact: "紧凑三槽",
};

/** 下拉展示用 */
export const STRATEGY_OPTIONS: { id: BuilderStrategyId; label: string; disabled?: boolean }[] = [
  { id: "modular", label: "Modular 策略" },
  { id: "compact", label: "紧凑三槽（示例）" },
];
