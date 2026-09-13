import { create } from "zustand";
import type {
  BenchmarkAuthoringDocument,
  BenchmarkAuthoringRevision,
} from "@/entities/benchmark-authoring";
import {
  cloneAuthoringDocument,
  equalJson,
  normalizeAuthoringInventory,
  replaceTaskFileTasks,
} from "../lib/authoringDocument";
import {
  createTaskBuffers,
  inspectTaskBuffer,
  isTaskBufferUnapplied,
  prettyTaskJson,
  type TaskBufferMap,
} from "../lib/taskBuffers";

export type BenchmarkDefinitionEditorStatus = {
  parsedDirty: boolean;
  rawDirty: boolean;
  hasBufferError: boolean;
  hasUnappliedBuffer: boolean;
  dirty: boolean;
  savePending: boolean;
  saveable: boolean;
};

export type BenchmarkDefinitionEditorState = {
  draftId: string | null;
  baselineRevision: BenchmarkAuthoringRevision | null;
  workingDocument: BenchmarkAuthoringDocument | null;
  taskBuffers: TaskBufferMap;
  selectedMember: string;
  focusedFieldPath: Array<string | number>;
  conflictRevisionId: string | null;
  remoteMayBeNewer: boolean;
  savePending: boolean;
  hydrate: (revision: BenchmarkAuthoringRevision) => void;
  reload: (revision: BenchmarkAuthoringRevision) => void;
  adoptSavedRevision: (revision: BenchmarkAuthoringRevision) => void;
  replaceWorkingDocument: (document: BenchmarkAuthoringDocument) => void;
  selectMember: (key: string) => void;
  focusMember: (key: string, fieldPath: Array<string | number>) => void;
  updateTaskBuffer: (path: string, text: string) => void;
  applyTaskBuffer: (path: string) => boolean;
  reset: () => void;
  setConflict: (revisionId: string | null) => void;
  setSavePending: (pending: boolean) => void;
  clear: () => void;
};

/** Derive parsed/raw dirty and saveability facts from editor-owned state. */
export function benchmarkDefinitionEditorStatus(
  state: BenchmarkDefinitionEditorState,
): BenchmarkDefinitionEditorStatus {
  const parsedDirty =
    state.baselineRevision !== null
    && state.workingDocument !== null
    && !equalJson(
      state.baselineRevision.document,
      state.workingDocument,
    );
  const hasBufferError = Object.values(state.taskBuffers).some(
    (buffer) => buffer.error !== null,
  );
  const hasUnappliedBuffer = Object.values(state.taskBuffers).some(
    isTaskBufferUnapplied,
  );
  const rawDirty =
    state.baselineRevision !== null
    && Object.entries(state.taskBuffers).some(([path, buffer]) => {
      const baseline = state.baselineRevision?.document.taskFiles.find(
        (item) => item.path === path,
      );
      return baseline ? buffer.text !== prettyTaskJson(baseline.tasks) : true;
    });
  const dirty = parsedDirty || rawDirty;
  return {
    parsedDirty,
    rawDirty,
    hasBufferError,
    hasUnappliedBuffer,
    dirty,
    savePending: state.savePending,
    saveable:
      dirty
      && !hasBufferError
      && !hasUnappliedBuffer
      && !state.savePending
      && state.conflictRevisionId === null,
  };
}

/** Convert one immutable revision into a detached clean editor session. */
function revisionSession(revision: BenchmarkAuthoringRevision) {
  const document = cloneAuthoringDocument(revision.document);
  return {
    draftId: revision.draftId,
    baselineRevision: revision,
    workingDocument: document,
    taskBuffers: createTaskBuffers(document),
    selectedMember: "manifest",
    focusedFieldPath: [],
    conflictRevisionId: null,
    remoteMayBeNewer: false,
    savePending: false,
  };
}

/** Own only draft-local editable state; server resources remain in Query. */
export const useBenchmarkDefinitionEditorStore =
  create<BenchmarkDefinitionEditorState>((set, get) => ({
    draftId: null,
    baselineRevision: null,
    workingDocument: null,
    taskBuffers: {},
    selectedMember: "manifest",
    focusedFieldPath: [],
    conflictRevisionId: null,
    remoteMayBeNewer: false,
    savePending: false,

    hydrate: (revision) => {
      const state = get();
      if (state.draftId !== revision.draftId || state.baselineRevision === null) {
        set(revisionSession(revision));
        return;
      }
      if (state.baselineRevision.revisionId !== revision.revisionId) {
        set({ remoteMayBeNewer: true });
      }
    },
    reload: (revision) => set(revisionSession(revision)),
    adoptSavedRevision: (revision) => set(revisionSession(revision)),
    replaceWorkingDocument: (document) =>
      set({
        workingDocument: normalizeAuthoringInventory(document),
        conflictRevisionId: null,
      }),
    selectMember: (selectedMember) => set({ selectedMember, focusedFieldPath: [] }),
    focusMember: (selectedMember, focusedFieldPath) =>
      set({ selectedMember, focusedFieldPath: [...focusedFieldPath] }),
    updateTaskBuffer: (path, text) => {
      const buffer = get().taskBuffers[path];
      if (!buffer) return;
      const inspected = inspectTaskBuffer({ ...buffer, text });
      set((state) => ({
        taskBuffers: {
          ...state.taskBuffers,
          [path]: { ...buffer, text, error: inspected.error },
        },
        conflictRevisionId: null,
      }));
    },
    applyTaskBuffer: (path) => {
      const state = get();
      const buffer = state.taskBuffers[path];
      if (!buffer || !state.workingDocument) return false;
      const inspected = inspectTaskBuffer(buffer);
      if (!inspected.tasks) {
        set((current) => ({
          taskBuffers: {
            ...current.taskBuffers,
            [path]: { ...buffer, error: inspected.error },
          },
        }));
        return false;
      }
      const document = replaceTaskFileTasks(
        state.workingDocument,
        path,
        inspected.tasks,
      );
      const appliedText = prettyTaskJson(inspected.tasks);
      set((current) => ({
        workingDocument: document,
        taskBuffers: {
          ...current.taskBuffers,
          [path]: { text: appliedText, appliedText, error: null },
        },
        conflictRevisionId: null,
      }));
      return true;
    },
    reset: () => {
      const baseline = get().baselineRevision;
      if (baseline) set(revisionSession(baseline));
    },
    setConflict: (conflictRevisionId) =>
      set({ conflictRevisionId, savePending: false }),
    setSavePending: (savePending) => set({ savePending }),
    clear: () =>
      set({
        draftId: null,
        baselineRevision: null,
        workingDocument: null,
        taskBuffers: {},
        selectedMember: "manifest",
        focusedFieldPath: [],
        conflictRevisionId: null,
        remoteMayBeNewer: false,
        savePending: false,
      }),
  }));
