export type BenchmarkResourceGateCode =
  | "allowed"
  | "not-ready"
  | "definition-invalid"
  | "definition-unapplied"
  | "definition-dirty"
  | "definition-save-pending"
  | "content-pending"
  | "conflict"
  | "remote-newer"
  | "revision-mismatch";

export type BenchmarkResourceMutationGate = {
  allowed: boolean;
  code: BenchmarkResourceGateCode;
  message: string;
};

export type BenchmarkResourceGateInput = {
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
};

/** Derive the fail-closed clean-baseline gate for content mutations. */
export function benchmarkResourceMutationGate(
  input: BenchmarkResourceGateInput,
): BenchmarkResourceMutationGate {
  if (!input.baselineRevisionId || !input.queryCurrentRevisionId) {
    return gate("not-ready", "当前 draft 尚未形成可写入的已保存基线。");
  }
  if (input.definitionStatus.savePending) {
    return gate("definition-save-pending", "定义 revision 正在保存，请等待完成。");
  }
  if (input.contentPending) {
    return gate("content-pending", "已有资源命令正在提交，请等待结果。");
  }
  if (input.conflictRevisionId) {
    return gate("conflict", "存在 revision 冲突；请先 Reload Remote。");
  }
  if (input.remoteMayBeNewer) {
    return gate("remote-newer", "远端 current revision 可能已更新；请先 Reload Remote。");
  }
  if (input.definitionStatus.hasBufferError) {
    return gate("definition-invalid", "本地 Task JSON 无效，不能从该状态修改资源。");
  }
  if (input.definitionStatus.hasUnappliedBuffer) {
    return gate("definition-unapplied", "本地 Task JSON 尚未应用，不能修改资源。");
  }
  if (input.definitionStatus.dirty) {
    return gate("definition-dirty", "请先保存或重置定义修改，再执行资源命令。");
  }
  if (input.baselineRevisionId !== input.queryCurrentRevisionId) {
    return gate("revision-mismatch", "本地基线不是服务端 current revision；请重新加载。");
  }
  return { allowed: true, code: "allowed", message: "资源命令可执行。" };
}

/** Build one blocked resource gate fact. */
function gate(
  code: Exclude<BenchmarkResourceGateCode, "allowed">,
  message: string,
): BenchmarkResourceMutationGate {
  return { allowed: false, code, message };
}
