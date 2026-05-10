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
        "group relative flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left outline-none transition-[background-color,box-shadow,color]",
        "focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-sidebar)]",
        active ? "shadow-[0_12px_32px_rgba(90,174,253,0.38)]" : "hover:bg-white/[0.05]",
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
          active ? "bg-white/15" : "bg-black/25 group-hover:bg-black/35",
        ].join(" ")}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1 text-[13px] font-semibold leading-tight tracking-tight">{label}</span>
    </button>
  );
}

/** 历史模块专属侧栏（第四章 4.3） */
export function HistoryModuleSidebar() {
  return (
    <StudioModuleAside title="历史" subtitle="运行记录（接口占位）">
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
      <div className="h-px shrink-0 bg-[rgba(255,255,255,0.2)]" role="separator" aria-hidden />
      <NavLink
        to="/help"
        className="group block rounded-xl no-underline outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-sidebar)]"
      >
        {({ isActive }) => (
          <div
            className={[
              "flex items-center gap-3 px-3 py-2.5 text-[13px] font-semibold tracking-tight transition-colors",
              isActive ? "text-[color:var(--zx-text-body)]" : "text-[color:var(--zx-text-muted)] hover:bg-white/[0.05] hover:text-[color:var(--zx-text-body)]",
            ].join(" ")}
          >
            <span
              aria-hidden
              className={[
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                isActive ? "bg-white/[0.08]" : "bg-black/20 group-hover:bg-black/30",
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
