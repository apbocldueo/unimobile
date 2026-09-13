import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type {
  BenchmarkExperimentHistoryFilters,
  CancelBenchmarkExperimentInput,
  CreateBenchmarkExperimentInput,
} from "../model/benchmarkExperiment.schema";
import {
  cancelBenchmarkExperiment,
  createBenchmarkExperiment,
  getBenchmarkExperiment,
  listBenchmarkExperiments,
  listBenchmarkTaskRuns,
  normalizeBenchmarkExperimentHistoryFilters,
} from "./benchmarkExperimentApi";

export const benchmarkExperimentKeys = {
  all: ["studio", "benchmark-experiments"] as const,
  history: (
    filters: BenchmarkExperimentHistoryFilters,
    limit: number,
    cursor: string | null,
  ) =>
    [
      "studio",
      "benchmark-experiments",
      "history",
      filters,
      limit,
      cursor,
    ] as const,
  detail: (experimentId: string) =>
    ["studio", "benchmark-experiment", experimentId] as const,
  taskRuns: (experimentId: string) =>
    ["studio", "benchmark-experiment", experimentId, "task-runs"] as const,
};

/** Build a reconstructible Experiment history query configuration. */
export function benchmarkExperimentHistoryQueryOptions(
  limit = 50,
  cursor: string | null = null,
  filters: BenchmarkExperimentHistoryFilters = {},
) {
  const normalized = normalizeBenchmarkExperimentHistoryFilters(filters);
  return queryOptions({
    queryKey: benchmarkExperimentKeys.history(normalized, limit, cursor),
    queryFn: ({ signal }) =>
      listBenchmarkExperiments(cursor, limit, normalized, signal),
    placeholderData: keepPreviousData,
  });
}

/** Build the shared authoritative Experiment query configuration. */
export function benchmarkExperimentQueryOptions(experimentId: string) {
  return queryOptions({
    queryKey: benchmarkExperimentKeys.detail(experimentId),
    queryFn: () => getBenchmarkExperiment(experimentId),
    enabled: experimentId.length > 0,
  });
}

/** Subscribe to one authoritative Experiment resource. */
export function useBenchmarkExperiment(experimentId: string) {
  return useQuery(benchmarkExperimentQueryOptions(experimentId));
}

/** Subscribe to the stable TaskRun page without copying it into feature state. */
export function useBenchmarkTaskRuns(experimentId: string) {
  return useQuery({
    queryKey: benchmarkExperimentKeys.taskRuns(experimentId),
    queryFn: () => listBenchmarkTaskRuns(experimentId),
    enabled: experimentId.length > 0,
  });
}

/** Create an Experiment and seed its authoritative resource cache. */
export function useCreateBenchmarkExperiment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateBenchmarkExperimentInput) =>
      createBenchmarkExperiment(input),
    onSuccess: (response) => {
      queryClient.setQueryData(
        benchmarkExperimentKeys.detail(response.experiment.experimentId),
        response.experiment,
      );
    },
  });
}

/** Request cooperative cancel and refresh both aggregate and children. */
export function useCancelBenchmarkExperiment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CancelBenchmarkExperimentInput) =>
      cancelBenchmarkExperiment(input),
    onSuccess: (experiment) => {
      queryClient.setQueryData(
        benchmarkExperimentKeys.detail(experiment.experimentId),
        experiment,
      );
      void queryClient.invalidateQueries({
        queryKey: benchmarkExperimentKeys.taskRuns(experiment.experimentId),
      });
    },
  });
}
