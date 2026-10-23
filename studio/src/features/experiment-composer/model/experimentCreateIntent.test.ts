import { describe, expect, it } from "vitest";
import {
  defaultExperimentProtocol,
  type ExperimentPreview,
  type ExperimentPreviewRequest,
} from "@/entities/experiment-preview";
import {
  isPreparedPreviewCurrent,
  prepareExperimentCreateIntent,
  type PreparedExperimentPreview,
} from "./experimentCreateIntent";

const hash = `sha256:${"a".repeat(64)}`;

/** Build one exact preview request and response pair. */
function prepared(semanticVersion = 1): PreparedExperimentPreview {
  const request: ExperimentPreviewRequest = {
    schemaVersion: 1,
    agentRevisions: [{ agentId: "agent-1", revisionId: "revision-1" }],
    benchmark: {
      catalogEntryId: "catalog-entry-1",
      split: "test",
      taskIds: ["task-1"],
    },
    protocol: defaultExperimentProtocol(),
    deviceProfileId: "local-android",
  };
  const value: ExperimentPreview = {
    schemaVersion: 1,
    previewOnly: true,
    previewFingerprint: hash,
    identities: {
      package: "fixture@1",
      packageContent: hash,
      benchmarkPlan: hash,
      experimentProtocol: hash,
    },
    agentRevisions: [
      { agentId: "agent-1", revisionId: "revision-1", agentGraph: hash },
    ],
    normalizedProtocol: defaultExperimentProtocol(),
    deviceProfileId: "local-android",
    executionLimits: {
      maxAgents: 1,
      maxSelectedTasks: 1,
      maxRepeats: 1,
      multiAgentComparison: false,
    },
    schedule: [
      {
        plannedEntryId: "planned-1",
        agentId: "agent-1",
        revisionId: "revision-1",
        taskId: "task-1",
        repeat: 0,
        order: 0,
        derivedSeed: 7,
        taskInstance: {
          availability: "template_only",
          identity: null,
          parameters: null,
        },
      },
    ],
    diagnostics: [],
  };
  return { semanticVersion, request, value, invalidated: false };
}

describe("Experiment create intent", () => {
  it("reuses one identity for an exact unknown-result retry", () => {
    let generated = 0;
    const factory = () => `intent-${++generated}`;
    const first = prepareExperimentCreateIntent(null, prepared(), factory);
    const retry = prepareExperimentCreateIntent(first, prepared(), factory);
    expect(retry).toBe(first);
    expect(retry.input.clientRequestId).toBe("intent-1");
    expect(generated).toBe(1);
  });

  it("creates a new identity after a semantic change", () => {
    let generated = 0;
    const factory = () => `intent-${++generated}`;
    const first = prepareExperimentCreateIntent(null, prepared(1), factory);
    const next = prepareExperimentCreateIntent(first, prepared(2), factory);
    expect(next.input.clientRequestId).toBe("intent-2");
  });

  it("rejects stale or explicitly invalidated previews", () => {
    expect(isPreparedPreviewCurrent(prepared(1), 2)).toBe(false);
    expect(
      isPreparedPreviewCurrent({ ...prepared(1), invalidated: true }, 1),
    ).toBe(false);
  });
});
