import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { saveAgentRevision, type AgentRevision } from "@/entities/agent-revision";
import { StudioApiError } from "@/shared/api";
import { useToastStore } from "@/stores/toastStore";
import { useAgentBuilderDocumentStore as store } from "./builder.store";
import { useSaveAgentRevisionCommand } from "./useSaveAgentRevisionCommand";

vi.mock("@/entities/agent-revision", async (original) => ({ ...await original<object>(), saveAgentRevision: vi.fn() }));

/** Construct a schema-valid incomplete graph; incomplete graphs are saveable drafts. */
function fixture(): AgentRevision {
  return { agentId: "a", revisionId: "r1", ordinal: 1, parentRevisionId: null, createdAt: 1,
    document: createEmptyStudioDocument("a", "Test", "d"), compileSnapshot: { status: "invalid", diagnostics: [], sourceMap: [] } };
}

/** Prepare exactly the same invocation boundary used by toolbar and leave dialog. */
function input() { const snapshot = store.getState().prepareSnapshot(); return { document: snapshot.document, baseRevisionId: snapshot.baseRevisionId, snapshot }; }

/** Mount two consumers to test the shared session lock rather than a hook-local flag. */
function setup() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return renderHook(() => [useSaveAgentRevisionCommand(), useSaveAgentRevisionCommand()] as const, {
    wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  });
}

beforeEach(() => { vi.clearAllMocks(); store.getState().hydrate(fixture()); });
afterEach(() => { cleanup(); store.getState().clear(); for (const toast of useToastStore.getState().toasts) useToastStore.getState().dismiss(toast.id); });

describe("shared save command ownership", () => {
  it("serializes separate consumers without releasing another request's lock", async () => {
    let resolve!: (value: Awaited<ReturnType<typeof saveAgentRevision>>) => void;
    vi.mocked(saveAgentRevision).mockImplementation(() => new Promise((done) => { resolve = done; }));
    const { result } = setup();
    let first!: Promise<unknown>;
    act(() => { first = result.current[0].mutateAsync(input()); });
    await waitFor(() => expect(saveAgentRevision).toHaveBeenCalledOnce());
    await act(async () => { await expect(result.current[1].mutateAsync(input())).rejects.toThrow("已有保存正在进行"); });
    expect(store.getState().savePending).toBe(true);
    await act(async () => { resolve({ agent: { agentId: "a", name: "Test", currentRevisionId: "r2", createdAt: 1, updatedAt: 2 }, revision: { ...fixture(), revisionId: "r2" } }); await first; });
    expect(store.getState().savePending).toBe(false);
    expect(input().baseRevisionId).toBe("r2");
  });

  it("ignores a late conflict after the same Agent was rehydrated", async () => {
    let reject!: (error: Error) => void;
    vi.mocked(saveAgentRevision).mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
    const { result } = setup();
    let pending!: Promise<unknown>;
    act(() => { pending = result.current[0].mutateAsync(input()).catch(() => undefined); });
    await waitFor(() => expect(saveAgentRevision).toHaveBeenCalledOnce());
    act(() => store.getState().hydrate(fixture()));
    await act(async () => { reject(new StudioApiError(409, { error: { currentRevisionId: "remote" } })); await pending; });
    expect(store.getState().conflictRevisionId).toBeNull();
    expect(useToastStore.getState().toasts).toEqual([]);
  });

  it("rejects an invocation captured before a session replacement", async () => {
    const captured = input();
    store.getState().hydrate(fixture());
    const { result } = setup();
    await act(async () => { await expect(result.current[0].mutateAsync(captured)).rejects.toThrow("编辑内容已变化"); });
    expect(saveAgentRevision).not.toHaveBeenCalled();
    expect(store.getState().savePending).toBe(false);
  });
});
