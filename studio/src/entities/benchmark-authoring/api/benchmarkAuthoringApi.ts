import {
  studioHeadRequest,
  studioRawJsonRequest,
  studioRequest,
  type StudioHeadResponse,
} from "@/shared/api";
import {
  parseBenchmarkAuthoringContentCommandResult,
  parseBenchmarkAuthoringRevision,
  parseBenchmarkDraftCommandResponse,
  parseBenchmarkDraftDetail,
  parseBenchmarkDraftPage,
  type BenchmarkAuthoringRevision,
  type BenchmarkAuthoringContentCommandResult,
  type BenchmarkDraftCommandResponse,
  type BenchmarkDraftDetail,
  type BenchmarkDraftPage,
  type CreateBenchmarkDraftInput,
  type SaveBenchmarkRevisionInput,
} from "../model/benchmarkAuthoring.schema";
import {
  parseBenchmarkDryRunResult,
  parseBenchmarkValidationResult,
  type BenchmarkDryRunRequest,
  type BenchmarkDryRunResult,
  type BenchmarkValidationRequest,
  type BenchmarkValidationResult,
} from "../model/benchmarkAuthoringAnalysis.schema";
import {
  parseBenchmarkContractTestProfilePage,
  parseBenchmarkContractTestResult,
  type BenchmarkContractTestProfilePage,
  type BenchmarkContractTestRequest,
  type BenchmarkContractTestResult,
} from "../model/benchmarkAuthoringContractTests.schema";

export type BenchmarkDraftListInput = {
  limit?: number;
  cursor?: string | null;
};

export type UploadBenchmarkAuthoringResourceInput = {
  draftId: string;
  baseRevisionId: string;
  clientRequestId: string;
  resourceId: string;
  kind: "asset" | "ground_truth";
  path: string;
  mediaType: string;
  body: Blob;
  signal?: AbortSignal;
};

export type ReplaceBenchmarkAuthoringResourceInput = {
  draftId: string;
  baseRevisionId: string;
  clientRequestId: string;
  resourceId: string;
  mediaType: string;
  body: Blob;
  signal?: AbortSignal;
};

export type RemoveBenchmarkAuthoringResourceInput = {
  draftId: string;
  baseRevisionId: string;
  clientRequestId: string;
  resourceId: string;
  signal?: AbortSignal;
};

export type HeadBenchmarkAuthoringResourceInput = {
  draftId: string;
  revisionId: string;
  resourceId: string;
  mediaType: string;
  size: number;
  signal?: AbortSignal;
};

export type ValidateBenchmarkDraftInput = {
  draftId: string;
  request: BenchmarkValidationRequest;
  signal?: AbortSignal;
};

export type DryRunBenchmarkDraftInput = {
  draftId: string;
  request: BenchmarkDryRunRequest;
  signal?: AbortSignal;
};

export type RunBenchmarkContractTestsInput = {
  draftId: string;
  request: BenchmarkContractTestRequest;
  signal?: AbortSignal;
};

/** Build one exact draft-owned resource command route. */
function resourceCommandPath(
  draftId: string,
  resourceId: string,
  operation: "upload" | "replace" | "remove",
  query: URLSearchParams,
): string {
  return (
    `/studio/benchmark-authoring/drafts/${encodeURIComponent(draftId)}`
    + `/resources/${encodeURIComponent(resourceId)}/${operation}`
    + `?${query.toString()}`
  );
}

/** Build one exact immutable revision/resource content capability. */
function resourceContentPath(
  draftId: string,
  revisionId: string,
  resourceId: string,
): string {
  return (
    `/studio/benchmark-authoring/drafts/${encodeURIComponent(draftId)}`
    + `/revisions/${encodeURIComponent(revisionId)}`
    + `/resources/${encodeURIComponent(resourceId)}/content`
  );
}

/** List one bounded cursor page of durable Benchmark drafts. */
export async function listBenchmarkDrafts(
  input: BenchmarkDraftListInput = {},
  signal?: AbortSignal,
): Promise<BenchmarkDraftPage> {
  const query = new URLSearchParams({ limit: String(input.limit ?? 30) });
  if (input.cursor) query.set("cursor", input.cursor);
  return parseBenchmarkDraftPage(
    await studioRequest(
      `/studio/benchmark-authoring/drafts?${query.toString()}`,
      { signal },
    ),
  );
}

/** Load one draft and its authoritative current immutable revision. */
export async function getBenchmarkDraft(
  draftId: string,
  signal?: AbortSignal,
): Promise<BenchmarkDraftDetail> {
  return parseBenchmarkDraftDetail(
    await studioRequest(
      `/studio/benchmark-authoring/drafts/${encodeURIComponent(draftId)}`,
      { signal },
    ),
  );
}

/** Load one exact immutable revision scoped by its owning draft. */
export async function getBenchmarkDraftRevision(
  draftId: string,
  revisionId: string,
  signal?: AbortSignal,
): Promise<BenchmarkAuthoringRevision> {
  return parseBenchmarkAuthoringRevision(
    await studioRequest(
      `/studio/benchmark-authoring/drafts/${encodeURIComponent(draftId)}/revisions/${encodeURIComponent(revisionId)}`,
      { signal },
    ),
  );
}

