import type { BenchmarkExperimentResource } from "@/entities/benchmark-experiment";
import type { BenchmarkEventSessionSnapshot } from "../model/benchmarkEventSession";

type ExperimentMonitorHeaderProps = {
  experiment: BenchmarkExperimentResource;
  session: BenchmarkEventSessionSnapshot;
  completedTaskRuns: number;
  totalTaskRuns: number;
  canCancel: boolean;
  canOpenReport: boolean;
  cancelPending: boolean;
  onRequestCancel: () => void;
  onOpenReport: () => void;
};

/** Render only aggregate resource and transport facts in the Monitor header. */
export function ExperimentMonitorHeader({
  experiment,
  session,
  completedTaskRuns,
  totalTaskRuns,
  canCancel,
  canOpenReport,
  cancelPending,
  onRequestCancel,
  onOpenReport,
}: ExperimentMonitorHeaderProps) {
  return (
    <header className="flex min-h-[78px] flex-wrap items-center justify-between gap-4 border-b border-[var(--zx-divider-ui)] bg-[var(--zx-card)] px-5 py-3">
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-primary)]">
          Benchmark Experiment · Monitor
        </p>
        <h1 className="mt-1 truncate text-[15px] font-semibold text-[color:var(--zx-text-title)]">
          {experiment.definition.source.packageIdentity}
        </h1>
        <code className="block truncate text-[10px] text-[color:var(--zx-text-muted)]">
          {experiment.experimentId}
        </code>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Fact label="Lifecycle" value={experiment.lifecycle} />
        <Fact
          label="TaskRuns"
          value={`${completedTaskRuns}/${totalTaskRuns}`}
        />
        <Fact label="Connection" value={session.connection} />
        <Fact
          label="Cursor"
          value={`${session.cursor}/${Math.max(session.highWaterMark, experiment.eventHighWaterMark)}`}
        />
        {canOpenReport ? (
          <button
            type="button"
            onClick={onOpenReport}
            className="rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-3 py-2 text-[11px] font-semibold text-[color:var(--zx-primary)]"
          >
            Open Report
          </button>
        ) : null}
        {canCancel ? (
          <button
            type="button"
            disabled={cancelPending}
            onClick={onRequestCancel}
            className="rounded-lg border border-rose-500/40 px-3 py-2 text-[11px] font-semibold text-rose-300 disabled:opacity-50"
          >
            {cancelPending ? "Cancelling…" : "Cancel Experiment"}
          </button>
        ) : null}
      </div>
    </header>
  );
}

/** Render one independent header fact without combining lifecycle semantics. */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-[78px] rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] px-3 py-2">
      <span className="block text-[9px] uppercase tracking-[0.1em] text-[color:var(--zx-text-muted)]">
        {label}
      </span>
      <strong
        data-value={value}
        className="mt-0.5 block text-[11px] text-[color:var(--zx-text-title)]"
      >
        {value}
      </strong>
    </div>
  );
}
