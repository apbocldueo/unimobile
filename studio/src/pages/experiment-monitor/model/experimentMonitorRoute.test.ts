import { describe, expect, it } from "vitest";
import { parseExperimentMonitorRoute } from "./experimentMonitorRoute";

describe("parseExperimentMonitorRoute", () => {
  it("accepts only a stable Benchmark Experiment identity", () => {
    const experimentId = `experiment-${"a".repeat(32)}`;
    expect(parseExperimentMonitorRoute(experimentId)).toEqual({
      mode: "monitor",
      experimentId,
    });
    expect(parseExperimentMonitorRoute("experiment-unsafe")).toMatchObject({
      mode: "invalid",
    });
    expect(parseExperimentMonitorRoute(undefined)).toMatchObject({
      mode: "invalid",
    });
  });
});
