import type { ReactNode } from "react";
import { EvidenceOriginFacts } from "@/entities/evidence-origin";
import type { BenchmarkEventSessionSnapshot } from "../model/benchmarkEventSession";
import type { BenchmarkTaskRunViewModel } from "../model/benchmarkMonitor";

type BenchmarkTaskRunInspectorProps = {
  viewModel: BenchmarkTaskRunViewModel;
  session: BenchmarkEventSessionSnapshot;
  onOpenReplay: (replayId: string) => void;
};

/** Format one backend timestamp without changing or inferring its meaning. */
function formatTimestamp(value: number | null): string {
  if (value === null) return "—";
  const milliseconds = value > 10_000_000_000 ? value : value * 1000;
  return new Date(milliseconds).toLocaleString();
}

/** Render committed Benchmark facts and explicit evidence availability only. */
export function BenchmarkTaskRunInspector({
  viewModel,
  session,
  onOpenReplay,
}: BenchmarkTaskRunInspectorProps) {
  const { experiment, taskRun } = viewModel;
  return (
    <section
      aria-label="Benchmark Inspector"
      className="h-full overflow-auto bg-[var(--zx-card)] p-4"
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--zx-primary)]">
        Inspector · committed facts
      </p>
      <FactSection title="Experiment">
        <Fact label="Lifecycle" value={experiment.lifecycle} />
        <Fact label="Terminal reason" value={experiment.terminalReason ?? "—"} />
        <Fact label="Accepted" value={formatTimestamp(experiment.acceptedAt)} />
        <Fact label="Updated" value={formatTimestamp(experiment.updatedAt)} />
        <Fact
          label="Outcome"
          value={experiment.outcomeAvailability}
        />
      </FactSection>

      <FactSection title="Selected TaskRun">
        {taskRun ? (
          <>
            <Fact label="Task" value={taskRun.taskId} />
            <Fact label="Lifecycle" value={taskRun.lifecycle} />
            <Fact label="Terminal reason" value={taskRun.terminalReason ?? "—"} />
            <Fact
              label="Agent status"
              value={taskRun.agentStatus ?? taskRun.agentStatusAvailability}
            />
            <Fact
              label="Benchmark outcome"
              value={taskRun.benchmarkOutcome ?? taskRun.outcomeAvailability}
            />
            <Fact label="Started" value={formatTimestamp(taskRun.startedAt)} />
            <Fact label="Terminal" value={formatTimestamp(taskRun.terminalAt)} />
          </>
        ) : (
          <p className="text-[11px] text-[color:var(--zx-text-muted)]">
            尚无 authoritative TaskRun。
          </p>
        )}
      </FactSection>

      <FactSection title="Benchmark phases">
        {taskRun?.phases.length ? (
          taskRun.phases.map((phase, index) => (
            <div
              key={`${phase.phase}:${index}`}
              className="rounded-lg border border-[var(--zx-border-light)] p-3"
            >
              <div className="flex justify-between gap-3">
                <strong className="text-[11px] text-[color:var(--zx-text-title)]">
                  {phase.phase}
                </strong>
                <span className="text-[10px] text-[color:var(--zx-text-muted)]">
                  {phase.status} · {phase.durationMs}ms
                </span>
              </div>
              {phase.errorCode || phase.message ? (
                <p className="mt-2 text-[10px] text-amber-300">
                  {[phase.errorCode, phase.message].filter(Boolean).join(": ")}
                </p>
              ) : null}
            </div>
          ))
        ) : (
          <p className="text-[11px] text-[color:var(--zx-text-muted)]">
            phase availability: {taskRun?.phaseAvailability ?? "pending"}
          </p>
        )}
      </FactSection>

      <FactSection title="Evidence boundary">
        {taskRun?.result ? (
          <EvidenceOriginFacts origin={taskRun.result.evidenceOrigin} />
        ) : (
          <p className="text-[10px] leading-relaxed text-[color:var(--zx-text-muted)]">
            Evidence origin is pending; Monitor does not infer a device claim.
          </p>
        )}
      </FactSection>

      <FactSection title="Live evidence">
        <Availability label="Node activation" value="not_captured" />
        <Availability label="Screenshot" value={viewModel.screenshotAvailability} />
        <Availability label="UI XML" value={viewModel.uiXmlAvailability} />
        <p className="text-[10px] leading-relaxed text-[color:var(--zx-text-muted)]">
          Benchmark phase 不等于 Agent node activation；此处不会猜测节点或生成手机画面。
        </p>
      </FactSection>

      <FactSection title="Publication">
        {taskRun ? (
          <>
            <Availability label="Replay" value={taskRun.replayAvailability} />
            <Availability label="Report" value={taskRun.reportAvailability} />
            <Availability
              label="Trajectory"
              value={taskRun.trajectoryAvailability}
            />
            <Availability label="Bundle" value={taskRun.bundleAvailability} />
            {taskRun.publicationDiagnostics.map((diagnostic) => (
              <p
                key={`${diagnostic.component}:${diagnostic.code}`}
                className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-[10px] text-amber-200"
              >
                {diagnostic.component} · {diagnostic.code}: {diagnostic.message}
              </p>
            ))}
            {viewModel.replayId ? (
              <button
                type="button"
                onClick={() => onOpenReplay(viewModel.replayId!)}
                className="w-full rounded-lg bg-[var(--zx-primary)] px-3 py-2 text-[11px] font-semibold text-white"
              >
                打开持久 Replay
              </button>
            ) : (
              <p className="text-[10px] text-[color:var(--zx-text-muted)]">
                Replay 尚不可用；Monitor 不会从 live event buffer 构造 Replay。
              </p>
            )}
          </>
        ) : null}
      </FactSection>

      <FactSection title="Journal transport">
        <Fact label="Connection" value={session.connection} />
        <Fact label="Cursor" value={`${session.cursor}/${session.highWaterMark}`} />
        <Fact
          label="Last heartbeat/data"
          value={formatTimestamp(session.lastFreshAt)}
        />
        <div className="space-y-1">
          {session.events.slice(-8).map((event) => (
            <p
              key={event.eventId}
              className="truncate font-mono text-[9px] text-[color:var(--zx-text-muted)]"
              title={event.kind}
            >
              #{event.sequence} · {event.kind}
              {event.phase ? ` · ${event.phase}` : ""}
            </p>
          ))}
        </div>
      </FactSection>
    </section>
  );
}

/** Group related Inspector facts without merging their semantics. */
function FactSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="mt-4 space-y-2 rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] p-3">
      <h2 className="text-[9px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-muted)]">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** Render one label/value fact row. */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 text-[10px]">
      <span className="text-[color:var(--zx-text-muted)]">{label}</span>
      <strong className="break-all text-right text-[color:var(--zx-text-title)]">
        {value}
      </strong>
    </div>
  );
}

/** Render one explicit backend evidence/publication availability value. */
function Availability({ label, value }: { label: string; value: string }) {
  return <Fact label={label} value={value} />;
}
