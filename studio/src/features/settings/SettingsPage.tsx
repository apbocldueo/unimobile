import { useStudioModuleShellStore } from "@/stores/studioModuleShellStore";
import {
  useStudioSettingsStore,
  type StudioDefaultModule,
  type StudioFontScale,
  type StudioThemeMode,
} from "@/stores/studioSettingsStore";
import { useToastStore } from "@/stores/toastStore";
import { ChromePrimaryButton } from "@/app/shell/ChromePrimaryButton";

const MODULE_OPTIONS: { path: StudioDefaultModule; label: string }[] = [
  { path: "/builder", label: "流程编辑" },
  { path: "/benchmark", label: "试车场" },
  { path: "/history", label: "历史" },
  { path: "/settings", label: "设置" },
];

/** 设置：侧栏联动 + 列表式表单（第四章 4.4） */
export function SettingsPage() {
  const section = useStudioModuleShellStore((s) => s.settingsSidebarKey);
  const themeMode = useStudioSettingsStore((s) => s.themeMode);
  const fontScale = useStudioSettingsStore((s) => s.fontScale);
  const defaultModule = useStudioSettingsStore((s) => s.defaultModule);
  const setThemeMode = useStudioSettingsStore((s) => s.setThemeMode);
  const setFontScale = useStudioSettingsStore((s) => s.setFontScale);
  const setDefaultModule = useStudioSettingsStore((s) => s.setDefaultModule);
  const pushToast = useToastStore((s) => s.pushToast);

  const panelTitle =
    section === "prefs"
      ? "系统偏好"
      : section === "theme"
        ? "主题设置"
        : section === "shortcuts"
          ? "快捷键配置"
          : section === "account"
            ? "账户管理"
            : "关于我们";

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header
        className="shrink-0 border-b px-6 py-5"
        style={{ borderColor: "var(--zx-divider-ui)", backgroundColor: "var(--zx-canvas)" }}
      >
        <h1 className="text-[15px] font-semibold text-[color:var(--zx-text-title)]">{panelTitle}</h1>
        <p className="mt-2 max-w-2xl text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">
          左侧入口后续可由接口下发；主题与字号修改后立即作用于全局界面。
        </p>
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-6 py-6">
        {section === "prefs" ? (
          <div className="mx-auto flex max-w-xl flex-col gap-5">
            <Field label="默认打开模块">
              <select
                className="zx-control zx-body-sm w-full cursor-pointer px-3 py-2"
                value={defaultModule}
                onChange={(e) => {
                  setDefaultModule(e.target.value as StudioDefaultModule);
                  pushToast({ message: "已保存默认模块", tone: "success", durationMs: 3200 });
                }}
              >
                {MODULE_OPTIONS.map((o) => (
                  <option key={o.path} value={o.path} className="bg-[var(--zx-card)] text-[color:var(--zx-text-title)]">
                    {o.label}
                  </option>
                ))}
              </select>
              <Hint>根路径 `/` 现为开始页；此项保留供后续扩展（例如快捷入口或书签），当前不会自动跳转。</Hint>
            </Field>
          </div>
        ) : null}

        {section === "theme" ? (
          <div className="mx-auto flex max-w-xl flex-col gap-5">
            <Field label="界面主题">
              <div className="flex flex-wrap gap-3">
                {(
                  [
                    { id: "dark" as const, label: "深色" },
                    { id: "light" as const, label: "浅色" },
                  ] satisfies { id: StudioThemeMode; label: string }[]
                ).map((o) => (
                  <label
                    key={o.id}
                    className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-[13px]"
                    style={{
                      borderColor: themeMode === o.id ? "var(--zx-primary)" : "var(--zx-border-light)",
                      backgroundColor: themeMode === o.id ? "var(--zx-primary-soft)" : "transparent",
                    }}
                  >
                    <input
                      type="radio"
                      name="zx-theme"
                      checked={themeMode === o.id}
                      onChange={() => setThemeMode(o.id)}
                      className="accent-[color:var(--zx-primary)]"
                    />
                    {o.label}
                  </label>
                ))}
              </div>
            </Field>
            <Field label="字号档位">
              <div className="flex flex-wrap gap-3">
                {(
                  [
                    { id: "sm" as const, label: "较小" },
                    { id: "md" as const, label: "标准" },
                    { id: "lg" as const, label: "较大" },
                  ] satisfies { id: StudioFontScale; label: string }[]
                ).map((o) => (
                  <label
                    key={o.id}
                    className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-[13px]"
                    style={{
                      borderColor: fontScale === o.id ? "var(--zx-primary)" : "var(--zx-border-light)",
                      backgroundColor: fontScale === o.id ? "var(--zx-primary-soft)" : "transparent",
                    }}
                  >
                    <input
                      type="radio"
                      name="zx-font"
                      checked={fontScale === o.id}
                      onChange={() => setFontScale(o.id)}
                      className="accent-[color:var(--zx-primary)]"
                    />
                    {o.label}
                  </label>
                ))}
              </div>
            </Field>
          </div>
        ) : null}

        {section === "shortcuts" ? (
          <div className="mx-auto max-w-xl rounded-lg border px-5 py-5 text-[13px] text-[color:var(--zx-text-body)]" style={{ borderColor: "var(--zx-border-light)" }}>
            <p className="text-[color:var(--zx-text-muted)]">快捷键配置占位：后续接入快捷键捕获与冲突检测。</p>
            <ul className="mt-4 list-disc space-y-2 pl-5 text-[color:var(--zx-text-muted)]">
              <li>保存：Ctrl / ⌘ + S（占位）</li>
              <li>运行：Ctrl / ⌘ + Enter（占位）</li>
            </ul>
          </div>
        ) : null}

        {section === "account" ? (
          <div className="mx-auto max-w-xl rounded-lg border px-5 py-5 text-[13px]" style={{ borderColor: "var(--zx-border-light)" }}>
            <p className="text-[color:var(--zx-text-body)]">账户管理占位：后续对接登录态、团队与权限。</p>
            <div className="mt-4">
              <ChromePrimaryButton onClick={() => pushToast({ message: "账户同步（占位）", tone: "info", durationMs: 3000 })}>
                同步账户信息
              </ChromePrimaryButton>
            </div>
          </div>
        ) : null}

        {section === "about" ? (
          <div className="mx-auto max-w-xl rounded-lg border px-5 py-5 text-[13px] leading-relaxed text-[color:var(--zx-text-body)]" style={{ borderColor: "var(--zx-border-light)" }}>
            <p className="font-semibold text-[color:var(--zx-text-title)]">ZhiXing Studio</p>
            <p className="mt-2 text-[color:var(--zx-text-muted)]">版本占位 0.1.0 · 知行 Agent 工作台</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-[12px] font-semibold text-[color:var(--zx-text-muted)]">{label}</span>
      {children}
    </label>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] leading-snug text-[color:var(--zx-text-muted)]">{children}</p>;
}
