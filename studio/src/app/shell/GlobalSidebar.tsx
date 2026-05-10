import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { IconBot, IconHelpCircle, IconSave } from "@/components/icons/StudioIcons";

const ICON = 18;
const STROKE = 1.75;

/** 辅助区：透明底、方角，hover 深灰底（与全局辅助按钮一致） */
function AuxShell({ children }: { children: ReactNode }) {
  return (
    <div className="studio-aux-hit flex items-center gap-3 px-3 py-2.5 text-[13px] font-medium text-[color:var(--zx-text-muted)] hover:text-[color:var(--zx-text-body)]">
      {children}
    </div>
  );
}

/**
 * 左侧栏：核心入口「流程编辑」；细分隔线下为辅助操作（保存、帮助）。
 */
export function GlobalSidebar() {
  return (
    <aside
      className="flex w-[13.5rem] shrink-0 flex-col rounded-xl border shadow-[var(--zx-shadow-soft)]"
      style={{
        backgroundColor: "var(--zx-sidebar)",
        borderColor: "var(--zx-border-light)",
      }}
    >
      <div className="px-4 py-3">
        <div className="zx-title tracking-tight text-[color:var(--zx-text-title)]">ZhiXing Studio</div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-6 px-3 pb-4 pt-1">
        <section aria-label="核心入口" className="flex flex-col gap-2">
          <NavLink
            to="/builder"
            end
            className="block rounded-xl no-underline outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-sidebar)]"
          >
            {({ isActive }) => (
              <div
                className={[
                  "group relative flex items-center gap-3 rounded-xl px-3 py-3 transition-[background-color,box-shadow,color,transform]",
                  isActive
                    ? "shadow-[0_12px_32px_rgba(90,174,253,0.38)]"
                    : "hover:bg-white/[0.05]",
                ].join(" ")}
                style={
                  isActive
                    ? {
                        backgroundColor: "var(--zx-primary)",
                        color: "#ffffff",
                      }
                    : { color: "var(--zx-text-muted)" }
                }
              >
                {isActive ? (
                  <span
                    aria-hidden
                    className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-white/90"
                  />
                ) : null}
                <span
                  aria-hidden
                  className={[
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors",
                    isActive ? "bg-white/15" : "bg-black/25 group-hover:bg-black/35",
                  ].join(" ")}
                >
                  <IconBot
                    size={ICON}
                    strokeWidth={STROKE}
                    style={{ color: isActive ? "#ffffff" : "var(--zx-text-muted)" }}
                  />
                </span>
                <span className="min-w-0 flex-1 text-[13px] font-semibold leading-tight tracking-tight">
                  流程编辑
                </span>
              </div>
            )}
          </NavLink>
        </section>

        <div className="h-px shrink-0 bg-[rgba(255,255,255,0.2)]" role="separator" aria-hidden />

        <section className="flex flex-col gap-2" aria-label="辅助操作">
          <button
            type="button"
            title="即将支持"
            disabled
            className="block w-full cursor-not-allowed rounded-none border border-transparent text-left outline-none"
          >
            <div
              className="flex items-center gap-3 px-3 py-2.5 text-[13px] font-medium"
              style={{
                backgroundColor: "var(--zx-disabled-bg)",
                color: "rgba(255, 255, 255, var(--zx-disabled-text-opacity))",
              }}
            >
              <span aria-hidden className="flex h-9 w-9 shrink-0 items-center justify-center rounded-none bg-black/15">
                <IconSave size={ICON} strokeWidth={STROKE} style={{ color: "rgba(255,255,255,0.45)" }} />
              </span>
              <span className="min-w-0 flex-1 font-semibold leading-tight tracking-tight">流程保存</span>
            </div>
          </button>

          <NavLink
            to="/help"
            className="group block rounded-xl no-underline outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--zx-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--zx-sidebar)]"
          >
            {({ isActive }) => (
              <AuxShell>
                <span
                  aria-hidden
                  className={[
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors",
                    isActive ? "bg-white/[0.08]" : "bg-black/20 group-hover:bg-black/30",
                  ].join(" ")}
                >
                  <IconHelpCircle
                    size={ICON}
                    strokeWidth={STROKE}
                    style={{
                      color: isActive ? "var(--zx-text-body)" : "var(--zx-text-muted)",
                    }}
                  />
                </span>
                <span
                  className="min-w-0 flex-1 font-semibold leading-tight tracking-tight"
                  style={{ color: isActive ? "var(--zx-text-body)" : undefined }}
                >
                  帮助中心
                </span>
              </AuxShell>
            )}
          </NavLink>
        </section>
      </div>
    </aside>
  );
}
