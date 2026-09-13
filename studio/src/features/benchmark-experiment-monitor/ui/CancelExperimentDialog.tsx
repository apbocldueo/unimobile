type CancelExperimentDialogProps = {
  open: boolean;
  pending: boolean;
  error: string | null;
  onDismiss: () => void;
  onConfirm: () => void;
};

/** Render an explicit accepted-only cooperative cancellation confirmation. */
export function CancelExperimentDialog({
  open,
  pending,
  error,
  onDismiss,
  onConfirm,
}: CancelExperimentDialogProps) {
  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cancel-experiment-title"
      className="absolute inset-0 z-50 grid place-items-center bg-black/65 p-6"
    >
      <section className="w-full max-w-md rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-5 shadow-2xl">
        <h2
          id="cancel-experiment-title"
          className="text-[15px] font-semibold text-[color:var(--zx-text-title)]"
        >
          取消 accepted Experiment？
        </h2>
        <p className="mt-2 text-[11px] leading-relaxed text-[color:var(--zx-text-muted)]">
          这是显式协作命令。Monitor 不会在关闭页面、断开 SSE 或跳转 Replay 时自动取消。
        </p>
        {error ? (
          <p role="alert" className="mt-3 text-[11px] text-rose-300">
            {error}
          </p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            disabled={pending}
            onClick={onDismiss}
            className="rounded-lg border border-[var(--zx-border-light)] px-3 py-2 text-[11px] text-[color:var(--zx-text-body)] disabled:opacity-50"
          >
            返回
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={onConfirm}
            className="rounded-lg bg-rose-600 px-3 py-2 text-[11px] font-semibold text-white disabled:opacity-50"
          >
            {pending ? "提交中…" : "确认取消"}
          </button>
        </div>
      </section>
    </div>
  );
}
