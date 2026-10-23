import { useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useBenchmarkExperiment,
  useBenchmarkTaskRuns,
  type BenchmarkExperimentResource,
  type BenchmarkTaskRun,
} from "@/entities/benchmark-experiment";
import {
  benchmarkExperimentReportQueryOptions,
  benchmarkReportKeys,
  getBenchmarkRunReport,
  listBenchmarkArtifactInventory,
  resolveBenchmarkRunReportArtifact,
  type BenchmarkArtifactInventoryPage,
  type BenchmarkRunReportScope,
} from "@/entities/benchmark-report";
import {
  projectBenchmarkExperimentResults,
} from "./benchmarkComparisonMetrics";
import {
  projectBenchmarkEvaluation,
  projectBenchmarkReportRuns,
  projectBenchmarkRunDetail,
  selectBenchmarkReportRun,
} from "./benchmarkReportProjection";
import { collectBenchmarkReportInventory } from "./benchmarkReportInventory";
import {
  benchmarkReportState,
  classifyBenchmarkReportError,
  classifyExperimentPublication,
  type BenchmarkReportComponentState,
} from "./benchmarkReportState";

const EMPTY_LINK = "";

export type BenchmarkExportMetadataSnapshot = {
  experiment: BenchmarkExperimentResource;
  taskRuns: BenchmarkTaskRun[];
  inventory: BenchmarkArtifactInventoryPage;
};

/** Return one integrity state without exposing a projection exception. */
function integrityState(message: string): BenchmarkReportComponentState {
  return benchmarkReportState("integrity", message, true);
}

