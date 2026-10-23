import {
  benchmarkExperimentCreateInput,
  type CreateBenchmarkExperimentInput,
} from "@/entities/benchmark-experiment";
import type {
  ExperimentPreview,
  ExperimentPreviewRequest,
} from "@/entities/experiment-preview";

export type PreparedExperimentPreview = {
  semanticVersion: number;
  request: ExperimentPreviewRequest;
  value: ExperimentPreview;
  invalidated: boolean;
};

export type ExperimentCreateIntent = {
  semanticVersion: number;
  input: CreateBenchmarkExperimentInput;
};

/** Create one stable browser intent identity without persisting semantic data. */
export function createExperimentIntentId(): string {
  return `benchmark-create-${crypto.randomUUID()}`;
}

/** Determine whether one preview still belongs to the current Composer draft. */
export function isPreparedPreviewCurrent(
  preview: PreparedExperimentPreview | null,
  semanticVersion: number,
): preview is PreparedExperimentPreview {
  return (
    preview !== null
    && !preview.invalidated
    && preview.semanticVersion === semanticVersion
  );
}

/** Reuse an unknown-result intent or create one for the exact current preview. */
export function prepareExperimentCreateIntent(
  current: ExperimentCreateIntent | null,
  preview: PreparedExperimentPreview,
  createIdentity: () => string = createExperimentIntentId,
): ExperimentCreateIntent {
  if (
    current !== null
    && current.semanticVersion === preview.semanticVersion
    && current.input.previewFingerprint === preview.value.previewFingerprint
    && JSON.stringify(current.input.definition) === JSON.stringify(preview.request)
  ) {
    return current;
  }
  return {
    semanticVersion: preview.semanticVersion,
    input: benchmarkExperimentCreateInput(
      createIdentity(),
      preview.value.previewFingerprint,
      preview.request,
    ),
  };
}
