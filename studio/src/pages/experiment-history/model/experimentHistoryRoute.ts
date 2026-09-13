import {
  normalizeBenchmarkExperimentHistoryFilters,
  type BenchmarkExperimentHistoryFilters,
  type BenchmarkExperimentLifecycle,
} from "@/entities/benchmark-experiment";

export type ExperimentHistoryRoute =
  | {
      mode: "history";
      limit: number;
      cursor: string | null;
      filters: BenchmarkExperimentHistoryFilters;
    }
  | { mode: "invalid"; reason: string };

const ALLOWED_QUERY_KEYS = new Set([
  "limit",
  "cursor",
  "lifecycle",
  "catalogEntryId",
  "agentId",
  "acceptedFrom",
  "acceptedBefore",
]);
const LIFECYCLES = new Set<BenchmarkExperimentLifecycle>([
  "accepted",
  "starting",
  "running",
  "cancelling",
  "finalizing",
  "terminal",
]);
const STABLE_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/;
const CANONICAL_INTEGER = /^(0|[1-9][0-9]*)$/;

/** Parse one optional canonical non-negative JavaScript-safe integer. */
function parseSafeEpoch(
  params: URLSearchParams,
  key: "acceptedFrom" | "acceptedBefore",
): number | undefined {
  const value = params.get(key);
  if (value === null) return undefined;
  if (!CANONICAL_INTEGER.test(value)) {
    throw new Error(`${key} 不是 canonical epoch milliseconds。`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error(`${key} 超出 JavaScript-safe integer 范围。`);
  }
  return parsed;
}

/** Parse the complete reconstructable `/experiments` query contract. */
export function parseExperimentHistoryRoute(
  params: URLSearchParams,
): ExperimentHistoryRoute {
  for (const key of params.keys()) {
    if (!ALLOWED_QUERY_KEYS.has(key)) {
      return { mode: "invalid", reason: `History 地址含未知参数：${key}` };
    }
  }
  for (const key of ALLOWED_QUERY_KEYS) {
    const values = params.getAll(key);
    if (values.length > 1) {
      return { mode: "invalid", reason: `History 地址重复参数：${key}` };
    }
    if (values.length === 1 && values[0] === "") {
      return { mode: "invalid", reason: `History 地址含空参数：${key}` };
    }
  }
  const limitValue = params.get("limit") ?? "50";
  if (!CANONICAL_INTEGER.test(limitValue)) {
    return { mode: "invalid", reason: "limit 不是 canonical integer。" };
  }
  const limit = Number(limitValue);
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    return { mode: "invalid", reason: "limit 必须位于 1 到 100。" };
  }
  const cursor = params.get("cursor");
  if (cursor !== null && cursor.length > 2048) {
    return { mode: "invalid", reason: "cursor 超出有界长度。" };
  }
  const lifecycleValue = params.get("lifecycle");
  if (
    lifecycleValue !== null
    && !LIFECYCLES.has(lifecycleValue as BenchmarkExperimentLifecycle)
  ) {
    return { mode: "invalid", reason: "lifecycle 不受支持。" };
  }
  const catalogEntryId = params.get("catalogEntryId") ?? undefined;
  const agentId = params.get("agentId") ?? undefined;
  if (catalogEntryId !== undefined && !STABLE_ID.test(catalogEntryId)) {
    return { mode: "invalid", reason: "catalogEntryId 不符合 exact identity。" };
  }
  if (agentId !== undefined && !STABLE_ID.test(agentId)) {
    return { mode: "invalid", reason: "agentId 不符合 exact identity。" };
  }
  try {
    const filters = normalizeBenchmarkExperimentHistoryFilters({
      ...(lifecycleValue === null
        ? {}
        : { lifecycle: lifecycleValue as BenchmarkExperimentLifecycle }),
      ...(catalogEntryId === undefined ? {} : { catalogEntryId }),
      ...(agentId === undefined ? {} : { agentId }),
      acceptedFrom: parseSafeEpoch(params, "acceptedFrom"),
      acceptedBefore: parseSafeEpoch(params, "acceptedBefore"),
    });
    return { mode: "history", limit, cursor, filters };
  } catch (error) {
    return {
      mode: "invalid",
      reason: error instanceof Error ? error.message : "History filter 无效。",
    };
  }
}

/** Serialize one valid History state in fixed canonical query-key order. */
export function serializeExperimentHistoryRoute(
  route: Extract<ExperimentHistoryRoute, { mode: "history" }>,
): URLSearchParams {
  const filters = normalizeBenchmarkExperimentHistoryFilters(route.filters);
  const params = new URLSearchParams({ limit: String(route.limit) });
  if (filters.lifecycle) params.set("lifecycle", filters.lifecycle);
  if (filters.catalogEntryId) {
    params.set("catalogEntryId", filters.catalogEntryId);
  }
  if (filters.agentId) params.set("agentId", filters.agentId);
  if (filters.acceptedFrom !== undefined) {
    params.set("acceptedFrom", String(filters.acceptedFrom));
  }
  if (filters.acceptedBefore !== undefined) {
    params.set("acceptedBefore", String(filters.acceptedBefore));
  }
  if (route.cursor) params.set("cursor", route.cursor);
  return params;
}
