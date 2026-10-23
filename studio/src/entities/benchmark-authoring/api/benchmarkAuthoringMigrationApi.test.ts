import { afterEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkLegacyMigrationConfirmFixture,
  benchmarkLegacyMigrationPreviewFixture,
  benchmarkLegacyMigrationTargetFixture,
  confirmBenchmarkLegacyMigration,
  previewBenchmarkLegacyMigration,
} from "@/entities/benchmark-authoring";

afterEach(() => vi.unstubAllGlobals());

describe("Benchmark legacy migration API", () => {
  it("sends source text to only the exact Preview route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(benchmarkLegacyMigrationPreviewFixture()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await previewBenchmarkLegacyMigration({
      schemaVersion: 1,
      sourceName: "legacy.json",
      sourceText: "[]",
      target: benchmarkLegacyMigrationTargetFixture(),
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/legacy-migrations\/preview$/),
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(body).toMatchObject({ sourceName: "legacy.json", sourceText: "[]" });
    expect(body).not.toHaveProperty("sourcePath");
  });

  it.each([201, 200])("parses authoritative Confirm status %s", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(benchmarkLegacyMigrationConfirmFixture(status === 201)), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    ));
    const result = await confirmBenchmarkLegacyMigration({
      schemaVersion: 1,
      sourceName: "legacy.json",
      sourceText: "[]",
      target: benchmarkLegacyMigrationTargetFixture(),
      clientRequestId: "migration-request-1",
      previewFingerprint: benchmarkLegacyMigrationPreviewFixture().previewFingerprint!,
      migrationContractIdentity: benchmarkLegacyMigrationPreviewFixture().migrationContractIdentity,
    });
    expect(result.created).toBe(status === 201);
    expect(result.revision.provenance.sourceKind).toBe("legacy_migration");
  });
});
