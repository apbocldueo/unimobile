import type {
  BenchmarkExportResult,
  BenchmarkPackageExport,
  BenchmarkPackagePublication,
  BenchmarkPackageRevisionPage,
  BenchmarkPublicationResult,
} from "../model/benchmarkAuthoringRelease.schema";
import {
  benchmarkDigestFixture,
  benchmarkDraftFixtureId,
  benchmarkRevisionFixtureId,
} from "./benchmarkAuthoring.fixtures";

export const benchmarkPackageRevisionFixtureId =
  `benchmark-package-revision-${"1".repeat(32)}`;
export const benchmarkAttestationFixtureId =
  `benchmark-validation-attestation-${"2".repeat(32)}`;
export const benchmarkPublicationFixtureId =
  `benchmark-package-publication-${"3".repeat(32)}`;
export const benchmarkExportFixtureId =
  `benchmark-package-export-${"4".repeat(32)}`;
export const benchmarkReleaseCatalogFixtureId =
  `benchmark-entry-${"5".repeat(32)}`;
export const benchmarkClosureFixture = `sha256:${"6".repeat(64)}`;
export const benchmarkArchiveFixture = `sha256:${"7".repeat(64)}`;

/** Build one immutable managed Catalog publication fixture. */
export function benchmarkPackagePublicationFixture(): BenchmarkPackagePublication {
  return {
    schemaVersion: 1,
    publicationId: benchmarkPublicationFixtureId,
    draftId: benchmarkDraftFixtureId,
    packageRevisionId: benchmarkPackageRevisionFixtureId,
    validationAttestationId: benchmarkAttestationFixtureId,
    packageIdentity: "fixture/authoring@0.1.0",
    packageContentIdentity: benchmarkDigestFixture,
    closureIdentity: benchmarkClosureFixture,
    catalogEntryId: benchmarkReleaseCatalogFixtureId,
    sourceId: "studio-managed-benchmark-publications",
    sourceKind: "catalog",
    createdAt: 1_700_000_000_100,
    safety: {
      frozenClosureVerified: true,
      publicationEvidence: true,
      contractTestEvidence: false,
      executionEvidence: false,
      realDeviceEvidence: false,
      modelEvidence: false,
      packagePluginEvidence: false,
    },
  };
}

/** Build one deterministic downloadable Package export fixture. */
export function benchmarkPackageExportFixture(): BenchmarkPackageExport {
  return {
    schemaVersion: 1,
    exportId: benchmarkExportFixtureId,
    draftId: benchmarkDraftFixtureId,
    packageRevisionId: benchmarkPackageRevisionFixtureId,
    validationAttestationId: benchmarkAttestationFixtureId,
    packageIdentity: "fixture/authoring@0.1.0",
    packageContentIdentity: benchmarkDigestFixture,
    closureIdentity: benchmarkClosureFixture,
    exportContractVersion: "studio-benchmark-package-zip-v1",
    memberCount: 1,
    archiveMediaType: "application/zip",
    filename: `benchmark-package-${"1".repeat(32)}.zip`,
    size: 128,
    sha256: benchmarkArchiveFixture,
    contentLink:
      `/api/studio/benchmark-authoring/drafts/${benchmarkDraftFixtureId}`
      + `/package-revisions/${benchmarkPackageRevisionFixtureId}`
      + `/exports/${benchmarkExportFixtureId}/content`,
    availability: "available",
    createdAt: 1_700_000_000_200,
    safety: {
      frozenClosureVerified: true,
      archiveIntegrityVerified: true,
      publicationEvidence: false,
      contractTestEvidence: false,
      executionEvidence: false,
      realDeviceEvidence: false,
      modelEvidence: false,
      packagePluginEvidence: false,
    },
  };
}

/** Build one bounded release page with optional final release facts. */
export function benchmarkPackageRevisionPageFixture(options: {
  published?: boolean;
  exported?: boolean;
} = {}): BenchmarkPackageRevisionPage {
  return {
    schemaVersion: 1,
    items: [{
      packageRevisionId: benchmarkPackageRevisionFixtureId,
      authoringRevisionId: benchmarkRevisionFixtureId,
      validationAttestationId: benchmarkAttestationFixtureId,
      packageIdentity: "fixture/authoring@0.1.0",
      packageContentIdentity: benchmarkDigestFixture,
      closureIdentity: benchmarkClosureFixture,
      memberCount: 1,
      createdAt: 1_700_000_000_000,
      detailLink:
        `/api/studio/benchmark-authoring/drafts/${benchmarkDraftFixtureId}`
        + `/package-revisions/${benchmarkPackageRevisionFixtureId}`,
      publication: options.published ? benchmarkPackagePublicationFixture() : null,
      packageExport: options.exported ? benchmarkPackageExportFixture() : null,
    }],
    nextCursor: null,
  };
}

/** Build one successful publication command response fixture. */
export function benchmarkPublicationResultFixture(): BenchmarkPublicationResult {
  return {
    schemaVersion: 1,
    created: true,
    publication: benchmarkPackagePublicationFixture(),
  };
}

/** Build one successful export command response fixture. */
export function benchmarkExportResultFixture(): BenchmarkExportResult {
  return {
    schemaVersion: 1,
    created: true,
    packageExport: benchmarkPackageExportFixture(),
  };
}

/** Build one strict E-1 Freeze response as untrusted server JSON. */
export function benchmarkFreezeResultFixture(): object {
  return {
    schemaVersion: 1,
    created: true,
    detail: {
      schemaVersion: 1,
      packageRevision: {
        schemaVersion: 1,
        packageRevisionId: benchmarkPackageRevisionFixtureId,
        draftId: benchmarkDraftFixtureId,
        authoringRevisionId: benchmarkRevisionFixtureId,
        validationAttestationId: benchmarkAttestationFixtureId,
        packageIdentity: "fixture/authoring@0.1.0",
        packageContentIdentity: benchmarkDigestFixture,
        closureIdentity: benchmarkClosureFixture,
        members: [{
          ordinal: 0,
          kind: "manifest",
          path: "benchmark.yaml",
          mediaType: "application/yaml",
          size: 128,
          sha256: benchmarkDigestFixture,
          contentIdentity: `benchmark-content-${"8".repeat(64)}`,
        }],
        createdAt: 1_700_000_000_000,
      },
      validationAttestation: {
        schemaVersion: 1,
        attestationId: benchmarkAttestationFixtureId,
        draftId: benchmarkDraftFixtureId,
        authoringRevisionId: benchmarkRevisionFixtureId,
        documentFingerprint: benchmarkDigestFixture,
        validationContractVersion: "studio-benchmark-freeze-validation-v1",
        packageIdentity: "fixture/authoring@0.1.0",
        packageContentIdentity: benchmarkDigestFixture,
        splits: [{}],
        diagnostics: [],
        warnings: [],
        unverifiedChecks: ["runtime-not-executed"],
        safety: {
          completeDeclaredSplits: true,
          definitionOnly: true,
          executionEvidence: false,
          realDeviceEvidence: false,
          modelEvidence: false,
          packagePluginEvidence: false,
          publicationEvidence: false,
          contractTestRequired: false,
        },
        createdAt: 1_700_000_000_000,
      },
    },
  };
}
