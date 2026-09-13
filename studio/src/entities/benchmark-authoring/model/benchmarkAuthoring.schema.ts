import {
  cloneJson,
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
  type JsonValue,
} from "@/shared/lib";

export type BenchmarkAuthoringTemplate =
  | "minimal"
  | "dynamic-task"
  | "composite-evaluation";

export type BenchmarkAuthoringResource = {
  id: string;
  kind: "asset" | "ground_truth";
  path: string;
  mediaType: string;
  sha256: string;
  size: number;
  contentIdentity: string;
};

export type BenchmarkAuthoringDocument = {
  schemaVersion: 1;
  status: "unvalidated";
  manifest: {
    path: "benchmark.yaml";
    document: Record<string, JsonValue>;
  };
  taskFiles: Array<{
    path: string;
    tasks: JsonValue[];
  }>;
  protocolFiles: Array<{
    path: string;
    document: Record<string, JsonValue>;
  }>;
  resources: BenchmarkAuthoringResource[];
  directories: ["assets", "ground_truth"];
};

export type BenchmarkAuthoringProvenance = {
  sourceKind: "template" | "catalog" | "edit" | "legacy_migration";
  templateName: BenchmarkAuthoringTemplate | null;
  catalogEntryId: string | null;
  catalogSnapshotIdentity: string | null;
  packageIdentity: string | null;
  sourceFingerprint: string | null;
  sourceDisplayName: string | null;
  previewFingerprint: string | null;
  candidateDocumentFingerprint: string | null;
  migrationContractIdentity: string | null;
  taskEntryCount: number | null;
  uniqueTaskCount: number | null;
};

export type BenchmarkDraftRecord = {
  draftId: string;
  name: string;
  currentRevisionId: string;
  createdAt: number;
  updatedAt: number;
};

export type BenchmarkAuthoringRevision = {
  schemaVersion: 1;
  revisionId: string;
  draftId: string;
  ordinal: number;
  parentRevisionId: string | null;
  document: BenchmarkAuthoringDocument;
  documentFingerprint: string;
  provenance: BenchmarkAuthoringProvenance;
  status: "unvalidated";
  createdAt: number;
};

export type BenchmarkDraftPage = {
  schemaVersion: 1;
  items: BenchmarkDraftRecord[];
  nextCursor: string | null;
};

export type BenchmarkDraftDetail = {
  schemaVersion: 1;
  draft: BenchmarkDraftRecord;
  currentRevision: BenchmarkAuthoringRevision;
};

export type BenchmarkDraftCreateSource =
  | {
      kind: "template";
      template: BenchmarkAuthoringTemplate;
      publisher: string;
      packageName: string;
      version: string;
    }
  | {
      kind: "catalog";
      catalogEntryId: string;
    };

export type CreateBenchmarkDraftInput = {
  schemaVersion: 1;
  clientRequestId: string;
  name: string;
  source: BenchmarkDraftCreateSource;
};

export type SaveBenchmarkRevisionInput = {
  schemaVersion: 1;
  clientRequestId: string;
  baseRevisionId: string;
  document: BenchmarkAuthoringDocument;
};

export type BenchmarkDraftCommandResponse = {
  schemaVersion: 1;
  created: boolean;
  draft: BenchmarkDraftRecord;
  revision: BenchmarkAuthoringRevision;
};

export type BenchmarkAuthoringContentOperation =
  | "upload"
  | "replace"
  | "remove";

export type BenchmarkAuthoringContentCommandResult = {
  schemaVersion: 1;
  operation: BenchmarkAuthoringContentOperation;
  created: boolean;
  draft: BenchmarkDraftRecord;
  revision: BenchmarkAuthoringRevision;
  resource: BenchmarkAuthoringResource | null;
  removedResourceId: string | null;
};

const DRAFT_ID = /^benchmark-draft-[a-f0-9]{32}$/;
const REVISION_ID = /^benchmark-authoring-revision-[a-f0-9]{32}$/;
const ENTRY_ID = /^benchmark-entry-[a-f0-9]{32}$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;
const CONTENT_ID = /^benchmark-content-[a-f0-9]{64}$/;
const STABLE_ID = /^[a-z][a-z0-9_.-]{0,127}$/;
const PACKAGE_PATH = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))(?!.*\\)(?!.*\/\/)[^\0]+$/;

/** Require a strict schema-version-one object. */
function responseObject(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value) || value.schemaVersion !== 1) {
    throw new Error(`${path} must be a schemaVersion 1 object`);
  }
  return value;
}

