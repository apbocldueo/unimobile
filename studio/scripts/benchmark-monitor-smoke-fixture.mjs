import { createServer } from "node:http";

const PORT = Number(process.env.ZHIXING_STUDIO_FIXTURE_PORT ?? "8765");
const HASH = `sha256:${"c".repeat(64)}`;
const TASK_RUN_ID = `task-run-${"b".repeat(32)}`;
const CORE_TASK_RUN_ID = "f".repeat(32);
const REPORT_ARTIFACT_ID = `artifact-${"f".repeat(32)}`;
const REPLAY_ID = `benchmark-replay-${"d".repeat(32)}`;
const TEXT_PREVIEW_MAX_BYTES = 2 * 1024 * 1024;
const EXPORT_ARTIFACT_IDS = Object.freeze({
  report: `artifact-${"a".repeat(32)}`,
  bundle: `artifact-${"b".repeat(32)}`,
  manifest: `artifact-${"c".repeat(32)}`,
  trajectory: `artifact-${"d".repeat(32)}`,
});

/** Compute one ZIP-compatible CRC-32 for deterministic fixture bytes. */
function fixtureCrc32(body) {
  let value = 0xffffffff;
  for (const byte of body) {
    value ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value >>> 1) ^ (value & 1 ? 0xedb88320 : 0);
    }
  }
  return (value ^ 0xffffffff) >>> 0;
}

