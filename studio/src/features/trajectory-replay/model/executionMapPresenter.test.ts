import { describe, expect, it } from "vitest";
import {
  createEmptyStudioDocument,
  STUDIO_CAPABILITY_AUTHORING_POLICY,
  STUDIO_CAPABILITY_LOWERING_PROFILE,
  type StudioFlowDocument,
} from "@/entities/agent-graph";
import {
  createReplayProjection,
  type ActivationProjection,
  type ReplayProjection,
  type RunSnapshot,
} from "@/entities/run";
import { presentRunExecutionMap } from "./executionMapPresenter";

/** Build one schema-3 fixture with a relation-owned generated runtime node. */
function executionMapSnapshot(): RunSnapshot {
  const empty = createEmptyStudioDocument("agent-1", "Agent", "document-1");
  const capabilityDocument: StudioFlowDocument = {
    ...empty,
    capabilities: [
      {
        canvasId: "canvas-perception",
        logicalId: "perception",
        family: "perception",
        lifecycle: "per_step",
        implementation: {
          policy: "single",
          candidates: [{
            namespace: "studio.capability",
            name: "perception",
            version: "1",
            params: {},
            dependencies: {},
          }],
        },
        primary: true,
      },
      {
        canvasId: "canvas-action",
        logicalId: "action_executor",
        family: "action_executor",
        lifecycle: "per_step",
        implementation: {
          policy: "single",
          candidates: [{
            namespace: "studio.capability",
            name: "action_executor",
            version: "1",
            params: {},
            dependencies: {},
          }],
        },
        primary: true,
      },
    ],
    relations: [
      {
        canvasId: "relation-input",
        source: { ownerId: "input", portId: "task" },
        target: { ownerId: "perception", portId: "task" },
        kind: "data",
      },
      {
        canvasId: "relation-action",
        source: { ownerId: "perception", portId: "observation" },
        target: { ownerId: "action_executor", portId: "observation" },
        kind: "activation",
      },
      {
        canvasId: "relation-feedback",
        source: { ownerId: "action_executor", portId: "result" },
        target: { ownerId: "perception", portId: "feedback" },
        kind: "feedback",
      },
      {
        canvasId: "relation-terminal",
        source: { ownerId: "action_executor", portId: "result" },
        target: { ownerId: "output", portId: "terminal" },
        kind: "termination",
      },
    ],
    presentation: {
      ...empty.presentation,
      nodes: {
        ...empty.presentation.nodes,
        "canvas-perception": { x: 700, y: 30, label: "Perception" },
        "canvas-action": { x: 30, y: 30, label: "Action Executor" },
      },
    },
  };
  return {
    agentId: "agent-1",
    revisionId: "revision-1",
    contractVersion: "1.1",
    canonicalHash: `sha256:${"a".repeat(64)}`,
    graphStatus: "available",
    agentGraph: {},
    graphNodes: [
      { id: "input", kind: "input", role: "", lifecycle: "on_run_start", primary: false },
      { id: "perception", kind: "component", role: "perception", lifecycle: "per_step", primary: true },
      { id: "generated.activation", kind: "router", role: "internal", lifecycle: "per_step", primary: false },
      { id: "action_executor", kind: "component", role: "action_executor", lifecycle: "per_step", primary: true },
      { id: "generated.terminal", kind: "condition", role: "internal", lifecycle: "per_step", primary: false },
      { id: "output", kind: "output", role: "", lifecycle: "terminal", primary: false },
    ],
    graphEdges: [],
    presentation: capabilityDocument.presentation,
    sourceMap: [],
    authoringPolicy: STUDIO_CAPABILITY_AUTHORING_POLICY,
    loweringProfile: STUDIO_CAPABILITY_LOWERING_PROFILE,
    capabilityHash: `sha256:${"b".repeat(64)}`,
    capabilityDocument,
    projectionMap: [
      { graphKind: "node", graphId: "input", owner: { kind: "input", ownerId: "input" }, propertyPath: [] },
      { graphKind: "node", graphId: "perception", owner: { kind: "capability", ownerId: "perception" }, propertyPath: [] },
      { graphKind: "node", graphId: "generated.activation", owner: { kind: "relation", ownerId: "relation-action" }, propertyPath: [] },
      { graphKind: "node", graphId: "action_executor", owner: { kind: "capability", ownerId: "action_executor" }, propertyPath: [] },
      { graphKind: "node", graphId: "generated.terminal", owner: { kind: "relation", ownerId: "relation-terminal" }, propertyPath: [] },
      { graphKind: "node", graphId: "output", owner: { kind: "output", ownerId: "output" }, propertyPath: [] },
    ],
    providerIdentities: [],
  };
}

