import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import {
  createEmptyLegacyStudioDocument,
  createEmptyStudioDocument,
  STUDIO_CAPABILITY_AUTHORING_POLICY,
  STUDIO_CAPABILITY_LOWERING_PROFILE,
  type StudioFlowDocument,
} from "@/entities/agent-graph";
import {
  createReplayProjection,
  type RunResultSummary,
  type RunSnapshot,
} from "@/entities/run";
import { RunGraph } from "./ReplayGraph";

const OriginalResizeObserver = globalThis.ResizeObserver;

beforeAll(() => {
  globalThis.ResizeObserver = class ResizeObserver {
    /** Observe an inert test element. */
    observe(): void {}
    /** Stop observing an inert test element. */
    unobserve(): void {}
    /** Release the inert observer. */
    disconnect(): void {}
  };
});

afterAll(() => {
  globalThis.ResizeObserver = OriginalResizeObserver;
});

afterEach(cleanup);

const result: RunResultSummary = {
  status: "failure",
  kernelStatus: "failure",
  error: "generated condition failed",
  stepCount: 1,
  activationCount: 2,
  interactionCount: 0,
  usage: {},
};

/** Build one snapshot whose internal graph contains forbidden terminal labels. */
function capabilitySnapshot(): RunSnapshot {
  const empty = createEmptyStudioDocument("agent-1", "Agent", "document-1");
  const capabilityDocument: StudioFlowDocument = {
    ...empty,
    capabilities: [{
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
    }],
    relations: [{
      canvasId: "relation-terminal",
      source: { ownerId: "action_executor", portId: "result" },
      target: { ownerId: "output", portId: "terminal" },
      kind: "termination",
    }, {
      canvasId: "relation-feedback",
      source: { ownerId: "action_executor", portId: "result" },
      target: { ownerId: "action_executor", portId: "feedback" },
      kind: "feedback",
    }],
    presentation: {
      ...empty.presentation,
      nodes: {
        ...empty.presentation.nodes,
        "canvas-action": { x: 240, y: 160, label: "Action Executor" },
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
      { id: "action_executor", kind: "component", role: "action_executor", lifecycle: "per_step", primary: true },
      { id: "studio_generated.action_executor.terminal", kind: "condition", role: "DONE / FAIL", lifecycle: "per_step", primary: false },
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
      { graphKind: "node", graphId: "action_executor", owner: { kind: "capability", ownerId: "action_executor" }, propertyPath: [] },
      { graphKind: "node", graphId: "studio_generated.action_executor.terminal", owner: { kind: "relation", ownerId: "relation-terminal" }, propertyPath: [] },
      { graphKind: "node", graphId: "output", owner: { kind: "output", ownerId: "output" }, propertyPath: [] },
    ],
    providerIdentities: [],
  };
}

/** Build one exactly recognized schema-2 Studio snapshot with hidden runtime glue. */
function legacySnapshot(): RunSnapshot {
  const document = createEmptyLegacyStudioDocument("agent-legacy", "Legacy", "document-legacy");
  document.semantic.nodes = [
    {
      canvasId: "canvas-input",
      logicalId: "input",
      kind: "input",
      lifecycle: "on_run_start",
    },
    {
      canvasId: "canvas-reasoning",
      logicalId: "reasoning",
      kind: "component",
      lifecycle: "per_step",
      role: "reasoning",
      component: {
        policy: "single",
        candidates: [{
          namespace: "agent.reasoning",
          name: "reasoning",
          version: "1",
          params: {},
          dependencies: {},
        }],
      },
      primary: true,
    },
    {
      canvasId: "canvas-terminal",
      logicalId: "terminal",
      kind: "condition",
      lifecycle: "per_step",
      role: "DONE / FAIL",
      predicate: { field: "result", operator: "equals", value: "done" },
    },
    {
      canvasId: "canvas-output",
      logicalId: "output",
      kind: "output",
      lifecycle: "terminal",
    },
  ];
  document.semantic.edges = [
    { canvasId: "edge-input", source: { canvasId: "canvas-input", portId: "task" }, target: { canvasId: "canvas-reasoning", portId: "task" }, kind: "data" },
    { canvasId: "edge-terminal", source: { canvasId: "canvas-reasoning", portId: "result" }, target: { canvasId: "canvas-terminal", portId: "value" }, kind: "data" },
    { canvasId: "edge-output", source: { canvasId: "canvas-terminal", portId: "true" }, target: { canvasId: "canvas-output", portId: "result" }, kind: "data" },
  ];
  document.presentation.nodes = {
    "canvas-input": { x: 0, y: 0, label: "Input" },
    "canvas-reasoning": { x: 240, y: 0, label: "Reasoning" },
    "canvas-terminal": { x: 480, y: 0, label: "DONE / FAIL" },
    "canvas-output": { x: 720, y: 0, label: "Output" },
  };
  return {
    ...capabilitySnapshot(),
    agentId: "agent-legacy",
    revisionId: "revision-legacy",
    capabilityDocument: document,
    authoringPolicy: null,
    loweringProfile: null,
    capabilityHash: null,
    projectionMap: [],
    presentation: document.presentation,
    graphNodes: document.semantic.nodes.map((node) => ({
      id: node.logicalId,
      kind: node.kind,
      role: node.role ?? "",
      lifecycle: node.lifecycle,
      primary: node.primary === true,
    })),
    graphEdges: [
      { id: "input-reasoning", sourceNode: "input", targetNode: "reasoning", kind: "data" },
      { id: "reasoning-terminal", sourceNode: "reasoning", targetNode: "terminal", kind: "data" },
      { id: "terminal-output", sourceNode: "terminal", targetNode: "output", kind: "data" },
    ],
  };
}

describe("capability-only Live/Replay graph", () => {
  it("projects generated runtime nodes onto capabilities without outcome text", () => {
    const snapshot = capabilitySnapshot();
    const projection = createReplayProjection(snapshot, result, null, [], [], {}, "complete");
    projection.nodesById["studio_generated.action_executor.terminal"] = {
      nodeId: "studio_generated.action_executor.terminal",
      status: "failure",
      activationIds: ["activation-terminal"],
      executionCount: 1,
      feedbackCount: 0,
      badges: ["FAIL"],
    };
    render(
      <div style={{ width: 960, height: 640 }}>
        <RunGraph snapshot={snapshot} projection={projection} selectedActivationId={null} onSelectActivation={() => undefined} />
      </div>,
    );
    expect(screen.getByText("Action Executor")).not.toBeNull();
    expect(screen.queryByText("studio_generated.action_executor.terminal")).toBeNull();
    expect(screen.queryByText(/DONE|FAIL/i)).toBeNull();
    expect(screen.getByText("Input")).not.toBeNull();
    expect(screen.getByText("Output")).not.toBeNull();
  });

  it("shows an unavailable state instead of guessing a Studio mapping", () => {
    const snapshot = { ...capabilitySnapshot(), projectionMap: [] };
    const projection = createReplayProjection(snapshot, result, null, [], [], {}, "partial");
    render(<RunGraph snapshot={snapshot} projection={projection} selectedActivationId={null} onSelectActivation={() => undefined} />);
    expect(screen.getByText("capability_projection_unavailable")).not.toBeNull();
    expect(screen.queryByText("studio_generated.action_executor.terminal")).toBeNull();
  });

  it("projects an exact schema-2 Studio topology without exposing its glue labels", () => {
    const snapshot = legacySnapshot();
    const projection = createReplayProjection(snapshot, result, null, [], [], {}, "complete");
    render(<RunGraph snapshot={snapshot} projection={projection} selectedActivationId={null} onSelectActivation={() => undefined} />);
    expect(screen.getByText("Input")).not.toBeNull();
    expect(screen.getByText("Reasoning")).not.toBeNull();
    expect(screen.getByText("Output")).not.toBeNull();
    expect(screen.queryByText(/DONE|FAIL/i)).toBeNull();
    expect(screen.queryByText("capability_projection_unavailable")).toBeNull();
  });

  it("rejects a schema-2 compatibility projection when graph identity is ambiguous", () => {
    const snapshot = legacySnapshot();
    snapshot.graphNodes = snapshot.graphNodes.slice(0, -1);
    const projection = createReplayProjection(snapshot, result, null, [], [], {}, "partial");
    render(<RunGraph snapshot={snapshot} projection={projection} selectedActivationId={null} onSelectActivation={() => undefined} />);
    expect(screen.getByText("capability_projection_unavailable")).not.toBeNull();
  });

  it("separates one current marker from a historical selection and switches relation disclosure", () => {
    const snapshot = capabilitySnapshot();
    const projection = createReplayProjection(snapshot, result, null, [], [], {}, "complete");
    projection.activationsById["activation-input"] = {
      activationId: "activation-input",
      nodeId: "input",
      nodePath: "input",
      role: "input",
      component: "input",
      parentActivationId: "",
      loopPath: "",
      loopIteration: null,
      interactionStep: 0,
      status: "success",
      startCursor: 0,
      endCursor: 1,
      durationMs: 1,
      payloadHistory: [],
    };
    projection.activationsById["activation-action"] = {
      ...projection.activationsById["activation-input"],
      activationId: "activation-action",
      nodeId: "action_executor",
      nodePath: "action_executor",
      role: "action_executor",
      component: "action_executor",
      status: "running",
      endCursor: null,
      durationMs: null,
    };
    projection.nodesById.input = {
      nodeId: "input",
      status: "success",
      activationIds: ["activation-input"],
      executionCount: 1,
      feedbackCount: 0,
      badges: [],
    };
    projection.nodesById.action_executor = {
      nodeId: "action_executor",
      status: "running",
      activationIds: ["activation-action"],
      executionCount: 1,
      feedbackCount: 1,
      badges: [],
    };
    projection.currentActivationId = "activation-action";

    const rendered = render(
      <div style={{ width: 960, height: 640 }}>
        <RunGraph
          snapshot={snapshot}
          projection={projection}
          displayActivationId="activation-action"
          selectedActivationId="activation-input"
          onSelectActivation={() => undefined}
        />
      </div>,
    );

    expect(rendered.container.querySelectorAll('[data-current="true"]')).toHaveLength(1);
    expect(rendered.container.querySelectorAll('[data-selected="true"]')).toHaveLength(1);
    expect(screen.getByText("当前执行")).not.toBeNull();
    expect(screen.getByText(/已经过/)).not.toBeNull();
    expect(screen.getByRole("button", { name: "聚焦当前" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", { name: "运行路径" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "关系全图" }));
    expect(screen.getByRole("button", { name: "关系全图" }).getAttribute("aria-pressed")).toBe("true");
    expect(rendered.container.querySelectorAll('[data-current="true"]')).toHaveLength(1);

    rendered.rerender(
      <div style={{ width: 960, height: 640 }}>
        <RunGraph
          snapshot={snapshot}
          projection={projection}
          displayActivationId="activation-input"
          selectedActivationId="activation-action"
          onSelectActivation={() => undefined}
        />
      </div>,
    );
    const current = rendered.container.querySelector('[data-current="true"]');
    expect(current?.getAttribute("aria-label")).toContain("Input");
    expect(rendered.container.querySelectorAll('[data-current="true"]')).toHaveLength(1);
    expect(rendered.container.querySelectorAll('[data-selected="true"]')).toHaveLength(1);
  });
});
