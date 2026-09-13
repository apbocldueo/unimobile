import {
  cloneJson,
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
  type JsonValue,
} from "@/shared/lib";

export type BenchmarkReleaseCommand = {
  schemaVersion: 1;
  clientRequestId: string;
};

export type BenchmarkFrozenMember = {
  ordinal: number;
  kind: "manifest" | "task" | "protocol" | "asset" | "ground_truth";
  path: string;
  mediaType: string;
  size: number;
  sha256: string;
  contentIdentity: string;
};

export type BenchmarkPackageRevision = {
  schemaVersion: 1;
  packageRevisionId: string;
  draftId: string;
  authoringRevisionId: string;
  validationAttestationId: string;
  packageIdentity: string;
  packageContentIdentity: string;
  closureIdentity: string;
  members: BenchmarkFrozenMember[];
  createdAt: number;
};

export type BenchmarkPackageRevisionDetail = {
  schemaVersion: 1;
  packageRevision: BenchmarkPackageRevision;
  validationAttestation: {
    attestationId: string;
    draftId: string;
    authoringRevisionId: string;
    packageIdentity: string;
    packageContentIdentity: string;
    safety: {
      completeDeclaredSplits: true;
      definitionOnly: true;
      publicationEvidence: false;
      executionEvidence: false;
      realDeviceEvidence: false;
      modelEvidence: false;
      packagePluginEvidence: false;
      contractTestRequired: false;
    };
    raw: Record<string, JsonValue>;
  };
};

export type BenchmarkFreezeResult = {
  schemaVersion: 1;
  created: boolean;
  detail: BenchmarkPackageRevisionDetail;
};

export type BenchmarkPackagePublication = {
  schemaVersion: 1;
  publicationId: string;
  draftId: string;
  packageRevisionId: string;
  validationAttestationId: string;
  packageIdentity: string;
  packageContentIdentity: string;
  closureIdentity: string;
  catalogEntryId: string;
  sourceId: "studio-managed-benchmark-publications";
  sourceKind: "catalog";
  createdAt: number;
  safety: {
    frozenClosureVerified: true;
    publicationEvidence: true;
    contractTestEvidence: false;
    executionEvidence: false;
    realDeviceEvidence: false;
    modelEvidence: false;
    packagePluginEvidence: false;
  };
};

export type BenchmarkPackageExport = {
  schemaVersion: 1;
  exportId: string;
  draftId: string;
  packageRevisionId: string;
  validationAttestationId: string;
  packageIdentity: string;
  packageContentIdentity: string;
  closureIdentity: string;
  exportContractVersion: "studio-benchmark-package-zip-v1";
  memberCount: number;
  archiveMediaType: "application/zip";
  filename: string;
  size: number;
  sha256: string;
  contentLink: string;
  availability: "available";
  createdAt: number;
  safety: {
    frozenClosureVerified: true;
    archiveIntegrityVerified: true;
    publicationEvidence: false;
    contractTestEvidence: false;
    executionEvidence: false;
    realDeviceEvidence: false;
    modelEvidence: false;
    packagePluginEvidence: false;
  };
};

export type BenchmarkPackageRevisionSummary = {
  packageRevisionId: string;
  authoringRevisionId: string;
  validationAttestationId: string;
  packageIdentity: string;
  packageContentIdentity: string;
  closureIdentity: string;
  memberCount: number;
  createdAt: number;
  detailLink: string;
  publication: BenchmarkPackagePublication | null;
  packageExport: BenchmarkPackageExport | null;
};

export type BenchmarkPackageRevisionPage = {
  schemaVersion: 1;
  items: BenchmarkPackageRevisionSummary[];
  nextCursor: string | null;
};

export type BenchmarkPublicationResult = {
  schemaVersion: 1;
  created: boolean;
  publication: BenchmarkPackagePublication;
};

export type BenchmarkExportResult = {
  schemaVersion: 1;
  created: boolean;
  packageExport: BenchmarkPackageExport;
};

