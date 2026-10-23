import { uiText } from "@/shared/i18n";
export type BenchmarkContractTestGateInput = {
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
  peerAnalysisPending: boolean;
  contractTestPending: boolean;
};

export type BenchmarkContractTestGate = {
  allowed: boolean;
  code: string;
  message: string;
};

/** Derive the fail-closed clean saved-baseline Contract Test gate. */
export function benchmarkContractTestGate(
  input: BenchmarkContractTestGateInput,
): BenchmarkContractTestGate {
  if (!input.baselineRevisionId || !input.queryCurrentRevisionId) {
    return blocked("not-ready", uiText("当前 draft 尚未形成可测试的 saved baseline。"));
  }
  if (input.definitionStatus.savePending) {
    return blocked("save-pending", uiText("定义 revision 正在保存，请等待完成。"));
  }
  if (input.contentPending) {
    return blocked("content-pending", uiText("资源命令正在提交，请等待权威 revision 返回。"));
  }
  if (input.peerAnalysisPending) {
    return blocked("analysis-pending", uiText("Validation/Dry-run 正在运行，请等待完成。"));
  }
  if (input.contractTestPending) {
    return blocked("contract-pending", uiText("Contract Tests 正在运行；修改输入可取消。"));
  }
  if (input.conflictRevisionId) {
    return blocked("conflict", uiText("存在 revision 冲突；请先 Reload Remote。"));
  }
  if (input.remoteMayBeNewer) {
    return blocked("remote-newer", uiText("远端 current revision 可能已更新；请先 Reload Remote。"));
  }
  if (input.definitionStatus.hasBufferError) {
    return blocked("definition-invalid", uiText("Task JSON 无效；请修复并 Apply 后保存。"));
  }
  if (input.definitionStatus.hasUnappliedBuffer) {
    return blocked("definition-unapplied", uiText("Task JSON 尚未 Apply；请 Apply 后保存。"));
  }
  if (input.definitionStatus.dirty) {
    return blocked("definition-dirty", uiText("请先保存或 Reset 本地修改，再运行 Contract Tests。"));
  }
  if (input.baselineRevisionId !== input.queryCurrentRevisionId) {
    return blocked("revision-mismatch", uiText("本地 baseline 不是 current revision；请 Reload Remote。"));
  }
  return { allowed: true, code: "allowed", message: uiText("当前 saved revision 可运行 fake-fixture Contract Tests。") };
}

/** Build one blocked gate fact with its required corrective action. */
function blocked(code: string, message: string): BenchmarkContractTestGate {
  return { allowed: false, code, message };
}
