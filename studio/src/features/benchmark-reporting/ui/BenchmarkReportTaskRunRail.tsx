import type {
  BenchmarkReportRunItem,
  BenchmarkReportSelection,
} from "../model/benchmarkReportProjection";
import type { BenchmarkReportComponentState } from "../model/benchmarkReportState";

type BenchmarkReportTaskRunRailProps = {
  items: BenchmarkReportRunItem[];
  selection: BenchmarkReportSelection | null;
  state: BenchmarkReportComponentState;
  onSelect: (taskRunId: string) => void;
  onRetry: () => void;
};

/** Render stable planned TaskRuns with independent three-axis summaries. */
export function BenchmarkReportTaskRunRail({
  items,
  selection,
  state,
  onSelect,
  onRetry,
}: BenchmarkReportTaskRunRailProps) {
  return (
    <aside
      aria-label="Report TaskRun rail"
      className="h-full min-h-0 overflow-auto border-r border-[var(--zx-divider-ui)] bg-[var(--zx-card)] p-3"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <strong className="text-[11px] text-[color:var(--zx-text-title)]">
          TaskRuns · {items.length}
        </strong>
        {state.retryable ? (
          <button
            type="button"
            onClick={onRetry}
            className="text-[10px] text-[color:var(--zx-primary)] underline"
          >
            Retry
          </button>
        ) : null}
      </div>
      {selection?.invalidRequestedSelection ? (
        <p
          role="alert"
          className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-[10px] text-amber-200"
        >
          URL TaskRun selection is outside this verified report; showing the
          deterministic first selectable run.
        </p>
      ) : null}
      {items.length === 0 ? (
        <p className="rounded-lg border border-[var(--zx-border-light)] p-3 text-[10px] text-[color:var(--zx-text-muted)]">
          No published run summaries are available.
        </p>
      ) : (
        <ol className="space-y-2">
          {items.map((item) => {
            const selected =
              selection?.selectedTaskRunId !== null
              && item.taskRunId === selection?.selectedTaskRunId;
            const selectable =
              item.taskRunId !== null && item.integrityError === null;
            return (
              <li key={item.coreTaskRunId}>
                <button
                  type="button"
                  disabled={!selectable}
                  aria-pressed={selected}
                  onClick={() => {
                    if (item.taskRunId) onSelect(item.taskRunId);
                  }}
                  className={`w-full rounded-lg border p-3 text-left disabled:cursor-not-allowed disabled:opacity-60 ${
                    selected
                      ? "border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)]"
                      : "border-[var(--zx-border-light)] bg-[var(--zx-canvas)]"
                  }`}
                >
                  <span className="text-[9px] uppercase tracking-[0.1em] text-[color:var(--zx-text-muted)]">
                    {item.order === null ? "unmapped" : `#${item.order + 1}`}
                    {" · "}
                    {item.summary.agentId}
                  </span>
                  <strong className="mt-1 block truncate text-[11px] text-[color:var(--zx-text-title)]">
                    {item.summary.taskId} · repeat {item.summary.repeat + 1}
                  </strong>
                  <span className="mt-2 block text-[9px] text-[color:var(--zx-text-muted)]">
                    service {item.axes.serviceLifecycle ?? "unavailable"}
                  </span>
                  <span className="block text-[9px] text-[color:var(--zx-text-muted)]">
                    Agent {item.axes.agentStatus ?? "unavailable"}
                  </span>
                  <span className="block text-[9px] text-[color:var(--zx-text-muted)]">
                    Benchmark {item.axes.benchmarkOutcome ?? "unavailable"}
                  </span>
                  {item.integrityError ? (
                    <span className="mt-2 block text-[9px] text-rose-300">
                      {item.integrityError}
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </aside>
  );
}
