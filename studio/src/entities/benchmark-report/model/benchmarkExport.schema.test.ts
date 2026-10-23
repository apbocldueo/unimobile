import { describe, expect, it } from "vitest";
import {
  BENCHMARK_PUBLICATION_MANIFEST_MAX_MEMBERS,
  parseBenchmarkPublicationManifest,
  reportExperimentId,
  reportTaskRunId,
  summarizeBenchmarkPublicationManifest,
} from "@/entities/benchmark-report";

const HASH = `sha256:${"a".repeat(64)}`;

/** Build one publisher-shaped strict manifest. */
function manifest() {
  return {
    schemaVersion: 1,
    kind: "studio_benchmark_publication_manifest",
    experimentId: reportExperimentId,
    taskRunId: reportTaskRunId,
    members: [
      {
        reference: "experiment-report.json",
        kind: "experiment_report",
        contentType: "application/json",
        size: 12,
        sha256: HASH,
        scope: { experimentId: reportExperimentId },
        availability: "available",
        exclusionReason: "",
      },
      {
        reference: `runs/${reportTaskRunId}/trajectory.jsonl`,
        kind: "task_trajectory",
        contentType: "application/x-ndjson",
        size: 20,
        sha256: HASH,
        scope: {
          experimentId: reportExperimentId,
          taskRunId: reportTaskRunId,
        },
        availability: "available",
        exclusionReason: "",
      },
    ],
    excludedEvidence: [
      {
        kind: "prompt",
        availability: "hidden",
        reason: "hidden_by_default_policy",
      },
    ],
  };
}

describe("parseBenchmarkPublicationManifest", () => {
  it("parses and summarizes exact member and excluded-evidence facts", () => {
    const parsed = parseBenchmarkPublicationManifest(
      manifest(),
      reportExperimentId,
      new Set([reportTaskRunId]),
    );
    expect(summarizeBenchmarkPublicationManifest(parsed)).toMatchObject({
      memberCount: 2,
      declaredBytes: 32,
      excludedEvidence: [
        {
          kind: "prompt",
          availability: "hidden",
          reason: "hidden_by_default_policy",
        },
      ],
    });
  });

  it.each([
    ["schema", { schemaVersion: 2 }, /schema/],
    ["Experiment", { experimentId: `experiment-${"f".repeat(32)}` }, /identities/],
    ["TaskRun", { taskRunId: `task-run-${"f".repeat(32)}` }, /identities/],
  ])("rejects conflicting %s identity", (_label, patch, error) => {
    expect(() =>
      parseBenchmarkPublicationManifest(
        { ...manifest(), ...patch },
        reportExperimentId,
        new Set([reportTaskRunId]),
      )
    ).toThrow(error);
  });

  it.each([
    ["unsafe reference", { reference: "../secret.json" }, /safe relative/],
    ["unknown kind", { kind: "arbitrary" }, /kind is unsupported/],
    ["unknown media", { contentType: "text/html" }, /contentType/],
    ["bad digest", { sha256: "sha256:no" }, /sha256/],
    ["bad scope", { scope: { experimentId: reportExperimentId, taskRunId: `task-run-${"f".repeat(32)}` } }, /scope/],
  ])("rejects member %s", (_label, patch, error) => {
    const value = manifest();
    value.members[0] = { ...value.members[0]!, ...patch };
    expect(() =>
      parseBenchmarkPublicationManifest(
        value,
        reportExperimentId,
        new Set([reportTaskRunId]),
      )
    ).toThrow(error);
  });

  it("rejects duplicate references and unbounded collections", () => {
    const duplicate = manifest();
    duplicate.members[1] = {
      ...duplicate.members[1]!,
      reference: duplicate.members[0]!.reference,
    };
    expect(() =>
      parseBenchmarkPublicationManifest(
        duplicate,
        reportExperimentId,
        new Set([reportTaskRunId]),
      )
    ).toThrow(/duplicate/);
    const oversized = manifest();
    oversized.members = Array.from(
      { length: BENCHMARK_PUBLICATION_MANIFEST_MAX_MEMBERS + 1 },
      () => oversized.members[0]!,
    );
    expect(() =>
      parseBenchmarkPublicationManifest(
        oversized,
        reportExperimentId,
        new Set([reportTaskRunId]),
      )
    ).toThrow(/bounded/);
  });

  it("rejects unknown excluded policy instead of exposing content", () => {
    const value = manifest();
    value.excludedEvidence[0] = {
      kind: "prompt",
      availability: "hidden",
      reason: "hidden_by_default_policy",
    };
    (value.excludedEvidence[0] as { kind: string }).kind = "secret";
    expect(() =>
      parseBenchmarkPublicationManifest(
        value,
        reportExperimentId,
        new Set([reportTaskRunId]),
      )
    ).toThrow(/exclusion policy/);
  });
});
