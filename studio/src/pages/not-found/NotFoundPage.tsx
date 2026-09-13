import { Link } from "react-router-dom";

/** Render a safe unknown-route state without guessing a resource identity. */
export function NotFoundPage() {
  return (
    <div className="flex h-full items-center justify-center bg-[var(--zx-canvas)] p-8 text-center">
      <div className="max-w-md rounded-2xl border border-[var(--zx-border-light)] bg-[var(--zx-panel)] p-8 shadow-[var(--zx-shadow-soft)]">
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-primary)]">Not found</p>
        <h1 className="mt-2 text-[18px] font-semibold text-[color:var(--zx-text-title)]">这个 Studio 页面不存在</h1>
        <p className="mt-3 text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">地址可能已失效。Studio 不会根据缓存或最近访问记录替你选择另一个 Agent、Run 或 Experiment。</p>
        <Link to="/" className="mt-5 inline-block rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[11px] font-semibold text-white no-underline">返回首页</Link>
      </div>
    </div>
  );
}
