import { describe, expect, it } from "vitest";
import {
  defaultExperimentProtocol,
  parseExperimentPreview,
  parseExperimentProtocol,
} from "@/entities/experiment-preview";

const hash = `sha256:${"a".repeat(64)}`;

/** Build one complete backend-shaped preview response. */
function previewResponse() {
  const protocol = defaultExperimentProtocol();
  return {
    schemaVersion: 1,
    previewOnly: true,
    previewFingerprint: hash,
    identities: {
      package: "tests/fixture@1.0.0",
      packageContent: hash,
      benchmarkPlan: hash,
      experimentProtocol: hash,
    },
    agentRevisions: [
      { agentId: "agent-1", revisionId: "revision-1", agentGraph: hash },
    ],
    normalizedProtocol: protocol,
    deviceProfileId: "local-android",
    executionLimits: {
      maxAgents: 1,
      maxSelectedTasks: 1,
      maxRepeats: 1,
      multiAgentComparison: false,
    },
    schedule: [
      {
        plannedEntryId: "planned-entry-1",
        agentId: "agent-1",
        revisionId: "revision-1",
        taskId: "fixture-task",
        repeat: 0,
        order: 0,
        derivedSeed: 42,
        taskInstance: {
          availability: "template_only",
          identity: null,
          parameters: null,
        },
      },
    ],
    diagnostics: [],
  };
}

describe("Experiment preview browser contracts", () => {
  it("parses the complete formal Protocol and preview schedule", () => {
    const protocol = parseExperimentProtocol(defaultExperimentProtocol());
    expect(protocol.budget.maxInteractions).toBe(15);
    expect(parseExperimentPreview(previewResponse()).schedule[0]?.derivedSeed).toBe(42);
  });

  it("normalizes omitted optional task materialization fields to null", () => {
    const response = previewResponse();
    const taskInstance = response.schedule[0]!.taskInstance as {
      availability: string;
      identity?: null;
      parameters?: null;
    };
    delete taskInstance.identity;
    delete taskInstance.parameters;

    expect(parseExperimentPreview(response).schedule[0]?.taskInstance).toEqual({
      availability: "template_only",
      identity: null,
      parameters: null,
    });
  });

  it("rejects unknown fields, non-finite budgets, and materialized instances", () => {
    expect(() =>
      parseExperimentProtocol({
        ...defaultExperimentProtocol(),
        hiddenDefault: true,
      }),
    ).toThrow(/hiddenDefault/);
    expect(() =>
      parseExperimentProtocol({
        ...defaultExperimentProtocol(),
        budget: {
          ...defaultExperimentProtocol().budget,
          timeoutSeconds: Number.POSITIVE_INFINITY,
        },
      }),
    ).toThrow(/finite/);
    const materialized = previewResponse() as unknown as {
      schedule: Array<{ taskInstance: { identity: unknown } }>;
    };
    materialized.schedule[0]!.taskInstance.identity = "forbidden";
    expect(() => parseExperimentPreview(materialized)).toThrow(/unmaterialized/);
  });
});
