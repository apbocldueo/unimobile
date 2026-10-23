import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkLegacyMigrationPreviewFixture,
  benchmarkLegacyMigrationTargetFixture,
} from "@/entities/benchmark-authoring";
import { prepareBenchmarkLegacyMigrationConfirmIntent } from "./benchmarkLegacyMigration.intent";
import { useBenchmarkLegacyMigrationStore } from "./benchmarkLegacyMigration.store";

describe("Benchmark legacy migration session", () => {
  beforeEach(() => {
    useBenchmarkLegacyMigrationStore.getState().reset();
    vi.stubGlobal("crypto", {
      randomUUID: vi.fn()
        .mockReturnValueOnce("first-uuid")
        .mockReturnValue("next-uuid"),
    });
  });

  it("retains exact retry identity only for unchanged authority", () => {
    const request = {
      schemaVersion: 1 as const,
      sourceName: "legacy.json",
      sourceText: "[]",
      target: benchmarkLegacyMigrationTargetFixture(),
    };
    const preview = benchmarkLegacyMigrationPreviewFixture();
    const first = prepareBenchmarkLegacyMigrationConfirmIntent(null, request, preview);
    expect(prepareBenchmarkLegacyMigrationConfirmIntent(first, request, preview)).toBe(first);
    expect(prepareBenchmarkLegacyMigrationConfirmIntent(first, {
      ...request,
      target: { ...request.target, split: "dev" },
    }, preview).input.clientRequestId).not.toBe(first.input.clientRequestId);
  });

  it("rejects late Preview ownership and invalidates on every edit", () => {
    const state = useBenchmarkLegacyMigrationStore.getState();
    const firstGeneration = state.beginSourceFile(new File(["[]"], "one.json"));
    const secondGeneration = state.beginSourceFile(new File(["[]"], "two.json"));
    expect(state.adoptPreview(firstGeneration, benchmarkLegacyMigrationPreviewFixture())).toBe(false);
    expect(state.adoptPreview(secondGeneration, benchmarkLegacyMigrationPreviewFixture())).toBe(true);
    useBenchmarkLegacyMigrationStore.getState().updateTarget("title", "Changed");
    expect(useBenchmarkLegacyMigrationStore.getState().preview).toBeNull();
  });

  it("disposes file text, Preview, and uncertain intent on reset", () => {
    const state = useBenchmarkLegacyMigrationStore.getState();
    const generation = state.beginSourceFile(new File(["[]"], "legacy.json"));
    state.completeSourceRead(generation, "[]");
    state.adoptPreview(generation, benchmarkLegacyMigrationPreviewFixture());
    state.reset();
    expect(useBenchmarkLegacyMigrationStore.getState()).toMatchObject({
      sourceFile: null,
      sourceText: null,
      preview: null,
      confirmIntent: null,
      generation: 0,
    });
  });
});
