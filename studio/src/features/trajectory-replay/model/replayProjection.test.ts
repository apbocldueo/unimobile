import { beforeEach, describe, expect, it } from "vitest";
import type { ReplayEnvelope, ReplayMoment } from "@/entities/replay";
import {
  projectReplay,
  replayMilestoneCursors,
  reduceReplayMoment,
  selectFailureTargets,
  selectPhoneFrame,
} from "./replayProjection";
import { useReplayPlaybackStore } from "./playback.store";
import { replayDelayMs } from "../lib/playbackTiming";
import { layoutReplayGraph } from "../lib/dagreLayout";

/** Build one normalized moment with explicit causal facts. */
function moment(
  causalIndex: number,
  sourceSequence: number,
  kind: string,
  activationId: string,
  overrides: Partial<ReplayMoment> = {},
): ReplayMoment {
  return {
    momentId: `moment-${causalIndex}`,
    causalIndex,
    sourceKind: "agent_graph",
    sourceSequence,
    timestamp: causalIndex,
    phase: "graph_kernel",
    kind,
    role: "reasoning",
    component: "reasoning",
    nodeId: "reasoning",
    nodePath: "loop/body/reasoning",
    activationId,
    parentActivationId: "",
    loopPath: "loop",
    loopIteration: 0,
    interactionStep: 0,
    durationMs: null,
    payload: {},
    observationId: null,
    actionId: null,
    artifactIds: [],
    ...overrides,
  };
}

/** Build a compact complete envelope for pure projection tests. */
function envelope(moments: ReplayMoment[]): ReplayEnvelope {
  return {
    schemaVersion: 1,
    runId: "projection-run",
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
      agentId: "agent-1",
      revisionId: null,
      contractVersion: "1.1",
      canonicalHash: "sha256:" + "1".repeat(64),
      graphStatus: "available",
      agentGraph: { nodes: [], edges: [] },
      graphNodes: [
        {
          id: "reasoning",
          kind: "component",
          role: "reasoning",
          lifecycle: "per_step",
          primary: false,
        },
        {
          id: "never-ran",
          kind: "component",
          role: "verifier",
          lifecycle: "post_action",
          primary: false,
        },
      ],
      graphEdges: [],
      presentation: null,
      sourceMap: [],
      providerIdentities: [],
    },
    result: {
      status: "success",
      kernelStatus: "success",
      error: "",
      stepCount: 1,
      activationCount: 2,
      interactionCount: 2,
      usage: {},
    },
    moments,
    observations: [
      {
        observationId: "observation-0",
        sequence: 0,
        interactionStep: 0,
        screenshotArtifactId: "artifact-" + "1".repeat(32),
        uiArtifactId: null,
        width: 1080,
        height: 2400,
        platform: "fake",
        deviceId: "device-sha256:fixture",
        overlay: [],
      },
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
    actions: [],
    benchmark: {
      experimentId: "experiment-1",
      taskId: "task-1",
      agentId: "agent-1",
      repeat: 0,
      outcome: "fail",
      identities: {},
      phases: [{ phase: "evaluation", status: "failure", durationMs: 1, errorCode: "", message: "", evidence: {} }],
      evaluation: { isPass: false },
    },
    artifacts: [],
    availability: {
      screenshots: { state: "available", reasonCode: "", detail: "" },
    },
    integrity: [],
  };
}

