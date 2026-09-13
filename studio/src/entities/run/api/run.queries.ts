import {
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  cancelStudioRun,
  createStudioRun,
  getStudioRun,
} from "./runApi";
import type { CreateStudioRunInput } from "../model/liveRun.schema";

export const studioRunKeys = {
  all: ["studio", "runs"] as const,
  detail: (runId: string) => ["studio", "run", runId] as const,
};

/** Build the shared authoritative Run query configuration. */
export function studioRunQueryOptions(runId: string) {
  return queryOptions({
    queryKey: studioRunKeys.detail(runId),
    queryFn: () => getStudioRun(runId),
    enabled: runId.length > 0,
  });
}

/** Subscribe to one authoritative Run without copying it into client stores. */
export function useStudioRun(runId: string) {
  return useQuery(studioRunQueryOptions(runId));
}

/** Create a Run and seed only its authoritative query-cache entry. */
export function useCreateStudioRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateStudioRunInput) => createStudioRun(input),
    onSuccess: (run) => {
      queryClient.setQueryData(studioRunKeys.detail(run.runId), run);
    },
  });
}

/** Request cooperative cancellation and refresh the affected Run cache. */
export function useCancelStudioRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => cancelStudioRun(runId),
    onSuccess: (run) => {
      queryClient.setQueryData(studioRunKeys.detail(run.runId), run);
    },
  });
}
