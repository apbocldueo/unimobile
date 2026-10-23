import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQuery,
} from "@tanstack/react-query";
import {
  getBenchmarkDetail,
  listBenchmarkCatalog,
  listBenchmarkTasks,
  listDeviceProfiles,
  validateBenchmark,
  type BenchmarkCatalogFilters,
} from "./benchmarkCatalogApi";

export const benchmarkCatalogKeys = {
  all: ["studio", "benchmark-catalog"] as const,
  list: (filters: BenchmarkCatalogFilters) =>
    ["studio", "benchmark-catalog", "list", filters] as const,
  detail: (catalogEntryId: string) =>
    ["studio", "benchmark-catalog", "detail", catalogEntryId] as const,
  tasks: (
    catalogEntryId: string,
    split: string,
    cursor: string | null,
  ) => [
    "studio",
    "benchmark-catalog",
    "tasks",
    catalogEntryId,
    split,
    cursor,
  ] as const,
  deviceProfiles: ["studio", "device-profiles"] as const,
};

/** Build shared Catalog query options with cancellation and stable cache identity. */
export function benchmarkCatalogQueryOptions(filters: BenchmarkCatalogFilters) {
  return queryOptions({
    queryKey: benchmarkCatalogKeys.list(filters),
    queryFn: ({ signal }) => listBenchmarkCatalog(filters, signal),
    placeholderData: keepPreviousData,
  });
}

/** Subscribe to one filtered Catalog page. */
export function useBenchmarkCatalog(filters: BenchmarkCatalogFilters) {
  return useQuery(benchmarkCatalogQueryOptions(filters));
}

/** Subscribe to one concrete Package detail. */
export function useBenchmarkDetail(catalogEntryId: string) {
  return useQuery({
    queryKey: benchmarkCatalogKeys.detail(catalogEntryId),
    queryFn: ({ signal }) => getBenchmarkDetail(catalogEntryId, signal),
    enabled: catalogEntryId.length > 0,
  });
}

/** Subscribe to one split task page without copying it into form state. */
export function useBenchmarkTasks(
  catalogEntryId: string,
  split: string,
  cursor: string | null,
) {
  return useQuery({
    queryKey: benchmarkCatalogKeys.tasks(catalogEntryId, split, cursor),
    queryFn: ({ signal }) =>
      listBenchmarkTasks(
        catalogEntryId,
        split,
        100,
        cursor ?? undefined,
        signal,
      ),
    enabled: catalogEntryId.length > 0 && split.length > 0,
    placeholderData: keepPreviousData,
  });
}

/** Expose explicit validation as a command rather than background discovery. */
export function useValidateBenchmark() {
  return useMutation({
    mutationFn: (input: { catalogEntryId: string; split: string | null }) =>
      validateBenchmark(input.catalogEntryId, input.split),
  });
}

/** Subscribe to the static safe device-profile directory. */
export function useDeviceProfiles() {
  return useQuery({
    queryKey: benchmarkCatalogKeys.deviceProfiles,
    queryFn: ({ signal }) => listDeviceProfiles(signal),
  });
}