const DRAFT_ID = /^benchmark-draft-[a-f0-9]{32}$/;
const REVISION_ID = /^benchmark-authoring-revision-[a-f0-9]{32}$/;
const PACKAGE_REVISION_ID = /^benchmark-package-revision-[a-f0-9]{32}$/;
const ATTESTATION_ID = /^benchmark-validation-attestation-[a-f0-9]{32}$/;
const PUBLICATION_ID = /^benchmark-package-publication-[a-f0-9]{32}$/;
const EXPORT_ID = /^benchmark-package-export-[a-f0-9]{32}$/;
const ENTRY_ID = /^benchmark-entry-[a-f0-9]{32}$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;
const CONTENT_ID = /^benchmark-content-[a-f0-9]{64}$/;
const CLIENT_REQUEST_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/;
const PACKAGE_PATH = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))(?!.*\\)(?!.*\/\/)[^\0]+$/;
const FILENAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.zip$/;
const DETAIL_LINK = new RegExp(
  `^/api/studio/benchmark-authoring/drafts/(${DRAFT_ID.source.slice(1, -1)})`
  + `/package-revisions/(${PACKAGE_REVISION_ID.source.slice(1, -1)})$`,
);

/** Require one exact schema-version-one object. */
function schemaOne(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value) || value.schemaVersion !== 1) {
    throw new Error(`${path} must be a schemaVersion 1 object`);
  }
  return value;
}

/** Require one opaque identity matching a release contract. */
function identity(value: unknown, pattern: RegExp, path: string): string {
  const parsed = requireString(value, path);
  if (!pattern.test(parsed)) throw new Error(`${path} is malformed`);
  return parsed;
}

/** Require one finite bounded non-negative safe integer. */
function boundedInteger(
  value: unknown,
  path: string,
  maximum: number,
): number {
  const parsed = requireNumber(value, path);
  if (!Number.isSafeInteger(parsed) || parsed < 0 || parsed > maximum) {
    throw new Error(`${path} is outside its safe integer bound`);
  }
  return parsed;
}

/** Require one exact fixed boolean evidence fact. */
function fixedBoolean(value: unknown, expected: boolean, path: string) {
  if (value !== expected) throw new Error(`${path} must be ${String(expected)}`);
  return expected;
}

/** Parse the minimal idempotent release command before transport. */
export function parseBenchmarkReleaseCommand(
  value: unknown,
): BenchmarkReleaseCommand {
  const object = schemaOne(value, "releaseCommand");
  rejectUnknownKeys(object, ["schemaVersion", "clientRequestId"], "releaseCommand");
  return {
    schemaVersion: 1,
    clientRequestId: identity(
      object.clientRequestId,
      CLIENT_REQUEST_ID,
      "releaseCommand.clientRequestId",
    ),
  };
}

/** Parse one exact immutable frozen Package member descriptor. */
function parseFrozenMember(value: unknown, path: string): BenchmarkFrozenMember {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["ordinal", "kind", "path", "mediaType", "size", "sha256", "contentIdentity"],
    path,
  );
  if (![
    "manifest",
    "task",
    "protocol",
    "asset",
    "ground_truth",
  ].includes(String(value.kind))) {
    throw new Error(`${path}.kind is unsupported`);
  }
  const memberPath = requireString(value.path, `${path}.path`);
  if (!PACKAGE_PATH.test(memberPath)) throw new Error(`${path}.path is unsafe`);
  return {
    ordinal: boundedInteger(value.ordinal, `${path}.ordinal`, 255),
    kind: value.kind as BenchmarkFrozenMember["kind"],
    path: memberPath,
    mediaType: requireString(value.mediaType, `${path}.mediaType`),
    size: boundedInteger(value.size, `${path}.size`, 64 * 1024 * 1024),
    sha256: identity(value.sha256, DIGEST, `${path}.sha256`),
    contentIdentity: identity(value.contentIdentity, CONTENT_ID, `${path}.contentIdentity`),
  };
}

