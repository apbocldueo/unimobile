import { describe, expect, it } from "vitest";
import {
  benchmarkContractProfilePageFixture,
  benchmarkContractTestResultFixture,
  parseBenchmarkContractTestProfilePage,
  parseBenchmarkContractTestResult,
} from "@/entities/benchmark-authoring";

describe("Benchmark Contract Test schema", () => {
  it("accepts complete and mixed coverage while preserving ownership", () => {
    const complete = benchmarkContractTestResultFixture();
    expect(parseBenchmarkContractTestResult(complete)).toEqual(complete);
    const mixed = structuredClone(complete);
    mixed.coverage = {
      total: 2,
      passed: 1,
      failed: 0,
      skipped: 1,
      complete: false,
      executedChecksPassed: true,
    };
    mixed.cases.push({
      ...mixed.cases[0]!,
      caseId: `sha256:${"6".repeat(64)}`,
      kind: "environment",
      logicalName: "third_party_setup",
      status: "skipped",
      fixtureId: null,
      fixtureVersion: null,
      checks: [],
      skipped: ["fixture:not-registered"],
      diagnostics: [{
        code: "benchmark.ctk.fixture_missing",
        message: "No explicit environment fake fixture is registered.",
        memberKind: "task",
        memberPath: "tasks/test.json",
        fieldPath: [0, "environment_initializer", 0],
        taskId: "fixture-task",
      }],
    });
    expect(parseBenchmarkContractTestResult(mixed).coverage.complete).toBe(false);
  });

  it("rejects contradictory counts, unsafe paths, and stronger safety claims", () => {
    const contradictory = structuredClone(benchmarkContractTestResultFixture()) as unknown as Record<string, unknown>;
    (contradictory.coverage as Record<string, unknown>).passed = 0;
    expect(() => parseBenchmarkContractTestResult(contradictory)).toThrow(/contradict/i);

    const unsafe = structuredClone(benchmarkContractTestResultFixture()) as unknown as Record<string, unknown>;
    ((unsafe.cases as Array<Record<string, unknown>>)[0]!).memberPath = "/tmp/private";
    expect(() => parseBenchmarkContractTestResult(unsafe)).toThrow(/malformed/i);

    const misleading = structuredClone(benchmarkContractTestResultFixture()) as unknown as Record<string, unknown>;
    (misleading.safety as Record<string, unknown>).processSandbox = true;
    expect(() => parseBenchmarkContractTestResult(misleading)).toThrow(/misleading/i);
  });

  it("rejects unknown fields and oversized profile collections", () => {
    const page = benchmarkContractProfilePageFixture() as unknown as Record<string, unknown>;
    page.module = "forbidden.fixture";
    expect(() => parseBenchmarkContractTestProfilePage(page)).toThrow(/not supported/i);
    const oversized = benchmarkContractProfilePageFixture() as unknown as Record<string, unknown>;
    oversized.profiles = Array.from({ length: 33 }, () => benchmarkContractProfilePageFixture().profiles[0]);
    expect(() => parseBenchmarkContractTestProfilePage(oversized)).toThrow(/bound/i);

    const cases = structuredClone(benchmarkContractTestResultFixture()) as unknown as Record<string, unknown>;
    cases.cases = Array.from({ length: 1_001 }, () => (benchmarkContractTestResultFixture().cases[0]));
    expect(() => parseBenchmarkContractTestResult(cases)).toThrow(/bound/i);

    const owner = structuredClone(benchmarkContractTestResultFixture()) as unknown as Record<string, unknown>;
    owner.draftId = "foreign-draft";
    expect(() => parseBenchmarkContractTestResult(owner)).toThrow(/draftId/i);
  });
});
