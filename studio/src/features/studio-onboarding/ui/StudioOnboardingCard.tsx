import { Link } from "react-router-dom";

/** Offer actionable first-use destinations without inventing completion facts. */
export function StudioOnboardingCard({ readiness, onDismiss }: {
  readiness: "ready" | "blocked" | "unknown";
  onDismiss: () => void;
}) {
  return <section className="mt-5 rounded-xl border border-[var(--zx-border-light)] p-5" aria-labelledby="onboarding-heading">
    <div className="flex items-center justify-between gap-4"><h2 id="onboarding-heading" className="text-sm font-semibold">第一次使用，从这里继续</h2><button type="button" className="text-xs text-[color:var(--zx-text-muted)]" onClick={onDismiss}>暂时隐藏</button></div>
    <ol className="mt-4 grid gap-4 text-[13px] md:grid-cols-3">
      <li><Link className="text-[color:var(--zx-primary)]" to="/settings">1. 准备模型与设备 →</Link><p className="mt-1 text-[color:var(--zx-text-muted)]">{readiness === "blocked" ? "需要补齐运行配置。" : readiness === "ready" ? "已读取到配置；实际连接在运行时验证。" : "尚未取得配置结果，可在设置中检查。"}</p></li>
      <li><Link className="text-[color:var(--zx-primary)]" to="/agents?create=example">2. 从示例试跑 →</Link><p className="mt-1 text-[color:var(--zx-text-muted)]">确认设置首页的观察任务，无需先编辑流程图。</p></li>
      <li><Link className="text-[color:var(--zx-primary)]" to="/history">3. 查看结果，再改进 →</Link><p className="mt-1 text-[color:var(--zx-text-muted)]">检查截图和执行过程，再复制任务重试或调整设计。</p></li>
    </ol>
  </section>;
}
