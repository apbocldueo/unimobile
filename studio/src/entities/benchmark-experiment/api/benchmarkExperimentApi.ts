import type { ExperimentPreviewRequest } from "@/entities/experiment-preview";
import { studioRequest } from "@/shared/api";
import {
  parseBenchmarkExperimentEventPage,
  parseBenchmarkExperimentHistoryPage,
  parseBenchmarkExperimentResource,
  parseBenchmarkTaskRun,
  parseBenchmarkTaskRunPage,
  parseCreateBenchmarkExperimentResponse,
  type BenchmarkExperimentEventPage,
  type BenchmarkExperimentHistoryFilters,
  type BenchmarkExperimentHistoryPage,
  type BenchmarkExperimentResource,
  type BenchmarkTaskRun,
  type BenchmarkTaskRunPage,
  type CancelBenchmarkExperimentInput,
  type CreateBenchmarkExperimentInput,
  type CreateBenchmarkExperimentResponse,
} from "../model/benchmarkExperiment.schema";

const STABLE_HISTORY_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/;
const HISTORY_LIFECYCLES = new Set([
  "accepted",
  "starting",
  "running",
  "cancelling",
  "finalizing",
  "terminal",
]);

/** Validate and canonicalize optional exact Experiment History filters. */
export function normalizeBenchmarkExperimentHistoryFilters(
  filters: BenchmarkExperimentHistoryFilters = {},
): BenchmarkExperimentHistoryFilters {
  const normalized: {
    lifecycle?: BenchmarkExperimentHistoryFilters["lifecycle"];
    catalogEntryId?: string;
    agentId?: string;
    acceptedFrom?: number;
    acceptedBefore?: number;
  } = {};
  if (filters.lifecycle !== undefined) {
    if (!HISTORY_LIFECYCLES.has(filters.lifecycle)) {
      throw new Error("lifecycle is invalid");
    }
    normalized.lifecycle = filters.lifecycle;
  }
  for (const key of ["catalogEntryId", "agentId"] as const) {
    const value = filters[key];
    if (value !== undefined) {
      if (!STABLE_HISTORY_ID.test(value)) {
        throw new Error(`${key} is invalid`);
      }
      normalized[key] = value;
    }
  }
  for (const key of ["acceptedFrom", "acceptedBefore"] as const) {
    const value = filters[key];
    if (value !== undefined) {
      if (!Number.isSafeInteger(value) || value < 0) {
        throw new Error(`${key} must be a non-negative safe integer`);
      }
      normalized[key] = value;
    }
  }
  if (
    normalized.acceptedFrom !== undefined
    && normalized.acceptedBefore !== undefined
    && normalized.acceptedFrom >= normalized.acceptedBefore
  ) {
    throw new Error("acceptedFrom must precede acceptedBefore");
  }
  return Object.freeze(normalized);
}

/** List a bounded newest-first page of compact Benchmark Experiments. */
export async function listBenchmarkExperiments(
  cursor: string | null = null,
  limit = 50,
  filters: BenchmarkExperimentHistoryFilters = {},
  signal?: AbortSignal,
): Promise<BenchmarkExperimentHistoryPage> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error("limit must be an integer from 1 through 100");
  }
  const normalized = normalizeBenchmarkExperimentHistoryFilters(filters);
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  if (normalized.lifecycle) {
    query.set("lifecycle", normalized.lifecycle);
  }
  if (normalized.catalogEntryId) {
    query.set("catalogEntryId", normalized.catalogEntryId);
  }
  if (normalized.agentId) query.set("agentId", normalized.agentId);
  if (normalized.acceptedFrom !== undefined) {
    query.set("acceptedFrom", String(normalized.acceptedFrom));
  }
  if (normalized.acceptedBefore !== undefined) {
    query.set("acceptedBefore", String(normalized.acceptedBefore));
  }
  return parseBenchmarkExperimentHistoryPage(
    await studioRequest(
      `/studio/benchmark-experiments?${query.toString()}`,
      { signal },
    ),
  );
}

/** Create or retrieve one idempotent durable Benchmark Experiment. */
export async function createBenchmarkExperiment(
  input: CreateBenchmarkExperimentInput,
): Promise<CreateBenchmarkExperimentResponse> {
  return parseCreateBenchmarkExperimentResponse(
    await studioRequest("/studio/benchmark-experiments", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  );
}

/** Build one complete create request from the current successful preview. */
export function benchmarkExperimentCreateInput(
  clientRequestId: string,
  previewFingerprint: string,
  definition: ExperimentPreviewRequest,
): CreateBenchmarkExperimentInput {
  return {
    schemaVersion: 1,
    clientRequestId,
    previewFingerprint,
    definition,
  };
}

/** Load one authoritative durable Benchmark Experiment resource. */
export async function getBenchmarkExperiment(
  experimentId: string,
): Promise<BenchmarkExperimentResource> {
  return parseBenchmarkExperimentResource(
    await studioRequest(
      `/studio/benchmark-experiments/${encodeURIComponent(experimentId)}`,
    ),
  );
}

/** Request cooperative cancellation using an explicit idempotency identity. */
export async function cancelBenchmarkExperiment(
  input: CancelBenchmarkExperimentInput,
): Promise<BenchmarkExperimentResource> {
  return parseBenchmarkExperimentResource(
    await studioRequest(
      `/studio/benchmark-experiments/${encodeURIComponent(input.experimentId)}/cancel`,
      {
        method: "POST",
        body: JSON.stringify({
          schemaVersion: 1,
          clientRequestId: input.clientRequestId,
          reasonCode: "user_requested",
        }),
      },
    ),
  );
}

/** List a bounded stable page of TaskRuns scoped to one Experiment. */
export async function listBenchmarkTaskRuns(
  experimentId: string,
  cursor: string | null = null,
  limit = 100,
): Promise<BenchmarkTaskRunPage> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error("limit must be an integer from 1 through 100");
  }
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  return parseBenchmarkTaskRunPage(
    await studioRequest(
      `/studio/benchmark-experiments/${encodeURIComponent(experimentId)}/task-runs?${query.toString()}`,
    ),
  );
}

/** Load one TaskRun only through its owning Experiment scope. */
export async function getBenchmarkTaskRun(
  experimentId: string,
  taskRunId: string,
): Promise<BenchmarkTaskRun> {
  return parseBenchmarkTaskRun(
    await studioRequest(
      `/studio/benchmark-experiments/${encodeURIComponent(experimentId)}/task-runs/${encodeURIComponent(taskRunId)}`,
    ),
  );
}

/** Query one bounded journal page after an exclusive Experiment-local cursor. */
export async function getBenchmarkExperimentEvents(
  experimentId: string,
  after: number,
  limit = 100,
): Promise<BenchmarkExperimentEventPage> {
  if (!Number.isInteger(after) || after < 0) {
    throw new Error("after must be a non-negative integer");
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > 500) {
    throw new Error("limit must be an integer from 1 through 500");
  }
  const query = new URLSearchParams({
    after: String(after),
    limit: String(limit),
  });
  return parseBenchmarkExperimentEventPage(
    await studioRequest(
      `/studio/benchmark-experiments/${encodeURIComponent(experimentId)}/events?${query.toString()}`,
    ),
  );
}
