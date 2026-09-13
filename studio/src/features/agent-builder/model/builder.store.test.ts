import { beforeEach, describe, expect, it } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import type { AgentRevision } from "@/entities/agent-revision";
import { useAgentBuilderDocumentStore } from "./builder.store";

function revision(): AgentRevision {
  return {
    revisionId: "revision-current",
    agentId: "agent-test",
    ordinal: 1,
    parentRevisionId: null,
    document: createEmptyStudioDocument("agent-test", "Test", "document-test"),
    compileSnapshot: { status: "invalid", diagnostics: [], sourceMap: [], projectionMap: [] },
    createdAt: 1,
  };
}

describe("schema-3 builder store", () => {
  beforeEach(() => useAgentBuilderDocumentStore.getState().clear());

  it("keeps system Input/Output while adding and deleting multiple capability instances", () => {
    useAgentBuilderDocumentStore.getState().hydrate(revision());
    const store = useAgentBuilderDocumentStore.getState();
    store.addNode({
      canvasId: "reasoning_1",
      logicalId: "reasoning_1",
      family: "reasoning",
      lifecycle: "per_step",
      implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "universal_reasoning", version: "1", params: {}, dependencies: {} }] },
    }, { x: 10, y: 20, label: "Reasoning" });
    store.addNode({
      canvasId: "reasoning_2",
      logicalId: "reasoning_2",
      family: "reasoning",
      lifecycle: "per_step",
      implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "universal_reasoning", version: "1", params: {}, dependencies: {} }] },
    }, { x: 30, y: 40, label: "Reasoning" });
    expect(useAgentBuilderDocumentStore.getState().document?.capabilities).toHaveLength(2);
    store.removeNodes(["input", "output", "reasoning_1"]);
    const document = useAgentBuilderDocumentStore.getState().document!;
    expect(document.input.kind).toBe("input");
    expect(document.output.kind).toBe("output");
    expect(document.capabilities.map((item) => item.logicalId)).toEqual(["reasoning_2"]);
  });

  it("does not silently convert a legacy revision", () => {
    const legacy = revision();
    legacy.document = {
      schemaVersion: 2,
      contractVersion: "1.1",
      documentId: "legacy-document",
      agentId: "agent-test",
      name: "Legacy",
      semantic: { profile: "mobile_agent", policies: {}, nodes: [], edges: [] },
      presentation: { nodes: {}, viewport: { x: 0, y: 0, zoom: 1 } },
      authoring: { description: "", createdAt: 0, updatedAt: 0 },
    };
    useAgentBuilderDocumentStore.getState().hydrate(legacy);
    expect(useAgentBuilderDocumentStore.getState().document).toBeNull();
    expect(useAgentBuilderDocumentStore.getState().legacyRevisionId).toBe("revision-current");
  });
});