/** Parse a nullable string while rejecting other primitive values. */
function nullableString(value: unknown, path: string): string | null {
  if (value === null || value === undefined) return null;
  return requireString(value, path);
}

/** Require one finite non-negative safe integer. */
function nonNegativeInteger(value: unknown, path: string): number {
  const parsed = requireNumber(value, path);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error(`${path} must be a non-negative safe integer`);
  }
  return parsed;
}

/** Require one opaque identifier to match its declared contract. */
function identifier(
  value: unknown,
  pattern: RegExp,
  path: string,
): string {
  const parsed = requireString(value, path);
  if (!pattern.test(parsed)) throw new Error(`${path} is malformed`);
  return parsed;
}

/** Require one normalized Package-relative member path with an expected prefix. */
function memberPath(
  value: unknown,
  prefix: string,
  suffixes: readonly string[],
  path: string,
): string {
  const parsed = requireString(value, path);
  if (
    !PACKAGE_PATH.test(parsed)
    || !parsed.startsWith(prefix)
    || !suffixes.some((suffix) => parsed.endsWith(suffix))
  ) {
    throw new Error(`${path} is not a supported Package member path`);
  }
  return parsed;
}

/** Clone one arbitrary safe JSON mapping without closing extension fields. */
function jsonMapping(
  value: unknown,
  path: string,
): Record<string, JsonValue> {
  const cloned = cloneJson(value, path);
  if (cloned === null || Array.isArray(cloned) || typeof cloned !== "object") {
    throw new Error(`${path} must be a JSON object`);
  }
  return cloned;
}

/** Parse one metadata-only server-owned authoring resource. */
export function parseBenchmarkAuthoringResource(
  value: unknown,
  path = "resource",
): BenchmarkAuthoringResource {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["id", "kind", "path", "mediaType", "sha256", "size", "contentIdentity"],
    path,
  );
  if (value.kind !== "asset" && value.kind !== "ground_truth") {
    throw new Error(`${path}.kind is unsupported`);
  }
  const resourcePath = memberPath(
    value.path,
    value.kind === "asset" ? "assets/" : "ground_truth/",
    [""],
    `${path}.path`,
  );
  return {
    id: identifier(value.id, STABLE_ID, `${path}.id`),
    kind: value.kind,
    path: resourcePath,
    mediaType: requireString(value.mediaType, `${path}.mediaType`),
    sha256: identifier(value.sha256, DIGEST, `${path}.sha256`),
    size: nonNegativeInteger(value.size, `${path}.size`),
    contentIdentity: identifier(
      value.contentIdentity,
      CONTENT_ID,
      `${path}.contentIdentity`,
    ),
  };
}