/** Parse one exact immutable Package revision and complete member inventory. */
export function parseBenchmarkPackageRevision(
  value: unknown,
  path = "packageRevision",
): BenchmarkPackageRevision {
  const object = schemaOne(value, path);
  rejectUnknownKeys(
    object,
    [
      "schemaVersion",
      "packageRevisionId",
      "draftId",
      "authoringRevisionId",
      "validationAttestationId",
      "packageIdentity",
      "packageContentIdentity",
      "closureIdentity",
      "members",
      "createdAt",
    ],
    path,
  );
  if (!Array.isArray(object.members) || object.members.length === 0 || object.members.length > 256) {
    throw new Error(`${path}.members is outside its bound`);
  }
  const members = object.members.map((item, index) =>
    parseFrozenMember(item, `${path}.members[${index}]`),
  );
  if (
    members.some((item, index) => item.ordinal !== index)
    || members.some((item, index) => index > 0 && members[index - 1]!.path >= item.path)
  ) {
    throw new Error(`${path}.members is not a complete deterministic closure`);
  }
  return {
    schemaVersion: 1,
    packageRevisionId: identity(object.packageRevisionId, PACKAGE_REVISION_ID, `${path}.packageRevisionId`),
    draftId: identity(object.draftId, DRAFT_ID, `${path}.draftId`),
    authoringRevisionId: identity(object.authoringRevisionId, REVISION_ID, `${path}.authoringRevisionId`),
    validationAttestationId: identity(object.validationAttestationId, ATTESTATION_ID, `${path}.validationAttestationId`),
    packageIdentity: requireString(object.packageIdentity, `${path}.packageIdentity`),
    packageContentIdentity: identity(object.packageContentIdentity, DIGEST, `${path}.packageContentIdentity`),
    closureIdentity: identity(object.closureIdentity, DIGEST, `${path}.closureIdentity`),
    members,
    createdAt: boundedInteger(object.createdAt, `${path}.createdAt`, Number.MAX_SAFE_INTEGER),
  };
}

/** Parse the exact Package revision and linked successful validation authority. */
export function parseBenchmarkPackageRevisionDetail(
  value: unknown,
): BenchmarkPackageRevisionDetail {
  const object = schemaOne(value, "packageRevisionDetail");
  rejectUnknownKeys(
    object,
    ["schemaVersion", "packageRevision", "validationAttestation"],
    "packageRevisionDetail",
  );
  const packageRevision = parseBenchmarkPackageRevision(object.packageRevision);
  const raw = schemaOne(object.validationAttestation, "validationAttestation");
  rejectUnknownKeys(
    raw,
    [
      "schemaVersion",
      "attestationId",
      "draftId",
      "authoringRevisionId",
      "documentFingerprint",
      "validationContractVersion",
      "packageIdentity",
      "packageContentIdentity",
      "splits",
      "diagnostics",
      "warnings",
      "unverifiedChecks",
      "safety",
      "createdAt",
    ],
    "validationAttestation",
  );
  if (!isRecord(raw.safety)) throw new Error("validationAttestation.safety must be an object");
  rejectUnknownKeys(
    raw.safety,
    [
      "completeDeclaredSplits",
      "definitionOnly",
      "executionEvidence",
      "realDeviceEvidence",
      "modelEvidence",
      "packagePluginEvidence",
      "publicationEvidence",
      "contractTestRequired",
    ],
    "validationAttestation.safety",
  );
  if (
    raw.validationContractVersion !== "studio-benchmark-freeze-validation-v1"
    || !Array.isArray(raw.splits)
    || raw.splits.length === 0
    || raw.splits.length > 64
    || !Array.isArray(raw.diagnostics)
    || raw.diagnostics.length > 200
    || !Array.isArray(raw.warnings)
    || raw.warnings.length > 100
    || !Array.isArray(raw.unverifiedChecks)
    || raw.unverifiedChecks.length > 100
  ) {
    throw new Error("validationAttestation bounded validation facts are invalid");
  }
  identity(raw.documentFingerprint, DIGEST, "validationAttestation.documentFingerprint");
  boundedInteger(raw.createdAt, "validationAttestation.createdAt", Number.MAX_SAFE_INTEGER);
  const attestation = {
    attestationId: identity(raw.attestationId, ATTESTATION_ID, "validationAttestation.attestationId"),
    draftId: identity(raw.draftId, DRAFT_ID, "validationAttestation.draftId"),
    authoringRevisionId: identity(raw.authoringRevisionId, REVISION_ID, "validationAttestation.authoringRevisionId"),
    packageIdentity: requireString(raw.packageIdentity, "validationAttestation.packageIdentity"),
    packageContentIdentity: identity(raw.packageContentIdentity, DIGEST, "validationAttestation.packageContentIdentity"),
    safety: {
      completeDeclaredSplits: fixedBoolean(raw.safety.completeDeclaredSplits, true, "validationAttestation.safety.completeDeclaredSplits") as true,
      definitionOnly: fixedBoolean(raw.safety.definitionOnly, true, "validationAttestation.safety.definitionOnly") as true,
      publicationEvidence: fixedBoolean(raw.safety.publicationEvidence, false, "validationAttestation.safety.publicationEvidence") as false,
      executionEvidence: fixedBoolean(raw.safety.executionEvidence, false, "validationAttestation.safety.executionEvidence") as false,
      realDeviceEvidence: fixedBoolean(raw.safety.realDeviceEvidence, false, "validationAttestation.safety.realDeviceEvidence") as false,
      modelEvidence: fixedBoolean(raw.safety.modelEvidence, false, "validationAttestation.safety.modelEvidence") as false,
      packagePluginEvidence: fixedBoolean(raw.safety.packagePluginEvidence, false, "validationAttestation.safety.packagePluginEvidence") as false,
      contractTestRequired: fixedBoolean(raw.safety.contractTestRequired, false, "validationAttestation.safety.contractTestRequired") as false,
    },
    raw: cloneJson(raw, "validationAttestation") as Record<string, JsonValue>,
  };
  if (
    attestation.attestationId !== packageRevision.validationAttestationId
    || attestation.draftId !== packageRevision.draftId
    || attestation.authoringRevisionId !== packageRevision.authoringRevisionId
    || attestation.packageIdentity !== packageRevision.packageIdentity
    || attestation.packageContentIdentity !== packageRevision.packageContentIdentity
  ) {
    throw new Error("Package revision and attestation identities disagree");
  }
  return { schemaVersion: 1, packageRevision, validationAttestation: attestation };
}

