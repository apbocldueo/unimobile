import { create } from "zustand";
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
import {
  applyLlmDependencyToCompatibleCandidates,
  applyLlmDependencyToMissingCandidates,
  alignLegacyOpenAiSecretRefs,
  type LlmDependencyReference,
} from "./llmDependencies";

type BuilderState = {
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
  removeNodes: (canvasIds: string[]) => void;
  addEdge: (edge: StudioCapabilityRelation) => void;
  updateEdge: (edgeId: string, update: (edge: StudioCapabilityRelation) => StudioCapabilityRelation) => void;
  removeEdges: (edgeIds: string[]) => void;
  setNodePosition: (canvasId: string, x: number, y: number) => void;
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

function cloneDocument(document: StudioFlowDocument): StudioFlowDocument {
  return parseStudioFlowDocument(document);
}

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

/** Own the editable schema-3 capability draft without duplicating server state. */
export const useAgentBuilderDocumentStore = create<BuilderState>((set, get) => ({
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

  hydrate: (revision) => {
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

  replaceDocument: (document, revisionId = null) => {
    const parsed = cloneDocument(document);
    set({
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
  importDocument: (document) => get().replaceDocument(document, null),
  updateCurrentDocument: (update) => {
    const document = get().document;
    if (!document) return;
    set({
      document: parseStudioFlowDocument(update(document)),
      dirty: true,
      compileResult: null,
      conflictRevisionId: null,
      bulkUndoDocument: null,
    });
  },
  addNode: (node, presentation) => get().updateCurrentDocument((document) => ({
    ...document,
    capabilities: [...document.capabilities, node],
    presentation: { ...document.presentation, nodes: { ...document.presentation.nodes, [node.canvasId]: presentation } },
  })),
  updateNode: (canvasId, update) => get().updateCurrentDocument((document) => ({
    ...document,
    capabilities: document.capabilities.map((node) => node.canvasId === canvasId ? update(node) : node),
  })),
  removeNodes: (canvasIds) => {
    const removedCanvas = new Set(canvasIds);
    get().updateCurrentDocument((document) => {
      const removedLogical = new Set(
        document.capabilities.filter((item) => removedCanvas.has(item.canvasId)).map((item) => item.logicalId),
      );
      const presentations = { ...document.presentation.nodes };
      for (const canvasId of removedCanvas) delete presentations[canvasId];
      return {
        ...document,
        capabilities: document.capabilities.filter((item) => !removedCanvas.has(item.canvasId)),
        relations: document.relations.filter(
          (item) => !removedLogical.has(item.source.ownerId) && !removedLogical.has(item.target.ownerId),
        ),
        presentation: { ...document.presentation, nodes: presentations },
      };
    });
    set({ selectedCanvasId: null });
  },
  addEdge: (edge) => get().updateCurrentDocument((document) => ({ ...document, relations: [...document.relations, edge] })),
  updateEdge: (edgeId, update) => get().updateCurrentDocument((document) => ({
    ...document,
    relations: document.relations.map((edge) => edge.canvasId === edgeId ? update(edge) : edge),
  })),
  removeEdges: (edgeIds) => {
    const removed = new Set(edgeIds);
    get().updateCurrentDocument((document) => ({ ...document, relations: document.relations.filter((edge) => !removed.has(edge.canvasId)) }));
    set({ selectedEdgeId: null });
  },
  setNodePosition: (canvasId, x, y) => get().updateCurrentDocument((document) => ({
    ...document,
    presentation: {
      ...document.presentation,
      nodes: { ...document.presentation.nodes, [canvasId]: { ...document.presentation.nodes[canvasId], x, y } },
    },
  })),
  setViewport: (x, y, zoom) => get().updateCurrentDocument((document) => ({
    ...document,
    presentation: { ...document.presentation, viewport: { x, y, zoom } },
  })),
  selectNode: (selectedCanvasId) => set({ selectedCanvasId, selectedEdgeId: null }),
  selectEdge: (selectedEdgeId) => set({ selectedCanvasId: null, selectedEdgeId }),
  enterCanvas: () => undefined,
  leaveCanvas: () => set({ canvasPath: [] }),
  setCanvasPath: () => set({ canvasPath: [] }),
  setCompileResult: (compileResult) => set({ compileResult }),
  markSaved: (revision) => get().hydrate(revision),
  setConflict: (conflictRevisionId) => set({ conflictRevisionId }),
  applyLlmDependencyToAll: (catalog, reference) => {
    const document = get().document;
    if (!document) return 0;
    const updated = applyLlmDependencyToCompatibleCandidates(document, catalog, reference);
    if (!updated.changedCandidates) return 0;
    set({ bulkUndoDocument: cloneDocument(document), document: cloneDocument(updated.document), dirty: true, compileResult: null });
    return updated.changedCandidates;
  },
  repairMissingLlmDependencies: (catalog, reference) => {
    const document = get().document;
    if (!document) return 0;
    const updated = applyLlmDependencyToMissingCandidates(document, catalog, reference);
    if (!updated.changedCandidates) return 0;
    set({ bulkUndoDocument: cloneDocument(document), document: cloneDocument(updated.document), dirty: true, compileResult: null });
    return updated.changedCandidates;
  },
  alignLegacyLlmSecretRefs: () => {
    const document = get().document;
    if (!document) return 0;
    const updated = alignLegacyOpenAiSecretRefs(document);
    if (!updated.changedCandidates) return 0;
    set({ bulkUndoDocument: cloneDocument(document), document: cloneDocument(updated.document), dirty: true, compileResult: null });
    return updated.changedCandidates;
  },
  undoLastBulkLlmApply: () => {
    const previous = get().bulkUndoDocument;
    if (previous) set({ document: cloneDocument(previous), bulkUndoDocument: null, dirty: true, compileResult: null });
  },
  resetToBaseline: () => {
    const baseline = get().baseline;
    if (baseline) set({ document: cloneDocument(baseline), dirty: false, selectedCanvasId: null, selectedEdgeId: null, compileResult: null });
  },
  clear: () => set({
    agentId: null, baseRevisionId: null, legacyRevisionId: null, baseline: null, document: null,
    dirty: false, selectedCanvasId: null, selectedEdgeId: null, canvasPath: [], compileResult: null,
    conflictRevisionId: null, bulkUndoDocument: null,
  }),
}));

/** Select the only editable top-level capability document. */
export function selectVisibleDocument(state: BuilderState): StudioFlowDocument | null {
  return state.document;
}
