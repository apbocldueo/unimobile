import { describe, expect, it } from "vitest";
import type {
  ActivationProjection,
  DebugPayload,
  ReplayProjection,
  RunSnapshot,
} from "@/entities/run";
import { createReplayProjection } from "@/entities/run";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { selectRunStory } from "./runStoryPresenter";

/** Build one exact activation projection for presenter tests. */
function activation(
  activationId: string,
  nodeId: string,
  role: string,
  interactionStep: number,
  startCursor: number,
  payloadHistory: ActivationProjection["payloadHistory"],
): ActivationProjection {
  return {
    activationId,
    nodeId,
    nodePath: nodeId,
    role,
    component: role,
    parentActivationId: "",
    loopPath: "",
    loopIteration: null,
    interactionStep,
    status: "success",
    startCursor,
    endCursor: startCursor + 1,
    durationMs: 12,
    payloadHistory,
  };
}

/** Build one typed activation-scoped Debug Payload using actual Studio fields. */
function debugPayload(
  activationId: string,
  role: string,
  inputSummary: DebugPayload["inputSummary"],
  outputSummary: DebugPayload["outputSummary"],
): DebugPayload {
  return {
    schemaVersion: 1,
    debugId: `debug-${activationId}`,
    runId: "run-story",
    nodePath: activationId,
    activationId,
    componentIdentity: `component-${role}`,
    role,
    stage: "complete",
    task: "打开系统设置",
    inputSummary,
    outputSummary,
    durationMs: 12,
    error: "",
    usage: {},
    artifactIds: [],
    evidenceRefs: role === "reasoning" ? {
      modelResponse: {
        schemaVersion: 1,
        kind: "model_response",
        artifactId: "model-response",
        availability: "available",
        contentType: "application/json",
        size: 20,
        originalSize: null,
        sha256: null,
        provenance: "native_studio_run",
        causalIdentity: activationId,
        hidden: false,
      },
    } : {},
    availability: {
      debugPayload: "available",
      modelResponse: role === "reasoning" ? "available" : "not_captured",
      prompt: "hidden",
    },
    diagnostics: [],
  };
}