/** Parse an exact freeze command response used to select a release candidate. */
export function parseBenchmarkFreezeResult(value: unknown): BenchmarkFreezeResult {
  const object = schemaOne(value, "freezeResult");
  rejectUnknownKeys(object, ["schemaVersion", "created", "detail"], "freezeResult");
  if (typeof object.created !== "boolean") throw new Error("freezeResult.created must be boolean");
  return {
    schemaVersion: 1,
    created: object.created,
    detail: parseBenchmarkPackageRevisionDetail(object.detail),
  };
}

/** Parse fixed publication evidence without admitting runtime claims. */
function parsePublicationSafety(value: unknown, path: string) {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["frozenClosureVerified", "publicationEvidence", "contractTestEvidence", "executionEvidence", "realDeviceEvidence", "modelEvidence", "packagePluginEvidence"], path);
  return {
    frozenClosureVerified: fixedBoolean(value.frozenClosureVerified, true, `${path}.frozenClosureVerified`) as true,
    publicationEvidence: fixedBoolean(value.publicationEvidence, true, `${path}.publicationEvidence`) as true,
    contractTestEvidence: fixedBoolean(value.contractTestEvidence, false, `${path}.contractTestEvidence`) as false,
    executionEvidence: fixedBoolean(value.executionEvidence, false, `${path}.executionEvidence`) as false,
    realDeviceEvidence: fixedBoolean(value.realDeviceEvidence, false, `${path}.realDeviceEvidence`) as false,
    modelEvidence: fixedBoolean(value.modelEvidence, false, `${path}.modelEvidence`) as false,
    packagePluginEvidence: fixedBoolean(value.packagePluginEvidence, false, `${path}.packagePluginEvidence`) as false,
  };
}

/** Parse one immutable managed Catalog publication. */
export function parseBenchmarkPackagePublication(
  value: unknown,
  path = "publication",
): BenchmarkPackagePublication {
  const object = schemaOne(value, path);
  rejectUnknownKeys(object, ["schemaVersion", "publicationId", "draftId", "packageRevisionId", "validationAttestationId", "packageIdentity", "packageContentIdentity", "closureIdentity", "catalogEntryId", "sourceId", "sourceKind", "createdAt", "safety"], path);
  if (object.sourceId !== "studio-managed-benchmark-publications" || object.sourceKind !== "catalog") {
    throw new Error(`${path} managed provenance is invalid`);
  }
  return {
    schemaVersion: 1,
    publicationId: identity(object.publicationId, PUBLICATION_ID, `${path}.publicationId`),
    draftId: identity(object.draftId, DRAFT_ID, `${path}.draftId`),
    packageRevisionId: identity(object.packageRevisionId, PACKAGE_REVISION_ID, `${path}.packageRevisionId`),
    validationAttestationId: identity(object.validationAttestationId, ATTESTATION_ID, `${path}.validationAttestationId`),
    packageIdentity: requireString(object.packageIdentity, `${path}.packageIdentity`),
    packageContentIdentity: identity(object.packageContentIdentity, DIGEST, `${path}.packageContentIdentity`),
    closureIdentity: identity(object.closureIdentity, DIGEST, `${path}.closureIdentity`),
    catalogEntryId: identity(object.catalogEntryId, ENTRY_ID, `${path}.catalogEntryId`),
    sourceId: "studio-managed-benchmark-publications",
    sourceKind: "catalog",
    createdAt: boundedInteger(object.createdAt, `${path}.createdAt`, Number.MAX_SAFE_INTEGER),
    safety: parsePublicationSafety(object.safety, `${path}.safety`),
  };
}

