import { describe, expect, it } from "vitest";
import {
  parseBenchmarkExperimentHistoryPage,
  parseBenchmarkExperimentResource,
} from "./benchmarkExperiment.schema";
import { benchmarkExperimentFixture } from "../testing/benchmarkExperiment.fixtures";

const newerId = `experiment-${"b".repeat(32)}`;
const olderId = `experiment-${"a".repeat(32)}`;
const otherId = `experiment-${"f".repeat(32)}`;

/** Build one compact immutable Experiment history item. */
function historyItem(experimentId: string, acceptedAt: number) {
  const base = `/studio/benchmark-experiments/${experimentId}`;
  return {
    schemaVersion: 1,
    experimentId,
    lifecycle: "running",
    terminalReason: null,
    source: {
      catalogEntryId: "catalog-1",
      packageIdentity: "package@1",
      split: "test",
    },
    agents: [{ agentId: "agent-1", revisionId: "revision-1" }],
    plannedTaskRunCount: 1,
    outcomeAvailability: "pending",
    reportAvailability: "pending",
    replayAvailability: "pending",
    trajectoryAvailability: "pending",
    bundleAvailability: "pending",
    acceptedAt,
    updatedAt: acceptedAt,
    terminalAt: null,
    links: {
      self: base,
      taskRuns: `${base}/task-runs`,
      artifacts: `${base}/artifacts`,
      report: null,
      bundle: null,
    },
  };
}

describe("Benchmark Experiment history contracts", () => {
  it("accepts deterministic newest-first compact summaries", () => {
    const page = parseBenchmarkExperimentHistoryPage({
      schemaVersion: 1,
      items: [historyItem(newerId, 2), historyItem(olderId, 1)],
      nextCursor: "opaque",
    });
    expect(page.items[0]?.experimentId).toBe(newerId);
    expect(JSON.stringify(page)).not.toContain("agentGraph");
  });

  it("rejects full-definition leakage, unstable order and cross-scope links", () => {
    expect(() =>
      parseBenchmarkExperimentHistoryPage({
        schemaVersion: 1,
        items: [{ ...historyItem(newerId, 2), definition: {} }],
        nextCursor: null,
      }),
    ).toThrow(/not supported/);
    expect(() =>
      parseBenchmarkExperimentHistoryPage({
        schemaVersion: 1,
        items: [historyItem(olderId, 1), historyItem(newerId, 2)],
        nextCursor: null,
      }),
    ).toThrow(/newest first/);
    expect(() =>
      parseBenchmarkExperimentHistoryPage({
        schemaVersion: 1,
        items: [
          { ...historyItem(newerId, 2), plannedTaskRunCount: 0 },
        ],
        nextCursor: null,
      }),
    ).toThrow(/positive integer/);
    expect(() =>
      parseBenchmarkExperimentHistoryPage({
        schemaVersion: 1,
        items: [
          {
            ...historyItem(newerId, 2),
            links: {
              ...historyItem(newerId, 2).links,
              self: `/studio/benchmark-experiments/${olderId}`,
            },
          },
        ],
        nextCursor: null,
      }),
    ).toThrow(/expected resource scope/);
  });

  it("accepts the new exact artifact inventory link on Experiment detail", () => {
    expect(
      parseBenchmarkExperimentResource(benchmarkExperimentFixture()).links
        .artifacts,
    ).toContain("/artifacts");
    expect(() =>
      parseBenchmarkExperimentResource({
        ...benchmarkExperimentFixture(),
        links: {
          ...benchmarkExperimentFixture().links,
          artifacts: `/studio/benchmark-experiments/${otherId}/artifacts`,
        },
      }),
    ).toThrow(/expected resource scope/);
  });
});
