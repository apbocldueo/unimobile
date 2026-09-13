import { createReadStream, existsSync, statSync } from "node:fs";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.ZHIXING_AUTHORING_FIXTURE_PORT ?? 8766);
const DIST = process.env.ZHIXING_AUTHORING_FIXTURE_DIST
  ?? join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const HASH = `sha256:${"e".repeat(64)}`;
const ENTRY_ID = `benchmark-entry-${"d".repeat(32)}`;
const CONTENT_ID = `benchmark-content-${"f".repeat(64)}`;
const ANALYSIS_AGENT_ID = "agent-no-device-fixture";
const ANALYSIS_AGENT_REVISION_ID = "agent-revision-no-device-fixture";
const ANALYSIS_GRAPH_IDENTITY = `sha256:${"a".repeat(64)}`;
const CONTRACT_PROFILE = {
  profileId: "studio-safe-v1",
  version: "1.0.0",
  title: "Studio safe fake fixtures",
  description: "Reviewed in-process fake contracts for a no-device browser fixture.",
  evidenceLevel: "fake-contract",
  supportedKinds: ["environment", "evaluator", "initializer"],
  capabilities: [],
};
let draftOrdinal = 1;
let revisionOrdinal = 1;
const drafts = new Map();
const retryAttempts = new Set();
const contentCommands = new Map();
const packageRevisions = new Map();
const releaseCommands = new Map();
const publications = new Map();
const packageExports = new Map();
const managedContent = new Map([
  [`benchmark-content-${"0".repeat(64)}`, Buffer.alloc(64, 0)],
]);
const forbiddenBoundaryCalls = {
  initializer: 0,
  environment: 0,
  evaluator: 0,
  agentExecution: 0,
  device: 0,
  pluginConstruction: 0,
  model: 0,
  network: 0,
  secret: 0,
  experiment: 0,
  taskRunResult: 0,
  reportReplay: 0,
  contractTest: 0,
  publicationMigrationExport: 0,
  releasePublication: 0,
  packageExport: 0,
  android: 0,
};

/** Return one opaque deterministic ID from a bounded fixture ordinal. */
function opaqueId(prefix, ordinal) {
  return `${prefix}-${ordinal.toString(16).padStart(32, "0")}`;
}

