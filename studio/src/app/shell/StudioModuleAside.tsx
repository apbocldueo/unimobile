import type { ReactNode } from "react";

/** 非兵工厂模块侧栏外框：与 GlobalSidebar 宽度、圆角、底色一致（第四章） */
export function StudioModuleAside({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <aside
      className="flex w-[13.5rem] shrink-0 flex-col rounded-xl border shadow-[var(--zx-shadow-soft)]"
      style={{
        backgroundColor: "var(--zx-sidebar)",
        borderColor: "var(--zx-border-light)",
      }}
    >
      <div className="px-4 py-3">
        <div className="zx-title tracking-tight text-[color:var(--zx-text-title)]">{title}</div>
        {subtitle ? (
          <p className="mt-1 text-[11px] leading-snug text-[color:var(--zx-text-muted)]">{subtitle}</p>
        ) : null}
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-2 px-3 pb-4 pt-1">{children}</div>
    </aside>
  );
}
