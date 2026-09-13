import { RunGraph } from "@/features/trajectory-replay";
import { VirtualPhone } from "@/features/virtual-phone";
import {
  BenchmarkTaskRunInspector,
  CancelExperimentDialog,
  ExperimentMonitorHeader,
  TaskRunRail,
  type BenchmarkEventSessionSnapshot,
  type BenchmarkTaskRunRailItem,
  type BenchmarkTaskRunSelection,
  type BenchmarkTaskRunViewModel,
} from "@/features/benchmark-experiment-monitor";
import type { BenchmarkExperimentResource } from "@/entities/benchmark-experiment";
import { ThreePaneWorkbenchLayout } from "@/widgets/three-pane-workbench";

type BenchmarkExperimentWorkbenchProps = {
  experiment: BenchmarkExperimentResource;
  viewModel: BenchmarkTaskRunViewModel;
  railItems: BenchmarkTaskRunRailItem[];
  selection: BenchmarkTaskRunSelection;
  railCollapsed: boolean;
  taskRunError: string | null;
  session: BenchmarkEventSessionSnapshot;
  cancelConfirmationOpen: boolean;
  cancelPending: boolean;
  cancelError: string | null;
  canCancel: boolean;
  canOpenReport: boolean;
  onToggleRail: () => void;
  onSelectTaskRun: (taskRunId: string) => void;
  onReturnToCurrent: () => void;
  onRequestCancel: () => void;
  onDismissCancel: () => void;
  onConfirmCancel: () => void;
  onRetry: () => void;
  onOpenReplay: (replayId: string) => void;
  onOpenReport: () => void;
};

/** Compose plural TaskRun navigation around the shared three-pane workbench. */
export function BenchmarkExperimentWorkbench({
  experiment,
  viewModel,
  railItems,
  selection,
  railCollapsed,
  taskRunError,
  session,
  cancelConfirmationOpen,
  cancelPending,
  cancelError,
  canCancel,
  canOpenReport,
  onToggleRail,
  onSelectTaskRun,
  onReturnToCurrent,
  onRequestCancel,
  onDismissCancel,
  onConfirmCancel,
  onRetry,
  onOpenReplay,
  onOpenReport,
}: BenchmarkExperimentWorkbenchProps) {
  const completedTaskRuns = railItems.filter(
    (item) => item.lifecycle === "terminal",
  ).length;
  return (
    <div className="relative flex h-full min-h-0 bg-[var(--zx-canvas)]">
      <TaskRunRail
        items={railItems}
        collapsed={railCollapsed}
        locked={selection.locked}
        error={taskRunError}
        onToggle={onToggleRail}
        onSelect={onSelectTaskRun}
        onReturnToCurrent={onReturnToCurrent}
        onRetry={onRetry}
      />
      <div className="min-w-0 flex-1">
        <ThreePaneWorkbenchLayout
          header={
            <ExperimentMonitorHeader
              experiment={experiment}
              session={session}
              completedTaskRuns={completedTaskRuns}
              totalTaskRuns={railItems.length}
              canCancel={canCancel}
              canOpenReport={canOpenReport}
              cancelPending={cancelPending}
              onRequestCancel={onRequestCancel}
              onOpenReport={onOpenReport}
            />
          }
          banner={
            <TransportBanner
              experiment={experiment}
              session={session}
              onRetry={onRetry}
            />
          }
          left={
            viewModel.snapshot && viewModel.projection ? (
              <div className="flex h-full min-h-0 flex-col">
                <div className="shrink-0 border-b border-[var(--zx-divider-ui)] bg-amber-500/10 px-3 py-2 text-[10px] text-amber-200">
                  Immutable AgentGraph · live node activation unavailable
                </div>
                <div className="min-h-0 flex-1">
                  <RunGraph
                    ariaLabel="Benchmark immutable AgentGraph"
                    snapshot={viewModel.snapshot}
                    projection={viewModel.projection}
                    selectedActivationId={null}
                    onSelectActivation={() => undefined}
                  />
                </div>
              </div>
            ) : (
              <EvidenceUnavailable
                title="AgentGraph unavailable"
                detail="Immutable Agent snapshot 未提供可验证 graph body。"
              />
            )
          }
          middle={
            <VirtualPhone
              modeLabel="BENCHMARK · NO LIVE EVIDENCE"
              frame={viewModel.phoneFrame}
              latestAction={null}
              resolveArtifact={() => null}
            />
          }
          right={
            <BenchmarkTaskRunInspector
              viewModel={viewModel}
              session={session}
              onOpenReplay={onOpenReplay}
            />
          }
        />
      </div>
      <CancelExperimentDialog
        open={cancelConfirmationOpen}
        pending={cancelPending}
        error={cancelError}
        onDismiss={onDismissCancel}
        onConfirm={onConfirmCancel}
      />
    </div>
  );
}

/** Render transport/recovery state without changing authoritative lifecycle. */
function TransportBanner({
  experiment,
  session,
  onRetry,
}: {
  experiment: BenchmarkExperimentResource;
  session: BenchmarkEventSessionSnapshot;
  onRetry: () => void;
}) {
  if (session.connection === "frozen") {
    return (
      <div
        role="alert"
        className="flex items-center justify-between gap-4 border-b border-rose-500/30 bg-rose-500/10 px-4 py-2 text-[10px] text-rose-200"
      >
        <span>
          Journal 完整性错误：{session.integrityError}。最后验证前缀已冻结。
        </span>
        <button type="button" onClick={onRetry} className="underline">
          显式重试
        </button>
      </div>
    );
  }
  if (
    session.connection === "backfilling"
    || session.connection === "connecting"
    || session.connection === "reconnecting"
  ) {
    return (
      <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-[10px] text-amber-200">
        传输状态 {session.connection}；从已验证 cursor {session.cursor} 恢复。Experiment
        lifecycle 仍以 HTTP resource 为准。
      </div>
    );
  }
  if (
    experiment.lifecycle === "terminal"
    && experiment.terminalReason === "interrupted"
  ) {
    return (
      <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-[10px] text-amber-200">
        服务已将本次 Experiment 标记为 interrupted；这不是浏览器根据断线推导的状态。
      </div>
    );
  }
  return null;
}

/** Render a bounded explicit missing-evidence pane. */
function EvidenceUnavailable({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <div className="grid h-full place-items-center p-6 text-center">
      <div>
        <span className="text-2xl text-[color:var(--zx-text-muted)]">◇</span>
        <strong className="mt-2 block text-[12px] text-[color:var(--zx-text-title)]">
          {title}
        </strong>
        <p className="mt-2 max-w-xs text-[10px] leading-relaxed text-[color:var(--zx-text-muted)]">
          {detail}
        </p>
      </div>
    </div>
  );
}
