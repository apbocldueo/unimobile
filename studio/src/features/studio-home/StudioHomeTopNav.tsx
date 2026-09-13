import { IconBot, IconHelpCircle, IconSettings, IconUser } from "@/components/icons/StudioIcons";

/** 顶栏行高：规范上限 56px（h-14），单行垂直居中，不把行高压成 1 以免裁切下行字母 */
const BAR_ROW = "flex h-14 min-h-[52px] w-full min-w-0 items-center justify-between gap-4 px-4 sm:px-6";

/** 顶栏可点击项：hover 加深背景、点击轻微缩小，与壳子页按钮反馈一致 */
const hitBase =
  "inline-flex items-center justify-center rounded-lg outline-none transition-[color,background-color,transform] duration-150 ease-out select-none active:scale-[0.97]";

const iconHit = [
  hitBase,
  "h-9 w-9 text-[color:var(--zx-text-muted)] hover:bg-[var(--zx-nav-hover-bg)] hover:text-[color:var(--zx-text-title)]",
  "focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--studio-chrome-bg)]",
].join(" ");

const ICON_SZ = 18;
const ICON_STROKE = 1.75;

/**
 * 开始页专用顶栏：与 AppShell 顶栏分离，半透明主题面 + 模糊；品牌 + 右侧操作区，中间导航可后续再加。
 */
export function StudioHomeTopNav() {
  return (
    <header
      className="fixed inset-x-0 top-0 z-[100] flex h-14 min-h-[52px] shrink-0 items-center border-b border-[color:var(--zx-divider-ui)] font-sans"
      style={{
        backgroundColor: "var(--studio-chrome-bg)",
        backdropFilter: "blur(10px)",
        WebkitBackdropFilter: "blur(10px)",
      }}
    >
      <div className={BAR_ROW}>
        <div className="flex min-w-0 items-center">
          <div
            className="flex min-w-0 items-center gap-2 text-[16px] font-semibold leading-snug tracking-tight text-[color:var(--zx-text-title)]"
            aria-label="ZhiXing Studio"
          >
            <span className="flex shrink-0 items-center text-[color:var(--zx-primary)]" aria-hidden>
              <IconBot size={20} strokeWidth={ICON_STROKE} className="text-current" />
            </span>
            <span className="whitespace-nowrap text-[color:var(--zx-text-title)]">ZhiXing Studio</span>
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-end gap-0.5">
          <button type="button" className={iconHit} title="设置（即将支持）" aria-label="设置（即将支持）">
            <IconSettings size={ICON_SZ} strokeWidth={ICON_STROKE} className="text-current" aria-hidden />
          </button>
          <button type="button" className={iconHit} title="账户（即将支持）" aria-label="账户（即将支持）">
            <IconUser size={ICON_SZ} strokeWidth={ICON_STROKE} className="text-current" aria-hidden />
          </button>
          <button type="button" className={iconHit} title="帮助中心（即将支持）" aria-label="帮助中心（即将支持）">
            <IconHelpCircle size={ICON_SZ} strokeWidth={ICON_STROKE} className="text-current" aria-hidden />
          </button>
        </div>
      </div>
    </header>
  );
}
