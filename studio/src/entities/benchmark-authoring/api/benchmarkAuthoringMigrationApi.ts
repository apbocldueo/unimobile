import { studioRequest } from "@/shared/api";
import {
  parseBenchmarkLegacyMigrationConfirmResponse,
  parseBenchmarkLegacyMigrationPreview,
  type BenchmarkLegacyMigrationConfirmRequest,
  type BenchmarkLegacyMigrationConfirmResponse,
  type BenchmarkLegacyMigrationPreview,
  type BenchmarkLegacyMigrationPreviewRequest,
} from "../model/benchmarkAuthoringMigration.schema";

/** Analyze browser-read legacy JSON text without creating durable state. */
export async function previewBenchmarkLegacyMigration(
  input: BenchmarkLegacyMigrationPreviewRequest,
): Promise<BenchmarkLegacyMigrationPreview> {
  return parseBenchmarkLegacyMigrationPreview(
    await studioRequest(
      "/studio/benchmark-authoring/legacy-migrations/preview",
      { method: "POST", body: JSON.stringify(input) },
    ),
  );
}

/** Confirm one exact reviewed migration and parse the authoritative draft. */
export async function confirmBenchmarkLegacyMigration(
  input: BenchmarkLegacyMigrationConfirmRequest,
): Promise<BenchmarkLegacyMigrationConfirmResponse> {
  return parseBenchmarkLegacyMigrationConfirmResponse(
    await studioRequest(
      "/studio/benchmark-authoring/legacy-migrations/confirm",
      { method: "POST", body: JSON.stringify(input) },
    ),
  );
}