/** Build one valid uncompressed single-member ZIP without runtime dependencies. */
function storedFixtureZip(filename, body) {
  const name = Buffer.from(filename);
  const crc = fixtureCrc32(body);
  const local = Buffer.alloc(30);
  local.writeUInt32LE(0x04034b50, 0);
  local.writeUInt16LE(20, 4);
  local.writeUInt32LE(crc, 14);
  local.writeUInt32LE(body.byteLength, 18);
  local.writeUInt32LE(body.byteLength, 22);
  local.writeUInt16LE(name.byteLength, 26);
  const central = Buffer.alloc(46);
  central.writeUInt32LE(0x02014b50, 0);
  central.writeUInt16LE(20, 4);
  central.writeUInt16LE(20, 6);
  central.writeUInt32LE(crc, 16);
  central.writeUInt32LE(body.byteLength, 20);
  central.writeUInt32LE(body.byteLength, 24);
  central.writeUInt16LE(name.byteLength, 28);
  const centralOffset = local.byteLength + name.byteLength + body.byteLength;
  const centralSize = central.byteLength + name.byteLength;
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(1, 8);
  end.writeUInt16LE(1, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(centralOffset, 16);
  return Buffer.concat([local, name, body, central, name, end]);
}

const EXPORT_BUNDLE_BODY = storedFixtureZip(
  "bounded-no-device-evidence.bin",
  Buffer.alloc(4 * 1024 * 1024, 0x5a),
);
const EXPORT_TRAJECTORY_BODY = Buffer.from(
  `${JSON.stringify({
    schema_version: "1.0",
    task_run_id: CORE_TASK_RUN_ID,
    sequence: 1,
    kind: "task.completed",
  })}\n`,
);

/** Build one stable opaque artifact identity from a small fixture ordinal. */
function evidenceArtifactId(ordinal) {
  return `artifact-${ordinal.toString(16).padStart(32, "0")}`;
}

const PNG_ONE_PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
  + "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);
const EVIDENCE_CASES = Object.freeze([
  {
    artifactId: evidenceArtifactId(1),
    reference: "evidence/result.json",
    kind: "fixture.json",
    availability: "available",
    contentType: "application/json",
    body: Buffer.from('{"matched":true,"markup":"<script>inert</script>"}'),
  },
  {
    artifactId: evidenceArtifactId(2),
    reference: "evidence/events.ndjson",
    kind: "fixture.ndjson",
    availability: "available",
    contentType: "application/x-ndjson",
    body: Buffer.from('{"sequence":1}\n\n{"sequence":2}\n'),
  },
  {
    artifactId: evidenceArtifactId(3),
    reference: "evidence/source.xml",
    kind: "fixture.xml",
    availability: "available",
    contentType: "application/xml",
    body: Buffer.from("<root><![CDATA[<script>inert</script>]]>&entity;</root>"),
  },
  {
    artifactId: evidenceArtifactId(4),
    reference: "evidence/notes.txt",
    kind: "fixture.text",
    availability: "available",
    contentType: "text/plain",
    body: Buffer.from("line one\n/path-shaped inert text\n<script>inert</script>"),
  },
  {
    artifactId: evidenceArtifactId(5),
    reference: "evidence/screenshot.png",
    kind: "fixture.png",
    availability: "available",
    contentType: "image/png",
    body: PNG_ONE_PIXEL,
  },
  {
    artifactId: evidenceArtifactId(6),
    reference: "evidence/archive.zip",
    kind: "fixture.zip",
    availability: "available",
    contentType: "application/zip",
    body: Buffer.from("PK\u0005\u0006".padEnd(22, "\u0000"), "binary"),
  },
  {
    artifactId: evidenceArtifactId(7),
    reference: "evidence/redacted.json",
    kind: "fixture.redacted",
    availability: "redacted",
    contentType: "application/json",
    body: Buffer.from('{"value":"<redacted>"}'),
  },
  {
    artifactId: evidenceArtifactId(8),
    reference: "evidence/truncated.txt",
    kind: "fixture.truncated",
    availability: "truncated",
    contentType: "text/plain",
    body: Buffer.from("bounded prefix only"),
  },
  ...[
    "pending",
    "not_produced",
    "excluded",
    "missing",
    "corrupt",
    "failed",
  ].map((availability, index) => ({
    artifactId: evidenceArtifactId(9 + index),
    reference: `evidence/${availability}.txt`,
    kind: `fixture.${availability}`,
    availability,
    contentType: "",
    body: null,
  })),
  {
    artifactId: evidenceArtifactId(15),
    reference: "evidence/duplicate.json",
    kind: "fixture.duplicate-a",
    availability: "available",
    contentType: "application/json",
    body: Buffer.from('{"duplicate":"a"}'),
  },
  {
    artifactId: evidenceArtifactId(16),
    reference: "evidence/duplicate.json",
    kind: "fixture.duplicate-b",
    availability: "available",
    contentType: "application/json",
    body: Buffer.from('{"duplicate":"b"}'),
  },
  {
    artifactId: evidenceArtifactId(17),
    reference: "evidence/oversized.txt",
    kind: "fixture.oversized",
    availability: "available",
    contentType: "text/plain",
    body: null,
    descriptorSize: TEXT_PREVIEW_MAX_BYTES + 1,
  },
  {
    artifactId: evidenceArtifactId(18),
    reference: "evidence/mime-mismatch.txt",
    kind: "fixture.mime-mismatch",
    availability: "available",
    contentType: "text/plain",
    responseContentType: "application/json",
    body: Buffer.from("mismatched media"),
  },
  {
    artifactId: evidenceArtifactId(19),
    reference: "evidence/partial.txt",
    kind: "fixture.partial",
    availability: "available",
    contentType: "text/plain",
    body: Buffer.from("short"),
    descriptorSize: 10,
  },
]);

/** Build exact bounded managed bodies used by the Export browser journey. */
function exportArtifactCases(experimentId) {
  const reportBody = Buffer.from(JSON.stringify(
    experimentReport(experimentId, "report-ready"),
  ));
  const manifestBody = Buffer.from(JSON.stringify({
    schemaVersion: 1,
    kind: "studio_benchmark_publication_manifest",
    experimentId,
    taskRunId: TASK_RUN_ID,
    members: [
      {
        reference: "experiment-report.json",
        kind: "experiment_report",
        contentType: "application/json",
        size: reportBody.byteLength,
        sha256: HASH,
        scope: { experimentId },
        availability: "available",
        exclusionReason: "",
      },
      {
        reference: `runs/${CORE_TASK_RUN_ID}/trajectory.jsonl`,
        kind: "task_trajectory",
        contentType: "application/x-ndjson",
        size: EXPORT_TRAJECTORY_BODY.byteLength,
        sha256: HASH,
        scope: { experimentId, taskRunId: TASK_RUN_ID },
        availability: "available",
        exclusionReason: "",
      },
    ],
    excludedEvidence: [
      {
        kind: "prompt",
        availability: "hidden",
        reason: "hidden_by_default_policy",
      },
    ],
  }));
  return [
    {
      artifactId: EXPORT_ARTIFACT_IDS.report,
      taskRunId: null,
      reference: "experiment-report.json",
      kind: "experiment_report",
      contentType: "application/json",
      body: reportBody,
    },
    {
      artifactId: EXPORT_ARTIFACT_IDS.bundle,
      taskRunId: null,
      reference: "studio-experiment-bundle.zip",
      kind: "experiment_bundle",
      contentType: "application/zip",
      body: EXPORT_BUNDLE_BODY,
    },
    {
      artifactId: EXPORT_ARTIFACT_IDS.manifest,
      taskRunId: null,
      reference: "studio-publication-manifest.json",
      kind: "studio_publication_manifest",
      contentType: "application/json",
      body: manifestBody,
    },
    {
      artifactId: EXPORT_ARTIFACT_IDS.trajectory,
      taskRunId: TASK_RUN_ID,
      reference: `runs/${CORE_TASK_RUN_ID}/trajectory.jsonl`,
      kind: "task_trajectory",
      contentType: "application/x-ndjson",
      body: EXPORT_TRAJECTORY_BODY,
    },
  ];
}
const IDS = Object.freeze({
  active: `experiment-${"1".repeat(32)}`,
  replayUnavailable: `experiment-${"2".repeat(32)}`,
  replayAvailable: `experiment-${"3".repeat(32)}`,
  notFound: `experiment-${"4".repeat(32)}`,
  cancellable: `experiment-${"5".repeat(32)}`,
  reconnecting: `experiment-${"6".repeat(32)}`,
  loading: `experiment-${"7".repeat(32)}`,
  integrityFrozen: `experiment-${"8".repeat(32)}`,
  reportReady: `experiment-${"9".repeat(32)}`,
  reportPending: `experiment-${"a".repeat(32)}`,
  reportFailed: `experiment-${"b".repeat(32)}`,
  reportCorrupt: `experiment-${"c".repeat(32)}`,
  taskReportMissing: `experiment-${"d".repeat(32)}`,
  nullEvaluation: `experiment-${"e".repeat(32)}`,
  comparisonMetrics: `experiment-${"f".repeat(32)}`,
});

const HISTORY_ROWS = Object.freeze([
  {
    experimentId: IDS.reportReady,
    acceptedAt: 500,
    catalogEntryId: "history-catalog-a",
    agentIds: ["fixture-agent"],
  },
  {
    experimentId: IDS.active,
    acceptedAt: 400,
    catalogEntryId: "history-catalog-a",
    agentIds: ["fixture-agent"],
  },
  {
    experimentId: IDS.reportPending,
    acceptedAt: 300,
    catalogEntryId: "history-catalog-a",
    agentIds: ["fixture-agent"],
  },
  {
    experimentId: IDS.comparisonMetrics,
    acceptedAt: 200,
    catalogEntryId: "synthetic-comparison-metrics-fixture",
    agentIds: [
      "synthetic-agent-a",
      "synthetic-agent-b",
      "synthetic-agent-c",
    ],
  },
  {
    experimentId: IDS.reportFailed,
    acceptedAt: 200,
    catalogEntryId: "deleted-history-catalog",
    agentIds: ["deleted-history-agent"],
  },
  {
    experimentId: IDS.cancellable,
    acceptedAt: 100,
    catalogEntryId: "history-catalog-b",
    agentIds: ["fixture-agent"],
  },
]);

const SYNTHETIC_COMPARISON_RUNS = Object.freeze([
  {
    taskRunId: `task-run-${"1".repeat(32)}`,
    coreTaskRunId: "1".repeat(32),
    artifactId: `artifact-${"1".repeat(32)}`,
    agentId: "synthetic-agent-a",
    revisionId: "synthetic-revision-a",
    taskId: "synthetic-shared-task",
    outcome: "pass",
  },
  {
    taskRunId: `task-run-${"2".repeat(32)}`,
    coreTaskRunId: "2".repeat(32),
    artifactId: `artifact-${"2".repeat(32)}`,
    agentId: "synthetic-agent-b",
    revisionId: "synthetic-revision-b",
    taskId: "synthetic-shared-task",
    outcome: "fail",
  },
  {
    taskRunId: `task-run-${"3".repeat(32)}`,
    coreTaskRunId: "3".repeat(32),
    artifactId: `artifact-${"3".repeat(32)}`,
    agentId: "synthetic-agent-c",
    revisionId: "synthetic-revision-c",
    taskId: "synthetic-invalid-task",
    outcome: "invalid",
  },
  {
    taskRunId: `task-run-${"4".repeat(32)}`,
    coreTaskRunId: "4".repeat(32),
    artifactId: `artifact-${"4".repeat(32)}`,
    agentId: "synthetic-agent-c",
    revisionId: "synthetic-revision-c",
    taskId: "synthetic-skipped-task",
    outcome: "skipped",
  },
]);

const reconnectAttempts = new Map();
const historyRetryAttempts = new Map();

/** Return the formal no-device protocol embedded in immutable fixture snapshots. */
function protocol() {
  return {
    schemaVersion: "1.0",
    seed: 42,
    repeats: 1,
    taskOrder: { strategy: "fixed" },
    taskMaterialization: {
      reuseAcrossAgents: true,
      strictFairness: false,
    },
    device: {
      platform: "android",
      locale: "en-US",
      orientation: "portrait",
      versionPolicy: "compatible",
    },
    apps: [],
    budget: {
      maxInteractions: 15,
      maxActivations: 200,
      timeoutSeconds: 600,
      requireObservableTokens: false,
    },
    isolation: {
      reset: "before_each_agent",
      cleanup: "after_each_run",
      requireVerifiedReset: true,
    },
    failure: {
      initializer: {
        outcome: "invalidate",
        continueSuite: true,
        preserveEvidence: true,
      },
      agent: {
        outcome: "evaluate_if_possible",
        continueSuite: true,
        preserveEvidence: true,
      },
      evaluator: {
        outcome: "invalidate",
        continueSuite: true,
        preserveEvidence: true,
      },
      cleanup: {
        outcome: "invalidate",
        continueSuite: true,
        preserveEvidence: true,
      },
    },
  };
}

/** Build one immutable definition snapshot with a static read-only graph. */
function definition(scenario = "single-agent") {
  const base = {
    schemaVersion: 1,
    previewFingerprint: HASH,
    snapshotFingerprint: HASH,
    source: {
      sourceId: "benchmark-monitor-smoke",
      sourceKind: "catalog",
      relativeKey: "no-device-fixture",
      catalogEntryId: "benchmark-monitor-smoke",
      packageIdentity: "smoke/no-device@1.0.0",
      packageContentIdentity: HASH,
      benchmarkPlanIdentity: HASH,
      experimentProtocolIdentity: HASH,
    },
    agentSnapshots: [
      {
        schemaVersion: 1,
        agentId: "fixture-agent",
        revisionId: "fixture-revision",
        contractVersion: "1.1",
        compileContractVersion: "studio-compile-v1",
        canonicalHash: HASH,
        agentGraph: {
          schemaVersion: "1.1",
          nodes: [
            {
              id: "observe",
              kind: "component",
              role: "observation_provider",
              lifecycle: "per_step",
              primary: true,
            },
          ],
          edges: [],
        },
        presentation: {},
        sourceMap: [],
        providerIdentities: [],
      },
    ],
    benchmarkPlan: {},
    protocol: protocol(),
    split: "test",
    taskIds: ["fixture-task"],
    schedule: [
      {
        plannedEntryId: "fixture-plan-entry",
        agentId: "fixture-agent",
        revisionId: "fixture-revision",
        taskId: "fixture-task",
        repeat: 0,
        order: 0,
        derivedSeed: 42,
        taskInstance: { availability: "template_only" },
      },
    ],
    deviceProfileId: "fake-no-device",
    executionLimits: {
      maxAgents: 1,
      maxSelectedTasks: 1,
      maxRepeats: 1,
      multiAgentComparison: false,
    },
  };
  if (scenario !== "comparison-metrics") return base;
  const agentSnapshots = ["a", "b", "c"].map((suffix) => ({
    ...structuredClone(base.agentSnapshots[0]),
    agentId: `synthetic-agent-${suffix}`,
    revisionId: `synthetic-revision-${suffix}`,
  }));
  return {
    ...base,
    source: {
      ...base.source,
      sourceId: "synthetic-comparison-metrics-fixture",
      relativeKey: "synthetic-comparison-metrics",
      catalogEntryId: "synthetic-comparison-metrics-fixture",
      packageIdentity: "fixture/synthetic-comparison-metrics@1.0.0",
    },
    agentSnapshots,
    taskIds: [
      "synthetic-shared-task",
      "synthetic-invalid-task",
      "synthetic-skipped-task",
    ],
    schedule: SYNTHETIC_COMPARISON_RUNS.map((run, order) => ({
      plannedEntryId: `synthetic-plan-entry-${order + 1}`,
      agentId: run.agentId,
      revisionId: run.revisionId,
      taskId: run.taskId,
      repeat: 0,
      order,
      derivedSeed: 100 + order,
      taskInstance: { availability: "template_only" },
    })),
    executionLimits: {
      maxAgents: 3,
      maxSelectedTasks: 3,
      maxRepeats: 1,
      multiAgentComparison: true,
    },
  };
}

/** Resolve the deterministic scenario attached to one valid Experiment identity. */
function scenarioFor(experimentId) {
  if (experimentId === IDS.replayUnavailable) return "replay-unavailable";
  if (experimentId === IDS.replayAvailable) return "replay-available";
  if (experimentId === IDS.notFound) return "not-found";
  if (experimentId === IDS.cancellable) return "cancellable";
  if (experimentId === IDS.reconnecting) return "reconnecting";
  if (experimentId === IDS.loading) return "loading";
  if (experimentId === IDS.integrityFrozen) return "integrity-frozen";
  if (experimentId === IDS.reportReady) return "report-ready";
  if (experimentId === IDS.reportPending) return "report-pending";
  if (experimentId === IDS.reportFailed) return "report-failed";
  if (experimentId === IDS.reportCorrupt) return "report-corrupt";
  if (experimentId === IDS.taskReportMissing) return "task-report-missing";
  if (experimentId === IDS.nullEvaluation) return "null-evaluation";
  if (experimentId === IDS.comparisonMetrics) return "comparison-metrics";
  return experimentId === IDS.active ? "active" : "not-found";
}

/** Build one authoritative Experiment fixture for a browser smoke scenario. */
function experiment(experimentId, scenario) {
  const terminal = [
    "replay-unavailable",
    "replay-available",
    "report-ready",
    "report-pending",
    "report-failed",
    "report-corrupt",
    "task-report-missing",
    "null-evaluation",
    "comparison-metrics",
  ].includes(scenario);
  const cancellable = scenario === "cancellable";
  const eventHighWaterMark = scenario === "integrity-frozen" ? 2 : 1;
  const reportAvailability =
    scenario === "report-pending"
      ? "pending"
      : scenario === "report-failed"
        ? "failed"
        : terminal
          ? "available"
          : "pending";
  const reportAvailable = reportAvailability === "available";
  const replayAvailable =
    scenario === "replay-available"
    || scenario === "report-ready"
    || scenario === "null-evaluation";
  return {
    schemaVersion: 1,
    experimentId,
    clientRequestId: "benchmark-monitor-smoke",
    definition: definition(scenario),
    lifecycle: terminal ? "terminal" : cancellable ? "accepted" : "running",
    terminalReason: terminal ? "completed" : null,
    cancellation: null,
    outcomeAvailability: terminal ? "available" : "pending",
    reportAvailability,
    replayAvailability:
      replayAvailable
        ? "available"
        : terminal
          ? "not_produced"
          : "pending",
    trajectoryAvailability: terminal ? "available" : "pending",
    bundleAvailability: terminal ? "available" : "pending",
    publicationDiagnostics: [],
    eventHighWaterMark,
    acceptedAt: 1,
    updatedAt: terminal ? 10 : 2,
    terminalAt: terminal ? 10 : null,
    capabilities: {
      executes: true,
      cancelAccepted: true,
      cancelActive: !terminal,
      eventStream: true,
      replay: true,
      reports: true,
    },
    links: {
      self: `/studio/benchmark-experiments/${experimentId}`,
      cancel: !terminal
        ? `/studio/benchmark-experiments/${experimentId}/cancel`
        : null,
      taskRuns: `/studio/benchmark-experiments/${experimentId}/task-runs`,
      artifacts: reportAvailable
        ? `/studio/benchmark-experiments/${experimentId}/artifacts`
        : null,
      events: `/studio/benchmark-experiments/${experimentId}/events`,
      eventStream: `/studio/benchmark-experiments/${experimentId}/events/stream`,
      report: reportAvailable
        ? `/studio/benchmark-experiments/${experimentId}/report`
        : null,
      bundle: terminal
        ? `/studio/benchmark-experiments/${experimentId}/bundle`
        : null,
    },
  };
}

/** Build one authoritative TaskRun fixture without live screenshot or UI-XML evidence. */
function taskRun(experimentId, scenario) {
  const terminal = [
    "replay-unavailable",
    "replay-available",
    "report-ready",
    "report-pending",
    "report-failed",
    "report-corrupt",
    "task-report-missing",
    "null-evaluation",
  ].includes(scenario);
  const reportAvailability =
    scenario === "report-pending"
      ? "pending"
      : scenario === "report-failed"
        ? "failed"
        : terminal
          ? "available"
          : "pending";
  const replayAvailable =
    scenario === "replay-available"
    || scenario === "report-ready"
    || scenario === "null-evaluation";
  return {
    schemaVersion: 1,
    taskRunId: TASK_RUN_ID,
    experimentId,
    plannedEntryId: "fixture-plan-entry",
    order: 0,
    agentId: "fixture-agent",
    revisionId: "fixture-revision",
    taskId: "fixture-task",
    repeat: 0,
    derivedSeed: 42,
    lifecycle: terminal ? "terminal" : "running",
    terminalReason: terminal ? "completed" : null,
    processOwnerId: terminal ? "" : "fixture-worker",
    coreTaskRunId: CORE_TASK_RUN_ID,
    agentRunId: "fixture-agent-run",
    taskInstanceIdentity: HASH,
    phases: [
      {
        phase: "reset",
        status: "success",
        durationMs: 12,
        errorCode: "",
        message: "",
        evidence: {},
        artifactRefs: [],
      },
    ],
    agentStatus: terminal ? "success" : null,
    benchmarkOutcome: terminal ? "pass" : null,
    evaluation: terminal ? { score: 1 } : null,
    taskInstanceAvailability: "available",
    phaseAvailability: "available",
    agentStatusAvailability: terminal ? "available" : "pending",
    outcomeAvailability: terminal ? "available" : "pending",
    resultAvailability: terminal ? "available" : "pending",
    evaluationAvailability: terminal ? "available" : "pending",
    replayAvailability: replayAvailable
      ? "available"
      : terminal
        ? "not_produced"
        : "pending",
    reportAvailability,
    trajectoryAvailability: terminal ? "available" : "pending",
    bundleAvailability: terminal ? "available" : "pending",
    replayId: replayAvailable ? REPLAY_ID : null,
    artifacts: [],
    publicationDiagnostics: [],
    links: {
      self: `/studio/benchmark-experiments/${experimentId}/task-runs/${TASK_RUN_ID}`,
      artifacts:
        reportAvailability === "available"
          ? `/studio/benchmark-experiments/${experimentId}/task-runs/`
            + `${TASK_RUN_ID}/artifacts`
          : null,
      replay: replayAvailable ? `/studio/replays/${REPLAY_ID}` : null,
    },
    result: terminal ? { status: "completed" } : null,
    resultFingerprint: terminal ? HASH : null,
    createdAt: 1,
    updatedAt: terminal ? 10 : 2,
    startedAt: 2,
    evaluatingAt: terminal ? 8 : null,
    cleaningUpAt: terminal ? 9 : null,
    terminalAt: terminal ? 10 : null,
  };
}

/** Build synthetic TaskRuns aligned with the multi-Agent report fixture. */
function syntheticComparisonTaskRuns(experimentId) {
  return SYNTHETIC_COMPARISON_RUNS.map((run, order) => {
    const base = taskRun(experimentId, "report-ready");
    return {
      ...base,
      taskRunId: run.taskRunId,
      plannedEntryId: `synthetic-plan-entry-${order + 1}`,
      order,
      agentId: run.agentId,
      revisionId: run.revisionId,
      taskId: run.taskId,
      derivedSeed: 100 + order,
      coreTaskRunId: run.coreTaskRunId,
      agentRunId: `synthetic-agent-run-${order + 1}`,
      agentStatus:
        run.outcome === "invalid"
          ? "failure"
          : run.outcome === "skipped"
            ? "cancelled"
            : "success",
      benchmarkOutcome: run.outcome,
      evaluation: {
        score: run.outcome === "pass" ? 1 : run.outcome === "fail" ? 0 : null,
      },
      replayAvailability: "not_produced",
      replayId: null,
      links: {
        ...base.links,
        self:
          `/studio/benchmark-experiments/${experimentId}/task-runs/`
          + run.taskRunId,
        artifacts:
          `/studio/benchmark-experiments/${experimentId}/task-runs/`
          + `${run.taskRunId}/artifacts`,
        replay: null,
      },
    };
  });
}

/** Build one durable journal envelope with a canonical deterministic fingerprint. */
function event(experimentId, sequence, kind = "experiment.accepted") {
  return {
    schemaVersion: 1,
    eventId: `benchmark-event-${sequence.toString(16).padStart(32, "0")}`,
    timestamp: sequence,
    source: "service",
    kind,
    taskRunId: TASK_RUN_ID,
    sourceSequence: sequence,
    phase: "",
    payload: { fixture: "no-device" },
    experimentId,
    sequence,
    fingerprint: `sha256:${sequence.toString(16).padStart(64, "0")}`,
  };
}

/** Build one publisher-shaped Core Experiment report for browser verification. */
function experimentReport(experimentId, scenario = "single-agent") {
  if (scenario === "comparison-metrics") {
    return syntheticComparisonExperimentReport(experimentId);
  }
  return {
    schema_version: "1.0",
    kind: "benchmark_experiment_report",
    experiment_id: experimentId,
    benchmark_plan_identity: HASH,
    experiment_protocol_identity: HASH,
    counts: { pass: 1, fail: 0, invalid: 0, skipped: 0 },
    agent_metrics: [
      {
        agent_id: "fixture-agent",
        counts: { pass: 1, fail: 0, invalid: 0, skipped: 0 },
        eligible_count: 1,
        success_rate_micro: 1,
        success_rate_macro: 1,
        duration_mean_ms: 12,
        duration_median_ms: 12,
        duration_sample_variance: null,
        wilson_interval_95: [0.2, 1],
        usage_available_runs: 1,
      },
    ],
    comparisons: [],
    run_summaries: [
      {
        task_run_id: CORE_TASK_RUN_ID,
        task_id: "fixture-task",
        agent_id: "fixture-agent",
        repeat: 0,
        outcome: "pass",
        report_ref: `runs/${CORE_TASK_RUN_ID}/run-report.json`,
        trajectory_ref: `runs/${CORE_TASK_RUN_ID}/trajectory.jsonl`,
      },
    ],
    fairness_warnings: [],
    significance_claimed: false,
  };
}

/** Build a clearly synthetic multi-Agent report with aggregate edge states. */
function syntheticComparisonExperimentReport(experimentId) {
  return {
    schema_version: "1.0",
    kind: "benchmark_experiment_report",
    experiment_id: experimentId,
    benchmark_plan_identity: HASH,
    experiment_protocol_identity: HASH,
    counts: { pass: 1, fail: 1, invalid: 1, skipped: 1 },
    agent_metrics: [
      {
        agent_id: "synthetic-agent-a",
        counts: { pass: 1, fail: 0, invalid: 0, skipped: 0 },
        eligible_count: 1,
        success_rate_micro: 1,
        success_rate_macro: 1,
        duration_mean_ms: 0,
        duration_median_ms: 0,
        duration_sample_variance: 0,
        wilson_interval_95: [0.2, 1],
        usage_available_runs: 1,
      },
      {
        agent_id: "synthetic-agent-b",
        counts: { pass: 0, fail: 1, invalid: 0, skipped: 0 },
        eligible_count: 1,
        success_rate_micro: 0,
        success_rate_macro: 0,
        duration_mean_ms: 14,
        duration_median_ms: 14,
        duration_sample_variance: null,
        wilson_interval_95: [0, 0.8],
        usage_available_runs: 0,
      },
      {
        agent_id: "synthetic-agent-c",
        counts: { pass: 0, fail: 0, invalid: 1, skipped: 1 },
        eligible_count: 0,
        success_rate_micro: null,
        success_rate_macro: null,
        duration_mean_ms: null,
        duration_median_ms: null,
        duration_sample_variance: null,
        wilson_interval_95: null,
        usage_available_runs: 0,
      },
    ],
    comparisons: [
      {
        left_agent_id: "synthetic-agent-a",
        right_agent_id: "synthetic-agent-b",
        paired: true,
        matched_count: 1,
        unmatched_eligible_count: 2,
        left_wins: 1,
        right_wins: 0,
        ties: 0,
        significance_claimed: false,
      },
      {
        left_agent_id: "synthetic-agent-a",
        right_agent_id: "synthetic-agent-c",
        paired: false,
        matched_count: 0,
        unmatched_eligible_count: 1,
        left_wins: 0,
        right_wins: 0,
        ties: 0,
        significance_claimed: false,
      },
    ],
    run_summaries: SYNTHETIC_COMPARISON_RUNS.map((run) => ({
      task_run_id: run.coreTaskRunId,
      task_id: run.taskId,
      agent_id: run.agentId,
      repeat: 0,
      outcome: run.outcome,
      report_ref: `runs/${run.coreTaskRunId}/run-report.json`,
      trajectory_ref: `runs/${run.coreTaskRunId}/trajectory.jsonl`,
    })),
    fairness_warnings: [
      "benchmark.protocol.unpaired_materialization",
      "benchmark.protocol.shared_device_state_across_agents",
    ],
    significance_claimed: false,
  };
}

/** Build one bounded Evaluation Tree with safely redacted token evidence. */
function evaluation() {
  return {
    path: "root",
    name: "all",
    status: "success",
    is_pass: null,
    reason: "",
    token: "<redacted>",
    score: 1,
    duration_ms: 5,
    evidence: {},
    aggregation: { method: "all" },
    evaluator_result: null,
    short_circuited: false,
    children: [
      {
        path: "root/fixture-leaf",
        name: "fixture-leaf",
        status: "success",
        is_pass: true,
        reason: "publisher-shaped no-device fixture",
        token: "<redacted>",
        score: 1,
        duration_ms: 4,
        evidence: {},
        aggregation: {},
        evaluator_result: {
          schema_version: "2.0",
          evaluator_id: "fixture-evaluator",
          status: "completed",
          passed: true,
          score: 1,
          reason: "fixture evidence matched",
          duration_ms: 4,
          usage: {
            availability: "available",
            prompt_tokens: 1,
            completion_tokens: 1,
            total_tokens: 2,
          },
          evidence: EVIDENCE_CASES.map((item) => ({
            kind: item.kind,
            value: { fixture: true },
            artifact_ref: item.reference,
            metadata: {},
          })),
          metadata: {},
          error_code: "",
        },
        short_circuited: false,
        children: [],
      },
    ],
  };
}

/** Build one publisher-shaped Core TaskRun report for the selected run. */
function runReport(experimentId, scenario, syntheticRun = null) {
  if (scenario === "comparison-metrics" && syntheticRun !== null) {
    return syntheticComparisonRunReport(experimentId, syntheticRun);
  }
  return {
    schema_version: "1.0",
    kind: "benchmark_run_report",
    task_run_id: CORE_TASK_RUN_ID,
    experiment_id: experimentId,
    task_id: "fixture-task",
    agent_id: "fixture-agent",
    repeat: 0,
    outcome: "pass",
    identities: {
      agent_graph: HASH,
      benchmark_plan: HASH,
      experiment_protocol: HASH,
      task_instance: HASH,
    },
    stages: [
      {
        phase: "evaluation",
        status: "success",
        duration_ms: 12,
        error_code: "",
        message: "",
        evidence: {},
        artifact_refs: [],
      },
    ],
    evaluation: scenario === "null-evaluation" ? null : evaluation(),
    usage: { total_tokens: 2 },
    artifact_namespace: CORE_TASK_RUN_ID,
  };
}

/** Build one synthetic TaskRun report aligned to its resource and run summary. */
function syntheticComparisonRunReport(experimentId, run) {
  const eligible = run.outcome === "pass" || run.outcome === "fail";
  const passed = run.outcome === "pass";
  return {
    schema_version: "1.0",
    kind: "benchmark_run_report",
    task_run_id: run.coreTaskRunId,
    experiment_id: experimentId,
    task_id: run.taskId,
    agent_id: run.agentId,
    repeat: 0,
    outcome: run.outcome,
    identities: {
      agent_graph: HASH,
      benchmark_plan: HASH,
      experiment_protocol: HASH,
      task_instance: HASH,
    },
    stages: [
      {
        phase: "evaluation",
        status: eligible ? "success" : run.outcome === "skipped" ? "skipped" : "failure",
        duration_ms: eligible ? 14 : 0,
        error_code: eligible ? "" : `fixture.${run.outcome}`,
        message: "",
        evidence: {},
        artifact_refs: [],
      },
    ],
    evaluation: eligible
      ? {
          ...evaluation(),
          status: passed ? "success" : "failure",
          is_pass: passed,
          score: passed ? 1 : 0,
          reason: `synthetic ${run.outcome} presentation fixture`,
        }
      : null,
    usage: eligible ? { total_tokens: 2 } : {},
    artifact_namespace: run.coreTaskRunId,
  };
}

/** Build metadata-only report inventory with explicit closure states. */
function artifactInventory(experimentId, scenario) {
  if (scenario === "comparison-metrics") {
    return {
      schemaVersion: 1,
      experimentId,
      items: SYNTHETIC_COMPARISON_RUNS.map((run) => ({
        schemaVersion: 1,
        descriptor: {
          schemaVersion: 1,
          artifactId: run.artifactId,
          experimentId,
          taskRunId: run.taskRunId,
          kind: "task_report",
          availability: "available",
          contentType: "application/json",
          size: 512,
          sha256: HASH,
          provenance: "synthetic_no_device_fixture",
          causalIdentity: `runs/${run.coreTaskRunId}/run-report.json`,
          hidden: false,
        },
        links: {
          content:
            `/studio/benchmark-experiments/${experimentId}/task-runs/`
            + `${run.taskRunId}/artifacts/${run.artifactId}`,
        },
      })),
      hiddenCount: 0,
      nextCursor: null,
    };
  }
  const missing = scenario === "task-report-missing";
  const exportItems = scenario === "report-ready"
    ? exportArtifactCases(experimentId).map((item) => ({
        schemaVersion: 1,
        descriptor: {
          schemaVersion: 1,
          artifactId: item.artifactId,
          experimentId,
          taskRunId: item.taskRunId,
          kind: item.kind,
          availability: "available",
          contentType: item.contentType,
          size: item.body.byteLength,
          sha256: HASH,
          provenance: "deterministic_no_device_fixture",
          causalIdentity: item.reference,
          hidden: false,
        },
        links: {
          content: item.taskRunId === null
            ? `/studio/benchmark-experiments/${experimentId}/artifacts/`
              + item.artifactId
            : `/studio/benchmark-experiments/${experimentId}/task-runs/`
              + `${item.taskRunId}/artifacts/${item.artifactId}`,
        },
      }))
    : [];
  const evidenceItems = scenario === "report-ready"
    ? EVIDENCE_CASES.map((item) => {
        const readable = ["available", "redacted", "truncated"].includes(
          item.availability,
        );
        const size = item.descriptorSize ?? item.body?.byteLength ?? 0;
        return {
          schemaVersion: 1,
          descriptor: {
            schemaVersion: 1,
            artifactId: item.artifactId,
            experimentId,
            taskRunId: TASK_RUN_ID,
            kind: item.kind,
            availability: item.availability,
            contentType: readable ? item.contentType : "",
            size,
            sha256: readable ? HASH : null,
            provenance: "deterministic_no_device_fixture",
            causalIdentity: item.reference,
            hidden: false,
          },
          links: {
            content: readable
              ? `/studio/benchmark-experiments/${experimentId}/task-runs/`
                + `${TASK_RUN_ID}/artifacts/${item.artifactId}`
              : null,
          },
        };
      })
    : [];
  return {
    schemaVersion: 1,
    experimentId,
    items: [
      ...evidenceItems,
      ...exportItems,
      {
        schemaVersion: 1,
        descriptor: {
          schemaVersion: 1,
          artifactId: REPORT_ARTIFACT_ID,
          experimentId,
          taskRunId: TASK_RUN_ID,
          kind: "task_report",
          availability: missing ? "missing" : "available",
          contentType: "application/json",
          size: missing
            ? 0
            : Buffer.byteLength(JSON.stringify(
                runReport(experimentId, scenario),
              )),
          sha256: missing ? null : HASH,
          provenance: "native_benchmark",
          causalIdentity: `runs/${CORE_TASK_RUN_ID}/run-report.json`,
          hidden: false,
        },
        links: {
          content: missing
            ? null
            : `/studio/benchmark-experiments/${experimentId}/task-runs/`
              + `${TASK_RUN_ID}/artifacts/${REPORT_ARTIFACT_ID}`,
        },
      },
    ],
    hiddenCount: scenario === "report-ready" ? 1 : 0,
    nextCursor: null,
  };
}

/** Build one persisted no-device Replay envelope for authoritative handoff checks. */
function replayEnvelope() {
  return {
    schemaVersion: 1,
    runId: REPLAY_ID,
    importedAt: 10,
    provenance: "fake_contract_fixture",
    integrityState: "partial",
    snapshot: {
      agentId: "fixture-agent",
      revisionId: "fixture-revision",
      contractVersion: "1.1",
      canonicalHash: HASH,
      graphStatus: "available",
      agentGraph: definition().agentSnapshots[0].agentGraph,
      presentation: {},
      sourceMap: [],
      providerIdentities: [],
    },
    result: {
      status: "success",
      kernelStatus: "success",
      error: "",
      stepCount: 1,
      activationCount: 1,
      interactionCount: 1,
      usage: {},
    },
    moments: [
      {
        momentId: "fixture-observe-start",
        causalIndex: 0,
        sourceKind: "agent_graph",
        sourceSequence: 1,
        timestamp: 1,
        phase: "graph_kernel",
        kind: "start",
        role: "observation_provider",
        component: "fixture_observation_provider",
        nodeId: "observe",
        nodePath: "observe",
        activationId: "fixture-activation-observe",
        parentActivationId: "",
        loopPath: "",
        loopIteration: null,
        interactionStep: 1,
        durationMs: null,
        payload: { task: "Inspect no-device fixture" },
        observationId: null,
        actionId: null,
        artifactIds: [],
      },
      {
        momentId: "fixture-observe-complete",
        causalIndex: 1,
        sourceKind: "agent_graph",
        sourceSequence: 2,
        timestamp: 2,
        phase: "graph_kernel",
        kind: "complete",
        role: "observation_provider",
        component: "fixture_observation_provider",
        nodeId: "observe",
        nodePath: "observe",
        activationId: "fixture-activation-observe",
        parentActivationId: "",
        loopPath: "",
        loopIteration: null,
        interactionStep: 1,
        durationMs: 4,
        payload: { observation: "No screenshot was captured by the fixture." },
        observationId: null,
        actionId: null,
        artifactIds: [],
      },
    ],
    observations: [],
    actions: [],
    benchmark: {
      experimentId: IDS.reportReady,
      taskId: "fixture-task",
      agentId: "fixture-agent",
      repeat: 0,
      outcome: "pass",
      identities: {
        benchmarkPlan: HASH,
        experimentProtocol: HASH,
        agentGraph: HASH,
        taskInstance: HASH,
      },
      phases: [],
      evaluation: { isPass: true, score: 1 },
    },
    artifacts: [],
    availability: {
      agentGraph: { state: "available", reasonCode: "", detail: "" },
      screenshots: {
        state: "not_captured",
        reasonCode: "fixture.no_device",
        detail: "No device screenshot was captured by this fixture.",
      },
      prompt: {
        state: "excluded",
        reasonCode: "fixture.no_prompt",
        detail: "Prompt evidence is outside this smoke fixture.",
      },
    },
    integrity: [
      {
        code: "fixture.no_device",
        message: "Replay is structurally valid but contains no device evidence.",
        severity: "warning",
        source: "benchmark-monitor-smoke",
        causalIndex: null,
      },
    ],
  };
}

/** Project one compact metadata-only History row without full definitions. */
function historyItem(row) {
  const scenario = scenarioFor(row.experimentId);
  const resource = experiment(row.experimentId, scenario);
  const base = `/studio/benchmark-experiments/${row.experimentId}`;
  const agents = row.agentIds.map((agentId, index) => ({
    agentId,
    revisionId:
      agentId === "deleted-history-agent"
        ? "deleted-history-revision"
        : resource.definition.agentSnapshots[index]?.revisionId
          ?? `fixture-revision-${index + 1}`,
  }));
  return {
    schemaVersion: 1,
    experimentId: row.experimentId,
    lifecycle: resource.lifecycle,
    terminalReason: resource.terminalReason,
    source: {
      catalogEntryId: row.catalogEntryId,
      packageIdentity:
        row.catalogEntryId === "deleted-history-catalog"
          ? "deleted/history@1.0.0"
          : resource.definition.source.packageIdentity,
      split: resource.definition.split,
    },
    agents,
    plannedTaskRunCount: resource.definition.schedule.length,
    outcomeAvailability: resource.outcomeAvailability,
    reportAvailability: resource.reportAvailability,
    replayAvailability: resource.replayAvailability,
    trajectoryAvailability: resource.trajectoryAvailability,
    bundleAvailability: resource.bundleAvailability,
    acceptedAt: row.acceptedAt,
    updatedAt: Math.max(row.acceptedAt, row.acceptedAt + 10),
    terminalAt:
      resource.lifecycle === "terminal" ? row.acceptedAt + 10 : null,
    links: {
      self: base,
      taskRuns: `${base}/task-runs`,
      artifacts: `${base}/artifacts`,
      report:
        resource.reportAvailability === "available"
          ? `${base}/report`
          : null,
      bundle:
        resource.bundleAvailability === "available"
          ? `${base}/bundle`
          : null,
    },
  };
}

/** Return the canonical filter tuple used to bind fixture cursors. */
function historyFilterIdentity(url) {
  return JSON.stringify({
    lifecycle: url.searchParams.get("lifecycle") ?? null,
    catalogEntryId: url.searchParams.get("catalogEntryId") ?? null,
    agentId: url.searchParams.get("agentId") ?? null,
    acceptedFrom: url.searchParams.get("acceptedFrom") ?? null,
    acceptedBefore: url.searchParams.get("acceptedBefore") ?? null,
  });
}

/** Encode one deterministic filter-bound forward cursor for the fixture. */
function encodeHistoryCursor(offset, filters) {
  return Buffer.from(JSON.stringify({ v: 2, offset, filters }), "utf8")
    .toString("base64url");
}

/** Decode one fixture cursor and reject cross-filter reuse. */
function decodeHistoryCursor(cursor, filters) {
  if (cursor === null) return 0;
  const value = JSON.parse(
    Buffer.from(cursor, "base64url").toString("utf8"),
  );
  if (
    value?.v !== 2
    || !Number.isInteger(value.offset)
    || value.offset < 0
    || value.filters !== filters
  ) {
    throw new Error("fixture cursor is invalid");
  }
  return value.offset;
}

/** Build one filtered newest-first History page with tied timestamp ordering. */
function experimentHistoryPage(url) {
  const limit = Number(url.searchParams.get("limit") ?? "50");
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error("fixture limit is invalid");
  }
  const lifecycle = url.searchParams.get("lifecycle");
  const catalogEntryId = url.searchParams.get("catalogEntryId");
  const agentId = url.searchParams.get("agentId");
  const acceptedFrom = Number(url.searchParams.get("acceptedFrom") ?? "0");
  const acceptedBefore = Number(
    url.searchParams.get("acceptedBefore")
      ?? String(Number.MAX_SAFE_INTEGER),
  );
  const filters = historyFilterIdentity(url);
  const offset = decodeHistoryCursor(
    url.searchParams.get("cursor"),
    filters,
  );
  const matching = HISTORY_ROWS
    .map(historyItem)
    .filter((item) =>
      (lifecycle === null || item.lifecycle === lifecycle)
      && (
        catalogEntryId === null
        || item.source.catalogEntryId === catalogEntryId
      )
      && (
        agentId === null
        || item.agents.some((agent) => agent.agentId === agentId)
      )
      && item.acceptedAt >= acceptedFrom
      && item.acceptedAt < acceptedBefore
    )
    .sort((left, right) =>
      right.acceptedAt - left.acceptedAt
      || right.experimentId.localeCompare(left.experimentId)
    );
  const items = matching.slice(offset, offset + limit);
  const nextOffset = offset + items.length;
  return {
    schemaVersion: 1,
    items,
    nextCursor:
      nextOffset < matching.length
        ? encodeHistoryCursor(nextOffset, filters)
        : null,
  };
}

