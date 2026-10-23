import { describe, expect, it } from "vitest";
import { benchmarkContractTestGate } from "./benchmarkContractTestGate";

const clean = {
  definitionStatus: {
    dirty: false,
    hasBufferError: false,
    hasUnappliedBuffer: false,
    savePending: false,
  },
  baselineRevisionId: "revision-1",
  queryCurrentRevisionId: "revision-1",
  conflictRevisionId: null,
  remoteMayBeNewer: false,
  contentPending: false,
  peerAnalysisPending: false,
  contractTestPending: false,
};

describe("Benchmark Contract Test gate", () => {
  it("allows only a clean authoritative saved baseline", () => {
    expect(benchmarkContractTestGate(clean).allowed).toBe(true);
    expect(benchmarkContractTestGate({ ...clean, definitionStatus: { ...clean.definitionStatus, dirty: true } }).code).toBe("definition-dirty");
    expect(benchmarkContractTestGate({ ...clean, definitionStatus: { ...clean.definitionStatus, hasBufferError: true } }).code).toBe("definition-invalid");
    expect(benchmarkContractTestGate({ ...clean, definitionStatus: { ...clean.definitionStatus, hasUnappliedBuffer: true } }).code).toBe("definition-unapplied");
    expect(benchmarkContractTestGate({ ...clean, conflictRevisionId: "later" }).code).toBe("conflict");
    expect(benchmarkContractTestGate({ ...clean, remoteMayBeNewer: true }).code).toBe("remote-newer");
    expect(benchmarkContractTestGate({ ...clean, contentPending: true }).code).toBe("content-pending");
    expect(benchmarkContractTestGate({ ...clean, contractTestPending: true }).code).toBe("contract-pending");
    expect(benchmarkContractTestGate({ ...clean, definitionStatus: { ...clean.definitionStatus, savePending: true } }).code).toBe("save-pending");
    expect(benchmarkContractTestGate({ ...clean, peerAnalysisPending: true }).code).toBe("analysis-pending");
    expect(benchmarkContractTestGate({ ...clean, queryCurrentRevisionId: "revision-2" }).code).toBe("revision-mismatch");
  });
});
