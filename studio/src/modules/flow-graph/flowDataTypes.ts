/** 连线与端口的数据类型标识（与设计方案表格一致）。 */

export type FlowDataType =
  | "task_input"
  | "device_observation"
  | "plan_result"
  | "perception_result"
  | "memory_context"
  | "action"
  | "action_result"
  | "verifier_result"
  | "run_result"
  | "control";

export const FLOW_TYPE_LABELS: Record<FlowDataType, string> = {
  task_input: "任务输入",
  device_observation: "设备观察",
  plan_result: "规划结果",
  perception_result: "感知结果",
  memory_context: "记忆上下文",
  action: "执行动作",
  action_result: "动作结果",
  verifier_result: "校验结果",
  run_result: "运行结果",
  control: "控制流",
};

export const FLOW_TYPE_COLORS: Record<FlowDataType, string> = {
  task_input: "#66ccff",
  device_observation: "#99ccff",
  plan_result: "#4096ff",
  perception_result: "#36d399",
  memory_context: "#f6ad55",
  action: "#10b981",
  action_result: "#14b8a6",
  verifier_result: "#8b5cf6",
  run_result: "#0f766e",
  control: "#f87171",
};

export function formatTypesForTooltip(types: FlowDataType[]): string {
  return types
    .map((t) => FLOW_TYPE_LABELS[t] ?? t)
    .join("，");
}
