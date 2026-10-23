import { uiText } from "@/shared/i18n";
import { create } from "zustand";
import { appendHistory, sameSemanticContent, type HistoryEntry } from "./editHistory";
import { fieldCandidate, materializeFields, parseRawObject, rawFieldKey, sameJson, type EditSnapshot, type RawField, type RawFieldOwner } from "./editSession";
import {
  parseStudioFlowDocument,
  type StudioCapabilityNode,
  type StudioCapabilityRelation,
  type StudioCompileResult,
  type StudioFlowDocument,
  type StudioNodePresentation,
} from "@/entities/agent-graph";
import type { AgentRevision } from "@/entities/agent-revision";
import type { ComponentCatalog } from "@/entities/component-catalog";
import type { JsonValue } from "@/shared/lib";
import {
  applyLlmDependencyToCompatibleCandidates,
  applyLlmDependencyToMissingCandidates,
  alignLegacyOpenAiSecretRefs,
  type LlmDependencyReference,
} from "./llmDependencies";

type BuilderState = {
  past: HistoryEntry[];
  future: HistoryEntry[];
  historyGroup: string | null;
  cameraViewport: { x: number; y: number; zoom: number } | null;
  checkpoint: (group?: string) => void;
  finishHistoryGroup: () => void;
  undo: () => void;
  redo: () => void;
  matchesValidationSnapshot: (snapshot: EditSnapshot) => boolean;
  removeElements: (canvasIds: string[], edgeIds: string[]) => void;
  sessionId: number;
  generation: number;
  validationId: number;
  savePending: boolean;
  rawFields: Record<string, RawField>;
  focusField: string | null;
  inputError: string | null;
  departurePath: string | null;
  editRaw: (owner: RawFieldOwner, text: string) => void;
  prepareSnapshot: () => EditSnapshot;
  matchesSnapshot: (snapshot: EditSnapshot) => boolean;
  acknowledgeSave: (snapshot: EditSnapshot, revision: AgentRevision) => void;
  confirmDiscardFields: (canvasIds: string[]) => boolean;
  agentId: string | null;
  baseRevisionId: string | null;
  legacyRevisionId: string | null;
  baseline: StudioFlowDocument | null;
  document: StudioFlowDocument | null;
  dirty: boolean;
  selectedCanvasId: string | null;
  selectedEdgeId: string | null;
  canvasPath: string[];
  compileResult: StudioCompileResult | null;
  conflictRevisionId: string | null;
  bulkUndoDocument: StudioFlowDocument | null;
  hydrate: (revision: AgentRevision) => void;
  replaceDocument: (document: StudioFlowDocument, revisionId?: string | null) => void;
  importDocument: (document: StudioFlowDocument) => void;
  updateCurrentDocument: (update: (document: StudioFlowDocument) => StudioFlowDocument) => void;
  addNode: (node: StudioCapabilityNode, presentation: StudioNodePresentation) => void;
  updateNode: (canvasId: string, update: (node: StudioCapabilityNode) => StudioCapabilityNode) => void;
  updateCandidateProperty: (canvasId: string, candidateIndex: number, property: "params" | "dependencies", value: Record<string, JsonValue>) => void;
  removeNodes: (canvasIds: string[]) => void;
  addEdge: (edge: StudioCapabilityRelation) => void;
  updateEdge: (edgeId: string, update: (edge: StudioCapabilityRelation) => StudioCapabilityRelation) => void;
  removeEdges: (edgeIds: string[]) => void;
  setNodePosition: (canvasId: string, x: number, y: number) => void;
  setNodePositions: (positions: Record<string, { x: number; y: number }>) => void;
  setViewport: (x: number, y: number, zoom: number) => void;
  selectNode: (canvasId: string | null) => void;
  selectEdge: (edgeId: string | null) => void;
  enterCanvas: (canvasId: string) => void;
  leaveCanvas: (depth?: number) => void;
  setCanvasPath: (path: string[]) => void;
  setCompileResult: (result: StudioCompileResult | null) => void;
  markSaved: (revision: AgentRevision) => void;
  setConflict: (revisionId: string | null) => void;
  applyLlmDependencyToAll: (catalog: ComponentCatalog, reference: LlmDependencyReference) => number;
  repairMissingLlmDependencies: (catalog: ComponentCatalog, reference: LlmDependencyReference) => number;
  alignLegacyLlmSecretRefs: () => number;
  undoLastBulkLlmApply: () => void;
  resetToBaseline: () => void;
  clear: () => void;
};

