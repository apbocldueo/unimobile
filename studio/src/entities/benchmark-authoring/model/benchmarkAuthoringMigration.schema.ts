import {
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
} from "@/shared/lib";
import {
  parseBenchmarkAuthoringRevision,
  parseBenchmarkDraftRecord,
  type BenchmarkAuthoringRevision,
  type BenchmarkDraftRecord,
} from "./benchmarkAuthoring.schema";

export const BENCHMARK_LEGACY_MIGRATION_MAX_SOURCE_BYTES = 1024 * 1024;
export const BENCHMARK_LEGACY_MIGRATION_MAX_TASKS = 100;
export const BENCHMARK_LEGACY_MIGRATION_MAX_DIAGNOSTICS = 100;

export type BenchmarkLegacyMigrationTarget = {
  draftName: string;
  publisher: string;
  packageName: string;
  version: string;
  title: string;
  platform: "android" | "harmonyos";
  split: string;
  taskFilePath: string;
};

export type BenchmarkLegacyMigrationPreviewRequest = {
  schemaVersion: 1;
  sourceName: string;
  sourceText: string;
  target: BenchmarkLegacyMigrationTarget;
};

export type BenchmarkLegacyMigrationConfirmRequest =
  BenchmarkLegacyMigrationPreviewRequest & {
    clientRequestId: string;
    previewFingerprint: string;
    migrationContractIdentity: string;
  };

export type BenchmarkLegacyMigrationSourceFacts = {
  sourceName: string;
  utf8Size: number;
  sourceFingerprint: string;
  entryCount: number;
  uniqueTaskCount: number;
};

export type BenchmarkLegacyMigrationDiagnostic = {
  code: string;
  severity: "error" | "warning";
  message: string;
  sourceIndex: number | null;
  fieldPath: Array<string | number>;
  taskId: string | null;
};

export type BenchmarkLegacyMigrationDiffEntry = {
  code: string;
  category: "wrapper" | "declaration" | "omission" | "representation";
  path: string[];
  message: string;
};

export type BenchmarkLegacyMigrationDiff = {
  taskChanges: {
    retained: number;
    renamed: 0;
    removed: 0;
    deduplicated: 0;
    rewritten: 0;
  };
  entries: BenchmarkLegacyMigrationDiffEntry[];
  pluginIds: string[];
  appIds: string[];
};

export type BenchmarkLegacyMigrationPostWork = {
  code: string;
  message: string;
  sourceIndexes: number[];
};

export type BenchmarkLegacyMigrationEvidence = {
  validation: false;
  contractTest: false;
  freeze: false;
  publication: false;
  export: false;
  execution: false;
  device: false;
};

export type BenchmarkLegacyMigrationPreview = {
  schemaVersion: 1;
  confirmable: boolean;
  source: BenchmarkLegacyMigrationSourceFacts;
  target: BenchmarkLegacyMigrationTarget;
  migrationContractIdentity: string;
  candidateDocumentFingerprint: string | null;
  previewFingerprint: string | null;
  diff: BenchmarkLegacyMigrationDiff;
  diagnostics: BenchmarkLegacyMigrationDiagnostic[];
  postMigrationWork: BenchmarkLegacyMigrationPostWork[];
  evidence: BenchmarkLegacyMigrationEvidence;
};

export type BenchmarkLegacyMigrationConfirmResponse = {
  schemaVersion: 1;
  created: boolean;
  draft: BenchmarkDraftRecord;
  revision: BenchmarkAuthoringRevision;
  sourceFingerprint: string;
  previewFingerprint: string;
  migrationContractIdentity: string;
  candidateDocumentFingerprint: string;
  evidence: BenchmarkLegacyMigrationEvidence;
};

const DIGEST = /^sha256:[a-f0-9]{64}$/;

/** Require one strict schema-version-one response object. */
function responseObject(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value) || value.schemaVersion !== 1) {
    throw new Error(`${path} must be a schemaVersion 1 object`);
  }
  return value;
}

/** Require one finite non-negative safe integer. */
function count(value: unknown, path: string): number {
  const parsed = requireNumber(value, path);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error(`${path} must be a non-negative safe integer`);
  }
  return parsed;
}

/** Require one canonical prefixed SHA-256 identity. */
function digest(value: unknown, path: string): string {
  const parsed = requireString(value, path);
  if (!DIGEST.test(parsed)) throw new Error(`${path} is malformed`);
  return parsed;
}