/** Parse fixed export integrity evidence without publication/runtime claims. */
function parseExportSafety(value: unknown, path: string) {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["frozenClosureVerified", "archiveIntegrityVerified", "publicationEvidence", "contractTestEvidence", "executionEvidence", "realDeviceEvidence", "modelEvidence", "packagePluginEvidence"], path);
  return {
    frozenClosureVerified: fixedBoolean(value.frozenClosureVerified, true, `${path}.frozenClosureVerified`) as true,
    archiveIntegrityVerified: fixedBoolean(value.archiveIntegrityVerified, true, `${path}.archiveIntegrityVerified`) as true,
    publicationEvidence: fixedBoolean(value.publicationEvidence, false, `${path}.publicationEvidence`) as false,
    contractTestEvidence: fixedBoolean(value.contractTestEvidence, false, `${path}.contractTestEvidence`) as false,
    executionEvidence: fixedBoolean(value.executionEvidence, false, `${path}.executionEvidence`) as false,
    realDeviceEvidence: fixedBoolean(value.realDeviceEvidence, false, `${path}.realDeviceEvidence`) as false,
    modelEvidence: fixedBoolean(value.modelEvidence, false, `${path}.modelEvidence`) as false,
    packagePluginEvidence: fixedBoolean(value.packagePluginEvidence, false, `${path}.packagePluginEvidence`) as false,
  };
}

/** Parse one immutable deterministic Package export descriptor. */
export function parseBenchmarkPackageExport(
  value: unknown,
  path = "packageExport",
): BenchmarkPackageExport {
  const object = schemaOne(value, path);
  rejectUnknownKeys(object, ["schemaVersion", "exportId", "draftId", "packageRevisionId", "validationAttestationId", "packageIdentity", "packageContentIdentity", "closureIdentity", "exportContractVersion", "memberCount", "archiveMediaType", "filename", "size", "sha256", "contentLink", "availability", "createdAt", "safety"], path);
  if (object.exportContractVersion !== "studio-benchmark-package-zip-v1" || object.archiveMediaType !== "application/zip" || object.availability !== "available") {
    throw new Error(`${path} export contract is unsupported`);
  }
  const filename = requireString(object.filename, `${path}.filename`);
  const contentLink = requireString(object.contentLink, `${path}.contentLink`);
  const exportId = identity(object.exportId, EXPORT_ID, `${path}.exportId`);
  const draftId = identity(object.draftId, DRAFT_ID, `${path}.draftId`);
  const packageRevisionId = identity(object.packageRevisionId, PACKAGE_REVISION_ID, `${path}.packageRevisionId`);
  const expectedContentLink =
    `/api/studio/benchmark-authoring/drafts/${draftId}`
    + `/package-revisions/${packageRevisionId}/exports/${exportId}/content`;
  if (!FILENAME.test(filename) || contentLink !== expectedContentLink) {
    throw new Error(`${path} download capability is unsafe`);
  }
  return {
    schemaVersion: 1,
    exportId,
    draftId,
    packageRevisionId,
    validationAttestationId: identity(object.validationAttestationId, ATTESTATION_ID, `${path}.validationAttestationId`),
    packageIdentity: requireString(object.packageIdentity, `${path}.packageIdentity`),
    packageContentIdentity: identity(object.packageContentIdentity, DIGEST, `${path}.packageContentIdentity`),
    closureIdentity: identity(object.closureIdentity, DIGEST, `${path}.closureIdentity`),
    exportContractVersion: "studio-benchmark-package-zip-v1",
    memberCount: boundedInteger(object.memberCount, `${path}.memberCount`, 256),
    archiveMediaType: "application/zip",
    filename,
    size: boundedInteger(object.size, `${path}.size`, 272 * 1024 * 1024),
    sha256: identity(object.sha256, DIGEST, `${path}.sha256`),
    contentLink,
    availability: "available",
    createdAt: boundedInteger(object.createdAt, `${path}.createdAt`, Number.MAX_SAFE_INTEGER),
    safety: parseExportSafety(object.safety, `${path}.safety`),
  };
}

