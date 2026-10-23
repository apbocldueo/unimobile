import { describe, expect, it } from "vitest";
import {
  benchmarkAuthoringDocumentFixture,
  benchmarkDraftFixtureId,
  benchmarkRevisionFixtureId,
} from "@/entities/benchmark-authoring";
import {
  prepareBenchmarkCreateIntent,
  prepareBenchmarkSaveIntent,
} from "@/features/benchmark-definition-editor";

describe("Benchmark authoring command intents", () => {
  it("reuses unchanged create intent and retires it after semantic edits", () => {
    let identity = 0;
    const createIdentity = () => `intent-${++identity}`;
    const semantic = {
      name: "Fixture",
      source: {
        kind: "template" as const,
        template: "minimal" as const,
        publisher: "fixture",
        packageName: "authoring",
        version: "0.1.0",
      },
    };
    const first = prepareBenchmarkCreateIntent(null, semantic, createIdentity);
    const retry = prepareBenchmarkCreateIntent(first, semantic, createIdentity);
    const changed = prepareBenchmarkCreateIntent(
      retry,
      { ...semantic, name: "Changed" },
      createIdentity,
    );
    expect(retry.input.clientRequestId).toBe(first.input.clientRequestId);
    expect(changed.input.clientRequestId).not.toBe(first.input.clientRequestId);
  });

  it("reuses exact save intent and changes identity for document/base changes", () => {
    let identity = 0;
    const createIdentity = () => `save-${++identity}`;
    const semantic = {
      draftId: benchmarkDraftFixtureId,
      baseRevisionId: benchmarkRevisionFixtureId,
      document: benchmarkAuthoringDocumentFixture(),
    };
    const first = prepareBenchmarkSaveIntent(null, semantic, createIdentity);
    const retry = prepareBenchmarkSaveIntent(first, semantic, createIdentity);
    const changedDocument = benchmarkAuthoringDocumentFixture();
    changedDocument.manifest.document.title = "Changed";
    const changed = prepareBenchmarkSaveIntent(
      retry,
      { ...semantic, document: changedDocument },
      createIdentity,
    );
    expect(retry.input.clientRequestId).toBe(first.input.clientRequestId);
    expect(changed.input.clientRequestId).not.toBe(first.input.clientRequestId);
  });
});
