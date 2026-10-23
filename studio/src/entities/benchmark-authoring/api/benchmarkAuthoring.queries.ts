import {
  keepPreviousData,
  type QueryClient,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  createBenchmarkDraft,
  dryRunBenchmarkDraft,
  getBenchmarkDraft,
  getBenchmarkDraftRevision,
  headBenchmarkAuthoringResource,
  listBenchmarkDrafts,
  listBenchmarkContractTestProfiles,
  removeBenchmarkAuthoringResource,
  replaceBenchmarkAuthoringResource,
  saveBenchmarkDraftRevision,
  runBenchmarkContractTests,
  uploadBenchmarkAuthoringResource,
  type BenchmarkDraftListInput,
  type DryRunBenchmarkDraftInput,
  type HeadBenchmarkAuthoringResourceInput,
  type RemoveBenchmarkAuthoringResourceInput,
  type ReplaceBenchmarkAuthoringResourceInput,
  type UploadBenchmarkAuthoringResourceInput,
  type ValidateBenchmarkDraftInput,
  type RunBenchmarkContractTestsInput,
  validateBenchmarkDraft,
} from "./benchmarkAuthoringApi";
import type {
  BenchmarkAuthoringContentCommandResult,
  BenchmarkAuthoringRevision,
  BenchmarkDraftDetail,
  CreateBenchmarkDraftInput,
  SaveBenchmarkRevisionInput,
} from "../model/benchmarkAuthoring.schema";

export type BenchmarkAuthoringContentMutationOutcome = {
  result: BenchmarkAuthoringContentCommandResult;
  currentRevision: BenchmarkAuthoringRevision;
  historicalRetry: boolean;
};

export const benchmarkAuthoringKeys = {
  all: ["studio", "benchmark-authoring"] as const,
  drafts: (input: BenchmarkDraftListInput) =>
    ["studio", "benchmark-authoring", "drafts", input] as const,
  detail: (draftId: string) =>
    ["studio", "benchmark-authoring", "draft", draftId] as const,
  revision: (draftId: string, revisionId: string) =>
    [
      "studio",
      "benchmark-authoring",
      "draft",
      draftId,
      "revision",
      revisionId,
    ] as const,
  resourceHead: (draftId: string, revisionId: string, resourceId: string) =>
    [
      "studio",
      "benchmark-authoring",
      "draft",
      draftId,
      "revision",
      revisionId,
      "resource",
      resourceId,
      "head",
    ] as const,
  contractTestProfiles: () =>
    ["studio", "benchmark-authoring", "contract-test-profiles"] as const,
};

/**
 * Reconcile a managed-content result without regressing the current draft.
 *
 * Args:
 *   queryClient: TanStack Query cache that owns server-authoritative state.
 *   result: Strict upload, replacement, or logical-removal response.
 *   loadCurrent: Authoritative detail loader, injectable for focused tests.
 *
 * Returns:
 *   The command result plus the revision that is safe for editor rehydration.
 */
export async function reconcileBenchmarkAuthoringContentResult(
  queryClient: QueryClient,
  result: BenchmarkAuthoringContentCommandResult,
  loadCurrent: (draftId: string) => Promise<BenchmarkDraftDetail> =
    getBenchmarkDraft,
): Promise<BenchmarkAuthoringContentMutationOutcome> {
  const draftId = result.draft.draftId;
  queryClient.setQueryData(
    benchmarkAuthoringKeys.revision(draftId, result.revision.revisionId),
    result.revision,
  );

  if (result.draft.currentRevisionId === result.revision.revisionId) {
    queryClient.setQueryData(benchmarkAuthoringKeys.detail(draftId), {
      schemaVersion: 1,
      draft: result.draft,
      currentRevision: result.revision,
    } satisfies BenchmarkDraftDetail);
    void queryClient.invalidateQueries({
      queryKey: ["studio", "benchmark-authoring", "drafts"],
    });
    return {
      result,
      currentRevision: result.revision,
      historicalRetry: false,
    };
  }

  // An exact idempotent retry may truthfully return an older committed
  // revision. Fetch the moving pointer before allowing another command.
  const currentDetail = await queryClient.fetchQuery({
    queryKey: benchmarkAuthoringKeys.detail(draftId),
    queryFn: () => loadCurrent(draftId),
    staleTime: 0,
  });
  void queryClient.invalidateQueries({
    queryKey: ["studio", "benchmark-authoring", "drafts"],
  });
  return {
    result,
    currentRevision: currentDetail.currentRevision,
    historicalRetry: true,
  };
}

/** Build reusable query options for one bounded draft page. */
export function benchmarkDraftsQueryOptions(input: BenchmarkDraftListInput) {
  return queryOptions({
    queryKey: benchmarkAuthoringKeys.drafts(input),
    queryFn: ({ signal }) => listBenchmarkDrafts(input, signal),
    placeholderData: keepPreviousData,
  });
}

/** Subscribe to one bounded page of draft metadata. */
export function useBenchmarkDrafts(input: BenchmarkDraftListInput) {
  return useQuery(benchmarkDraftsQueryOptions(input));
}

