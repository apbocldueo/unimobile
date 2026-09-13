export type ExperimentReportRoute =
  | {
      mode: "report";
      experimentId: string;
      requestedTaskRunId: string | null;
    }
  | { mode: "invalid"; reason: string };

const EXPERIMENT_ID = /^experiment-[a-f0-9]{32}$/;
const TASK_RUN_ID = /^task-run-[a-f0-9]{32}$/;

/** Parse one reconstructable Experiment Report route and optional selection. */
export function parseExperimentReportRoute(
  experimentId: string | undefined,
  searchParams: URLSearchParams,
): ExperimentReportRoute {
  if (!experimentId || !EXPERIMENT_ID.test(experimentId)) {
    return {
      mode: "invalid",
      reason: "experimentId 不符合版本化 Studio identity contract。",
    };
  }
  const requested = searchParams.getAll("taskRun");
  if (requested.length > 1) {
    return {
      mode: "invalid",
      reason: "Report 地址包含多个冲突的 TaskRun selection。",
    };
  }
  const requestedTaskRunId = requested[0] ?? null;
  if (requestedTaskRunId !== null && !TASK_RUN_ID.test(requestedTaskRunId)) {
    return {
      mode: "invalid",
      reason: "taskRun 不符合版本化 Studio identity contract。",
    };
  }
  return {
    mode: "report",
    experimentId,
    requestedTaskRunId,
  };
}
