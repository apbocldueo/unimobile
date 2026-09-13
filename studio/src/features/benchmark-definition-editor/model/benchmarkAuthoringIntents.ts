import type {
  BenchmarkAuthoringDocument,
  BenchmarkDraftCreateSource,
  CreateBenchmarkDraftInput,
  SaveBenchmarkRevisionInput,
} from "@/entities/benchmark-authoring";
import { equalJson } from "../lib/authoringDocument";

export type BenchmarkCreateIntent = {
  input: CreateBenchmarkDraftInput;
};

export type BenchmarkSaveIntent = {
  draftId: string;
  input: SaveBenchmarkRevisionInput;
};

/** Generate one browser-safe durable command identity. */
export function createBenchmarkAuthoringIntentId(): string {
  return `benchmark-authoring-${crypto.randomUUID()}`;
}

/** Reuse an unchanged create intent and retire it after semantic edits. */
export function prepareBenchmarkCreateIntent(
  current: BenchmarkCreateIntent | null,
  semantic: { name: string; source: BenchmarkDraftCreateSource },
  createIdentity: () => string = createBenchmarkAuthoringIntentId,
): BenchmarkCreateIntent {
  if (
    current
    && current.input.name === semantic.name
    && equalJson(current.input.source, semantic.source)
  ) {
    return current;
  }
  return {
    input: {
      schemaVersion: 1,
      clientRequestId: createIdentity(),
      name: semantic.name,
      source: semantic.source,
    },
  };
}

/** Reuse an unchanged save intent over one exact draft/base/document tuple. */
export function prepareBenchmarkSaveIntent(
  current: BenchmarkSaveIntent | null,
  semantic: {
    draftId: string;
    baseRevisionId: string;
    document: BenchmarkAuthoringDocument;
  },
  createIdentity: () => string = createBenchmarkAuthoringIntentId,
): BenchmarkSaveIntent {
  if (
    current
    && current.draftId === semantic.draftId
    && current.input.baseRevisionId === semantic.baseRevisionId
    && equalJson(current.input.document, semantic.document)
  ) {
    return current;
  }
  return {
    draftId: semantic.draftId,
    input: {
      schemaVersion: 1,
      clientRequestId: createIdentity(),
      baseRevisionId: semantic.baseRevisionId,
      document: semantic.document,
    },
  };
}
