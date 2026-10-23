import type {
  BenchmarkAuthoringContentCommandResult,
  BenchmarkAuthoringDocument,
  BenchmarkAuthoringRevision,
  BenchmarkDraftCommandResponse,
  BenchmarkDraftDetail,
  BenchmarkDraftPage,
} from "../model/benchmarkAuthoring.schema";

export const benchmarkDraftFixtureId = `benchmark-draft-${"a".repeat(32)}`;
export const benchmarkRevisionFixtureId =
  `benchmark-authoring-revision-${"b".repeat(32)}`;
export const benchmarkNextRevisionFixtureId =
  `benchmark-authoring-revision-${"c".repeat(32)}`;
export const benchmarkLaterRevisionFixtureId =
  `benchmark-authoring-revision-${"d".repeat(32)}`;
export const benchmarkCatalogFixtureId = `benchmark-entry-${"d".repeat(32)}`;
export const benchmarkDigestFixture = `sha256:${"e".repeat(64)}`;
export const benchmarkContentFixture =
  `benchmark-content-${"f".repeat(64)}`;

/** Build an extension-heavy parsed document with metadata-only resources. */
export function benchmarkAuthoringDocumentFixture(): BenchmarkAuthoringDocument {
  return {
    schemaVersion: 1,
    status: "unvalidated",
    manifest: {
      path: "benchmark.yaml",
      document: {
        schema_version: "1.0",
        identity: {
          publisher: "fixture",
          name: "authoring",
          version: "0.1.0",
          extension_identity: "preserved",
        },
        title: "Authoring Fixture",
        platforms: ["android"],
        splits: {
          test: {
            files: ["tasks/test.json"],
            extension_split: { keep: true },
          },
        },
        applications: [{ id: "fixture-app", package: "dev.fixture" }],
        plugins: [{ id: "fixture-plugin" }],
        default_protocol: "protocols/default.yaml",
        ground_truth: {
          inline: { kind: "json", value: { expected: true } },
          file: {
            kind: "file",
            resource_id: "fixture-ground-truth",
          },
        },
        x_extension: { nested: ["must", "survive"] },
      },
    },
    taskFiles: [
      {
        path: "tasks/test.json",
        tasks: [
          {
            id: "fixture-task",
            instruction: "Open the fixture app",
            extension_task: { keep: true },
          },
        ],
      },
    ],
    protocolFiles: [
      {
        path: "protocols/default.yaml",
        document: {
          schema_version: "1.0",
          seed: 17,
          repeats: 1,
          x_protocol: "preserved",
        },
      },
    ],
    resources: [
      {
        id: "fixture-asset",
        kind: "asset",
        path: "assets/screen.png",
        mediaType: "image/png",
        sha256: benchmarkDigestFixture,
        size: 128,
        contentIdentity: benchmarkContentFixture,
      },
      {
        id: "fixture-ground-truth",
        kind: "ground_truth",
        path: "ground_truth/expected.json",
        mediaType: "application/json",
        sha256: `sha256:${"f".repeat(64)}`,
        size: 64,
        contentIdentity: `benchmark-content-${"0".repeat(64)}`,
      },
    ],
    directories: ["assets", "ground_truth"],
  };
}

