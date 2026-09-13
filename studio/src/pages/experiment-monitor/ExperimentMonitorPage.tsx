import type { ReactNode } from "react";
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useBenchmarkExperimentMonitor } from "@/features/benchmark-experiment-monitor";
import { StudioApiError } from "@/shared/api";
import { BenchmarkExperimentWorkbench } from "@/widgets/benchmark-experiment-workbench";
import { parseExperimentMonitorRoute } from "./model/experimentMonitorRoute";

/** Load and reconstruct one durable Benchmark Experiment Monitor route. */
export function ExperimentMonitorPage() {
  const params = useParams<{ experimentId: string }>();
  const navigate = useNavigate();
  const route = useMemo(
    () => parseExperimentMonitorRoute(params.experimentId),
    [params.experimentId],
  );
  const experimentId = route.mode === "monitor" ? route.experimentId : "";
  const monitor = useBenchmarkExperimentMonitor(experimentId);

  if (route.mode === "invalid") {
    return (
      <MonitorPageState
        title="无效 Experiment 地址"
        detail={route.reason}
      />
    );
  }
  if (monitor.experiment.isLoading) {
    return (
      <MonitorPageState
        title="正在重建 Experiment Monitor"
        detail="读取 durable Experiment、TaskRuns 与 event cursor…"
        busy
      />
    );
  }
  if (monitor.experiment.isError) {
    const notFound =
      monitor.experiment.error instanceof StudioApiError
      && monitor.experiment.error.status === 404;
    return (
      <MonitorPageState
        title={notFound ? "Experiment 不存在" : "Experiment 加载失败"}
        detail={
          notFound
            ? `没有找到 ${route.experimentId}`
            : monitor.experiment.error.message
        }
        action={
          <button type="button" onClick={monitor.retry} className="underline">
            重试 durable resource
          </button>
        }
      />
    );
  }
  if (!monitor.experiment.data || !monitor.viewModel) {
    return (
      <MonitorPageState
        title="Experiment resource 不可用"
        detail="服务未返回可验证的版本化资源。"
        action={
          <button type="button" onClick={monitor.retry} className="underline">
            重试
          </button>
        }
      />
    );
  }

  return (
    <BenchmarkExperimentWorkbench
      experiment={monitor.experiment.data}
      viewModel={monitor.viewModel}
      railItems={monitor.railItems}
      selection={monitor.selection}
      railCollapsed={monitor.railCollapsed}
      taskRunError={
        monitor.taskRuns.isError ? monitor.taskRuns.error.message : null
      }
      session={monitor.session}
      cancelConfirmationOpen={monitor.cancelConfirmationOpen}
      cancelPending={monitor.cancelCommand.isPending}
      cancelError={
        monitor.cancelCommand.isError
          ? monitor.cancelCommand.error.message
          : null
      }
      canCancel={monitor.canCancel}
      canOpenReport={
        monitor.experiment.data.capabilities.reports
        && monitor.experiment.data.reportAvailability === "available"
        && monitor.experiment.data.links.report !== null
      }
      onToggleRail={monitor.toggleRail}
      onSelectTaskRun={monitor.selectTaskRun}
      onReturnToCurrent={monitor.returnToCurrent}
      onRequestCancel={monitor.requestCancel}
      onDismissCancel={monitor.dismissCancel}
      onConfirmCancel={monitor.confirmCancel}
      onRetry={monitor.retry}
      onOpenReplay={(replayId) =>
        navigate(`/runs/${encodeURIComponent(replayId)}/replay`)
      }
      onOpenReport={() =>
        navigate(`/experiments/${route.experimentId}/report`)
      }
    />
  );
}

/** Render stable loading, not-found, invalid, or retryable route state. */
function MonitorPageState({
  title,
  detail,
  busy = false,
  action,
}: {
  title: string;
  detail: string;
  busy?: boolean;
  action?: ReactNode;
}) {
  return (
    <div className="flex h-full items-center justify-center bg-[var(--zx-canvas)] p-8">
      <section className="max-w-lg rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-7 text-center shadow-[var(--zx-shadow-soft)]">
        <span
          className={`mx-auto mb-4 block h-8 w-8 rounded-full border-2 border-[var(--zx-primary)] ${
            busy ? "animate-spin border-t-transparent" : ""
          }`}
        />
        <h1 className="text-[15px] font-semibold text-[color:var(--zx-text-title)]">
          {title}
        </h1>
        <p className="mt-2 text-[11px] text-[color:var(--zx-text-muted)]">
          {detail}
        </p>
        {action ? (
          <div className="mt-4 text-[11px] text-[color:var(--zx-primary)]">
            {action}
          </div>
        ) : null}
      </section>
    </div>
  );
}
