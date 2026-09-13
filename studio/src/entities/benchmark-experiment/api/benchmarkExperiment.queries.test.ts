import { describe, expect, it } from "vitest";
import {
  benchmarkExperimentHistoryQueryOptions,
  benchmarkExperimentKeys,
} from "./benchmarkExperiment.queries";

describe("Benchmark Experiment History query identity", () => {
  it("separates filters, limit, and opaque cursor in the cache key", () => {
    const running = benchmarkExperimentHistoryQueryOptions(
      25,
      "cursor-a",
      { lifecycle: "running", agentId: "agent-one" },
    );
    const accepted = benchmarkExperimentHistoryQueryOptions(
      25,
      "cursor-a",
      { lifecycle: "accepted", agentId: "agent-one" },
    );
    expect(running.queryKey).not.toEqual(accepted.queryKey);
    expect(running.queryKey).toEqual(
      benchmarkExperimentKeys.history(
        { lifecycle: "running", agentId: "agent-one" },
        25,
        "cursor-a",
      ),
    );
  });

  it("preserves the old unfiltered query configuration", () => {
    expect(benchmarkExperimentHistoryQueryOptions().queryKey).toEqual(
      benchmarkExperimentKeys.history({}, 50, null),
    );
  });
});