/** Send one bounded JSON response and close the request. */
function sendJson(response, body, status = 200) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  response.end(JSON.stringify(body));
}

/** Send managed artifact headers for GET or bodyless HEAD.
 *
 * Args:
 *   request: Incoming request whose method controls body emission.
 *   response: Node HTTP response.
 *   body: Bounded fixture bytes.
 *   contentType: Exact allowlisted media type.
 *   filename: Safe opaque attachment filename.
 *   declaredSize: Optional descriptor length used by mismatch fixtures.
 *
 * Returns:
 *   Nothing; the response is always closed.
 */
function sendManagedBytes(
  request,
  response,
  body,
  contentType,
  filename,
  declaredSize = body.byteLength,
) {
  response.writeHead(200, {
    "Content-Type": contentType,
    "Content-Length": String(declaredSize),
    "Content-Disposition": `attachment; filename="${filename}"`,
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "Access-Control-Expose-Headers":
      "Content-Disposition, Content-Length, Content-Type",
  });
  response.end(request.method === "HEAD" ? undefined : body);
}

/** Encode and send one managed JSON artifact through GET or HEAD. */
function sendManagedJson(request, response, body, filename) {
  sendManagedBytes(
    request,
    response,
    Buffer.from(JSON.stringify(body)),
    "application/json",
    filename,
  );
}