/** Parse the complete open-mapping authoring document and closed inventory. */
export function parseBenchmarkAuthoringDocument(
  value: unknown,
  path = "document",
): BenchmarkAuthoringDocument {
  const object = responseObject(value, path);
  rejectUnknownKeys(
    object,
    [
      "schemaVersion",
      "status",
      "manifest",
      "taskFiles",
      "protocolFiles",
      "resources",
      "directories",
    ],
    path,
  );
  if (object.status !== "unvalidated") {
    throw new Error(`${path}.status must be unvalidated`);
  }
  if (!isRecord(object.manifest)) {
    throw new Error(`${path}.manifest must be an object`);
  }
  rejectUnknownKeys(object.manifest, ["path", "document"], `${path}.manifest`);
  if (object.manifest.path !== "benchmark.yaml") {
    throw new Error(`${path}.manifest.path must be benchmark.yaml`);
  }
  if (
    !Array.isArray(object.taskFiles)
    || !Array.isArray(object.protocolFiles)
    || !Array.isArray(object.resources)
  ) {
    throw new Error(`${path} inventory members must be arrays`);
  }
  if (
    !Array.isArray(object.directories)
    || object.directories.length !== 2
    || object.directories[0] !== "assets"
    || object.directories[1] !== "ground_truth"
  ) {
    throw new Error(`${path}.directories must use the fixed inventory`);
  }

  const taskFiles = object.taskFiles.map((item, index) => {
    const itemPath = `${path}.taskFiles[${index}]`;
    if (!isRecord(item)) throw new Error(`${itemPath} must be an object`);
    rejectUnknownKeys(item, ["path", "tasks"], itemPath);
    if (!Array.isArray(item.tasks)) {
      throw new Error(`${itemPath}.tasks must be an array`);
    }
    return {
      path: memberPath(item.path, "tasks/", [".json"], `${itemPath}.path`),
      tasks: item.tasks.map((task, taskIndex) =>
        cloneJson(task, `${itemPath}.tasks[${taskIndex}]`),
      ),
    };
  });
  const protocolFiles = object.protocolFiles.map((item, index) => {
    const itemPath = `${path}.protocolFiles[${index}]`;
    if (!isRecord(item)) throw new Error(`${itemPath} must be an object`);
    rejectUnknownKeys(item, ["path", "document"], itemPath);
    return {
      path: memberPath(
        item.path,
        "protocols/",
        [".json", ".yaml", ".yml"],
        `${itemPath}.path`,
      ),
      document: jsonMapping(item.document, `${itemPath}.document`),
    };
  });
  const resources = object.resources.map((item, index) =>
    parseBenchmarkAuthoringResource(item, `${path}.resources[${index}]`),
  );
  const paths = [
    "benchmark.yaml",
    ...taskFiles.map((item) => item.path),
    ...protocolFiles.map((item) => item.path),
    ...resources.map((item) => item.path),
  ];
  if (new Set(paths).size !== paths.length) {
    throw new Error(`${path} member paths must be unique`);
  }
  if (
    taskFiles.some((item, index) => index > 0 && taskFiles[index - 1].path > item.path)
    || protocolFiles.some(
      (item, index) => index > 0 && protocolFiles[index - 1].path > item.path,
    )
    || resources.some(
      (item, index) => index > 0 && resources[index - 1].path > item.path,
    )
  ) {
    throw new Error(`${path} inventory must use deterministic path order`);
  }
  if (new Set(resources.map((item) => item.id)).size !== resources.length) {
    throw new Error(`${path} resource identities must be unique`);
  }

  return {
    schemaVersion: 1,
    status: "unvalidated",
    manifest: {
      path: "benchmark.yaml",
      document: jsonMapping(
        object.manifest.document,
        `${path}.manifest.document`,
      ),
    },
    taskFiles,
    protocolFiles,
    resources,
    directories: ["assets", "ground_truth"],
  };
}

/** Parse safe immutable revision provenance without exposing source paths. */
function parseProvenance(
  value: unknown,
  path: string,
): BenchmarkAuthoringProvenance {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "sourceKind",
      "templateName",
      "catalogEntryId",
      "catalogSnapshotIdentity",
      "packageIdentity",
      "sourceFingerprint",
      "sourceDisplayName",
      "previewFingerprint",
      "candidateDocumentFingerprint",
      "migrationContractIdentity",
      "taskEntryCount",
      "uniqueTaskCount",
    ],
    path,
  );
  if (
    value.sourceKind !== "template"
    && value.sourceKind !== "catalog"
    && value.sourceKind !== "edit"
    && value.sourceKind !== "legacy_migration"
  ) {
    throw new Error(`${path}.sourceKind is unsupported`);
  }
  const templateName = nullableString(value.templateName, `${path}.templateName`);
  if (
    templateName !== null
    && templateName !== "minimal"
    && templateName !== "dynamic-task"
    && templateName !== "composite-evaluation"
  ) {
    throw new Error(`${path}.templateName is unsupported`);
  }
  const catalogEntryId = nullableString(
    value.catalogEntryId,
    `${path}.catalogEntryId`,
  );
  if (catalogEntryId !== null && !ENTRY_ID.test(catalogEntryId)) {
    throw new Error(`${path}.catalogEntryId is malformed`);
  }
  const catalogSnapshotIdentity = nullableString(
    value.catalogSnapshotIdentity,
    `${path}.catalogSnapshotIdentity`,
  );
  const sourceFingerprint = nullableString(
    value.sourceFingerprint,
    `${path}.sourceFingerprint`,
  );
  const previewFingerprint = nullableString(
    value.previewFingerprint,
    `${path}.previewFingerprint`,
  );
  const candidateDocumentFingerprint = nullableString(
    value.candidateDocumentFingerprint,
    `${path}.candidateDocumentFingerprint`,
  );
  const migrationContractIdentity = nullableString(
    value.migrationContractIdentity,
    `${path}.migrationContractIdentity`,
  );
  for (const [label, digest] of [
    ["catalogSnapshotIdentity", catalogSnapshotIdentity],
    ["sourceFingerprint", sourceFingerprint],
    ["previewFingerprint", previewFingerprint],
    ["candidateDocumentFingerprint", candidateDocumentFingerprint],
    ["migrationContractIdentity", migrationContractIdentity],
  ] as const) {
    if (digest !== null && !DIGEST.test(digest)) {
      throw new Error(`${path}.${label} is malformed`);
    }
  }
  return {
    sourceKind: value.sourceKind,
    templateName: templateName as BenchmarkAuthoringTemplate | null,
    catalogEntryId,
    catalogSnapshotIdentity,
    packageIdentity: nullableString(
      value.packageIdentity,
      `${path}.packageIdentity`,
    ),
    sourceFingerprint,
    sourceDisplayName: nullableString(
      value.sourceDisplayName,
      `${path}.sourceDisplayName`,
    ),
    previewFingerprint,
    candidateDocumentFingerprint,
    migrationContractIdentity,
    taskEntryCount: value.taskEntryCount === null || value.taskEntryCount === undefined
      ? null
      : nonNegativeInteger(value.taskEntryCount, `${path}.taskEntryCount`),
    uniqueTaskCount: value.uniqueTaskCount === null || value.uniqueTaskCount === undefined
      ? null
      : nonNegativeInteger(value.uniqueTaskCount, `${path}.uniqueTaskCount`),
  };
}

