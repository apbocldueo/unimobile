import type { ReplayEnvelope } from "../replay.schema";

const GRAPH_HASH = `sha256:${"1".repeat(64)}`;

/** Build one deterministic complete Replay fixture for frontend presentation tests. */
export function createReplayEnvelopeFixture(
  overrides: Partial<ReplayEnvelope> = {},
): ReplayEnvelope {
  const base: ReplayEnvelope = {
    schemaVersion: 1,
    runId: "focused-replay-fixture",
    importedAt: 1,
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
      agentId: "research-agent",
      revisionId: "revision-1",
      contractVersion: "1.1",
      canonicalHash: GRAPH_HASH,
      graphStatus: "available",
      agentGraph: {
        nodes: [
          { id: "observe", kind: "component", role: "observation_provider" },
          { id: "reason", kind: "component", role: "reasoning" },
          { id: "act", kind: "component", role: "action_executor" },
        ],
        edges: [
          {
            source: { node: "observe", port: "observation" },
            target: { node: "reason", port: "observation" },
            kind: "data",
          },
          {
            source: { node: "reason", port: "decision" },
            target: { node: "act", port: "action" },
            kind: "data",
          },
        ],
      },
      graphNodes: [
        { id: "observe", kind: "component", role: "observation_provider", lifecycle: "", primary: false },
        { id: "reason", kind: "component", role: "reasoning", lifecycle: "", primary: true },
        { id: "act", kind: "component", role: "action_executor", lifecycle: "", primary: false },
      ],
      graphEdges: [
        { id: "observe->reason", sourceNode: "observe", targetNode: "reason", kind: "data" },
        { id: "reason->act", sourceNode: "reason", targetNode: "act", kind: "data" },
      ],
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
      interactionCount: 1,
      usage: {},
    },
    moments: [
      {
        momentId: "reason-start",
        causalIndex: 0,
        sourceKind: "agent_graph",
        sourceSequence: 1,
        timestamp: 1,
        phase: "graph_kernel",
        kind: "start",
        role: "reasoning",
        component: "reasoning",
        nodeId: "reason",
        nodePath: "reason",
        activationId: "activation-reason",
        parentActivationId: "",
        loopPath: "",
        loopIteration: null,
        interactionStep: 1,
        durationMs: null,
        payload: { task: "打开设置", observation: "设置页" },
        observationId: null,
        actionId: null,
        artifactIds: [],
      },
      {
        momentId: "reason-complete",
        causalIndex: 1,
        sourceKind: "agent_graph",
        sourceSequence: 2,
        timestamp: 2,
        phase: "graph_kernel",
        kind: "complete",
        role: "reasoning",
        component: "reasoning",
        nodeId: "reason",
        nodePath: "reason",
        activationId: "activation-reason",
        parentActivationId: "",
        loopPath: "",
        loopIteration: null,
        interactionStep: 1,
        durationMs: 12,
        payload: { decision: "点击设置", result: "decision-ready" },
        observationId: "observation-1",
        actionId: "action-1",
        artifactIds: [],
      },
    ],
    observations: [
      {
        observationId: "observation-1",
        sequence: 1,
        interactionStep: 1,
        screenshotArtifactId: null,
        uiArtifactId: null,
        width: 1080,
        height: 2400,
        platform: "fake",
        deviceId: "device-sha256:fixture",
        overlay: [],
      },
    ],
    actions: [
      {
        actionId: "action-1",
        sequence: 1,
        interactionStep: 1,
        status: "success",
        actionType: "tap",
        effectPerformed: true,
        effectKind: "device_input",
        terminalStatus: null,
        message: "",
        error: "",
        artifactId: null,
      },
    ],
    benchmark: {
      experimentId: "experiment-1",
      taskId: "task-1",
      agentId: "research-agent",
      repeat: 0,
      outcome: "fail",
      identities: {},
      phases: [
        {
          phase: "evaluation",
          status: "failure",
          durationMs: 2,
          errorCode: "evaluation.failed",
          message: "目标状态未满足",
          evidence: { isPass: false },
        },
      ],
      evaluation: { isPass: false },
    },
    artifacts: [],
    availability: {
      agentGraph: { state: "available", reasonCode: "", detail: "" },
      screenshots: { state: "missing", reasonCode: "", detail: "" },
      uiXml: { state: "not_captured", reasonCode: "", detail: "" },
      modelResponse: { state: "not_captured", reasonCode: "", detail: "" },
      prompt: { state: "excluded", reasonCode: "policy", detail: "" },
      debugPayload: { state: "available", reasonCode: "", detail: "" },
    },
    integrity: [],
  };
  return { ...base, ...overrides };
}

/** Build a historical real-Android projection without upgrading it to fresh evidence. */
export function createHistoricalAndroidReplayFixture(): ReplayEnvelope {
  return createReplayEnvelopeFixture({
    provenance: "native_benchmark_task_run",
    evidenceOrigin: {
      schemaVersion: 1,
      acquisition: "replay_projection",
      environment: "real_android",
      deviceProfileId: "android-accepted",
      deviceChecks: [],
      realDeviceEvidence: false,
    },
  });
}
