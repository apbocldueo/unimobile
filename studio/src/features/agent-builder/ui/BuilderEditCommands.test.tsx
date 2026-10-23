import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createEmptyStudioDocument, compileStudioDocument, type StudioCompileResult } from "@/entities/agent-graph";
import { getAgentRevision, saveAgentRevision, type AgentRevision } from "@/entities/agent-revision";
import { createStudioAgent } from "@/entities/agent";
import { runtimeReadinessKeys } from "@/entities/runtime-readiness";
import { useAgentBuilderDocumentStore as store } from "../model/builder.store";
import { BuilderInspector } from "./BuilderInspector";
import { BuilderToolbar } from "./BuilderToolbar";

vi.mock("@/entities/agent-graph", async (original) => ({ ...await original<object>(), compileStudioDocument: vi.fn() }));
vi.mock("@/entities/agent-revision", async (original) => ({ ...await original<object>(), saveAgentRevision: vi.fn(), getAgentRevision: vi.fn() }));
vi.mock("@/entities/agent", async (original) => ({ ...await original<object>(), createStudioAgent: vi.fn() }));

/** Observe automatic handoffs without mounting a runtime. */
function LocationProbe() { return <output aria-label="location">{useLocation().pathname}</output>; }

/** Build an editable revision with a known valid compile snapshot. */
function fixture(): AgentRevision {
  const document = createEmptyStudioDocument("agent", "Test", "document");
  document.capabilities.push({ canvasId: "node", logicalId: "node", family: "reasoning", lifecycle: "per_step",
    implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "reason", version: "1", params: {}, dependencies: {} }] } });
  return { revisionId: "r1", agentId: "agent", ordinal: 1, parentRevisionId: null, document,
    compileSnapshot: { status: "valid", diagnostics: [], sourceMap: [], canonicalHash: `sha256:${"a".repeat(64)}`, agentGraph: {} }, createdAt: 1 };
}

/** Provide a deferred response so editing can interleave with a real command boundary. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

/** Mount real Inspector and toolbar against isolated cached readiness. */
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  client.setQueryData(runtimeReadinessKeys.process, { schemaVersion: 1, ready: true, providers: [], secrets: [], deviceProfiles: [], diagnostics: [] });
  render(<QueryClientProvider client={client}><MemoryRouter ><BuilderToolbar agentName="Test" catalogVersion="catalog" onReload={vi.fn()} /><BuilderInspector catalog={null} /><LocationProbe /></MemoryRouter></QueryClientProvider>);
  return client;
}

beforeEach(() => { vi.clearAllMocks(); store.getState().hydrate(fixture()); store.getState().selectNode("node"); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); store.getState().clear(); });

