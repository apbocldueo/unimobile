import { describe, expect, it } from "vitest";
import { createEmptyStudioDocument, parseStudioCompileResult } from "@/entities/agent-graph";
import { diagnosticAdvice, diagnosticTarget } from "./diagnosticGuidance";

/** Produce a null-graph response like an invalid compile, not a runnable fixture. */
function result(diagnostic: Record<string, unknown>, maps: Record<string, unknown> = {}) {
  return parseStudioCompileResult({ schemaVersion: 1, isSuccess: false, catalogVersion: "fixture", canonicalHash: null,
    agentGraph: null, diagnostics: [{ code: "unknown", severity: "error", message: "Check configuration", ...diagnostic }],
    sourceMap: [], projectionMap: [], summary: { errorCount: 1, warningCount: 0, nodeCount: 0, edgeCount: 0 }, ...maps });
}

describe("diagnostic location contract", () => {
  const document = createEmptyStudioDocument("agent", "Test", "document");
  it("resolves the captured early missing-LLM diagnostic without parsing its legacy path", () => {
    const current = structuredClone(document);
    current.capabilities.push({ canvasId: "tpl_reasoning", logicalId: "reasoning", family: "reasoning", lifecycle: "per_step",
      implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "reason", version: "1", params: {}, dependencies: {} }] } });
    const compile = result({ code: "graph.studio.component_dependency_required", node_id: "reasoning", source_id: "studio-flow:capability:tpl_reasoning",
      path: ["semantic", "nodes", 2, "component", "candidates", 0, "dependencies", "llm"] });
    expect(diagnosticTarget(compile.diagnostics[0]!, current, compile)).toEqual({ kind: "node", id: "tpl_reasoning" });
    expect(diagnosticTarget({ ...compile.diagnostics[0]!, code: "unknown" }, current, compile)).toBeNull();
    expect(diagnosticTarget({ ...compile.diagnostics[0]!, nodeId: "missing" }, current, compile)).toBeNull();
    const duplicate = structuredClone(current.capabilities[0]!);
    duplicate.canvasId = "duplicate";
    current.capabilities.push(duplicate);
    expect(diagnosticTarget(compile.diagnostics[0]!, current, compile)).toBeNull();
  });
  it("rejects conflicts between an early authoring identity and an explicit source map", () => {
    const current = structuredClone(document);
    current.capabilities.push({ canvasId: "reason", logicalId: "reasoning", family: "reasoning", lifecycle: "per_step",
      implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "reason", version: "1", params: {}, dependencies: {} }] } });
    const compile = result({ code: "graph.studio.component_dependency_required", node_id: "reasoning", source_id: "conflict" },
      { sourceMap: [{ source_id: "conflict", canvas_node_id: "output" }] });
    expect(diagnosticTarget(compile.diagnostics[0]!, current, compile)).toBeNull();
  });
  it("preserves explicit backend locators including edge index zero", () => {
    expect(result({ node_id: "input", edge_index: 0, port_id: "out", source_id: "source" }).diagnostics[0])
      .toMatchObject({ nodeId: "input", edgeIndex: 0, portId: "out", sourceId: "source" });
  });
  it.each([{ edge_index: -1 }, { edge_index: 1.5 }, { node_id: 1 }, { port_id: {} }, { source_id: "a", sourceId: "b" }])("rejects malformed locators %j", (raw) => {
    expect(() => result(raw)).toThrow();
  });
  it("resolves an invalid compile's projection without requiring agentGraph", () => {
    const compile = result({ node_id: "generated.input" }, { projectionMap: [{ graphKind: "node", graphId: "generated.input", owner: { kind: "input", ownerId: document.input.logicalId }, propertyPath: [] }] });
    expect(diagnosticTarget(compile.diagnostics[0]!, document, compile)).toEqual({ kind: "node", id: document.input.canvasId });
  });
  it("uses exact source-map identities", () => {
    const compile = result({ source_id: "exact" }, { sourceMap: [{ source_id: "exact", document_id: "document", canvas_node_id: "output" }] });
    expect(diagnosticTarget(compile.diagnostics[0]!, document, compile)).toEqual({ kind: "node", id: "output" });
  });
  it("preserves current tuple source paths and rejects malformed segments", () => {
    const source = { source_id: "s", canvas_path: [], logical_node_path: ["reason"], property_path: ["implementation", "candidates", 0] };
    expect(result({}, { sourceMap: [source] }).sourceMap[0]).toMatchObject({ logicalNodePath: ["reason"], propertyPath: ["implementation", "candidates", 0] });
    expect(() => result({}, { sourceMap: [{ ...source, canvas_path: [2] }] })).toThrow();
    expect(() => result({ path: [NaN] })).toThrow();
    expect(() => result({ path: "nodes.2" })).toThrow();
    expect(() => result({}, { projectionMap: [{ graphKind: "node", graphId: "n", owner: { kind: "capability", ownerId: "n" }, propertyPath: [1.5] }] })).toThrow();
  });
  it("does not interpret a message as a node location", () => {
    const compile = result({ message: "input output capability:input" });
    expect(diagnosticTarget(compile.diagnostics[0]!, document, compile)).toBeNull();
  });
  it("degrades conflicting owners rather than selecting the first", () => {
    const compile = result({ path: ["input"], source_id: "other" }, { sourceMap: [{ source_id: "other", canvas_node_id: "output" }] });
    expect(diagnosticTarget(compile.diagnostics[0]!, document, compile)).toBeNull();
  });
  it("ignores out-of-bounds and foreign-document locations", () => {
    const compile = result({ path: ["capabilities", 999], source_id: "other" }, { sourceMap: [{ source_id: "other", document_id: "foreign", canvas_node_id: "output" }] });
    expect(diagnosticTarget(compile.diagnostics[0]!, document, compile)).toBeNull();
  });
});

describe("actionable diagnostic advice", () => {
  it("explains the runtime-provided observation boundary", () => {
    expect(diagnosticAdvice("graph.port.required_missing", { portId: "perception" })).toContain("不要把 Input 直接连到 Perception");
    expect(diagnosticAdvice("graph.port.cardinality_exceeded", { portId: "observation" })).toContain("删除手动 observation 连线");
  });

  it("names the missing execution path", () => {
    expect(diagnosticAdvice("graph.studio.termination_source_forbidden")).toContain("Action Executor");
    expect(diagnosticAdvice("graph.port.required_missing", { portId: "action" })).toContain("Reasoning");
  });
});