/** Clone through the strict schema before accepting external document ownership. */
function cloneDocument(document: StudioFlowDocument): StudioFlowDocument {
  return parseStudioFlowDocument(document);
}

/** Compute unsaved work from parsed content and all outstanding raw input. */
function isDirty(document: StudioFlowDocument | null, baseline: StudioFlowDocument | null, fields: Record<string, RawField>): boolean {
  if (!document) return false;
  try { return !sameJson(materializeFields(document, fields), baseline); } catch { return true; }
}

/** Project a verified revision snapshot into the existing Builder validation view. */
function compileFromRevision(revision: AgentRevision, document: StudioFlowDocument): StudioCompileResult {
  return {
    schemaVersion: 1,
    isSuccess: revision.compileSnapshot.status === "valid",
    contractVersion: "1.1",
    catalogVersion: "",
    canonicalHash: revision.compileSnapshot.canonicalHash ?? null,
    authoringPolicy: revision.compileSnapshot.authoringPolicy ?? null,
    loweringProfile: revision.compileSnapshot.loweringProfile ?? null,
    capabilityHash: revision.compileSnapshot.capabilityHash ?? null,
    agentGraph: revision.compileSnapshot.agentGraph ?? null,
    diagnostics: revision.compileSnapshot.diagnostics,
    sourceMap: revision.compileSnapshot.sourceMap,
    projectionMap: revision.compileSnapshot.projectionMap ?? [],
    summary: {
      errorCount: revision.compileSnapshot.diagnostics.filter((item) => item.severity === "error").length,
      warningCount: revision.compileSnapshot.diagnostics.filter((item) => item.severity === "warning").length,
      nodeCount: document.capabilities.length + 2,
      edgeCount: document.relations.length,
    },
  };
}

/** Capture only immutable editor content, never server revision/CAS authority.
 * Args: state is an editor session with a loaded document.
 * Returns: A local checkpoint sharing immutable document/buffer references.
 */
function historyEntry(state: BuilderState): HistoryEntry {
  return { document: state.document!, rawFields: state.rawFields,
    selectedCanvasId: state.selectedCanvasId, selectedEdgeId: state.selectedEdgeId };
}

/** Preserve validation only when both raw-buffer projections retain identical meaning.
 * Args: state and target are the current and restored content checkpoints.
 * Returns: False for changed semantics or any invalid raw input.
 */
function sameEditableMeaning(state: HistoryEntry, target: HistoryEntry): boolean {
  try { return sameSemanticContent(materializeFields(state.document, state.rawFields), materializeFields(target.document, target.rawFields)); }
  catch { return false; }
}

/** Restore editor facts while leaving save baselines, conflicts and session identity intact.
 * Args: state is the current session; target is one local history checkpoint.
 * Returns: The content patch, with newer response ownership and safe validation state.
 */
function restoreHistory(state: BuilderState, target: HistoryEntry): Partial<BuilderState> {
  const inputError = Object.values(target.rawFields).find((field) => field.error)?.error ?? null;
  return { ...target, generation: state.generation + 1, historyGroup: null,
    inputError, focusField: null, departurePath: null, bulkUndoDocument: null,
    dirty: isDirty(target.document, state.baseline, target.rawFields),
    compileResult: sameEditableMeaning(historyEntry(state), target) ? state.compileResult : null };
}

