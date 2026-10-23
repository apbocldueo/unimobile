import { describe, expect, it } from "vitest";
import { parseExperimentReportRoute } from "./experimentReportRoute";

const experimentId = `experiment-${"a".repeat(32)}`;
const taskRunId = `task-run-${"b".repeat(32)}`;

describe("parseExperimentReportRoute", () => {
  it("accepts a stable Experiment and optional Studio TaskRun selection", () => {
    expect(
      parseExperimentReportRoute(experimentId, new URLSearchParams()),
    ).toEqual({
      mode: "report",
      experimentId,
      requestedTaskRunId: null,
    });
    expect(
      parseExperimentReportRoute(
        experimentId,
        new URLSearchParams({ taskRun: taskRunId }),
      ),
    ).toEqual({
      mode: "report",
      experimentId,
      requestedTaskRunId: taskRunId,
    });
  });

  it("rejects malformed and duplicate route identities", () => {
    expect(
      parseExperimentReportRoute("experiment-unsafe", new URLSearchParams()),
    ).toMatchObject({ mode: "invalid" });
    expect(
      parseExperimentReportRoute(
        experimentId,
        new URLSearchParams({ taskRun: "core-run" }),
      ),
    ).toMatchObject({ mode: "invalid" });
    expect(
      parseExperimentReportRoute(
        experimentId,
        new URLSearchParams(`taskRun=${taskRunId}&taskRun=${taskRunId}`),
      ),
    ).toMatchObject({ mode: "invalid" });
  });
});
