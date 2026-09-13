import { describe, expect, it } from "vitest";
import {
  parseBenchmarkAuthoringContentCommandResult,
  parseBenchmarkAuthoringDocument,
  parseBenchmarkDraftDetail,
  parseBenchmarkDraftPage,
} from "@/entities/benchmark-authoring";
import {
  benchmarkAuthoringContentCommandFixture,
  benchmarkAuthoringDocumentFixture,
  benchmarkDraftDetailFixture,
  benchmarkDraftPageFixture,
} from "../testing/benchmarkAuthoring.fixtures";

describe("Benchmark authoring schema", () => {
  it("parses template, extension, resource, and pagination facts losslessly", () => {
    const page = parseBenchmarkDraftPage(benchmarkDraftPageFixture());
    const detail = parseBenchmarkDraftDetail(benchmarkDraftDetailFixture());
    expect(page.nextCursor).toBe("opaque-next");
    expect(detail.currentRevision.provenance.templateName).toBe("minimal");
    expect(
      detail.currentRevision.document.manifest.document.x_extension,
    ).toEqual({ nested: ["must", "survive"] });
    expect(detail.currentRevision.document.resources).toHaveLength(2);
  });

  it("parses Catalog provenance without exposing source paths", () => {
    const detail = benchmarkDraftDetailFixture();
    detail.currentRevision.provenance = {
      sourceKind: "catalog",
      templateName: null,
      catalogEntryId: `benchmark-entry-${"a".repeat(32)}`,
      catalogSnapshotIdentity: `sha256:${"b".repeat(64)}`,
      packageIdentity: "fixture/package@1.0.0",
      sourceFingerprint: `sha256:${"c".repeat(64)}`,
      sourceDisplayName: null,
      previewFingerprint: null,
      candidateDocumentFingerprint: null,
      migrationContractIdentity: null,
      taskEntryCount: null,
      uniqueTaskCount: null,
    };
    expect(
      parseBenchmarkDraftDetail(detail).currentRevision.provenance.sourceKind,
    ).toBe("catalog");
  });

  it("fails closed on malformed envelopes, identifiers, and inventory", () => {
    expect(() =>
      parseBenchmarkDraftPage({ schemaVersion: 2, items: [] }),
    ).toThrow(/schemaVersion 1/);
    const detail = benchmarkDraftDetailFixture();
    detail.draft.draftId = "not-a-draft";
    expect(() => parseBenchmarkDraftDetail(detail)).toThrow(/malformed/);
    const document = benchmarkAuthoringDocumentFixture();
    document.taskFiles.push({
      path: "tasks/a.json",
      tasks: [],
    });
    expect(() => parseBenchmarkAuthoringDocument(document)).toThrow(
      /deterministic path order/,
    );
  });

  it("rejects non-JSON and unknown closed response fields", () => {
    const detail = {
      ...benchmarkDraftDetailFixture(),
      unexpected: true,
    };
    expect(() => parseBenchmarkDraftDetail(detail)).toThrow(/unexpected/);
    const document = benchmarkAuthoringDocumentFixture() as unknown as Record<
      string,
      unknown
    >;
    const manifest = document.manifest as {
      path: string;
      document: Record<string, unknown>;
    };
    manifest.document.invalid = Number.NaN;
    expect(() => parseBenchmarkAuthoringDocument(document)).toThrow(/finite/);
  });

  it("parses content operations and a historical exact retry without regression assumptions", () => {
    expect(
      parseBenchmarkAuthoringContentCommandResult(
        benchmarkAuthoringContentCommandFixture("upload"),
      ).resource?.id,
    ).toBe("fixture-asset");
    expect(
      parseBenchmarkAuthoringContentCommandResult(
        benchmarkAuthoringContentCommandFixture("remove"),
      ).removedResourceId,
    ).toBe("fixture-asset");
    const historical = parseBenchmarkAuthoringContentCommandResult(
      benchmarkAuthoringContentCommandFixture("replace", true),
    );
    expect(historical.created).toBe(false);
    expect(historical.draft.currentRevisionId).not.toBe(
      historical.revision.revisionId,
    );
  });

  it("rejects contradictory content operation and projection fields", () => {
    const missingResource = benchmarkAuthoringContentCommandFixture("upload") as
      unknown as Record<string, unknown>;
    delete missingResource.resource;
    expect(() =>
      parseBenchmarkAuthoringContentCommandResult(missingResource),
    ).toThrow(/write fields/);

    const wrongOwner = benchmarkAuthoringContentCommandFixture("upload");
    wrongOwner.revision.draftId = `benchmark-draft-${"9".repeat(32)}`;
    expect(() =>
      parseBenchmarkAuthoringContentCommandResult(wrongOwner),
    ).toThrow(/ownership/);

    const conflicting = benchmarkAuthoringContentCommandFixture("replace");
    conflicting.resource!.size += 1;
    expect(() =>
      parseBenchmarkAuthoringContentCommandResult(conflicting),
    ).toThrow(/projection/);
  });
});
