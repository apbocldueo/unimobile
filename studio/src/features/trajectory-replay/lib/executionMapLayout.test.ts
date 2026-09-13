import { describe, expect, it } from "vitest";
import type {
  ExecutionMapNode,
  ExecutionMapRelation,
} from "../model/executionMapPresenter";
import { layoutExecutionMap } from "./executionMapLayout";

/** Build one quiet execution-map node for deterministic layout tests. */
function node(id: string, kind = "component"): ExecutionMapNode {
  return {
    id,
    canvasId: `canvas-${id}`,
    label: id,
    kind,
    role: id,
    lifecycle: kind === "output" ? "terminal" : "per_step",
    primary: kind === "component",
    runtimeNodeIds: [id],
    aggregate: {
      nodeId: id,
      status: "not_observed",
      activationIds: [],
      executionCount: 0,
      feedbackCount: 0,
      badges: [],
    },
    current: false,
    selected: false,
    failed: false,
    dependencyOwnerIds: [],
  };
}

/** Build one declared relation for layout tests. */
function relation(
  id: string,
  sourceNode: string,
  targetNode: string,
  kind = "data",
): ExecutionMapRelation {
  return { id, sourceNode, targetNode, kind, current: false };
}

describe("vertical execution-map layout", () => {
  const nodes = [
    node("input", "input"),
    node("memory"),
    node("perception"),
    node("reasoning"),
    node("action"),
    node("extension"),
    node("output", "output"),
  ];
  const relations = [
    relation("input-perception", "input", "perception"),
    relation("memory-reasoning", "memory", "reasoning"),
    relation("perception-reasoning", "perception", "reasoning"),
    relation("reasoning-action", "reasoning", "action", "activation"),
    relation("extension-action", "extension", "action"),
    relation("action-output", "action", "output", "termination"),
    relation("action-perception", "action", "perception", "feedback"),
  ];

  it("keeps Input first, Output last, and parallel inputs on one rank", () => {
    const positions = layoutExecutionMap(nodes, relations);

    expect(positions.input!.y).toBeLessThan(positions.perception!.y);
    expect(positions.output!.y).toBeGreaterThan(positions.action!.y);
    expect(positions.memory!.y).toBe(positions.perception!.y);
    expect(positions.memory!.x).not.toBe(positions.perception!.x);
  });

  it("is stable across reordered node and relation inputs", () => {
    const forward = layoutExecutionMap(nodes, relations);
    const reordered = layoutExecutionMap([...nodes].reverse(), [...relations].reverse());

    expect(reordered).toEqual(forward);
  });

  it("ignores feedback cycles while ranking", () => {
    const withoutFeedback = layoutExecutionMap(
      nodes,
      relations.filter((item) => item.kind !== "feedback"),
    );
    const withFeedback = layoutExecutionMap(nodes, relations);

    expect(withFeedback).toEqual(withoutFeedback);
  });
});
