import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createEmptyStudioDocument, createEmptyLegacyStudioDocument } from "@/entities/agent-graph";
import { getStudioAgent } from "@/entities/agent";
import { useAgentBuilderDocumentStore as store } from "@/features/agent-builder";
import { AgentBuilderWorkbench } from "./AgentBuilderWorkbench";

// Exercise workbench hydration/cleanup/unload without unrelated canvas rendering.
vi.mock("@/features/agent-builder", async (original) => ({
  ...await original<object>(),
  AgentBuilderFlowProvider: ({ children }: { children: React.ReactNode }) => children,
  BuilderLeaveGuard: () => null, BuilderCanvas: () => null, BuilderInspector: () => null,
  BuilderPalette: () => null, BuilderToolbar: ({ onReload }: { onReload: () => Promise<void> }) => <button onClick={() => void onReload()}>Reload test</button>,
}));
vi.mock("@/entities/agent", async (original) => ({ ...await original<object>(), getStudioAgent: vi.fn() }));

/** Cache a safe current revision without network, devices or model dependencies. */
function seed(client: QueryClient, agentId: string) {
  const document = createEmptyStudioDocument(agentId, agentId, `document-${agentId}`);
  document.capabilities.push({ canvasId: "node", logicalId: "node", family: "reasoning", lifecycle: "per_step", implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "reason", version: "1", params: {}, dependencies: {} }] } });
  client.setQueryData(["studio-agent", agentId], { agent: { agentId, name: agentId }, currentRevision: { agentId, revisionId: `${agentId}-r1`, document, compileSnapshot: { status: "invalid", diagnostics: [], sourceMap: [] } } });
  client.setQueryData(["studio-component-catalog"], {});
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); store.getState().clear(); });

describe("Builder workbench lifecycle", () => {
  it("keeps a historical Agent opened from Home read-only instead of offering editing", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
    seed(client, "legacy");
    const cached = client.getQueryData<Record<string, unknown>>(["studio-agent", "legacy"])!;
    client.setQueryData(["studio-agent", "legacy"], { ...cached, currentRevision: {
      agentId: "legacy", revisionId: "legacy-r1", document: createEmptyLegacyStudioDocument("legacy", "Legacy", "legacy-document"),
      compileSnapshot: { status: "invalid", diagnostics: [], sourceMap: [] },
    } });
    render(<QueryClientProvider client={client}><AgentBuilderWorkbench agentId="legacy" /></QueryClientProvider>);
    expect(await screen.findByText(/此 Revision 使用历史 Studio 图契约/)).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Reload test" })).toBeNull();
    expect(store.getState().document).toBeNull();
  });
  it("hydrates in StrictMode, guards raw unload, releases after unmount, and replaces Agent identity", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
    seed(client, "a"); seed(client, "b");
    /** Preserve React component identity while switching the routed Agent. */
    const view = (agentId: string) => <StrictMode><QueryClientProvider client={client}><AgentBuilderWorkbench agentId={agentId} /></QueryClientProvider></StrictMode>;
    const mounted = render(view("a"));
    await waitFor(() => expect(store.getState().agentId).toBe("a"));
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    act(() => store.getState().editRaw({ canvasId: "node", candidate: 0, implementation: '["agent.reasoning","reason","1"]', property: "params" }, "{"));
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
    const originalSession = store.getState().sessionId;
    // The route guard authorizes departures separately; this checks authorized reuse.
    mounted.rerender(view("b"));
    await waitFor(() => expect(store.getState().agentId).toBe("b"));
    expect(store.getState().sessionId).toBeGreaterThan(originalSession);
    expect(store.getState().dirty).toBe(false);
    expect(store.getState().rawFields).toEqual({});
    mounted.unmount();
    expect(store.getState().document).toBeNull();
    const closed = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(closed);
    expect(closed.defaultPrevented).toBe(false);
  });

  it("does not treat cached data as a successful reload after transport failure", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
    seed(client, "a");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(getStudioAgent).mockRejectedValue(new Error("offline"));
    render(<QueryClientProvider client={client}><AgentBuilderWorkbench agentId="a" /></QueryClientProvider>);
    await waitFor(() => expect(store.getState().agentId).toBe("a"));
    act(() => store.getState().updateCurrentDocument((document) => ({ ...document, name: "New work" })));
    fireEvent.click(screen.getByText("Reload test"));
    await waitFor(() => expect(client.getQueryState(["studio-agent", "a"])?.status).toBe("error"));
    expect(store.getState().document!.name).toBe("New work");
    expect(store.getState().dirty).toBe(true);
    expect(screen.getByText("Reload test")).not.toBeNull();
  });
});
