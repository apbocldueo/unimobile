import { Outlet, useLocation } from "react-router-dom";
import { resolveStudioRouteTrail } from "@/app/navigation/studioNavigation";
import { CanvasModuleNavBanner } from "./CanvasModuleNavBanner";
import { TopActionBar } from "./TopActionBar";
import { useModuleNavSwitch } from "./ModuleNavSwitchContext";

/** Compose the shared product shell without repeating module-specific sidebars. */
export function AppShell() {
  const { errorPath } = useModuleNavSwitch();
  const location = useLocation();
  const trail = resolveStudioRouteTrail(location.pathname);
  return (
    <div className="relative flex h-screen min-h-0 min-w-0 flex-col overflow-hidden bg-[var(--zx-app)]">
      <TopActionBar />
      <main className="relative mt-[56px] min-h-0 min-w-0 flex-1 overflow-hidden bg-[var(--zx-canvas)]">
        <CanvasModuleNavBanner />
        <div className={`relative z-[1] flex h-full min-h-0 flex-col ${errorPath ? "pt-11" : ""}`}>
          {trail ? (
            <div aria-label="当前位置" className="flex h-8 shrink-0 items-center gap-2 border-b border-[var(--zx-divider-ui)] bg-[var(--zx-panel)] px-5 text-[10px] text-[color:var(--zx-text-muted)]">
              <span>{trail.domainLabel}</span><span aria-hidden>/</span><strong className="font-semibold text-[color:var(--zx-text-body)]">{trail.contextLabel}</strong>
            </div>
          ) : null}
          <div className="min-h-0 flex-1"><Outlet /></div>
        </div>
      </main>
    </div>
  );
}
