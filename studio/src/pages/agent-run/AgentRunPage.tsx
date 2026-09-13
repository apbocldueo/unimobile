import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useStudioAgent } from "@/entities/agent";
import { getAgentRevision } from "@/entities/agent-revision";
import {
  adaptRevisionToLaunchSnapshot,
  adaptRevisionToRunSnapshot,
  useStudioRun,
  type RunSnapshot,
} from "@/entities/run";
import {
  resolveAgentTitle,
  ThreePaneLaunchWorkbench,
  ThreePaneLiveRunWorkbench,
} from "@/widgets/three-pane-workbench";
import { decideTerminalHandoff } from "@/features/live-run-session";
import { parseAgentRunSearch } from "./model/agentRunRoute";
import { AgentWorkspaceFrame } from "@/widgets/agent-workspace";

/** Bind launch/live search state to one Agent-scoped Run page. */
export function AgentRunPage() {
  const { agentId = "" } = useParams<{ agentId: string }>();
  const navigate = useNavigate();
  const agent = useStudioAgent(agentId);
  const [searchParams] = useSearchParams();
  const route = useMemo(
    () => parseAgentRunSearch(`?${searchParams.toString()}`),
    [searchParams],
  );
  if (!agentId) return <Navigate to="/agents" replace />;
  if (route.mode === "invalid") {
    return <RunPageState title="无效 Run 地址" detail={route.reason} />;
  }
  const agentName = resolveAgentTitle(agent.data?.agent.name, agentId);
  let content: React.ReactNode;
  if (route.mode === "current") {
    const revisionId = agent.data?.agent.currentRevisionId ?? "";
    content = agent.isLoading ? (
      <RunPageState title="正在读取 Agent" detail="正在解析当前 immutable revision。" busy />
    ) : agent.isError ? (
      <RunPageState
        title="Agent 加载失败"
        detail={String(agent.error)}
        action={<button type="button" onClick={() => void agent.refetch()}>重试</button>}
      />
    ) : revisionId ? (
      <RunLaunch agentId={agentId} agentName={agentName} revisionId={revisionId} />
    ) : (
      <RunPageState
        title="Agent 尚不能运行"
        detail="该 Agent 没有当前 immutable revision；请先在设计页校验并保存。"
        action={<button type="button" onClick={() => navigate(`/agents/${encodeURIComponent(agentId)}/design`)}>返回设计</button>}
      />
    );
  } else if (route.mode === "launch") {
    content = <RunLaunch agentId={agentId} agentName={agentName} revisionId={route.revisionId} />;
  } else {
    content = <RunBoundState agentId={agentId} agentName={agentName} runId={route.runId} />;
  }
  return <AgentWorkspaceFrame agentId={agentId} activeMode="run">{content}</AgentWorkspaceFrame>;
}

/** Render one exact immutable revision in the integrated launch workbench. */
function RunLaunch({
  agentId,
  agentName,
  revisionId,
}: {
  agentId: string;
  agentName: string;
  revisionId: string;
}) {
  const navigate = useNavigate();
  const revision = useQuery({
    queryKey: ["studio-agent-revision", agentId, revisionId],
    queryFn: () => getAgentRevision(agentId, revisionId),
    enabled: Boolean(agentId && revisionId),
    retry: false,
  });

  if (revision.isLoading) {
    return <RunPageState title="正在读取 revision" detail={revisionId} busy />;
  }
  if (revision.isError) {
    return (
      <RunPageState
        title="Revision 加载失败"
        detail={String(revision.error)}
        action={
          <button type="button" onClick={() => void revision.refetch()}>
            重试
          </button>
        }
      />
    );
  }
  if (!revision.data || revision.data.agentId !== agentId) {
    return (
      <RunPageState
        title="Revision 身份不匹配"
        detail="该 immutable revision 不属于路由中的 Agent。"
      />
    );
  }
  if (revision.data.compileSnapshot.status !== "valid") {
    return (
      <RunPageState
        title="Revision 无法运行"
        detail="compile status 为 invalid；请回到 Builder 修正 diagnostics。"
      />
    );
  }
  let snapshot: RunSnapshot;
  try {
    snapshot = adaptRevisionToLaunchSnapshot(revision.data);
  } catch (error) {
    return (
      <RunPageState
        title="Revision 无法运行"
        detail={error instanceof Error ? error.message : "无法验证 exact revision。"}
      />
    );
  }
  if (!snapshot.canonicalHash || !snapshot.revisionId) {
    return <RunPageState title="Revision 无法运行" detail="缺少正式 revision/canonical identity。" />;
  }
  return (
    <ThreePaneLaunchWorkbench
      agentName={agentName}
      snapshot={snapshot}
      target={{ agentId, revisionId: snapshot.revisionId, canonicalHash: snapshot.canonicalHash }}
      onCreated={(created) => navigate(
        `/agents/${encodeURIComponent(agentId)}/run?runId=${encodeURIComponent(created.runId)}`,
        { replace: true },
      )}
    />
  );
}

