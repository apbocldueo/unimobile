import { describe, expect, it } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { relationEndpointFocus, relationKindLabel } from "./relationPresentation";

describe("relation presentation", () => {
  it("resolves source and target ports for the selected edge", () => {
    const document = createEmptyStudioDocument("agent-relation", "Relation", "document-relation");
    document.capabilities.push({ canvasId: "reason", logicalId: "reason", family: "reasoning", lifecycle: "per_step", implementation: { policy: "single", candidates: [] } });
    document.relations.push({ canvasId: "edge", source: { ownerId: "input", portId: "task" }, target: { ownerId: "reason", portId: "task" }, kind: "data" });
    expect(relationEndpointFocus(document, "input", "edge")).toEqual({ role: "source", portId: "task" });
    expect(relationEndpointFocus(document, "reason", "edge")).toEqual({ role: "target", portId: "task" });
  });

  it("maps the termination target to the visible Output connection port", () => {
    const document = createEmptyStudioDocument("agent-termination", "Termination", "document-termination");
    document.capabilities.push({ canvasId: "action", logicalId: "action", family: "action_executor", lifecycle: "per_step", implementation: { policy: "single", candidates: [] } });
    document.relations.push({ canvasId: "edge", source: { ownerId: "action", portId: "result" }, target: { ownerId: "output", portId: "terminal" }, kind: "termination" });
    expect(relationEndpointFocus(document, "output", "edge")).toEqual({ role: "target", portId: "connection" });
    expect(relationKindLabel("feedback")).toBe("下一轮反馈");
  });
});
