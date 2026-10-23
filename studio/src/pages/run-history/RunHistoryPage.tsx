import { uiText, useUiLocale } from "@/shared/i18n";
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
  useUiLocale();
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
      || item.agentId.toLowerCase().includes(query.toLowerCase())
      || (item.agentName ?? "").toLowerCase().includes(query.toLowerCase())
      || (item.taskSummary ?? "").toLowerCase().includes(query.toLowerCase());
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
              {agentId ? uiText("这个 Agent 的运行记录") : uiText("运行记录")}
            </h1>
            <p className="mt-2 text-[11px] text-[color:var(--zx-text-muted)]">
              {agentId ? uiText("查看这个 Agent 已完成的任务、结果和回放。") : uiText("查找已完成的普通任务。Benchmark 评测结果可切换到实验记录查看。")}
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
            placeholder={uiText("搜索当前页的 Agent、任务或 ID")}
          />
        </label>
        <label className="flex min-w-[10rem] flex-col gap-1 text-[9px] font-bold uppercase tracking-wide text-[color:var(--zx-text-muted)]">
          Agent status
          <select
            className="zx-control px-3 py-2 text-[11px]"
            value={status}
            onChange={(event) => setFilter("status", event.target.value)}
          >
            <option value="all">{uiText("全部")}</option>
            <option value="success">success</option>
            <option value="failure">failure</option>
            <option value="cancelled">cancelled</option>
          </select>
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-6 py-5">
        {page.isLoading ? (
          <HistoryState title={uiText("正在读取 Replay index…")} />
        ) : page.isError ? (
          <HistoryState
            title={uiText("History 加载失败")}
            detail={String(page.error)}
            action={<button type="button" onClick={() => void page.refetch()}>{uiText("重试")}</button>}
          />
        ) : items.length === 0 ? (
          <HistoryState
            title={uiText("没有匹配的 Replay")}
            detail={
              page.data?.items.length
                ? uiText("调整 URL 筛选条件后重试。")
                : agentId
                  ? uiText("这个 Agent 还没有普通 Run；可以先运行一个真实任务。")
                  : uiText("先运行一个真实任务，或通过 replay-import CLI 显式导入证据。")
            }
            action={agentId ? <Link to={`/agents/${encodeURIComponent(agentId)}/run`}>{uiText("运行这个 Agent")}</Link> : undefined}
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-[var(--zx-border-light)] bg-black/10">
            <table className="w-full border-collapse text-left text-[12px]">
              <thead>
                <tr className="border-b border-[var(--zx-divider-ui)] text-[11px] uppercase tracking-[0.08em] text-[color:var(--zx-text-muted)]">
                  <th className="px-4 py-3">{uiText("任务 / Agent")}</th>
                  <th className="px-4 py-3">{uiText("运行结果")}</th>
                  <th className="px-4 py-3">Benchmark</th>
                  <th className="px-4 py-3">{uiText("证据")}</th>
                  <th className="px-4 py-3">{uiText("归档时间")}</th>
                  <th className="px-4 py-3">{uiText("操作")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.runId} className="border-b border-[var(--zx-border)] last:border-0">
                    <td className="max-w-[15rem] px-4 py-3">
                      <strong className="block overflow-hidden text-ellipsis whitespace-nowrap text-[color:var(--zx-text-title)]">
                        {item.taskSummary || uiText("未记录任务摘要")}
                      </strong>
                      <span className="mt-1 block text-[12px]">{item.agentName || item.agentId || uiText("Agent 名称不可用")}</span>
                      <code className="mt-1 block overflow-hidden text-ellipsis whitespace-nowrap text-[11px] text-[color:var(--zx-text-muted)]">
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
                        <span className="text-[color:var(--zx-text-muted)]">{uiText("未附带评测")}</span>
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
                        <span className="mt-1 block text-[11px] text-[color:var(--zx-text-muted)]">
                          {uiText("采集覆盖")}{" "}{item.evidenceCompleteness}{uiText("% · 完整性")}{" "}{item.integrityState}
                        </span>
                        <span className="block text-[11px] text-[color:var(--zx-text-muted)]">
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
                          {uiText("查看回放")}</Link>
                        <a
                          className="text-[color:var(--zx-text-muted)] no-underline hover:text-[color:var(--zx-text-body)]"
                          href={replayBundleUrl(item.runId)}
                          download
                        >
                          {uiText("下载证据")}</a>
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
          className="text-[12px] text-[color:var(--zx-text-muted)] disabled:opacity-35"
          disabled={!cursor}
          onClick={() => window.history.back()}
        >
          {uiText("上一页")}</button>
        {page.data?.nextCursor ? (
          <button
            type="button"
            className="rounded-md border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-3 py-1.5 text-[12px] font-bold text-[color:var(--zx-primary)]"
            onClick={() => {
              const next = new URLSearchParams(search);
              next.set("cursor", page.data!.nextCursor!);
              setSearch(next);
            }}
          >
            {uiText("下一页")}</button>
        ) : (
          <span className="text-[9px] text-[color:var(--zx-text-muted)]">{uiText("已到最后一页")}</span>
        )}
      </footer>
    </div>
  );
  return agentId ? <AgentWorkspaceFrame agentId={agentId} activeMode="runs">{content}</AgentWorkspaceFrame> : content;
}

/** Render a compact independent status badge. */
function ResultBadge({ value }: { value: string }) {
  useUiLocale();
  const successful = value === "success" || value === "pass";
  const failed = value === "failure" || value === "fail";
  return (
    <span
      className="inline-flex rounded-full border px-2 py-1 text-[11px] font-bold uppercase"
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
  useUiLocale();
  return (
    <div className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed border-[var(--zx-border-light)] p-8 text-center">
      <strong className="text-[12px] text-[color:var(--zx-text-body)]">{title}</strong>
      {detail ? <p className="mt-2 text-[12px] text-[color:var(--zx-text-muted)]">{detail}</p> : null}
      {action ? <div className="mt-4 text-[12px] text-[color:var(--zx-primary)]">{action}</div> : null}
    </div>
  );
}