/** Create one durable draft with an idempotent browser command identity. */
export async function createBenchmarkDraft(
  input: CreateBenchmarkDraftInput,
): Promise<BenchmarkDraftCommandResponse> {
  return parseBenchmarkDraftCommandResponse(
    await studioRequest("/studio/benchmark-authoring/drafts", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  );
}

/** Append one immutable authoring revision with optimistic concurrency. */
export async function saveBenchmarkDraftRevision(
  draftId: string,
  input: SaveBenchmarkRevisionInput,
): Promise<BenchmarkDraftCommandResponse> {
  return parseBenchmarkDraftCommandResponse(
    await studioRequest(
      `/studio/benchmark-authoring/drafts/${encodeURIComponent(draftId)}/revisions`,
      {
        method: "POST",
        body: JSON.stringify(input),
      },
    ),
  );
}

/** Upload one new draft-owned managed resource as a raw browser body. */
export async function uploadBenchmarkAuthoringResource(
  input: UploadBenchmarkAuthoringResourceInput,
): Promise<BenchmarkAuthoringContentCommandResult> {
  const query = new URLSearchParams({
    schemaVersion: "1",
    clientRequestId: input.clientRequestId,
    baseRevisionId: input.baseRevisionId,
    kind: input.kind,
    path: input.path,
  });
  return parseBenchmarkAuthoringContentCommandResult(
    await studioRawJsonRequest(
      resourceCommandPath(input.draftId, input.resourceId, "upload", query),
      {
        body: input.body,
        contentType: input.mediaType,
        signal: input.signal,
      },
    ),
  );
}

/** Replace one owned resource while retaining its logical identity and path. */
export async function replaceBenchmarkAuthoringResource(
  input: ReplaceBenchmarkAuthoringResourceInput,
): Promise<BenchmarkAuthoringContentCommandResult> {
  const query = new URLSearchParams({
    schemaVersion: "1",
    clientRequestId: input.clientRequestId,
    baseRevisionId: input.baseRevisionId,
  });
  return parseBenchmarkAuthoringContentCommandResult(
    await studioRawJsonRequest(
      resourceCommandPath(input.draftId, input.resourceId, "replace", query),
      {
        body: input.body,
        contentType: input.mediaType,
        signal: input.signal,
      },
    ),
  );
}

/** Logically remove one resource from a new immutable revision. */
export async function removeBenchmarkAuthoringResource(
  input: RemoveBenchmarkAuthoringResourceInput,
): Promise<BenchmarkAuthoringContentCommandResult> {
  const query = new URLSearchParams({
    schemaVersion: "1",
    clientRequestId: input.clientRequestId,
    baseRevisionId: input.baseRevisionId,
  });
  return parseBenchmarkAuthoringContentCommandResult(
    await studioRawJsonRequest(
      resourceCommandPath(input.draftId, input.resourceId, "remove", query),
      { signal: input.signal },
    ),
  );
}

/** Verify one current-revision resource through its exact no-body capability. */
export async function headBenchmarkAuthoringResource(
  input: HeadBenchmarkAuthoringResourceInput,
): Promise<StudioHeadResponse> {
  return studioHeadRequest(
    resourceContentPath(input.draftId, input.revisionId, input.resourceId),
    {
      expectedContentType: input.mediaType,
      expectedBytes: input.size,
      signal: input.signal,
    },
  );
}

/**
 * Validate one exact current immutable authoring revision without side effects.
 *
 * Args:
 *   input: Draft owner, schema-1 revision request, and optional cancellation signal.
 *
 * Returns:
 *   A strict bounded validation projection.
 *
 * Raises:
 *   StudioApiError: The HTTP resource rejects ownership, capacity, or availability.
 *   Error: The success envelope violates the strict frontend contract.
 */
export async function validateBenchmarkDraft(
  input: ValidateBenchmarkDraftInput,
): Promise<BenchmarkValidationResult> {
  return parseBenchmarkValidationResult(
    await studioRequest(
      `/studio/benchmark-authoring/drafts/${encodeURIComponent(input.draftId)}/validate`,
      {
        method: "POST",
        body: JSON.stringify(input.request),
        signal: input.signal,
      },
    ),
  );
}

/**
 * Project one exact current revision into a deterministic non-executing plan.
 *
 * Args:
 *   input: Draft owner, exact task/Agent request, and optional cancellation signal.
 *
 * Returns:
 *   A strict complete bounded schedule projection with no execution evidence.
 *
 * Raises:
 *   StudioApiError: The HTTP resource rejects ownership, capacity, or availability.
 *   Error: The success envelope is malformed or claims contradictory facts.
 */
export async function dryRunBenchmarkDraft(
  input: DryRunBenchmarkDraftInput,
): Promise<BenchmarkDryRunResult> {
  return parseBenchmarkDryRunResult(
    await studioRequest(
      `/studio/benchmark-authoring/drafts/${encodeURIComponent(input.draftId)}/dry-run`,
      {
        method: "POST",
        body: JSON.stringify(input.request),
        signal: input.signal,
      },
    ),
  );
}

/** Load bounded metadata for server-owned fake-fixture profiles. */
export async function listBenchmarkContractTestProfiles(
  signal?: AbortSignal,
): Promise<BenchmarkContractTestProfilePage> {
  return parseBenchmarkContractTestProfilePage(
    await studioRequest(
      "/studio/benchmark-authoring/contract-test-profiles",
      { signal },
    ),
  );
}

/** Run transient fake-fixture contracts for one exact current revision. */
export async function runBenchmarkContractTests(
  input: RunBenchmarkContractTestsInput,
): Promise<BenchmarkContractTestResult> {
  return parseBenchmarkContractTestResult(
    await studioRequest(
      `/studio/benchmark-authoring/drafts/${encodeURIComponent(input.draftId)}/contract-tests`,
      {
        method: "POST",
        body: JSON.stringify(input.request),
        signal: input.signal,
      },
    ),
  );
}
