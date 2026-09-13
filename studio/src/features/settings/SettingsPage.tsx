import {
  useStudioModuleShellStore,
  type SettingsSidebarKey,
} from "@/stores/studioModuleShellStore";
import {
  useStudioSettingsStore,
  type StudioDefaultModule,
  type StudioFontScale,
  type StudioThemeMode,
} from "@/stores/studioSettingsStore";
import { useToastStore } from "@/stores/toastStore";
import { ChromePrimaryButton } from "@/app/shell/ChromePrimaryButton";
import { useRuntimeEnvironmentReadiness } from "@/entities/runtime-readiness";

const MODULE_OPTIONS: { path: StudioDefaultModule; label: string }[] = [
  { path: "/", label: "首页" },
  { path: "/agents", label: "Agents" },
  { path: "/benchmarks", label: "Experiments" },
  { path: "/history", label: "Runs" },
  { path: "/settings", label: "设置" },
];

const SETTINGS_SECTIONS: Array<{ id: SettingsSidebarKey; label: string }> = [
  { id: "runtime", label: "运行环境" },
  { id: "prefs", label: "系统偏好" },
  { id: "theme", label: "主题与字号" },
  { id: "shortcuts", label: "快捷键" },
  { id: "account", label: "账户" },
  { id: "about", label: "关于" },
];

