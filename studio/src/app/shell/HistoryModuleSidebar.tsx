import { NavLink } from "react-router-dom";
import { IconArchive, IconEye, IconHelpCircle, IconHistory } from "@/components/icons/StudioIcons";
import { StudioModuleAside } from "./StudioModuleAside";
import { useStudioModuleShellStore, type HistorySidebarKey } from "@/stores/studioModuleShellStore";

const ICON = 18;
const STROKE = 1.75;

function NavRow({
  id,
  label,
  icon,
}: {
  id: HistorySidebarKey;
  label: string;
  icon: React.ReactNode;
}) {
  const active = useStudioModuleShellStore((s) => s.historySidebarKey === id);
  const set = useStudioModuleShellStore((s) => s.setHistorySidebarKey);

  return (
    <button
      type="button"
      onClick={() => set(id)}
      className={[
        "group relative flex w-full items-center gap-3 rounded-xl px-3 py-3.5 text-left outline-none transition-[background-color,box-shadow,color]",
        "focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-sidebar)]",
        active ? "shadow-[0_12px_32px_rgba(51,156,255,0.25)]" : "hover:bg-[var(--zx-nav-hover-bg)]",
      ].join(" ")}
      style={
        active
          ? { backgroundColor: "var(--zx-primary)", color: "#ffffff" }
          : { color: "var(--zx-text-muted)" }
      }
    >
      {active ? (
        <span aria-hidden className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-white/90" />
      ) : null}
      <span
        aria-hidden
        className={[
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors",
          active ? "bg-white/15" : "bg-[var(--zx-nav-icon-bg)] group-hover:bg-[var(--zx-primary-soft)]",
        ].join(" ")}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1 text-[15px] font-semibold leading-tight tracking-tight">{label}</span>
    </button>
  );
}

/** Render the History navigation, using a compact back rail inside Replay. */
export function HistoryModuleSidebar({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <aside
        aria-label="Replay 历史导航"
        className="flex w-16 shrink-0 flex-col items-center rounded-xl border bg-[var(--zx-sidebar)] py-3 shadow-[var(--zx-shadow-soft)]"
        style={{ borderColor: "var(--zx-border-light)" }}
      >
        <NavLink
          to="/history"
          title="返回运行历史"
          aria-label="返回运行历史"
          className="flex h-11 w-11 items-center justify-center rounded-xl text-[color:var(--zx-text-muted)] no-underline outline-none transition-colors hover:bg-[var(--zx-primary-soft)] hover:text-[color:var(--zx-primary)] focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)]"
        >
          <IconHistory size={20} strokeWidth={STROKE} aria-hidden />
        </NavLink>
        <span className="mt-2 text-[11px] font-semibold text-[color:var(--zx-text-muted)]">
          历史
        </span>
      </aside>
    );
  }
  return (
    <StudioModuleAside title="历史" subtitle="持久 Replay 索引">
      <section aria-label="历史入口" className="flex flex-col gap-2">
        <NavRow
          id="runs"
          label="运行历史"
          icon={<IconHistory size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
        />
        <NavRow
          id="filters"
          label="筛选条件"
          icon={<IconEye size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
        />
        <NavRow
          id="export"
          label="导出记录"
          icon={<IconArchive size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
        />
      </section>
      <div className="h-px shrink-0 bg-[var(--zx-divider-ui)]" role="separator" aria-hidden />
      <NavLink
        to="/help"
        className="group block rounded-xl no-underline outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-sidebar)]"
      >
        {({ isActive }) => (
          <div
            className={[
              "flex items-center gap-3 px-3 py-3 text-[14px] font-semibold tracking-tight transition-colors",
              isActive ? "text-[color:var(--zx-text-body)]" : "text-[color:var(--zx-text-muted)] hover:bg-[var(--zx-nav-hover-bg)] hover:text-[color:var(--zx-text-body)]",
            ].join(" ")}
          >
            <span
              aria-hidden
              className={[
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                isActive ? "bg-[var(--zx-primary-soft)]" : "bg-[var(--zx-nav-icon-bg)] group-hover:bg-[var(--zx-primary-soft)]",
              ].join(" ")}
            >
              <IconHelpCircle size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} />
            </span>
            帮助中心
          </div>
        )}
      </NavLink>
    </StudioModuleAside>
  );
}
