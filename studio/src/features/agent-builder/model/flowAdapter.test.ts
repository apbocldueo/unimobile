import { describe, expect, it } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import type { ComponentCatalog } from "@/entities/component-catalog";
import { defaultFeedbackPolicy, documentToFlow, hasOrdinaryReturnPath, validateBuilderConnection } from "./flowAdapter";

import { connectionCandidateHandleIds } from "./connectionCandidates";

const catalog: ComponentCatalog = {
  schemaVersion: 1,
  catalogVersion: "sha256:test",
  diagnostics: [],
  capabilityFamilies: [
    { family: "reasoning", label: "Reasoning", extension: false, availableImplementationCount: 1 },
    { family: "action_executor", label: "Action Executor", extension: false, availableImplementationCount: 1 },
  ],
  components: [
    {
      identifier: "agent.reasoning:reason@1",
      namespace: "agent.reasoning", name: "reason", version: "1", providerId: "test",
      placement: "agent_capability", capabilityFamily: "reasoning",
      contract: { ref: { id: "zhixing.core.reasoning", version: "1.0" }, ports: [
        { id: "task", direction: "input", dataTypes: ["task_input"], required: true, cardinality: "single" },
        { id: "action", direction: "output", dataTypes: ["action"], required: false, cardinality: "single" },
      ], adapter: "core_role", sideEffect: "none", idempotent: true },
      category: "core_agent", role: "reasoning", configSchema: {}, dependencySlots: [],
      availability: { available: true, extra: "", errorType: "" }, capabilities: {}, provenance: {}, display: { label: "Reasoning", group: "reasoning" },
    },
    {
      identifier: "studio.capability:action_executor@1",
      namespace: "studio.capability", name: "action_executor", version: "1", providerId: "test",
      placement: "agent_capability", capabilityFamily: "action_executor",
      termination: { sourcePort: "result" },
      contract: { ref: { id: "zhixing.core.action_executor", version: "1.0" }, ports: [
        { id: "action", direction: "input", dataTypes: ["action"], required: true, cardinality: "single" },
        { id: "result", direction: "output", dataTypes: ["action_result"], required: false, cardinality: "single" },
      ], adapter: "core_role", sideEffect: "device_action", idempotent: false },
      category: "core_agent", role: "action_executor", configSchema: {}, dependencySlots: [],
      availability: { available: true, extra: "", errorType: "" }, capabilities: {}, provenance: {}, display: { label: "Action Executor", group: "action_executor" },
    },
    {
      identifier: "llm:provider@1", namespace: "llm", name: "provider", version: "1", providerId: "test",
      placement: "dependency_only",
      contract: { ref: { id: "llm", version: "1" }, ports: [], adapter: "typed_invoke", sideEffect: "read", idempotent: true },
      category: "runtime_service", configSchema: {}, dependencySlots: [], availability: { available: true, extra: "", errorType: "" }, capabilities: {}, provenance: {}, display: { label: "LLM", group: "llm" },
    },
  ],
};

/** Create the two-component graph used to exercise connection constraints. */
function document() {
  const value = createEmptyStudioDocument("agent-test", "Test", "document-test");
  value.capabilities = [
    { canvasId: "reason", logicalId: "reason", family: "reasoning", lifecycle: "per_step", implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "reason", version: "1", params: {}, dependencies: {} }] } },
    { canvasId: "action", logicalId: "action", family: "action_executor", lifecycle: "per_step", primary: true, implementation: { policy: "single", candidates: [{ namespace: "studio.capability", name: "action_executor", version: "1", params: {}, dependencies: {} }] } },
  ];
  value.presentation.nodes.reason = { x: 100, y: 100, label: "Reasoning" };
  value.presentation.nodes.action = { x: 300, y: 100, label: "Action Executor" };
  return value;
}