/** Own the editable schema-3 capability draft without duplicating server state. */
export const useAgentBuilderDocumentStore = create<BuilderState>((set, get) => ({
  past: [], future: [], historyGroup: null, cameraViewport: null,
  /** Record one operation; repeated typing in the same focused field is one step. */
  checkpoint: (group) => {
    const state = get();
    if (!state.document) return;
    const coalesced = group !== undefined && state.historyGroup === group;
    set({ past: coalesced ? state.past : appendHistory(state.past, historyEntry(state)), future: [], historyGroup: group ?? null });
  },
  /** End text/discard grouping at an explicit editing command or focus boundary. */
  finishHistoryGroup: () => set({ historyGroup: null }),
  /** Undo one local edit without rolling back the acknowledged server revision. */
  undo: () => {
    const state = get();
    const target = state.past.at(-1);
    if (!target || !state.document) return;
    set({ ...restoreHistory(state, target), past: state.past.slice(0, -1), future: appendHistory(state.future, historyEntry(state)) });
  },
  /** Redo one local edit; a new command invalidates the abandoned redo branch. */
  redo: () => {
    const state = get();
    const target = state.future.at(-1);
    if (!target || !state.document) return;
    set({ ...restoreHistory(state, target), past: appendHistory(state.past, historyEntry(state)), future: state.future.slice(0, -1) });
  },
  /** Accept semantic validation across presentation edits, never another session/raw error. */
  matchesValidationSnapshot: (snapshot) => {
    const state = get();
    if (state.sessionId !== snapshot.sessionId || !state.document) return false;
    try { return sameSemanticContent(materializeFields(state.document, state.rawFields), snapshot.document); }
    catch { return false; }
  },
  sessionId: 0, generation: 0, validationId: 0, savePending: false,
  rawFields: {}, focusField: null, inputError: null, departurePath: null,
  /** Retain exact input and invalidate current feedback on every edit. */
  editRaw: (owner, text) => {
    const state = get();
    if (!state.document) return;
    if (state.rawFields[rawFieldKey(owner)]?.text === text) return;
    get().checkpoint(rawFieldKey(owner));
    let error: string | null = null;
    try {
      fieldCandidate(state.document, owner);
      parseRawObject(text);
      // Reuse formal schema checks (including host-path safety) for field-level focus.
      materializeFields(state.document, { [rawFieldKey(owner)]: { ...owner, text, error: null } });
    }
    catch (cause) { error = cause instanceof Error ? cause.message : uiText("配置无效。"); }
    const rawFields = { ...state.rawFields, [rawFieldKey(owner)]: { ...owner, text, error } };
    set({ rawFields, generation: state.generation + 1, dirty: isDirty(state.document, state.baseline, rawFields), compileResult: null, inputError: Object.values(rawFields).find((field) => field.error)?.error ?? null, focusField: null, departurePath: null });
  },
  /** Atomically prepare current content. Raises safe errors and focuses invalid input. */
  prepareSnapshot: () => {
    const state = get();
    if (!state.document) throw new Error(uiText("Agent document 尚未加载"));
    get().finishHistoryGroup();
    try {
      const document = materializeFields(state.document, state.rawFields);
      set({ document, rawFields: {}, focusField: null, inputError: null, dirty: !sameJson(document, state.baseline) });
      return { document, sessionId: state.sessionId, generation: state.generation, baseRevisionId: state.baseRevisionId };
    } catch (cause) {
      const entry = Object.entries(state.rawFields).find(([, field]) => field.error);
      const message = cause instanceof Error ? cause.message : uiText("配置无效。");
      set({ inputError: message, compileResult: null, focusField: entry?.[0] ?? null, ...(entry ? { selectedCanvasId: entry[1].canvasId, selectedEdgeId: null } : {}) });
      throw new Error(message);
    }
  },
  /** Match the originating session and edit generation, including unparsed text. */
  matchesSnapshot: (snapshot) => get().sessionId === snapshot.sessionId && get().generation === snapshot.generation && get().agentId === snapshot.document.agentId,
  /** Advance only the acknowledged baseline; preserve edits made during saving. */
  acknowledgeSave: (snapshot, revision) => {
    const state = get();
    if (state.sessionId !== snapshot.sessionId || state.agentId !== revision.agentId || revision.document.schemaVersion !== 3) return;
    const unchanged = state.matchesSnapshot(snapshot);
    const baseline = cloneDocument(revision.document);
    const document = unchanged ? cloneDocument(baseline) : state.document;
    const rawFields = unchanged ? {} : state.rawFields;
    let compileResult: StudioCompileResult | null = null;
    try {
      if (document && sameSemanticContent(materializeFields(document, rawFields), baseline)) compileResult = compileFromRevision(revision, baseline);
    } catch { /* Invalid current raw input must not inherit saved validation. */ }
    set({ baseline, document, rawFields, baseRevisionId: revision.revisionId, dirty: isDirty(document, baseline, rawFields), conflictRevisionId: null,
      compileResult });
  },
  /** Confirm only outstanding fields owned by nodes about to be replaced or removed. */
  confirmDiscardFields: (canvasIds) => {
    const state = get();
    const affected = Object.entries(state.rawFields).filter(([, field]) => canvasIds.includes(field.canvasId));
    if (!affected.length) return true;
    if (!window.confirm(uiText("此操作会丢弃该组件尚未应用的配置输入，是否继续？"))) return false;
    get().checkpoint("discard");
    const rawFields = { ...state.rawFields };
    for (const [key] of affected) delete rawFields[key];
    set({ rawFields, dirty: isDirty(state.document, state.baseline, rawFields), inputError: Object.values(rawFields).find((field) => field.error)?.error ?? null, focusField: null, generation: state.generation + 1, departurePath: null, compileResult: null });
    return true;
  },
  agentId: null,
  baseRevisionId: null,
  legacyRevisionId: null,
  baseline: null,
  document: null,
  dirty: false,
  selectedCanvasId: null,
  selectedEdgeId: null,
  canvasPath: [],
  compileResult: null,
  conflictRevisionId: null,
  bulkUndoDocument: null,

  /** Start a new session from an acknowledged revision; legacy documents remain read-only. */
  hydrate: (revision) => {
    set({ past: [], future: [], historyGroup: null, cameraViewport: null, sessionId: get().sessionId + 1, generation: 0, rawFields: {}, inputError: null, focusField: null, savePending: false, departurePath: null });
    if (revision.document.schemaVersion !== 3) {
      set({
        agentId: revision.agentId,
        baseRevisionId: revision.revisionId,
        legacyRevisionId: revision.revisionId,
        baseline: null,
        document: null,
        dirty: false,
        selectedCanvasId: null,
        selectedEdgeId: null,
        canvasPath: [],
        compileResult: null,
        conflictRevisionId: null,
        bulkUndoDocument: null,
      });
      return;
    }
    const document = cloneDocument(revision.document);
    set({
      agentId: revision.agentId,
      baseRevisionId: revision.revisionId,
      legacyRevisionId: null,
      baseline: document,
      document: cloneDocument(document),
      dirty: false,
      selectedCanvasId: null,
      selectedEdgeId: null,
      canvasPath: [],
      compileResult: compileFromRevision(revision, document),
      conflictRevisionId: null,
      bulkUndoDocument: null,
    });
  },

  /** Replace an explicitly authorized session. Raises on invalid schema before mutation. */
  replaceDocument: (document, revisionId = null) => {
    const parsed = cloneDocument(document);
    set({
      past: [], future: [], historyGroup: null, cameraViewport: null, sessionId: get().sessionId + 1, generation: 0, rawFields: {}, inputError: null, focusField: null, savePending: false, departurePath: null,
      agentId: parsed.agentId,
      baseRevisionId: revisionId,
      legacyRevisionId: null,
      baseline: revisionId ? cloneDocument(parsed) : null,
      document: parsed,
      dirty: revisionId === null,
      selectedCanvasId: null,
      selectedEdgeId: null,
      canvasPath: [],
      compileResult: null,
      conflictRevisionId: null,
      bulkUndoDocument: null,
    });
  },
  /** Replace a draft without discarding its optimistic save authority. */
  importDocument: (document) => {
    const { baseline, baseRevisionId } = get();
    get().replaceDocument(document, baseRevisionId);
    set({ baseline, dirty: isDirty(get().document, baseline, {}) });
  },
  /** Apply a parsed edit, invalidating response ownership only when content changed. */
  updateCurrentDocument: (update) => {
    const document = get().document;
    if (!document) return;
    const updated = parseStudioFlowDocument(update(document));
    if (sameJson(updated, document)) { get().finishHistoryGroup(); return; }
    const before = get();
    // A confirmed raw-field removal and its following mutation are one operation.
    if (before.historyGroup !== "discard") get().checkpoint();
    set({
      historyGroup: null,
      document: updated,
      generation: get().generation + 1,
      departurePath: null,
      dirty: isDirty(updated, get().baseline, get().rawFields),
      compileResult: sameSemanticContent(document, updated) ? before.compileResult : null,
      bulkUndoDocument: null,
    });
  },
  /** Atomically add and select one node without changing existing node positions.
   * Args: node is Catalog-created; presentation contains its chosen location.
   * Returns: Nothing when no document is loaded; otherwise one authoring edit.
   */
  addNode: (node, presentation) => {
    const state = get();
    if (!state.document) return;
    const document = { ...state.document,
      capabilities: [...state.document.capabilities, node],
      presentation: { ...state.document.presentation, nodes: { ...state.document.presentation.nodes, [node.canvasId]: presentation } },
    };
    get().checkpoint();
    set({ document, selectedCanvasId: node.canvasId, selectedEdgeId: null,
      generation: state.generation + 1, departurePath: null,
      dirty: isDirty(document, state.baseline, state.rawFields), compileResult: null, bulkUndoDocument: null });
  },
  updateNode: (canvasId, update) => get().updateCurrentDocument((document) => ({
    ...document,
    capabilities: document.capabilities.map((node) => node.canvasId === canvasId ? update(node) : node),
  })),
  /** Apply a typed candidate object and retire only its stale raw editor buffer.
   * Args: canvasId identifies the capability; candidateIndex selects its implementation;
   * property is params or dependencies; value is the parsed JSON object from a form.
   * Returns: Nothing when the candidate is absent; otherwise one undoable authoring edit.
   */
  updateCandidateProperty: (canvasId, candidateIndex, property, value) => {
    const state = get();
    const document = state.document;
    const node = document?.capabilities.find((item) => item.canvasId === canvasId);
    const candidate = node?.implementation.candidates[candidateIndex];
    if (!document || !node || !candidate) return;
    const owner: RawFieldOwner = {
      canvasId,
      candidate: candidateIndex,
      implementation: JSON.stringify([candidate.namespace, candidate.name, candidate.version]),
      property,
    };
    const key = rawFieldKey(owner);
    const hadRaw = state.rawFields[key] !== undefined;
    const rawFields = { ...state.rawFields };
    delete rawFields[key];
    const updated = parseStudioFlowDocument({
      ...document,
      capabilities: document.capabilities.map((item) => item.canvasId !== canvasId ? item : {
        ...item,
        implementation: {
          ...item.implementation,
          candidates: item.implementation.candidates.map((itemCandidate, index) => index !== candidateIndex ? itemCandidate : {
            ...itemCandidate,
            [property]: value,
          }),
        },
      }),
    });
    if (sameJson(updated, document) && !hadRaw) return;
    if (state.historyGroup !== "discard") get().checkpoint();
    let preserveValidation = false;
    try { preserveValidation = sameSemanticContent(materializeFields(document, state.rawFields), updated); } catch { /* Invalid raw text must clear validation. */ }
    set({
      historyGroup: null,
      document: updated,
      rawFields,
      generation: state.generation + 1,
      departurePath: null,
      dirty: isDirty(updated, state.baseline, rawFields),
      inputError: Object.values(rawFields).find((entry) => entry.error)?.error ?? null,
      compileResult: preserveValidation ? state.compileResult : null,
      bulkUndoDocument: null,
    });
  },
  /** Remove nodes and all selected/incident relations as one recoverable command. */
  removeElements: (canvasIds, edgeIds) => {
    const current = get().document;
    if (!current) return;
    const eligible = canvasIds.filter((id) => current.capabilities.some((node) => node.canvasId === id));
    if (!get().confirmDiscardFields(eligible)) return;
    const removedCanvas = new Set(eligible);
    const removedEdges = new Set(edgeIds);
    get().updateCurrentDocument((document) => {
      const removedLogical = new Set(document.capabilities.filter((item) => removedCanvas.has(item.canvasId)).map((item) => item.logicalId));
      const presentations = { ...document.presentation.nodes };
      for (const canvasId of removedCanvas) delete presentations[canvasId];
      return { ...document,
        capabilities: document.capabilities.filter((item) => !removedCanvas.has(item.canvasId)),
        relations: document.relations.filter((edge) => !removedEdges.has(edge.canvasId) && !removedLogical.has(edge.source.ownerId) && !removedLogical.has(edge.target.ownerId)),
        presentation: { ...document.presentation, nodes: presentations } };
    });
    set({ selectedCanvasId: null, selectedEdgeId: null });
  },
  /** Delete capabilities through the atomic element command, preserving boundaries. */
  removeNodes: (canvasIds) => get().removeElements(canvasIds, []),
  addEdge: (edge) => get().updateCurrentDocument((document) => ({ ...document, relations: [...document.relations, edge] })),
  updateEdge: (edgeId, update) => get().updateCurrentDocument((document) => ({
    ...document,
    relations: document.relations.map((edge) => edge.canvasId === edgeId ? update(edge) : edge),
  })),
  /** Delete selected relations as one history step. */
  removeEdges: (edgeIds) => get().removeElements([], edgeIds),
  /** Save one completed node movement as an undoable presentation-only edit. */
  setNodePosition: (canvasId, x, y) => get().updateCurrentDocument((document) => ({
    ...document,
    presentation: {
      ...document.presentation,
      nodes: { ...document.presentation.nodes, [canvasId]: { ...document.presentation.nodes[canvasId], x, y } },
    },
  })),
  /** Save a complete deterministic canvas layout as one undoable presentation-only edit.
   * Args: positions maps existing canvas IDs to finite x/y coordinates.
   * Returns: Nothing; invalid or unknown positions are ignored without changing the document.
   */
  setNodePositions: (positions) => get().updateCurrentDocument((document) => {
    const known = new Set([document.input.canvasId, document.output.canvasId, ...document.capabilities.map((node) => node.canvasId)]);
    const nodes = { ...document.presentation.nodes };
    let changed = false;
    for (const [canvasId, position] of Object.entries(positions)) {
      if (!known.has(canvasId) || !Number.isFinite(position.x) || !Number.isFinite(position.y)) continue;
      const previous = nodes[canvasId];
      if (previous?.x === position.x && previous?.y === position.y) continue;
      nodes[canvasId] = { ...previous, x: position.x, y: position.y };
      changed = true;
    }
    return changed ? { ...document, presentation: { ...document.presentation, nodes } } : document;
  }),
  /** Remember only the session camera; never dirty or invalidate the Agent document. */
  setViewport: (x, y, zoom) => {
    if ([x, y, zoom].every(Number.isFinite) && zoom > 0) set({ cameraViewport: { x, y, zoom } });
  },
  selectNode: (selectedCanvasId) => set({ selectedCanvasId, selectedEdgeId: null }),
  selectEdge: (selectedEdgeId) => set({ selectedCanvasId: null, selectedEdgeId }),
  enterCanvas: () => undefined,
  leaveCanvas: () => set({ canvasPath: [] }),
  setCanvasPath: () => set({ canvasPath: [] }),
  setCompileResult: (compileResult) => set({ compileResult }),
  markSaved: (revision) => get().hydrate(revision),
  setConflict: (conflictRevisionId) => set({ conflictRevisionId }),
  /** Apply compatible LLM bindings after a raw-input decision; return changed candidate count. */
  applyLlmDependencyToAll: (catalog, reference) => {
    const document = get().document;
    if (!document) return 0;
    const updated = applyLlmDependencyToCompatibleCandidates(document, catalog, reference);
    if (!updated.changedCandidates) return 0;
    if (!get().confirmDiscardFields(document.capabilities.map((node) => node.canvasId))) return 0;
    get().updateCurrentDocument(() => updated.document);
    set({ bulkUndoDocument: cloneDocument(document) });
    return updated.changedCandidates;
  },
  /** Fill missing compatible bindings without bypassing edit-generation ownership. */
  repairMissingLlmDependencies: (catalog, reference) => {
    const document = get().document;
    if (!document) return 0;
    const updated = applyLlmDependencyToMissingCandidates(document, catalog, reference);
    if (!updated.changedCandidates) return 0;
    if (!get().confirmDiscardFields(document.capabilities.map((node) => node.canvasId))) return 0;
    get().updateCurrentDocument(() => updated.document);
    set({ bulkUndoDocument: cloneDocument(document) });
    return updated.changedCandidates;
  },
  /** Align legacy reference identities after confirming outstanding raw edits. */
  alignLegacyLlmSecretRefs: () => {
    const document = get().document;
    if (!document) return 0;
    const updated = alignLegacyOpenAiSecretRefs(document);
    if (!updated.changedCandidates) return 0;
    if (!get().confirmDiscardFields(document.capabilities.map((node) => node.canvasId))) return 0;
    get().updateCurrentDocument(() => updated.document);
    set({ bulkUndoDocument: cloneDocument(document) });
    return updated.changedCandidates;
  },
  /** Restore the last bulk-edit document only after confirming any new raw work. */
  undoLastBulkLlmApply: () => {
    const previous = get().bulkUndoDocument;
    if (previous && get().confirmDiscardFields(previous.capabilities.map((node) => node.canvasId))) {
      get().updateCurrentDocument(() => cloneDocument(previous));
      set({ bulkUndoDocument: null });
    }
  },
  /** Start a fresh in-memory session at the saved baseline after UI confirmation. */
  resetToBaseline: () => {
    const baseline = get().baseline;
    if (baseline) set({ past: [], future: [], historyGroup: null, cameraViewport: null, sessionId: get().sessionId + 1, generation: 0, rawFields: {}, inputError: null, focusField: null, savePending: false, departurePath: null, bulkUndoDocument: null, document: cloneDocument(baseline), dirty: false, selectedCanvasId: null, selectedEdgeId: null, compileResult: null });
  },
  /** Release local work after authorized departure and invalidate all old responses. */
  clear: () => set({
    past: [], future: [], historyGroup: null, cameraViewport: null, sessionId: get().sessionId + 1, generation: 0, rawFields: {}, inputError: null, focusField: null, savePending: false, departurePath: null,
    agentId: null, baseRevisionId: null, legacyRevisionId: null, baseline: null, document: null,
    dirty: false, selectedCanvasId: null, selectedEdgeId: null, canvasPath: [], compileResult: null,
    conflictRevisionId: null, bulkUndoDocument: null,
  }),
}));

/** Select the only editable top-level capability document. */
export function selectVisibleDocument(state: BuilderState): StudioFlowDocument | null {
  return state.document;
}
