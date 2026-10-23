import { describe, expect, it } from "vitest";
import { benchmarkAnalysisGate, type BenchmarkAnalysisGateInput } from "@/features/benchmark-validation-dry-run";

const base: BenchmarkAnalysisGateInput = {
  definitionStatus: {
    dirty: false,
    hasBufferError: false,
    hasUnappliedBuffer: false,
    savePending: false,
  },
  baselineRevisionId: "revision-current",
  queryCurrentRevisionId: "revision-current",
  conflictRevisionId: null,
  remoteMayBeNewer: false,
  contentPending: false,
  analysisPending: false,
};

describe("benchmark analysis gate", () => {
  it("allows only one exact clean saved baseline", () => {
    expect(benchmarkAnalysisGate(base)).toMatchObject({
      allowed: true,
      code: "allowed",
    });
  });

  it.each([
    [{ baselineRevisionId: null }, "not-ready"],
    [{ definitionStatus: { ...base.definitionStatus, savePending: true } }, "definition-save-pending"],
    [{ contentPending: true }, "content-pending"],
    [{ analysisPending: true }, "analysis-pending"],
    [{ conflictRevisionId: "revision-remote" }, "conflict"],
    [{ remoteMayBeNewer: true }, "remote-newer"],
    [{ definitionStatus: { ...base.definitionStatus, hasBufferError: true } }, "definition-invalid"],
    [{ definitionStatus: { ...base.definitionStatus, hasUnappliedBuffer: true } }, "definition-unapplied"],
    [{ definitionStatus: { ...base.definitionStatus, dirty: true } }, "definition-dirty"],
    [{ queryCurrentRevisionId: "revision-remote" }, "revision-mismatch"],
  ] as const)("blocks %s as %s", (patch, code) => {
    expect(benchmarkAnalysisGate({ ...base, ...patch })).toMatchObject({
      allowed: false,
      code,
    });
  });
});