/** Subscribe to one authoritative draft/current-revision pair. */
export function useBenchmarkDraft(draftId: string) {
  return useQuery({
    queryKey: benchmarkAuthoringKeys.detail(draftId),
    queryFn: ({ signal }) => getBenchmarkDraft(draftId, signal),
    enabled: draftId.length > 0,
  });
}

/** Subscribe to one exact immutable revision owned by a draft. */
export function useBenchmarkDraftRevision(
  draftId: string,
  revisionId: string,
) {
  return useQuery({
    queryKey: benchmarkAuthoringKeys.revision(draftId, revisionId),
    queryFn: ({ signal }) =>
      getBenchmarkDraftRevision(draftId, revisionId, signal),
    enabled: draftId.length > 0 && revisionId.length > 0,
  });
}

/** Lazily verify only the currently selected immutable revision resource. */
export function useBenchmarkAuthoringResourceHead(
  input: HeadBenchmarkAuthoringResourceInput | null,
) {
  return useQuery({
    queryKey: input
      ? benchmarkAuthoringKeys.resourceHead(
          input.draftId,
          input.revisionId,
          input.resourceId,
        )
      : [...benchmarkAuthoringKeys.all, "resource-head-disabled"],
    queryFn: ({ signal }) =>
      headBenchmarkAuthoringResource({ ...input!, signal }),
    enabled: input !== null,
    retry: false,
  });
}

/** Create a draft and seed its authoritative detail and revision caches. */
export function useCreateBenchmarkDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateBenchmarkDraftInput) =>
      createBenchmarkDraft(input),
    onSuccess: (response) => {
      queryClient.setQueryData(
        benchmarkAuthoringKeys.detail(response.draft.draftId),
        {
          schemaVersion: 1,
          draft: response.draft,
          currentRevision: response.revision,
        },
      );
      queryClient.setQueryData(
        benchmarkAuthoringKeys.revision(
          response.draft.draftId,
          response.revision.revisionId,
        ),
        response.revision,
      );
      void queryClient.invalidateQueries({
        queryKey: benchmarkAuthoringKeys.all,
      });
    },
  });
}

/** Save a revision and replace only authoritative server-resource caches. */
export function useSaveBenchmarkDraftRevision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      draftId,
      input,
    }: {
      draftId: string;
      input: SaveBenchmarkRevisionInput;
    }) => saveBenchmarkDraftRevision(draftId, input),
    onSuccess: (response) => {
      queryClient.setQueryData(
        benchmarkAuthoringKeys.detail(response.draft.draftId),
        {
          schemaVersion: 1,
          draft: response.draft,
          currentRevision: response.revision,
        },
      );
      queryClient.setQueryData(
        benchmarkAuthoringKeys.revision(
          response.draft.draftId,
          response.revision.revisionId,
        ),
        response.revision,
      );
      void queryClient.invalidateQueries({
        queryKey: benchmarkAuthoringKeys.all,
      });
    },
  });
}

/** Upload a managed resource and reconcile immutable/current revision caches. */
export function useUploadBenchmarkAuthoringResource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: UploadBenchmarkAuthoringResourceInput) =>
      reconcileBenchmarkAuthoringContentResult(
        queryClient,
        await uploadBenchmarkAuthoringResource(input),
      ),
  });
}

/** Replace a managed resource and reconcile immutable/current revision caches. */
export function useReplaceBenchmarkAuthoringResource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: ReplaceBenchmarkAuthoringResourceInput) =>
      reconcileBenchmarkAuthoringContentResult(
        queryClient,
        await replaceBenchmarkAuthoringResource(input),
      ),
  });
}

/** Logically remove a resource and reconcile immutable/current revision caches. */
export function useRemoveBenchmarkAuthoringResource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: RemoveBenchmarkAuthoringResourceInput) =>
      reconcileBenchmarkAuthoringContentResult(
        queryClient,
        await removeBenchmarkAuthoringResource(input),
      ),
  });
}

/** Execute transient revision-bound validation without writing Query cache. */
export function useValidateBenchmarkDraft() {
  return useMutation({
    mutationFn: (input: ValidateBenchmarkDraftInput) =>
      validateBenchmarkDraft(input),
  });
}

/** Execute transient side-effect-free dry-run without writing Query cache. */
export function useDryRunBenchmarkDraft() {
  return useMutation({
    mutationFn: (input: DryRunBenchmarkDraftInput) =>
      dryRunBenchmarkDraft(input),
  });
}

/** Subscribe to bounded server-owned fixture-profile metadata. */
export function useBenchmarkContractTestProfiles() {
  return useQuery({
    queryKey: benchmarkAuthoringKeys.contractTestProfiles(),
    queryFn: ({ signal }) => listBenchmarkContractTestProfiles(signal),
    staleTime: 30_000,
  });
}

/** Execute transient exact-revision fake-fixture Contract Tests. */
export function useRunBenchmarkContractTests() {
  return useMutation({
    mutationFn: (input: RunBenchmarkContractTestsInput) =>
      runBenchmarkContractTests(input),
  });
}
