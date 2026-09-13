import { NavLink } from "react-router-dom";
import { useStudioAgent } from "@/entities/agent";

export type AgentWorkspaceMode = "design" | "run" | "runs";

/** Keep one Agent identity visible while route-owned work modes remain isolated. */
export function AgentWorkspaceFrame({
  agentId,
  activeMode,
  children,
}: {
  agentId: string;
  activeMode: AgentWorkspaceMode;
  children: React.ReactNode;
}) {
  const agent = useStudioAgent(agentId);
  const name = agent.data?.agent.name.trim() || "Agent";
  const revisionId = agent.data?.agent.currentRevisionId ?? null;
  const modes: Array<{ id: AgentWorkspaceMode; label: string; path: string }> = [
    { id: "design", label: "设计", path: `/agents/${encodeURIComponent(agentId)}/design` },
    { id: "run", label: "运行", path: `/agents/${encodeURIComponent(agentId)}/run` },
    { id: "runs", label: "运行记录", path: `/agents/${encodeURIComponent(agentId)}/runs` },
  ];
  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header className="flex min-h-[58px] shrink-0 flex-wrap items-center gap-4 border-b border-[var(--zx-divider-ui)] bg-[var(--zx-panel)] px-5 py-2" aria-label="Agent 工作区">
        <div className="min-w-[180px]">
          <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-primary)]">Agent</p>
          <strong className="mt-0.5 block truncate text-[15px] font-semibold text-[color:var(--zx-text-title)]">{agent.isLoading ? "正在读取 Agent…" : name}</strong>
        </div>
        <nav aria-label="Agent 工作模式" className="flex items-center gap-1">
          {modes.map((mode) => <NavLink key={mode.id} to={mode.path} aria-current={mode.id === activeMode ? "page" : undefined} className={["rounded-lg px-3 py-2 text-[11px] font-semibold no-underline outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)]", mode.id === activeMode ? "bg-[var(--zx-primary-soft)] text-[color:var(--zx-text-title)]" : "text-[color:var(--zx-text-muted)] hover:bg-[var(--zx-nav-hover-bg)] hover:text-[color:var(--zx-text-title)]"].join(" ")}>{mode.label}</NavLink>)}
        </nav>
        <details className="ml-auto max-w-[360px] text-[9px] text-[color:var(--zx-text-muted)]">
          <summary className="cursor-pointer rounded-md px-2 py-1 hover:bg-[var(--zx-nav-hover-bg)]">技术详情</summary>
          <div className="absolute right-5 z-20 mt-2 w-[340px] rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-panel)] p-3 shadow-[var(--zx-shadow-soft)]">
            <span className="block">Agent identity</span><code className="mt-1 block break-all text-[color:var(--zx-text-body)]">{agentId}</code>
            <span className="mt-2 block">Current revision</span><code className="mt-1 block break-all text-[color:var(--zx-text-body)]">{revisionId ?? "none"}</code>
          </div>
        </details>
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
