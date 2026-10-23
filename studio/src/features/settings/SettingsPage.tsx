import { uiText, useUiLocale, useUiLocaleStore } from "@/shared/i18n";
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
import { useRuntimeEnvironmentReadiness, readinessRemediation } from "@/entities/runtime-readiness";

const MODULE_OPTIONS: { path: StudioDefaultModule; label: string }[] = [
  { path: "/", /** Read this static UI label in the selected language. */ get label() { return uiText("首页"); } },
  { path: "/agents", label: "Agents" },
  { path: "/benchmarks", label: "Experiments" },
  { path: "/history", label: "Runs" },
  { path: "/settings", /** Read this static UI label in the selected language. */ get label() { return uiText("设置"); } },
];

const SETTINGS_SECTIONS: Array<{ id: SettingsSidebarKey; label: string }> = [
  { id: "runtime", /** Read this static UI label in the selected language. */ get label() { return uiText("运行环境"); } },
  { id: "prefs", /** Read this static UI label in the selected language. */ get label() { return uiText("系统偏好"); } },
  { id: "theme", /** Read this static UI label in the selected language. */ get label() { return uiText("主题与字号"); } },
  { id: "shortcuts", /** Read this static UI label in the selected language. */ get label() { return uiText("快捷键"); } },
  { id: "account", /** Read this static UI label in the selected language. */ get label() { return uiText("账户"); } },
  { id: "about", /** Read this static UI label in the selected language. */ get label() { return uiText("关于"); } },
];