/** Parse one strict Benchmark draft metadata record. */
export function parseBenchmarkDraftRecord(
  value: unknown,
  path = "draft",
): BenchmarkDraftRecord {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["draftId", "name", "currentRevisionId", "createdAt", "updatedAt"],
    path,
  );
  return {
    draftId: identifier(value.draftId, DRAFT_ID, `${path}.draftId`),
    name: requireString(value.name, `${path}.name`),
    currentRevisionId: identifier(
      value.currentRevisionId,
      REVISION_ID,
      `${path}.currentRevisionId`,
    ),
    createdAt: nonNegativeInteger(value.createdAt, `${path}.createdAt`),
    updatedAt: nonNegativeInteger(value.updatedAt, `${path}.updatedAt`),
  };
}

/** Parse one immutable authoring revision and its complete parsed document. */
export function parseBenchmarkAuthoringRevision(
  value: unknown,
  path = "revision",
): BenchmarkAuthoringRevision {
  const object = responseObject(value, path);
  rejectUnknownKeys(
    object,
    [
      "schemaVersion",
      "revisionId",
      "draftId",
      "ordinal",
      "parentRevisionId",
      "document",
      "documentFingerprint",
      "provenance",
      "status",
      "createdAt",
    ],
    path,
  );
  if (object.status !== "unvalidated") {
    throw new Error(`${path}.status must be unvalidated`);
  }
  const ordinal = nonNegativeInteger(object.ordinal, `${path}.ordinal`);
  if (ordinal < 1) throw new Error(`${path}.ordinal must be positive`);
  const parentRevisionId = nullableString(
    object.parentRevisionId,
    `${path}.parentRevisionId`,
  );
  if (parentRevisionId !== null && !REVISION_ID.test(parentRevisionId)) {
    throw new Error(`${path}.parentRevisionId is malformed`);
  }
  if ((ordinal === 1) !== (parentRevisionId === null)) {
    throw new Error(`${path} parent/ordinal facts disagree`);
  }
  return {
    schemaVersion: 1,
    revisionId: identifier(object.revisionId, REVISION_ID, `${path}.revisionId`),
    draftId: identifier(object.draftId, DRAFT_ID, `${path}.draftId`),
    ordinal,
    parentRevisionId,
    document: parseBenchmarkAuthoringDocument(
      object.document,
      `${path}.document`,
    ),
    documentFingerprint: identifier(
      object.documentFingerprint,
      DIGEST,
      `${path}.documentFingerprint`,
    ),
    provenance: parseProvenance(object.provenance, `${path}.provenance`),
    status: "unvalidated",
    createdAt: nonNegativeInteger(object.createdAt, `${path}.createdAt`),
  };
}

/** Parse one bounded deterministic draft page. */
export function parseBenchmarkDraftPage(value: unknown): BenchmarkDraftPage {
  const object = responseObject(value, "draftPage");
  rejectUnknownKeys(object, ["schemaVersion", "items", "nextCursor"], "draftPage");
  if (!Array.isArray(object.items)) {
    throw new Error("draftPage.items must be an array");
  }
  return {
    schemaVersion: 1,
    items: object.items.map((item, index) =>
      parseBenchmarkDraftRecord(item, `draftPage.items[${index}]`),
    ),
    nextCursor: nullableString(object.nextCursor, "draftPage.nextCursor"),
  };
}