/** Render discoverable local settings modes inside the stable product shell. */
export function SettingsPage() {
  const section = useStudioModuleShellStore((s) => s.settingsSidebarKey);
  const setSection = useStudioModuleShellStore((s) => s.setSettingsSidebarKey);
  const themeMode = useStudioSettingsStore((s) => s.themeMode);
  const fontScale = useStudioSettingsStore((s) => s.fontScale);
  const defaultModule = useStudioSettingsStore((s) => s.defaultModule);
  const setThemeMode = useStudioSettingsStore((s) => s.setThemeMode);
  const setFontScale = useStudioSettingsStore((s) => s.setFontScale);
  const setDefaultModule = useStudioSettingsStore((s) => s.setDefaultModule);
  const pushToast = useToastStore((s) => s.pushToast);
  const runtime = useRuntimeEnvironmentReadiness();

  const panelTitle =
    section === "runtime"
      ? "运行环境"
      : section === "prefs"
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
          运行配置保持只读；主题、字号和显示偏好只影响本地界面。
        </p>
        <nav aria-label="设置分区" className="mt-4 flex flex-wrap gap-2">
          {SETTINGS_SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={section === item.id ? "page" : undefined}
              className={[
                "rounded-lg px-3 py-2 text-[11px] font-semibold transition",
                section === item.id
                  ? "bg-[var(--zx-primary-soft)] text-[color:var(--zx-text-title)]"
                  : "text-[color:var(--zx-text-muted)] hover:bg-[var(--zx-nav-hover-bg)] hover:text-[color:var(--zx-text-title)]",
              ].join(" ")}
              onClick={() => setSection(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-6 py-6">
        {section === "runtime" ? (
          <div className="mx-auto flex max-w-2xl flex-col gap-4" aria-label="Runtime Environment">
            <section className="rounded-xl border bg-[var(--zx-card)] p-5" style={{ borderColor: "var(--zx-border-light)" }}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="m-0 text-[14px] font-semibold text-[color:var(--zx-text-title)]">
                    {runtime.data?.ready ? "静态运行配置已就绪" : "静态运行配置需要处理"}
                  </h2>
                  <p className="mt-2 text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">
                    这里只显示 Provider、SecretRef identity 与安全 Device Profile；不会读取或展示凭证、ADB serial 和在线设备状态。
                  </p>
                </div>
                <button type="button" className="zx-control px-3 py-2 text-[12px]" disabled={runtime.isFetching} onClick={() => void runtime.refetch()}>
                  {runtime.isFetching ? "刷新中…" : "刷新"}
                </button>
              </div>
              {runtime.isLoading ? <p className="mt-4 text-[12px] text-[color:var(--zx-text-muted)]">正在读取服务配置…</p> : null}
              {runtime.isError ? (
                <p className="mt-4 text-[12px] text-red-600">无法读取运行环境：{runtime.error instanceof Error ? runtime.error.message : "unknown"}</p>
              ) : null}
            </section>

            {runtime.data ? (
              <>
                <RuntimeList
                  title="LLM / Runtime Providers"
                  rows={runtime.data.providers.map((item) => ({
                    identity: item.identifier,
                    state: item.available ? "available" : item.errorType || "unavailable",
                    ready: item.available,
                  }))}
                />
                <RuntimeList
                  title="SecretRef identities"
                  rows={runtime.data.secrets.map((item) => ({
                    identity: item.secretRef,
                    state: item.configured ? "configured" : "missing",
                    ready: item.configured,
                  }))}
                />
                <RuntimeList
                  title="Device Profiles"
                  rows={runtime.data.deviceProfiles.map((item) => ({
                    identity: item.label,
                    state: `${item.deviceProfileId} · ${item.platform}`,
                    ready: true,
                  }))}
                  empty="尚未配置安全 Device Profile。"
                />
              </>
            ) : null}

            <section className="rounded-xl border bg-[var(--zx-card)] p-5 text-[12px] leading-relaxed" style={{ borderColor: "var(--zx-border-light)" }}>
              <h2 className="m-0 text-[13px] font-semibold text-[color:var(--zx-text-title)]">服务端配置方式</h2>
              <p className="mt-2 text-[color:var(--zx-text-muted)]">在 `unimobile` 环境重启 Studio，并传入受信本地文件：</p>
              <code className="mt-3 block overflow-x-auto rounded-lg bg-[var(--zx-canvas)] p-3 text-[11px] text-[color:var(--zx-text-body)]">
                conda run -n unimobile --no-capture-output python -m zhixing.studio serve --secrets ./secrets.yaml --device-profile-config ./device-profiles.json
              </code>
              <p className="mt-3 text-[color:var(--zx-text-muted)]">本页面只读；凭证不会进入浏览器、URL、Toast 或 localStorage。</p>
            </section>
          </div>
        ) : null}

        {section === "prefs" ? (
          <div className="mx-auto flex max-w-xl flex-col gap-5">
            <Field label="默认打开模块">
              <select
                aria-label="默认打开模块"
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

function RuntimeList({
  title,
  rows,
  empty = "没有可显示的条目。",
}: {
  title: string;
  rows: { identity: string; state: string; ready: boolean }[];
  empty?: string;
}) {
  return (
    <section className="rounded-xl border bg-[var(--zx-card)] p-5" style={{ borderColor: "var(--zx-border-light)" }}>
      <h2 className="m-0 text-[13px] font-semibold text-[color:var(--zx-text-title)]">{title}</h2>
      {rows.length ? (
        <ul className="mt-3 m-0 list-none space-y-2 p-0">
          {rows.map((row) => (
            <li key={`${title}-${row.identity}`} className="flex items-center justify-between gap-4 rounded-lg border px-3 py-2" style={{ borderColor: "var(--zx-border-light)" }}>
              <span className="min-w-0 truncate text-[12px] text-[color:var(--zx-text-body)]">{row.identity}</span>
              <span className={row.ready ? "text-[11px] font-semibold text-emerald-600" : "text-[11px] font-semibold text-amber-600"}>{row.state}</span>
            </li>
          ))}
        </ul>
      ) : <p className="mt-3 text-[12px] text-[color:var(--zx-text-muted)]">{empty}</p>}
    </section>
  );
}

/** Group one settings control without creating invalid nested labels. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="group" aria-label={label} className="flex flex-col gap-2">
      <span className="text-[12px] font-semibold text-[color:var(--zx-text-muted)]">{label}</span>
      {children}
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] leading-snug text-[color:var(--zx-text-muted)]">{children}</p>;
}
