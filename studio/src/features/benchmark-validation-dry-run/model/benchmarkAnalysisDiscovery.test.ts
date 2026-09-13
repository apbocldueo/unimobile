import { describe, expect, it } from "vitest";
import { benchmarkAuthoringDocumentFixture } from "@/entities/benchmark-authoring";
import { discoverBenchmarkSplits, discoverBenchmarkTaskIds } from "@/features/benchmark-validation-dry-run";

describe("benchmark analysis discovery", () => {
  it("discovers bounded manifest suggestions and split-owned tasks", () => {
    const document = benchmarkAuthoringDocumentFixture();
    expect(discoverBenchmarkSplits(document)).toEqual(["test"]);
    expect(discoverBenchmarkTaskIds(document, "test")).toEqual(["fixture-task"]);
    expect(discoverBenchmarkTaskIds(document, "missing")).toEqual([]);
  });

  it("keeps malformed open mappings out of suggestions without validating", () => {
    const document = benchmarkAuthoringDocumentFixture();
    document.manifest.document.splits = {
      "../unsafe": { files: ["tasks/test.json"] },
      test: { files: "not-an-array" },
    };
    expect(discoverBenchmarkSplits(document)).toEqual(["test"]);
    expect(discoverBenchmarkTaskIds(document, "test")).toEqual([]);
  });
});
