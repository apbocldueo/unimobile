import { describe, expect, it } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { parseAgentRevision } from "./revision.schema";

/** Build a persisted invalid revision without executable graph or runtime evidence. */
function revision(diagnostic: Record<string, unknown>) {
  return { agentId: "agent", revisionId: "revision", ordinal: 1, parentRevisionId: null, createdAt: 1,
    document: createEmptyStudioDocument("agent", "Test", "document"),
    compileSnapshot: { status: "invalid", diagnostics: [{ code: "graph.studio.component_dependency_required", severity: "error", message: "Dependency required", ...diagnostic }],
      sourceMap: [{ source_id: "source", canvas_node_id: "input", logical_node_path: ["input"] }], projectionMap: [] } };
}

describe("immutable revision locator normalization", () => {
  it("keeps the same typed locators after save and reload as live compile", () => {
    const parsed = parseAgentRevision(revision({ node_id: "reasoning", source_id: "source", path: ["semantic", "nodes", 2] }));
    expect(parsed.compileSnapshot.diagnostics[0]).toMatchObject({ nodeId: "reasoning", sourceId: "source", path: ["semantic", "nodes", 2] });
    expect(parsed.compileSnapshot.sourceMap[0]).toMatchObject({ sourceId: "source", canvasNodeId: "input", logicalNodePath: ["input"] });
  });
  it("rejects malformed saved locators instead of silently treating them as usable", () => {
    expect(() => parseAgentRevision(revision({ node_id: 2 }))).toThrow();
    expect(() => parseAgentRevision(revision({ edge_index: -1 }))).toThrow();
  });
});