/** Parse one exact explicit migration target echoed by Preview. */
export function parseBenchmarkLegacyMigrationTarget(
  value: unknown,
  path = "target",
): BenchmarkLegacyMigrationTarget {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["draftName", "publisher", "packageName", "version", "title", "platform", "split", "taskFilePath"], path);
  if (value.platform !== "android" && value.platform !== "harmonyos") {
    throw new Error(`${path}.platform is unsupported`);
  }
  return {
    draftName: requireString(value.draftName, `${path}.draftName`),
    publisher: requireString(value.publisher, `${path}.publisher`),
    packageName: requireString(value.packageName, `${path}.packageName`),
    version: requireString(value.version, `${path}.version`),
    title: requireString(value.title, `${path}.title`),
    platform: value.platform,
    split: requireString(value.split, `${path}.split`),
    taskFilePath: requireString(value.taskFilePath, `${path}.taskFilePath`),
  };
}

/** Parse one bounded sanitized migration diagnostic. */
function parseDiagnostic(
  value: unknown,
  path: string,
): BenchmarkLegacyMigrationDiagnostic {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["code", "severity", "message", "sourceIndex", "fieldPath", "taskId"], path);
  if (value.severity !== "error" && value.severity !== "warning") {
    throw new Error(`${path}.severity is unsupported`);
  }
  if (!Array.isArray(value.fieldPath)) throw new Error(`${path}.fieldPath must be an array`);
  const fieldPath = value.fieldPath.map((item, index) => {
    if (typeof item === "string") return item;
    return count(item, `${path}.fieldPath[${index}]`);
  });
  return {
    code: requireString(value.code, `${path}.code`),
    severity: value.severity,
    message: requireString(value.message, `${path}.message`),
    sourceIndex: value.sourceIndex === null || value.sourceIndex === undefined
      ? null
      : count(value.sourceIndex, `${path}.sourceIndex`),
    fieldPath,
    taskId: value.taskId === null || value.taskId === undefined
      ? null
      : requireString(value.taskId, `${path}.taskId`),
  };
}

/** Parse one structured deterministic migration diff. */
function parseDiff(value: unknown, path: string): BenchmarkLegacyMigrationDiff {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["taskChanges", "entries", "pluginIds", "appIds"], path);
  if (!isRecord(value.taskChanges)) throw new Error(`${path}.taskChanges must be an object`);
  const taskChanges = value.taskChanges;
  rejectUnknownKeys(taskChanges, ["retained", "renamed", "removed", "deduplicated", "rewritten"], `${path}.taskChanges`);
  const zero = (field: "renamed" | "removed" | "deduplicated" | "rewritten"): 0 => {
    if (taskChanges[field] !== 0) throw new Error(`${path}.taskChanges.${field} must be zero`);
    return 0;
  };
  if (!Array.isArray(value.entries) || !Array.isArray(value.pluginIds) || !Array.isArray(value.appIds)) {
    throw new Error(`${path} collections must be arrays`);
  }
  const entries = value.entries.map((item, index) => {
    const itemPath = `${path}.entries[${index}]`;
    if (!isRecord(item)) throw new Error(`${itemPath} must be an object`);
    rejectUnknownKeys(item, ["code", "category", "path", "message"], itemPath);
    if (!Array.isArray(item.path) || !item.path.every((part) => typeof part === "string")) throw new Error(`${itemPath}.path must be a string array`);
    if (item.category !== "wrapper" && item.category !== "declaration" && item.category !== "omission" && item.category !== "representation") throw new Error(`${itemPath}.category is unsupported`);
    return {
      code: requireString(item.code, `${itemPath}.code`),
      category: item.category as BenchmarkLegacyMigrationDiffEntry["category"],
      path: [...item.path] as string[],
      message: requireString(item.message, `${itemPath}.message`),
    };
  });
  return {
    taskChanges: {
      retained: count(taskChanges.retained, `${path}.taskChanges.retained`),
      renamed: zero("renamed"),
      removed: zero("removed"),
      deduplicated: zero("deduplicated"),
      rewritten: zero("rewritten"),
    },
    entries,
    pluginIds: value.pluginIds.map((item, index) => requireString(item, `${path}.pluginIds[${index}]`)),
    appIds: value.appIds.map((item, index) => requireString(item, `${path}.appIds[${index}]`)),
  };
}

/** Parse the closed all-false evidence boundary. */
function parseEvidence(value: unknown, path: string): BenchmarkLegacyMigrationEvidence {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  const keys = ["validation", "contractTest", "freeze", "publication", "export", "execution", "device"] as const;
  rejectUnknownKeys(value, keys, path);
  for (const key of keys) {
    if (value[key] !== false) throw new Error(`${path}.${key} must be false`);
  }
  return {
    validation: false,
    contractTest: false,
    freeze: false,
    publication: false,
    export: false,
    execution: false,
    device: false,
  };
}

