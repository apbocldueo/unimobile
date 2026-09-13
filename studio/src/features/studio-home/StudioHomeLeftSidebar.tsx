import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useModuleNavSwitch } from "@/app/shell/ModuleNavSwitchContext";
import { listStudioAgents } from "@/entities/agent";
import {
  IconChevronLeft,
  IconChevronRight,
  IconFolder,
  IconPlus,
  IconUpload,
} from "@/components/icons/StudioIcons";
import { STUDIO_HOME_SIDEBAR_HINT, STUDIO_HOME_SIDEBAR_TITLE } from "./studioHomeSidebarConfig";

const LS_SIDEBAR_COLLAPSED = "zx-studio-home-sidebar-collapsed-v1";
const W_EXPAND = 260;
const W_COLLAPSE = 60;

const sidebarSurface = {
  backgroundColor: "var(--zx-sidebar)",
  backdropFilter: "blur(10px)",
  WebkitBackdropFilter: "blur(10px)",
} as const;

const iconActionClass =
  "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[color:var(--zx-primary)] outline-none transition-[color,background-color,transform] duration-150 hover:bg-[var(--zx-nav-hover-bg)] hover:text-[color:var(--zx-primary-dim)] active:scale-[0.97] focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-sidebar)]";

const listRowBase =
  "flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-[15px] font-medium outline-none transition-[background-color,color,transform] duration-150 active:scale-[0.99] focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-sidebar)]";

function loadCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(LS_SIDEBAR_COLLAPSED) === "1";
  } catch {
    return false;
  }
}

function persistCollapsed(collapsed: boolean) {
  try {
    window.localStorage.setItem(LS_SIDEBAR_COLLAPSED, collapsed ? "1" : "0");
  } catch {
    /* */
  }
}

/**
 * 开始页左侧栏：与顶栏同系半透明 + 模糊；支持折叠为纯图标列。
 */
export function StudioHomeLeftSidebar() {
  const { switchModule } = useModuleNavSwitch();
  const agents = useQuery({
    queryKey: ["studio-agents"],
    queryFn: () => listStudioAgents(50),
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
  });
  const [collapsed, setCollapsed] = useState(loadCollapsed);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((c) => {
      const next = !c;
      persistCollapsed(next);
      return next;
    });
  }, []);

  const widthPx = collapsed ? W_COLLAPSE : W_EXPAND;

  return (
    <aside
      className="flex h-full shrink-0 flex-col border-r border-[color:var(--zx-divider-ui)] transition-[width] duration-200 ease-out"
      style={{ ...sidebarSurface, width: widthPx }}
      aria-label="流程与项目"
    >
      <div className="flex min-h-0 flex-1 flex-col">
        {/* 标题行 + 折叠 + 新建 / 导入 */}
        <div
          className={[
            "flex shrink-0 border-b border-[color:var(--zx-divider-ui)] py-2.5",
            collapsed ? "flex-col items-center gap-2 px-1" : "flex-row items-center justify-between gap-2 px-2.5",
          ].join(" ")}
        >
          <button
            type="button"
            onClick={toggleCollapsed}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[color:var(--zx-text-muted)] outline-none transition-[color,background-color,transform] hover:bg-[var(--zx-nav-hover-bg)] hover:text-[color:var(--zx-text-title)] active:scale-[0.97] focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)]"
            title={collapsed ? "展开侧栏" : "折叠侧栏"}
            aria-expanded={!collapsed}
            aria-label={collapsed ? "展开侧栏" : "折叠侧栏"}
          >
            {collapsed ? (
              <IconChevronRight size={18} strokeWidth={2} aria-hidden />
            ) : (
              <IconChevronLeft size={18} strokeWidth={2} aria-hidden />
            )}
          </button>

          {!collapsed ? (
            <h2 className="min-w-0 flex-1 truncate text-[20px] font-semibold leading-snug tracking-tight text-[color:var(--zx-text-title)]">{STUDIO_HOME_SIDEBAR_TITLE}</h2>
          ) : null}

          <div className={`flex shrink-0 items-center ${collapsed ? "flex-col gap-1" : "gap-0.5"}`}>
            <button
              type="button"
              className={iconActionClass}
              title="新建 Agent"
              aria-label="新建 Agent"
              onClick={() => void switchModule("/builder")}
            >
              <IconPlus size={18} strokeWidth={2} aria-hidden />
            </button>
            <button type="button" className={iconActionClass} title="导入（即将支持）" aria-label="导入（即将支持）">
              <IconUpload size={18} strokeWidth={2} aria-hidden />
            </button>
          </div>
        </div>

        {/* 列表 */}
        <nav className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-1.5 py-2" aria-label="流程列表">
          {agents.isError ? (
            !collapsed ? (
              <button
                type="button"
                className="mx-1 rounded-lg border border-[color:var(--zx-status-danger)] px-2 py-4 text-center text-[12px] leading-relaxed text-[color:var(--zx-status-danger)]"
                onClick={() => void agents.refetch()}
              >
                Agent 列表读取失败 · 点击重试
              </button>
            ) : (
              <span className="sr-only">Agent 列表读取失败</span>
            )
          ) : (agents.data?.items.length ?? 0) === 0 ? (
            !collapsed ? (
              <div
                className="rounded-lg px-2 py-8 text-center text-[12px] leading-relaxed text-[color:var(--zx-text-muted)] opacity-80"
                role="status"
              >
                {agents.isLoading ? "正在加载 Agent…" : "暂无已保存的 Agent"}
              </div>
            ) : (
              <span className="sr-only">暂无已保存的 Agent</span>
            )
          ) : (
            <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
              {agents.data?.items.map((agent) => (
                <li key={agent.agentId}>
                  <button
                    type="button"
                    className={[
                      listRowBase,
                      collapsed ? "justify-center px-0" : "text-[color:var(--zx-text-body)]",
                      "bg-[var(--zx-nav-hover-bg)] hover:bg-[var(--zx-primary-soft)] hover:text-[color:var(--zx-text-title)]",
                    ].join(" ")}
                    title={collapsed ? agent.name : undefined}
                    onClick={() =>
                      void switchModule(
                        `/agents/${encodeURIComponent(agent.agentId)}/design`,
                      )
                    }
                  >
                    <span className="flex shrink-0 text-[color:var(--zx-primary)] opacity-90" aria-hidden>
                      <IconFolder size={collapsed ? 20 : 18} strokeWidth={1.85} className="text-current" />
                    </span>
                    {!collapsed ? <span className="min-w-0 flex-1 truncate text-left">{agent.name}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>

        {/* 底部提示 */}
        {!collapsed ? (
          <p className="shrink-0 border-t border-[color:var(--zx-divider-ui)] px-3 py-3 text-[13px] leading-relaxed text-[color:var(--zx-text-muted)]">
            {STUDIO_HOME_SIDEBAR_HINT}
          </p>
        ) : (
          <span className="sr-only">{STUDIO_HOME_SIDEBAR_HINT}</span>
        )}
      </div>
    </aside>
  );
}
