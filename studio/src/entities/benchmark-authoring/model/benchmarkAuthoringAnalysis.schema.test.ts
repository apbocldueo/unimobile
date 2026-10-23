import { describe, expect, it } from "vitest";
import {
  BENCHMARK_ANALYSIS_MAX_DIAGNOSTICS,
  BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES,
  benchmarkDryRunResultFixture,
  benchmarkValidationResultFixture,
  parseBenchmarkDryRunResult,
  parseBenchmarkValidationResult,
} from "@/entities/benchmark-authoring";

/** Clone one JSON-compatible fixture for adversarial parser mutation. */
function cloned<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

describe("Benchmark authoring analysis schema", () => {
  it("preserves partial validation and complete dry-run facts", () => {
    expect(parseBenchmarkValidationResult(benchmarkValidationResultFixture()))
      .toEqual(benchmarkValidationResultFixture());
    expect(parseBenchmarkDryRunResult(benchmarkDryRunResultFixture()))
      .toEqual(benchmarkDryRunResultFixture());
  });

  it("rejects unknown fields, unsafe paths, and execution claims", () => {
    const unknown = cloned(benchmarkValidationResultFixture()) as Record<string, unknown>;
    unknown.runtimeResult = "forbidden";
    expect(() => parseBenchmarkValidationResult(unknown)).toThrow(/runtimeResult/);

    const unsafe = cloned(benchmarkValidationResultFixture());
    unsafe.diagnostics[0]!.memberPath = "../../private";
    expect(() => parseBenchmarkValidationResult(unsafe)).toThrow(/memberPath/);

    const claimed = cloned(benchmarkDryRunResultFixture()) as unknown as {
      executionEvidence: boolean;
    };
    claimed.executionEvidence = true;
    expect(() => parseBenchmarkDryRunResult(claimed)).toThrow(/evidence/);
  });

  it("enforces diagnostics and schedule capacities before projection", () => {
    const diagnostics = cloned(benchmarkValidationResultFixture());
    diagnostics.diagnostics = Array.from(
      { length: BENCHMARK_ANALYSIS_MAX_DIAGNOSTICS + 1 },
      () => diagnostics.diagnostics[0]!,
    );
    expect(() => parseBenchmarkValidationResult(diagnostics)).toThrow(/bound/);

    const schedule = cloned(benchmarkDryRunResultFixture());
    schedule.schedule = Array.from(
      { length: BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES + 1 },
      () => schedule.schedule[0]!,
    );
    expect(() => parseBenchmarkDryRunResult(schedule)).toThrow(/bound/);
  });

  it("rejects partial planning facts on a failed dry-run", () => {
    const failed = cloned(benchmarkDryRunResultFixture());
    failed.ok = false;
    expect(() => parseBenchmarkDryRunResult(failed)).toThrow(/partial/);
  });

  it("rejects malformed ownership and AgentGraph identities", () => {
    const owner = cloned(benchmarkValidationResultFixture());
    owner.revisionId = "revision-not-authoring";
    expect(() => parseBenchmarkValidationResult(owner)).toThrow(/revisionId/);

    const graph = cloned(benchmarkDryRunResultFixture());
    graph.agentRevisions[0]!.agentGraphIdentity = "caller-supplied";
    expect(() => parseBenchmarkDryRunResult(graph)).toThrow(/agentGraphIdentity/);
  });
});
