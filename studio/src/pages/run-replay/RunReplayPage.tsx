import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { useStudioAgent } from "@/entities/agent";
import { getAgentRevision } from "@/entities/agent-revision";
import { useReplay } from "@/entities/replay";
import { TaskRunBar, decideReplayRerunEligibility } from "@/features/agent-task-run";
import {
  ReadOnlyRunReason,
  resolveAgentTitle,
  ThreePaneReplayWorkbench,
} from "@/widgets/three-pane-workbench";
import { AgentWorkspaceFrame } from "@/widgets/agent-workspace";

/** Load a durable Replay resource and hand it to the three-pane workbench. */
export function RunReplayPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const replay = useReplay(runId);
  const agentId = replay.data?.snapshot.agentId ?? "";
  const revisionId = replay.data?.snapshot.revisionId ?? "";
  const canQueryExactRevision = Boolean(
    replay.data
    && replay.data.provenance === "native_studio_run"
    && replay.data.benchmark === null
    && agentId
    && revisionId
    && replay.data.snapshot.canonicalHash,
  );
  const agent = useStudioAgent(agentId);
  const revision = useQuery({
    queryKey: ["studio-agent-revision", agentId, revisionId],
    queryFn: () => getAgentRevision(agentId, revisionId),
    enabled: canQueryExactRevision,
    retry: false,
  });
  const eligibility = useMemo(
    () => replay.data
      ? decideReplayRerunEligibility(
          replay.data,
          canQueryExactRevision
            ? revision.isLoading
              ? undefined
              : revision.data ?? null
            : null,
        )
      : null,
    [canQueryExactRevision, replay.data, revision.data, revision.isLoading],
  );
  if (!runId) {
    return <PageState title="无效 Replay 地址" detail="路由缺少 runId。" />;
  }
  if (replay.isLoading) {
    return <PageState title="正在加载 Replay" detail="读取持久化 evidence envelope…" busy />;
  }
  if (replay.isError) {
    const notFound =
      typeof replay.error === "object"
      && replay.error !== null
      && "status" in replay.error
      && replay.error.status === 404;
    return (
      <PageState
        title={notFound ? "Replay 不存在" : "Replay 加载失败"}
        detail={notFound ? `没有找到 ${runId}` : String(replay.error)}
        action={<button type="button" onClick={() => void replay.refetch()}>重试</button>}
      />
    );
  }
  if (!replay.data) {
    return <PageState title="Replay 不可用" detail="服务没有返回 Replay evidence。" />;
  }
  const agentName = resolveAgentTitle(agent.data?.agent.name, replay.data.snapshot.agentId);
  const taskControl = eligibility?.kind === "eligible" ? (
    <TaskRunBar
      target={eligibility.target}
      onCreated={(created) => navigate(
        `/agents/${encodeURIComponent(created.agentId)}/run?runId=${encodeURIComponent(created.runId)}`,
      )}
    />
  ) : (
    <ReadOnlyRunReason
      reason={eligibility?.reason ?? "该 Replay 不具备普通 task 运行上下文。"}
    />
  );
  const workbench = <ThreePaneReplayWorkbench agentName={agentName} envelope={replay.data} taskControl={taskControl} />;
  return agentId
    ? <AgentWorkspaceFrame agentId={agentId} activeMode="runs">{workbench}</AgentWorkspaceFrame>
    : workbench;
}

/** Render a stable loading, empty, not-found, or retry state. */
function PageState({
  title,
  detail,
  busy = false,
  action,
}: {
  title: string;
  detail: string;
  busy?: boolean;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex h-full items-center justify-center bg-[var(--zx-canvas)] p-8">
      <div className="max-w-md rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-panel)] p-7 text-center shadow-[var(--zx-shadow-soft)]">
        <span className={`mx-auto mb-4 block h-8 w-8 rounded-full border-2 border-[var(--zx-primary)] ${busy ? "animate-spin border-t-transparent" : ""}`} />
        <h1 className="m-0 text-[15px] text-[color:var(--zx-text-title)]">{title}</h1>
        <p className="mt-2 text-[11px] text-[color:var(--zx-text-muted)]">{detail}</p>
        <div className="mt-4 text-[11px] text-[color:var(--zx-primary)]">{action}</div>
      </div>
    </div>
  );
}
