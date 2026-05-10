import type { AgentDraft } from "./types";

/** 将 Agent 草稿序列化为后端可解析的 JSON（占位实现）。 */
export function serializeAgentDraft(_draft: AgentDraft): string {
  return JSON.stringify(_draft, null, 2);
}