/** Write one named SSE frame with an optional durable sequence identity. */
function sendSse(response, type, data, id = null) {
  if (id !== null) response.write(`id: ${id}\n`);
  response.write(`event: ${type}\n`);
  response.write(`data: ${JSON.stringify(data)}\n\n`);
}

/** Parse the scoped Benchmark Experiment route or return null for unrelated paths. */
function parseRoute(pathname) {
  const match = pathname.match(
    /^\/studio\/benchmark-experiments\/(experiment-[a-f0-9]{32})(?:\/(.*))?$/,
  );
  return match
    ? { experimentId: match[1], suffix: match[2] ?? "" }
    : null;
}

/** Handle one deterministic no-device Studio Monitor request. */
async function handleRequest(request, response) {
  const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
  if (
    url.pathname === "/studio/benchmark-experiments"
    && request.method === "GET"
  ) {
    if (url.searchParams.get("cursor") === "fixture-retry") {
      const attempts = (historyRetryAttempts.get(url.search) ?? 0) + 1;
      historyRetryAttempts.set(url.search, attempts);
      if (attempts <= 3) {
        sendJson(response, {
          schemaVersion: 1,
          error: {
            code: "fixture.history_retry",
            message:
              "Fixture History exhausted the automatic retry; retry the same URL.",
          },
        }, 503);
        return;
      }
      url.searchParams.delete("cursor");
    }
    try {
      sendJson(response, experimentHistoryPage(url));
    } catch {
      sendJson(response, {
        schemaVersion: 1,
        error: {
          code: "benchmark.experiment.history_cursor_invalid",
          message: "Benchmark Experiment history cursor is invalid",
        },
      }, 400);
    }
    return;
  }
  if (url.pathname === "/studio/benchmarks" && request.method === "GET") {
    sendJson(response, {
      schemaVersion: 1,
      items: [
        {
          catalogEntryId: "history-catalog-a",
          packageIdentity: "smoke/no-device@1.0.0",
          title: "History no-device fixture",
          version: "1.0.0",
          sourceKind: "catalog",
          platforms: ["android"],
          splits: [{ name: "test", taskCount: 1 }],
          availability: "available",
          warnings: [],
        },
      ],
      nextCursor: null,
    });
    return;
  }
  if (url.pathname === "/studio/agents" && request.method === "GET") {
    sendJson(response, {
      schemaVersion: 1,
      items: [
        {
          agentId: "fixture-agent",
          name: "History fixture Agent",
          currentRevisionId: "fixture-revision",
          createdAt: 1,
          updatedAt: 1,
        },
      ],
      nextCursor: null,
    });
    return;
  }
  if (
    [
      `/studio/replays/${REPLAY_ID}`,
      `/api/studio/replays/${REPLAY_ID}`,
    ].includes(url.pathname)
    && request.method === "GET"
  ) {
    sendJson(response, replayEnvelope());
    return;
  }
  const route = parseRoute(url.pathname);
  if (!route) {
    sendJson(response, {
      schemaVersion: 1,
      error: { code: "fixture.route_not_found", message: "fixture route not found" },
    }, 404);
    return;
  }
  const scenario = scenarioFor(route.experimentId);
  if (scenario === "not-found") {
    sendJson(response, {
      schemaVersion: 1,
      error: {
        code: "studio.benchmark_experiment.not_found",
        message: "Experiment fixture not found",
      },
    }, 404);
    return;
  }
  if (scenario === "loading") {
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
  const resource = experiment(route.experimentId, scenario);
  if (route.suffix === "" && request.method === "GET") {
    sendJson(response, resource);
    return;
  }
  if (route.suffix === "task-runs" && request.method === "GET") {
    sendJson(response, {
      schemaVersion: 1,
      experimentId: route.experimentId,
      items:
        scenario === "comparison-metrics"
          ? syntheticComparisonTaskRuns(route.experimentId)
          : [taskRun(route.experimentId, scenario)],
      nextCursor: null,
    });
    return;
  }
  if (route.suffix === "artifacts" && request.method === "GET") {
    sendJson(
      response,
      artifactInventory(route.experimentId, scenario),
    );
    return;
  }
  if (
    route.suffix === "report"
    && (request.method === "GET" || request.method === "HEAD")
  ) {
    if (scenario === "report-corrupt") {
      sendJson(response, {
        schemaVersion: 1,
        error: {
          code: "benchmark.artifact.corrupt",
          message: "Fixture report failed integrity verification",
        },
      }, 409);
      return;
    }
    sendManagedJson(
      request,
      response,
      experimentReport(route.experimentId, scenario),
      `${route.experimentId}.report.json`,
    );
    return;
  }
  if (
    route.suffix === "bundle"
    && (request.method === "GET" || request.method === "HEAD")
    && scenario === "report-ready"
  ) {
    sendManagedBytes(
      request,
      response,
      EXPORT_BUNDLE_BODY,
      "application/zip",
      `${route.experimentId}.zip`,
    );
    return;
  }
  const experimentArtifactRoute = route.suffix.match(
    /^artifacts\/(artifact-[a-f0-9]{32})$/,
  );
  if (
    scenario === "report-ready"
    && experimentArtifactRoute
    && (request.method === "GET" || request.method === "HEAD")
  ) {
    const item = exportArtifactCases(route.experimentId).find(
      (candidate) =>
        candidate.taskRunId === null
        && candidate.artifactId === experimentArtifactRoute[1],
    );
    if (item) {
      sendManagedBytes(
        request,
        response,
        item.body,
        item.contentType,
        item.artifactId,
      );
      return;
    }
  }
  const syntheticArtifactRoute = route.suffix.match(
    /^task-runs\/(task-run-[a-f0-9]{32})\/artifacts\/(artifact-[a-f0-9]{32})$/,
  );
  if (
    scenario === "comparison-metrics"
    && syntheticArtifactRoute
    && (request.method === "GET" || request.method === "HEAD")
  ) {
    const run = SYNTHETIC_COMPARISON_RUNS.find(
      (item) =>
        item.taskRunId === syntheticArtifactRoute[1]
        && item.artifactId === syntheticArtifactRoute[2],
    );
    if (run) {
      sendManagedJson(
        request,
        response,
        runReport(route.experimentId, scenario, run),
        run.artifactId,
      );
      return;
    }
  }
  if (
    route.suffix
      === `task-runs/${TASK_RUN_ID}/artifacts/${REPORT_ARTIFACT_ID}`
    && (request.method === "GET" || request.method === "HEAD")
  ) {
    if (scenario === "task-report-missing") {
      sendJson(response, {
        schemaVersion: 1,
        error: {
          code: "benchmark.artifact.missing",
          message: "Fixture TaskRun report is missing",
        },
      }, 404);
      return;
    }
    sendManagedJson(
      request,
      response,
      runReport(route.experimentId, scenario),
      REPORT_ARTIFACT_ID,
    );
    return;
  }
  const evidenceArtifactRoute = route.suffix.match(
    new RegExp(
      `^task-runs/${TASK_RUN_ID}/artifacts/(artifact-[a-f0-9]{32})$`,
    ),
  );
  if (
    scenario === "report-ready"
    && evidenceArtifactRoute
    && (request.method === "GET" || request.method === "HEAD")
  ) {
    const exportItem = exportArtifactCases(route.experimentId).find(
      (candidate) =>
        candidate.taskRunId === TASK_RUN_ID
        && candidate.artifactId === evidenceArtifactRoute[1],
    );
    if (exportItem) {
      sendManagedBytes(
        request,
        response,
        exportItem.body,
        exportItem.contentType,
        exportItem.artifactId,
      );
      return;
    }
    const item = EVIDENCE_CASES.find(
      (candidate) => candidate.artifactId === evidenceArtifactRoute[1],
    );
    if (item && item.body !== null) {
      sendManagedBytes(
        request,
        response,
        item.body,
        item.responseContentType ?? item.contentType,
        item.artifactId,
        item.descriptorSize ?? item.body.byteLength,
      );
      return;
    }
    sendJson(response, {
      schemaVersion: 1,
      error: {
        code: `benchmark.artifact.${item?.availability ?? "not_found"}`,
        message: "Fixture evidence is not readable",
      },
    }, item?.availability === "corrupt" ? 409 : 404);
    return;
  }
  if (route.suffix === "cancel" && request.method === "POST") {
    sendJson(response, {
      ...resource,
      lifecycle: "terminal",
      terminalReason: "cancelled",
      cancellation: {
        schemaVersion: 1,
        clientRequestId: "smoke-cancel",
        requestedAt: 3,
        reasonCode: "user_requested",
      },
      updatedAt: 3,
      terminalAt: 3,
      links: { ...resource.links, cancel: null },
    }, 202);
    return;
  }
  if (route.suffix === "events" && request.method === "GET") {
    const after = Number(url.searchParams.get("after") ?? "0");
    const sequence = scenario === "integrity-frozen" ? 2 : 1;
    const item =
      after < sequence
        ? [event(
            route.experimentId,
            sequence,
            resource.lifecycle === "terminal"
              ? "experiment.terminal"
              : "experiment.accepted",
          )]
        : [];
    sendJson(response, {
      schemaVersion: 1,
      experimentId: route.experimentId,
      items: item,
      nextCursor: item.length > 0 ? sequence : after,
      highWaterMark: sequence,
      terminal: resource.lifecycle === "terminal" && after >= sequence,
    });
    return;
  }
  if (route.suffix === "events/stream" && request.method === "GET") {
    response.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    response.write(": benchmark-monitor-smoke\n\n");
    if (scenario === "reconnecting") {
      const attempts = (reconnectAttempts.get(route.experimentId) ?? 0) + 1;
      reconnectAttempts.set(route.experimentId, attempts);
      if (attempts === 1) {
        setTimeout(() => {
          sendSse(response, "error", { reason: "fixture_disconnect" });
          response.end();
        }, 250);
        return;
      }
    }
    sendSse(response, "heartbeat", { cursor: 1 });
    const heartbeat = setInterval(() => {
      if (!response.destroyed) sendSse(response, "heartbeat", { cursor: 1 });
    }, 1000);
    request.on("close", () => clearInterval(heartbeat));
    return;
  }
  sendJson(response, {
    schemaVersion: 1,
    error: { code: "fixture.route_not_found", message: "fixture route not found" },
  }, 404);
}

const server = createServer((request, response) => {
  void handleRequest(request, response).catch((error) => {
    sendJson(response, {
      schemaVersion: 1,
      error: {
        code: "fixture.internal_error",
        message: error instanceof Error ? error.message : String(error),
      },
    }, 500);
  });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Benchmark Monitor no-device fixture: http://127.0.0.1:${PORT}`);
  for (const [name, experimentId] of Object.entries(IDS)) {
    console.log(`${name}: http://127.0.0.1:5173/experiments/${experimentId}`);
  }
});
