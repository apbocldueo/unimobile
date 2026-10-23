import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  exportBenchmarkPackage,
  freezeBenchmarkDraft,
  getBenchmarkPackageExport,
  getBenchmarkPackagePublication,
  listBenchmarkPackageRevisions,
  prepareBenchmarkPackageDownload,
  publishBenchmarkPackage,
  type BenchmarkExportReadInput,
  type BenchmarkPackageReleaseInput,
  type BenchmarkPackageRevisionListInput,
  type BenchmarkPublicationReadInput,
  type FreezeBenchmarkDraftInput,
} from "./benchmarkAuthoringReleaseApi";
import type { BenchmarkPackageExport } from "../model/benchmarkAuthoringRelease.schema";

export const benchmarkAuthoringReleaseKeys = {
  all: ["studio", "benchmark-authoring", "release"] as const,
  packageRevisions: (input: BenchmarkPackageRevisionListInput) =>
    ["studio", "benchmark-authoring", "release", "package-revisions", input] as const,
  publication: (input: BenchmarkPublicationReadInput) =>
    ["studio", "benchmark-authoring", "release", "publication", input] as const,
  packageExport: (input: BenchmarkExportReadInput) =>
    ["studio", "benchmark-authoring", "release", "export", input] as const,
};

/** Subscribe to one bounded page of immutable Package release candidates. */
export function useBenchmarkPackageRevisions(
  input: BenchmarkPackageRevisionListInput,
) {
  return useQuery({
    queryKey: benchmarkAuthoringReleaseKeys.packageRevisions(input),
    queryFn: ({ signal }) => listBenchmarkPackageRevisions(input, signal),
    placeholderData: keepPreviousData,
    enabled: input.draftId.length > 0,
  });
}

/** Subscribe to one exact immutable managed publication. */
export function useBenchmarkPackagePublication(
  input: BenchmarkPublicationReadInput | null,
) {
  return useQuery({
    queryKey: input
      ? benchmarkAuthoringReleaseKeys.publication(input)
      : [...benchmarkAuthoringReleaseKeys.all, "publication-disabled"],
    queryFn: ({ signal }) => getBenchmarkPackagePublication(input!, signal),
    enabled: input !== null,
  });
}

/** Subscribe to one exact immutable deterministic export descriptor. */
export function useBenchmarkPackageExport(input: BenchmarkExportReadInput | null) {
  return useQuery({
    queryKey: input
      ? benchmarkAuthoringReleaseKeys.packageExport(input)
      : [...benchmarkAuthoringReleaseKeys.all, "export-disabled"],
    queryFn: ({ signal }) => getBenchmarkPackageExport(input!, signal),
    enabled: input !== null,
  });
}

/** Freeze one clean exact-current revision and refresh release candidates. */
export function useFreezeBenchmarkDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: FreezeBenchmarkDraftInput) => freezeBenchmarkDraft(input),
    onSuccess: (_result, input) => {
      void queryClient.invalidateQueries({
        queryKey: [
          "studio",
          "benchmark-authoring",
          "release",
          "package-revisions",
        ],
      });
      void queryClient.invalidateQueries({
        queryKey: ["studio", "benchmark-authoring", "draft", input.draftId],
      });
    },
  });
}

/** Publish one Package then refresh release and Catalog server facts. */
export function usePublishBenchmarkPackage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: BenchmarkPackageReleaseInput) =>
      publishBenchmarkPackage(input),
    onSuccess: (result, input) => {
      queryClient.setQueryData(
        benchmarkAuthoringReleaseKeys.publication({
          draftId: result.publication.draftId,
          packageRevisionId: result.publication.packageRevisionId,
          publicationId: result.publication.publicationId,
        }),
        result.publication,
      );
      void queryClient.invalidateQueries({
        queryKey: [
          "studio",
          "benchmark-authoring",
          "release",
          "package-revisions",
        ],
      });
      void queryClient.invalidateQueries({
        queryKey: ["studio", "benchmark-catalog"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["studio", "benchmark-authoring", "draft", input.draftId],
      });
    },
  });
}

/** Export one Package then refresh its immutable release facts. */
export function useExportBenchmarkPackage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: BenchmarkPackageReleaseInput) =>
      exportBenchmarkPackage(input),
    onSuccess: (result) => {
      queryClient.setQueryData(
        benchmarkAuthoringReleaseKeys.packageExport({
          draftId: result.packageExport.draftId,
          packageRevisionId: result.packageExport.packageRevisionId,
          exportId: result.packageExport.exportId,
        }),
        result.packageExport,
      );
      void queryClient.invalidateQueries({
        queryKey: [
          "studio",
          "benchmark-authoring",
          "release",
          "package-revisions",
        ],
      });
    },
  });
}

/** Run exact no-body download preparation as an explicit user mutation. */
export function usePrepareBenchmarkPackageDownload() {
  return useMutation({
    mutationFn: ({
      packageExport,
      signal,
    }: {
      packageExport: BenchmarkPackageExport;
      signal?: AbortSignal;
    }) => prepareBenchmarkPackageDownload(packageExport, signal),
  });
}
