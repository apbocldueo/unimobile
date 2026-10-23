import { beforeEach, describe, expect, it, vi } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import type { AgentRevision } from "@/entities/agent-revision";
import { useAgentBuilderDocumentStore as store } from "./builder.store";
import { candidateIdentity, rawFieldKey } from "./editSession";
import { appendHistory, HISTORY_LIMIT, HISTORY_BYTE_LIMIT } from "./editHistory";

/** Build a saved editor fixture; its valid snapshot tests state, not runtime support. */
function revision(): AgentRevision {
  const document = createEmptyStudioDocument("history-agent", "History", "history-doc");
  document.capabilities = [{ canvasId: "reason", logicalId: "reason", family: "reasoning", lifecycle: "per_step",
    implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "reason", version: "1", params: {}, dependencies: {} }] } }];
  document.presentation.nodes.reason = { x: 200, y: 100 };
  document.relations = [{ canvasId: "edge", source: { ownerId: "input", portId: "task" }, target: { ownerId: "reason", portId: "task" }, kind: "data" }];
  return { revisionId: "r1", agentId: document.agentId, ordinal: 1, parentRevisionId: null, document,
    compileSnapshot: { status: "valid", diagnostics: [], sourceMap: [] }, createdAt: 1 };
}

/** Return an exact parameter owner for raw-buffer history assertions. */
function owner() {
  return { canvasId: "reason", candidate: 0, implementation: candidateIdentity(store.getState().document!.capabilities[0]!, 0), property: "params" as const };
}

beforeEach(() => { vi.restoreAllMocks(); store.getState().hydrate(revision()); });

describe("bounded Builder editing history", () => {
  it("restores a deleted node, incident relation and invalid raw input atomically", () => {
    const field = owner();
    store.getState().editRaw(field, "{");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    store.getState().removeElements(["reason"], ["edge"]);
    store.getState().undo();
    expect(store.getState().document!.relations).toHaveLength(1);
    expect(store.getState().document!.capabilities).toHaveLength(1);
    expect(store.getState().rawFields[rawFieldKey(field)]?.text).toBe("{");
    expect(store.getState().inputError).toBeTruthy();
    store.getState().redo();
    expect(store.getState().document!.capabilities).toHaveLength(0);
    expect(store.getState().document!.relations).toHaveLength(0);
    expect(store.getState().inputError).toBeNull();
  });

  it("coalesces field typing but keeps later edits and redo branches separate", () => {
    store.getState().editRaw(owner(), "{");
    store.getState().editRaw(owner(), '{"count":2}');
    store.getState().prepareSnapshot();
    expect(store.getState().past).toHaveLength(1);
    store.getState().undo();
    expect(store.getState().dirty).toBe(false);
    store.getState().redo();
    expect(store.getState().prepareSnapshot().document.capabilities[0]!.implementation.candidates[0]!.params).toEqual({ count: 2 });
    store.getState().undo();
    store.getState().setNodePosition("reason", 320, 180);
    expect(store.getState().future).toHaveLength(0);
  });

  it("preserves save and conflict authority while undo invalidates an in-flight snapshot", () => {
    store.getState().editRaw(owner(), '{"count":2}');
    const snapshot = store.getState().prepareSnapshot();
    store.getState().acknowledgeSave(snapshot, { ...revision(), revisionId: "r2", document: snapshot.document });
    store.getState().setConflict("r3");
    store.getState().undo();
    expect(store.getState().baseRevisionId).toBe("r2");
    expect(store.getState().conflictRevisionId).toBe("r3");
    expect(store.getState().matchesSnapshot(snapshot)).toBe(false);
    expect(store.getState().dirty).toBe(true);
    store.getState().redo();
    expect(store.getState().dirty).toBe(false);
    expect(store.getState().matchesSnapshot(snapshot)).toBe(false);
  });

  it("keeps a new baseline but does not erase undo performed while a save was pending", () => {
    store.getState().editRaw(owner(), '{"count":2}');
    const snapshot = store.getState().prepareSnapshot();
    store.getState().undo();
    store.getState().acknowledgeSave(snapshot, { ...revision(), revisionId: "r2", document: snapshot.document });
    expect(store.getState().baseRevisionId).toBe("r2");
    expect(store.getState().document!.capabilities[0]!.implementation.candidates[0]!.params).toEqual({});
    expect(store.getState().dirty).toBe(true);
  });

  it("keeps camera temporary and node layout undoable without clearing validation", () => {
    const before = store.getState();
    store.getState().setViewport(100, -80, 0.7);
    expect(store.getState().document).toBe(before.document);
    expect(store.getState().generation).toBe(before.generation);
    expect(store.getState().dirty).toBe(false);
    expect(store.getState().past).toHaveLength(0);
    store.getState().setNodePosition("reason", 300, 200);
    expect(store.getState().compileResult).toBe(before.compileResult);
    expect(store.getState().dirty).toBe(true);
    store.getState().undo();
    expect(store.getState().document!.presentation.nodes.reason).toEqual(before.document!.presentation.nodes.reason);
    expect(store.getState().compileResult).toBe(before.compileResult);
    expect(store.getState().dirty).toBe(false);
  });

  it("accepts validation across layout changes but rejects new semantic input and sessions", () => {
    const snapshot = store.getState().prepareSnapshot();
    store.getState().setNodePosition("reason", 300, 200);
    expect(store.getState().matchesValidationSnapshot(snapshot)).toBe(true);
    store.getState().editRaw(owner(), "{");
    expect(store.getState().matchesValidationSnapshot(snapshot)).toBe(false);
    store.getState().hydrate(revision());
    expect(store.getState().past).toHaveLength(0);
    expect(store.getState().future).toHaveLength(0);
    expect(store.getState().matchesValidationSnapshot(snapshot)).toBe(false);
  });

  it("keeps server validation when only layout changes during save", () => {
    const snapshot = store.getState().prepareSnapshot();
    store.getState().setNodePosition("reason", 80, 100);
    store.getState().acknowledgeSave(snapshot, { ...revision(), revisionId: "r2" });
    expect(store.getState().baseRevisionId).toBe("r2");
    expect(store.getState().dirty).toBe(true);
    expect(store.getState().compileResult?.isSuccess).toBe(true);
    expect(store.getState().document?.presentation.nodes.reason?.x).toBe(80);
  });

  it("bounds memory and never keeps an oversized checkpoint", () => {
    const entry = { document: revision().document as ReturnType<typeof createEmptyStudioDocument>, rawFields: {}, selectedCanvasId: null, selectedEdgeId: null };
    let history: import("./editHistory").HistoryEntry[] = [];
    for (let i = 0; i < 80; i += 1) history = appendHistory(history, entry);
    expect(history).toHaveLength(HISTORY_LIMIT);
    expect(appendHistory(history, { ...entry, document: { ...entry.document, name: "x".repeat(HISTORY_BYTE_LIMIT) } })).toHaveLength(0);
  });
});
