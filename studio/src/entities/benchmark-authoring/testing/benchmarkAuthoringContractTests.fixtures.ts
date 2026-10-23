import type {
  BenchmarkContractTestProfilePage,
  BenchmarkContractTestResult,
} from "../model/benchmarkAuthoringContractTests.schema";
import {
  benchmarkDigestFixture,
  benchmarkDraftFixtureId,
  benchmarkRevisionFixtureId,
} from "./benchmarkAuthoring.fixtures";

export const benchmarkContractProfileFixture = {
  profileId: "studio-safe-v1",
  version: "1.0.0",
  title: "Studio safe fake fixtures",
  description: "Reviewed in-process fake contracts.",
  evidenceLevel: "fake-contract",
  supportedKinds: ["evaluator", "initializer"],
  capabilities: [],
} as const;

/** Build the bounded metadata-only profile resource fixture. */
export function benchmarkContractProfilePageFixture(): BenchmarkContractTestProfilePage {
  return {
    schemaVersion: 1,
    profiles: [{
      ...benchmarkContractProfileFixture,
      supportedKinds: [...benchmarkContractProfileFixture.supportedKinds],
      capabilities: [],
    }],
  };
}

/** Build one complete passing exact-revision Contract Test fixture. */
export function benchmarkContractTestResultFixture(): BenchmarkContractTestResult {
  return {
    schemaVersion: 1,
    mode: "fake-fixture",
    draftId: benchmarkDraftFixtureId,
    revisionId: benchmarkRevisionFixtureId,
    documentFingerprint: benchmarkDigestFixture,
    requestFingerprint: `sha256:${"1".repeat(64)}`,
    split: "test",
    seed: 17,
    profile: benchmarkContractProfilePageFixture().profiles[0]!,
    identities: {
      package: "fixture/authoring@0.1.0",
      packageContent: `sha256:${"2".repeat(64)}`,
      benchmarkPlan: `sha256:${"3".repeat(64)}`,
      experimentProtocol: `sha256:${"4".repeat(64)}`,
    },
    validDefinition: true,
    coverage: {
      total: 1,
      passed: 1,
      failed: 0,
      skipped: 0,
      complete: true,
      executedChecksPassed: true,
    },
    cases: [{
      caseId: `sha256:${"5".repeat(64)}`,
      taskId: "fixture-task",
      kind: "evaluator",
      logicalName: "file_exist",
      memberPath: "tasks/test.json",
      fieldPath: [0, "evaluator"],
      phase: "evaluation",
      seed: 123,
      status: "passed",
      fixtureId: "studio.file_exist",
      fixtureVersion: "1.0.0",
      checks: ["determinism", "serialization"],
      skipped: [],
      diagnostics: [],
    }],
    preconditionDiagnostics: [],
    diagnosticsTruncated: false,
    safety: {
      fixtureExecution: true,
      packageCodeExecuted: false,
      realDeviceEvidence: false,
      processSandbox: false,
      deviceCapability: false,
      modelCapability: false,
      networkCapability: false,
      secretCapability: false,
      runtimeCapability: false,
      experimentCapability: false,
      outputPathCapability: false,
      benchmarkExecution: false,
      agentExecution: false,
      publicationEligibility: false,
      resultPersisted: false,
    },
  };
}
