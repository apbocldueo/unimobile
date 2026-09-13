export type BenchmarkAnalysisGateCode =
  | "allowed"
  | "not-ready"
  | "definition-invalid"
  | "definition-unapplied"
  | "definition-dirty"
  | "definition-save-pending"
  | "content-pending"
  | "analysis-pending"
  | "conflict"
  | "remote-newer"
  | "revision-mismatch";

export type BenchmarkAnalysisGate = {
  allowed: boolean;
  code: BenchmarkAnalysisGateCode;
  message: string;
};

export type BenchmarkAnalysisGateInput = {
  definitionStatus: {
    dirty: boolean;
    hasBufferError: boolean;
    hasUnappliedBuffer: boolean;
    savePending: boolean;
  };
  baselineRevisionId: string | null;
  queryCurrentRevisionId: string | null;
  conflictRevisionId: string | null;
  remoteMayBeNewer: boolean;
  contentPending: boolean;
  analysisPending: boolean;
};

/**
 * Derive the fail-closed clean saved-baseline gate for analysis commands.
 *
 * Args:
 *   input: Public definition, current-revision, conflict, and pending facts.
 *
 * Returns:
 *   One allowed fact or a stable blocked code with a corrective action.
 */
export function benchmarkAnalysisGate(
  input: BenchmarkAnalysisGateInput,
): BenchmarkAnalysisGate {
  if (!input.baselineRevisionId || !input.queryCurrentRevisionId) {
    return blocked("not-ready", "当前 draft 尚未形成可分析的已保存基线。");
  }
  if (input.definitionStatus.savePending) {
    return blocked("definition-save-pending", "定义 revision 正在保存，请等待完成。");
  }
  if (input.contentPending) {
    return blocked("content-pending", "资源命令正在提交，请等待权威 revision 返回。");
  }
  if (input.analysisPending) {
    return blocked("analysis-pending", "分析命令正在运行；请等待或修改输入以取消。");
  }
  if (input.conflictRevisionId) {
    return blocked("conflict", "存在 revision 冲突；请先 Reload Remote。");
  }
  if (input.remoteMayBeNewer) {
    return blocked("remote-newer", "远端 current revision 可能已更新；请先 Reload Remote。");
  }
  if (input.definitionStatus.hasBufferError) {
    return blocked("definition-invalid", "本地 Task JSON 无效；请修复并 Apply 后保存。");
  }
  if (input.definitionStatus.hasUnappliedBuffer) {
    return blocked("definition-unapplied", "本地 Task JSON 尚未 Apply；请 Apply 后保存。");
  }
  if (input.definitionStatus.dirty) {
    return blocked("definition-dirty", "请先保存或 Reset 本地修改，再分析 saved revision。");
  }
  if (input.baselineRevisionId !== input.queryCurrentRevisionId) {
    return blocked("revision-mismatch", "本地基线不是服务端 current revision；请 Reload Remote。");
  }
  return { allowed: true, code: "allowed", message: "当前 saved revision 可分析。" };
}

/**
 * Build one blocked analysis-gate fact with a corrective message.
 *
 * Args:
 *   code: Stable non-allowed gate reason.
 *   message: User-facing corrective action.
 *
 * Returns:
 *   A fail-closed gate projection.
 */
function blocked(
  code: Exclude<BenchmarkAnalysisGateCode, "allowed">,
  message: string,
): BenchmarkAnalysisGate {
  return { allowed: false, code, message };
}
