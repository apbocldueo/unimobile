import { defaultExperimentProtocol } from "@/entities/experiment-preview";

export const benchmarkExperimentId = `experiment-${"a".repeat(32)}`;
export const benchmarkTaskRunId = `task-run-${"b".repeat(32)}`;
export const benchmarkFixtureHash = `sha256:${"c".repeat(64)}`;

/** Build one valid immutable definition snapshot for contract tests. */
export function benchmarkDefinitionFixture() {
  return {
    schemaVersion: 1,
    previewFingerprint: benchmarkFixtureHash,
    snapshotFingerprint: benchmarkFixtureHash,
    source: {
      sourceId: "workspace-benchmarks",
      sourceKind: "catalog",
      relativeKey: "android_world",
      catalogEntryId: "catalog-entry-1",
      packageIdentity: "android-world",
      packageContentIdentity: benchmarkFixtureHash,
      benchmarkPlanIdentity: benchmarkFixtureHash,
      experimentProtocolIdentity: benchmarkFixtureHash,
    },
    agentSnapshots: [
      {
        schemaVersion: 1,
        agentId: "agent-1",
        revisionId: "revision-1",
        contractVersion: "1.1",
        compileContractVersion: "studio-compile-v1",
        canonicalHash: benchmarkFixtureHash,
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
    protocol: defaultExperimentProtocol(),
    split: "test",
    taskIds: ["task-1"],
    schedule: [
      {
        plannedEntryId: "planned-1",
        agentId: "agent-1",
        revisionId: "revision-1",
        taskId: "task-1",
        repeat: 0,
        order: 0,
        derivedSeed: 7,
        taskInstance: { availability: "pending_materialization" },
      },
    ],
    deviceProfileId: "local-android",
    executionLimits: {
      maxAgents: 1,
      maxSelectedTasks: 1,
      maxRepeats: 1,
      multiAgentComparison: false,
    },
  };
}

/** Build one valid running Experiment resource. */
export function benchmarkExperimentFixture() {
  return {
    schemaVersion: 1,
    experimentId: benchmarkExperimentId,
    clientRequestId: "create-1",
    definition: benchmarkDefinitionFixture(),
    lifecycle: "running",
    terminalReason: null,
    cancellation: null,
    outcomeAvailability: "pending",
    reportAvailability: "pending",
    replayAvailability: "pending",
    trajectoryAvailability: "pending",
    bundleAvailability: "pending",
    publicationDiagnostics: [],
    eventHighWaterMark: 2,
    acceptedAt: 1,
    updatedAt: 2,
    terminalAt: null,
    capabilities: {
      executes: true,
      cancelAccepted: true,
      cancelActive: true,
      eventStream: true,
      replay: true,
      reports: true,
    },
    links: {
      self: `/studio/benchmark-experiments/${benchmarkExperimentId}`,
      cancel: `/studio/benchmark-experiments/${benchmarkExperimentId}/cancel`,
      taskRuns: `/studio/benchmark-experiments/${benchmarkExperimentId}/task-runs`,
      artifacts: `/studio/benchmark-experiments/${benchmarkExperimentId}/artifacts`,
      events: `/studio/benchmark-experiments/${benchmarkExperimentId}/events`,
      eventStream: `/studio/benchmark-experiments/${benchmarkExperimentId}/events/stream`,
      report: null,
      bundle: null,
    },
  };
}

/** Build one valid non-terminal TaskRun record with a stable unique identity. */
export function benchmarkTaskRunFixture(order = 0) {
  const taskRunId =
    order === 0
      ? benchmarkTaskRunId
      : `task-run-${order.toString(16).padStart(32, "0")}`;
  return {
    schemaVersion: 1,
    taskRunId,
    experimentId: benchmarkExperimentId,
    plannedEntryId: `planned-${order}`,
    order,
    agentId: "agent-1",
    revisionId: "revision-1",
    taskId: `task-${order + 1}`,
    repeat: 0,
    derivedSeed: 7 + order,
    lifecycle: "running",
    terminalReason: null,
    processOwnerId: "worker-1",
    coreTaskRunId: "core-run-1",
    agentRunId: "agent-run-1",
    taskInstanceIdentity: benchmarkFixtureHash,
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
    agentStatus: null,
    benchmarkOutcome: null,
    evaluation: null,
    taskInstanceAvailability: "available",
    phaseAvailability: "available",
    agentStatusAvailability: "pending",
    outcomeAvailability: "pending",
    resultAvailability: "pending",
    evaluationAvailability: "pending",
    replayAvailability: "pending",
    reportAvailability: "pending",
    trajectoryAvailability: "pending",
    bundleAvailability: "pending",
    replayId: null,
    artifacts: [],
    publicationDiagnostics: [],
    links: {
      self: `/studio/benchmark-experiments/${benchmarkExperimentId}/task-runs/${taskRunId}`,
      artifacts: null,
      replay: null,
    },
    result: null,
    resultFingerprint: null,
    createdAt: 1,
    updatedAt: 2,
    startedAt: 2,
    evaluatingAt: null,
    cleaningUpAt: null,
    terminalAt: null,
  };
}

/** Build one valid committed Benchmark event. */
export function benchmarkEventFixture(sequence = 1) {
  return {
    schemaVersion: 1,
    eventId: `benchmark-event-${sequence.toString(16).padStart(32, "0")}`,
    timestamp: sequence,
    source: "worker",
    kind: sequence === 1 ? "experiment.accepted" : "benchmark.phase.started",
    taskRunId: benchmarkTaskRunId,
    sourceSequence: sequence,
    phase: sequence === 1 ? "" : "action",
    payload: { status: "committed" },
    experimentId: benchmarkExperimentId,
    sequence,
    fingerprint: `sha256:${sequence.toString(16).padStart(64, "0")}`,
  };
}
