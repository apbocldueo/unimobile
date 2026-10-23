import { uiText, useUiLocale } from "@/shared/i18n";
import { useState } from "react";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { studioRunQueryOptions, type StudioRunResource } from "@/entities/run";

/** Recheck session-known unfinished Runs and offer exact return links without inventing an inventory. */
export function RecentRunReturn() {
  useUiLocale();
  const client = useQueryClient();
  // Capture identities only; status and task text below must come from fresh server reads.
  const [known] = useState(() => client.getQueriesData<StudioRunResource>({ queryKey: ["studio", "run"] })
    .flatMap(([, run]) => run && run.lifecycle !== "terminal" ? [{ runId: run.runId, agentId: run.agentId }] : []));
  const results = useQueries({ queries: known.map(({ runId }) => ({
    ...studioRunQueryOptions(runId), staleTime: 0, refetchOnMount: "always" as const,
    refetchInterval: (query: { state: { data?: StudioRunResource } }) => query.state.data?.lifecycle === "terminal" ? false : 5000,
  })) });
  if (!known.length) return null;
  return <section aria-label={uiText("本次使用中的任务")} className="my-5 rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-primary-soft)] p-5">
    <h2 className="text-base font-semibold">{uiText("本次使用中的任务")}</h2>
    {known.map((reference, index) => {
      const result = results[index];
      const run = result.data;
      const fresh = result.isFetchedAfterMount && !result.isError;
      const status = !fresh ? result.isError ? uiText("状态检查失败") : uiText("正在确认状态") : run?.lifecycle === "terminal" ? uiText("已结束") : run?.lifecycle === "running" ? uiText("正在运行") : run?.lifecycle === "cancelling" ? uiText("正在取消") : uiText("正在准备");
      return <div key={reference.runId} className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <span>{fresh && run ? run.task.text : uiText("已打开的任务")} · {status}</span>
        <Link className="text-[var(--zx-primary-dim)]" to={`/agents/${encodeURIComponent(reference.agentId)}/run?runId=${encodeURIComponent(reference.runId)}`}>{uiText("查看进度 →")}</Link>
      </div>;
    })}
    <p className="mt-3 text-xs text-[var(--zx-text-muted)]">{uiText("这里保留本次页面会话中打开过的任务；重新打开应用后，请通过原任务链接返回。")}</p>
  </section>;
}
