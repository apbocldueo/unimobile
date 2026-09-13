import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { listStudioAgents, type StudioAgent } from "@/entities/agent";
import { benchmarkExperimentHistoryQueryOptions } from "@/entities/benchmark-experiment";
import { useReplayPage } from "@/entities/replay";
import { useRuntimeEnvironmentReadiness } from "@/entities/runtime-readiness";
import { StudioOnboardingCard, useStudioOnboarding } from "@/features/studio-onboarding";

/** Format one authoritative resource timestamp using the browser locale. */
function formatRecentTime(value: number): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(value);
}

/** Render a bounded Agent continuation item without duplicating the full Library. */
function RecentAgent({ agent }: { agent: StudioAgent }) {
  return (
    <Link to={`/agents/${encodeURIComponent(agent.agentId)}/design`} className="rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-4 no-underline transition hover:border-[var(--zx-primary-border)]">
      <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-primary)]">Agent</span>
      <strong className="mt-2 block truncate text-[13px] text-[color:var(--zx-text-title)]">{agent.name}</strong>
      <span className="mt-2 block text-[10px] text-[color:var(--zx-text-muted)]">更新于 {formatRecentTime(agent.updatedAt)}</span>
    </Link>
  );
}

/** Render the start-and-continue Studio landing page from bounded authoritative queries. */
export function StudioHomePage() {
  const agents = useQuery({ queryKey: ["studio-agents", "home", 4], queryFn: () => listStudioAgents(4), retry: false });
  const replays = useReplayPage(4);
  const experiments = useQuery(benchmarkExperimentHistoryQueryOptions(4));
  const readiness = useRuntimeEnvironmentReadiness();
  const onboarding = useStudioOnboarding();
  const readinessState = readiness.isError || readiness.isLoading
    ? "unknown"
    : readiness.data?.ready
      ? "ready"
      : "blocked";

  return (
    <div className="h-full overflow-auto bg-[var(--zx-app)] px-6 py-8 text-[color:var(--zx-text-body)]">
      <div className="mx-auto max-w-6xl">
        <header className="rounded-2xl border border-[var(--zx-border-light)] bg-[var(--zx-panel)] px-6 py-8 shadow-[var(--zx-shadow-soft)] md:px-9">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[color:var(--zx-primary)]">Mobile Agent Research Studio</p>
          <h1 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight text-[color:var(--zx-text-title)]">构建、运行并评测 Mobile Agent</h1>
          <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-[color:var(--zx-text-muted)]">从 AgentGraph 设计开始，在真实运行与 Benchmark 实验中检查设备、组件和结构化证据，然后继续迭代。</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/agents?create=blank" className="rounded-lg bg-[var(--zx-primary)] px-5 py-2.5 text-[12px] font-semibold text-white no-underline">创建 Agent</Link>
            <Link to="/agents?create=example" className="rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-5 py-2.5 text-[12px] font-semibold text-[color:var(--zx-text-title)] no-underline">从示例开始</Link>
          </div>
        </header>

        <section className="mt-5 grid gap-4 md:grid-cols-[minmax(0,1fr)_320px]">
          {!onboarding.dismissed ? <StudioOnboardingCard readiness={readinessState} onDismiss={onboarding.dismiss} /> : <button type="button" className="rounded-xl border border-dashed border-[var(--zx-border-light)] bg-[var(--zx-panel)] px-5 py-4 text-left text-[11px] text-[color:var(--zx-text-muted)]" onClick={onboarding.reopen}>重新打开首次使用引导</button>}
          <aside className="rounded-2xl border border-[var(--zx-border-light)] bg-[var(--zx-panel)] p-5" aria-labelledby="readiness-heading">
            <div className="flex items-center justify-between gap-3"><h2 id="readiness-heading" className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">运行准备</h2><span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${readinessState === "ready" ? "bg-emerald-500/15 text-emerald-500" : readinessState === "blocked" ? "bg-amber-500/15 text-amber-600" : "bg-black/5 text-[color:var(--zx-text-muted)]"}`}>{readinessState === "ready" ? "已就绪" : readinessState === "blocked" ? "需要配置" : "未知"}</span></div>
            <p className="mt-3 text-[11px] leading-relaxed text-[color:var(--zx-text-muted)]">{readiness.isLoading ? "正在读取 Provider、SecretRef 与安全设备配置…" : readiness.isError ? "准备状态暂时无法读取。" : readiness.data?.ready ? `${readiness.data.providers.filter((item) => item.available).length} 个 Provider、${readiness.data.deviceProfiles.length} 个设备 Profile 已配置。` : readiness.data?.diagnostics[0]?.message ?? "当前环境尚未满足运行条件。"}</p>
            <Link to="/settings" className="mt-4 inline-block text-[11px] font-semibold text-[color:var(--zx-primary)] no-underline">查看设置与完整诊断 →</Link>
          </aside>
        </section>

        <section className="mt-8" aria-labelledby="recent-heading">
          <div className="flex items-end justify-between gap-3"><div><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-primary)]">Continue</p><h2 id="recent-heading" className="mt-1 text-[18px] font-semibold text-[color:var(--zx-text-title)]">最近工作</h2></div><Link to="/agents" className="text-[11px] font-semibold text-[color:var(--zx-primary)] no-underline">查看全部 Agents</Link></div>
          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <RecentSection title="Agents" loading={agents.isLoading} error={agents.isError ? String(agents.error) : null} onRetry={() => void agents.refetch()} empty="还没有 Agent。">
              {agents.data?.items.map((agent) => <RecentAgent key={agent.agentId} agent={agent} />)}
            </RecentSection>
            <RecentSection title="普通 Runs" loading={replays.isLoading} error={replays.isError ? String(replays.error) : null} onRetry={() => void replays.refetch()} empty="还没有可回放的普通 Run。" allPath="/history">
              {replays.data?.items.map((item) => <Link key={item.runId} to={`/runs/${encodeURIComponent(item.runId)}/replay`} className="rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-4 no-underline"><span className="text-[10px] font-semibold uppercase text-[color:var(--zx-primary)]">{item.agentStatus}</span><strong className="mt-2 block text-[12px] text-[color:var(--zx-text-title)]">Agent Run</strong><span className="mt-2 block text-[10px] text-[color:var(--zx-text-muted)]">{formatRecentTime(item.importedAt)}</span></Link>)}
            </RecentSection>
            <RecentSection title="Benchmark Experiments" loading={experiments.isLoading} error={experiments.isError ? String(experiments.error) : null} onRetry={() => void experiments.refetch()} empty="还没有 Benchmark Experiment。" allPath="/experiments">
              {experiments.data?.items.map((item) => <Link key={item.experimentId} to={`/experiments/${encodeURIComponent(item.experimentId)}`} className="rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-4 no-underline"><span className="text-[10px] font-semibold uppercase text-[color:var(--zx-primary)]">{item.lifecycle}</span><strong className="mt-2 block truncate text-[12px] text-[color:var(--zx-text-title)]">{item.source.packageIdentity}</strong><span className="mt-2 block text-[10px] text-[color:var(--zx-text-muted)]">{formatRecentTime(item.updatedAt)}</span></Link>)}
            </RecentSection>
          </div>
        </section>
      </div>
    </div>
  );
}

/** Isolate one recent-resource query so partial failure does not block Home. */
function RecentSection({ title, loading, error, onRetry, empty, allPath, children }: { title: string; loading: boolean; error: string | null; onRetry: () => void; empty: string; allPath?: string; children: ReactNode }) {
  const hasChildren = Array.isArray(children) ? children.length > 0 : Boolean(children);
  return <section className="rounded-2xl border border-[var(--zx-border-light)] bg-[var(--zx-panel)] p-4"><div className="flex items-center justify-between gap-3"><h3 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">{title}</h3>{allPath ? <Link to={allPath} className="text-[10px] text-[color:var(--zx-primary)] no-underline">全部</Link> : null}</div><div className="mt-3 grid gap-2">{loading ? <p className="text-[11px] text-[color:var(--zx-text-muted)]">正在读取…</p> : error ? <div role="alert" className="rounded-lg border border-rose-500/30 p-3 text-[11px] text-rose-500"><p>{error}</p><button type="button" className="mt-2 font-semibold" onClick={onRetry}>重试</button></div> : hasChildren ? children : <p className="rounded-lg border border-dashed border-[var(--zx-border-light)] p-4 text-[11px] text-[color:var(--zx-text-muted)]">{empty}</p>}</div></section>;
}
