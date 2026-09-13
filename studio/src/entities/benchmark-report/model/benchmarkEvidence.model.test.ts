import { describe, expect, it } from "vitest";
import {
  benchmarkReportInventoryFixture,
  benchmarkRunReportFixture,
  parseBenchmarkArtifactInventoryPage,
  parseBenchmarkRunReport,
  reportExperimentId,
  reportTaskRunId,
} from "@/entities/benchmark-report";
import { resolveBenchmarkEvidence } from "./benchmarkEvidence.model";

/** Build the strict fixture evidence descriptor and assign one causal ref. */
function evidence(reference = "runs/evidence.json") {
  const value = parseBenchmarkRunReport(
    benchmarkRunReportFixture(),
  ).evaluation!.children[0]!.evaluatorResult!.evidence[0]!;
  return { ...value, artifactRef: reference };
}

/** Build one closed parsed same-scope inventory with a selected causal ref. */
function inventory(reference = "runs/evidence.json") {
  const raw = benchmarkReportInventoryFixture();
  raw.items[0]!.descriptor.kind = "evaluator_evidence";
  raw.items[0]!.descriptor.causalIdentity = reference;
  return parseBenchmarkArtifactInventoryPage(raw);
}

describe("resolveBenchmarkEvidence", () => {
  const scope = {
    experimentId: reportExperimentId,
    taskRunId: reportTaskRunId,
  };

  it("resolves exactly one visible same-Experiment and same-TaskRun match", () => {
    expect(resolveBenchmarkEvidence(scope, evidence(), inventory())).toMatchObject({
      kind: "readable",
      availability: "available",
    });
  });

  it("distinguishes empty references and hidden aggregate uncertainty", () => {
    const value = inventory();
    value.hiddenCount = 2;
    expect(resolveBenchmarkEvidence(scope, evidence(""), value)).toEqual({
      kind: "no-reference",
      hiddenCount: 2,
    });
    expect(
      resolveBenchmarkEvidence(scope, evidence("runs/absent.json"), value),
    ).toMatchObject({
      kind: "reference-unavailable",
      hiddenCount: 2,
    });
  });

  it("rejects cross-Experiment, cross-TaskRun, and Experiment-scoped candidates", () => {
    const wrongExperiment = inventory();
    wrongExperiment.experimentId = `experiment-${"f".repeat(32)}`;
    expect(
      resolveBenchmarkEvidence(scope, evidence(), wrongExperiment),
    ).toMatchObject({ kind: "reference-unavailable" });

    const wrongTask = inventory();
    wrongTask.items[0]!.descriptor.taskRunId = `task-run-${"e".repeat(32)}`;
    expect(resolveBenchmarkEvidence(scope, evidence(), wrongTask)).toMatchObject({
      kind: "reference-unavailable",
    });

    const experimentScoped = inventory();
    experimentScoped.items[0]!.descriptor.taskRunId = null;
    expect(
      resolveBenchmarkEvidence(scope, evidence(), experimentScoped),
    ).toMatchObject({ kind: "reference-unavailable" });
  });

  it("fails closed for duplicate references and incomplete closure", () => {
    const duplicate = inventory();
    duplicate.items.push({
      ...structuredClone(duplicate.items[0]!),
      descriptor: {
        ...structuredClone(duplicate.items[0]!.descriptor),
        artifactId: `artifact-${"e".repeat(32)}`,
      },
      links: {
        content:
          `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
          + `${reportTaskRunId}/artifacts/artifact-${"e".repeat(32)}`,
      },
    });
    expect(resolveBenchmarkEvidence(scope, evidence(), duplicate)).toMatchObject({
      kind: "ambiguous-reference",
      matchCount: 2,
    });

    const incomplete = inventory();
    incomplete.nextCursor = "still-open";
    expect(
      resolveBenchmarkEvidence(scope, evidence(), incomplete),
    ).toMatchObject({
      kind: "reference-unavailable",
      reason: "incomplete-inventory",
    });
  });

  it("rejects an unsafe or rebuilt content capability", () => {
    const unsafe = inventory();
    unsafe.items[0]!.links.content = "/guessed/content/path";
    expect(resolveBenchmarkEvidence(scope, evidence(), unsafe)).toMatchObject({
      kind: "reference-unavailable",
      reason: "scope-conflict",
    });
  });

  it.each([
    "pending",
    "not_produced",
    "excluded",
    "missing",
    "corrupt",
    "failed",
  ] as const)("preserves persisted %s availability", (availability) => {
    const value = inventory();
    value.items[0]!.descriptor.availability = availability;
    value.items[0]!.descriptor.contentType = "";
    value.items[0]!.descriptor.sha256 = null;
    value.items[0]!.links.content = null;
    expect(resolveBenchmarkEvidence(scope, evidence(), value)).toMatchObject({
      kind: "persisted-unreadable",
      availability,
    });
  });
});

