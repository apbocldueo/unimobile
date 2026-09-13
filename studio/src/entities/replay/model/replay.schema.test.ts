import { describe, expect, it } from "vitest";
import { parseReplayEnvelope, parseReplayPage } from "./replay.schema";

/** Build a minimal strict transport envelope for parser tests. */
function rawEnvelope(): Record<string, unknown> {
  return {
    schemaVersion: 1,
    runId: "run-parser",
    importedAt: 10,
    provenance: "fake_contract_fixture",
    evidenceOrigin: {
      schemaVersion: 1,
      acquisition: "contract_fixture",
      environment: "fake_device",
      deviceProfileId: "fixture-android",
      deviceChecks: [],
      realDeviceEvidence: false,
    },
    integrityState: "complete",
    snapshot: {
      agentId: "agent-1",
      revisionId: null,
      contractVersion: "1.1",
      canonicalHash: null,
      graphStatus: "not_captured",
      agentGraph: null,
      presentation: null,
      sourceMap: [],
      providerIdentities: [],
    },
    result: {
      status: "success",
      kernelStatus: "success",
      error: "",
      stepCount: 1,
      activationCount: 1,
      interactionCount: 0,
      usage: {},
    },
    moments: [
      {
        momentId: "moment-1",
        causalIndex: 0,
        sourceKind: "agent_graph",
        sourceSequence: 1,
        timestamp: 1,
        phase: "graph_kernel",
        kind: "start",
        role: "reasoning",
        component: "reasoning",
        nodeId: "reasoning",
        nodePath: "reasoning",
        activationId: "activation-1",
        parentActivationId: "",
        loopPath: "",
        loopIteration: null,
        interactionStep: 0,
        durationMs: null,
        payload: {},
        observationId: null,
        actionId: null,
        artifactIds: [],
      },
    ],
    observations: [],
    actions: [],
    benchmark: null,
    artifacts: [],
    availability: {
      screenshots: { state: "not_captured", reasonCode: "", detail: "" },
    },
    integrity: [],
  };
}

describe("Replay DTO parser", () => {
  it("parses the strict envelope and list page", () => {
    const envelope = parseReplayEnvelope(rawEnvelope());
    expect(envelope.runId).toBe("run-parser");
    expect(envelope.moments[0]?.activationId).toBe("activation-1");
    const page = parseReplayPage({
      schemaVersion: 1,
      items: [
        {
          runId: "run-parser",
          agentId: "agent-1",
          agentStatus: "success",
          benchmarkOutcome: "fail",
          provenance: "fake_contract_fixture",
          evidenceOrigin: {
            schemaVersion: 1,
            acquisition: "replay_projection",
            environment: "fake_device",
            deviceProfileId: "fixture-android",
            deviceChecks: [],
            realDeviceEvidence: false,
          },
          integrityState: "complete",
          evidenceCompleteness: 80,
          importedAt: 10,
        },
      ],
      nextCursor: null,
    });
    expect(page.items[0]?.benchmarkOutcome).toBe("fail");
    expect(envelope.evidenceOrigin.environment).toBe("fake_device");
    expect(page.items[0]?.evidenceOrigin.acquisition).toBe("replay_projection");
  });

  it("accepts the native Benchmark TaskRun Replay provenance", () => {
    const raw = rawEnvelope();
    raw.provenance = "native_benchmark_task_run";
    raw.evidenceOrigin = {
      schemaVersion: 1,
      acquisition: "replay_projection",
      environment: "fake_device",
      deviceProfileId: "acceptance-fake",
      deviceChecks: [],
      realDeviceEvidence: false,
    };

    const envelope = parseReplayEnvelope(raw);

    expect(envelope.provenance).toBe("native_benchmark_task_run");
    expect(envelope.evidenceOrigin.environment).toBe("fake_device");
  });

  it("rejects unknown fields and causal reordering", () => {
    expect(() => parseReplayEnvelope({ ...rawEnvelope(), hostPath: "/tmp/x" })).toThrow(
      "hostPath",
    );
    const raw = rawEnvelope();
    raw.moments = [
      { ...(raw.moments as Record<string, unknown>[])[0], causalIndex: 2 },
      {
        ...(raw.moments as Record<string, unknown>[])[0],
        momentId: "moment-2",
        causalIndex: 1,
        sourceSequence: 2,
      },
    ];
    expect(() => parseReplayEnvelope(raw)).toThrow("causalIndex");
  });
});
