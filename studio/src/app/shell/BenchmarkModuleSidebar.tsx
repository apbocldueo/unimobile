import { NavLink } from "react-router-dom";
import { IconArchive, IconBadgeCheck, IconHelpCircle, IconSettings } from "@/components/icons/StudioIcons";
import { StudioModuleAside } from "./StudioModuleAside";
import { useStudioModuleShellStore, type BenchmarkSidebarKey } from "@/stores/studioModuleShellStore";

const ICON = 18;
const STROKE = 1.75;

function NavRow({
  id,
  label,
  icon,
}: {
  id: BenchmarkSidebarKey;
  label: string;
  icon: React.ReactNode;
}) {
  const active = useStudioModuleShellStore((s) => s.benchmarkSidebarKey === id);
  const set = useStudioModuleShellStore((s) => s.setBenchmarkSidebarKey);

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

/** 试车场专属侧栏（第四章 4.2，入口列表占位，后续可接接口） */
export function BenchmarkModuleSidebar() {
  return (
    <StudioModuleAside title="试车场" subtitle="评测与基准（接口占位）">
      <section aria-label="试车场入口" className="flex flex-col gap-2">
        <NavRow
          id="tasks"
          label="任务列表"
          icon={<IconArchive size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
        />
        <NavRow
          id="benchmark"
          label="基准配置"
          icon={<IconBadgeCheck size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
        />
        <NavRow
          id="params"
          label="参数设置"
          icon={<IconSettings size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
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
