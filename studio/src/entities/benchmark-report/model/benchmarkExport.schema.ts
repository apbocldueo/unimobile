import {
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
} from "@/shared/lib";

export const BENCHMARK_PUBLICATION_MANIFEST_MAX_BYTES = 2 * 1024 * 1024;
export const BENCHMARK_PUBLICATION_MANIFEST_MAX_MEMBERS = 2000;

export type BenchmarkPublicationManifestScope = {
  experimentId: string;
  taskRunId: string | null;
};

export type BenchmarkPublicationManifestMember = {
  reference: string;
  kind: string;
  contentType: string;
  size: number;
  sha256: string;
  scope: BenchmarkPublicationManifestScope;
  availability: string;
  exclusionReason: string;
};

export type BenchmarkPublicationExcludedEvidence = {
  kind: "prompt";
  availability: "hidden";
  reason: string;
};

export type BenchmarkPublicationManifest = {
  schemaVersion: 1;
  kind: "studio_benchmark_publication_manifest";
  experimentId: string;
  taskRunId: string;
  members: BenchmarkPublicationManifestMember[];
  excludedEvidence: BenchmarkPublicationExcludedEvidence[];
};

export type BenchmarkPublicationManifestSummary = {
  experimentId: string;
  taskRunId: string;
  memberCount: number;
  declaredBytes: number;
  members: BenchmarkPublicationManifestMember[];
  excludedEvidence: BenchmarkPublicationExcludedEvidence[];
};

const EXPERIMENT_ID = /^experiment-[a-f0-9]{32}$/;
const TASK_RUN_ID = /^task-run-[a-f0-9]{32}$/;
const SHA256 = /^sha256:[a-f0-9]{64}$/;
const SAFE_REFERENCE_MAX = 1024;
const TEXT_MAX = 1000;
const KNOWN_CONTENT_TYPES = new Set([
  "application/json",
  "application/x-ndjson",
  "application/xml",
  "application/zip",
  "image/png",
]);
const KNOWN_MEMBER_KINDS = new Set([
  "action_evidence",
  "core_trajectory_bundle",
  "definition_snapshot",
  "experiment_report",
  "experiment_result",
  "model_response",
  "publication_manifest",
  "runtime_manifest",
  "runtime_task_result",
  "screenshot",
  "task_report",
  "task_result",
  "task_trajectory",
  "ui_xml",
]);
const KNOWN_AVAILABILITIES = new Set([
  "available",
  "redacted",
  "truncated",
  "excluded",
  "missing",
  "corrupt",
  "failed",
  "not_produced",
]);

/** Require one bounded non-empty text field. */
function boundedText(value: unknown, path: string, max = TEXT_MAX): string {
  const parsed = requireString(value, path);
  if (parsed.length === 0 || parsed.length > max) {
    throw new Error(`${path} has invalid text length`);
  }
  return parsed;
}

/** Require a canonical non-negative safe integer. */
function nonNegativeInteger(value: unknown, path: string): number {
  const parsed = requireNumber(value, path);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error(`${path} must be a non-negative safe integer`);
  }
  return parsed;
}

/** Parse one safe Experiment-root-relative publication reference. */
function safeReference(value: unknown, path: string): string {
  const reference = boundedText(value, path, SAFE_REFERENCE_MAX);
  const parts = reference.split("/");
  if (
    reference.startsWith("/")
    || reference.startsWith("\\")
    || /^[A-Za-z]:[\\/]/.test(reference)
    || reference.includes("\\")
    || parts.some((part) => part.length === 0 || part === "." || part === "..")
  ) {
    throw new Error(`${path} must be a safe relative reference`);
  }
  return reference;
}

/** Parse one exact manifest member scope. */
function parseMemberScope(
  value: unknown,
  expectedExperimentId: string,
  expectedTaskRunId: string,
  path: string,
): BenchmarkPublicationManifestScope {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["experimentId", "taskRunId"], path);
  const experimentId = requireString(value.experimentId, `${path}.experimentId`);
  const taskRunId = value.taskRunId === undefined
    ? null
    : requireString(value.taskRunId, `${path}.taskRunId`);
  if (
    experimentId !== expectedExperimentId
    || (taskRunId !== null && taskRunId !== expectedTaskRunId)
  ) {
    throw new Error(`${path} conflicts with publication scope`);
  }
  return { experimentId, taskRunId };
}

