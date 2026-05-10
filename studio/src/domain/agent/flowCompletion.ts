import { getPluginParamGroups } from "@/domain/agent/pluginParamUi";
import type { BuilderStrategyId } from "@/domain/agent/builderStrategies";
import { getStrategySlotIds } from "@/domain/agent/strategyBlueprint";

type Assignment = { pluginId: string; pluginTitle: string };

/**
 * 未完成数：未选算法，或已选算法但该插件有可配置字段且用户尚未在卡片内编辑过参数。
 * @param slotIds 当前策略模板上的槽位 id 列表（与画布节点一致）。
 */
export function countIncompleteSlots(
  assignments: Record<string, Assignment>,
  slotParamsTouched: Record<string, boolean>,
  slotIds: string[],
): number {
  let incomplete = 0;
  for (const slotId of slotIds) {
    const a = assignments[slotId];
    if (!a) {
      incomplete++;
      continue;
    }
    const hasConfigurableFields = getPluginParamGroups(a.pluginId).some((g) => g.fields.length > 0);
    if (hasConfigurableFields && !slotParamsTouched[slotId]) incomplete++;
  }
  return incomplete;
}

export function countIncompleteForStrategy(
  assignments: Record<string, Assignment>,
  slotParamsTouched: Record<string, boolean>,
  strategyId: BuilderStrategyId,
): number {
  return countIncompleteSlots(assignments, slotParamsTouched, getStrategySlotIds(strategyId));
}