/** Return the definition-only initial document for one fixture draft. */
function initialDocument(packageName = "browser-fixture") {
  return {
    schemaVersion: 1,
    status: "unvalidated",
    manifest: {
      path: "benchmark.yaml",
      document: {
        schema_version: "1.0",
        identity: {
          publisher: "fixture",
          name: packageName,
          version: "0.1.0",
          extension_identity: "preserve-me",
        },
        title: "Browser Fixture",
        platforms: ["android"],
        splits: {
          test: {
            files: ["tasks/test.json"],
            extension_split: { keep: true },
          },
        },
        applications: [{ id: "fixture-app" }],
        plugins: [{ id: "fixture-plugin" }],
        default_protocol: "protocols/default.yaml",
        ground_truth: {
          inline: { kind: "json", value: { expected: true } },
          file: { kind: "file", resource_id: "fixture-ground-truth" },
        },
        x_extension: { keep: true },
      },
    },
    taskFiles: [
      {
        path: "tasks/test.json",
        tasks: [{ id: "browser-task", instruction: "No device is used." }],
      },
    ],
    protocolFiles: [
      {
        path: "protocols/default.yaml",
        document: {
          schema_version: "1.0",
          seed: 17,
          repeats: 1,
          x_protocol: "preserve-me",
        },
      },
    ],
    resources: [
      {
        id: "fixture-asset",
        kind: "asset",
        path: "assets/screen.png",
        mediaType: "image/png",
        sha256: HASH,
        size: 128,
        contentIdentity: CONTENT_ID,
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

/** Create one immutable fixture revision and advance its identity sequence. */
function revision(draftId, document, provenance, parentRevisionId = null) {
  const ordinal = parentRevisionId === null ? 1 : drafts.get(draftId).revision.ordinal + 1;
  const value = {
    schemaVersion: 1,
    revisionId: opaqueId("benchmark-authoring-revision", revisionOrdinal++),
    draftId,
    ordinal,
    parentRevisionId,
    document,
    documentFingerprint: HASH,
    provenance,
    status: "unvalidated",
    createdAt: Date.now(),
  };
  return value;
}

/** Persist one in-memory draft and return the versioned command response. */
function createDraft(name, document, provenance) {
  const draftId = opaqueId("benchmark-draft", draftOrdinal++);
  const firstRevision = revision(draftId, document, provenance);
  const draft = {
    draftId,
    name,
    currentRevisionId: firstRevision.revisionId,
    createdAt: firstRevision.createdAt,
    updatedAt: firstRevision.createdAt,
  };
  drafts.set(draftId, {
    draft,
    revision: firstRevision,
    revisions: new Map([[firstRevision.revisionId, firstRevision]]),
  });
  return {
    schemaVersion: 1,
    created: true,
    draft,
    revision: firstRevision,
  };
}

const seeded = createDraft(
  "Browser Seed Draft",
  initialDocument(),
  {
    sourceKind: "catalog",
    templateName: null,
    catalogEntryId: ENTRY_ID,
    catalogSnapshotIdentity: HASH,
    packageIdentity: "fixture/browser-fixture@0.1.0",
    sourceFingerprint: `sha256:${"1".repeat(64)}`,
  },
);

/** Read a bounded JSON request body from the local fixture client. */
async function readJson(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 2 * 1024 * 1024) throw new Error("fixture body too large");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

/** Read one bounded raw managed-content body without JSON or Base64 framing. */
async function readRaw(request, maxBytes = 8 * 1024 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > maxBytes) throw new Error("fixture managed content too large");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

/** Clone one fixture document before projecting an immutable child revision. */
function cloneDocument(document) {
  return JSON.parse(JSON.stringify(document));
}

/** Return an authoritative resource descriptor derived from uploaded bytes. */
function managedResource({ id, kind, path, mediaType, bytes }) {
  const digest = createHash("sha256").update(bytes).digest("hex");
  const contentIdentity = `benchmark-content-${digest}`;
  managedContent.set(contentIdentity, bytes);
  return {
    id,
    kind,
    path,
    mediaType,
    sha256: `sha256:${digest}`,
    size: bytes.byteLength,
    contentIdentity,
  };
}

/** Advance one draft through an immutable unvalidated resource projection. */
function applyResourceRevision(item, resources) {
  const document = cloneDocument(item.revision.document);
  document.resources = [...resources].sort((left, right) =>
    left.path.localeCompare(right.path));
  const next = revision(
    item.draft.draftId,
    document,
    {
      sourceKind: "edit",
      templateName: null,
      catalogEntryId: null,
      catalogSnapshotIdentity: null,
      packageIdentity: null,
      sourceFingerprint: null,
    },
    item.revision.revisionId,
  );
  item.revision = next;
  item.revisions.set(next.revisionId, next);
  item.draft = {
    ...item.draft,
    currentRevisionId: next.revisionId,
    updatedAt: next.createdAt,
  };
  return next;
}

/** Build one strict content-command result over an immutable revision. */
function contentResult(item, operation, created, revisionValue, resource, removedResourceId) {
  return {
    schemaVersion: 1,
    operation,
    created,
    draft: item.draft,
    revision: revisionValue,
    resource,
    removedResourceId,
  };
}

/** Send one JSON response with explicit no-store semantics. */
function sendJson(response, status, value) {
  const body = Buffer.from(JSON.stringify(value));
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": body.byteLength,
    "Cache-Control": "no-store",
  });
  response.end(body);
}

/** Send one no-store deterministic Package archive response or HEAD metadata. */
function sendArchive(request, response, descriptor, bytes) {
  const headers = {
    "Content-Type": descriptor.archiveMediaType,
    "Content-Length": bytes.byteLength,
    "Content-Disposition": `attachment; filename="${descriptor.filename}"`,
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Content-SHA256": descriptor.sha256,
    ETag: `"${descriptor.sha256.slice("sha256:".length)}"`,
    "Access-Control-Expose-Headers": "Content-Length, Content-Disposition, X-Content-SHA256, ETag",
  };
  response.writeHead(200, headers);
  response.end(request.method === "HEAD" ? undefined : bytes);
}

/** Send one stable Studio error envelope. */
function sendError(response, status, code, message, currentRevisionId = null) {
  sendJson(response, status, {
    schemaVersion: 1,
    error: { code, message, currentRevisionId },
  });
}

/** Return the Catalog page used by opaque copy creation. */
function catalogPage() {
  const released = [...publications.values()].map((publication) => ({
    catalogEntryId: publication.catalogEntryId,
    packageIdentity: publication.packageIdentity,
    title: "Managed Browser Release",
    version: "0.1.0",
    sourceKind: "catalog",
    platforms: ["android"],
    splits: [{ name: "test", taskCount: 1 }],
    availability: "available",
    warnings: [],
  }));
  return {
    schemaVersion: 1,
    items: [
      {
        catalogEntryId: ENTRY_ID,
        packageIdentity: "fixture/browser-fixture@0.1.0",
        title: "Browser Catalog Fixture",
        version: "0.1.0",
        sourceKind: "catalog",
        platforms: ["android"],
        splits: [{ name: "test", taskCount: 1 }],
        availability: "available",
        warnings: [],
      },
      ...released,
    ],
    nextCursor: null,
  };
}

/** Build one exact E-1 freeze response and retain its immutable release facts. */
function freezePackage(item, command) {
  const commandKey = `${item.draft.draftId}:${command.clientRequestId}`;
  const existing = releaseCommands.get(commandKey);
  if (existing) return { schemaVersion: 1, created: false, detail: existing };
  const packageRevisionId = opaqueId(
    "benchmark-package-revision",
    packageRevisions.size + 1,
  );
  const attestationId = opaqueId(
    "benchmark-validation-attestation",
    packageRevisions.size + 1,
  );
  const closureIdentity = `sha256:${createHash("sha256")
    .update(`${item.revision.revisionId}:closure`)
    .digest("hex")}`;
  const detail = {
    schemaVersion: 1,
    packageRevision: {
      schemaVersion: 1,
      packageRevisionId,
      draftId: item.draft.draftId,
      authoringRevisionId: item.revision.revisionId,
      validationAttestationId: attestationId,
      packageIdentity: "fixture/browser-fixture@0.1.0",
      packageContentIdentity: HASH,
      closureIdentity,
      members: [{
        ordinal: 0,
        kind: "manifest",
        path: "benchmark.yaml",
        mediaType: "application/json",
        size: 128,
        sha256: HASH,
        contentIdentity: CONTENT_ID,
      }],
      createdAt: Date.now(),
    },
    validationAttestation: {
      schemaVersion: 1,
      attestationId,
      draftId: item.draft.draftId,
      authoringRevisionId: item.revision.revisionId,
      documentFingerprint: item.revision.documentFingerprint,
      validationContractVersion: "studio-benchmark-freeze-validation-v1",
      packageIdentity: "fixture/browser-fixture@0.1.0",
      packageContentIdentity: HASH,
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
      createdAt: Date.now(),
    },
  };
  packageRevisions.set(packageRevisionId, detail);
  releaseCommands.set(commandKey, detail);
  return { schemaVersion: 1, created: true, detail };
}

/** Project one frozen detail into the bounded release page shape. */
function packageRevisionPage(draftId) {
  const items = [...packageRevisions.values()]
    .filter((detail) => detail.packageRevision.draftId === draftId)
    .map((detail) => {
      const packageRevision = detail.packageRevision;
      return {
        packageRevisionId: packageRevision.packageRevisionId,
        authoringRevisionId: packageRevision.authoringRevisionId,
        validationAttestationId: packageRevision.validationAttestationId,
        packageIdentity: packageRevision.packageIdentity,
        packageContentIdentity: packageRevision.packageContentIdentity,
        closureIdentity: packageRevision.closureIdentity,
        memberCount: packageRevision.members.length,
        createdAt: packageRevision.createdAt,
        detailLink:
          `/api/studio/benchmark-authoring/drafts/${draftId}`
          + `/package-revisions/${packageRevision.packageRevisionId}`,
        publication: publications.get(packageRevision.packageRevisionId) ?? null,
        packageExport: packageExports.get(packageRevision.packageRevisionId)?.descriptor ?? null,
      };
    })
    .reverse();
  return { schemaVersion: 1, items, nextCursor: null };
}

/** Create or replay one managed Catalog publication fixture. */
function publishPackage(detail, command) {
  const packageRevision = detail.packageRevision;
  const existing = publications.get(packageRevision.packageRevisionId);
  if (existing) return { schemaVersion: 1, created: false, publication: existing };
  const publication = {
    schemaVersion: 1,
    publicationId: opaqueId("benchmark-package-publication", publications.size + 1),
    draftId: packageRevision.draftId,
    packageRevisionId: packageRevision.packageRevisionId,
    validationAttestationId: packageRevision.validationAttestationId,
    packageIdentity: packageRevision.packageIdentity,
    packageContentIdentity: packageRevision.packageContentIdentity,
    closureIdentity: packageRevision.closureIdentity,
    catalogEntryId: opaqueId("benchmark-entry", publications.size + 16),
    sourceId: "studio-managed-benchmark-publications",
    sourceKind: "catalog",
    createdAt: Date.now(),
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
  publications.set(packageRevision.packageRevisionId, publication);
  releaseCommands.set(`publish:${command.clientRequestId}`, publication);
  forbiddenBoundaryCalls.releasePublication += 1;
  return { schemaVersion: 1, created: true, publication };
}

/** Create or replay one deterministic browser-owned Package export fixture. */
function exportPackage(detail, command) {
  const packageRevision = detail.packageRevision;
  const existing = packageExports.get(packageRevision.packageRevisionId);
  if (existing) return { schemaVersion: 1, created: false, packageExport: existing.descriptor };
  const exportId = opaqueId("benchmark-package-export", packageExports.size + 1);
  const bytes = Buffer.concat([Buffer.from("PK\x03\x04"), Buffer.alloc(124, 0)]);
  const digest = `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
  const descriptor = {
    schemaVersion: 1,
    exportId,
    draftId: packageRevision.draftId,
    packageRevisionId: packageRevision.packageRevisionId,
    validationAttestationId: packageRevision.validationAttestationId,
    packageIdentity: packageRevision.packageIdentity,
    packageContentIdentity: packageRevision.packageContentIdentity,
    closureIdentity: packageRevision.closureIdentity,
    exportContractVersion: "studio-benchmark-package-zip-v1",
    memberCount: packageRevision.members.length,
    archiveMediaType: "application/zip",
    filename: `benchmark-package-${packageRevision.packageRevisionId.slice(-32)}.zip`,
    size: bytes.byteLength,
    sha256: digest,
    contentLink:
      `/api/studio/benchmark-authoring/drafts/${packageRevision.draftId}`
      + `/package-revisions/${packageRevision.packageRevisionId}`
      + `/exports/${exportId}/content`,
    availability: "available",
    createdAt: Date.now(),
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
  packageExports.set(packageRevision.packageRevisionId, { descriptor, bytes });
  releaseCommands.set(`export:${command.clientRequestId}`, descriptor);
  forbiddenBoundaryCalls.packageExport += 1;
  return { schemaVersion: 1, created: true, packageExport: descriptor };
}

/** Return one bounded Agent candidate page without constructing Agent code. */
function agentPage() {
  return {
    schemaVersion: 1,
    items: [
      {
        agentId: ANALYSIS_AGENT_ID,
        name: "No-device analysis fixture",
        currentRevisionId: ANALYSIS_AGENT_REVISION_ID,
        createdAt: 1,
        updatedAt: 1,
      },
      {
        agentId: "agent-without-current-revision",
        name: "Unsaved Agent candidate",
        currentRevisionId: null,
        createdAt: 1,
        updatedAt: 1,
      },
    ],
    nextCursor: null,
  };
}

/**
 * Build one strict partial or valid revision-bound validation projection.
 *
 * Args:
 *   item: In-memory durable draft and current immutable revision.
 *   body: Exact schema-1 browser request.
 *
 * Returns:
 *   A bounded no-execution validation envelope for browser acceptance.
 */
function validationResult(item, body) {
  const valid = item.revision.document.manifest.document.title.includes("Ready");
  return {
    schemaVersion: 1,
    mode: "validation",
    draftId: item.draft.draftId,
    revisionId: item.revision.revisionId,
    documentFingerprint: item.revision.documentFingerprint,
    split: body.split,
    valid,
    identities: {
      package: "fixture/browser-fixture@0.1.0",
      packageContent: HASH,
      benchmarkPlan: valid ? `sha256:${"b".repeat(64)}` : null,
      experimentProtocol: valid ? `sha256:${"c".repeat(64)}` : null,
    },
    diagnostics: valid ? [] : [
      {
        code: "benchmark.manifest.title_fixture",
        message: "Rename this fixture title to include Ready before validation.",
        severity: "error",
        memberKind: "manifest",
        memberPath: "benchmark.yaml",
        fieldPath: ["title"],
        taskId: null,
        resourceId: null,
        agentId: null,
        revisionId: null,
      },
    ],
    diagnosticsTruncated: false,
    unverifiedChecks: ["plugin-availability"],
    executionEvidence: false,
  };
}

/**
 * Build one complete bounded deterministic plan without entering runtime.
 *
 * Args:
 *   item: In-memory durable draft and current immutable revision.
 *   body: Exact task scope and frozen Agent revision selection.
 *
 * Returns:
 *   A complete deterministic schedule and explicit unverified facts.
 */
function dryRunResult(item, body) {
  const tasks = body.taskIds.length > 0 ? body.taskIds : ["browser-task"];
  const schedule = [];
  for (let repeat = 0; repeat < 60; repeat += 1) {
    for (const taskId of tasks) {
      for (const agent of body.agentRevisions) {
        schedule.push({
          repeat,
          taskId,
          agentId: agent.agentId,
          seed: 17 + repeat,
          sharedInstanceKey: `${taskId}:${repeat}`,
        });
      }
    }
  }
  return {
    schemaVersion: 1,
    mode: "side-effect-free-dry-run",
    draftId: item.draft.draftId,
    revisionId: item.revision.revisionId,
    documentFingerprint: item.revision.documentFingerprint,
    split: body.split,
    ok: true,
    identities: {
      package: "fixture/browser-fixture@0.1.0",
      packageContent: HASH,
      benchmarkPlan: `sha256:${"b".repeat(64)}`,
      experimentProtocol: `sha256:${"c".repeat(64)}`,
    },
    agentRevisions: body.agentRevisions.map((agent) => ({
      ...agent,
      agentGraphIdentity: ANALYSIS_GRAPH_IDENTITY,
    })),
    schedule,
    budget: {
      maxInteractions: 20,
      maxActivations: 30,
      timeoutSeconds: 300,
      tokenLimit: null,
      requireObservableTokens: false,
    },
    fairnessWarnings: ["Definition-level ordering is not runtime fairness proof."],
    outputLayout: {
      experimentReport: "<artifact-root>/<experiment-id>/experiment-report.json",
      runReport: "<artifact-root>/<experiment-id>/runs/<task-run-id>/run-report.json",
      trajectory: "<artifact-root>/<experiment-id>/runs/<task-run-id>/trajectory.jsonl",
      bundle: "<artifact-root>/<experiment-id>/trajectory-bundle.zip",
    },
    unverifiedChecks: ["current-worker-cardinality", "dynamic-materialization"],
    diagnostics: [],
    diagnosticsTruncated: false,
    executionEvidence: false,
  };
}

/**
 * Build one bounded disposable Contract Test result selected by fixture seed.
 *
 * Args:
 *   item: In-memory draft and exact current immutable revision.
 *   body: Strict browser command containing split, seed, and profile identity.
 *
 * Returns:
 *   Passing, failed, skipped, or mixed fake-fixture facts for browser QA.
 */
function contractTestResult(item, body) {
  const passed = {
    caseId: `sha256:${"5".repeat(64)}`,
    taskId: "browser-task",
    kind: "evaluator",
    logicalName: "file_exist",
    memberPath: "tasks/test.json",
    fieldPath: [0, "evaluator"],
    phase: "evaluation",
    seed: 101,
    status: "passed",
    fixtureId: "studio.file_exist",
    fixtureVersion: "1.0.0",
    checks: ["determinism", "serialization"],
    skipped: [],
    diagnostics: [],
  };
  const failed = {
    ...passed,
    caseId: `sha256:${"6".repeat(64)}`,
    logicalName: "contains",
    status: "failed",
    fixtureId: "studio.contains",
    diagnostics: [{
      code: "benchmark.ctk.output_not_deterministic",
      message: "Evaluator fake fixture failed (_FixtureContractFailure).",
      memberKind: "task",
      memberPath: "tasks/test.json",
      fieldPath: [0, "evaluator"],
      taskId: "browser-task",
    }],
  };
  const skipped = {
    ...passed,
    caseId: `sha256:${"7".repeat(64)}`,
    kind: "environment",
    logicalName: "third_party_setup",
    fieldPath: [0, "environment_initializer", 0],
    phase: "setup",
    seed: 202,
    status: "skipped",
    fixtureId: null,
    fixtureVersion: null,
    checks: [],
    skipped: ["fixture:not-registered"],
    diagnostics: [{
      code: "benchmark.ctk.fixture_missing",
      message: "No explicit environment fake fixture is registered.",
      memberKind: "task",
      memberPath: "tasks/test.json",
      fieldPath: [0, "environment_initializer", 0],
      taskId: "browser-task",
    }],
  };
  const cases = body.seed === 1
    ? [passed]
    : body.seed === 2
      ? [failed]
      : body.seed === 3
        ? [skipped]
        : [passed, skipped];
  const counts = {
    passed: cases.filter((entry) => entry.status === "passed").length,
    failed: cases.filter((entry) => entry.status === "failed").length,
    skipped: cases.filter((entry) => entry.status === "skipped").length,
  };
  const requestFingerprint = `sha256:${createHash("sha256")
    .update(JSON.stringify(body))
    .digest("hex")}`;
  return {
    schemaVersion: 1,
    mode: "fake-fixture",
    draftId: item.draft.draftId,
    revisionId: item.revision.revisionId,
    documentFingerprint: item.revision.documentFingerprint,
    requestFingerprint,
    split: body.split,
    seed: body.seed,
    profile: CONTRACT_PROFILE,
    identities: {
      package: "fixture/browser-fixture@0.1.0",
      packageContent: HASH,
      benchmarkPlan: `sha256:${"b".repeat(64)}`,
      experimentProtocol: `sha256:${"c".repeat(64)}`,
    },
    validDefinition: true,
    coverage: {
      total: cases.length,
      ...counts,
      complete: counts.skipped === 0,
      executedChecksPassed: counts.failed === 0,
    },
    cases,
    preconditionDiagnostics: [],
    diagnosticsTruncated: false,
    safety: {
      fixtureExecution: true,
      packageCodeExecuted: false,
      realDeviceEvidence: false,
      processSandbox: false,
      deviceCapability: false,
      modelCapability: false,
      networkCapability: false,
      secretCapability: false,
      runtimeCapability: false,
      experimentCapability: false,
      outputPathCapability: false,
      benchmarkExecution: false,
      agentExecution: false,
      publicationEligibility: false,
      resultPersisted: false,
    },
  };
}

/** Handle all Stage 5.5A authoring and Catalog fixture endpoints. */
async function handleApi(request, response, url) {
  if (request.method === "GET" && url.pathname === "/studio/agents") {
    sendJson(response, 200, agentPage());
    return true;
  }
  if (
    request.method === "GET"
    && url.pathname === "/studio/benchmark-authoring/fixture-canaries"
  ) {
    sendJson(response, 200, {
      schemaVersion: 1,
      forbiddenBoundaryCalls,
    });
    return true;
  }
  if (
    request.method === "GET"
    && url.pathname === "/studio/benchmark-authoring/contract-test-profiles"
  ) {
    sendJson(response, 200, { schemaVersion: 1, profiles: [CONTRACT_PROFILE] });
    return true;
  }
  if (request.method === "GET" && url.pathname === "/studio/benchmarks") {
    sendJson(response, 200, catalogPage());
    return true;
  }
  if (
    url.pathname === "/studio/benchmark-authoring/drafts"
    && request.method === "GET"
  ) {
    sendJson(response, 200, {
      schemaVersion: 1,
      items: [...drafts.values()].map((item) => item.draft).reverse(),
      nextCursor: null,
    });
    return true;
  }
  if (
    url.pathname === "/studio/benchmark-authoring/drafts"
    && request.method === "POST"
  ) {
    const body = await readJson(request);
    if (
      body.name.includes("Retry")
      && !retryAttempts.has(body.clientRequestId)
    ) {
      retryAttempts.add(body.clientRequestId);
      sendError(
        response,
        503,
        "benchmark.authoring.fixture_uncertain",
        "Injected uncertain create response",
      );
      return true;
    }
    const source = body.source;
    const template = source.kind === "template" ? source.template : null;
    const created = createDraft(
      body.name,
      initialDocument(
        source.kind === "template" ? source.packageName : "catalog-copy",
      ),
      source.kind === "template"
        ? {
            sourceKind: "template",
            templateName: template,
            catalogEntryId: null,
            catalogSnapshotIdentity: null,
            packageIdentity: `${source.publisher}/${source.packageName}@${source.version}`,
            sourceFingerprint: null,
          }
        : {
            sourceKind: "catalog",
            templateName: null,
            catalogEntryId: source.catalogEntryId,
            catalogSnapshotIdentity: HASH,
            packageIdentity: "fixture/browser-fixture@0.1.0",
            sourceFingerprint: `sha256:${"1".repeat(64)}`,
          },
    );
    sendJson(response, 201, created);
    return true;
  }

  const packageCollectionMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/package-revisions$/.exec(
    url.pathname,
  );
  if (packageCollectionMatch && request.method === "GET") {
    sendJson(response, 200, packageRevisionPage(packageCollectionMatch[1]));
    return true;
  }
  if (packageCollectionMatch && request.method === "POST") {
    const item = drafts.get(packageCollectionMatch[1]);
    if (!item) {
      sendError(response, 404, "benchmark.authoring.not_found", "Draft not found");
      return true;
    }
    const command = await readJson(request);
    if (command.revisionId !== item.revision.revisionId) {
      sendError(
        response,
        409,
        "benchmark.authoring.freeze_revision_conflict",
        "Current authoring revision changed",
        item.revision.revisionId,
      );
      return true;
    }
    const result = freezePackage(item, command);
    sendJson(response, result.created ? 201 : 200, result);
    return true;
  }

  const packageDetailMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/package-revisions\/(benchmark-package-revision-[a-f0-9]{32})$/.exec(
    url.pathname,
  );
  if (packageDetailMatch && request.method === "GET") {
    const detail = packageRevisions.get(packageDetailMatch[2]);
    if (!detail || detail.packageRevision.draftId !== packageDetailMatch[1]) {
      sendError(response, 404, "benchmark.authoring.not_found", "Package not found");
    } else {
      sendJson(response, 200, detail);
    }
    return true;
  }

  const publicationCollectionMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/package-revisions\/(benchmark-package-revision-[a-f0-9]{32})\/publications$/.exec(
    url.pathname,
  );
  if (publicationCollectionMatch && request.method === "POST") {
    const detail = packageRevisions.get(publicationCollectionMatch[2]);
    if (!detail || detail.packageRevision.draftId !== publicationCollectionMatch[1]) {
      sendError(response, 404, "benchmark.authoring.not_found", "Package not found");
      return true;
    }
    const result = publishPackage(detail, await readJson(request));
    sendJson(response, result.created ? 201 : 200, result);
    return true;
  }
  const publicationDetailMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/package-revisions\/(benchmark-package-revision-[a-f0-9]{32})\/publications\/(benchmark-package-publication-[a-f0-9]{32})$/.exec(
    url.pathname,
  );
  if (publicationDetailMatch && request.method === "GET") {
    const publication = publications.get(publicationDetailMatch[2]);
    if (
      !publication
      || publication.draftId !== publicationDetailMatch[1]
      || publication.publicationId !== publicationDetailMatch[3]
    ) {
      sendError(response, 404, "benchmark.authoring.not_found", "Publication not found");
    } else {
      sendJson(response, 200, publication);
    }
    return true;
  }

  const exportCollectionMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/package-revisions\/(benchmark-package-revision-[a-f0-9]{32})\/exports$/.exec(
    url.pathname,
  );
  if (exportCollectionMatch && request.method === "POST") {
    const detail = packageRevisions.get(exportCollectionMatch[2]);
    if (!detail || detail.packageRevision.draftId !== exportCollectionMatch[1]) {
      sendError(response, 404, "benchmark.authoring.not_found", "Package not found");
      return true;
    }
    const result = exportPackage(detail, await readJson(request));
    sendJson(response, result.created ? 201 : 200, result);
    return true;
  }
  const exportDetailMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/package-revisions\/(benchmark-package-revision-[a-f0-9]{32})\/exports\/(benchmark-package-export-[a-f0-9]{32})$/.exec(
    url.pathname,
  );
  if (exportDetailMatch && request.method === "GET") {
    const stored = packageExports.get(exportDetailMatch[2]);
    if (
      !stored
      || stored.descriptor.draftId !== exportDetailMatch[1]
      || stored.descriptor.exportId !== exportDetailMatch[3]
    ) {
      sendError(response, 404, "benchmark.authoring.not_found", "Export not found");
    } else {
      sendJson(response, 200, stored.descriptor);
    }
    return true;
  }
  const exportContentMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/package-revisions\/(benchmark-package-revision-[a-f0-9]{32})\/exports\/(benchmark-package-export-[a-f0-9]{32})\/content$/.exec(
    url.pathname,
  );
  if (exportContentMatch && (request.method === "GET" || request.method === "HEAD")) {
    const stored = packageExports.get(exportContentMatch[2]);
    if (
      !stored
      || stored.descriptor.draftId !== exportContentMatch[1]
      || stored.descriptor.exportId !== exportContentMatch[3]
    ) {
      sendError(response, 404, "benchmark.authoring.not_found", "Export not found");
    } else {
      sendArchive(request, response, stored.descriptor, stored.bytes);
    }
    return true;
  }

  const detailMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})$/.exec(
    url.pathname,
  );
  if (request.method === "GET" && detailMatch) {
    const item = drafts.get(detailMatch[1]);
    if (!item) {
      sendError(response, 404, "benchmark.authoring.not_found", "Draft not found");
    } else {
      sendJson(response, 200, {
        schemaVersion: 1,
        draft: item.draft,
        currentRevision: item.revision,
      });
    }
    return true;
  }

  const analysisMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/(validate|dry-run)$/.exec(
    url.pathname,
  );
  if (request.method === "POST" && analysisMatch) {
    const [, draftId, operation] = analysisMatch;
    const item = drafts.get(draftId);
    if (!item) {
      sendError(response, 404, "benchmark.authoring.not_found", "Draft not found");
      return true;
    }
    const body = await readJson(request);
    if (body.revisionId !== item.revision.revisionId || body.split === "stale") {
      sendError(
        response,
        409,
        "benchmark.authoring.revision_conflict",
        "Injected exact-current analysis conflict",
        item.revision.revisionId,
      );
      return true;
    }
    if (body.split === "too-large") {
      sendError(
        response,
        413,
        "benchmark.authoring.analysis_capacity",
        "Injected bounded analysis capacity failure",
      );
      return true;
    }
    if (body.split === "delayed") {
      await new Promise((resolve) => setTimeout(resolve, 750));
    }
    sendJson(
      response,
      200,
      operation === "validate"
        ? validationResult(item, body)
        : dryRunResult(item, body),
    );
    return true;
  }

  const contractTestMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/contract-tests$/.exec(
    url.pathname,
  );
  if (request.method === "POST" && contractTestMatch) {
    const item = drafts.get(contractTestMatch[1]);
    if (!item) {
      sendError(response, 404, "benchmark.authoring.not_found", "Draft not found");
      return true;
    }
    const body = await readJson(request);
    if (body.revisionId !== item.revision.revisionId || body.seed === 409) {
      sendError(
        response,
        409,
        "benchmark.authoring.analysis_revision_stale",
        "Injected exact-current Contract Test conflict",
        item.revision.revisionId,
      );
      return true;
    }
    if (body.seed === 413) {
      sendError(
        response,
        413,
        "benchmark.authoring.contract_test_too_large",
        "Injected Contract Test capacity failure",
      );
      return true;
    }
    if (body.seed === 911) {
      await new Promise((resolve) => setTimeout(resolve, 750));
    }
    sendJson(response, 200, contractTestResult(item, body));
    return true;
  }

  const saveMatch = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/revisions$/.exec(
    url.pathname,
  );
  if (request.method === "POST" && saveMatch) {
    const item = drafts.get(saveMatch[1]);
    if (!item) {
      sendError(response, 404, "benchmark.authoring.not_found", "Draft not found");
      return true;
    }
    const body = await readJson(request);
    if (body.document.manifest.document.title === "Conflict Title") {
      sendError(
        response,
        409,
        "benchmark.authoring.revision_conflict",
        "Injected safe revision conflict",
        item.revision.revisionId,
      );
      return true;
    }
    if (body.baseRevisionId !== item.revision.revisionId) {
      sendError(
        response,
        409,
        "benchmark.authoring.revision_conflict",
        "Current revision changed",
        item.revision.revisionId,
      );
      return true;
    }
    const next = revision(
      item.draft.draftId,
      body.document,
      {
        sourceKind: "edit",
        templateName: null,
        catalogEntryId: null,
        catalogSnapshotIdentity: null,
        packageIdentity: null,
        sourceFingerprint: null,
      },
      item.revision.revisionId,
    );
    item.revision = next;
    item.revisions.set(next.revisionId, next);
    item.draft = {
      ...item.draft,
      currentRevisionId: next.revisionId,
      updatedAt: next.createdAt,
    };
    sendJson(response, 201, {
      schemaVersion: 1,
      created: true,
      draft: item.draft,
      revision: next,
    });
    return true;
  }

  const contentAction = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/resources\/([a-z][a-z0-9_.-]{0,127})\/(upload|replace|remove)$/.exec(
    url.pathname,
  );
  if (request.method === "POST" && contentAction) {
    const [, draftId, resourceId, operation] = contentAction;
    const item = drafts.get(draftId);
    if (!item) {
      sendError(response, 404, "benchmark.authoring.not_found", "Draft not found");
      return true;
    }
    const clientRequestId = url.searchParams.get("clientRequestId") ?? "";
    const baseRevisionId = url.searchParams.get("baseRevisionId") ?? "";
    const commandKey = `${draftId}:${clientRequestId}`;
    const existingCommand = contentCommands.get(commandKey);
    if (existingCommand) {
      sendJson(response, 200, {
        ...existingCommand,
        created: false,
        draft: item.draft,
      });
      return true;
    }
    if (resourceId === "conflict-asset" || baseRevisionId !== item.revision.revisionId) {
      sendError(
        response,
        409,
        "benchmark.authoring.content_conflict",
        "Injected safe managed-content conflict",
        item.revision.revisionId,
      );
      return true;
    }
    const currentResources = item.revision.document.resources;
    const existing = currentResources.find((resource) => resource.id === resourceId);
    let resource = null;
    let removedResourceId = null;
    let resources;
    if (operation === "upload") {
      if (existing) {
        sendError(response, 409, "benchmark.authoring.resource_exists", "Resource already exists");
        return true;
      }
      const bytes = await readRaw(request);
      resource = managedResource({
        id: resourceId,
        kind: url.searchParams.get("kind"),
        path: url.searchParams.get("path"),
        mediaType: request.headers["content-type"] ?? "application/octet-stream",
        bytes,
      });
      resources = [...currentResources, resource];
    } else if (operation === "replace") {
      if (!existing) {
        sendError(response, 404, "benchmark.authoring.resource_not_found", "Resource not found");
        return true;
      }
      const bytes = await readRaw(request);
      resource = managedResource({
        id: existing.id,
        kind: existing.kind,
        path: existing.path,
        mediaType: request.headers["content-type"] ?? existing.mediaType,
        bytes,
      });
      resources = currentResources.map((candidate) =>
        candidate.id === resourceId ? resource : candidate);
    } else {
      if (!existing) {
        sendError(response, 404, "benchmark.authoring.resource_not_found", "Resource not found");
        return true;
      }
      await readRaw(request, 0);
      removedResourceId = resourceId;
      resources = currentResources.filter((candidate) => candidate.id !== resourceId);
    }
    const commandRevision = applyResourceRevision(item, resources);
    const result = contentResult(
      item,
      operation,
      true,
      commandRevision,
      resource,
      removedResourceId,
    );
    contentCommands.set(commandKey, result);
    if (resourceId === "retry-asset") {
      // Commit the command, advance current once more, then make the first
      // response uncertain. The exact retry is therefore historical.
      applyResourceRevision(item, item.revision.document.resources);
      sendError(
        response,
        503,
        "benchmark.authoring.fixture_uncertain",
        "Injected committed-but-uncertain managed-content response",
      );
      return true;
    }
    sendJson(response, 201, result);
    return true;
  }

  const resourceContent = /^\/studio\/benchmark-authoring\/drafts\/(benchmark-draft-[a-f0-9]{32})\/revisions\/(benchmark-authoring-revision-[a-f0-9]{32})\/resources\/([a-z][a-z0-9_.-]{0,127})\/content$/.exec(
    url.pathname,
  );
  if (request.method === "HEAD" && resourceContent) {
    const [, draftId, revisionId, resourceId] = resourceContent;
    const item = drafts.get(draftId);
    const revisionValue = item?.revisions.get(revisionId);
    const resource = revisionValue?.document.resources.find(
      (candidate) => candidate.id === resourceId,
    );
    const bytes = resource ? managedContent.get(resource.contentIdentity) : null;
    if (!resource || !bytes) {
      sendError(response, 404, "benchmark.authoring.content_missing", "Managed content missing");
      return true;
    }
    response.writeHead(200, {
      "Content-Type": resource.mediaType,
      "Content-Length": String(resource.size),
      "Content-Disposition": `attachment; filename="${resource.id}"`,
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    });
    response.end();
    return true;
  }
  return false;
}

/** Resolve a safe static build asset or the SPA fallback. */
function staticPath(pathname) {
  const candidate = normalize(
    join(DIST, pathname === "/" ? "index.html" : pathname.slice(1)),
  );
  if (!candidate.startsWith(DIST)) return join(DIST, "index.html");
  if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  return join(DIST, "index.html");
}

/** Return one common static content type for the built application. */
function contentType(path) {
  return (
    {
      ".html": "text/html; charset=utf-8",
      ".js": "text/javascript; charset=utf-8",
      ".css": "text/css; charset=utf-8",
      ".svg": "image/svg+xml",
      ".png": "image/png",
    }[extname(path)] ?? "application/octet-stream"
  );
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", `http://127.0.0.1:${PORT}`);
    const apiUrl = new URL(url);
    if (apiUrl.pathname.startsWith("/api/studio/")) {
      apiUrl.pathname = apiUrl.pathname.slice("/api".length);
    }
    if (await handleApi(request, response, apiUrl)) return;
    if (url.pathname.startsWith("/studio/")) {
      sendError(response, 404, "studio.http.not_found", "Fixture route not found");
      return;
    }
    const path = staticPath(url.pathname);
    response.writeHead(200, {
      "Content-Type": contentType(path),
      "Cache-Control": "no-store",
    });
    createReadStream(path).pipe(response);
  } catch (error) {
    sendError(
      response,
      500,
      "benchmark.authoring.fixture_failed",
      error instanceof Error ? error.message : "Fixture failed",
    );
  }
});

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(
    `Benchmark authoring no-device fixture: http://127.0.0.1:${PORT}/benchmark-authoring\n`
    + `Seed draft: ${seeded.draft.draftId}\n`,
  );
});

/** Close the local fixture server cleanly after browser verification. */
function closeServer() {
  server.close(() => process.exit(0));
}

process.on("SIGINT", closeServer);
process.on("SIGTERM", closeServer);
