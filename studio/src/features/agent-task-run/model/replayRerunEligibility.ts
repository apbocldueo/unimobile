import type { AgentRevision } from "@/entities/agent-revision";
import type { ReplayEnvelope } from "@/entities/replay";
import type { AgentRunTarget } from "./taskRunDraft";

export type ReplayRerunEligibility =
  | { kind: "eligible"; target: AgentRunTarget }
  | { kind: "checking"; reason: string }
  | { kind: "read_only"; reason: string };

/** Decide whether one persisted Replay can safely launch a new ordinary Run.
 *
 * Args:
 *   envelope: Strict persisted Replay facts currently being inspected.
 *   revision: Exact locally queried revision, `undefined` while checking, or `null` when unavailable.
 *
 * Returns:
 *   An eligible exact target or a reader-facing fail-closed reason.
 */
export function decideReplayRerunEligibility(
  envelope: ReplayEnvelope,
  revision: AgentRevision | null | undefined,
): ReplayRerunEligibility {
  if (envelope.provenance !== "native_studio_run") {
    return {
      kind: "read_only",
      reason: "该 Replay 不是本地普通 Agent Run，不能据此启动普通 task。",
    };
  }
  if (envelope.benchmark !== null) {
    return {
      kind: "read_only",
      reason: "Benchmark Replay 保持只读；请从 Benchmark Experiment 工作流运行任务。",
    };
  }
  const { agentId, revisionId, canonicalHash } = envelope.snapshot;
  if (!agentId || !revisionId || !canonicalHash) {
    return {
      kind: "read_only",
      reason: "Replay 未保存完整的本地 Agent/revision/canonical identity。",
    };
  }
  if (revision === undefined) {
    return { kind: "checking", reason: "正在验证 Replay 对应的 exact revision…" };
  }
  if (revision === null) {
    return {
      kind: "read_only",
      reason: "本地 exact revision 不可用；不会改用 Agent 的 current revision。",
    };
  }
  if (revision.agentId !== agentId || revision.revisionId !== revisionId) {
    return { kind: "read_only", reason: "Replay 与本地 revision 的资源身份不匹配。" };
  }
  if (
    revision.compileSnapshot.status !== "valid"
    || !revision.compileSnapshot.agentGraph
  ) {
    return { kind: "read_only", reason: "Replay 对应 revision 当前无法通过正式编译验证。" };
  }
  if (revision.compileSnapshot.canonicalHash !== canonicalHash) {
    return { kind: "read_only", reason: "Replay 与本地 revision 的 canonical identity 不一致。" };
  }
  return {
    kind: "eligible",
    target: { agentId, revisionId, canonicalHash },
  };
}
