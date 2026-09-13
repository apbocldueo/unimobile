import type { BenchmarkExperimentResource } from "@/entities/benchmark-experiment";
import { EvidenceOriginFacts } from "@/entities/evidence-origin";
import type {
  BenchmarkReportRunItem,
  BenchmarkRunDetailProjection,
} from "../model/benchmarkReportProjection";
import type { BenchmarkReportComponentState } from "../model/benchmarkReportState";

type BenchmarkReportFactsInspectorProps = {
  experiment: BenchmarkExperimentResource;
  selected: BenchmarkReportRunItem | null;
  detail: BenchmarkRunDetailProjection | null;
  state: BenchmarkReportComponentState;
  replayState: BenchmarkReportComponentState;
  onRetry: () => void;
  onOpenReplay: (replayId: string) => void;
};

/** Render independently verified run facts, identities, stages, and Replay. */
export function BenchmarkReportFactsInspector({
  experiment,
  selected,
  detail,
  state,
  replayState,
  onRetry,
  onOpenReplay,
}: BenchmarkReportFactsInspectorProps) {
  const axes = detail?.axes ?? selected?.axes ?? null;
  return (
    <aside
      aria-label="Benchmark report facts"
      className="h-full min-h-0 overflow-auto bg-[var(--zx-card)] p-4"
    >
      <PanelTitle title="Verified facts" />
      <div className="grid grid-cols-1 gap-2">
        <Fact
          label="Service lifecycle"
          value={axes?.serviceLifecycle ?? "unavailable"}
        />
        <Fact label="Agent status" value={axes?.agentStatus ?? "unavailable"} />
        <Fact
          label="Benchmark outcome"
          value={axes?.benchmarkOutcome ?? "unavailable"}
        />
      </div>

      {selected?.taskRun?.result ? (
        <section className="mt-5">
          <EvidenceOriginFacts
            origin={selected.taskRun.result.evidenceOrigin}
            title="Selected TaskRun provenance"
          />
        </section>
      ) : (
        <p className="mt-5 text-[10px] leading-relaxed text-[color:var(--zx-text-muted)]">
          Selected TaskRun provenance is unavailable; Report does not infer it
          from artifacts, routes, or prior page state.
        </p>
      )}

      <section className="mt-5">
        <PanelTitle title="Canonical identities" />
        <Identity
          label="Experiment"
          value={experiment.experimentId}
        />
        <Identity
          label="Benchmark plan"
          value={experiment.definition.source.benchmarkPlanIdentity}
        />
        <Identity
          label="Experiment protocol"
          value={experiment.definition.source.experimentProtocolIdentity}
        />
        {detail ? (
          <>
            <Identity label="Core run" value={detail.report.coreTaskRunId} />
            <Identity
              label="Agent graph"
              value={detail.report.identities.agentGraph}
            />
            <Identity
              label="Task instance"
              value={detail.report.identities.taskInstance}
            />
          </>
        ) : null}
      </section>

      <section className="mt-5">
        <div className="flex items-center justify-between gap-2">
          <PanelTitle title="TaskRun report" />
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
        <p
          data-state={state.kind}
          className="rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] p-3 text-[10px] leading-relaxed text-[color:var(--zx-text-muted)]"
        >
          {state.message}
        </p>
      </section>

      {detail ? (
        <section className="mt-5">
          <PanelTitle title={`Lifecycle stages · ${detail.report.stages.length}`} />
          <ol className="space-y-2">
            {detail.report.stages.map((stage, index) => (
              <li
                key={`${stage.phase}-${index}`}
                className="rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] p-3"
              >
                <strong className="text-[10px] text-[color:var(--zx-text-title)]">
                  {stage.phase}
                </strong>
                <span className="ml-2 text-[9px] text-[color:var(--zx-text-muted)]">
                  {stage.status} · {stage.durationMs} ms
                </span>
                {stage.message ? (
                  <p className="mt-1 text-[9px] text-[color:var(--zx-text-muted)]">
                    {stage.message}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="mt-5">
        <PanelTitle title="Native Replay" />
        {detail?.replayId ? (
          <button
            type="button"
            onClick={() => onOpenReplay(detail.replayId!)}
            className="w-full rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-3 py-2 text-[11px] font-semibold text-[color:var(--zx-primary)]"
          >
            Open authoritative Replay
          </button>
        ) : (
          <p className="text-[10px] text-[color:var(--zx-text-muted)]">
            {replayState.message}
          </p>
        )}
      </section>
    </aside>
  );
}

/** Render one inspector section heading. */
function PanelTitle({ title }: { title: string }) {
  return (
    <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-muted)]">
      {title}
    </h2>
  );
}

/** Render one status axis without combining semantic meanings. */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] p-3">
      <span className="block text-[9px] text-[color:var(--zx-text-muted)]">
        {label}
      </span>
      <strong className="mt-1 block text-[11px] text-[color:var(--zx-text-title)]">
        {value}
      </strong>
    </div>
  );
}

/** Render an immutable identity as copyable factual text. */
function Identity({ label, value }: { label: string; value: string }) {
  return (
    <div className="mb-2">
      <span className="block text-[9px] text-[color:var(--zx-text-muted)]">
        {label}
      </span>
      <code className="block break-all text-[9px] text-[color:var(--zx-text-title)]">
        {value}
      </code>
    </div>
  );
}
