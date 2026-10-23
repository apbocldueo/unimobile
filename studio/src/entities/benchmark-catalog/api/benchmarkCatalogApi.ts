import { studioRequest } from "@/shared/api";
import {
  parseBenchmarkCatalogPage,
  parseBenchmarkDetail,
  parseBenchmarkTaskPage,
  parseBenchmarkValidationResult,
  parseDeviceProfilePage,
  type BenchmarkCatalogPage,
  type BenchmarkDetail,
  type BenchmarkTaskPage,
  type BenchmarkValidationResult,
  type DeviceProfilePage,
} from "../model/benchmarkCatalog.schema";

export type BenchmarkCatalogFilters = {
  limit?: number;
  cursor?: string;
  query?: string;
  platform?: string;
  sourceKind?: string;
};

/** List one deterministic page of configured Benchmark Packages. */
export async function listBenchmarkCatalog(
  filters: BenchmarkCatalogFilters = {},
  signal?: AbortSignal,
): Promise<BenchmarkCatalogPage> {
  const query = new URLSearchParams({ limit: String(filters.limit ?? 30) });
  if (filters.cursor) query.set("cursor", filters.cursor);
  if (filters.query) query.set("query", filters.query);
  if (filters.platform) query.set("platform", filters.platform);
  if (filters.sourceKind) query.set("sourceKind", filters.sourceKind);
  return parseBenchmarkCatalogPage(
    await studioRequest(`/studio/benchmarks?${query.toString()}`, { signal }),
  );
}

/** Load one concrete Benchmark Package source by opaque identity. */
export async function getBenchmarkDetail(
  catalogEntryId: string,
  signal?: AbortSignal,
): Promise<BenchmarkDetail> {
  return parseBenchmarkDetail(
    await studioRequest(
      `/studio/benchmarks/${encodeURIComponent(catalogEntryId)}`,
      { signal },
    ),
  );
}

/** List one stable page of safe task templates for a split. */
export async function listBenchmarkTasks(
  catalogEntryId: string,
  split: string,
  limit = 50,
  cursor?: string,
  signal?: AbortSignal,
): Promise<BenchmarkTaskPage> {
  const query = new URLSearchParams({ split, limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  return parseBenchmarkTaskPage(
    await studioRequest(
      `/studio/benchmarks/${encodeURIComponent(catalogEntryId)}/tasks?${query.toString()}`,
      { signal },
    ),
  );
}

/** Run explicit full definition validation without executing a Benchmark. */
export async function validateBenchmark(
  catalogEntryId: string,
  split: string | null,
): Promise<BenchmarkValidationResult> {
  return parseBenchmarkValidationResult(
    await studioRequest(
      `/studio/benchmarks/${encodeURIComponent(catalogEntryId)}/validate`,
      {
        method: "POST",
        body: JSON.stringify({ schemaVersion: 1, split }),
      },
    ),
  );
}

/** List safe profile descriptors without resolving a physical device. */
export async function listDeviceProfiles(
  signal?: AbortSignal,
): Promise<DeviceProfilePage> {
  return parseDeviceProfilePage(
    await studioRequest("/studio/device-profiles", { signal }),
  );
}
