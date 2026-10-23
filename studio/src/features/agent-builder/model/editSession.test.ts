import { beforeEach, describe, expect, it, vi } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import type { AgentRevision } from "@/entities/agent-revision";
import { useAgentBuilderDocumentStore as store } from "./builder.store";
import { candidateIdentity, rawFieldKey, type RawFieldOwner } from "./editSession";

/** Create a safe schema-3 revision with one editable capability for session tests. */
function fixture(): AgentRevision {
  const document = createEmptyStudioDocument("agent", "Test", "document");
  document.capabilities.push({ canvasId: "node", logicalId: "node", family: "reasoning", lifecycle: "per_step",
    implementation: { policy: "single", candidates: [{ namespace: "agent.reasoning", name: "reason", version: "1", params: {}, dependencies: {} }] } });
  return { revisionId: "r1", agentId: "agent", ordinal: 1, parentRevisionId: null, document, compileSnapshot: { status: "invalid", diagnostics: [], sourceMap: [] }, createdAt: 1 };
}

/** Return the exact owner of the test parameter field. */
function owner(property: RawFieldOwner["property"] = "params"): RawFieldOwner {
  return { canvasId: "node", candidate: 0, implementation: candidateIdentity(store.getState().document!.capabilities[0]!, 0), property };
}

beforeEach(() => { vi.restoreAllMocks(); store.getState().hydrate(fixture()); });

describe("Builder editing session", () => {
  it("prepares all fields atomically and retains valid siblings when another is invalid", () => {
    store.getState().editRaw(owner(), '{"temperature":0.4}');
    store.getState().editRaw(owner("dependencies"), "{");
    expect(() => store.getState().prepareSnapshot()).toThrow("JSON 格式错误");
    expect(store.getState().document!.capabilities[0]!.implementation.candidates[0]!.params).toEqual({});
    expect(Object.keys(store.getState().rawFields)).toHaveLength(2);
    expect(store.getState().focusField).toBe(rawFieldKey(owner("dependencies")));
  });

  it("does not leak malformed source or a synthetic credential through errors", () => {
    for (const text of ['{"password":"CANARY_NOT_A_REAL_SECRET"}', 'CANARY_NOT_A_REAL_SECRET']) {
      store.getState().editRaw(owner(), text);
      let message = "";
      try { store.getState().prepareSnapshot(); } catch (error) { message = (error as Error).message; }
      expect(message).not.toContain("CANARY");
      expect(store.getState().inputError).not.toContain("CANARY");
      expect(JSON.stringify(store.getState().document)).not.toContain("CANARY");
    }
  });

  it("returns to clean for equivalent JSON and a reverted edit", () => {
    store.getState().editRaw(owner(), "{\n }");
    expect(store.getState().dirty).toBe(false);
    store.getState().editRaw(owner(), '{"count":1}');
    expect(store.getState().dirty).toBe(true);
    store.getState().editRaw(owner(), "{}");
    expect(store.getState().dirty).toBe(false);
  });

  it("locates schema-invalid fields without echoing a host path", () => {
    store.getState().editRaw(owner(), '{"file":"/private/NO_REAL_PATH"}');
    expect(store.getState().inputError).not.toBeNull();
    expect(store.getState().inputError).not.toContain("NO_REAL_PATH");
    expect(() => store.getState().prepareSnapshot()).toThrow();
    expect(store.getState().focusField).toBe(rawFieldKey(owner()));
  });

  it("preserves B and raw text when save A is acknowledged", () => {
    store.getState().editRaw(owner(), '{"count":1}');
    const a = store.getState().prepareSnapshot();
    store.getState().editRaw(owner(), "{");
    store.getState().acknowledgeSave(a, { ...fixture(), revisionId: "r2", document: a.document });
    expect(store.getState().baseRevisionId).toBe("r2");
    expect(store.getState().dirty).toBe(true);
    expect(store.getState().rawFields[rawFieldKey(owner())]!.text).toBe("{");
    expect(store.getState().compileResult).toBeNull();
  });

  it("ignores save acknowledgement after session replacement, even for the same Agent", () => {
    const a = store.getState().prepareSnapshot();
    store.getState().hydrate(fixture());
    store.getState().acknowledgeSave(a, { ...fixture(), revisionId: "wrong" });
    expect(store.getState().baseRevisionId).toBe("r1");
    expect(store.getState().matchesSnapshot(a)).toBe(false);
  });

  it("keeps conflict authority across raw and parsed edits", () => {
    store.getState().setConflict("remote");
    store.getState().editRaw(owner(), '{"count":1}');
    store.getState().prepareSnapshot();
    store.getState().setNodePosition("node", 50, 40);
    expect(store.getState().conflictRevisionId).toBe("remote");
  });

  it("confirms owner removal and preserves input when cancelled", () => {
    store.getState().editRaw(owner(), "{");
    vi.spyOn(window, "confirm").mockReturnValue(false);
    store.getState().removeNodes(["node"]);
    expect(store.getState().document!.capabilities).toHaveLength(1);
    expect(Object.keys(store.getState().rawFields)).toHaveLength(1);
    vi.mocked(window.confirm).mockReturnValue(true);
    store.getState().removeNodes(["node"]);
    expect(store.getState().document!.capabilities).toHaveLength(0);
    expect(Object.keys(store.getState().rawFields)).toHaveLength(0);
  });

  it("invalidates snapshot ownership on viewport and node edits without changing execution content", () => {
    const snapshot = store.getState().prepareSnapshot();
    store.getState().setNodePosition("node", 150, 250);
    expect(store.getState().matchesSnapshot(snapshot)).toBe(false);
    expect(store.getState().document!.capabilities).toEqual(snapshot.document.capabilities);
  });

  it("preserves current CAS baseline when importing a replacement draft", () => {
    const document = store.getState().document!;
    store.getState().importDocument({ ...document, name: "Imported" });
    expect(store.getState().baseRevisionId).toBe("r1");
    expect(store.getState().dirty).toBe(true);
  });

  it("rejects reused candidate slots and clears only explicitly discarded owners", () => {
    const oldOwner = owner();
    store.getState().editRaw(oldOwner, "{");
    store.getState().updateNode("node", (node) => ({ ...node, implementation: { ...node.implementation, candidates: [{ ...node.implementation.candidates[0]!, name: "replacement" }] } }));
    expect(() => store.getState().prepareSnapshot()).toThrow("配置所属组件已变化");
    expect(store.getState().rawFields[rawFieldKey(oldOwner)]!.text).toBe("{");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    expect(store.getState().confirmDiscardFields(["node"])).toBe(true);
    expect(store.getState().prepareSnapshot().document.capabilities[0]!.implementation.candidates[0]!.params).toEqual({});
  });
});
