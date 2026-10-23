import { describe, expect, it } from "vitest";
import {
  parseBenchmarkExperimentResource,
  parseBenchmarkTaskRun,
} from "@/entities/benchmark-experiment";
import {
  benchmarkExperimentFixture,
  benchmarkTaskRunFixture,
} from "@/entities/benchmark-experiment";
import {
  currentBenchmarkTaskRun,
  projectBenchmarkTaskRunRail,
  projectBenchmarkTaskRunView,
  reconcileBenchmarkTaskRunSelection,
  selectBenchmarkTaskRun,
} from "./benchmarkMonitor";

/** Parse a test TaskRun after applying a narrow fixture override. */
function taskRun(
  order: number,
  overrides: Record<string, unknown> = {},
) {
  return parseBenchmarkTaskRun({
    ...benchmarkTaskRunFixture(order),
    ...overrides,
  });
}

describe("Benchmark Monitor projections", () => {
  it("uses planned order and preserves an explicit historical lock", () => {
    const terminal = taskRun(0, {
      lifecycle: "terminal",
      terminalReason: "completed",
      terminalAt: 8,
    });
    const active = taskRun(1);
    const items = [active, terminal];
    expect(currentBenchmarkTaskRun(items)?.taskRunId).toBe(active.taskRunId);
    const locked = selectBenchmarkTaskRun(items, terminal.taskRunId);
    expect(locked).toEqual({
      selectedTaskRunId: terminal.taskRunId,
      locked: true,
    });
    expect(reconcileBenchmarkTaskRunSelection(items, locked)).toEqual(locked);
    const rail = projectBenchmarkTaskRunRail(items, locked);
    expect(rail.map((item) => item.order)).toEqual([0, 1]);
    expect(rail[0]).toMatchObject({ isSelected: true, isCurrent: false });
    expect(rail[1]).toMatchObject({ isSelected: false, isCurrent: true });
  });

  it("follows the current item after refresh and deterministically selects the final terminal item", () => {
    const first = taskRun(0, {
      lifecycle: "terminal",
      terminalReason: "completed",
      terminalAt: 8,
    });
    const second = taskRun(1, {
      lifecycle: "terminal",
      terminalReason: "failed",
      terminalAt: 9,
    });
    expect(
      reconcileBenchmarkTaskRunSelection([second, first], {
        selectedTaskRunId: first.taskRunId,
        locked: false,
      }),
    ).toEqual({
      selectedTaskRunId: second.taskRunId,
      locked: false,
    });
  });

  it("keeps the graph static, phone empty, and exposes Replay only from durable facts", () => {
    const experiment = parseBenchmarkExperimentResource(
      benchmarkExperimentFixture(),
    );
    const replayId = `benchmark-replay-${"d".repeat(32)}`;
    const selected = taskRun(0, {
      lifecycle: "terminal",
      terminalReason: "completed",
      terminalAt: 8,
      agentStatus: "success",
      benchmarkOutcome: "passed",
      outcomeAvailability: "available",
      replayAvailability: "available",
      replayId,
      links: {
        ...benchmarkTaskRunFixture(0).links,
        replay: `/studio/replays/${replayId}`,
      },
    });
    const view = projectBenchmarkTaskRunView(experiment, [selected], {
      selectedTaskRunId: selected.taskRunId,
      locked: false,
    });
    expect(view.projection?.currentActivationId).toBeNull();
    expect(view.projection?.nodesById.observe).toMatchObject({
      status: "not_observed",
      executionCount: 0,
    });
    expect(view.phoneFrame).toMatchObject({
      state: "not_captured",
      screenshotArtifactId: null,
    });
    expect(view.replayId).toBe(replayId);
  });
});