/** Coordinate reconstructable Benchmark report resources without Monitor state. */
export function useBenchmarkExperimentReport(
  experimentId: string,
  requestedTaskRunId: string | null,
) {
  const experiment = useBenchmarkExperiment(experimentId);
  const taskRuns = useBenchmarkTaskRuns(experimentId);
  const reportLink = experiment.data?.links.report ?? EMPTY_LINK;
  const inventoryLink = experiment.data?.links.artifacts ?? EMPTY_LINK;
  const publicationReady =
    experiment.data?.lifecycle === "terminal"
    && experiment.data.reportAvailability === "available";

  const experimentReport = useQuery({
    ...benchmarkExperimentReportQueryOptions(experimentId, reportLink),
    enabled: publicationReady && reportLink.length > 0,
  });
  const inventory = useQuery({
    queryKey: [
      ...benchmarkReportKeys.all,
      experimentId,
      "complete-inventory",
      inventoryLink,
    ] as const,
    queryFn: () =>
      collectBenchmarkReportInventory(
        experimentId,
        (cursor, limit) =>
          listBenchmarkArtifactInventory(
            experimentId,
            inventoryLink,
            cursor,
            limit,
          ),
      ),
    enabled: publicationReady && inventoryLink.length > 0,
  });

  const aggregateProjection = useMemo(() => {
    if (!experiment.data || !experimentReport.isSuccess) return null;
    try {
      return {
        data: projectBenchmarkExperimentResults(
          experiment.data,
          experimentReport.data,
        ),
        error: null,
      };
    } catch {
      return {
        data: null,
        error: integrityState(
          "Experiment results conflict with persisted resource identities.",
        ),
      };
    }
  }, [
    experiment.data,
    experimentReport.data,
    experimentReport.isSuccess,
  ]);

  const runProjection = useMemo(() => {
    if (!experiment.data || !experimentReport.isSuccess) return null;
    try {
      return {
        data: projectBenchmarkReportRuns(
          experiment.data,
          taskRuns.isSuccess ? taskRuns.data.items : null,
          experimentReport.data,
        ),
        error: null,
      };
    } catch {
      return {
        data: null,
        error: integrityState(
          "Experiment report identities conflict with persisted resources.",
        ),
      };
    }
  }, [
    experiment.data,
    experimentReport.data,
    experimentReport.isSuccess,
    taskRuns.data,
    taskRuns.isSuccess,
  ]);
  const selection = useMemo(
    () =>
      runProjection?.data
        ? selectBenchmarkReportRun(
            runProjection.data,
            requestedTaskRunId,
          )
        : null,
    [requestedTaskRunId, runProjection],
  );

  const selectedArtifact = useMemo(() => {
    if (!selection?.selected || !inventory.isSuccess) return null;
    const item = selection.selected;
    if (
      !item.taskRunId
      || item.taskRun?.reportAvailability !== "available"
      || item.taskRun.links?.artifacts === null
    ) {
      return null;
    }
    const scoped = inventory.data.items.filter((artifact) =>
      artifact.descriptor.taskRunId === item.taskRunId
      && artifact.descriptor.kind === "task_report"
      && artifact.descriptor.causalIdentity === item.summary.reportRef
    );
    if (scoped.length === 1 && scoped[0]!.links.content === null) {
      const availability = scoped[0]!.descriptor.availability;
      if (availability === "missing" || availability === "corrupt") {
        return {
          data: null,
          error: benchmarkReportState(
            availability,
            availability === "missing"
              ? "The selected TaskRun report artifact is missing."
              : "The selected TaskRun report artifact is corrupt.",
            true,
          ),
        };
      }
    }
    try {
      return {
        data: resolveBenchmarkRunReportArtifact(
          {
            experimentId,
            taskRunId: item.taskRunId,
            coreTaskRunId: item.coreTaskRunId,
          },
          item.summary,
          inventory.data,
        ),
        error: null,
      };
    } catch {
      return {
        data: null,
        error: integrityState(
          "The selected TaskRun report has no unique verified artifact.",
        ),
      };
    }
  }, [experimentId, inventory.data, inventory.isSuccess, selection]);

  const runScope: BenchmarkRunReportScope | null = useMemo(() => {
    const selected = selection?.selected;
    if (
      !selected?.taskRun
      || !selected.taskRunId
      || !selectedArtifact?.data?.links.content
    ) {
      return null;
    }
    return {
      experimentId,
      taskRunId: selected.taskRunId,
      coreTaskRunId: selected.coreTaskRunId,
      taskId: selected.taskRun.taskId,
      agentId: selected.taskRun.agentId,
      repeat: selected.taskRun.repeat,
    };
  }, [experimentId, selectedArtifact, selection]);
  const runReportLink = selectedArtifact?.data?.links.content ?? EMPTY_LINK;
  const runReport = useQuery({
    queryKey: runScope
      ? benchmarkReportKeys.run(runScope, runReportLink)
      : [...benchmarkReportKeys.all, experimentId, "run", "disabled"],
    queryFn: () => {
      if (!runScope) throw new Error("TaskRun report scope is unavailable");
      return getBenchmarkRunReport(runScope, runReportLink);
    },
    enabled: runScope !== null && runReportLink.length > 0,
  });

  const runDetail = useMemo(() => {
    if (
      !experiment.data
      || !inventory.isSuccess
      || !selection?.selected
      || !runReport.isSuccess
    ) {
      return null;
    }
    try {
      return {
        data: projectBenchmarkRunDetail(
          experiment.data,
          inventory.data,
          selection.selected,
          runReport.data,
        ),
        error: null,
      };
    } catch {
      return {
        data: null,
        error: integrityState(
          "TaskRun report identities conflict with persisted resources.",
        ),
      };
    }
  }, [
    experiment.data,
    inventory.data,
    inventory.isSuccess,
    runReport.data,
    runReport.isSuccess,
    selection,
  ]);
  const evaluation = useMemo(() => {
    const root = runDetail?.data?.report.evaluation;
    if (root === null) {
      return {
        data: null,
        state: benchmarkReportState(
          "unavailable",
          "This TaskRun report has no Evaluation Tree.",
        ),
      };
    }
    if (!root) return null;
    try {
      return {
        data: projectBenchmarkEvaluation(root),
        state: benchmarkReportState(
          "available",
          "Evaluation Tree is available.",
        ),
      };
    } catch {
      return {
        data: null,
        state: integrityState(
          "Evaluation Tree paths are not uniquely addressable.",
        ),
      };
    }
  }, [runDetail]);

  const experimentState = useMemo((): BenchmarkReportComponentState => {
    if (experiment.isPending) {
      return benchmarkReportState("loading", "Loading Experiment…");
    }
    if (experiment.isError) {
      const state = classifyBenchmarkReportError(
        experiment.error,
        "Experiment was not found.",
      );
      return state.kind === "missing"
        ? { ...state, kind: "not_found" }
        : state;
    }
    return benchmarkReportState("available", "Experiment is available.");
  }, [experiment.error, experiment.isError, experiment.isPending]);

  const publicationState = useMemo((): BenchmarkReportComponentState => {
    if (!experiment.data) return benchmarkReportState("idle", "Waiting for Experiment.");
    const gate = classifyExperimentPublication(
      experiment.data,
      experiment.data.reportAvailability,
      experiment.data.links.report,
    );
    if (gate.kind !== "loading") return gate;
    if (experimentReport.isPending || experimentReport.isFetching) return gate;
    if (experimentReport.isError) {
      return classifyBenchmarkReportError(
        experimentReport.error,
        "The published Experiment report is missing.",
      );
    }
    if (aggregateProjection?.error) return aggregateProjection.error;
    return benchmarkReportState(
      "available",
      "Published Experiment report is verified.",
    );
  }, [
    experiment.data,
    experimentReport.error,
    experimentReport.isError,
    experimentReport.isFetching,
    experimentReport.isPending,
    aggregateProjection,
  ]);
  const aggregateState =
    publicationState.kind === "available" && aggregateProjection?.data
      ? benchmarkReportState(
          "available",
          aggregateProjection.data.agentMetrics.length === 0
          && aggregateProjection.data.comparisons.length === 0
            ? "The formal report contains no Agent metrics or comparisons."
            : "Experiment metrics and comparisons are available.",
        )
      : publicationState;

  const taskRunsState = taskRuns.isPending
    ? benchmarkReportState("loading", "Loading TaskRuns…")
    : taskRuns.isError
      ? benchmarkReportState(
          "failed",
          "TaskRun resources are temporarily unavailable.",
          true,
        )
      : benchmarkReportState("available", "TaskRun resources are available.");
  const inventoryState = !publicationReady
    ? benchmarkReportState("idle", "Inventory is not required yet.")
    : inventoryLink.length === 0
      ? integrityState("Publication has no artifact inventory capability.")
      : inventory.isPending || inventory.isFetching
        ? benchmarkReportState("loading", "Loading artifact inventory…")
        : inventory.isError
          ? classifyBenchmarkReportError(
              inventory.error,
              "Artifact inventory is missing.",
            )
          : benchmarkReportState(
              "available",
              "Artifact inventory is verified.",
            );
  const runReportState = !selection?.selected
    ? benchmarkReportState(
        "unavailable",
        selection?.invalidRequestedSelection
          ? "The requested TaskRun does not belong to this report."
          : "No verified TaskRun report is selectable.",
      )
    : selection.selected.taskRun?.reportAvailability === "pending"
      ? benchmarkReportState(
          "pending",
          "The selected TaskRun report is still pending.",
          true,
        )
      : selection.selected.taskRun?.reportAvailability === "not_produced"
        ? benchmarkReportState(
            "not_produced",
            "The selected TaskRun did not produce a report.",
          )
        : selection.selected.taskRun?.reportAvailability === "failed"
          ? benchmarkReportState(
              "failed",
              "The selected TaskRun report publication failed.",
              true,
            )
          : selection.selected.taskRun?.links?.artifacts === null
            ? integrityState(
                "TaskRun report availability has no artifact capability.",
              )
            : inventoryState.kind !== "available"
              ? inventoryState
              : selectedArtifact?.error
      ? selectedArtifact.error
      : !selectedArtifact?.data
        ? benchmarkReportState("loading", "Resolving TaskRun report…")
        : runReport.isPending || runReport.isFetching
          ? benchmarkReportState("loading", "Loading TaskRun report…")
          : runReport.isError
            ? classifyBenchmarkReportError(
                runReport.error,
                "The selected TaskRun report is missing.",
              )
            : runDetail?.error
              ? runDetail.error
              : benchmarkReportState(
                  "available",
                  "TaskRun report is verified.",
                );
  const replayState = runDetail?.data?.replayId
    ? benchmarkReportState("available", "Native Replay is available.")
    : benchmarkReportState(
        "unavailable",
        "Native Replay is not available for this TaskRun.",
      );

  /** Retry only the authoritative Experiment resource. */
  const retryExperiment = useCallback(
    () => experiment.refetch(),
    [experiment],
  );
  /** Retry only the stable TaskRun resource page. */
  const retryTaskRuns = useCallback(() => taskRuns.refetch(), [taskRuns]);
  /** Retry only the metadata-only artifact inventory. */
  const retryInventory = useCallback(() => inventory.refetch(), [inventory]);
  /** Retry only the immutable Experiment report. */
  const retryExperimentReport = useCallback(
    () => experimentReport.refetch(),
    [experimentReport],
  );
  /** Retry selected report after refreshing its integrity closure. */
  const retryRunReport = useCallback(async () => {
    await Promise.all([
      experiment.refetch(),
      taskRuns.refetch(),
      inventory.refetch(),
    ]);
    return runReport.refetch();
  }, [experiment, inventory, runReport, taskRuns]);
  /** Retry Evaluation from its selected immutable TaskRun report. */
  const retryEvaluation = useCallback(
    () => retryRunReport(),
    [retryRunReport],
  );
  /** Retry only persisted TaskRun facts that own native Replay capability. */
  const retryReplay = useCallback(
    () => taskRuns.refetch(),
    [taskRuns],
  );
  /** Refresh every authoritative metadata owner required by Export prepare. */
  const refreshExportMetadata =
    useCallback(async (): Promise<BenchmarkExportMetadataSnapshot> => {
      const [experimentResult, taskRunsResult, inventoryResult] =
        await Promise.all([
          experiment.refetch(),
          taskRuns.refetch(),
          inventory.refetch(),
        ]);
      if (
        !experimentResult.data
        || !taskRunsResult.data
        || !inventoryResult.data
      ) {
        throw new Error("Benchmark Export metadata refresh is incomplete");
      }
      return {
        experiment: experimentResult.data,
        taskRuns: taskRunsResult.data.items,
        inventory: inventoryResult.data,
      };
    }, [experiment, inventory, taskRuns]);

  return {
    experiment,
    taskRuns,
    inventory,
    experimentReport,
    runReport,
    aggregate: aggregateProjection,
    runProjection,
    selection,
    runDetail,
    evaluation,
    states: {
      experiment: experimentState,
      publication: publicationState,
      aggregate: aggregateState,
      taskRuns: taskRunsState,
      inventory: inventoryState,
      runReport: runReportState,
      evaluation:
        evaluation?.state
        ?? benchmarkReportState("idle", "Evaluation is not loaded."),
      replay: replayState,
    },
    retryExperiment,
    retryTaskRuns,
    retryInventory,
    retryExperimentReport,
    retryRunReport,
    retryEvaluation,
    retryReplay,
    refreshExportMetadata,
  };
}
