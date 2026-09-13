import { describe, expect, it } from "vitest";
import {
  benchmarkContractProfilePageFixture,
  benchmarkContractTestResultFixture,
} from "@/entities/benchmark-authoring";
import {
  acceptBenchmarkContractTestResult,
  benchmarkContractTestRequestOwner,
  createBenchmarkContractTestSession,
  setBenchmarkContractTestInputs,
} from "./benchmarkContractTestSession";

describe("Benchmark Contract Test request ownership", () => {
  it("accepts only the active exact input/profile generation", () => {
    const result = benchmarkContractTestResultFixture();
    let session = createBenchmarkContractTestSession({
      draftId: result.draftId,
      revisionId: result.revisionId,
      documentFingerprint: result.documentFingerprint,
      split: result.split,
    });
    session = setBenchmarkContractTestInputs(session, {
      seed: result.seed,
      profile: benchmarkContractProfilePageFixture().profiles[0]!,
    });
    const owner = benchmarkContractTestRequestOwner(session)!;
    expect(acceptBenchmarkContractTestResult(session, owner, result).result).toEqual(result);
    const changed = setBenchmarkContractTestInputs(session, { seed: result.seed + 1 });
    expect(acceptBenchmarkContractTestResult(changed, owner, result).result).toBeNull();
    const changedProfile = setBenchmarkContractTestInputs(session, {
      profile: { ...session.profile!, version: "2.0.0" },
    });
    expect(acceptBenchmarkContractTestResult(changedProfile, owner, result).result).toBeNull();
    const switchedRevision = createBenchmarkContractTestSession({
      draftId: result.draftId,
      revisionId: `${result.revisionId.slice(0, -1)}c`,
      documentFingerprint: result.documentFingerprint,
      split: result.split,
    });
    expect(acceptBenchmarkContractTestResult(switchedRevision, owner, result).result).toBeNull();
  });
});