describe("schema-3 flow projection", () => {
  it("projects only boundaries and capabilities and strips outcome text", () => {
    const value = document();
    value.presentation.nodes.output = { x: 500, y: 100, label: "DONE / FAIL" };
    value.relations.push({ canvasId: "terminal_relation", source: { ownerId: "action", portId: "result" }, target: { ownerId: "output", portId: "terminal" }, kind: "termination" });
    const flow = documentToFlow(value, catalog);
    expect(flow.nodes.map((item) => item.data.kind)).toEqual(["input", "output", "capability", "capability"]);
    expect(JSON.stringify(flow)).not.toMatch(/DONE|FAIL/i);
    expect(flow.edges[0]?.data?.semanticLabel).toBeUndefined();
  });

  it("accepts terminal connections only from formally declared implementations", () => {
    const value = document();
    expect(validateBuilderConnection({ document: value, catalog, sourceCanvasId: "action", sourcePortId: "result", targetCanvasId: "output", targetPortId: "connection" })).toEqual({ ok: true, kind: "termination" });
    expect(validateBuilderConnection({ document: value, catalog, sourceCanvasId: "reason", sourcePortId: "action", targetCanvasId: "output", targetPortId: "connection" })).toMatchObject({ ok: false, reason: expect.stringContaining("Action Executor") });
  });

  it("requires a forward ordinary path before authoring feedback", () => {
    const value = document();
    value.relations.push({
      canvasId: "forward",
      source: { ownerId: "action", portId: "result" },
      target: { ownerId: "reason", portId: "task" },
      kind: "data",
    });
    expect(hasOrdinaryReturnPath(value, "action", "reason")).toBe(true);
    expect(validateBuilderConnection({
      document: value,
      catalog,
      sourceCanvasId: "reason",
      sourcePortId: "action",
      targetCanvasId: "action",
      targetPortId: "action",
      requestedKind: "feedback",
    })).toEqual({ ok: true, kind: "feedback" });
    expect(defaultFeedbackPolicy()).toEqual({
      predicate: { field: "terminal_status", operator: "falsy" },
      maxIterations: 3,
      onExhausted: "fail",
    });
  });

  it("rejects feedback when the graph cannot return to its source", () => {
    const value = document();
    expect(validateBuilderConnection({
      document: value,
      catalog,
      sourceCanvasId: "reason",
      sourcePortId: "action",
      targetCanvasId: "action",
      targetPortId: "action",
      requestedKind: "feedback",
    })).toMatchObject({ ok: false, reason: expect.stringContaining("前向流程") });
  });
});


describe("connection candidate projection", () => {
  it("highlights compatible action input but excludes Output and wrong types", () => {
    const value = document();
    expect(connectionCandidateHandleIds({ document: value, catalog, nodes: documentToFlow(value, catalog).nodes,
      focus: { nodeId: "reason", handleId: "reason:output:action", handleType: "source", kind: "ordinary" },
    })).toEqual(["action:input:action"]);
  });

  it("supports starting at an input and excludes occupied single inputs", () => {
    const value = document();
    const nodes = documentToFlow(value, catalog).nodes;
    const focus = { nodeId: "action", handleId: "action:input:action", handleType: "target" as const, kind: "ordinary" as const };
    expect(connectionCandidateHandleIds({ document: value, catalog, nodes, focus })).toEqual(["reason:output:action"]);
    value.relations.push({ canvasId: "existing", source: { ownerId: "reason", portId: "action" }, target: { ownerId: "action", portId: "action" }, kind: "data" });
    expect(connectionCandidateHandleIds({ document: value, catalog, nodes, focus })).toEqual([]);
    expect(connectionCandidateHandleIds({ document: value, catalog, nodes, focus: { ...focus, ignoreEdgeId: "existing" } })).toEqual(["reason:output:action"]);
  });

  it("uses declared types rather than matching port names", () => {
    const value = document();
    const renamed = structuredClone(catalog);
    renamed.components[1]!.contract.ports[0]!.id = "incoming_action";
    expect(connectionCandidateHandleIds({ document: value, catalog: renamed, nodes: documentToFlow(value, renamed).nodes,
      focus: { nodeId: "reason", handleId: "reason:output:action", handleType: "source", kind: "ordinary" },
    })).toEqual(["action:input:incoming_action"]);
  });

  it("requires the feedback return path and clears candidates when cancelled", () => {
    const value = document();
    const nodes = documentToFlow(value, catalog).nodes;
    const focus = { nodeId: "reason", handleId: "reason:output:action", handleType: "source" as const, kind: "feedback" as const };
    expect(connectionCandidateHandleIds({ document: value, catalog, nodes, focus })).toEqual([]);
    value.relations.push({ canvasId: "forward", source: { ownerId: "action", portId: "result" }, target: { ownerId: "reason", portId: "task" }, kind: "data" });
    expect(connectionCandidateHandleIds({ document: value, catalog, nodes, focus })).toEqual(["action:input:action"]);
    expect(connectionCandidateHandleIds({ document: value, catalog, nodes, focus: null })).toEqual([]);
    expect(connectionCandidateHandleIds({ document: value, catalog: null, nodes, focus })).toEqual([]);
  });
});