/** Add one exact activation and its cumulative node facts to a projection. */
function observe(
  projection: ReplayProjection,
  activationId: string,
  nodeId: string,
  status: ActivationProjection["status"] = "success",
): void {
  projection.activationsById[activationId] = {
    activationId,
    nodeId,
    nodePath: nodeId,
    role: nodeId,
    component: nodeId,
    parentActivationId: "",
    loopPath: "",
    loopIteration: null,
    interactionStep: 1,
    status,
    startCursor: 0,
    endCursor: status === "running" ? null : 1,
    durationMs: status === "running" ? null : 1,
    payloadHistory: [],
  };
  projection.activationOrder.push(activationId);
  projection.nodesById[nodeId] = {
    nodeId,
    status,
    activationIds: [activationId],
    executionCount: 1,
    feedbackCount: 0,
    badges: [],
  };
}

/** Build an empty projection detached from runtime behavior. */
function projectionFor(snapshot: RunSnapshot): ReplayProjection {
  return createReplayProjection(
    snapshot,
    {
      status: "running",
      kernelStatus: "running",
      error: "",
      stepCount: 0,
      activationCount: 0,
      interactionCount: 0,
      usage: {},
    },
    null,
    [],
    [],
    {},
    "complete",
  );
}

describe("execution-map presenter", () => {
  it("keeps relation ownership and derives exactly one current card", () => {
    const snapshot = executionMapSnapshot();
    const projection = projectionFor(snapshot);
    observe(projection, "activation-perception", "perception");
    observe(projection, "activation-relation", "generated.activation", "running");
    projection.currentActivationId = "activation-relation";

    const model = presentRunExecutionMap({
      snapshot,
      projection,
      displayActivationId: projection.currentActivationId,
      selectedActivationId: null,
      viewMode: "path",
    });

    expect(model?.runtimeOwnerByNodeId["generated.activation"]).toEqual({
      kind: "relation",
      ownerId: "relation-action",
    });
    expect(model?.currentRelationId).toBe("relation-action");
    expect(model?.currentNodeId).toBe("action_executor");
    expect(model?.nodes.filter((node) => node.current)).toHaveLength(1);
  });

  it("keeps historical selection and failure separate from current", () => {
    const snapshot = executionMapSnapshot();
    const projection = projectionFor(snapshot);
    observe(projection, "activation-old", "perception");
    observe(projection, "activation-current", "action_executor", "running");
    projection.failureTargets.push({
      kind: "activation",
      cursor: 3,
      activationId: "activation-old",
      nodePath: "perception",
      label: "failure",
    });

    const model = presentRunExecutionMap({
      snapshot,
      projection,
      displayActivationId: "activation-current",
      selectedActivationId: "activation-old",
      viewMode: "path",
    });

    expect(model?.currentNodeId).toBe("action_executor");
    expect(model?.selectedNodeId).toBe("perception");
    expect(model?.failureNodeId).toBe("perception");
    expect(model?.nodes.filter((node) => node.current)).toHaveLength(1);
  });

  it("uses verified terminal mapping and never exposes generated labels", () => {
    const snapshot = executionMapSnapshot();
    const projection = projectionFor(snapshot);
    observe(projection, "activation-output", "output", "success");

    const model = presentRunExecutionMap({
      snapshot,
      projection,
      displayActivationId: "activation-output",
      selectedActivationId: null,
      viewMode: "relations",
    });

    expect(model?.currentNodeId).toBe("output");
    expect(model?.nodes.map((node) => node.id)).not.toContain("generated.terminal");
    expect(model?.relations).toHaveLength(4);
  });

  it("omits feedback from the default corridor and restores it in relations mode", () => {
    const snapshot = executionMapSnapshot();
    const projection = projectionFor(snapshot);
    observe(projection, "activation-current", "action_executor", "running");
    const shared = {
      snapshot,
      projection,
      displayActivationId: "activation-current",
      selectedActivationId: null,
    };

    const path = presentRunExecutionMap({ ...shared, viewMode: "path" });
    const relations = presentRunExecutionMap({ ...shared, viewMode: "relations" });

    expect(path?.visibleRelations.some((relation) => relation.kind === "feedback")).toBe(false);
    expect(relations?.visibleRelations.some((relation) => relation.kind === "feedback")).toBe(true);
    expect(relations?.nodes).toHaveLength(path?.nodes.length ?? 0);
  });

  it("does not reveal future output or failure facts after a backward prefix seek", () => {
    const snapshot = executionMapSnapshot();
    const before = projectionFor(snapshot);
    observe(before, "activation-perception", "perception", "running");
    const after = projectionFor(snapshot);
    observe(after, "activation-output", "output");
    after.failureTargets.push({
      kind: "activation",
      cursor: 8,
      activationId: "activation-output",
      nodePath: "output",
      label: "failure",
    });

    const beforeModel = presentRunExecutionMap({
      snapshot,
      projection: before,
      displayActivationId: "activation-perception",
      selectedActivationId: null,
      viewMode: "path",
    });
    const afterModel = presentRunExecutionMap({
      snapshot,
      projection: after,
      displayActivationId: "activation-output",
      selectedActivationId: null,
      viewMode: "path",
    });

    expect(beforeModel?.currentNodeId).toBe("perception");
    expect(beforeModel?.failureNodeId).toBeNull();
    expect(beforeModel?.nodes.find((node) => node.id === "output")?.aggregate.status).toBe("not_observed");
    expect(afterModel?.currentNodeId).toBe("output");
    expect(afterModel?.failureNodeId).toBe("output");
  });

  it("keeps repeated history neutral while rapid and unmapped display facts stay singular", () => {
    const snapshot = executionMapSnapshot();
    const projection = projectionFor(snapshot);
    observe(projection, "activation-perception-1", "perception");
    projection.activationsById["activation-perception-2"] = {
      ...projection.activationsById["activation-perception-1"]!,
      activationId: "activation-perception-2",
      startCursor: 2,
      endCursor: 3,
    };
    projection.nodesById.perception = {
      ...projection.nodesById.perception!,
      activationIds: ["activation-perception-1", "activation-perception-2"],
      executionCount: 2,
      feedbackCount: 1,
    };
    observe(projection, "activation-action", "action_executor", "running");
    const actionModel = presentRunExecutionMap({
      snapshot,
      projection,
      displayActivationId: "activation-action",
      selectedActivationId: "activation-perception-1",
      viewMode: "path",
    });

    expect(actionModel?.nodes.find((item) => item.id === "perception")?.aggregate).toMatchObject({
      executionCount: 2,
      feedbackCount: 1,
      status: "success",
    });
    expect(actionModel?.nodes.filter((item) => item.current)).toHaveLength(1);
    expect(actionModel?.nodes.find((item) => item.id === "perception")?.selected).toBe(true);

    projection.activationsById["activation-unmapped"] = {
      ...projection.activationsById["activation-action"]!,
      activationId: "activation-unmapped",
      nodeId: "unmapped-runtime-node",
      nodePath: "unmapped-runtime-node",
    };
    const unmappedModel = presentRunExecutionMap({
      snapshot,
      projection,
      displayActivationId: "activation-unmapped",
      selectedActivationId: null,
      viewMode: "path",
    });

    expect(unmappedModel?.currentNodeId).toBeNull();
    expect(unmappedModel?.nodes.filter((item) => item.current)).toHaveLength(0);
  });
});
