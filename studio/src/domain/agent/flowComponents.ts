import type { BuilderStrategyId } from "@/domain/agent/builderStrategies";

export type FlowComponentDef = {
  strategyId: BuilderStrategyId;
  /** 列表卡片标题，如「Modular 流程」 */
  title: string;
  /** 简介，UI 端最多展示三行并省略 */
  description: string;
  /** 为 false 时不参与列表（预留扩展） */
  enabled?: boolean;
};

export const FLOW_COMPONENT_CATALOG: FlowComponentDef[] = [
  {
    strategyId: "modular",
    title: "Modular 流程",
    description:
      "Modular 策略流程：包含感知、推理、记忆等 5 个核心组件，支持自定义算法配置。",
    enabled: true,
  },
  {
    strategyId: "compact",
    title: "紧凑三槽流程",
    description: "示例链路：感知、记忆、校验三节点，用于验证多策略下的画布与右栏联动。",
    enabled: true,
  },
];

export function getVisibleFlowComponents(): FlowComponentDef[] {
  return FLOW_COMPONENT_CATALOG.filter((c) => c.enabled !== false);
}