/** Verify that a live Run belongs to the route Agent before rendering it. */
function RunBoundState({
  agentId,
  agentName,
  runId,
}: {
  agentId: string;
  agentName: string;
  runId: string;
}) {
  const navigate = useNavigate();
  const run = useStudioRun(runId);
  const revision = useQuery({
    queryKey: [
      "studio-agent-revision",
      run.data?.agentId ?? agentId,
      run.data?.revisionId ?? "",
    ],
    queryFn: () =>
      getAgentRevision(
        run.data?.agentId ?? agentId,
        run.data?.revisionId ?? "",
      ),
    enabled: Boolean(
      run.data
      && run.data.agentId === agentId
      && run.data.revisionId,
    ),
    retry: false,
  });
  if (run.isLoading) {
    return <RunPageState title="正在恢复 Run" detail={runId} busy />;
  }
  if (run.isError) {
    return (
      <RunPageState
        title="Run 加载失败"
        detail={String(run.error)}
        action={
          <button type="button" onClick={() => void run.refetch()}>
            重试
          </button>
        }
      />
    );
  }
  if (!run.data || run.data.agentId !== agentId) {
    return (
      <RunPageState
        title="Run 身份不匹配"
        detail="该 Run 不属于路由中的 Agent，不会展示交叉资源。"
      />
    );
  }
  let snapshot: RunSnapshot = {
    agentId,
    revisionId: run.data.revisionId,
    contractVersion: "1.1",
    canonicalHash: run.data.canonicalHash,
    graphStatus: "not_captured",
    agentGraph: null,
    graphNodes: [],
    graphEdges: [],
    presentation: null,
    sourceMap: [],
    providerIdentities: [],
  };
  let graphError: string | null = revision.isLoading
    ? "正在读取 exact immutable revision"
    : revision.isError
      ? String(revision.error)
      : null;
  if (revision.data) {
    try {
      snapshot = adaptRevisionToRunSnapshot(revision.data, run.data);
    } catch (error) {
      graphError = error instanceof Error ? error.message : "Graph contract mismatch";
      snapshot = { ...snapshot, graphStatus: "corrupt" };
    }
  }

  /** Refresh the authoritative terminal resource while retaining the Live workspace. */
  const refreshTerminal = async () => {
    await run.refetch();
  };

  /** Revalidate the exact terminal event/resource pair after the user opens Replay. */
  const openTerminalReplay = async (
    terminalEvent: import("@/entities/run").StudioRunEvent,
  ) => {
    const refreshed = await run.refetch();
    const authoritative = refreshed.data;
    if (!authoritative) return;
    const decision = decideTerminalHandoff(authoritative, terminalEvent);
    if (decision.kind === "replay") {
      navigate(`/runs/${encodeURIComponent(decision.runId)}/replay`, {
        replace: true,
      });
    }
  };

  return (
    <ThreePaneLiveRunWorkbench
      agentName={agentName}
      run={run.data}
      snapshot={snapshot}
      graphError={graphError}
      onTerminal={() => void refreshTerminal()}
      onOpenReplay={(event) => void openTerminalReplay(event)}
    />
  );
}

/** Render stable loading, invalid, unavailable, and retry Run states. */
export function RunPageState({
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
      <div className="max-w-md rounded-xl border border-[var(--zx-border)] bg-[var(--zx-panel)] p-7 text-center">
        <span
          className={`mx-auto mb-4 block h-8 w-8 rounded-full border-2 border-[var(--zx-primary)] ${
            busy ? "animate-spin border-t-transparent" : ""
          }`}
        />
        <h1 className="m-0 text-[15px] text-[var(--zx-text-title)]">{title}</h1>
        <p className="mt-2 text-[11px] text-[var(--zx-text-muted)]">{detail}</p>
        <div className="mt-4 text-[11px] text-[var(--zx-primary)]">{action}</div>
      </div>
    </div>
  );
}
