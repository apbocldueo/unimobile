import { describe, expect, it } from "vitest";
import { StudioApiError, StudioHeadContractError } from "@/shared/api";
import {
  benchmarkResourceMutationGate,
  createBenchmarkResourceSession,
  prepareBenchmarkResourceIntent,
  projectBenchmarkResourceAvailability,
  reconcileBenchmarkResourceSession,
} from "@/features/benchmark-resource-editor";
import type { BenchmarkDefinitionEditorStatus } from "@/features/benchmark-definition-editor";

const cleanStatus: BenchmarkDefinitionEditorStatus = {
  parsedDirty: false,
  rawDirty: false,
  hasBufferError: false,
  hasUnappliedBuffer: false,
  dirty: false,
  saveable: false,
  savePending: false,
};

/** Build one exact clean-baseline gate input. */
function cleanGateInput() {
  return {
    definitionStatus: cleanStatus,
    baselineRevisionId: "revision-1",
    queryCurrentRevisionId: "revision-1",
    conflictRevisionId: null,
    remoteMayBeNewer: false,
    contentPending: false,
  };
}

describe("Benchmark resource command intents", () => {
  it("reuses only an exact uncertain command including the selected File", () => {
    let identity = 0;
    const createIdentity = () => `resource-${++identity}`;
    const file = new File(["a"], "a.json", { type: "application/json" });
    const semantic = {
      operation: "upload" as const,
      draftId: "draft-1",
      baseRevisionId: "revision-1",
      resourceId: "ground-truth",
      kind: "ground_truth" as const,
      path: "ground_truth/a.json",
      mediaType: "application/json",
      file,
    };
    const first = prepareBenchmarkResourceIntent(null, semantic, createIdentity);
    const retry = prepareBenchmarkResourceIntent(first, semantic, createIdentity);
    const newFile = prepareBenchmarkResourceIntent(
      retry,
      { ...semantic, file: new File(["a"], "a.json", { type: "application/json" }) },
      createIdentity,
    );
    const changedBase = prepareBenchmarkResourceIntent(
      retry,
      { ...semantic, baseRevisionId: "revision-2" },
      createIdentity,
    );
    const changedOperation = prepareBenchmarkResourceIntent(
      retry,
      {
        operation: "replace",
        draftId: semantic.draftId,
        baseRevisionId: semantic.baseRevisionId,
        resourceId: semantic.resourceId,
        mediaType: semantic.mediaType,
        file,
      },
      createIdentity,
    );
    expect(retry.clientRequestId).toBe(first.clientRequestId);
    expect(newFile.clientRequestId).not.toBe(first.clientRequestId);
    expect(changedBase.clientRequestId).not.toBe(first.clientRequestId);
    expect(changedOperation.clientRequestId).not.toBe(first.clientRequestId);
  });
});

describe("Benchmark resource mutation gate", () => {
  it("allows only an exact clean non-pending baseline", () => {
    expect(benchmarkResourceMutationGate(cleanGateInput()).allowed).toBe(true);
    expect(
      benchmarkResourceMutationGate({
        ...cleanGateInput(),
        definitionStatus: { ...cleanStatus, dirty: true },
      }).code,
    ).toBe("definition-dirty");
    expect(
      benchmarkResourceMutationGate({
        ...cleanGateInput(),
        definitionStatus: { ...cleanStatus, hasBufferError: true },
      }).code,
    ).toBe("definition-invalid");
    expect(
      benchmarkResourceMutationGate({
        ...cleanGateInput(),
        contentPending: true,
      }).code,
    ).toBe("content-pending");
    expect(
      benchmarkResourceMutationGate({
        ...cleanGateInput(),
        queryCurrentRevisionId: "revision-2",
      }).code,
    ).toBe("revision-mismatch");
  });
});

describe("Benchmark selected-resource availability", () => {
  it("projects unchecked, pending, readable, missing, and fail-closed states", () => {
    expect(projectBenchmarkResourceAvailability({ enabled: false, pending: false })).toEqual({ state: "unchecked" });
    expect(projectBenchmarkResourceAvailability({ enabled: true, pending: true })).toEqual({ state: "pending" });
    expect(projectBenchmarkResourceAvailability({
      enabled: true,
      pending: false,
      data: { contentType: "image/png", contentLength: 4, filename: "a.png" },
    }).state).toBe("readable");
    expect(projectBenchmarkResourceAvailability({
      enabled: true,
      pending: false,
      error: new StudioApiError(404, {}),
    }).state).toBe("missing");
    expect(projectBenchmarkResourceAvailability({
      enabled: true,
      pending: false,
      error: new StudioApiError(503, {}),
    }).state).toBe("unavailable");
    expect(projectBenchmarkResourceAvailability({
      enabled: true,
      pending: false,
      error: new StudioHeadContractError("size-mismatch"),
    }).state).toBe("contract-failure");
  });
});

describe("Benchmark resource session cleanup", () => {
  it("keeps valid selection but clears transient state on revision changes", () => {
    const initial = reconcileBenchmarkResourceSession(
      createBenchmarkResourceSession(),
      { draftId: "draft-1", revisionId: "revision-1", resourceIds: ["a", "b"] },
    );
    const file = new File(["x"], "x.bin");
    const dirty = {
      ...initial,
      selectedResourceId: "b",
      uploadFile: file,
      replacementFile: file,
      confirmationResourceId: "b",
      error: "failed",
      message: "uncertain",
    };
    const revised = reconcileBenchmarkResourceSession(dirty, {
      draftId: "draft-1",
      revisionId: "revision-2",
      resourceIds: ["a", "b"],
    });
    expect(revised.selectedResourceId).toBe("b");
    expect(revised.uploadFile).toBeNull();
    expect(revised.replacementFile).toBeNull();
    expect(revised.error).toBeNull();
    const removed = reconcileBenchmarkResourceSession(revised, {
      draftId: "draft-1",
      revisionId: "revision-3",
      resourceIds: ["a"],
    });
    expect(removed.selectedResourceId).toBe("a");
  });
});
