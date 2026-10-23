import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  benchmarkTaskRunFixture,
  benchmarkExperimentFixture,
  parseBenchmarkExperimentResource,
  parseBenchmarkTaskRun,
} from "@/entities/benchmark-experiment";
import {
  benchmarkReportState,
  type BenchmarkReportRunItem,
} from "@/features/benchmark-reporting";
import { BenchmarkReportFactsInspector } from "./BenchmarkReportFactsInspector";

afterEach(cleanup);

describe("BenchmarkReportFactsInspector", () => {
  it("preserves local report failure and unavailable Replay without erasing Experiment facts", () => {
    const experiment = parseBenchmarkExperimentResource(
      benchmarkExperimentFixture(),
    );
    render(
      <BenchmarkReportFactsInspector
        experiment={experiment}
        selected={null}
        detail={null}
        state={benchmarkReportState(
          "compatibility",
          "The selected report is incompatible.",
          true,
        )}
        replayState={benchmarkReportState(
          "unavailable",
          "Native Replay is not available for this TaskRun.",
        )}
        onRetry={() => undefined}
        onOpenReplay={() => undefined}
      />,
    );
    expect(screen.getByText(experiment.experimentId)).not.toBeNull();
    expect(screen.getByText(/selected report is incompatible/)).not.toBeNull();
    expect(screen.getByText(/Native Replay is not available/)).not.toBeNull();
    expect(
      screen.queryByRole("button", { name: /Open authoritative Replay/ }),
    ).toBeNull();
  });

  it("presents the selected authoritative TaskResult provenance", () => {
    const experiment = parseBenchmarkExperimentResource(
      benchmarkExperimentFixture(),
    );
    const taskRun = parseBenchmarkTaskRun({
      ...benchmarkTaskRunFixture(),
      resultAvailability: "available",
      result: {
        evidenceOrigin: {
          schemaVersion: 1,
          acquisition: "fresh_execution",
          environment: "real_android",
          deviceProfileId: "pixel-safe",
          deviceChecks: [],
          realDeviceEvidence: true,
        },
      },
    });
    const selected = {
      taskRunId: taskRun.taskRunId,
      taskRun,
    } as BenchmarkReportRunItem;
    render(
      <BenchmarkReportFactsInspector
        experiment={experiment}
        selected={selected}
        detail={null}
        state={benchmarkReportState("available", "Available")}
        replayState={benchmarkReportState("unavailable", "Unavailable")}
        onRetry={() => undefined}
        onOpenReplay={() => undefined}
      />,
    );
    expect(screen.getByText("Fresh real-Android source")).not.toBeNull();
    expect(screen.getByText("pixel-safe")).not.toBeNull();
  });
});
