import { describe, expect, it } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { autoLayoutPositions } from "./canvasLayout";

describe("Builder canvas layout", () => {
  it("separates tall and wide cards in the same column without changing semantics", () => {
    const document = createEmptyStudioDocument("measured", "Measured", "measured-doc");
    for (let index = 0; index < 8; index += 1) {
      document.capabilities.push({ canvasId: `m${index}`, logicalId: `m${index}`, family: "memory", lifecycle: "stateful", implementation: { policy: "single", candidates: [] } });
    }
    const sizes = Object.fromEntries([document.input, ...document.capabilities, document.output].map((node, index) =>
      [node.canvasId, { width: 250 + index * 30, height: 100 + index * 90 }]));
    const before = JSON.stringify(document);
    const positions = autoLayoutPositions(document, sizes);
    expect(positions).toEqual(autoLayoutPositions(document, sizes));
    const entries = Object.entries(positions);
    for (let i = 0; i < entries.length; i += 1) for (let j = i + 1; j < entries.length; j += 1) {
      const [a, p] = entries[i]!; const [b, q] = entries[j]!;
      expect(p.x + sizes[a]!.width <= q.x || q.x + sizes[b]!.width <= p.x
        || p.y + sizes[a]!.height <= q.y || q.y + sizes[b]!.height <= p.y).toBe(true);
    }
    expect(JSON.stringify(document)).toBe(before);
    expect(Object.values(autoLayoutPositions(document, { input: { width: NaN, height: -1 } }))
      .every((position) => Number.isFinite(position.x) && Number.isFinite(position.y))).toBe(true);
  });
  it("places ordinary flow left-to-right and keeps feedback out of layer ordering", () => {
    const document = createEmptyStudioDocument("agent-layout", "Layout", "document-layout");
    document.capabilities.push(
      { canvasId: "reason", logicalId: "reason", family: "reasoning", lifecycle: "per_step", implementation: { policy: "single", candidates: [] } },
      { canvasId: "action", logicalId: "action", family: "action_executor", lifecycle: "per_step", implementation: { policy: "single", candidates: [] } },
      { canvasId: "memory", logicalId: "memory", family: "memory", lifecycle: "stateful", implementation: { policy: "single", candidates: [] } },
    );
    document.relations.push(
      { canvasId: "forward-1", source: { ownerId: "input", portId: "task" }, target: { ownerId: "reason", portId: "task" }, kind: "data" },
      { canvasId: "forward-2", source: { ownerId: "reason", portId: "action" }, target: { ownerId: "action", portId: "action" }, kind: "data" },
      { canvasId: "forward-3", source: { ownerId: "action", portId: "result" }, target: { ownerId: "output", portId: "terminal" }, kind: "termination" },
      { canvasId: "feedback", source: { ownerId: "action", portId: "result" }, target: { ownerId: "memory", portId: "write" }, kind: "feedback" },
    );

    const positions = autoLayoutPositions(document);
    expect(positions.input?.x).toBeLessThan(positions.reason?.x ?? 0);
    expect(positions.reason?.x).toBeLessThan(positions.action?.x ?? 0);
    expect(positions.output?.x).toBeGreaterThan(positions.action?.x ?? 0);
    expect(positions.memory?.x).toBeGreaterThanOrEqual(positions.input?.x ?? 0);
    expect(positions.memory?.y).toBeGreaterThan(positions.reason?.y ?? 0);
    expect(new Set(Object.keys(positions))).toEqual(new Set(["input", "output", "reason", "action", "memory"]));
  });

  it("keeps perception above and memory below the primary reading lane", () => {
    const document = createEmptyStudioDocument("agent-lanes", "Lanes", "document-lanes");
    document.capabilities.push(
      { canvasId: "perception", logicalId: "perception", family: "perception", lifecycle: "per_step", implementation: { policy: "single", candidates: [] } },
      { canvasId: "reasoning", logicalId: "reasoning", family: "reasoning", lifecycle: "per_step", implementation: { policy: "single", candidates: [] } },
      { canvasId: "memory", logicalId: "memory", family: "memory", lifecycle: "stateful", implementation: { policy: "single", candidates: [] } },
    );
    document.relations.push(
      { canvasId: "perception-reasoning", source: { ownerId: "perception", portId: "perception" }, target: { ownerId: "reasoning", portId: "perception" }, kind: "data" },
      { canvasId: "reasoning-output", source: { ownerId: "reasoning", portId: "action" }, target: { ownerId: "output", portId: "terminal" }, kind: "termination" },
    );

    const positions = autoLayoutPositions(document);
    expect(positions.perception?.y).toBeLessThan(positions.reasoning?.y ?? 0);
    expect(positions.perception?.x).toBe(positions.input?.x);
    expect(positions.memory?.y).toBeGreaterThan(positions.reasoning?.y ?? 0);
  });
});
