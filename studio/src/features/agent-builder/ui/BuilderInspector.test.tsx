import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import type { ComponentCatalog } from "@/entities/component-catalog";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { BuilderInspector } from "./BuilderInspector";

const catalog: ComponentCatalog = {
  schemaVersion: 1, catalogVersion: "catalog", diagnostics: [],
  capabilityFamilies: [{ family: "reasoning", label: "Reasoning", extension: false, availableImplementationCount: 1 }],
  components: [{
    identifier: "agent.reasoning:reason@1", namespace: "agent.reasoning", name: "reason", version: "1", providerId: "fixture",
    placement: "agent_capability", capabilityFamily: "reasoning",
    contract: { ref: { id: "zhixing.core.reasoning", version: "1.0" }, ports: [], adapter: "core_role", sideEffect: "none", idempotent: true },
    category: "core_agent", role: "reasoning", configSchema: {}, dependencySlots: [],
    availability: { available: true, extra: "", errorType: "" }, capabilities: {}, provenance: {}, display: { label: "Reasoning", group: "reasoning" },
  }],
};

beforeEach(() => {
  const document = createEmptyStudioDocument("agent-test", "Test", "document-test");
  document.capabilities.push({
    canvasId: "reason", logicalId: "reason", family: "reasoning", lifecycle: "per_step",
    implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "reason", version: "1", params: {}, dependencies: {} }] },
  });
  document.presentation.nodes.reason = { x: 10, y: 20, label: "Reasoning" };
  useAgentBuilderDocumentStore.getState().replaceDocument(document, "revision-1");
});
afterEach(() => { cleanup(); useAgentBuilderDocumentStore.getState().clear(); });

describe("capability Builder Inspector", () => {
  it("keeps Input/Output implementation-free and explains Output semantics", () => {
    useAgentBuilderDocumentStore.getState().selectNode("output");
    render(<BuilderInspector catalog={catalog} />);
    expect(screen.getByText(/不承诺输出 payload/)).not.toBeNull();
    expect(screen.queryByText(/Binding policy/)).toBeNull();
  });

  it("edits exact implementation config inside one capability node", () => {
    useAgentBuilderDocumentStore.getState().selectNode("reason");
    render(<BuilderInspector catalog={catalog} />);
    const config = screen.getByLabelText("Candidate 1 config");
    fireEvent.change(config, { target: { value: '{"temperature":0.2}' } });
    fireEvent.blur(config);
    expect(useAgentBuilderDocumentStore.getState().document?.capabilities[0]?.implementation.candidates[0]?.params).toEqual({ temperature: 0.2 });
  });
});
