import { create } from "zustand";
import type {
  BenchmarkLegacyMigrationPreview,
  BenchmarkLegacyMigrationTarget,
} from "@/entities/benchmark-authoring";
import type { BenchmarkLegacyMigrationConfirmIntent } from "./benchmarkLegacyMigration.intent";

export const defaultBenchmarkLegacyMigrationTarget: BenchmarkLegacyMigrationTarget = {
  draftName: "Imported legacy Benchmark",
  publisher: "local",
  packageName: "legacy-benchmark",
  version: "0.1.0",
  title: "Imported legacy Benchmark",
  platform: "android",
  split: "test",
  taskFilePath: "tasks/imported.json",
};

type BenchmarkLegacyMigrationSession = {
  sourceFile: File | null;
  sourceText: string | null;
  target: BenchmarkLegacyMigrationTarget;
  generation: number;
  preview: BenchmarkLegacyMigrationPreview | null;
  previewGeneration: number | null;
  confirmIntent: BenchmarkLegacyMigrationConfirmIntent | null;
  beginSourceFile: (file: File) => number;
  completeSourceRead: (generation: number, sourceText: string) => void;
  updateTarget: <K extends keyof BenchmarkLegacyMigrationTarget>(
    key: K,
    value: BenchmarkLegacyMigrationTarget[K],
  ) => void;
  adoptPreview: (generation: number, preview: BenchmarkLegacyMigrationPreview) => boolean;
  setConfirmIntent: (intent: BenchmarkLegacyMigrationConfirmIntent | null) => void;
  invalidatePreview: () => void;
  reset: () => void;
};

/** Return the fresh disposable migration-session state. */
function initialSession() {
  return {
    sourceFile: null,
    sourceText: null,
    target: { ...defaultBenchmarkLegacyMigrationTarget },
    generation: 0,
    preview: null,
    previewGeneration: null,
    confirmIntent: null,
  };
}

/** Own only disposable file, form, Preview, and retry intent state. */
export const useBenchmarkLegacyMigrationStore =
  create<BenchmarkLegacyMigrationSession>((set, get) => ({
    ...initialSession(),
    beginSourceFile: (file) => {
      const generation = get().generation + 1;
      set({
        sourceFile: file,
        sourceText: null,
        generation,
        preview: null,
        previewGeneration: null,
        confirmIntent: null,
      });
      return generation;
    },
    completeSourceRead: (generation, sourceText) => {
      if (get().generation !== generation) return;
      set({ sourceText });
    },
    updateTarget: (key, value) =>
      set((state) => ({
        target: { ...state.target, [key]: value },
        generation: state.generation + 1,
        preview: null,
        previewGeneration: null,
        confirmIntent: null,
      })),
    adoptPreview: (generation, preview) => {
      if (get().generation !== generation) return false;
      set({ preview, previewGeneration: generation, confirmIntent: null });
      return true;
    },
    setConfirmIntent: (confirmIntent) => set({ confirmIntent }),
    invalidatePreview: () =>
      set((state) => ({
        generation: state.generation + 1,
        preview: null,
        previewGeneration: null,
        confirmIntent: null,
      })),
    reset: () => set(initialSession()),
  }));
