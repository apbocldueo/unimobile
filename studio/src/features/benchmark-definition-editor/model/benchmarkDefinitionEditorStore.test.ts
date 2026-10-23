import { beforeEach, describe, expect, it } from "vitest";
import {
  benchmarkAuthoringRevisionFixture,
  benchmarkNextRevisionFixtureId,
} from "@/entities/benchmark-authoring";
import {
  benchmarkDefinitionEditorStatus,
  patchManifest,
  useBenchmarkDefinitionEditorStore,
} from "@/features/benchmark-definition-editor";

beforeEach(() => {
  useBenchmarkDefinitionEditorStore.getState().clear();
});

describe("Benchmark definition editor store", () => {
  it("hydrates a draft-scoped clean baseline and derives parsed dirty state", () => {
    const revision = benchmarkAuthoringRevisionFixture();
    const store = useBenchmarkDefinitionEditorStore.getState();
    store.hydrate(revision);
    expect(
      benchmarkDefinitionEditorStatus(
        useBenchmarkDefinitionEditorStore.getState(),
      ).dirty,
    ).toBe(false);
    const working =
      useBenchmarkDefinitionEditorStore.getState().workingDocument!;
    store.replaceWorkingDocument(patchManifest(working, ["title"], "Edited"));
    const status = benchmarkDefinitionEditorStatus(
      useBenchmarkDefinitionEditorStore.getState(),
    );
    expect(status.parsedDirty).toBe(true);
    expect(status.saveable).toBe(true);
  });

  it("retains invalid/unapplied local buffers and blocks save until Apply JSON", () => {
    const store = useBenchmarkDefinitionEditorStore.getState();
    store.hydrate(benchmarkAuthoringRevisionFixture());
    store.updateTaskBuffer("tasks/test.json", "[");
    let status = benchmarkDefinitionEditorStatus(
      useBenchmarkDefinitionEditorStore.getState(),
    );
    expect(status.hasBufferError).toBe(true);
    expect(status.saveable).toBe(false);
    store.updateTaskBuffer("tasks/test.json", "[]");
    status = benchmarkDefinitionEditorStatus(
      useBenchmarkDefinitionEditorStore.getState(),
    );
    expect(status.hasUnappliedBuffer).toBe(true);
    expect(store.applyTaskBuffer("tasks/test.json")).toBe(true);
    status = benchmarkDefinitionEditorStatus(
      useBenchmarkDefinitionEditorStore.getState(),
    );
    expect(status.saveable).toBe(true);
  });

  it("never lets a background newer revision overwrite local work", () => {
    const first = benchmarkAuthoringRevisionFixture();
    const newer = {
      ...benchmarkAuthoringRevisionFixture("edit"),
      revisionId: benchmarkNextRevisionFixtureId,
      ordinal: 2,
      parentRevisionId: first.revisionId,
    };
    const store = useBenchmarkDefinitionEditorStore.getState();
    store.hydrate(first);
    const working = useBenchmarkDefinitionEditorStore.getState().workingDocument!;
    store.replaceWorkingDocument(patchManifest(working, ["title"], "Local"));
    store.hydrate(newer);
    const state = useBenchmarkDefinitionEditorStore.getState();
    expect(state.workingDocument?.manifest.document.title).toBe("Local");
    expect(state.remoteMayBeNewer).toBe(true);
    expect(state.baselineRevision?.revisionId).toBe(first.revisionId);
  });

  it("resets locally, reloads explicitly, and preserves edits on conflict", () => {
    const first = benchmarkAuthoringRevisionFixture();
    const store = useBenchmarkDefinitionEditorStore.getState();
    store.hydrate(first);
    const working = useBenchmarkDefinitionEditorStore.getState().workingDocument!;
    store.replaceWorkingDocument(patchManifest(working, ["title"], "Local"));
    store.setConflict(benchmarkNextRevisionFixtureId);
    expect(
      useBenchmarkDefinitionEditorStore.getState().workingDocument?.manifest
        .document.title,
    ).toBe("Local");
    store.reset();
    expect(
      useBenchmarkDefinitionEditorStore.getState().workingDocument?.manifest
        .document.title,
    ).toBe("Authoring Fixture");
  });
});
