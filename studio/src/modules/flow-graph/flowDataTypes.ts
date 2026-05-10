/** 连线与端口的数据类型标识（与设计方案表格一致）。 */

export const WILDCARD_FLOW_TYPE = "__wild__" as const;

export type FlowDataType =
  | "taskInput"
  | "plan"
  | "screenshot"
  | "perceptionResult"
  | "memoryContext"
  | "action"
  | "verifiedPlan"
  | "condition"
  | typeof WILDCARD_FLOW_TYPE;

export const FLOW_TYPE_LABELS: Record<Exclude<FlowDataType, typeof WILDCARD_FLOW_TYPE>, string> = {
  taskInput: "任务输入",
  plan: "规划结果",
  screenshot: "屏幕截图",
  perceptionResult: "感知结果",
  memoryContext: "记忆上下文",
  action: "执行动作",
  verifiedPlan: "校验后规划",
  condition: "条件输入",
};

export const FLOW_TYPE_COLORS: Record<FlowDataType, string> = {
  taskInput: "#66ccff",
  plan: "#4096ff",
  screenshot: "#99ccff",
  perceptionResult: "#36d399",
  memoryContext: "#f6ad55",
  action: "#10b981",
  verifiedPlan: "#8b5cf6",
  condition: "#f87171",
  [WILDCARD_FLOW_TYPE]: "#a8b0c4",
};

export function formatTypesForTooltip(types: FlowDataType[]): string {
  return types
    .map((t) => (t === WILDCARD_FLOW_TYPE ? "任意" : FLOW_TYPE_LABELS[t] ?? t))
    .join("，");
}
