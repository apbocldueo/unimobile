import type {
  BenchmarkDryRunResult,
  BenchmarkValidationResult,
} from "../model/benchmarkAuthoringAnalysis.schema";
import {
  benchmarkDigestFixture,
  benchmarkDraftFixtureId,
  benchmarkRevisionFixtureId,
} from "./benchmarkAuthoring.fixtures";

export const benchmarkAgentFixtureId = "agent-analysis-fixture";
export const benchmarkAgentRevisionFixtureId = "revision-analysis-fixture";

/** Build a partial invalid validation response with one navigable diagnostic. */
export function benchmarkValidationResultFixture(): BenchmarkValidationResult {
  return {
    schemaVersion: 1,
    mode: "validation",
    draftId: benchmarkDraftFixtureId,
    revisionId: benchmarkRevisionFixtureId,
    documentFingerprint: benchmarkDigestFixture,
    split: "test",
    valid: false,
    identities: {
      package: "fixture/authoring@0.1.0",
      packageContent: benchmarkDigestFixture,
      benchmarkPlan: null,
      experimentProtocol: null,
    },
    diagnostics: [
      {
        code: "benchmark.task.id_required",
        message: "Task id is required.",
        severity: "error",
        memberKind: "task",
        memberPath: "tasks/test.json",
        fieldPath: [0, "id"],
        taskId: null,
        resourceId: null,
        agentId: null,
        revisionId: null,
      },
    ],
    diagnosticsTruncated: false,
    unverifiedChecks: ["plugin-availability"],
    executionEvidence: false,
  };
}

/** Build one complete deterministic non-executing dry-run response. */
export function benchmarkDryRunResultFixture(): BenchmarkDryRunResult {
  return {
    schemaVersion: 1,
    mode: "side-effect-free-dry-run",
    draftId: benchmarkDraftFixtureId,
    revisionId: benchmarkRevisionFixtureId,
    documentFingerprint: benchmarkDigestFixture,
    split: "test",
    ok: true,
    identities: {
      package: "fixture/authoring@0.1.0",
      packageContent: benchmarkDigestFixture,
      benchmarkPlan: `sha256:${"1".repeat(64)}`,
      experimentProtocol: `sha256:${"2".repeat(64)}`,
    },
    agentRevisions: [
      {
        agentId: benchmarkAgentFixtureId,
        revisionId: benchmarkAgentRevisionFixtureId,
        agentGraphIdentity: `sha256:${"3".repeat(64)}`,
      },
    ],
    schedule: [
      {
        repeat: 0,
        taskId: "fixture-task",
        agentId: benchmarkAgentFixtureId,
        seed: 17,
        sharedInstanceKey: "fixture-task:0",
      },
    ],
    budget: {
      maxInteractions: 20,
      maxActivations: 30,
      timeoutSeconds: 300,
      tokenLimit: null,
      requireObservableTokens: false,
    },
    fairnessWarnings: ["TaskInstance reuse is not proven comparable."],
    outputLayout: {
      experimentReport: "<artifact-root>/<experiment-id>/experiment-report.json",
      runReport: "<artifact-root>/<experiment-id>/runs/<task-run-id>/run-report.json",
      trajectory: "<artifact-root>/<experiment-id>/runs/<task-run-id>/trajectory.jsonl",
      bundle: "<artifact-root>/<experiment-id>/trajectory-bundle.zip",
    },
    unverifiedChecks: ["current-worker-cardinality", "dynamic-materialization"],
    diagnostics: [],
    diagnosticsTruncated: false,
    executionEvidence: false,
  };
}
