import { Link } from "react-router-dom";
import { STUDIO_ONBOARDING_STEPS } from "../model/useStudioOnboarding";

/** Render a dismissible research workflow guide whose readiness label is authoritative. */
export function StudioOnboardingCard({
  readiness,
  onDismiss,
}: {
  readiness: "ready" | "blocked" | "unknown";
  onDismiss: () => void;
}) {
  return (
    <section className="rounded-2xl border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] p-5" aria-labelledby="onboarding-heading">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-primary)]">首次使用</p>
          <h2 id="onboarding-heading" className="mt-1 text-[15px] font-semibold text-[color:var(--zx-text-title)]">完成一次 Mobile Agent 研究闭环</h2>
        </div>
        <button type="button" className="text-[11px] text-[color:var(--zx-text-muted)]" onClick={onDismiss}>暂时隐藏</button>
      </div>
      <ol className="mt-4 grid gap-2 md:grid-cols-5">
        {STUDIO_ONBOARDING_STEPS.map((step, index) => <li key={step.id} data-prerequisite={step.prerequisite} className="rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-panel)] px-3 py-3 text-[11px] text-[color:var(--zx-text-body)]"><span className="mr-2 font-semibold text-[color:var(--zx-primary)]">{index + 1}</span>{step.label}{step.id === "run" && readiness !== "ready" ? <span className="mt-1 block text-[9px] text-amber-600">需先完成运行环境配置</span> : null}</li>)}
      </ol>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-[11px] text-[color:var(--zx-text-muted)]">运行环境：{readiness === "ready" ? "已就绪" : readiness === "blocked" ? "需要配置" : "状态未知"}。引导不会创建假 Run 或设备证据。</p>
        <Link to="/agents?create=example" className="rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[11px] font-semibold text-white no-underline">从正式示例开始</Link>
      </div>
    </section>
  );
}
