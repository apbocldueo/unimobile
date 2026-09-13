import { describe, expect, it } from "vitest";
import {
  benchmarkLegacyMigrationConfirmFixture,
  benchmarkLegacyMigrationPreviewFixture,
  parseBenchmarkLegacyMigrationConfirmResponse,
  parseBenchmarkLegacyMigrationPreview,
} from "@/entities/benchmark-authoring";

describe("Benchmark legacy migration schema", () => {
  it("parses strict Preview and migration provenance without source text", () => {
    const fixture = benchmarkLegacyMigrationPreviewFixture();
    fixture.diagnostics = [{
      code: "migration.warning",
      severity: "warning",
      message: "A safe source-wide warning.",
      fieldPath: [],
      sourceIndex: null,
      taskId: null,
    }];
    const wire = JSON.parse(JSON.stringify(fixture)) as Record<string, unknown>;
    const wireDiagnostic = (wire.diagnostics as Array<Record<string, unknown>>)[0];
    delete wireDiagnostic.sourceIndex;
    delete wireDiagnostic.taskId;
    const preview = parseBenchmarkLegacyMigrationPreview(wire);
    const confirmed = parseBenchmarkLegacyMigrationConfirmResponse(
      benchmarkLegacyMigrationConfirmFixture(),
    );
    expect(preview.diff.taskChanges).toMatchObject({ retained: 1, rewritten: 0 });
    expect(preview.diagnostics[0]).toMatchObject({ sourceIndex: null, taskId: null });
    expect(confirmed.revision.provenance.sourceKind).toBe("legacy_migration");
    expect(JSON.stringify(preview)).not.toContain("sourceText");
  });

  it("rejects unknown fields, non-zero mutation facts, and evidence claims", () => {
    expect(() => parseBenchmarkLegacyMigrationPreview({
      ...benchmarkLegacyMigrationPreviewFixture(),
      rawSource: "secret",
    })).toThrow(/rawSource/);
    const mutated = benchmarkLegacyMigrationPreviewFixture();
    (mutated.diff.taskChanges.rewritten as number) = 1;
    expect(() => parseBenchmarkLegacyMigrationPreview(mutated)).toThrow(/rewritten/);
    const claimed = benchmarkLegacyMigrationPreviewFixture();
    (claimed.evidence.execution as boolean) = true;
    expect(() => parseBenchmarkLegacyMigrationPreview(claimed)).toThrow(/execution/);
  });

  it("rejects malformed authority and optimistic Confirm additions", () => {
    const malformed = benchmarkLegacyMigrationConfirmFixture();
    malformed.previewFingerprint = "not-a-digest";
    expect(() => parseBenchmarkLegacyMigrationConfirmResponse(malformed)).toThrow(/malformed/);
    expect(() => parseBenchmarkLegacyMigrationConfirmResponse({
      ...benchmarkLegacyMigrationConfirmFixture(),
      optimistic: true,
    })).toThrow(/optimistic/);
  });
});