describe("Replay pure projection", () => {
  it("distinguishes evidence that is available later from evidence never captured", () => {
    const projected = projectReplay(envelope([]));
    expect(selectPhoneFrame(projected).state).toBe("pending");

    projected.availability.screenshots = {
      state: "not_captured",
      reasonCode: "source_did_not_capture",
      detail: "",
    };
    expect(selectPhoneFrame(projected).state).toBe("not_captured");
  });

  it("is deterministic, idempotent, and preserves activation history", () => {
    const moments = [
      moment(0, 1, "start", "activation-0"),
      moment(1, 2, "complete", "activation-0"),
      moment(2, 3, "feedback_latched", "activation-0"),
      moment(3, 4, "start", "activation-1", { loopIteration: 1 }),
      moment(4, 5, "complete", "activation-1", { loopIteration: 1 }),
    ];
    const first = projectReplay(envelope(moments));
    const second = projectReplay(envelope(moments));
    expect(second).toEqual(first);
    expect(first.activationOrder).toEqual(["activation-0", "activation-1"]);
    expect(first.nodesById.reasoning?.executionCount).toBe(2);
    expect(first.nodesById.reasoning?.feedbackCount).toBe(1);
    expect(first.nodesById["never-ran"]?.status).toBe("not_observed");
    const duplicated = reduceReplayMoment(first, moments[4]!);
    expect(duplicated).toBe(first);
  });

  it("stops at an unverified sequence gap and preserves split outcomes", () => {
    const projected = projectReplay(
      envelope([
        moment(0, 1, "start", "activation-0"),
        moment(1, 3, "complete", "activation-0"),
      ]),
    );
    expect(projected.integrityState).toBe("partial");
    expect(projected.accepting).toBe(false);
    expect(projected.activationsById["activation-0"]?.status).toBe("running");
    expect(projected.agentStatus).toBe("success");
    expect(projected.benchmarkOutcome).toBe("fail");
    expect(selectFailureTargets(projected)[0]?.kind).toBe("benchmark_evaluation");
  });

  it("selects missing current screenshots without pretending the old one is current", () => {
    const projected = projectReplay(
      envelope([
        moment(0, 1, "start", "activation-0"),
        moment(1, 2, "complete", "activation-0", {
          observationId: "observation-0",
        }),
        moment(2, 3, "start", "activation-1", {
          interactionStep: 1,
        }),
        moment(3, 4, "complete", "activation-1", {
          interactionStep: 1,
          observationId: "observation-1",
        }),
      ]),
    );
    const frame = selectPhoneFrame(projected);
    expect(frame.state).toBe("missing");
    expect(frame.observation?.observationId).toBe("observation-1");
    expect(frame.screenshotArtifactId).toBeNull();
  });

  it("moves the phone from first frame through stale feedback to the second terminal frame", () => {
    const moments = [
      moment(0, 1, "complete", "", {
        sourceKind: "observation",
        nodeId: "observe",
        nodePath: "observe",
        interactionStep: 0,
        observationId: "observation-0",
      }),
      moment(1, 2, "complete", "", {
        sourceKind: "action",
        nodeId: "action_executor",
        nodePath: "action_executor",
        interactionStep: 0,
        actionId: "action-0",
      }),
      moment(2, 3, "feedback_latched", "", {
        sourceKind: "action",
        nodeId: "action_executor",
        nodePath: "action_executor",
        interactionStep: 1,
        loopIteration: 1,
      }),
      moment(3, 4, "complete", "", {
        sourceKind: "observation",
        nodeId: "observe",
        nodePath: "observe",
        interactionStep: 1,
        observationId: "observation-1",
      }),
      moment(4, 5, "complete", "", {
        sourceKind: "action",
        nodeId: "action_executor",
        nodePath: "action_executor",
        interactionStep: 1,
        actionId: "action-1",
      }),
    ];
    const fixture = envelope(moments);
    fixture.observations[1] = {
      ...fixture.observations[1]!,
      screenshotArtifactId: "artifact-" + "2".repeat(32),
    };
    fixture.actions = [
      {
        actionId: "action-0",
        sequence: 0,
        interactionStep: 0,
        status: "success",
        actionType: "tap",
        effectPerformed: true,
        effectKind: "ui_input",
        terminalStatus: null,
        message: "",
        error: "",
        artifactId: null,
      },
      {
        actionId: "action-1",
        sequence: 1,
        interactionStep: 1,
        status: "terminal",
        actionType: "done",
        effectPerformed: false,
        effectKind: "none",
        terminalStatus: "success",
        message: "",
        error: "",
        artifactId: null,
      },
    ];

    expect(selectPhoneFrame(projectReplay(fixture, 0))).toMatchObject({
      state: "available",
      screenshotArtifactId: "artifact-" + "1".repeat(32),
    });
    expect(selectPhoneFrame(projectReplay(fixture, 2))).toMatchObject({
      state: "stale",
      isHistorical: true,
    });
    expect(selectPhoneFrame(projectReplay(fixture, 3))).toMatchObject({
      state: "available",
      screenshotArtifactId: "artifact-" + "2".repeat(32),
    });
    expect(selectPhoneFrame(projectReplay(fixture, 4))).toMatchObject({
      state: "available",
      observation: { observationId: "observation-1" },
    });
  });

  it("keeps first-observation failure and corrupt evidence truthful", () => {
    const failed = envelope([
      moment(0, 1, "start", "activation-observe", {
        sourceKind: "observation",
        nodeId: "observe",
      }),
      moment(1, 2, "failure", "activation-observe", {
        sourceKind: "observation",
        nodeId: "observe",
      }),
    ]);
    failed.result = { ...failed.result, status: "failure", error: "capture failed" };
    failed.availability.screenshots = {
      state: "not_captured",
      reasonCode: "capture_failed",
      detail: "",
    };
    expect(selectPhoneFrame(projectReplay(failed)).state).toBe("not_captured");
    failed.availability.screenshots = {
      state: "corrupt",
      reasonCode: "checksum_mismatch",
      detail: "",
    };
    expect(selectPhoneFrame(projectReplay(failed)).state).toBe("corrupt");
  });

  it("aggregates repeated graph activations without blaming an unactivated Output", () => {
    const fixture = envelope([
      moment(0, 1, "start", "observe-1", {
        nodeId: "observe",
        nodePath: "observe",
      }),
      moment(1, 2, "complete", "observe-1", {
        nodeId: "observe",
        nodePath: "observe",
      }),
      moment(2, 3, "start", "execute-1", {
        nodeId: "action_executor",
        nodePath: "action_executor",
      }),
      moment(3, 4, "complete", "execute-1", {
        nodeId: "action_executor",
        nodePath: "action_executor",
      }),
      moment(4, 5, "feedback_latched", "execute-1", {
        nodeId: "action_executor",
        nodePath: "action_executor",
        loopIteration: 1,
      }),
      moment(5, 6, "start", "observe-2", {
        nodeId: "observe",
        nodePath: "observe",
        loopIteration: 1,
      }),
      moment(6, 7, "complete", "observe-2", {
        nodeId: "observe",
        nodePath: "observe",
        loopIteration: 1,
      }),
    ]);
    fixture.snapshot.graphNodes.push({
      id: "output",
      kind: "output",
      role: "",
      lifecycle: "terminal",
      primary: false,
    });
    fixture.result = {
      ...fixture.result,
      status: "failure",
      error: "Agent ended at a non-output failure boundary",
    };

    const projected = projectReplay(fixture);
    expect(projected.nodesById.observe).toMatchObject({ executionCount: 2 });
    expect(projected.nodesById.action_executor).toMatchObject({ feedbackCount: 1 });
    expect(projected.nodesById.output).toMatchObject({ status: "not_observed" });
    expect(selectFailureTargets(projected)[0]).toMatchObject({
      kind: "agent_terminal",
      nodePath: null,
    });
  });

  it("prioritizes the first formal activation failure", () => {
    const projected = projectReplay(
      envelope([
        moment(0, 1, "start", "activation-0"),
        moment(1, 2, "failure", "activation-0"),
      ]),
    );
    expect(selectFailureTargets(projected)[0]).toMatchObject({
      kind: "activation",
      activationId: "activation-0",
      cursor: 1,
    });
  });
});