/** Parse one strict publication manifest member. */
function parseManifestMember(
  value: unknown,
  expectedExperimentId: string,
  expectedTaskRunId: string,
  path: string,
): BenchmarkPublicationManifestMember {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "reference",
      "kind",
      "contentType",
      "size",
      "sha256",
      "scope",
      "availability",
      "exclusionReason",
    ],
    path,
  );
  const kind = boundedText(value.kind, `${path}.kind`, 160);
  const contentType = boundedText(
    value.contentType,
    `${path}.contentType`,
    160,
  ).toLowerCase();
  const availability = boundedText(
    value.availability,
    `${path}.availability`,
    64,
  );
  const sha256 = requireString(value.sha256, `${path}.sha256`);
  if (!KNOWN_MEMBER_KINDS.has(kind)) {
    throw new Error(`${path}.kind is unsupported`);
  }
  if (!KNOWN_CONTENT_TYPES.has(contentType)) {
    throw new Error(`${path}.contentType is unsupported`);
  }
  if (!KNOWN_AVAILABILITIES.has(availability)) {
    throw new Error(`${path}.availability is unsupported`);
  }
  if (!SHA256.test(sha256)) {
    throw new Error(`${path}.sha256 is invalid`);
  }
  const exclusionReason = value.exclusionReason;
  if (
    typeof exclusionReason !== "string"
    || exclusionReason.length > TEXT_MAX
  ) {
    throw new Error(`${path}.exclusionReason must be a bounded string`);
  }
  return {
    reference: safeReference(value.reference, `${path}.reference`),
    kind,
    contentType,
    size: nonNegativeInteger(value.size, `${path}.size`),
    sha256,
    scope: parseMemberScope(
      value.scope,
      expectedExperimentId,
      expectedTaskRunId,
      `${path}.scope`,
    ),
    availability,
    exclusionReason,
  };
}

/** Parse one bounded explicit excluded-evidence policy fact. */
function parseExcludedEvidence(
  value: unknown,
  path: string,
): BenchmarkPublicationExcludedEvidence {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["kind", "availability", "reason"], path);
  if (value.kind !== "prompt" || value.availability !== "hidden") {
    throw new Error(`${path} has an unsupported exclusion policy`);
  }
  return {
    kind: "prompt",
    availability: "hidden",
    reason: boundedText(value.reason, `${path}.reason`, TEXT_MAX),
  };
}

/** Parse the exact bounded Studio Benchmark publication manifest schema 1.
 *
 * Args:
 *   value: Untrusted decoded JSON.
 *   expectedExperimentId: Owning Experiment identity.
 *   knownTaskRunIds: Durable TaskRun identities allowed by the Experiment.
 *
 * Raises:
 *   Error: Schema, identity, collection, member, or policy facts conflict.
 *
 * Returns:
 *   A strict immutable publication fact projection with no content capability.
 */
export function parseBenchmarkPublicationManifest(
  value: unknown,
  expectedExperimentId: string,
  knownTaskRunIds: ReadonlySet<string>,
): BenchmarkPublicationManifest {
  if (!isRecord(value)) throw new Error("publicationManifest must be an object");
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "kind",
      "experimentId",
      "taskRunId",
      "members",
      "excludedEvidence",
    ],
    "publicationManifest",
  );
  if (
    value.schemaVersion !== 1
    || value.kind !== "studio_benchmark_publication_manifest"
  ) {
    throw new Error("publicationManifest uses an unsupported schema or kind");
  }
  const experimentId = requireString(
    value.experimentId,
    "publicationManifest.experimentId",
  );
  const taskRunId = requireString(
    value.taskRunId,
    "publicationManifest.taskRunId",
  );
  if (
    experimentId !== expectedExperimentId
    || !EXPERIMENT_ID.test(experimentId)
    || !TASK_RUN_ID.test(taskRunId)
    || !knownTaskRunIds.has(taskRunId)
  ) {
    throw new Error("publicationManifest identities conflict with scope");
  }
  if (
    !Array.isArray(value.members)
    || value.members.length > BENCHMARK_PUBLICATION_MANIFEST_MAX_MEMBERS
  ) {
    throw new Error("publicationManifest.members must be bounded");
  }
  if (
    !Array.isArray(value.excludedEvidence)
    || value.excludedEvidence.length > 100
  ) {
    throw new Error("publicationManifest.excludedEvidence must be bounded");
  }
  const members = value.members.map((member, index) =>
    parseManifestMember(
      member,
      experimentId,
      taskRunId,
      `publicationManifest.members[${index}]`,
    ),
  );
  const references = new Set(members.map((member) => member.reference));
  if (references.size !== members.length) {
    throw new Error("publicationManifest contains duplicate member references");
  }
  return {
    schemaVersion: 1,
    kind: "studio_benchmark_publication_manifest",
    experimentId,
    taskRunId,
    members,
    excludedEvidence: value.excludedEvidence.map((item, index) =>
      parseExcludedEvidence(
        item,
        `publicationManifest.excludedEvidence[${index}]`,
      ),
    ),
  };
}

/** Summarize declared bundle facts without creating standalone capabilities. */
export function summarizeBenchmarkPublicationManifest(
  manifest: BenchmarkPublicationManifest,
): BenchmarkPublicationManifestSummary {
  return {
    experimentId: manifest.experimentId,
    taskRunId: manifest.taskRunId,
    memberCount: manifest.members.length,
    declaredBytes: manifest.members.reduce(
      (total, member) => total + member.size,
      0,
    ),
    members: manifest.members,
    excludedEvidence: manifest.excludedEvidence,
  };
}
