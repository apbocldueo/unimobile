import {
  type BenchmarkExperimentResource,
  type BenchmarkTaskRun,
} from "@/entities/benchmark-experiment";
import {
  resolveBenchmarkRunReportArtifact,
  type BenchmarkArtifactInventoryPage,
  type BenchmarkEvaluationNode,
  type BenchmarkExperimentReport,
  type BenchmarkRunReport,
  type BenchmarkRunSummary,
} from "@/entities/benchmark-report";

export type BenchmarkReportAxes = {
  serviceLifecycle: BenchmarkTaskRun["lifecycle"] | null;
  agentStatus: string | null;
  benchmarkOutcome: string | null;
};

export type BenchmarkReportRunItem = {
  taskRunId: string | null;
  coreTaskRunId: string;
  order: number | null;
  taskRun: BenchmarkTaskRun | null;
  summary: BenchmarkRunSummary;
  axes: BenchmarkReportAxes;
  integrityError: string | null;
};

export type BenchmarkReportSelection = {
  requestedTaskRunId: string | null;
  selectedTaskRunId: string | null;
  selected: BenchmarkReportRunItem | null;
  invalidRequestedSelection: boolean;
};

export type BenchmarkEvaluationProjection = {
  root: BenchmarkEvaluationNode;
  orderedPaths: string[];
  defaultExpandedPaths: string[];
};

export type BenchmarkRunDetailProjection = {
  item: BenchmarkReportRunItem;
  report: BenchmarkRunReport;
  axes: BenchmarkReportAxes;
  replayId: string | null;
};

/** Order persisted TaskRuns by immutable plan order and Studio identity. */
function orderTaskRuns(taskRuns: BenchmarkTaskRun[]): BenchmarkTaskRun[] {
  return [...taskRuns].sort(
    (left, right) =>
      left.order - right.order
      || left.taskRunId.localeCompare(right.taskRunId),
  );
}

/** Match one immutable Agent snapshot selected by a persisted TaskRun. */
function selectedAgentHash(
  experiment: BenchmarkExperimentResource,
  taskRun: BenchmarkTaskRun,
): string | null {
  return (
    experiment.definition.agentSnapshots.find(
      (snapshot) =>
        snapshot.agentId === taskRun.agentId
        && snapshot.revisionId === taskRun.revisionId,
    )?.canonicalHash
    ?? null
  );
}

/** Project Core run summaries onto Studio TaskRun resources without guessing. */
export function projectBenchmarkReportRuns(
  experiment: BenchmarkExperimentResource,
  taskRuns: BenchmarkTaskRun[] | null,
  report: BenchmarkExperimentReport,
): BenchmarkReportRunItem[] {
  if (
    report.experimentId !== experiment.experimentId
    || report.benchmarkPlanIdentity
      !== experiment.definition.source.benchmarkPlanIdentity
    || report.experimentProtocolIdentity
      !== experiment.definition.source.experimentProtocolIdentity
  ) {
    throw new Error("Experiment report conflicts with immutable definition");
  }
  if (taskRuns === null) {
    return report.runSummaries.map((summary) => ({
      taskRunId: null,
      coreTaskRunId: summary.coreTaskRunId,
      order: null,
      taskRun: null,
      summary,
      axes: {
        serviceLifecycle: null,
        agentStatus: null,
        benchmarkOutcome: null,
      },
      integrityError: "Studio TaskRun resource unavailable",
    }));
  }
  const byCoreId = new Map<string, BenchmarkTaskRun[]>();
  for (const taskRun of taskRuns) {
    if (taskRun.experimentId !== experiment.experimentId) continue;
    if (taskRun.coreTaskRunId === null) continue;
    const matches = byCoreId.get(taskRun.coreTaskRunId) ?? [];
    matches.push(taskRun);
    byCoreId.set(taskRun.coreTaskRunId, matches);
  }
  const summaries = new Map(
    report.runSummaries.map((summary) => [summary.coreTaskRunId, summary]),
  );
  const projected: BenchmarkReportRunItem[] = orderTaskRuns(taskRuns).flatMap(
    (taskRun): BenchmarkReportRunItem[] => {
    const summary = taskRun.coreTaskRunId
      ? summaries.get(taskRun.coreTaskRunId)
      : undefined;
    if (!summary) return [];
    const matches = byCoreId.get(summary.coreTaskRunId) ?? [];
    const identityMatches =
      taskRun.agentId === summary.agentId
      && taskRun.taskId === summary.taskId
      && taskRun.repeat === summary.repeat;
      return [{
      taskRunId: taskRun.taskRunId,
      coreTaskRunId: summary.coreTaskRunId,
      order: taskRun.order,
      taskRun,
      summary,
      axes: {
        serviceLifecycle: taskRun.lifecycle,
        agentStatus: taskRun.agentStatus,
        benchmarkOutcome: taskRun.benchmarkOutcome,
      },
      integrityError:
        matches.length !== 1
          ? "Core run identity does not map to exactly one Studio TaskRun"
          : identityMatches
            ? null
            : "Run summary conflicts with Studio TaskRun identity",
      }];
    },
  );
  const projectedCoreIds = new Set(
    projected.map((item) => item.coreTaskRunId),
  );
  for (const summary of report.runSummaries) {
    if (projectedCoreIds.has(summary.coreTaskRunId)) continue;
    projected.push({
      taskRunId: null,
      coreTaskRunId: summary.coreTaskRunId,
      order: null,
      taskRun: null,
      summary,
      axes: {
        serviceLifecycle: null,
        agentStatus: null,
        benchmarkOutcome: null,
      },
      integrityError: "Core run has no matching Studio TaskRun",
    });
  }
  return projected;
}