describe("Replay interaction model", () => {
  beforeEach(() => {
    useReplayPlaybackStore.setState({
      runId: null,
      cursor: -1,
      maxCursor: -1,
      isPlaying: false,
      speed: 1,
      autoFollow: true,
      lockedActivationId: null,
      selectedMomentId: null,
    });
  });

  it("supports speed, milestone stepping, lock, and return-to-current", () => {
    const store = useReplayPlaybackStore.getState();
    store.initialize("run-store", 8);
    useReplayPlaybackStore.getState().setSpeed(2);
    useReplayPlaybackStore.getState().step([0, 3, 8], 1);
    expect(useReplayPlaybackStore.getState().cursor).toBe(0);
    useReplayPlaybackStore.getState().lockActivation("activation-1");
    expect(useReplayPlaybackStore.getState().autoFollow).toBe(false);
    useReplayPlaybackStore.getState().returnToCurrent();
    expect(useReplayPlaybackStore.getState().lockedActivationId).toBeNull();
    expect(useReplayPlaybackStore.getState().autoFollow).toBe(true);
    expect(useReplayPlaybackStore.getState().speed).toBe(2);
  });

  it("bounds visual delay while preserving recorded timestamps", () => {
    const current = moment(0, 1, "start", "activation-0", { timestamp: 1 });
    const next = moment(1, 2, "complete", "activation-0", { timestamp: 20 });
    expect(replayDelayMs(current, next, 1)).toBe(1600);
    expect(replayDelayMs(current, next, 2)).toBe(800);
    expect(current.timestamp).toBe(1);
    expect(next.timestamp).toBe(20);
  });

  it("produces deterministic Dagre positions from reordered topology", () => {
    const nodes = [
      { id: "b", kind: "component", role: "", lifecycle: "", primary: false },
      { id: "a", kind: "component", role: "", lifecycle: "", primary: false },
    ];
    const edges = [
      { id: "edge-1", sourceNode: "a", targetNode: "b", kind: "data" },
    ];
    const positions = layoutReplayGraph(nodes, edges);
    expect(positions).toEqual(layoutReplayGraph([...nodes].reverse(), [...edges].reverse()));
    expect(positions.b!.y).toBeGreaterThan(positions.a!.y);
  });

  it("steps through observation and action milestones without promoting every event", () => {
    const moments = [
      moment(0, 1, "start", "activation-0"),
      moment(1, 2, "debug_payload", "activation-0"),
      moment(2, 3, "captured", "activation-0", { sourceKind: "observation" }),
      moment(3, 4, "executed", "activation-0", { sourceKind: "action" }),
      moment(4, 5, "complete", "activation-0"),
    ];
    expect(replayMilestoneCursors(moments)).toEqual([0, 2, 3, 4]);
  });
});
