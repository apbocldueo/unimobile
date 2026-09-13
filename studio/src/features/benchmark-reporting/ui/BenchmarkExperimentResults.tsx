import { useEffect, useMemo, useState } from "react";
import {
  BENCHMARK_METRIC_DEFINITIONS,
  formatBenchmarkDuration,
  formatBenchmarkRate,
  formatBenchmarkUsageCoverage,
  formatBenchmarkVariance,
  formatBenchmarkWilsonInterval,
  paginateBenchmarkResults,
  type BenchmarkExperimentResultsProjection,
  type BenchmarkResultsPage,
} from "../model/benchmarkComparisonMetrics";
import type { BenchmarkReportComponentState } from "../model/benchmarkReportState";

type BenchmarkExperimentResultsProps = {
  results: BenchmarkExperimentResultsProjection | null;
  state: BenchmarkReportComponentState;
  onRetry: () => void;
};

/** Render formal Experiment-level metrics without deriving statistical facts. */
export function BenchmarkExperimentResults({
  results,
  state,
  onRetry,
}: BenchmarkExperimentResultsProps) {
  const [expanded, setExpanded] = useState(true);
  const [metricPage, setMetricPage] = useState(1);
  const [comparisonPage, setComparisonPage] = useState(1);

  useEffect(() => {
    setMetricPage(1);
    setComparisonPage(1);
  }, [results?.identity]);

  const metricRows = useMemo(
    () => paginateBenchmarkResults(results?.agentMetrics ?? [], metricPage),
    [metricPage, results?.agentMetrics],
  );
  const comparisonRows = useMemo(
    () => paginateBenchmarkResults(results?.comparisons ?? [], comparisonPage),
    [comparisonPage, results?.comparisons],
  );

  if (state.kind !== "available" || results === null) {
    return (
      <section
        aria-labelledby="benchmark-experiment-results-title"
        className="shrink-0 border-b border-[var(--zx-border-light)] bg-[var(--zx-card)] px-4 py-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[9px] uppercase tracking-[0.18em] text-[color:var(--zx-text-muted)]">
              Formal Experiment report
            </p>
            <h2
              id="benchmark-experiment-results-title"
              className="text-[13px] font-semibold text-[color:var(--zx-text-title)]"
            >
              Experiment Results
            </h2>
          </div>
          <div className="text-right">
            <p
              role="status"
              data-state={state.kind}
              className="text-[10px] text-[color:var(--zx-text-muted)]"
            >
              {state.message}
            </p>
            {state.retryable ? (
              <button
                type="button"
                onClick={onRetry}
                className="mt-1 text-[10px] text-[color:var(--zx-primary)] underline"
              >
                Retry Experiment report
              </button>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  /** Toggle only the scrollable details while retaining the claim boundary. */
  const toggleExpanded = () => setExpanded((current) => !current);

  return (
    <section
      aria-labelledby="benchmark-experiment-results-title"
      className="shrink-0 border-b border-[var(--zx-border-light)] bg-[var(--zx-card)]"
    >
      <header className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
        <div>
          <p className="text-[9px] uppercase tracking-[0.18em] text-[color:var(--zx-text-muted)]">
            Formal Experiment report · schema {results.schemaVersion}
          </p>
          <h2
            id="benchmark-experiment-results-title"
            className="text-[13px] font-semibold text-[color:var(--zx-text-title)]"
          >
            Experiment Results
          </h2>
          <p className="mt-1 text-[10px] text-[color:var(--zx-text-muted)]">
            Outcome counts and per-Agent eligible denominators are kept separate.
          </p>
        </div>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls="benchmark-experiment-results-body"
          onClick={toggleExpanded}
          className="rounded-md border border-[var(--zx-border-light)] px-3 py-1.5 text-[10px] text-[color:var(--zx-text-muted)] hover:text-[color:var(--zx-text-title)]"
        >
          {expanded ? "Collapse details" : "Expand details"}
        </button>
      </header>

      <div
        role="note"
        className="mx-4 mb-3 rounded-md border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-[10px] text-sky-200"
      >
        {results.significanceBoundary}
      </div>

      {expanded ? (
        <div
          id="benchmark-experiment-results-body"
          className="max-h-[36vh] space-y-4 overflow-y-auto px-4 pb-4"
        >
          <section aria-labelledby="benchmark-outcomes-title">
            <h3
              id="benchmark-outcomes-title"
              className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-muted)]"
            >
              Outcome distribution
            </h3>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {results.outcomes.map((outcome) => (
                <article
                  key={outcome.outcome}
                  className="rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] px-3 py-2"
                >
                  <p className="text-[9px] text-[color:var(--zx-text-muted)]">
                    {outcome.label}
                  </p>
                  <p className="mt-1 text-[18px] font-semibold tabular-nums text-[color:var(--zx-text-title)]">
                    {outcome.count}
                  </p>
                </article>
              ))}
            </div>
          </section>

          <MetricDefinitions />

          <section aria-labelledby="benchmark-agent-metrics-title">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3
                id="benchmark-agent-metrics-title"
                className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-muted)]"
              >
                Per-Agent metrics
              </h3>
              <PageControls
                label="Agent metrics"
                page={metricRows}
                onPageChange={setMetricPage}
              />
            </div>
            {metricRows.total === 0 ? (
              <EmptyResult text="The formal report contains no Agent metrics." />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-[var(--zx-border-light)]">
                <table
                  aria-label="Per-Agent metrics"
                  className="w-full min-w-[76rem] border-collapse text-left text-[10px]"
                >
                  <thead className="bg-[var(--zx-canvas)] text-[color:var(--zx-text-muted)]">
                    <tr>
                      <th scope="col" className="px-3 py-2">Agent</th>
                      <th scope="col" className="px-3 py-2">Outcomes P/F/I/S</th>
                      <th scope="col" className="px-3 py-2">Eligible</th>
                      <th scope="col" className="px-3 py-2">Micro success</th>
                      <th scope="col" className="px-3 py-2">Macro success</th>
                      <th scope="col" className="px-3 py-2">Mean duration</th>
                      <th scope="col" className="px-3 py-2">Median duration</th>
                      <th scope="col" className="px-3 py-2">Sample variance</th>
                      <th scope="col" className="px-3 py-2">Wilson 95%</th>
                      <th scope="col" className="px-3 py-2">Usage coverage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metricRows.items.map((metric) => (
                      <tr
                        key={metric.agentId}
                        className="border-t border-[var(--zx-border-light)] text-[color:var(--zx-text-title)]"
                      >
                        <th scope="row" className="px-3 py-2 font-medium">
                          {metric.agentId}
                        </th>
                        <td className="px-3 py-2 tabular-nums">
                          {metric.counts.pass}/{metric.counts.fail}/
                          {metric.counts.invalid}/{metric.counts.skipped}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {metric.eligibleCount}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {formatBenchmarkRate(metric.successRateMicro)}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {formatBenchmarkRate(metric.successRateMacro)}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {formatBenchmarkDuration(metric.durationMeanMs)}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {formatBenchmarkDuration(metric.durationMedianMs)}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {formatBenchmarkVariance(
                            metric.durationSampleVariance,
                          )}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {formatBenchmarkWilsonInterval(
                            metric.wilsonInterval95,
                          )}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {formatBenchmarkUsageCoverage(
                            metric.usageAvailableRuns,
                            metric.eligibleCount,
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section aria-labelledby="benchmark-comparisons-title">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3
                  id="benchmark-comparisons-title"
                  className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-muted)]"
                >
                  Pairwise comparisons
                </h3>
                <p className="mt-1 text-[9px] text-[color:var(--zx-text-muted)]">
                  Backend order and Agent orientation are preserved.
                </p>
              </div>
              <PageControls
                label="Pairwise comparisons"
                page={comparisonRows}
                onPageChange={setComparisonPage}
              />
            </div>
            {comparisonRows.total === 0 ? (
              <EmptyResult text="No Agent pair is available to compare in this report." />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-[var(--zx-border-light)]">
                <table
                  aria-label="Pairwise comparisons"
                  className="w-full min-w-[58rem] border-collapse text-left text-[10px]"
                >
                  <thead className="bg-[var(--zx-canvas)] text-[color:var(--zx-text-muted)]">
                    <tr>
                      <th scope="col" className="px-3 py-2">Left Agent</th>
                      <th scope="col" className="px-3 py-2">Right Agent</th>
                      <th scope="col" className="px-3 py-2">Matched scope</th>
                      <th scope="col" className="px-3 py-2">Matched</th>
                      <th scope="col" className="px-3 py-2">Unmatched eligible</th>
                      <th scope="col" className="px-3 py-2">Left wins</th>
                      <th scope="col" className="px-3 py-2">Right wins</th>
                      <th scope="col" className="px-3 py-2">Ties</th>
                      <th scope="col" className="px-3 py-2">Inference</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparisonRows.items.map((comparison) => (
                      <tr
                        key={`${comparison.leftAgentId}\0${comparison.rightAgentId}`}
                        className="border-t border-[var(--zx-border-light)] text-[color:var(--zx-text-title)]"
                      >
                        <th scope="row" className="px-3 py-2 font-medium">
                          {comparison.leftAgentId}
                        </th>
                        <td className="px-3 py-2">{comparison.rightAgentId}</td>
                        <td className="px-3 py-2">{comparison.scopeLabel}</td>
                        <td className="px-3 py-2 tabular-nums">
                          {comparison.matchedCount}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {comparison.unmatchedEligibleCount}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {comparison.leftWins}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {comparison.rightWins}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {comparison.ties}
                        </td>
                        <td className="px-3 py-2">
                          No significance claimed
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section aria-labelledby="benchmark-fairness-title">
            <h3
              id="benchmark-fairness-title"
              className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-muted)]"
            >
              Fairness warnings
            </h3>
            {results.fairnessWarnings.length === 0 ? (
              <EmptyResult text="The formal report contains no fairness warning codes." />
            ) : (
              <ul className="space-y-2">
                {results.fairnessWarnings.map((warning, index) => (
                  <li
                    key={`${warning.code}\0${index}`}
                    className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2"
                  >
                    <code className="break-all text-[10px] text-amber-200">
                      {warning.code}
                    </code>
                    <p className="mt-1 text-[10px] text-[color:var(--zx-text-muted)]">
                      {warning.description}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}

/** Render concise schema-1.0 metric definitions for report readers. */
function MetricDefinitions() {
  return (
    <details className="rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] px-3 py-2">
      <summary className="cursor-pointer text-[10px] font-medium text-[color:var(--zx-text-title)]">
        Metric definitions and units
      </summary>
      <dl className="mt-2 grid gap-2 text-[9px] text-[color:var(--zx-text-muted)] md:grid-cols-2">
        {Object.entries(BENCHMARK_METRIC_DEFINITIONS).map(
          ([name, definition]) => (
            <div key={name}>
              <dt className="font-medium uppercase text-[color:var(--zx-text-title)]">
                {name}
              </dt>
              <dd>{definition}</dd>
            </div>
          ),
        )}
      </dl>
    </details>
  );
}

/** Render a truthful empty collection state rather than a transport failure. */
function EmptyResult({ text }: { text: string }) {
  return (
    <p className="rounded-lg border border-dashed border-[var(--zx-border-light)] px-3 py-3 text-[10px] text-[color:var(--zx-text-muted)]">
      {text}
    </p>
  );
}

/** Render stable local pagination without persisting or reordering report rows. */
function PageControls<T>({
  label,
  page,
  onPageChange,
}: {
  label: string;
  page: BenchmarkResultsPage<T>;
  onPageChange: (page: number) => void;
}) {
  if (page.total === 0) return null;
  /** Move to the prior bounded local page. */
  const previous = () => onPageChange(Math.max(1, page.page - 1));
  /** Move to the next bounded local page. */
  const next = () => onPageChange(Math.min(page.pageCount, page.page + 1));
  return (
    <nav
      aria-label={`${label} pagination`}
      className="flex items-center gap-2 text-[9px] text-[color:var(--zx-text-muted)]"
    >
      <span>
        {page.start}–{page.end} of {page.total}
      </span>
      <button
        type="button"
        aria-label={`Previous ${label} page`}
        disabled={page.page === 1}
        onClick={previous}
        className="rounded border border-[var(--zx-border-light)] px-2 py-1 disabled:opacity-40"
      >
        Previous
      </button>
      <span>
        {page.page}/{page.pageCount}
      </span>
      <button
        type="button"
        aria-label={`Next ${label} page`}
        disabled={page.page === page.pageCount}
        onClick={next}
        className="rounded border border-[var(--zx-border-light)] px-2 py-1 disabled:opacity-40"
      >
        Next
      </button>
    </nav>
  );
}
