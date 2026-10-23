import { describe, expect, it } from "vitest";
import {
  parseBenchmarkExperimentResource,
  parseBenchmarkTaskRun,
  benchmarkDefinitionFixture,
  benchmarkExperimentFixture,
  benchmarkTaskRunFixture,
} from "@/entities/benchmark-experiment";
import {
  benchmarkExperimentReportFixture,
  benchmarkReportInventoryFixture,
  benchmarkRunReportFixture,
  parseBenchmarkArtifactInventoryPage,
  parseBenchmarkExperimentReport,
  parseBenchmarkRunReport,
  reportCoreTaskRunId,
} from "@/entities/benchmark-report";
import {
  projectBenchmarkEvaluation,
  projectBenchmarkReportRuns,
  projectBenchmarkRunDetail,
  selectBenchmarkReportRun,
} from "./benchmarkReportProjection";

/** Build one terminal Studio TaskRun matching the publisher-shaped report. */
function matchingTaskRun(overrides: Record<string, unknown> = {}) {
  const replayId = `benchmark-replay-${"d".repeat(32)}`;
  const taskInstanceIdentity =
    benchmarkRunReportFixture().identities.task_instance;
  return parseBenchmarkTaskRun({
    ...benchmarkTaskRunFixture(),
    lifecycle: "terminal",
    terminalReason: "completed",
    terminalAt: 9,
    coreTaskRunId: reportCoreTaskRunId,
    taskInstanceIdentity,
    agentStatus: "success",
    benchmarkOutcome: "pass",
    outcomeAvailability: "available",
    reportAvailability: "available",
    replayAvailability: "available",
    replayId,
    links: {
      ...benchmarkTaskRunFixture().links,
      artifacts: "/studio/artifacts",
      replay: `/studio/replays/${replayId}`,
    },
    ...overrides,
  });
}

/** Build one Experiment whose immutable hashes match the report fixture. */
function matchingExperiment(overrides: Record<string, unknown> = {}) {
  const definition = benchmarkDefinitionFixture();
  const hash = benchmarkRunReportFixture().identities.benchmark_plan;
  definition.source.benchmarkPlanIdentity = hash;
  definition.source.experimentProtocolIdentity = hash;
  definition.agentSnapshots[0]!.canonicalHash = hash;
  return parseBenchmarkExperimentResource({
    ...benchmarkExperimentFixture(),
    definition,
    lifecycle: "terminal",
    terminalReason: "completed",
    terminalAt: 9,
    reportAvailability: "available",
    capabilities: {
      ...benchmarkExperimentFixture().capabilities,
      cancelActive: false,
    },
    links: {
      ...benchmarkExperimentFixture().links,
      cancel: null,
      report: `/studio/benchmark-experiments/${
        benchmarkExperimentFixture().experimentId
      }/report`,
    },
    ...overrides,
  });
}

describe("Benchmark Report projections", () => {
  it("joins Core summaries to Studio TaskRuns and selects deterministically", () => {
    const experiment = matchingExperiment();
    const taskRun = matchingTaskRun();
    const report = parseBenchmarkExperimentReport(
      benchmarkExperimentReportFixture(),
    );
    const items = projectBenchmarkReportRuns(experiment, [taskRun], report);
    expect(items[0]).toMatchObject({
      taskRunId: taskRun.taskRunId,
      coreTaskRunId: reportCoreTaskRunId,
      integrityError: null,
      axes: {
        serviceLifecycle: "terminal",
        agentStatus: "success",
        benchmarkOutcome: "pass",
      },
    });
    expect(selectBenchmarkReportRun(items, null).selectedTaskRunId).toBe(
      taskRun.taskRunId,
    );
    expect(
      selectBenchmarkReportRun(items, `task-run-${"f".repeat(32)}`),
    ).toMatchObject({
      selectedTaskRunId: taskRun.taskRunId,
      invalidRequestedSelection: true,
    });
  });

  it("preserves report summaries when TaskRun resources are unavailable", () => {
    const items = projectBenchmarkReportRuns(
      matchingExperiment(),
      null,
      parseBenchmarkExperimentReport(benchmarkExperimentReportFixture()),
    );
    expect(items[0]).toMatchObject({
      taskRunId: null,
      axes: {
        serviceLifecycle: null,
        agentStatus: null,
        benchmarkOutcome: null,
      },
    });
  });

  it("fails closed on Experiment and run identity drift", () => {
    const report = parseBenchmarkExperimentReport(
      benchmarkExperimentReportFixture(),
    );
    const wrongExperiment = matchingExperiment();
    wrongExperiment.definition.source.benchmarkPlanIdentity =
      `sha256:${"f".repeat(64)}`;
    expect(() =>
      projectBenchmarkReportRuns(wrongExperiment, [matchingTaskRun()], report),
    ).toThrow(/immutable definition/);

    const conflicting = matchingTaskRun({ taskId: "different-task" });
    expect(
      projectBenchmarkReportRuns(
        matchingExperiment(),
        [conflicting],
        report,
      )[0]?.integrityError,
    ).toMatch(/conflicts/);
  });

  it("validates every selected TaskRun report identity and Replay scope", () => {
    const experiment = matchingExperiment();
    const taskRun = matchingTaskRun();
    const report = parseBenchmarkExperimentReport(
      benchmarkExperimentReportFixture(),
    );
    const item = projectBenchmarkReportRuns(experiment, [taskRun], report)[0]!;
    const inventory = parseBenchmarkArtifactInventoryPage(
      benchmarkReportInventoryFixture(),
    );
    const run = parseBenchmarkRunReport(benchmarkRunReportFixture());
    expect(
      projectBenchmarkRunDetail(experiment, inventory, item, run).replayId,
    ).toBe(taskRun.replayId);

    for (const field of [
      "experimentId",
      "coreTaskRunId",
      "agentId",
      "taskId",
      "repeat",
      "outcome",
    ] as const) {
      const conflict = structuredClone(run);
      if (field === "repeat") conflict.repeat += 1;
      else if (field === "outcome") conflict.outcome = "fail";
      else conflict[field] = `conflict-${field}`;
      expect(() =>
        projectBenchmarkRunDetail(experiment, inventory, item, conflict),
      ).toThrow(/immutable resource facts/);
    }
    for (const field of [
      "agentGraph",
      "benchmarkPlan",
      "experimentProtocol",
      "taskInstance",
    ] as const) {
      const conflict = structuredClone(run);
      conflict.identities[field] = `sha256:${"f".repeat(64)}`;
      expect(() =>
        projectBenchmarkRunDetail(experiment, inventory, item, conflict),
      ).toThrow(/immutable resource facts/);
    }
  });

  it("preserves tri-state Evaluation facts and rejects duplicate paths", () => {
    const run = parseBenchmarkRunReport(benchmarkRunReportFixture());
    const projection = projectBenchmarkEvaluation(run.evaluation!);
    expect(projection.orderedPaths).toEqual(["root", "root/leaf"]);
    expect(projection.root.isPass).toBeNull();
    expect(projection.root.children[0]?.isPass).toBe(true);
    expect(projection.defaultExpandedPaths).toContain("root");

    const duplicate = structuredClone(run.evaluation!);
    duplicate.children[0]!.path = duplicate.path;
    expect(() => projectBenchmarkEvaluation(duplicate)).toThrow(
      /duplicate node paths/,
    );
  });
});
