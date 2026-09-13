export type AgentRunRouteState =
  | { mode: "current" }
  | { mode: "launch"; revisionId: string }
  | { mode: "live"; runId: string }
  | { mode: "invalid"; reason: string };

/** Parse the Agent's current revision or one explicit launch/live Run identity. */
export function parseAgentRunSearch(search: string): AgentRunRouteState {
  const params = new URLSearchParams(search);
  const revisionId = params.get("revisionId")?.trim() ?? "";
  const runId = params.get("runId")?.trim() ?? "";
  const unsupported = Array.from(params.keys()).find(
    (key) => key !== "revisionId" && key !== "runId",
  );
  if (unsupported) {
    return { mode: "invalid", reason: `不支持查询参数 ${unsupported}` };
  }
  if (!revisionId && !runId) return { mode: "current" };
  if (revisionId && !runId) return { mode: "launch", revisionId };
  if (runId && !revisionId) return { mode: "live", runId };
  return {
    mode: "invalid",
    reason: "地址必须且只能包含 revisionId 或 runId。",
  };
}
