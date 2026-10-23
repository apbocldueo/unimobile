import { uiText } from "@/shared/i18n";
import type { BuilderPort } from "./flowAdapter";

const PORT_LABELS: Record<string, string> = {
  /** Read this static UI label in the selected language. */ get task() { return uiText("任务"); },
  /** Read this static UI label in the selected language. */ get observation() { return uiText("设备观察"); },
  /** Read this static UI label in the selected language. */ get perception() { return uiText("感知结果"); },
  /** Read this static UI label in the selected language. */ get plan() { return uiText("计划"); },
  /** Read this static UI label in the selected language. */ get memory() { return uiText("记忆上下文"); },
  /** Read this static UI label in the selected language. */ get verification() { return uiText("验证结果"); },
  /** Read this static UI label in the selected language. */ get action() { return uiText("动作"); },
  /** Read this static UI label in the selected language. */ get result() { return uiText("执行结果"); },
  /** Read this static UI label in the selected language. */ get write() { return uiText("写入记忆"); },
  /** Read this static UI label in the selected language. */ get context() { return uiText("记忆上下文"); },
  /** Read this static UI label in the selected language. */ get control() { return uiText("控制"); },
  /** Read this static UI label in the selected language. */ get connection() { return uiText("结束"); },
};

/** Return a user-facing label for a Catalog port without changing its identity. */
export function portLabel(portId: string): string {
  return PORT_LABELS[portId] ?? portId;
}

/** Return a concise explanation of the value transported by one port. */
export function portDataHint(port: BuilderPort): string {
  const types = port.dataTypes.join(" / ");
  return `${portLabel(port.id)} (${port.id}) · ${types}`;
}

/** Explain why a port is unavailable during manual authoring. */
export function portRuntimeHint(port: BuilderPort, family?: string): string | undefined {
  if (port.direction === "input" && port.id === "observation" && ["perception", "action_executor"].includes(family ?? "")) return uiText("设备观察由运行时注入，无需手动连接");
  if (port.id === "control") return uiText("高级控制端口");
  return undefined;
}
