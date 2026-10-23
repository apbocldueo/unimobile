import { useMutation, useQueryClient } from "@tanstack/react-query";
import { benchmarkAuthoringKeys } from "./benchmarkAuthoring.queries";
import {
  confirmBenchmarkLegacyMigration,
  previewBenchmarkLegacyMigration,
} from "./benchmarkAuthoringMigrationApi";
import type {
  BenchmarkLegacyMigrationConfirmRequest,
  BenchmarkLegacyMigrationPreviewRequest,
} from "../model/benchmarkAuthoringMigration.schema";

/** Run an explicitly requested transient Preview without caching authority. */
export function usePreviewBenchmarkLegacyMigration() {
  return useMutation({
    mutationFn: (input: BenchmarkLegacyMigrationPreviewRequest) =>
      previewBenchmarkLegacyMigration(input),
  });
}

/** Confirm migration and adopt only the authoritative server revision. */
export function useConfirmBenchmarkLegacyMigration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: BenchmarkLegacyMigrationConfirmRequest) =>
      confirmBenchmarkLegacyMigration(input),
    onSuccess: (response) => {
      const draftId = response.draft.draftId;
      queryClient.setQueryData(benchmarkAuthoringKeys.detail(draftId), {
        schemaVersion: 1,
        draft: response.draft,
        currentRevision: response.revision,
      });
      queryClient.setQueryData(
        benchmarkAuthoringKeys.revision(draftId, response.revision.revisionId),
        response.revision,
      );
      void queryClient.invalidateQueries({
        queryKey: ["studio", "benchmark-authoring", "drafts"],
      });
    },
  });
}
