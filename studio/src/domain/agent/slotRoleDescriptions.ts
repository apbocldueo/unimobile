/**
 * 槽位角色说明兜底：须与 ``zhixing/core/agent/interfaces.py`` 中各 Base* 的 ``_description`` 保持一字不差。
 * 正常情况由 ``GET /studio/builder/agent-registry`` 的 ``slots[].baseDescription`` 覆盖；仅当未拉取到注册表或字段缺失时使用，避免卡片空白。
 */
export const SLOT_ROLE_DESCRIPTION_FALLBACK: Record<string, string> = {
  planner: "The Planner: decomposing the user's high-level goal.",
  verifier: "The Quality Inspector: ensuring the correctness of the action.",
  perception: "The Eye of the agent: observing the agent's environment.",
  memory: "The Memory Hub: maintaining the agent's context and knowledge.",
  reasoning: "The Decision Core: making decisions based on the plan and the environment.",
};

export function getSlotRoleDescriptionFallback(slotId: string): string {
  return (SLOT_ROLE_DESCRIPTION_FALLBACK[slotId] ?? "").trim();
}