/** Parse a stable bounded Package-revision release page. */
export function parseBenchmarkPackageRevisionPage(
  value: unknown,
): BenchmarkPackageRevisionPage {
  const object = schemaOne(value, "packageRevisionPage");
  rejectUnknownKeys(object, ["schemaVersion", "items", "nextCursor"], "packageRevisionPage");
  if (!Array.isArray(object.items) || object.items.length > 100) throw new Error("packageRevisionPage.items is outside its bound");
  const items = object.items.map((item, index) => {
    const path = `packageRevisionPage.items[${index}]`;
    if (!isRecord(item)) throw new Error(`${path} must be an object`);
    rejectUnknownKeys(item, ["packageRevisionId", "authoringRevisionId", "validationAttestationId", "packageIdentity", "packageContentIdentity", "closureIdentity", "memberCount", "createdAt", "detailLink", "publication", "packageExport"], path);
    const packageRevisionId = identity(item.packageRevisionId, PACKAGE_REVISION_ID, `${path}.packageRevisionId`);
    const detailLink = requireString(item.detailLink, `${path}.detailLink`);
    const linkMatch = DETAIL_LINK.exec(detailLink);
    if (!linkMatch || linkMatch[2] !== packageRevisionId) {
      throw new Error(`${path}.detailLink is not an exact scoped capability`);
    }
    const publication = item.publication === null || item.publication === undefined ? null : parseBenchmarkPackagePublication(item.publication, `${path}.publication`);
    const packageExport = item.packageExport === null || item.packageExport === undefined ? null : parseBenchmarkPackageExport(item.packageExport, `${path}.packageExport`);
    const packageIdentity = requireString(item.packageIdentity, `${path}.packageIdentity`);
    const packageContentIdentity = identity(item.packageContentIdentity, DIGEST, `${path}.packageContentIdentity`);
    const closureIdentity = identity(item.closureIdentity, DIGEST, `${path}.closureIdentity`);
    for (const resource of [publication, packageExport]) {
      if (
        resource !== null
        && (
          resource.draftId !== linkMatch[1]
          || resource.packageRevisionId !== packageRevisionId
          || resource.validationAttestationId !== item.validationAttestationId
          || resource.packageIdentity !== packageIdentity
          || resource.packageContentIdentity !== packageContentIdentity
          || resource.closureIdentity !== closureIdentity
        )
      ) {
        throw new Error(`${path} release resource changes Package ownership`);
      }
    }
    return {
      packageRevisionId,
      authoringRevisionId: identity(item.authoringRevisionId, REVISION_ID, `${path}.authoringRevisionId`),
      validationAttestationId: identity(item.validationAttestationId, ATTESTATION_ID, `${path}.validationAttestationId`),
      packageIdentity,
      packageContentIdentity,
      closureIdentity,
      memberCount: boundedInteger(item.memberCount, `${path}.memberCount`, 256),
      createdAt: boundedInteger(item.createdAt, `${path}.createdAt`, Number.MAX_SAFE_INTEGER),
      detailLink,
      publication,
      packageExport,
    };
  });
  const nextCursor = object.nextCursor === null || object.nextCursor === undefined ? null : requireString(object.nextCursor, "packageRevisionPage.nextCursor");
  if (nextCursor !== null && nextCursor.length > 2048) throw new Error("packageRevisionPage.nextCursor is outside its bound");
  return { schemaVersion: 1, items, nextCursor };
}

/** Parse a publication command response with creation disposition. */
export function parseBenchmarkPublicationResult(value: unknown): BenchmarkPublicationResult {
  const object = schemaOne(value, "publicationResult");
  rejectUnknownKeys(object, ["schemaVersion", "created", "publication"], "publicationResult");
  if (typeof object.created !== "boolean") throw new Error("publicationResult.created must be boolean");
  return { schemaVersion: 1, created: object.created, publication: parseBenchmarkPackagePublication(object.publication) };
}

/** Parse an export command response with creation disposition. */
export function parseBenchmarkExportResult(value: unknown): BenchmarkExportResult {
  const object = schemaOne(value, "exportResult");
  rejectUnknownKeys(object, ["schemaVersion", "created", "packageExport"], "exportResult");
  if (typeof object.created !== "boolean") throw new Error("exportResult.created must be boolean");
  return { schemaVersion: 1, created: object.created, packageExport: parseBenchmarkPackageExport(object.packageExport) };
}
