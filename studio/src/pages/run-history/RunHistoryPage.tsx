import { Link, useParams, useSearchParams } from "react-router-dom";
import { replayBundleUrl } from "@/entities/artifact";
import { useReplayPage } from "@/entities/replay";
import { AgentWorkspaceFrame } from "@/widgets/agent-workspace";
import { RunsTypeTabs } from "@/widgets/runs-navigation";

/** Format a persisted millisecond timestamp for the current locale. */
function formatImportedAt(value: number): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

/** Render real persisted Replay History with URL-owned filters and cursor. */
export function RunHistoryPage() {
  const { agentId } = useParams<{ agentId?: string }>();
  const [search, setSearch] = useSearchParams();
  const cursor = search.get("cursor") ?? undefined;
  const query = search.get("q") ?? "";
  const status = search.get("status") ?? "all";
  const page = useReplayPage(30, cursor, agentId);
  const items = (page.data?.items ?? []).filter((item) => {
    const matchesQuery =
      !query
      || item.runId.toLowerCase().includes(query.toLowerCase())
      || item.agentId.toLowerCase().includes(query.toLowerCase());
    return matchesQuery && (status === "all" || item.agentStatus === status);
  });

  /** Update one stable URL filter and restart cursor pagination. */
  const setFilter = (key: "q" | "status", value: string) => {
    const next = new URLSearchParams(search);
    if (!value || value === "all") next.delete(key);
    else next.set(key, value);
    next.delete("cursor");
    setSearch(next);
  };

  const content = (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header className="shrink-0 border-b border-[var(--zx-divider-ui)] px-6 py-5">
        <div className="flex items-start justify-between gap-5">
          <div>
            <p className="m-0 text-[9px] font-bold tracking-[0.14em] text-[color:var(--zx-text-muted)]">
              {agentId ? "AGENT RUNS" : "RUNS"}
            </p>
            <h1 className="mt-1 text-[15px] font-semibold text-[color:var(--zx-text-title)]">
              {agentId ? "这个 Agent 的运行记录" : "运行记录"}
            </h1>
            <p className="mt-2 text-[11px] text-[color:var(--zx-text-muted)]">
              {agentId ? "服务端按 exact Agent identity 筛选普通 Run；不混入 Benchmark Experiment。" : "普通 Agent Run 与 Benchmark Experiment 保持独立资源与状态轴。"}
            </p>
          </div>
          <span className="rounded-full border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-3 py-1 text-[9px] font-bold text-[color:var(--zx-primary)]">
            {page.data?.items.length ?? 0} RESOURCES
          </span>
        </div>
      </header>

      {!agentId ? <RunsTypeTabs active="ordinary" /> : null}

      <div className="flex shrink-0 flex-wrap items-end gap-3 border-b border-[var(--zx-border)] px-6 py-3">
        <label className="flex min-w-[15rem] flex-col gap-1 text-[9px] font-bold uppercase tracking-wide text-[color:var(--zx-text-muted)]">
          Run / Agent
          <input
            className="zx-control px-3 py-2 text-[11px]"
            value={query}
            onChange={(event) => setFilter("q", event.target.value)}
            placeholder="搜索当前页"
          />
        </label>
        <label className="flex min-w-[10rem] flex-col gap-1 text-[9px] font-bold uppercase tracking-wide text-[color:var(--zx-text-muted)]">
          Agent status
          <select
            className="zx-control px-3 py-2 text-[11px]"
            value={status}
            onChange={(event) => setFilter("status", event.target.value)}
          >
            <option value="all">全部</option>
            <option value="success">success</option>
            <option value="failure">failure</option>
            <option value="cancelled">cancelled</option>
          </select>
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-6 py-5">
        {page.isLoading ? (
          <HistoryState title="正在读取 Replay index…" />
        ) : page.isError ? (
          <HistoryState
            title="History 加载失败"
            detail={String(page.error)}
            action={<button type="button" onClick={() => void page.refetch()}>重试</button>}
          />
        ) : items.length === 0 ? (
          <HistoryState
            title="没有匹配的 Replay"
            detail={
              page.data?.items.length
                ? "调整 URL 筛选条件后重试。"
                : agentId
                  ? "这个 Agent 还没有普通 Run；可以先运行一个真实任务。"
                  : "先运行一个真实任务，或通过 replay-import CLI 显式导入证据。"
            }
            action={agentId ? <Link to={`/agents/${encodeURIComponent(agentId)}/run`}>运行这个 Agent</Link> : undefined}
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-[var(--zx-border-light)] bg-black/10">
            <table className="w-full border-collapse text-left text-[10px]">
              <thead>
                <tr className="border-b border-[var(--zx-divider-ui)] text-[8px] uppercase tracking-[0.08em] text-[color:var(--zx-text-muted)]">
                  <th className="px-4 py-3">Run / Agent</th>
                  <th className="px-4 py-3">Agent status</th>
                  <th className="px-4 py-3">Benchmark</th>
                  <th className="px-4 py-3">Evidence</th>
                  <th className="px-4 py-3">Imported</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.runId} className="border-b border-[var(--zx-border)] last:border-0">
                    <td className="max-w-[15rem] px-4 py-3">
                      <strong className="block overflow-hidden text-ellipsis whitespace-nowrap text-[color:var(--zx-text-title)]">
                        {item.agentId || "Unknown Agent"}
                      </strong>
                      <code className="mt-1 block overflow-hidden text-ellipsis whitespace-nowrap text-[8px] text-[color:var(--zx-text-muted)]">
                        {item.runId}
                      </code>
                    </td>
                    <td className="px-4 py-3">
                      <ResultBadge value={item.agentStatus} />
                    </td>
                    <td className="px-4 py-3">
                      {item.benchmarkOutcome ? (
                        <ResultBadge value={item.benchmarkOutcome} />
                      ) : (
                        <span className="text-[color:var(--zx-text-muted)]">not attached</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="w-24">
                        <div className="h-1 overflow-hidden rounded-full bg-white/10">
                          <i
                            className="block h-full bg-[var(--zx-primary)]"
                            style={{ width: `${item.evidenceCompleteness}%` }}
                          />
                        </div>
                        <span className="mt-1 block text-[8px] text-[color:var(--zx-text-muted)]">
                          {item.evidenceCompleteness}% · {item.integrityState}
                        </span>
                        <span className="block text-[8px] text-[color:var(--zx-text-muted)]">
                          {item.provenance}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[color:var(--zx-text-body)]">
                      {formatImportedAt(item.importedAt)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-3">
                        <Link
                          className="font-bold text-[color:var(--zx-primary)] no-underline hover:underline"
                          to={`/runs/${encodeURIComponent(item.runId)}/replay`}
                        >
                          Replay
                        </Link>
                        <a
                          className="text-[color:var(--zx-text-muted)] no-underline hover:text-[color:var(--zx-text-body)]"
                          href={replayBundleUrl(item.runId)}
                          download
                        >
                          Bundle
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <footer className="flex shrink-0 items-center justify-between border-t border-[var(--zx-divider-ui)] px-6 py-3">
        <button
          type="button"
          className="text-[10px] text-[color:var(--zx-text-muted)] disabled:opacity-35"
          disabled={!cursor}
          onClick={() => window.history.back()}
        >
          上一页
        </button>
        {page.data?.nextCursor ? (
          <button
            type="button"
            className="rounded-md border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-3 py-1.5 text-[10px] font-bold text-[color:var(--zx-primary)]"
            onClick={() => {
              const next = new URLSearchParams(search);
              next.set("cursor", page.data!.nextCursor!);
              setSearch(next);
            }}
          >
            下一页
          </button>
        ) : (
          <span className="text-[9px] text-[color:var(--zx-text-muted)]">已到最后一页</span>
        )}
      </footer>
    </div>
  );
  return agentId ? <AgentWorkspaceFrame agentId={agentId} activeMode="runs">{content}</AgentWorkspaceFrame> : content;
}

/** Render a compact independent status badge. */
function ResultBadge({ value }: { value: string }) {
  const successful = value === "success" || value === "pass";
  const failed = value === "failure" || value === "fail";
  return (
    <span
      className="inline-flex rounded-full border px-2 py-1 text-[8px] font-bold uppercase"
      style={{
        color: successful ? "#4adea5" : failed ? "#fb8585" : "var(--zx-text-muted)",
        borderColor: successful
          ? "rgba(74,222,165,.35)"
          : failed
            ? "rgba(251,113,133,.35)"
            : "var(--zx-border-light)",
      }}
    >
      {value}
    </span>
  );
}

/** Render one real History loading, empty, or error state. */
function HistoryState({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed border-[var(--zx-border-light)] p-8 text-center">
      <strong className="text-[12px] text-[color:var(--zx-text-body)]">{title}</strong>
      {detail ? <p className="mt-2 text-[10px] text-[color:var(--zx-text-muted)]">{detail}</p> : null}
      {action ? <div className="mt-4 text-[10px] text-[color:var(--zx-primary)]">{action}</div> : null}
    </div>
  );
}