/** Parse one draft with its authoritative current immutable revision. */
export function parseBenchmarkDraftDetail(value: unknown): BenchmarkDraftDetail {
  const object = responseObject(value, "draftDetail");
  rejectUnknownKeys(
    object,
    ["schemaVersion", "draft", "currentRevision"],
    "draftDetail",
  );
  const draft = parseBenchmarkDraftRecord(object.draft, "draftDetail.draft");
  const currentRevision = parseBenchmarkAuthoringRevision(
    object.currentRevision,
    "draftDetail.currentRevision",
  );
  if (
    draft.draftId !== currentRevision.draftId
    || draft.currentRevisionId !== currentRevision.revisionId
  ) {
    throw new Error("draftDetail current revision facts disagree");
  }
  return { schemaVersion: 1, draft, currentRevision };
}

/** Parse an idempotent create/save response and require aligned ownership. */
export function parseBenchmarkDraftCommandResponse(
  value: unknown,
): BenchmarkDraftCommandResponse {
  const object = responseObject(value, "draftCommand");
  rejectUnknownKeys(
    object,
    ["schemaVersion", "created", "draft", "revision"],
    "draftCommand",
  );
  if (typeof object.created !== "boolean") {
    throw new Error("draftCommand.created must be boolean");
  }
  const draft = parseBenchmarkDraftRecord(object.draft, "draftCommand.draft");
  const revision = parseBenchmarkAuthoringRevision(
    object.revision,
    "draftCommand.revision",
  );
  if (
    draft.draftId !== revision.draftId
    || draft.currentRevisionId !== revision.revisionId
  ) {
    throw new Error("draftCommand ownership facts disagree");
  }
  return {
    schemaVersion: 1,
    created: object.created,
    draft,
    revision,
  };
}

/** Parse one strict managed-content command result without assuming currentness.
 *
 * Args:
 *   value: Untrusted Studio command payload.
 *
 * Raises:
 *   Error: The envelope, operation fields, ownership, or revision projection
 *     is malformed.
 *
 * Returns:
 *   A typed immutable content-command result.
 */
export function parseBenchmarkAuthoringContentCommandResult(
  value: unknown,
): BenchmarkAuthoringContentCommandResult {
  const object = responseObject(value, "contentCommand");
  rejectUnknownKeys(
    object,
    [
      "schemaVersion",
      "operation",
      "created",
      "draft",
      "revision",
      "resource",
      "removedResourceId",
    ],
    "contentCommand",
  );
  if (
    object.operation !== "upload"
    && object.operation !== "replace"
    && object.operation !== "remove"
  ) {
    throw new Error("contentCommand.operation is unsupported");
  }
  if (typeof object.created !== "boolean") {
    throw new Error("contentCommand.created must be boolean");
  }
  const draft = parseBenchmarkDraftRecord(object.draft, "contentCommand.draft");
  const revision = parseBenchmarkAuthoringRevision(
    object.revision,
    "contentCommand.revision",
  );
  if (draft.draftId !== revision.draftId) {
    throw new Error("contentCommand ownership facts disagree");
  }

  if (object.operation === "remove") {
    if (object.resource != null || object.removedResourceId == null) {
      throw new Error("contentCommand remove fields are invalid");
    }
    const removedResourceId = identifier(
      object.removedResourceId,
      STABLE_ID,
      "contentCommand.removedResourceId",
    );
    if (
      revision.document.resources.some(
        (resource) => resource.id === removedResourceId,
      )
    ) {
      throw new Error("contentCommand removed resource remains in revision");
    }
    return {
      schemaVersion: 1,
      operation: "remove",
      created: object.created,
      draft,
      revision,
      resource: null,
      removedResourceId,
    };
  }

  if (object.resource == null || object.removedResourceId != null) {
    throw new Error("contentCommand write fields are invalid");
  }
  const resource = parseBenchmarkAuthoringResource(
    object.resource,
    "contentCommand.resource",
  );
  const projected = revision.document.resources.find(
    (item) => item.id === resource.id,
  );
  if (
    projected === undefined
    || JSON.stringify(projected) !== JSON.stringify(resource)
  ) {
    throw new Error("contentCommand resource projection disagrees");
  }
  return {
    schemaVersion: 1,
    operation: object.operation,
    created: object.created,
    draft,
    revision,
    resource,
    removedResourceId: null,
  };
}
