import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { listStudioAgents, type StudioAgent } from "@/entities/agent";
import { benchmarkExperimentHistoryQueryOptions } from "@/entities/benchmark-experiment";
import { useReplayPage } from "@/entities/replay";
import { useRuntimeEnvironmentReadiness } from "@/entities/runtime-readiness";
import { StudioOnboardingCard, useStudioOnboarding } from "@/features/studio-onboarding";
import styles from "./studioHome.module.css";

/** Format a server timestamp for the local research workbench. */
function formatRecentTime(value: number): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(value);
}

/** Render a named Agent with separate run and design destinations. */
function RecentAgent({ agent }: { agent: StudioAgent }) {
  return <article className={styles.row}>
    <strong>{agent.name}</strong><small>更新于 {formatRecentTime(agent.updatedAt)}</small>
    <div className={styles.links}>
      {agent.currentRevisionId ? <Link to={`/agents/${encodeURIComponent(agent.agentId)}/run`}>运行任务 →</Link> : null}
      <Link to={`/agents/${encodeURIComponent(agent.agentId)}/design`}>继续设计</Link>
    </div>
  </article>;
}

/** Compose the daily workspace at /workspace with independent resource queries. */
export function StudioHomePage() {
  const agents = useQuery({ queryKey: ["studio-agents", "home", 4], queryFn: () => listStudioAgents(4), retry: false });
  const replays = useReplayPage(4);
  const experiments = useQuery(benchmarkExperimentHistoryQueryOptions(4));
  const readiness = useRuntimeEnvironmentReadiness();
  const onboarding = useStudioOnboarding();
  const recentAgent = agents.isSuccess ? agents.data.items[0] : undefined;
  // Freshness is not a configuration failure. Launch still rechecks the exact revision.
  const readinessState = readiness.data ? readiness.data.ready ? "ready" : "blocked" : "unknown";
  const preparationLabel = readiness.isError ? "检查暂时失败" : readiness.isFetching ? "正在检查" : readiness.isStale && readiness.data ? "待复查" : readinessState === "ready" ? "配置已就绪" : readinessState === "blocked" ? "需要配置" : "尚未检查";

  return <div className={styles.page}><div className={styles.content}>
    <header className={styles.header}>
      <div><p className={styles.eyebrow}>知行 · Mobile Agent 研究工作台</p><h1>从一次任务开始</h1><p>运行你的 Agent，看清它的行动，再继续改进。</p></div>
      <Link to="/help?topic=start">使用指南 ↗</Link>
    </header>
    <div className={styles.startGrid}>
      <section className={styles.start} aria-labelledby="start-heading">
        <p className={styles.eyebrow}>{recentAgent ? "继续工作" : "第一次使用"}</p>
        <h2 id="start-heading">{recentAgent?.name ?? "先试一个观察任务"}</h2>
        <p>{recentAgent ? "用已保存的版本运行新任务，或者继续调整设计。" : "从正式示例创建 Agent，先确认它能读取手机画面并结束任务。"}</p>
        <div className={styles.actions}>
          {recentAgent?.currentRevisionId ? <Link className={styles.primary} to={`/agents/${encodeURIComponent(recentAgent.agentId)}/run`}>运行这个 Agent →</Link> : null}
          {recentAgent ? <Link className={styles.secondary} to={`/agents/${encodeURIComponent(recentAgent.agentId)}/design`}>继续设计</Link> : null}
          <Link className={recentAgent?.currentRevisionId ? styles.secondary : styles.primary} to="/agents?create=example">从示例开始</Link>
        </div>
        <div className={styles.taskBrief}>
          <strong>推荐首次任务 · 确认设置首页</strong>
          <p>先手动打开 Android 系统设置首页，再让 Agent 确认当前画面并结束。不需要更改手机设置。</p>
          <small>预期：看到设置首页的截图，以及任务结束结果。运行会调用模型；耗时和费用取决于你的配置。</small>
        </div>
        <div className={styles.links}><Link to="/agents?create=blank">创建空白 Agent</Link><Link to="/agents?create=import">导入已有 Agent</Link></div>
      </section>
      <aside className={styles.preparation} aria-labelledby="readiness-heading">
        <div className={styles.sectionHeading}><h2 id="readiness-heading">运行准备</h2><span role="status">{preparationLabel}</span></div>
        <p>{readiness.data ? readiness.data.ready ? "上次检查：运行配置齐全。" : readiness.data.diagnostics[0]?.message ?? "请补齐运行配置。" : readiness.isError ? "无法读取运行配置，请检查服务后重试。" : "正在读取运行配置…"}</p>
        <dl>
          <dt>设备配置</dt><dd>{readiness.data?.deviceProfiles.map((item) => item.label).join("、") || "尚无可用信息"}</dd>
          <dt>模型与设备连接</dt><dd>尚未在此页面测试</dd>
        </dl>
        <p className={styles.note}>{readiness.isError && readiness.data ? "上次结果仅供参考，本次检查未成功。" : readiness.isFetching ? "正在重新检查配置…" : readiness.isStale && readiness.data ? "上次检查已过期，运行前会再次核验。" : "配置齐全不代表设备在线或模型可调用。"}</p>
        <div className={styles.links}><button type="button" disabled={readiness.isFetching} onClick={() => void readiness.refetch()}>重新检查配置</button><Link to="/settings">设置与排查 →</Link></div>
      </aside>
    </div>
    {!onboarding.dismissed ? <StudioOnboardingCard readiness={readinessState} onDismiss={onboarding.dismiss} /> : <button className={styles.reopen} type="button" onClick={onboarding.reopen}>重新打开首次使用引导</button>}
    <section className={styles.recent} aria-labelledby="recent-heading">
      <div className={styles.sectionHeading}><h2 id="recent-heading">最近工作</h2><Link to="/history">全部运行记录 →</Link></div>
      <div className={styles.recentGrid}>
        <RecentSection title="任务结果" loading={replays.isLoading} error={replays.isError ? String(replays.error) : null} onRetry={() => void replays.refetch()} empty="还没有可回放的普通 Run。">
          {replays.data?.items.map((item) => <Link className={styles.row} key={item.runId} to={`/runs/${encodeURIComponent(item.runId)}/replay`}><span className={styles.result} data-status={item.agentStatus}>{item.agentStatus === "success" ? "已完成" : item.agentStatus === "failure" ? "运行失败" : item.agentStatus}</span><strong>{item.taskSummary || "任务摘要未记录"}</strong><small>{item.agentName || "Agent 名称未记录"} · {formatRecentTime(item.importedAt)}</small><span>查看结果与回放 →</span></Link>)}
        </RecentSection>
        <RecentSection title="你的 Agents" loading={agents.isLoading} error={agents.isError ? String(agents.error) : null} onRetry={() => void agents.refetch()} empty="还没有 Agent。" allPath="/agents">
          {agents.data?.items.map((agent) => <RecentAgent key={agent.agentId} agent={agent} />)}
        </RecentSection>
        <RecentSection title="Benchmark 实验" loading={experiments.isLoading} error={experiments.isError ? String(experiments.error) : null} onRetry={() => void experiments.refetch()} empty="还没有 Benchmark Experiment。" allPath="/experiments">
          {experiments.data?.items.map((item) => <Link className={styles.row} key={item.experimentId} to={`/experiments/${encodeURIComponent(item.experimentId)}`}><strong>{item.source.packageIdentity}</strong><small>{item.lifecycle} · {formatRecentTime(item.updatedAt)}</small><span>查看实验 →</span></Link>)}
        </RecentSection>
      </div>
      <Link className={styles.benchmarkLink} to="/benchmarks">选择 Benchmark，评测 Agent →</Link>
    </section>
  </div></div>;
}

/** Keep failure or loading of one recent directory local to that section. */
function RecentSection({ title, loading, error, onRetry, empty, allPath, children }: { title: string; loading: boolean; error: string | null; onRetry: () => void; empty: string; allPath?: string; children: ReactNode }) {
  const hasChildren = Array.isArray(children) ? children.some((item) => Array.isArray(item) ? item.length > 0 : Boolean(item)) : Boolean(children);
  return <section className={styles.recentSection}><div className={styles.sectionHeading}><h3>{title}</h3>{allPath ? <Link to={allPath}>全部</Link> : null}</div>{loading ? <p>正在读取…</p> : error ? <div role="alert"><p>{error}</p><button type="button" onClick={onRetry}>重试</button></div> : hasChildren ? children : <p className={styles.note}>{empty}</p>}</section>;
}