/** Parse one transient authoritative migration Preview envelope. */
export function parseBenchmarkLegacyMigrationPreview(
  value: unknown,
): BenchmarkLegacyMigrationPreview {
  const object = responseObject(value, "migrationPreview");
  rejectUnknownKeys(object, ["schemaVersion", "confirmable", "source", "target", "migrationContractIdentity", "candidateDocumentFingerprint", "previewFingerprint", "diff", "diagnostics", "postMigrationWork", "evidence"], "migrationPreview");
  if (typeof object.confirmable !== "boolean") throw new Error("migrationPreview.confirmable must be boolean");
  if (!isRecord(object.source)) throw new Error("migrationPreview.source must be an object");
  rejectUnknownKeys(object.source, ["sourceName", "utf8Size", "sourceFingerprint", "entryCount", "uniqueTaskCount"], "migrationPreview.source");
  if (!Array.isArray(object.diagnostics) || object.diagnostics.length > BENCHMARK_LEGACY_MIGRATION_MAX_DIAGNOSTICS) throw new Error("migrationPreview.diagnostics is not bounded");
  if (!Array.isArray(object.postMigrationWork)) throw new Error("migrationPreview.postMigrationWork must be an array");
  return {
    schemaVersion: 1,
    confirmable: object.confirmable,
    source: {
      sourceName: requireString(object.source.sourceName, "migrationPreview.source.sourceName"),
      utf8Size: count(object.source.utf8Size, "migrationPreview.source.utf8Size"),
      sourceFingerprint: digest(object.source.sourceFingerprint, "migrationPreview.source.sourceFingerprint"),
      entryCount: count(object.source.entryCount, "migrationPreview.source.entryCount"),
      uniqueTaskCount: count(object.source.uniqueTaskCount, "migrationPreview.source.uniqueTaskCount"),
    },
    target: parseBenchmarkLegacyMigrationTarget(object.target, "migrationPreview.target"),
    migrationContractIdentity: digest(object.migrationContractIdentity, "migrationPreview.migrationContractIdentity"),
    candidateDocumentFingerprint: object.candidateDocumentFingerprint === null || object.candidateDocumentFingerprint === undefined ? null : digest(object.candidateDocumentFingerprint, "migrationPreview.candidateDocumentFingerprint"),
    previewFingerprint: object.previewFingerprint === null || object.previewFingerprint === undefined ? null : digest(object.previewFingerprint, "migrationPreview.previewFingerprint"),
    diff: parseDiff(object.diff, "migrationPreview.diff"),
    diagnostics: object.diagnostics.map((item, index) => parseDiagnostic(item, `migrationPreview.diagnostics[${index}]`)),
    postMigrationWork: object.postMigrationWork.map((item, index) => {
      const itemPath = `migrationPreview.postMigrationWork[${index}]`;
      if (!isRecord(item)) throw new Error(`${itemPath} must be an object`);
      rejectUnknownKeys(item, ["code", "message", "sourceIndexes"], itemPath);
      if (!Array.isArray(item.sourceIndexes)) throw new Error(`${itemPath}.sourceIndexes must be an array`);
      return {
        code: requireString(item.code, `${itemPath}.code`),
        message: requireString(item.message, `${itemPath}.message`),
        sourceIndexes: item.sourceIndexes.map((entry, sourceIndex) => count(entry, `${itemPath}.sourceIndexes[${sourceIndex}]`)),
      };
    }),
    evidence: parseEvidence(object.evidence, "migrationPreview.evidence"),
  };
}

/** Parse one fresh or exactly replayed authoritative Confirm response. */
export function parseBenchmarkLegacyMigrationConfirmResponse(
  value: unknown,
): BenchmarkLegacyMigrationConfirmResponse {
  const object = responseObject(value, "migrationConfirm");
  rejectUnknownKeys(object, ["schemaVersion", "created", "draft", "revision", "sourceFingerprint", "previewFingerprint", "migrationContractIdentity", "candidateDocumentFingerprint", "evidence"], "migrationConfirm");
  if (typeof object.created !== "boolean") throw new Error("migrationConfirm.created must be boolean");
  return {
    schemaVersion: 1,
    created: object.created,
    draft: parseBenchmarkDraftRecord(object.draft, "migrationConfirm.draft"),
    revision: parseBenchmarkAuthoringRevision(object.revision, "migrationConfirm.revision"),
    sourceFingerprint: digest(object.sourceFingerprint, "migrationConfirm.sourceFingerprint"),
    previewFingerprint: digest(object.previewFingerprint, "migrationConfirm.previewFingerprint"),
    migrationContractIdentity: digest(object.migrationContractIdentity, "migrationConfirm.migrationContractIdentity"),
    candidateDocumentFingerprint: digest(object.candidateDocumentFingerprint, "migrationConfirm.candidateDocumentFingerprint"),
    evidence: parseEvidence(object.evidence, "migrationConfirm.evidence"),
  };
}
