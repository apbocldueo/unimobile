import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  benchmarkExperimentKeys,
  useBenchmarkExperiment,
  useBenchmarkTaskRuns,
  useCancelBenchmarkExperiment,
} from "@/entities/benchmark-experiment";
import { StudioApiError } from "@/shared/api";
import {
  projectBenchmarkTaskRunRail,
  projectBenchmarkTaskRunView,
  reconcileBenchmarkTaskRunSelection,
  selectBenchmarkTaskRun,
  type BenchmarkTaskRunSelection,
} from "./benchmarkMonitor";
import { useBenchmarkEventSession } from "./useBenchmarkEventSession";

const EMPTY_TASK_RUNS: never[] = [];

/** Generate one cancel command identity that remains stable across safe retry. */
function createCancelRequestId(): string {
  const random = globalThis.crypto?.randomUUID?.();
  return random
    ? `monitor-cancel-${random}`
    : `monitor-cancel-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** Coordinate resource truth, transport state, and local Monitor interaction. */
export function useBenchmarkExperimentMonitor(experimentId: string) {
  const queryClient = useQueryClient();
  const experiment = useBenchmarkExperiment(experimentId);
  const taskRuns = useBenchmarkTaskRuns(experimentId);
  const cancelCommand = useCancelBenchmarkExperiment();
  const [selection, setSelection] = useState<BenchmarkTaskRunSelection>({
    selectedTaskRunId: null,
    locked: false,
  });
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [cancelConfirmationOpen, setCancelConfirmationOpen] = useState(false);
  const cancelRequestId = useRef<string | null>(null);
  const eventSession = useBenchmarkEventSession({
    experimentId,
    enabled:
      experiment.data?.capabilities.eventStream === true
      && experiment.data.links.eventStream !== null,
  });
  const authoritativeTaskRuns = taskRuns.data?.items ?? EMPTY_TASK_RUNS;

  useEffect(() => {
    setSelection((current) =>
      reconcileBenchmarkTaskRunSelection(authoritativeTaskRuns, current),
    );
  }, [authoritativeTaskRuns]);

  const canCancel =
    experiment.data?.lifecycle === "accepted"
    && experiment.data.links.cancel !== null;

  useEffect(() => {
    if (!canCancel) setCancelConfirmationOpen(false);
  }, [canCancel]);

  const railItems = useMemo(
    () => projectBenchmarkTaskRunRail(authoritativeTaskRuns, selection),
    [authoritativeTaskRuns, selection],
  );
  const viewModel = useMemo(
    () =>
      experiment.data
        ? projectBenchmarkTaskRunView(
            experiment.data,
            authoritativeTaskRuns,
            selection,
          )
        : null,
    [authoritativeTaskRuns, experiment.data, selection],
  );

  /** Select one TaskRun, locking only when it is not the factual current item. */
  const selectTaskRun = useCallback(
    (taskRunId: string) => {
      setSelection(
        selectBenchmarkTaskRun(authoritativeTaskRuns, taskRunId),
      );
    },
    [authoritativeTaskRuns],
  );

  /** Return from a historical lock to the deterministic current TaskRun. */
  const returnToCurrent = useCallback(() => {
    setSelection((current) =>
      reconcileBenchmarkTaskRunSelection(authoritativeTaskRuns, {
        ...current,
        locked: false,
      }),
    );
  }, [authoritativeTaskRuns]);

  /** Confirm one accepted-only cooperative cancel without local lifecycle edits. */
  const confirmCancel = useCallback(() => {
    if (!canCancel || cancelCommand.isPending) return;
    cancelRequestId.current ??= createCancelRequestId();
    cancelCommand.mutate(
      {
        experimentId,
        clientRequestId: cancelRequestId.current,
      },
      {
        onSuccess: () => {
          cancelRequestId.current = null;
          setCancelConfirmationOpen(false);
        },
        onError: (error) => {
          if (
            error instanceof StudioApiError
            && (error.status === 404 || error.status === 409)
          ) {
            void Promise.all([
              queryClient.invalidateQueries({
                queryKey: benchmarkExperimentKeys.detail(experimentId),
              }),
              queryClient.invalidateQueries({
                queryKey: benchmarkExperimentKeys.taskRuns(experimentId),
              }),
            ]);
          }
        },
      },
    );
  }, [
    canCancel,
    cancelCommand,
    experimentId,
    queryClient,
  ]);

  /** Explicitly retry authoritative resources and transport from verified cursor. */
  const retry = useCallback(() => {
    void Promise.all([experiment.refetch(), taskRuns.refetch()]);
    eventSession.retry();
  }, [eventSession, experiment, taskRuns]);

  return {
    experiment,
    taskRuns,
    session: eventSession.session,
    selection,
    railItems,
    railCollapsed,
    cancelConfirmationOpen,
    cancelCommand,
    canCancel,
    viewModel,
    selectTaskRun,
    returnToCurrent,
    toggleRail: () => setRailCollapsed((current) => !current),
    requestCancel: () => {
      if (canCancel) setCancelConfirmationOpen(true);
    },
    dismissCancel: () => setCancelConfirmationOpen(false),
    confirmCancel,
    retry,
  };
}
