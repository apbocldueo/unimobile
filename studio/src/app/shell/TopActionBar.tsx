import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import {
  IconBot,
  IconChevronLeft,
  IconChevronRight,
  IconHelpCircle,
  IconHistory,
  IconLineChart,
  IconSettings,
  IconUser,
} from "@/components/icons/StudioIcons";
import { useModuleNavSwitch } from "./ModuleNavSwitchContext";
import { useStudioRegistryStore } from "@/stores/studioRegistryStore";

/** 第二章：顶栏与模块样式；第三章：hover / 选中态 / 加载与错误 */
const TOP_NAV_SHADOW = "0 2px 8px rgba(0,0,0,0.1)";
const MODULE_ICON = 16;
const MODULE_STROKE = 1.75;
const LOGO_ICON = 18;
const POPOVER_BG = "#242424";
const POPOVER_BORDER = "#444444";

function moduleNavClass({ isActive, disabled }: { isActive: boolean; disabled?: boolean }) {
  const base = [
    "relative flex shrink-0 items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 font-sans text-[14px] no-underline outline-none",
    "transition-[color,background-color]",
    "focus-visible:ring-2 focus-visible:ring-[#4096ff] focus-visible:ring-offset-2",
  ].join(" ");

  if (disabled) {
    return [
      base,
      "cursor-not-allowed font-normal text-[#666666] hover:bg-transparent pointer-events-none",
      "[&_svg]:opacity-50",
    ].join(" ");
  }

  if (isActive) {
    return [
      base,
      "cursor-pointer font-semibold text-white",
      "bg-[rgba(255,255,255,0.1)] hover:bg-[rgba(255,255,255,0.1)] hover:text-white",
      "after:pointer-events-none after:absolute after:inset-x-2 after:bottom-0 after:h-[2px] after:bg-[#4096ff] after:content-['']",
      "ring-offset-[#1e1e2e]",
    ].join(" ");
  }

  return [
    base,
    "cursor-pointer font-normal text-[#a0a0a0] bg-transparent hover:bg-[rgba(255,255,255,0.08)] hover:text-white",
    "ring-offset-[#1e1e2e]",
  ].join(" ");
}

function ModuleNavButton({
  targetPath,
  isActive,
  label,
  icon,
  locked,
}: {
  targetPath: string;
  isActive: boolean;
  label: string;
  icon: ReactNode;
  locked?: boolean;
}) {
  const { pendingPath, errorPath, switchModule } = useModuleNavSwitch();
  const isPending = pendingPath === targetPath;
  const isError = errorPath === targetPath;
  const isLocked = Boolean(locked);
  const showSelected = isActive && !isPending && !isError && !isLocked;

  const cls = [
    moduleNavClass({ isActive: showSelected, disabled: isLocked }),
    isError ? "text-[#ff6b6b] after:!hidden hover:!bg-transparent hover:!text-[#ff6b6b]" : "",
    isPending && !isLocked ? "pointer-events-none" : "",
  ].join(" ");

  return (
    <button
      type="button"
      className={cls}
      aria-current={showSelected ? "page" : undefined}
      aria-busy={isPending && !isLocked ? true : undefined}
      aria-disabled={isLocked || undefined}
      onClick={() => {
        if (isLocked) return;
        void switchModule(targetPath);
      }}
    >
      <span className="inline-flex shrink-0 items-center text-current">{icon}</span>
      <span className="text-current">{label}</span>
      {isPending && !isError ? (
        <span
          className="ml-1 inline-block h-3.5 w-3.5 shrink-0 rounded-full border-2 border-current border-t-transparent opacity-80 animate-spin"
          aria-hidden
        />
      ) : null}
    </button>
  );
}

function NavModuleIcon({ iconKey }: { iconKey: string }) {
  const k = iconKey.trim().toLowerCase();
  const p = { size: MODULE_ICON, strokeWidth: MODULE_STROKE, className: "text-current" as const, "aria-hidden": true as const };
  if (k === "linechart" || k === "chart" || k === "benchmark") return <IconLineChart {...p} />;
  if (k === "history" || k === "time") return <IconHistory {...p} />;
  if (k === "settings" || k === "gear") return <IconSettings {...p} />;
  return <IconBot {...p} />;
}

function isNavPathActive(pathname: string, modulePath: string) {
  if (modulePath === "/builder") return pathname.startsWith("/builder");
  return pathname === modulePath || pathname.startsWith(`${modulePath}/`);
}