/** Build one immutable revision from a template or Catalog provenance. */
export function benchmarkAuthoringRevisionFixture(
  sourceKind: "template" | "catalog" | "edit" = "template",
): BenchmarkAuthoringRevision {
  return {
    schemaVersion: 1,
    revisionId: benchmarkRevisionFixtureId,
    draftId: benchmarkDraftFixtureId,
    ordinal: 1,
    parentRevisionId: null,
    document: benchmarkAuthoringDocumentFixture(),
    documentFingerprint: benchmarkDigestFixture,
    provenance:
      sourceKind === "template"
        ? {
            sourceKind,
            templateName: "minimal",
            catalogEntryId: null,
            catalogSnapshotIdentity: null,
            packageIdentity: "fixture/authoring@0.1.0",
            sourceFingerprint: null,
            sourceDisplayName: null,
            previewFingerprint: null,
            candidateDocumentFingerprint: null,
            migrationContractIdentity: null,
            taskEntryCount: null,
            uniqueTaskCount: null,
          }
        : sourceKind === "catalog"
          ? {
              sourceKind,
              templateName: null,
              catalogEntryId: benchmarkCatalogFixtureId,
              catalogSnapshotIdentity: benchmarkDigestFixture,
              packageIdentity: "fixture/authoring@0.1.0",
              sourceFingerprint: `sha256:${"1".repeat(64)}`,
              sourceDisplayName: null,
              previewFingerprint: null,
              candidateDocumentFingerprint: null,
              migrationContractIdentity: null,
              taskEntryCount: null,
              uniqueTaskCount: null,
            }
          : {
              sourceKind,
              templateName: null,
              catalogEntryId: null,
              catalogSnapshotIdentity: null,
              packageIdentity: null,
              sourceFingerprint: null,
              sourceDisplayName: null,
              previewFingerprint: null,
              candidateDocumentFingerprint: null,
              migrationContractIdentity: null,
              taskEntryCount: null,
              uniqueTaskCount: null,
            },
    status: "unvalidated",
    createdAt: 1_700_000_000_000,
  };
}

/** Build one authoritative draft detail fixture. */
export function benchmarkDraftDetailFixture(): BenchmarkDraftDetail {
  const revision = benchmarkAuthoringRevisionFixture();
  return {
    schemaVersion: 1,
    draft: {
      draftId: benchmarkDraftFixtureId,
      name: "Authoring Fixture",
      currentRevisionId: revision.revisionId,
      createdAt: revision.createdAt,
      updatedAt: revision.createdAt,
    },
    currentRevision: revision,
  };
}

/** Build one bounded draft page with an optional pagination cursor. */
export function benchmarkDraftPageFixture(
  nextCursor: string | null = "opaque-next",
): BenchmarkDraftPage {
  return {
    schemaVersion: 1,
    items: [benchmarkDraftDetailFixture().draft],
    nextCursor,
  };
}

/** Build a committed create/save response for retry and conflict journeys. */
export function benchmarkDraftCommandFixture(): BenchmarkDraftCommandResponse {
  const detail = benchmarkDraftDetailFixture();
  return {
    schemaVersion: 1,
    created: true,
    draft: detail.draft,
    revision: detail.currentRevision,
  };
}

/** Build one content result, including the permitted historical retry shape. */
export function benchmarkAuthoringContentCommandFixture(
  operation: "upload" | "replace" | "remove" = "upload",
  historicalRetry = false,
): BenchmarkAuthoringContentCommandResult {
  const initial = benchmarkAuthoringRevisionFixture("edit");
  const document = JSON.parse(
    JSON.stringify(initial.document),
  ) as BenchmarkAuthoringDocument;
  const target = document.resources[0]!;
  if (operation === "remove") {
    document.resources = document.resources.filter(
      (resource) => resource.id !== target.id,
    );
  }
  const revision: BenchmarkAuthoringRevision = {
    ...initial,
    revisionId: benchmarkNextRevisionFixtureId,
    ordinal: 2,
    parentRevisionId: benchmarkRevisionFixtureId,
    document,
    createdAt: initial.createdAt + 1,
  };
  return {
    schemaVersion: 1,
    operation,
    created: !historicalRetry,
    draft: {
      ...benchmarkDraftDetailFixture().draft,
      currentRevisionId: historicalRetry
        ? benchmarkLaterRevisionFixtureId
        : revision.revisionId,
      updatedAt: revision.createdAt + (historicalRetry ? 1 : 0),
    },
    revision,
    resource: operation === "remove" ? null : { ...target },
    removedResourceId: operation === "remove" ? target.id : null,
  };
}
