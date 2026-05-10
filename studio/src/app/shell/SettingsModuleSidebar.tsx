import { IconBadgeCheck, IconBrain, IconLayers, IconSettings, IconUser } from "@/components/icons/StudioIcons";
import { StudioModuleAside } from "./StudioModuleAside";
import { useStudioModuleShellStore, type SettingsSidebarKey } from "@/stores/studioModuleShellStore";

const ICON = 18;
const STROKE = 1.75;

function NavRow({
  id,
  label,
  icon,
}: {
  id: SettingsSidebarKey;
  label: string;
  icon: React.ReactNode;
}) {
  const active = useStudioModuleShellStore((s) => s.settingsSidebarKey === id);
  const set = useStudioModuleShellStore((s) => s.setSettingsSidebarKey);

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

/** 设置模块专属侧栏（第四章 4.4） */
export function SettingsModuleSidebar() {
  return (
    <StudioModuleAside title="设置" subtitle="系统与偏好">
      <section aria-label="设置入口" className="flex flex-col gap-2">
        <NavRow
          id="prefs"
          label="系统偏好"
          icon={<IconBrain size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
        />
        <NavRow
          id="theme"
          label="主题设置"
          icon={<IconSettings size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
        />
        <NavRow
          id="shortcuts"
          label="快捷键配置"
          icon={<IconLayers size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
        />
        <NavRow
          id="account"
          label="账户管理"
          icon={<IconUser size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
        />
        <NavRow
          id="about"
          label="关于我们"
          icon={<IconBadgeCheck size={ICON} strokeWidth={STROKE} style={{ color: "currentColor" }} aria-hidden />}
        />
      </section>
    </StudioModuleAside>
  );
}