type HelpTab = "guide" | "faq" | "support";

const helpTabBtn =
  "rounded-lg px-3 py-1.5 text-[12px] font-medium outline-none transition-[background-color,color] focus-visible:ring-2 focus-visible:ring-[#4096ff] focus-visible:ring-offset-2 focus-visible:ring-offset-[#242424]";

export function TopActionBar() {
  const location = useLocation();
  const { switchModule } = useModuleNavSwitch();
  const navModules = useStudioRegistryStore((s) => s.navModules);
  const navLoadError = useStudioRegistryStore((s) => s.navLoadError);
  const loadNavModules = useStudioRegistryStore((s) => s.loadNavModules);
  const moduleConfigCache = useStudioRegistryStore((s) => s.moduleConfigCache);

  const scrollRef = useRef<HTMLElement>(null);
  const [showLeftArrow, setShowLeftArrow] = useState(false);
  const [showRightArrow, setShowRightArrow] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [helpTab, setHelpTab] = useState<HelpTab>("guide");
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [userMenuPos, setUserMenuPos] = useState<{ top: number; right: number } | null>(null);
  const avatarButtonRef = useRef<HTMLButtonElement>(null);
  const [logoAnimKey, setLogoAnimKey] = useState(0);

  const path = location.pathname;

  const updateScrollArrows = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    const overflow = scrollWidth > clientWidth + 1;
    setShowLeftArrow(overflow && scrollLeft > 2);
    setShowRightArrow(overflow && scrollLeft < scrollWidth - clientWidth - 2);
  }, []);

  useLayoutEffect(() => {
    updateScrollArrows();
  }, [path, updateScrollArrows]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => updateScrollArrows());
    ro.observe(el);
    return () => ro.disconnect();
  }, [updateScrollArrows]);

  useEffect(() => {
    if (!helpOpen && !userMenuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setHelpOpen(false);
        setUserMenuOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [helpOpen, userMenuOpen]);

  useEffect(() => {
    if (!userMenuOpen) return;
    const onPointer = (e: MouseEvent | PointerEvent) => {
      const t = e.target as Node;
      if (avatarButtonRef.current?.contains(t)) return;
      const menu = document.getElementById("zx-user-menu-popover");
      if (menu?.contains(t)) return;
      setUserMenuOpen(false);
    };
    window.addEventListener("mousedown", onPointer);
    return () => window.removeEventListener("mousedown", onPointer);
  }, [userMenuOpen]);

  const scrollNav = (dir: "left" | "right") => {
    const el = scrollRef.current;
    if (!el) return;
    const delta = Math.min(200, Math.floor(el.clientWidth * 0.6));
    el.scrollBy({ left: dir === "left" ? -delta : delta, behavior: "smooth" });
    window.requestAnimationFrame(() => updateScrollArrows());
  };

  const openUserMenu = () => {
    const btn = avatarButtonRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    setUserMenuPos({
      top: r.bottom + 6,
      right: document.documentElement.clientWidth - r.right,
    });
    setUserMenuOpen(true);
  };

  const onLogoClick = () => {
    setLogoAnimKey((k) => k + 1);
    void switchModule("/");
  };

  return (
    <>
      <header
        className="fixed inset-x-0 top-0 z-[100] flex h-[52px] min-h-[52px] max-h-[52px] shrink-0 items-stretch rounded-none border-b border-[rgba(255,255,255,0.2)] font-sans"
        style={{
          backgroundColor: "var(--studio-chrome-bg, #1e1e2e)",
          boxShadow: TOP_NAV_SHADOW,
        }}
      >
        <div className="flex shrink-0 items-center pl-6">
          <button
            type="button"
            className="flex h-full items-center gap-2 bg-transparent text-left font-sans no-underline outline-none focus-visible:ring-2 focus-visible:ring-[#4096ff] focus-visible:ring-offset-2 focus-visible:ring-offset-[#1e1e2e]"
            onClick={onLogoClick}
            aria-label="返回开始页"
          >
            <span
              aria-hidden
              key={logoAnimKey}
              className={[
                "flex h-[18px] w-[18px] shrink-0 items-center justify-center text-[#4096ff]",
                logoAnimKey > 0 ? "zx-logo-pop-anim" : "",
              ].join(" ")}
            >
              <IconBot size={LOGO_ICON} strokeWidth={MODULE_STROKE} className="text-current" />
            </span>
            <span className="text-[16px] font-semibold leading-none tracking-tight text-white">ZhiXing Studio</span>
          </button>
        </div>

        <div className="relative flex min-h-0 min-w-0 flex-1 items-center pl-6">
          {showLeftArrow ? (
            <button
              type="button"
              aria-label="向左滚动导航"
              className="absolute left-1 z-[1] flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-[#a0a0a0] shadow-sm backdrop-blur-sm transition-[color,transform,border-color,background-color] hover:scale-105 hover:border-white hover:bg-[rgba(255,255,255,0.05)] hover:text-white"
              style={{ borderColor: POPOVER_BORDER, backgroundColor: "rgba(30,30,46,0.95)" }}
              onClick={() => scrollNav("left")}
            >
              <IconChevronLeft size={16} strokeWidth={2} className="text-current" aria-hidden />
            </button>
          ) : null}
          <nav
            ref={scrollRef}
            onScroll={updateScrollArrows}
            className={[
              "flex h-full min-h-0 min-w-0 flex-1 items-center gap-6 overflow-x-auto overflow-y-hidden pr-2 font-sans [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden",
              showLeftArrow ? "pl-9" : "",
              showRightArrow ? "pr-9" : "",
            ].join(" ")}
            aria-label="核心模块"
            style={{ WebkitOverflowScrolling: "touch" }}
          >
            <div className="flex min-w-max items-center gap-6">
              {navLoadError ? (
                <button
                  type="button"
                  className="shrink-0 rounded-lg border border-[#444444] bg-[rgba(0,0,0,0.2)] px-2 py-1 text-[11px] font-semibold text-[#ff6b6b] outline-none transition-colors hover:bg-[rgba(255,255,255,0.06)] focus-visible:ring-2 focus-visible:ring-[#4096ff] focus-visible:ring-offset-2 focus-visible:ring-offset-[#1e1e2e]"
                  title={navLoadError}
                  onClick={() => void loadNavModules({ force: true })}
                >
                  重试导航
                </button>
              ) : null}
              {navModules.map((m) => {
                const cfg = moduleConfigCache[m.id]?.data;
                const locked = Boolean(m.disabled) || m.allowed === false || cfg?.permission === "deny";
                return (
                  <ModuleNavButton
                    key={m.id}
                    targetPath={m.path}
                    isActive={isNavPathActive(path, m.path)}
                    label={m.name}
                    locked={locked}
                    icon={<NavModuleIcon iconKey={m.iconKey} />}
                  />
                );
              })}
            </div>
          </nav>
          {showRightArrow ? (
            <button
              type="button"
              aria-label="向右滚动导航"
              className="absolute right-1 z-[1] flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-[#a0a0a0] shadow-sm backdrop-blur-sm transition-[color,transform,border-color,background-color] hover:scale-105 hover:border-white hover:bg-[rgba(255,255,255,0.05)] hover:text-white"
              style={{ borderColor: POPOVER_BORDER, backgroundColor: "rgba(30,30,46,0.95)" }}
              onClick={() => scrollNav("right")}
            >
              <IconChevronRight size={16} strokeWidth={2} className="text-current" aria-hidden />
            </button>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-4 pr-6">
          <button
            type="button"
            ref={avatarButtonRef}
            aria-expanded={userMenuOpen}
            aria-haspopup="menu"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[#444444] bg-transparent text-[#a0a0a0] outline-none transition-[transform,border-color,color] hover:scale-105 hover:border-white focus-visible:ring-2 focus-visible:ring-[#4096ff] focus-visible:ring-offset-2 focus-visible:ring-offset-[#1e1e2e]"
            onClick={() => (userMenuOpen ? setUserMenuOpen(false) : openUserMenu())}
          >
            <IconUser size={16} strokeWidth={2} className="text-current" aria-hidden />
          </button>
          <button
            type="button"
            aria-label="帮助中心"
            className="flex h-[52px] w-8 shrink-0 items-center justify-center rounded-lg text-[#a0a0a0] outline-none transition-colors hover:text-white focus-visible:ring-2 focus-visible:ring-[#4096ff] focus-visible:ring-offset-2 focus-visible:ring-offset-[#1e1e2e]"
            onClick={() => {
              setHelpTab("guide");
              setHelpOpen(true);
            }}
          >
            <IconHelpCircle size={16} strokeWidth={MODULE_STROKE} className="text-current" aria-hidden />
          </button>
        </div>
      </header>

      {userMenuOpen && userMenuPos ? (
        <div
          id="zx-user-menu-popover"
          role="menu"
          className="fixed z-[120] min-w-[11rem] rounded-lg border py-1 text-white shadow-[var(--zx-shadow-soft)]"
          style={{
            top: userMenuPos.top,
            right: userMenuPos.right,
            backgroundColor: POPOVER_BG,
            borderColor: POPOVER_BORDER,
          }}
        >
          <button
            type="button"
            role="menuitem"
            className="w-full rounded-lg px-3 py-2 text-left text-[12px] text-white/90 outline-none transition-colors hover:bg-[#333333]"
            onClick={() => setUserMenuOpen(false)}
          >
            账户信息
            <span className="mt-1 block text-[11px] text-white/70">演示用户 · 占位</span>
          </button>
          <div className="h-px bg-[#444444]" role="separator" />
          <button
            type="button"
            role="menuitem"
            className="w-full rounded-lg px-3 py-2 text-left text-[13px] text-white outline-none transition-colors hover:bg-[#333333]"
            onClick={() => setUserMenuOpen(false)}
          >
            退出登录
          </button>
        </div>
      ) : null}

      {helpOpen ? (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 font-sans" aria-modal="true" role="dialog">
          <button
            type="button"
            aria-label="关闭帮助"
            className="absolute inset-0 bg-black/55"
            onClick={() => setHelpOpen(false)}
          />
          <div
            className="relative z-[1] flex max-h-[min(80vh,520px)] w-full max-w-lg flex-col overflow-hidden rounded-lg border text-white shadow-[var(--zx-shadow-soft)]"
            style={{
              backgroundColor: POPOVER_BG,
              borderColor: POPOVER_BORDER,
            }}
          >
            <div
              className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3"
              style={{ borderColor: POPOVER_BORDER }}
            >
              <h2 className="text-[15px] font-semibold text-white">帮助中心</h2>
              <button
                type="button"
                className="rounded-lg px-2 py-1 text-[12px] text-white/80 outline-none transition-colors hover:bg-[#333333] hover:text-white"
                onClick={() => setHelpOpen(false)}
              >
                关闭
              </button>
            </div>
            <div className="flex flex-wrap gap-2 border-b px-5 py-3" style={{ borderColor: POPOVER_BORDER }}>
              <button
                type="button"
                className={[
                  helpTabBtn,
                  helpTab === "guide" ? "bg-[#333333] text-white" : "bg-transparent text-white/75 hover:bg-[#333333] hover:text-white",
                ].join(" ")}
                onClick={() => setHelpTab("guide")}
              >
                使用说明
              </button>
              <button
                type="button"
                className={[
                  helpTabBtn,
                  helpTab === "faq" ? "bg-[#333333] text-white" : "bg-transparent text-white/75 hover:bg-[#333333] hover:text-white",
                ].join(" ")}
                onClick={() => setHelpTab("faq")}
              >
                常见问题
              </button>
              <button
                type="button"
                className={[
                  helpTabBtn,
                  helpTab === "support" ? "bg-[#333333] text-white" : "bg-transparent text-white/75 hover:bg-[#333333] hover:text-white",
                ].join(" ")}
                onClick={() => setHelpTab("support")}
              >
                联系客服
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 text-[13px] leading-relaxed text-white/90">
              {helpTab === "guide" ? (
                <section>
                  <p className="text-white/75">
                    在「兵工厂」中编排 Agent 流程；「试车场」用于 Benchmark；「历史」查看运行记录；「设置」调整全局选项。本弹窗为占位说明，完整文档将后续接入。
                  </p>
                </section>
              ) : null}
              {helpTab === "faq" ? (
                <section>
                  <ul className="list-disc space-y-2 pl-4 text-white/75">
                    <li>流程未完成配置时无法运行或保存，请检查各槽位算法与参数。</li>
                    <li>侧栏「流程编辑」与顶栏「兵工厂」均进入同一模块。</li>
                  </ul>
                </section>
              ) : null}
              {helpTab === "support" ? (
                <section className="text-white/75">
                  <p className="mb-3">如需人工协助，请通过以下方式联系我们（占位）：</p>
                  <ul className="list-none space-y-2 pl-0">
                    <li>企业微信 / 飞书：稍后接入</li>
                    <li>邮件：support@zhixing.studio（示例）</li>
                  </ul>
                </section>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
