import { IconAlertCircle, IconCheck } from "@/components/icons/StudioIcons";
import { useToastStore, type ToastTone } from "@/stores/toastStore";

function toneBorder(t?: ToastTone) {
  if (t === "success") return "var(--zx-primary-border)";
  if (t === "warning") return "rgba(255, 180, 120, 0.45)";
  if (t === "error") return "var(--zx-primary-border)";
  return "var(--zx-border-light)";
}

function toneBg(t?: ToastTone) {
  if (t === "success") return "var(--zx-primary-soft-strong)";
  if (t === "warning") return "rgba(255, 160, 80, 0.12)";
  if (t === "error") return "rgba(35, 40, 48, 0.95)";
  return "var(--zx-panel)";
}

/**
 * 全局轻提示：靠右下角，约 3–5s 自动消失，不挡顶栏与侧栏主要操作。
 */
export function ToastViewport() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  if (toasts.length === 0) return null;

  return (
    <div
      className={[
        "pointer-events-none fixed right-6 z-[9999] flex w-[min(92vw,24rem)] flex-col items-end gap-2",
        "bottom-8",
      ].join(" ")}
      aria-live="polite"
      aria-relevant="additions"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className="pointer-events-auto zx-toast-item flex w-full items-start gap-3 rounded-xl border px-4 py-3 shadow-[var(--zx-shadow-soft)]"
          style={{
            borderColor: toneBorder(t.tone),
            backgroundColor: toneBg(t.tone),
            color: "var(--zx-text-body)",
          }}
          role="status"
        >
          {t.tone === "success" ? (
            <IconCheck size={18} strokeWidth={2.25} className="mt-0.5 shrink-0" style={{ color: "var(--zx-primary)" }} aria-hidden />
          ) : t.tone === "error" ? (
            <IconAlertCircle size={18} strokeWidth={2.25} className="mt-0.5 shrink-0" style={{ color: "var(--zx-primary)" }} aria-hidden />
          ) : (
            <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-[color:var(--zx-primary)]" aria-hidden />
          )}
          <p className="min-w-0 flex-1 text-[13px] leading-snug">{t.message}</p>
          <button
            type="button"
            className="shrink-0 rounded-md px-1.5 py-0.5 text-[11px] text-[color:var(--zx-text-muted)] transition-colors hover:text-[color:var(--zx-text-title)]"
            onClick={() => dismiss(t.id)}
          >
            关闭
          </button>
        </div>
      ))}
    </div>
  );
}
