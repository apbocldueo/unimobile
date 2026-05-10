import type { ReactNode } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { GlobalSidebar } from "./GlobalSidebar";
import { BenchmarkModuleSidebar } from "./BenchmarkModuleSidebar";
import { HistoryModuleSidebar } from "./HistoryModuleSidebar";
import { SettingsModuleSidebar } from "./SettingsModuleSidebar";
import { TopActionBar } from "./TopActionBar";
import { PropertyDrawer } from "./PropertyDrawer";
import { CanvasModuleNavBanner } from "./CanvasModuleNavBanner";
import { useModuleNavSwitch } from "./ModuleNavSwitchContext";

function renderLeftSidebar(pathname: string): ReactNode {
  const onBuilder = pathname.startsWith("/builder");
  const onBenchmark = pathname.startsWith("/benchmark");
  const onHistory = pathname.startsWith("/history");
  const onSettings = pathname.startsWith("/settings");
  const onHelp = pathname.startsWith("/help");

  if (onBuilder || onHelp) return <GlobalSidebar />;
  if (onBenchmark) return <BenchmarkModuleSidebar />;
  if (onHistory) return <HistoryModuleSidebar />;
  if (onSettings) return <SettingsModuleSidebar />;
  return <GlobalSidebar />;
}

/**
 * 顶栏固定 52px 全宽；侧栏与主区外沿与顶栏底对齐（第五章 5.3），流程编辑主区内再留 16px 顶距（5.1/5.2）。
 * 第四章：按模块切换左侧栏；流程编辑使用画布内嵌检查器，不挂载右侧抽屉。
 */
function AppShellBody() {
  const location = useLocation();
  const pathname = location.pathname;
  const onBuilder = pathname.startsWith("/builder");
  /** 流程编辑已内联节点检查器，不再使用兵工厂右侧浮动抽屉。 */
  const showPropertyDrawer = false;
  const { errorPath } = useModuleNavSwitch();

  return (
    <div className="relative flex h-screen min-h-0 min-w-0 flex-col overflow-hidden bg-[var(--zx-app)]">
      <TopActionBar />
      <div className="flex min-h-0 min-w-0 flex-1 gap-6 px-6 pb-6 pt-[52px]">
        {renderLeftSidebar(pathname)}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4">
          <div className={`flex min-h-0 min-w-0 flex-1 ${showPropertyDrawer ? "gap-4" : "gap-0"}`}>
            <main
              className="relative min-h-0 min-w-0 flex-1 overflow-hidden rounded-xl border bg-[var(--zx-canvas)] shadow-[var(--zx-shadow-soft)]"
              style={{ borderColor: "var(--zx-border-light)" }}
            >
              <CanvasModuleNavBanner />
              <div
                className={[
                  "relative z-[1] h-full min-h-0 font-sans",
                  errorPath ? "pt-11" : onBuilder ? "pt-4" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <Outlet />
              </div>
            </main>
            {showPropertyDrawer ? <PropertyDrawer /> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export function AppShell() {
  return <AppShellBody />;
}
