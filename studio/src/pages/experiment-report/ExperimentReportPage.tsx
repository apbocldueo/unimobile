import { useMemo, type ReactNode } from "react";
import {
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useBenchmarkExperimentReport } from "@/features/benchmark-reporting";
import { BenchmarkReportWorkbench } from "@/widgets/benchmark-report-workbench";
import { parseExperimentReportRoute } from "./model/experimentReportRoute";

/** Reconstruct one durable Benchmark Experiment Report from route identity. */
export function ExperimentReportPage() {
  const params = useParams<{ experimentId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const route = useMemo(
    () => parseExperimentReportRoute(params.experimentId, searchParams),
    [params.experimentId, searchParams],
  );
  const experimentId = route.mode === "report" ? route.experimentId : "";
  const requestedTaskRunId =
    route.mode === "report" ? route.requestedTaskRunId : null;
  const report = useBenchmarkExperimentReport(
    experimentId,
    requestedTaskRunId,
  );

  if (route.mode === "invalid") {
    return (
      <ReportPageState
        title="Invalid Experiment Report address"
        detail={route.reason}
      />
    );
  }
  if (report.states.experiment.kind === "loading") {
    return (
      <ReportPageState
        title="Reconstructing Benchmark Report"
        detail="Loading durable Experiment and report capabilities…"
        busy
      />
    );
  }
  if (
    report.states.experiment.kind !== "available"
    || !report.experiment.data
  ) {
    return (
      <ReportPageState
        title={
          report.states.experiment.kind === "not_found"
            ? "Experiment not found"
            : "Experiment could not be loaded"
        }
        detail={report.states.experiment.message}
        action={
          report.states.experiment.retryable ? (
            <button
              type="button"
              onClick={() => void report.retryExperiment()}
              className="underline"
            >
              Retry Experiment
            </button>
          ) : null
        }
      />
    );
  }

  /** Refresh each durable report dependency without touching Monitor SSE. */
  const refresh = () => {
    void Promise.all([
      report.retryExperiment(),
      report.retryTaskRuns(),
      report.retryInventory(),
      report.retryExperimentReport(),
      report.retryRunReport(),
    ]);
  };

  /** Persist explicit TaskRun selection in the reconstructable route. */
  const selectTaskRun = (taskRunId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("taskRun", taskRunId);
    setSearchParams(next);
  };

  return (
    <BenchmarkReportWorkbench
      experiment={report.experiment.data}
      experimentResults={report.aggregate?.data ?? null}
      inventory={report.inventory.data ?? null}
      runItems={report.runProjection?.data ?? []}
      selection={report.selection}
      runDetail={report.runDetail?.data ?? null}
      evaluation={report.evaluation?.data ?? null}
      states={report.states}
      refreshing={
        report.experiment.isFetching
        || report.taskRuns.isFetching
        || report.inventory.isFetching
        || report.experimentReport.isFetching
        || report.runReport.isFetching
      }
      onRefreshExportMetadata={report.refreshExportMetadata}
      onBackToMonitor={() => navigate(`/experiments/${route.experimentId}`)}
      onRefresh={refresh}
      onRetryTaskRuns={() => void report.retryTaskRuns()}
      onRetryPublication={() => void report.retryExperimentReport()}
      onRetryRunReport={() => void report.retryRunReport()}
      onRetryEvaluation={() => void report.retryEvaluation()}
      onSelectTaskRun={selectTaskRun}
      onOpenReplay={(replayId) =>
        navigate(`/runs/${encodeURIComponent(replayId)}/replay`)
      }
    />
  );
}

/** Render stable invalid, loading, not-found, or retryable page state. */
function ReportPageState({
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
