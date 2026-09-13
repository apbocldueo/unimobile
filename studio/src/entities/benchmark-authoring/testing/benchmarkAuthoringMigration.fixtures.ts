import type {
  BenchmarkLegacyMigrationConfirmResponse,
  BenchmarkLegacyMigrationPreview,
  BenchmarkLegacyMigrationTarget,
} from "../model/benchmarkAuthoringMigration.schema";
import {
  benchmarkAuthoringRevisionFixture,
  benchmarkDraftDetailFixture,
} from "./benchmarkAuthoring.fixtures";

export const benchmarkMigrationDigestFixture = `sha256:${"9".repeat(64)}`;

/** Build the explicit Package wrapper used by migration tests. */
export function benchmarkLegacyMigrationTargetFixture(): BenchmarkLegacyMigrationTarget {
  return {
    draftName: "Imported legacy Benchmark",
    publisher: "local",
    packageName: "legacy-benchmark",
    version: "0.1.0",
    title: "Imported legacy Benchmark",
    platform: "android",
    split: "test",
    taskFilePath: "tasks/imported.json",
  };
}

/** Build one strict confirmable, all-false migration Preview fixture. */
export function benchmarkLegacyMigrationPreviewFixture(): BenchmarkLegacyMigrationPreview {
  return {
    schemaVersion: 1,
    confirmable: true,
    source: {
      sourceName: "legacy.json",
      utf8Size: 128,
      sourceFingerprint: benchmarkMigrationDigestFixture,
      entryCount: 1,
      uniqueTaskCount: 1,
    },
    target: benchmarkLegacyMigrationTargetFixture(),
    migrationContractIdentity: benchmarkMigrationDigestFixture,
    candidateDocumentFingerprint: benchmarkMigrationDigestFixture,
    previewFingerprint: benchmarkMigrationDigestFixture,
    diff: {
      taskChanges: {
        retained: 1,
        renamed: 0,
        removed: 0,
        deduplicated: 0,
        rewritten: 0,
      },
      entries: [{
        code: "migration.wrapper",
        category: "wrapper",
        path: ["manifest"],
        message: "Adds the explicit Package wrapper.",
      }],
      pluginIds: ["fixture.initializer"],
      appIds: [],
    },
    diagnostics: [],
    postMigrationWork: [{
      code: "migration.resources",
      message: "Review legacy resource references.",
      sourceIndexes: [0],
    }],
    evidence: {
      validation: false,
      contractTest: false,
      freeze: false,
      publication: false,
      export: false,
      execution: false,
      device: false,
    },
  };
}

/** Build one authoritative legacy-migration Confirm response. */
export function benchmarkLegacyMigrationConfirmFixture(
  created = true,
): BenchmarkLegacyMigrationConfirmResponse {
  const detail = benchmarkDraftDetailFixture();
  const revision = benchmarkAuthoringRevisionFixture("edit");
  revision.provenance = {
    sourceKind: "legacy_migration",
    templateName: null,
    catalogEntryId: null,
    catalogSnapshotIdentity: null,
    packageIdentity: null,
    sourceFingerprint: benchmarkMigrationDigestFixture,
    sourceDisplayName: "legacy.json",
    previewFingerprint: benchmarkMigrationDigestFixture,
    candidateDocumentFingerprint: benchmarkMigrationDigestFixture,
    migrationContractIdentity: benchmarkMigrationDigestFixture,
    taskEntryCount: 1,
    uniqueTaskCount: 1,
  };
  return {
    schemaVersion: 1,
    created,
    draft: detail.draft,
    revision,
    sourceFingerprint: benchmarkMigrationDigestFixture,
    previewFingerprint: benchmarkMigrationDigestFixture,
    migrationContractIdentity: benchmarkMigrationDigestFixture,
    candidateDocumentFingerprint: benchmarkMigrationDigestFixture,
    evidence: benchmarkLegacyMigrationPreviewFixture().evidence,
  };
}
