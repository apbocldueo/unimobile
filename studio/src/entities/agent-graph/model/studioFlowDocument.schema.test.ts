import { describe, expect, it } from "vitest";
import { createEmptyStudioDocument, parseStudioFlowDocument } from "./studioFlowDocument.schema";

function rawDocument(): Record<string, unknown> {
  return structuredClone(createEmptyStudioDocument("agent-test", "Test Agent", "document-test"));
}

describe("parseStudioFlowDocument schema 3", () => {
  it("parses independent Input/Output capability authoring without mutating input", () => {
    const raw = rawDocument();
    (raw.capabilities as unknown[]).push({
      canvasId: "node_memory",
      logicalId: "memory",
      family: "memory",
      lifecycle: "stateful",
      implementation: {
        policy: "single",
        candidates: [{ namespace: "agent.memory", name: "sliding_window_memory", version: "1", params: {}, dependencies: {} }],
      },
    });
    const before = JSON.stringify(raw);
    const parsed = parseStudioFlowDocument(raw);
    expect(JSON.stringify(raw)).toBe(before);
    expect(parsed.input.kind).toBe("input");
    expect(parsed.output.kind).toBe("output");
    expect(parsed.capabilities[0]?.family).toBe("memory");
    (raw.capabilities as { logicalId: string }[])[0]!.logicalId = "changed";
    expect(parsed.capabilities[0]?.logicalId).toBe("memory");
  });

  it("rejects unknown fields, raw controls, generated identities, and malformed Output relations", () => {
    const unknown = rawDocument();
    unknown.semantic = { nodes: [{ kind: "router" }] };
    expect(() => parseStudioFlowDocument(unknown)).toThrow("document.semantic");

    const generated = rawDocument();
    generated.input = { canvasId: "studio_generated.input", logicalId: "input", kind: "input" };
    expect(() => parseStudioFlowDocument(generated)).toThrow("user-owned");

    const output = rawDocument();
    (output.relations as unknown[]).push({
      canvasId: "r1",
      source: { ownerId: "input", portId: "task" },
      target: { ownerId: "output", portId: "connection" },
      kind: "data",
    });
    expect(() => parseStudioFlowDocument(output)).toThrow("Output accepts only termination");
  });

  it("preserves strict boundary render modes", () => {
    const raw = rawDocument();
    const parsed = parseStudioFlowDocument(raw);
    expect(parsed.presentation.nodes.input?.renderMode).toBe("boundary");
    const invalid = structuredClone(raw);
    (invalid.presentation as { nodes: Record<string, Record<string, unknown>> }).nodes.input!.renderMode = "compact";
    expect(() => parseStudioFlowDocument(invalid)).toThrow("renderMode");
  });
});
