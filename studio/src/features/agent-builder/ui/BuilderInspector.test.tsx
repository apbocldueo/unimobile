import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createEmptyStudioDocument, type StudioCompileResult } from "@/entities/agent-graph";
import { useCanvasInteractionStore } from "../model/canvasInteraction.store";
import type { ComponentCatalog } from "@/entities/component-catalog";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { BuilderInspector } from "./BuilderInspector";
import { BuilderLayout } from "./BuilderLayout";

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
  it("keeps malformed configuration mounted when switching checks and closing the panel", () => {
    render(<BuilderLayout><BuilderInspector catalog={catalog} /></BuilderLayout>);
    act(() => useAgentBuilderDocumentStore.getState().selectNode("reason"));
    fireEvent.click(screen.getByText("高级参数 JSON"));
    const input = screen.getByLabelText("Candidate 1 config") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "{" } });
    const before = useAgentBuilderDocumentStore.getState();
    fireEvent.click(screen.getByRole("button", { name: "检查" }));
    expect(input.closest("[hidden]")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "关闭配置面板" }));
    fireEvent.click(screen.getByRole("button", { name: "配置与检查" }));
    fireEvent.click(screen.getByRole("button", { name: "配置" }));
    expect(screen.getByLabelText("Candidate 1 config")).toBe(input);
    expect(input.value).toBe("{");
    expect(input.closest("[hidden]")).toBeNull();
    expect(useAgentBuilderDocumentStore.getState()).toBe(before);
  });

  it("explains the next action before an object is selected", () => {
    render(<BuilderInspector catalog={catalog} />);
    expect(screen.getByRole("region", { name: "Inspector 使用提示" })).not.toBeNull();
    expect(screen.getByText(/已有示例可切换到运行页检查并试跑/)).not.toBeNull();
  });

  it("prioritizes purpose and keeps identity folded without mutating content", () => {
    useAgentBuilderDocumentStore.getState().selectNode("reason");
    const before = useAgentBuilderDocumentStore.getState();
    render(<BuilderInspector catalog={catalog} />);
    expect(screen.getByText("结合任务与上下文，选择下一步动作。")).not.toBeNull();
    const summary = screen.getByText("技术标识");
    expect(summary.closest("details")?.open).toBe(false);
    fireEvent.click(summary);
    expect(useAgentBuilderDocumentStore.getState()).toBe(before);
  });

  it("retains malformed expanded content and restores focus without a second textarea", () => {
    // jsdom has no native dialog behavior; real browser tests cover modality/focus trapping.
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } });
    Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); } });
    useAgentBuilderDocumentStore.getState().selectNode("reason");
    render(<BuilderInspector catalog={catalog} />);
    fireEvent.click(screen.getByText("高级参数 JSON"));
    const trigger = screen.getByRole("button", { name: "Expand Candidate 1 config" });
    fireEvent.click(trigger);
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    expect(screen.getAllByLabelText("Candidate 1 config")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect((screen.getByLabelText("Candidate 1 config") as HTMLTextAreaElement).value).toBe("{");
    expect(document.activeElement).toBe(trigger);
    expect(() => useAgentBuilderDocumentStore.getState().prepareSnapshot()).toThrow();
    expect(useAgentBuilderDocumentStore.getState().dirty).toBe(true);
    vi.restoreAllMocks();
  });

  it("keeps required dependency guidance visible outside advanced settings", () => {
    useAgentBuilderDocumentStore.getState().selectNode("reason");
    const requiredCatalog: ComponentCatalog = { ...catalog, components: [{ ...catalog.components[0]!, dependencySlots: [{ name: "llm", required: true, acceptedNamespaces: ["llm"], acceptedCategories: [], configSchema: {} }] }] };
    render(<BuilderInspector catalog={requiredCatalog} />);
    const missing = screen.getByText(/缺少必需依赖/);
    expect(missing.closest("details")).toBeNull();
    expect(screen.getByLabelText("Candidate 1 dependencies")).not.toBeNull();
  });

  it("turns a required llm dependency into a provider/model/SecretRef flow", () => {
    const reasoning = {
      ...catalog.components[0]!,
      dependencySlots: [{ name: "llm", required: true, acceptedNamespaces: ["llm"], acceptedCategories: ["runtime_service"], configSchema: {} }],
    };
    const provider = {
      identifier: "llm:openai_llm@1", namespace: "llm", name: "openai_llm", version: "1", providerId: "fixture",
      placement: "dependency_only" as const, category: "runtime_service",
      contract: { ref: { id: "llm", version: "1.0" }, ports: [], adapter: "runtime_service", sideEffect: "network", idempotent: false },
      configSchema: { type: "object", properties: {
        api_key: { type: "object", properties: { secret_ref: { type: "string" } }, "x-zhixing-secret-ref": true },
        model: { type: "string", default: "gpt-4o" },
      } },
      dependencySlots: [], availability: { available: true, extra: "", errorType: "" }, capabilities: {}, provenance: {}, display: { label: "OpenAI LLM", group: "llm" },
    };
    useAgentBuilderDocumentStore.getState().selectNode("reason");
    render(<BuilderInspector catalog={{ ...catalog, components: [reasoning, provider] }} />);
    fireEvent.change(screen.getByLabelText("模型提供方"), { target: { value: "llm:openai_llm@1" } });
    fireEvent.change(screen.getByLabelText("模型 ID"), { target: { value: "gpt-4.1-mini" } });
    fireEvent.change(screen.getByLabelText("API 凭证 SecretRef"), { target: { value: "openai_api_key" } });
    expect(useAgentBuilderDocumentStore.getState().document?.capabilities[0]?.implementation.candidates[0]?.dependencies).toEqual({
      llm: { namespace: "llm", name: "openai_llm", version: "1", params: { model: "gpt-4.1-mini", api_key: { secret_ref: "openai_api_key" } } },
    });
    expect(screen.getByText(/只填写 SecretRef 名称/)).not.toBeNull();
  });

  it("shows fallback order outside collapsed controls", () => {
    const state = useAgentBuilderDocumentStore.getState();
    state.updateNode("reason", (node) => ({ ...node, implementation: { policy: "fallback", candidates: [...node.implementation.candidates, { ...node.implementation.candidates[0]!, name: "other", version: "2" }] } }));
    state.selectNode("reason");
    render(<BuilderInspector catalog={catalog} />);
    expect(screen.getByText("Ordered fallback · reason · 1 → other · 2").closest("details")).toBeNull();
  });
  it("locates the early missing-LLM error without modifying the draft or clearing its result", () => {
    const state = useAgentBuilderDocumentStore.getState();
    const result: StudioCompileResult = { schemaVersion: 1, isSuccess: false, contractVersion: "1.1", catalogVersion: "catalog", canonicalHash: null, agentGraph: null,
      diagnostics: [{ code: "graph.studio.component_dependency_required", severity: "error", message: "Selected component requires dependency 'llm'", nodeId: "reason", path: ["semantic", "nodes", 2] }], sourceMap: [], projectionMap: [], summary: { errorCount: 1, warningCount: 0, nodeCount: 0, edgeCount: 0 } };
    state.setCompileResult(result);
    const before = useAgentBuilderDocumentStore.getState();
    let revealed = "";
    const unregister = useCanvasInteractionStore.getState().register({ sessionId: before.sessionId, placement: () => null, reveal: (id) => { revealed = id; } });
    render(<BuilderInspector catalog={catalog} />);
    fireEvent.click(screen.getByRole("button", { name: "查看对象" }));
    const after = useAgentBuilderDocumentStore.getState();
    expect(after.selectedCanvasId).toBe("reason");
    expect(revealed).toBe("reason");
    expect(after.document).toEqual(before.document);
    expect(after.generation).toBe(before.generation);
    expect(after.dirty).toBe(before.dirty);
    expect(after.compileResult).toBe(result);
    expect(screen.getByText(/暂不支持定位到具体字段/)).not.toBeNull();
    unregister();
  });
  it("does not dump arbitrary diagnostic details", () => {
    useAgentBuilderDocumentStore.getState().setCompileResult({ schemaVersion: 1, isSuccess: false, contractVersion: "1.1", catalogVersion: "catalog", canonicalHash: null, agentGraph: null,
      diagnostics: [{ code: "unknown", severity: "error", message: "Safe diagnostic", details: { api_key: "must-not-render", privatePath: "/private/hidden" } }], sourceMap: [], projectionMap: [], summary: { errorCount: 1, warningCount: 0, nodeCount: 0, edgeCount: 0 } });
    const view = render(<BuilderInspector catalog={catalog} />);
    expect(screen.queryByRole("button", { name: "查看对象" })).toBeNull();
    expect(view.container.textContent).not.toContain("must-not-render");
    expect(view.container.textContent).not.toContain("/private/hidden");
    expect(screen.getByText("unknown")).not.toBeNull();
  });
  it("counts unfinished raw input as unsaved and preserves it across selection", () => {
    useAgentBuilderDocumentStore.getState().selectNode("reason");
    render(<BuilderInspector catalog={catalog} />);
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    expect(useAgentBuilderDocumentStore.getState().dirty).toBe(true);
    act(() => useAgentBuilderDocumentStore.getState().selectNode("output"));
    act(() => useAgentBuilderDocumentStore.getState().selectNode("reason"));
    expect((screen.getByLabelText("Candidate 1 config") as HTMLTextAreaElement).value).toBe("{");
  });

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

  it("shows Catalog scalar parameters as a form and keeps the advanced JSON value aligned", () => {
    const formCatalog: ComponentCatalog = {
      ...catalog,
      components: [{
        ...catalog.components[0]!,
        configSchema: { type: "object", properties: { retries: { type: "integer", minimum: 0, default: 3 } } },
      }],
    };
    useAgentBuilderDocumentStore.getState().selectNode("reason");
    render(<BuilderInspector catalog={formCatalog} />);
    fireEvent.change(screen.getByLabelText("Config retries"), { target: { value: "4" } });
    expect(useAgentBuilderDocumentStore.getState().document?.capabilities[0]?.implementation.candidates[0]?.params).toEqual({ retries: 4 });
    expect((screen.getByLabelText("Candidate 1 config") as HTMLTextAreaElement).value).toContain('"retries": 4');
  });

  it("edits the feedback predicate and exhaustion policy in the relation inspector", () => {
    const state = useAgentBuilderDocumentStore.getState();
    state.addEdge({
      canvasId: "feedback",
      source: { ownerId: "reason", portId: "action" },
      target: { ownerId: "reason", portId: "task" },
      kind: "feedback",
      feedback: { predicate: { field: "terminal_status", operator: "falsy" }, maxIterations: 3, onExhausted: "fail" },
    });
    state.selectEdge("feedback");
    render(<BuilderInspector catalog={catalog} />);
    fireEvent.change(screen.getByLabelText("Feedback predicate field"), { target: { value: "score" } });
    fireEvent.change(screen.getByLabelText("Feedback predicate operator"), { target: { value: "eq" } });
    fireEvent.change(screen.getByLabelText("Feedback predicate value"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Feedback exhausted policy"), { target: { value: "terminate" } });
    fireEvent.change(screen.getByLabelText("Maximum feedback iterations"), { target: { value: "5" } });
    const relation = useAgentBuilderDocumentStore.getState().document?.relations.find((item) => item.canvasId === "feedback");
    expect(relation?.feedback).toEqual({ predicate: { field: "score", operator: "eq", value: 1 }, maxIterations: 5, onExhausted: "terminate" });
  });
});
