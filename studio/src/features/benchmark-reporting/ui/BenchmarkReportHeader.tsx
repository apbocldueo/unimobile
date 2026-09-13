import type { BenchmarkExperimentResource } from "@/entities/benchmark-experiment";
import type { BenchmarkReportComponentState } from "../model/benchmarkReportState";

type BenchmarkReportHeaderProps = {
  experiment: BenchmarkExperimentResource;
  publicationState: BenchmarkReportComponentState;
  refreshing: boolean;
  exportDisabled: boolean;
  onBackToMonitor: () => void;
  onRefresh: () => void;
  onOpenExport: () => void;
};

/** Render immutable Experiment identity and publication actions. */
export function BenchmarkReportHeader({
  experiment,
  publicationState,
  refreshing,
  exportDisabled,
  onBackToMonitor,
  onRefresh,
  onOpenExport,
}: BenchmarkReportHeaderProps) {
  return (
    <header className="flex min-h-[92px] flex-wrap items-center justify-between gap-4 border-b border-[var(--zx-divider-ui)] bg-[var(--zx-card)] px-5 py-3">
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-primary)]">
          Benchmark Experiment · Report
        </p>
        <h1 className="mt-1 truncate text-[15px] font-semibold text-[color:var(--zx-text-title)]">
          {experiment.definition.source.packageIdentity}
        </h1>
        <code className="block truncate text-[10px] text-[color:var(--zx-text-muted)]">
          {experiment.experimentId}
        </code>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <HeaderFact label="Lifecycle" value={experiment.lifecycle} />
        <HeaderFact
          label="Publication"
          value={publicationState.kind}
        />
        <HeaderFact
          label="Plan identity"
          value={shortIdentity(
            experiment.definition.source.benchmarkPlanIdentity,
          )}
        />
        <HeaderFact
          label="Protocol identity"
          value={shortIdentity(
            experiment.definition.source.experimentProtocolIdentity,
          )}
        />
        <button
          type="button"
          disabled={exportDisabled}
          onClick={onOpenExport}
          className="rounded-lg border border-[var(--zx-border-light)] px-3 py-2 text-[11px] font-semibold text-[color:var(--zx-text-title)] disabled:opacity-50"
        >
          Export
        </button>
        <button
          type="button"
          onClick={onBackToMonitor}
          className="rounded-lg border border-[var(--zx-border-light)] px-3 py-2 text-[11px] font-semibold text-[color:var(--zx-text-title)]"
        >
          Back to Monitor
        </button>
        <button
          type="button"
          disabled={refreshing}
          onClick={onRefresh}
          className="rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-3 py-2 text-[11px] font-semibold text-[color:var(--zx-primary)] disabled:opacity-50"
        >
          {refreshing ? "Refreshing…" : "Refresh report"}
        </button>
      </div>
    </header>
  );
}

/** Abbreviate a canonical identity only for display, never comparison. */
function shortIdentity(value: string): string {
  return value.length > 18 ? `${value.slice(0, 12)}…${value.slice(-6)}` : value;
}

/** Render one independently labeled immutable report fact. */
function HeaderFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-[92px] rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] px-3 py-2">
      <span className="block text-[9px] uppercase tracking-[0.1em] text-[color:var(--zx-text-muted)]">
        {label}
      </span>
      <strong
        data-value={value}
        className="mt-0.5 block max-w-32 truncate text-[10px] text-[color:var(--zx-text-title)]"
      >
        {value}
      </strong>
    </div>
  );
}