/** Build a two-interaction capability Run prefix with exact generated mappings. */
function storyFixture(): { snapshot: RunSnapshot; projection: ReplayProjection } {
  const document = createEmptyStudioDocument("agent-1", "Studio Capability Test Agent", "document-1");
  const implementation = {
    policy: "single" as const,
    candidates: [{
      namespace: "agent.test",
      name: "fixture",
      version: "1",
      params: {},
      dependencies: {},
    }],
  };
  document.capabilities = [
    { canvasId: "perception-canvas", logicalId: "perception", family: "perception", lifecycle: "per_step", implementation },
    { canvasId: "reasoning-canvas", logicalId: "reasoning", family: "reasoning", lifecycle: "per_step", implementation },
    { canvasId: "memory-canvas", logicalId: "memory", family: "memory", lifecycle: "per_step", implementation },
    { canvasId: "action-canvas", logicalId: "action", family: "action_executor", lifecycle: "per_step", implementation },
  ];
  document.relations = [{
    canvasId: "feedback-relation",
    source: { ownerId: "action", portId: "result" },
    target: { ownerId: "perception", portId: "observation" },
    kind: "feedback",
    feedback: { predicate: { field: "ready", operator: "truthy" }, maxIterations: 2, onExhausted: "fail" },
  }];
  const snapshot: RunSnapshot = {
    agentId: "agent-1",
    revisionId: "revision-1",
    contractVersion: "1.1",
    canonicalHash: `sha256:${"a".repeat(64)}`,
    graphStatus: "available",
    agentGraph: null,
    graphNodes: [],
    graphEdges: [],
    presentation: null,
    sourceMap: [],
    capabilityDocument: document,
    projectionMap: [
      { graphKind: "node", graphId: "observe-generated", owner: { kind: "capability", ownerId: "perception" }, propertyPath: [] },
      { graphKind: "node", graphId: "perception-runtime", owner: { kind: "capability", ownerId: "perception" }, propertyPath: [] },
      { graphKind: "node", graphId: "reasoning-runtime", owner: { kind: "capability", ownerId: "reasoning" }, propertyPath: [] },
      { graphKind: "node", graphId: "memory-runtime", owner: { kind: "capability", ownerId: "memory" }, propertyPath: [] },
      { graphKind: "node", graphId: "request-generated", owner: { kind: "capability", ownerId: "action" }, propertyPath: [] },
      { graphKind: "node", graphId: "action-runtime", owner: { kind: "capability", ownerId: "action" }, propertyPath: [] },
      { graphKind: "node", graphId: "feedback-generated", owner: { kind: "relation", ownerId: "feedback-relation" }, propertyPath: [] },
    ],
    providerIdentities: [],
  };
  const projection = createReplayProjection(
    snapshot,
    { status: "success", kernelStatus: "success", error: "", stepCount: 2, activationCount: 8, interactionCount: 2, usage: {} },
    null,
    [
      { observationId: "observation-1", sequence: 1, interactionStep: 1, screenshotArtifactId: "screenshot-1", uiArtifactId: null, width: 1080, height: 2400, platform: "android", deviceId: "safe-device", overlay: [] },
      { observationId: "observation-2", sequence: 2, interactionStep: 2, screenshotArtifactId: null, uiArtifactId: null, width: 1080, height: 2400, platform: "android", deviceId: "safe-device", overlay: [] },
    ],
    [{ actionId: "action-1", sequence: 1, interactionStep: 1, status: "success", actionType: "launch_app", effectPerformed: true, effectKind: "app_launch", terminalStatus: null, message: "", error: "", artifactId: null }],
    {},
    "complete",
  );
  const activations = [
    activation("observe-1", "observe-generated", "observation_provider", 1, 0, [{ observation: "home" }, { result: "captured" }]),
    activation("perception-1", "perception-runtime", "perception", 1, 2, [{ observation: "home" }, { elements: ["Settings"] }]),
    activation("memory-1", "memory-runtime", "memory", 1, 4, [{ read: [] }, { write: "goal" }]),
    activation("reasoning-1", "reasoning-runtime", "reasoning", 1, 6, [{ task: "打开系统设置" }, { decision: "启动系统设置" }]),
    activation("request-1", "request-generated", "runtime_service", 1, 8, [{ action: "launch_app" }, { status: "ready" }]),
    activation("action-1", "action-runtime", "action_executor", 1, 10, [{ action: "launch_app" }, { result: "success" }]),
    activation("feedback-1", "feedback-generated", "runtime_service", 1, 12, [{ ready: true }, { feedback: "continue" }]),
    activation("perception-2", "perception-runtime", "perception", 2, 14, [{ observation: "settings" }, { representation: "系统设置已打开" }]),
  ];
  projection.activationOrder = activations.map((item) => item.activationId);
  projection.activationsById = Object.fromEntries(activations.map((item) => [item.activationId, item]));
  projection.currentActivationId = "perception-2";
  projection.currentInteractionStep = 2;
  projection.cursor = 15;
  projection.visibleObservationIds = ["observation-1", "observation-2"];
  projection.currentObservationId = "observation-2";
  projection.visibleActionIds = ["action-1"];
  projection.latestActionId = "action-1";
  projection.debugByActivationId = {
    "perception-1": [debugPayload("perception-1", "perception", { observation: "home" }, { elements: ["Settings"] })],
    "memory-1": [debugPayload("memory-1", "memory", { read: [] }, { write: "goal" })],
    "reasoning-1": [debugPayload("reasoning-1", "reasoning", { perception: "Settings icon", memory: "goal" }, { decision: "启动系统设置", action: { type: "launch_app", params: { app: "settings" } } })],
    "action-1": [debugPayload("action-1", "action_executor", { action: "launch_app" }, { result: "success", effect: "app_launch" })],
    "perception-2": [debugPayload("perception-2", "perception", { observation: "settings" }, { representation: "系统设置已打开" })],
  };
  return { snapshot, projection };
}

