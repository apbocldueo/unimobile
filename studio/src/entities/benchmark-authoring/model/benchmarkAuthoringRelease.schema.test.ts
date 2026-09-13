import { describe, expect, it } from "vitest";
import {
  benchmarkFreezeResultFixture,
  benchmarkPackageExportFixture,
  benchmarkPackageRevisionPageFixture,
} from "../testing/benchmarkAuthoringRelease.fixtures";
import {
  parseBenchmarkFreezeResult,
  parseBenchmarkPackageExport,
  parseBenchmarkPackageRevisionPage,
  parseBenchmarkReleaseCommand,
} from "./benchmarkAuthoringRelease.schema";

/** Clone one JSON fixture so rejection tests never share mutated state. */
function cloneFixture<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

describe("Benchmark authoring release schema", () => {
  it("parses exact release resources with fixed negative runtime evidence", () => {
    const freeze = parseBenchmarkFreezeResult(benchmarkFreezeResultFixture());
    const page = parseBenchmarkPackageRevisionPage(
      benchmarkPackageRevisionPageFixture({ published: true, exported: true }),
    );
    expect(freeze.detail.validationAttestation.safety.executionEvidence).toBe(false);
    expect(page.items[0]?.publication?.safety.publicationEvidence).toBe(true);
    expect(page.items[0]?.packageExport?.safety.executionEvidence).toBe(false);
  });

  it("rejects coercion, unknown authority, and unsafe scoped capabilities", () => {
    expect(() => parseBenchmarkReleaseCommand({
      schemaVersion: "1",
      clientRequestId: "release-1",
    })).toThrow();
    expect(() => parseBenchmarkReleaseCommand({
      schemaVersion: 1,
      clientRequestId: "release-1",
      outputPath: "/tmp/package.zip",
    })).toThrow();

    const page = cloneFixture(benchmarkPackageRevisionPageFixture()) as {
      items: Array<Record<string, unknown>>;
    };
    page.items[0]!.detailLink = "/api/studio/benchmark-authoring/drafts/../../secret";
    expect(() => parseBenchmarkPackageRevisionPage(page)).toThrow();

    const packageExport = cloneFixture(benchmarkPackageExportFixture()) as
      Record<string, unknown>;
    packageExport.contentLink = "/api/studio/benchmark-authoring/drafts/other/content";
    expect(() => parseBenchmarkPackageExport(packageExport)).toThrow();
  });

  it("rejects broadened evidence and Package/attestation disagreement", () => {
    const packageExport = cloneFixture(benchmarkPackageExportFixture()) as {
      safety: Record<string, unknown>;
    };
    packageExport.safety.executionEvidence = true;
    expect(() => parseBenchmarkPackageExport(packageExport)).toThrow();

    const freeze = cloneFixture(benchmarkFreezeResultFixture()) as {
      detail: {
        validationAttestation: Record<string, unknown>;
      };
    };
    freeze.detail.validationAttestation.packageIdentity = "other/package@1.0.0";
    expect(() => parseBenchmarkFreezeResult(freeze)).toThrow();
    freeze.detail.validationAttestation.packageIdentity = "fixture/authoring@0.1.0";
    freeze.detail.validationAttestation.secret = "must-not-pass";
    expect(() => parseBenchmarkFreezeResult(freeze)).toThrow();
  });
});
