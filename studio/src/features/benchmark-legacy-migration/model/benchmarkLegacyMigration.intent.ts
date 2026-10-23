import type {
  BenchmarkLegacyMigrationConfirmRequest,
  BenchmarkLegacyMigrationPreviewRequest,
  BenchmarkLegacyMigrationPreview,
} from "@/entities/benchmark-authoring";

export type BenchmarkLegacyMigrationConfirmIntent = {
  semanticKey: string;
  input: BenchmarkLegacyMigrationConfirmRequest;
};

/** Build a stable key for one exact reviewed source, target, and Preview. */
export function benchmarkLegacyMigrationSemanticKey(
  request: BenchmarkLegacyMigrationPreviewRequest,
  preview: BenchmarkLegacyMigrationPreview,
): string {
  return JSON.stringify({
    request,
    previewFingerprint: preview.previewFingerprint,
    migrationContractIdentity: preview.migrationContractIdentity,
  });
}

/** Preserve a Confirm request ID only while its complete authority is unchanged. */
export function prepareBenchmarkLegacyMigrationConfirmIntent(
  current: BenchmarkLegacyMigrationConfirmIntent | null,
  request: BenchmarkLegacyMigrationPreviewRequest,
  preview: BenchmarkLegacyMigrationPreview,
): BenchmarkLegacyMigrationConfirmIntent {
  if (!preview.confirmable || preview.previewFingerprint === null) {
    throw new Error("Only a confirmable current Preview can be confirmed.");
  }
  const semanticKey = benchmarkLegacyMigrationSemanticKey(request, preview);
  if (current?.semanticKey === semanticKey) return current;
  return {
    semanticKey,
    input: {
      ...request,
      clientRequestId: `benchmark-migration-${crypto.randomUUID()}`,
      previewFingerprint: preview.previewFingerprint,
      migrationContractIdentity: preview.migrationContractIdentity,
    },
  };
}