/** Resolve URL-owned selection with a deterministic selectable fallback. */
export function selectBenchmarkReportRun(
  items: BenchmarkReportRunItem[],
  requestedTaskRunId: string | null,
): BenchmarkReportSelection {
  const selectable = items.filter(
    (item) => item.taskRunId !== null && item.integrityError === null,
  );
  const requested = requestedTaskRunId === null
    ? null
    : selectable.find((item) => item.taskRunId === requestedTaskRunId) ?? null;
  const selected = requested ?? selectable[0] ?? null;
  return {
    requestedTaskRunId,
    selectedTaskRunId: selected?.taskRunId ?? null,
    selected,
    invalidRequestedSelection:
      requestedTaskRunId !== null && requested === null,
  };
}

/** Resolve and validate one selected Core TaskRun report and Replay handoff. */
export function projectBenchmarkRunDetail(
  experiment: BenchmarkExperimentResource,
  inventory: BenchmarkArtifactInventoryPage,
  item: BenchmarkReportRunItem,
  report: BenchmarkRunReport,
): BenchmarkRunDetailProjection {
  const taskRun = item.taskRun;
  if (!taskRun || !item.taskRunId || item.integrityError) {
    throw new Error("Selected report run has no verified Studio TaskRun scope");
  }
  resolveBenchmarkRunReportArtifact(
    {
      experimentId: experiment.experimentId,
      taskRunId: item.taskRunId,
      coreTaskRunId: item.coreTaskRunId,
    },
    item.summary,
    inventory,
  );
  const agentHash = selectedAgentHash(experiment, taskRun);
  if (
    report.experimentId !== experiment.experimentId
    || report.coreTaskRunId !== item.coreTaskRunId
    || report.agentId !== taskRun.agentId
    || report.taskId !== taskRun.taskId
    || report.repeat !== taskRun.repeat
    || report.outcome !== item.summary.outcome
    || report.identities.benchmarkPlan
      !== experiment.definition.source.benchmarkPlanIdentity
    || report.identities.experimentProtocol
      !== experiment.definition.source.experimentProtocolIdentity
    || agentHash === null
    || report.identities.agentGraph !== agentHash
    || taskRun.taskInstanceIdentity === null
    || report.identities.taskInstance !== taskRun.taskInstanceIdentity
    || (
      taskRun.benchmarkOutcome !== null
      && taskRun.benchmarkOutcome !== report.outcome
    )
  ) {
    throw new Error("TaskRun report conflicts with immutable resource facts");
  }
  const replayId =
    taskRun.lifecycle === "terminal"
    && taskRun.replayAvailability === "available"
    && taskRun.replayId !== null
    && taskRun.links?.replay
      ? taskRun.replayId
      : null;
  return {
    item,
    report,
    axes: item.axes,
    replayId,
  };
}

/** Validate Evaluation paths and derive truthful default expansion. */
export function projectBenchmarkEvaluation(
  root: BenchmarkEvaluationNode,
): BenchmarkEvaluationProjection {
  const orderedPaths: string[] = [];
  const seen = new Set<string>();
  const defaultExpanded = new Set<string>();
  const visit = (node: BenchmarkEvaluationNode, isRoot: boolean): boolean => {
    if (seen.has(node.path)) {
      throw new Error("Evaluation Tree contains duplicate node paths");
    }
    seen.add(node.path);
    orderedPaths.push(node.path);
    let containsNonSuccess =
      node.status === "failure" || node.isPass === false;
    for (const child of node.children) {
      containsNonSuccess = visit(child, false) || containsNonSuccess;
    }
    if ((isRoot || containsNonSuccess) && node.children.length > 0) {
      defaultExpanded.add(node.path);
    }
    return containsNonSuccess;
  };
  visit(root, true);
  return {
    root,
    orderedPaths,
    defaultExpandedPaths: [...defaultExpanded],
  };
}
