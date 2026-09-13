import type { BenchmarkTaskRunRailItem } from "../model/benchmarkMonitor";

type TaskRunRailProps = {
  items: BenchmarkTaskRunRailItem[];
  collapsed: boolean;
  locked: boolean;
  error: string | null;
  onToggle: () => void;
  onSelect: (taskRunId: string) => void;
  onReturnToCurrent: () => void;
  onRetry: () => void;
};

/** Render plural TaskRuns outside the three-pane evidence workbench. */
export function TaskRunRail({
  items,
  collapsed,
  locked,
  error,
  onToggle,
  onSelect,
  onReturnToCurrent,
  onRetry,
}: TaskRunRailProps) {
  return (
    <aside
      aria-label="TaskRun rail"
      className={`shrink-0 border-r border-[var(--zx-divider-ui)] bg-[var(--zx-card)] ${
        collapsed ? "w-12" : "w-64"
      }`}
    >
      <div className="flex items-center justify-between border-b border-[var(--zx-divider-ui)] p-3">
        {!collapsed ? (
          <strong className="text-[11px] text-[color:var(--zx-text-title)]">
            TaskRuns · {items.length}
          </strong>
        ) : null}
        <button
          type="button"
          aria-label={collapsed ? "展开 TaskRun rail" : "折叠 TaskRun rail"}
          onClick={onToggle}
          className="rounded-md border border-[var(--zx-border-light)] px-2 py-1 text-[10px] text-[color:var(--zx-text-muted)]"
        >
          {collapsed ? "›" : "‹"}
        </button>
      </div>
      {collapsed ? null : (
        <div className="h-[calc(100%-49px)] overflow-auto p-3">
          {locked ? (
            <button
              type="button"
              onClick={onReturnToCurrent}
              className="mb-3 w-full rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-3 py-2 text-[10px] font-semibold text-[color:var(--zx-primary)]"
            >
              回到当前 TaskRun
            </button>
          ) : null}
          {error ? (
            <div
              role="alert"
              className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-[10px] text-amber-300"
            >
              <p>{error}</p>
              <button
                type="button"
                onClick={onRetry}
                className="mt-2 underline"
              >
                重试 TaskRun 查询
              </button>
            </div>
          ) : null}
          {items.length === 0 && !error ? (
            <p className="p-3 text-[10px] leading-relaxed text-[color:var(--zx-text-muted)]">
              尚无已提交 TaskRun。Experiment summary 与事件连接仍保持独立可见。
            </p>
          ) : (
            <ol className="space-y-2">
              {items.map((item) => (
                <li key={item.taskRunId}>
                  <button
                    type="button"
                    aria-pressed={item.isSelected}
                    onClick={() => onSelect(item.taskRunId)}
                    className={`w-full rounded-lg border p-3 text-left ${
                      item.isSelected
                        ? "border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)]"
                        : "border-[var(--zx-border-light)] bg-[var(--zx-canvas)]"
                    }`}
                  >
                    <span className="text-[9px] uppercase tracking-[0.1em] text-[color:var(--zx-text-muted)]">
                      #{item.order + 1}
                      {item.isCurrent ? " · current" : ""}
                    </span>
                    <strong className="mt-1 block truncate text-[11px] text-[color:var(--zx-text-title)]">
                      {item.label}
                    </strong>
                    <span className="mt-2 block text-[10px] text-[color:var(--zx-text-muted)]">
                      {item.lifecycle}
                      {item.terminalReason ? ` · ${item.terminalReason}` : ""}
                    </span>
                    <span className="mt-1 block text-[9px] text-[color:var(--zx-text-muted)]">
                      outcome {item.outcome ?? item.outcomeAvailability} · replay{" "}
                      {item.replayAvailability}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </aside>
  );
}