describe("current-content Builder commands", () => {
  it("preserves newer expanded edits during saving and closes on session replacement", async () => {
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } });
    Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); } });
    const pending = deferred<Awaited<ReturnType<typeof saveAgentRevision>>>();
    vi.mocked(saveAgentRevision).mockReturnValue(pending.promise);
    setup();
    fireEvent.click(screen.getByText("高级参数 JSON"));
    fireEvent.click(screen.getByRole("button", { name: "Expand Candidate 1 config" }));
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: '{"count":1}' } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(saveAgentRevision).toHaveBeenCalledOnce());
    const saved = vi.mocked(saveAgentRevision).mock.calls[0]![0].document;
    expect(saved.capabilities[0]!.implementation.candidates[0]!.params).toEqual({ count: 1 });
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    await act(async () => pending.resolve({ agent: { agentId: "agent", name: "Test", currentRevisionId: "r2", createdAt: 1, updatedAt: 2 }, revision: { ...fixture(), revisionId: "r2", document: saved } }));
    await waitFor(() => expect(store.getState().baseRevisionId).toBe("r2"));
    expect((screen.getByLabelText("Candidate 1 config") as HTMLTextAreaElement).value).toBe("{");
    expect(store.getState().dirty).toBe(true);
    act(() => store.getState().hydrate(fixture()));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("does not validate old content when the visible JSON is invalid", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    fireEvent.click(screen.getByRole("button", { name: "检查流程" }));
    expect(compileStudioDocument).not.toHaveBeenCalled();
    expect(screen.queryByText("流程检查通过")).toBeNull();
    expect(screen.getByText("草稿有未保存修改")).not.toBeNull();
  });

  it("saves the focused latest text in one click and permits compile-invalid revisions", async () => {
    vi.mocked(saveAgentRevision).mockImplementation(async (input) => ({ schemaVersion: 1, agent: { agentId: "agent", name: "Test", currentRevisionId: "r2", createdAt: 1, updatedAt: 2 }, revision: { ...fixture(), revisionId: "r2", document: input.document, compileSnapshot: { status: "invalid", diagnostics: [], sourceMap: [] } } }));
    setup();
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: '{"count":3}' } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(store.getState().baseRevisionId).toBe("r2"));
    expect(vi.mocked(saveAgentRevision).mock.calls[0]![0].document.capabilities[0]!.implementation.candidates[0]!.params).toEqual({ count: 3 });
    expect(store.getState().dirty).toBe(false);
    expect(store.getState().compileResult?.isSuccess).toBe(false);
  });

  it("does not apply delayed validation A to edited B", async () => {
    const pending = deferred<StudioCompileResult>();
    const result = store.getState().compileResult!;
    vi.mocked(compileStudioDocument).mockReturnValue(pending.promise);
    setup();
    fireEvent.click(screen.getByRole("button", { name: "检查流程" }));
    await waitFor(() => expect(compileStudioDocument).toHaveBeenCalledOnce());
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: '{"count":2}' } });
    await act(async () => pending.resolve(result));
    expect(store.getState().compileResult).toBeNull();
  });

  it("accepts delayed validation across layout and camera changes", async () => {
    const pending = deferred<StudioCompileResult>();
    const result = store.getState().compileResult!;
    vi.mocked(compileStudioDocument).mockReturnValue(pending.promise);
    setup();
    fireEvent.click(screen.getByRole("button", { name: "检查流程" }));
    await waitFor(() => expect(compileStudioDocument).toHaveBeenCalledOnce());
    act(() => {
      store.getState().setNodePosition("node", 140, 260);
      store.getState().setViewport(100, 200, 0.8);
      store.getState().setCompileResult(null);
    });
    await act(async () => pending.resolve(result));
    expect(store.getState().compileResult).toBe(result);
    expect(screen.getByText("布局有未保存修改")).not.toBeNull();
  });

  it("retains B while save A is pending and advances only the baseline", async () => {
    const pending = deferred<Awaited<ReturnType<typeof saveAgentRevision>>>();
    vi.mocked(saveAgentRevision).mockReturnValue(pending.promise);
    setup();
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: '{"count":1}' } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(saveAgentRevision).toHaveBeenCalledOnce());
    const saved = vi.mocked(saveAgentRevision).mock.calls[0]![0].document;
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    await act(async () => pending.resolve({ agent: { agentId: "agent", name: "Test", currentRevisionId: "r2", createdAt: 1, updatedAt: 2 }, revision: { ...fixture(), revisionId: "r2", document: saved } }));
    await waitFor(() => expect(store.getState().baseRevisionId).toBe("r2"));
    expect((screen.getByLabelText("Candidate 1 config") as HTMLTextAreaElement).value).toBe("{");
    expect(store.getState().dirty).toBe(true);
  });

  it.each(["edit", "replace"])("does not hand off 保存并试跑 after a pending %s", async (mode) => {
    const pending = deferred<Awaited<ReturnType<typeof saveAgentRevision>>>();
    vi.mocked(saveAgentRevision).mockReturnValue(pending.promise);
    setup();
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: '{"count":1}' } });
    fireEvent.click(screen.getByRole("button", { name: "保存并试跑" }));
    await waitFor(() => expect(saveAgentRevision).toHaveBeenCalledOnce());
    const saved = vi.mocked(saveAgentRevision).mock.calls[0]![0].document;
    if (mode === "edit") fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    else act(() => store.getState().hydrate(fixture()));
    await act(async () => pending.resolve({ agent: { agentId: "agent", name: "Test", currentRevisionId: "r2", createdAt: 1, updatedAt: 2 }, revision: { ...fixture(), revisionId: "r2", document: saved } }));
    expect(screen.getByLabelText("location").textContent).toBe("/");
    if (mode === "replace") expect(store.getState().baseRevisionId).toBe("r1");
  });

  it.each(["edit", "replace"])("does not navigate Save As after a pending %s", async (mode) => {
    const pending = deferred<Awaited<ReturnType<typeof createStudioAgent>>>();
    vi.mocked(createStudioAgent).mockReturnValue(pending.promise);
    vi.spyOn(window, "prompt").mockReturnValue("Copy");
    setup();
    fireEvent.click(screen.getByText("更多操作"));
    fireEvent.click(screen.getByRole("button", { name: "另存为" }));
    await waitFor(() => expect(createStudioAgent).toHaveBeenCalledOnce());
    if (mode === "edit") fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    else act(() => store.getState().hydrate(fixture()));
    await act(async () => pending.resolve({ agent: { agentId: "copy", name: "Copy", currentRevisionId: "copy-r1", createdAt: 1, updatedAt: 1 }, currentRevision: null }));
    expect(screen.getByLabelText("location").textContent).toBe("/");
  });

  it("never exports or creates from unsafe raw source", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: '{"password":"CANARY_NOT_REAL"}' } });
    fireEvent.click(screen.getByText("更多操作"));
    fireEvent.click(screen.getByRole("button", { name: "另存为" }));
    fireEvent.click(screen.getByRole("button", { name: "导出" }));
    expect(createStudioAgent).not.toHaveBeenCalled();
    expect(saveAgentRevision).not.toHaveBeenCalled();
    expect(compileStudioDocument).not.toHaveBeenCalled();
    expect(screen.getByLabelText("location").textContent).not.toContain("CANARY");
    expect(document.activeElement).toBe(screen.getByLabelText("Candidate 1 config"));
  });

  it("does not replace new raw work with a delayed revision load", async () => {
    const pending = deferred<AgentRevision>();
    vi.mocked(getAgentRevision).mockReturnValue(pending.promise);
    vi.spyOn(window, "prompt").mockReturnValue("old-revision");
    setup();
    fireEvent.click(screen.getByText("更多操作"));
    fireEvent.click(screen.getByRole("button", { name: "加载历史版本" }));
    await waitFor(() => expect(getAgentRevision).toHaveBeenCalledOnce());
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    await act(async () => pending.resolve({ ...fixture(), revisionId: "old-revision" }));
    expect(store.getState().baseRevisionId).toBe("r1");
    expect((screen.getByLabelText("Candidate 1 config") as HTMLTextAreaElement).value).toBe("{");
  });

  it("preserves invalid input on cancelled reset and revision replacement", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    setup();
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    fireEvent.click(screen.getByText("更多操作"));
    fireEvent.click(screen.getByRole("button", { name: "放弃修改" }));
    expect((screen.getByLabelText("Candidate 1 config") as HTMLTextAreaElement).value).toBe("{");
    fireEvent.click(screen.getByRole("button", { name: "加载历史版本" }));
    await waitFor(() => expect(window.confirm).toHaveBeenCalledTimes(2));
    expect(getAgentRevision).not.toHaveBeenCalled();
    expect(store.getState().dirty).toBe(true);
  });

  it("does not hand off a saved revision if readiness changed during saving", async () => {
    const pending = deferred<Awaited<ReturnType<typeof saveAgentRevision>>>();
    vi.mocked(saveAgentRevision).mockReturnValue(pending.promise);
    const client = setup();
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: '{"count":1}' } });
    fireEvent.click(screen.getByRole("button", { name: "保存并试跑" }));
    await waitFor(() => expect(saveAgentRevision).toHaveBeenCalledOnce());
    const saved = vi.mocked(saveAgentRevision).mock.calls[0]![0].document;
    act(() => client.setQueryData(runtimeReadinessKeys.process, { schemaVersion: 1, ready: false, providers: [], secrets: [], deviceProfiles: [], diagnostics: [] }));
    await act(async () => pending.resolve({ agent: { agentId: "agent", name: "Test", currentRevisionId: "r2", createdAt: 1, updatedAt: 2 }, revision: { ...fixture(), revisionId: "r2", document: saved } }));
    expect(store.getState().dirty).toBe(false);
    expect(screen.getByLabelText("location").textContent).toBe("/");
  });

  it("rejects a malformed import without replacing existing raw input", async () => {
    setup();
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    const session = store.getState().sessionId;
    const file = new File(["not-json"], "invalid.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: async () => "not-json" });
    await act(async () => fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } }));
    expect(store.getState().sessionId).toBe(session);
    expect((screen.getByLabelText("Candidate 1 config") as HTMLTextAreaElement).value).toBe("{");
  });

  it("ignores a valid import read when editing advanced while reading", async () => {
    setup();
    const read = deferred<string>();
    const file = new File([""], "candidate.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: () => read.promise });
    fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText("Candidate 1 config"), { target: { value: "{" } });
    await act(async () => read.resolve(JSON.stringify(fixture().document)));
    expect((screen.getByLabelText("Candidate 1 config") as HTMLTextAreaElement).value).toBe("{");
    expect(store.getState().baseRevisionId).toBe("r1");
  });
});