/** Render read-only configuration and explicit unverified connection status alongside preferences. */
export function SettingsPage() {
  const locale = useUiLocale();
  const setLocale = useUiLocaleStore((state) => state.setLocale);
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
      ? uiText("运行环境")
      : section === "prefs"
      ? uiText("系统偏好")
      : section === "theme"
        ? uiText("主题设置")
        : section === "shortcuts"
          ? uiText("快捷键配置")
          : section === "account"
            ? uiText("账户管理")
            : uiText("关于我们");

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header
        className="shrink-0 border-b px-6 py-5"
        style={{ borderColor: "var(--zx-divider-ui)", backgroundColor: "var(--zx-canvas)" }}
      >
        <h1 className="text-[15px] font-semibold text-[color:var(--zx-text-title)]">{panelTitle}</h1>
        <p className="mt-2 max-w-2xl text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">
          {uiText("运行配置保持只读；主题、字号和显示偏好只影响本地界面。")}</p>
        <div role="group" aria-label={uiText("语言选择")} className="mt-4 flex flex-wrap items-center gap-3">
          <span className="text-[12px] font-semibold">{uiText("界面语言")}</span>
          {([{ id: "zh-CN", label: "中文" }, { id: "en", label: "English" }] as const).map((language) => (
            <button key={language.id} type="button" lang={language.id} aria-pressed={locale === language.id}
              className={`zx-control px-4 py-2 text-[12px] ${locale === language.id ? "border-[var(--zx-primary)] bg-[var(--zx-primary-soft)] text-[color:var(--zx-text-title)]" : ""}`}
              onClick={() => setLocale(language.id)}>{language.label}</button>
          ))}
          <span className="text-[11px] text-[color:var(--zx-text-muted)]">{uiText("语言更改会立即应用并自动保存在此浏览器。")}</span>
        </div>
        <nav aria-label={uiText("设置分区")} className="mt-4 flex flex-wrap gap-2">
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
                    {runtime.isError ? uiText("静态配置状态未知") : runtime.isFetching ? uiText("正在检查静态配置") : runtime.data?.ready ? uiText("静态运行配置已就绪") : uiText("静态运行配置需要处理")}
                  </h2>
                  <p className="mt-2 text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">
                    {uiText("这里检查后端是否加载运行配置。设备开着不代表后端已配置；配置通过也不代表设备在线或模型接口可用。")}</p>
                </div>
                <button type="button" className="zx-control px-3 py-2 text-[12px]" disabled={runtime.isFetching} onClick={() => void runtime.refetch()}>
                  {runtime.isFetching ? uiText("刷新中…") : uiText("刷新")}
                </button>
              </div>
              {runtime.isLoading ? <p className="mt-4 text-[12px] text-[color:var(--zx-text-muted)]">{uiText("正在读取服务配置…")}</p> : null}
              {runtime.isError ? (
                <p className="mt-4 text-[12px] text-red-600">{uiText("无法读取运行环境：")}{runtime.error instanceof Error ? runtime.error.message : "unknown"}</p>
              ) : null}
            </section>

            {runtime.data && !runtime.isError && !runtime.isFetching ? (
              <>
                <section aria-label="Preparation checklist" className="space-y-3 rounded-xl border border-[var(--zx-border-light)] p-5">
                  <h2>Preparation checklist</h2>
                  <p className="text-sm">Process configuration only. The exact saved revision is checked separately in Run. This does not prove model access or device connectivity.</p>
                  {runtime.data.diagnostics.map((diagnostic, index) => {
                    const next = readinessRemediation(diagnostic);
                    return <div key={`${diagnostic.code}-${index}`} className="space-y-2 text-sm"><p>{diagnostic.message}</p><p>{next.instruction}</p><a href={`/help?topic=${next.preparation}`} target="_blank" rel="noopener noreferrer">How to prepare ↗</a><details><summary>Technical details</summary><code>{diagnostic.code}</code></details></div>;
                  })}
                  {!runtime.data.diagnostics.length ? <p>No process-level configuration issue reported. Check the selected revision before running.</p> : null}
                  <a href="/help?topic=model" target="_blank" rel="noopener noreferrer">Server configuration guide ↗</a>
                </section>
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
                  empty={uiText("后端未加载模型密钥配置；当前 Agent 所需的配置会在运行前另行检查。")}
                />
                <RuntimeList
                  title="Device Profiles"
                  rows={runtime.data.deviceProfiles.map((item) => ({
                    identity: item.label,
                    state: `${item.deviceProfileId} · ${item.platform}`,
                    ready: true,
                  }))}
                  empty={uiText("后端未加载设备配置。请使用下方启动方式；无需因为此提示重启手机或模拟器。")}
                />
                <section aria-label={uiText("连接验证状态")} className="rounded-xl border border-[var(--zx-border-light)] p-5 text-[12px] leading-relaxed">
                  <h2>{uiText("实际连接")}</h2>
                  <p>{uiText("设备在线状态：尚未检查")}</p>
                  <p>{uiText("模型接口连接：尚未测试")}</p>
                  <p className="mt-2 text-[color:var(--zx-text-muted)]">{uiText("本页刷新只重新读取配置，不连接设备、不调用模型。真实连接在任务执行时验证。")}</p>
                </section>
              </>
            ) : null}

            <section className="rounded-xl border bg-[var(--zx-card)] p-5 text-[12px] leading-relaxed" style={{ borderColor: "var(--zx-border-light)" }}>
              <h2 className="m-0 text-[13px] font-semibold text-[color:var(--zx-text-title)]">{uiText("本地启动方式")}</h2>
              <p className="mt-2 text-[color:var(--zx-text-muted)]">{uiText("先停止旧的前后端服务。在项目根目录激活 unimobile 环境，然后执行：")}</p>
              <code className="mt-3 block overflow-x-auto rounded-lg bg-[var(--zx-canvas)] p-3 text-[11px] text-[color:var(--zx-text-body)]">
                python run_studio.py
              </code>
              <p className="mt-3 text-[color:var(--zx-text-muted)]">{uiText("启动器自动读取 secrets.local.yaml（优先）或 secrets.yaml，以及 studio/device-profiles.json，并启动前后端。配置变更后需重启服务。")}</p>
              <p className="mt-3 text-[color:var(--zx-text-muted)]">{uiText("本页面只读；凭证不会进入浏览器、URL、Toast 或 localStorage。")}</p>
            </section>
          </div>
        ) : null}

        {section === "prefs" ? (
          <div className="mx-auto flex max-w-xl flex-col gap-5">
            <Field label={uiText("默认打开模块")}>
              <select
                aria-label={uiText("默认打开模块")}
                disabled
                className="zx-control zx-body-sm w-full cursor-pointer px-3 py-2"
                value={defaultModule}
                onChange={(e) => {
                  setDefaultModule(e.target.value as StudioDefaultModule);
                  pushToast({ message: uiText("已保存默认模块"), tone: "success", durationMs: 3200 });
                }}
              >
                {MODULE_OPTIONS.map((o) => (
                  <option key={o.path} value={o.path} className="bg-[var(--zx-card)] text-[color:var(--zx-text-title)]">
                    {o.label}
                  </option>
                ))}
              </select>
              <Hint>{uiText("根路径 `/` 现为开始页；默认模块切换暂不可用。")}</Hint>
            </Field>
          </div>
        ) : null}

        {section === "theme" ? (
          <div className="mx-auto flex max-w-xl flex-col gap-5">
            <Field label={uiText("界面主题")}>
              <div className="flex flex-wrap gap-3">
                {(
                  [
                    { id: "dark" as const, label: uiText("深色") },
                    { id: "light" as const, label: uiText("浅色") },
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
            <Field label={uiText("字号档位")}>
              <div className="flex flex-wrap gap-3">
                {(
                  [
                    { id: "sm" as const, label: uiText("较小") },
                    { id: "md" as const, label: uiText("标准") },
                    { id: "lg" as const, label: uiText("较大") },
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
            <p className="text-[color:var(--zx-text-muted)]">{uiText("快捷键配置占位：后续接入快捷键捕获与冲突检测。")}</p>
            <ul className="mt-4 list-disc space-y-2 pl-5 text-[color:var(--zx-text-muted)]">
              <li>{uiText("保存：Ctrl / ⌘ + S（占位）")}</li>
              <li>{uiText("运行：Ctrl / ⌘ + Enter（占位）")}</li>
            </ul>
          </div>
        ) : null}

        {section === "account" ? (
          <div className="mx-auto max-w-xl rounded-lg border px-5 py-5 text-[13px]" style={{ borderColor: "var(--zx-border-light)" }}>
            <p className="text-[color:var(--zx-text-body)]">{uiText("当前为本地工作区，暂不提供账户同步。")}</p>
            <div className="mt-4">
              <ChromePrimaryButton disabled>
                {uiText("同步账户信息")}</ChromePrimaryButton>
            </div>
          </div>
        ) : null}

        {section === "about" ? (
          <div className="mx-auto max-w-xl rounded-lg border px-5 py-5 text-[13px] leading-relaxed text-[color:var(--zx-text-body)]" style={{ borderColor: "var(--zx-border-light)" }}>
            <p className="font-semibold text-[color:var(--zx-text-title)]">ZhiXing Studio</p>
            <p className="mt-2 text-[color:var(--zx-text-muted)]">{uiText("版本占位 0.1.0 · 知行 Agent 工作台")}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RuntimeList({
  title,
  rows,
  empty = uiText("没有可显示的条目。"),
}: {
  title: string;
  rows: { identity: string; state: string; ready: boolean }[];
  empty?: string;
}) {
  useUiLocale();
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
  useUiLocale();
  return (
    <div role="group" aria-label={label} className="flex flex-col gap-2">
      <span className="text-[12px] font-semibold text-[color:var(--zx-text-muted)]">{label}</span>
      {children}
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  useUiLocale();
  return <p className="text-[11px] leading-snug text-[color:var(--zx-text-muted)]">{children}</p>;
}