describe("selectRunStory", () => {
  it("groups generated work into capability owners and preserves two interactions", () => {
    const { snapshot, projection } = storyFixture();
    const story = selectRunStory(snapshot, projection);
    expect(story.steps.map((step) => `${step.interactionStep}:${step.role}`)).toEqual([
      "1:perception",
      "1:memory",
      "1:reasoning",
      "1:action_executor",
      "1:feedback",
      "2:perception",
    ]);
    expect(story.steps.find((step) => step.role === "perception")?.activationIds).toContain("observe-1");
    expect(story.steps.find((step) => step.role === "action_executor")?.activationIds).toEqual(["request-1", "action-1"]);
  });

  it("separates role inputs and outputs while preserving evidence policy", () => {
    const { snapshot, projection } = storyFixture();
    const story = selectRunStory(snapshot, projection);
    const reasoning = story.steps.find((step) => step.role === "reasoning")!;
    expect(reasoning.inputs.map((fact) => fact.key)).toContain("perception");
    expect(reasoning.outputs.map((fact) => fact.key)).toContain("decision");
    expect(reasoning.modelResponse?.artifactId).toBe("model-response");
    expect(reasoning.promptAvailability).toBe("hidden");
    expect(JSON.stringify([reasoning.inputs, reasoning.outputs])).not.toContain("prompt");
    const action = story.steps.find((step) => step.role === "action_executor")!;
    expect(action.summary).toContain("launch_app");
    expect(action.outputs.find((fact) => fact.key === "effect")?.value).toContain("app_launch");
  });

  it("keeps runtime identities out of reader-facing summaries and facts", () => {
    const { snapshot, projection } = storyFixture();
    projection.debugByActivationId["memory-1"]![0]!.outputSummary = {
      activationId: "activation-internal-123456",
      result: "a2-871d9192",
      component: "studio_generated.perception.observe",
      durationMs: 12.4,
      canonicalHash: `sha256:${"b".repeat(64)}`,
    };
    const story = selectRunStory(snapshot, projection);
    const memory = story.steps.find((step) => step.role === "memory")!;
    expect(memory.summary).toBe("goal");
    expect(JSON.stringify(memory.outputs)).not.toContain("871d9192");
    expect(JSON.stringify(memory.outputs)).not.toContain("activation-internal");
    expect(JSON.stringify(memory.outputs)).not.toContain("studio_generated");
    expect(JSON.stringify(memory.outputs)).not.toContain("durationMs");
    expect(JSON.stringify(memory.outputs)).not.toContain("sha256");
  });

  it("unwraps typed summary envelopes instead of presenting event bookkeeping", () => {
    const { snapshot, projection } = storyFixture();
    projection.debugByActivationId["perception-1"]![0]!.inputSummary = {
      interaction_step: 1,
      kind: "start",
      phase: "graph_kernel",
      payload: {
        inputs: {
          keys: ["observation"],
          type: "dict",
          values: { observation: { interaction_step: 1, platform: "android", type: "DeviceObservation" } },
        },
      },
    };
    const story = selectRunStory(snapshot, projection);
    const perception = story.steps.find((step) => step.role === "perception")!;
    expect(perception.inputs.map((fact) => fact.key)).toContain("observation");
    expect(JSON.stringify(perception.inputs)).not.toContain("graph_kernel");
    expect(JSON.stringify(perception.inputs)).not.toContain("interaction_step");
  });

  it("does not guess an unmapped generated activation but supports exact external roles", () => {
    const { snapshot, projection } = storyFixture();
    const generated = activation("generated-unmapped", "generated-unmapped", "runtime_service", 2, 16, [{ id: "internal" }, { status: "done" }]);
    const external = activation("external-1", "external", "custom_research_tool", 2, 18, [{ query: "settings" }, { result: "found" }]);
    projection.activationOrder.push(generated.activationId, external.activationId);
    projection.activationsById[generated.activationId] = generated;
    projection.activationsById[external.activationId] = external;
    const story = selectRunStory(snapshot, projection);
    expect(story.unmappedActivationIds).toContain("generated-unmapped");
    expect(story.unmappedActivationIds).not.toContain("external-1");
    expect(story.steps.some((step) => step.ownerId === "generated-unmapped")).toBe(false);
    expect(story.steps.some((step) => step.ownerId === "external")).toBe(true);
  });

  it("is deterministic for the same prefix and adds terminal facts only when visible", () => {
    const { snapshot, projection } = storyFixture();
    const first = selectRunStory(snapshot, projection);
    const second = selectRunStory(snapshot, { ...projection });
    expect(second).toEqual(first);
    expect(first.steps.some((step) => step.role === "terminal")).toBe(false);
    const terminal = selectRunStory(snapshot, projection, { terminalVisible: true, agentStatus: "success" });
    expect(terminal.steps.at(-1)?.role).toBe("terminal");
    expect(terminal.steps.at(-1)?.summary).toContain("已完成");
  });

  it("bounds long stories without changing exact unmapped audit identities", () => {
    const { snapshot, projection } = storyFixture();
    for (let index = 0; index < 20; index += 1) {
      const item = activation(`reason-${index}`, "reasoning-runtime", "reasoning", index + 3, 20 + index * 2, [{ task: index }, { decision: index }]);
      projection.activationOrder.push(item.activationId);
      projection.activationsById[item.activationId] = item;
    }
    const story = selectRunStory(snapshot, projection, { maximumSteps: 10 });
    expect(story.steps).toHaveLength(10);
    expect(story.truncatedStepCount).toBeGreaterThan(0);
  });
});
