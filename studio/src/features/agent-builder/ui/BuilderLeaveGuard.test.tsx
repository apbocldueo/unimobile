import { StrictMode } from "react";
import { transferableAbortController } from "node:util";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, Link, RouterProvider, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { saveAgentRevision, type AgentRevision } from "@/entities/agent-revision";
import { useAgentBuilderDocumentStore as store } from "../model/builder.store";
import { BuilderLeaveGuard } from "./BuilderLeaveGuard";

vi.mock("@/entities/agent-revision", async (original) => ({ ...await original<object>(), saveAgentRevision: vi.fn() }));

/** Expose both anchor and imperative departures through the production blocker. */
function Editor() {
  const navigate = useNavigate();
  return <><BuilderLeaveGuard /><Link to="/agents">Agents</Link><Link to="/settings">设置</Link><Link to="/run">运行</Link>
    <button onClick={() => navigate("/settings")}>查看 Settings</button><Link to="/help" target="_blank">新窗口帮助</Link></>;
}

/** Mount the supported data-router integration with a real history stack. */
function setup() {
  const router = createMemoryRouter([{ path: "/edit", element: <Editor /> }, { path: "*", element: <p>Destination</p> }], { initialEntries: ["/previous", "/edit"], initialIndex: 1 });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<StrictMode><QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider></StrictMode>);
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
  // Match Node's Request realm instead of JSDOM's incompatible AbortSignal.
  vi.stubGlobal("AbortController", class { constructor() { return transferableAbortController(); } });
  // JSDOM has no modal implementation; real focus/inert behavior is browser acceptance.
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: vi.fn(function (this: HTMLDialogElement) { this.open = true; }),
  });
  store.getState().replaceDocument(createEmptyStudioDocument("agent", "Test", "document"), "r1");
  store.getState().updateCurrentDocument((document) => ({ ...document, name: "Changed" }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); store.getState().clear(); });

describe("Builder routed departure", () => {
  it.each(["Agents", "设置", "运行", "查看 Settings"])("retains editing when cancelling %s", async (name) => {
    const router = setup();
    fireEvent.click(screen.getByText(name));
    expect(await screen.findByRole("dialog")).not.toBeNull();
    fireEvent.click(screen.getByText("继续编辑"));
    expect(router.state.location.pathname).toBe("/edit");
    expect(store.getState().document!.name).toBe("Changed");
  });

  it("blocks POP, supports cancellation, and proceeds only on explicit discard", async () => {
    const router = setup();
    await act(async () => { await router.navigate(-1); });
    fireEvent.click(await screen.findByText("继续编辑"));
    expect(router.state.location.pathname).toBe("/edit");
    await act(async () => { await router.navigate(-1); });
    fireEvent.click(await screen.findByText("放弃修改并离开"));
    await waitFor(() => expect(router.state.location.pathname).toBe("/previous"));
  });

  it("does not block clean sessions", async () => {
    store.getState().resetToBaseline();
    const router = setup();
    fireEvent.click(screen.getByText("Agents"));
    await waitFor(() => expect(router.state.location.pathname).toBe("/agents"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps failed saves in the original editing session", async () => {
    vi.mocked(saveAgentRevision).mockRejectedValue(new Error("offline"));
    const router = setup();
    fireEvent.click(screen.getByText("设置"));
    fireEvent.click(await screen.findByText("保存并离开"));
    expect(await screen.findByText(/未能确认保存成功/)).not.toBeNull();
    expect(router.state.location.pathname).toBe("/edit");
    expect(store.getState().dirty).toBe(true);
  });

  it.each([false, true])("save-before-leave retains edits made during saving: %s", async (editDuringSave) => {
    let resolve!: (value: Awaited<ReturnType<typeof saveAgentRevision>>) => void;
    vi.mocked(saveAgentRevision).mockImplementation(() => new Promise((done) => { resolve = done; }));
    const router = setup();
    fireEvent.click(screen.getByText("设置"));
    fireEvent.click(await screen.findByText("保存并离开"));
    await waitFor(() => expect(saveAgentRevision).toHaveBeenCalledOnce());
    expect((screen.getByText("正在保存…") as HTMLButtonElement).disabled).toBe(true);
    const saved = vi.mocked(saveAgentRevision).mock.calls[0]![0].document;
    if (editDuringSave) act(() => store.getState().updateCurrentDocument((document) => ({ ...document, name: "Newer" })));
    const revision: AgentRevision = { agentId: "agent", revisionId: "r2", ordinal: 2, parentRevisionId: "r1", document: saved, compileSnapshot: { status: "invalid", diagnostics: [], sourceMap: [] }, createdAt: 2 };
    await act(async () => resolve({ agent: { agentId: "agent", name: "Test", currentRevisionId: "r2", createdAt: 1, updatedAt: 2 }, revision }));
    if (editDuringSave) {
      expect(await screen.findByText(/已有更新的编辑未保存/)).not.toBeNull();
      expect(router.state.location.pathname).toBe("/edit");
      expect(store.getState().document!.name).toBe("Newer");
    } else await waitFor(() => expect(router.state.location.pathname).toBe("/settings"));
  });

  it("does not intercept a new-tab link", () => {
    const router = setup();
    // Stop JSDOM's unsupported new-window default after React's handler runs.
    const link = screen.getByText("新窗口帮助");
    document.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(link);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(router.state.location.pathname).toBe("/edit");
    expect(store.getState().dirty).toBe(true);
  });
});
