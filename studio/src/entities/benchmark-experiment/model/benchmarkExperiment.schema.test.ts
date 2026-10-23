import { describe, expect, it } from "vitest";
import { defaultExperimentProtocol } from "@/entities/experiment-preview";
import {
  parseBenchmarkExperimentEventPage,
  parseBenchmarkExperimentResource,
  parseBenchmarkTaskRunPage,
} from "./benchmarkExperiment.schema";

const experimentId = `experiment-${"a".repeat(32)}`;
const taskRunId = `task-run-${"b".repeat(32)}`;
const hash = `sha256:${"c".repeat(64)}`;

/** Build one valid immutable definition snapshot for contract tests. */
export function benchmarkDefinitionFixture() {
  return {
    schemaVersion: 1,
    previewFingerprint: hash,
    snapshotFingerprint: hash,
    source: {
      sourceId: "workspace-benchmarks",
      sourceKind: "catalog",
      relativeKey: "android_world",
      catalogEntryId: "catalog-entry-1",
      packageIdentity: "android-world",
      packageContentIdentity: hash,
      benchmarkPlanIdentity: hash,
      experimentProtocolIdentity: hash,
    },
    agentSnapshots: [
      {
        schemaVersion: 1,
        agentId: "agent-1",
        revisionId: "revision-1",
        contractVersion: "1.1",
        compileContractVersion: "studio-compile-v1",
        canonicalHash: hash,
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
    experimentId,
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
      self: `/studio/benchmark-experiments/${experimentId}`,
      cancel: `/studio/benchmark-experiments/${experimentId}/cancel`,
      taskRuns: `/studio/benchmark-experiments/${experimentId}/task-runs`,
      artifacts: `/studio/benchmark-experiments/${experimentId}/artifacts`,
      events: `/studio/benchmark-experiments/${experimentId}/events`,
      eventStream: `/studio/benchmark-experiments/${experimentId}/events/stream`,
      report: null,
      bundle: null,
    },
  };
}

/** Build one valid non-terminal TaskRun record. */
export function benchmarkTaskRunFixture(order = 0) {
  return {
    schemaVersion: 1,
    taskRunId,
    experimentId,
    plannedEntryId: `planned-${order}`,
    order,
    agentId: "agent-1",
    revisionId: "revision-1",
    taskId: `task-${order + 1}`,
    repeat: 0,
    derivedSeed: 7,
    lifecycle: "running",
    terminalReason: null,
    processOwnerId: "worker-1",
    coreTaskRunId: "core-run-1",
    agentRunId: "agent-run-1",
    taskInstanceIdentity: hash,
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
      self: `/studio/benchmark-experiments/${experimentId}/task-runs/${taskRunId}`,
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
    taskRunId,
    sourceSequence: sequence,
    phase: sequence === 1 ? "" : "action",
    payload: { status: "committed" },
    experimentId,
    sequence,
    fingerprint: `sha256:${sequence.toString(16).padStart(64, "0")}`,
  };
}

describe("Benchmark Experiment contracts", () => {
  it("parses a strict resource and derives a shared static graph snapshot", () => {
    const resource = parseBenchmarkExperimentResource(
      benchmarkExperimentFixture(),
    );
    expect(resource.lifecycle).toBe("running");
    expect(
      resource.definition.agentSnapshots[0]?.runSnapshot.graphNodes[0]?.id,
    ).toBe("observe");
  });

  it("rejects unknown fields, unsafe links, and terminal-shape conflicts", () => {
    expect(() =>
      parseBenchmarkExperimentResource({
        ...benchmarkExperimentFixture(),
        surprise: true,
      }),
    ).toThrow(/not supported/);
    expect(() =>
      parseBenchmarkExperimentResource({
        ...benchmarkExperimentFixture(),
        links: {
          ...benchmarkExperimentFixture().links,
          self: "https://attacker.example/steal",
        },
      }),
    ).toThrow(/safe Studio path/);
    expect(() =>
      parseBenchmarkExperimentResource({
        ...benchmarkExperimentFixture(),
        lifecycle: "terminal",
      }),
    ).toThrow(/terminal fields/);
  });

  it("parses plural ordered TaskRuns and rejects Replay availability drift", () => {
    const result = {
      schemaVersion: 1,
      evidenceOrigin: {
        schemaVersion: 1,
        acquisition: "contract_fixture",
        environment: "fake_device",
        deviceProfileId: "fixture-android",
        deviceChecks: [],
        realDeviceEvidence: false,
      },
    };
    const page = parseBenchmarkTaskRunPage({
      schemaVersion: 1,
      experimentId,
      items: [{ ...benchmarkTaskRunFixture(), result, resultAvailability: "available" }],
      nextCursor: null,
    });
    expect(page.items[0]?.taskId).toBe("task-1");
    expect(page.items[0]?.result?.evidenceOrigin.environment).toBe("fake_device");
    expect(() =>
      parseBenchmarkTaskRunPage({
        schemaVersion: 1,
        experimentId,
        items: [
          {
            ...benchmarkTaskRunFixture(),
            replayAvailability: "available",
            replayId: null,
          },
        ],
        nextCursor: null,
      }),
    ).toThrow(/Replay identity/);
  });

  it("keeps unknown versioned kinds while enforcing continuous event pages", () => {
    const unknown = {
      ...benchmarkEventFixture(1),
      kind: "future.phase.v9",
    };
    const page = parseBenchmarkExperimentEventPage({
      schemaVersion: 1,
      experimentId,
      items: [unknown, benchmarkEventFixture(2)],
      nextCursor: 2,
      highWaterMark: 2,
      terminal: false,
    });
    expect(page.items[0]?.kind).toBe("future.phase.v9");
    expect(() =>
      parseBenchmarkExperimentEventPage({
        schemaVersion: 1,
        experimentId,
        items: [benchmarkEventFixture(1), benchmarkEventFixture(3)],
        nextCursor: 3,
        highWaterMark: 3,
        terminal: false,
      }),
    ).toThrow(/not continuous/);
  });
});
