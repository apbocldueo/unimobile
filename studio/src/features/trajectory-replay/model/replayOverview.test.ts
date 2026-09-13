import { describe, expect, it } from "vitest";
import {
  createHistoricalAndroidReplayFixture,
  createReplayEnvelopeFixture,
} from "@/entities/replay";
import { projectReplay } from "./replayProjection";
import { selectReplayOverview } from "./replayOverview";

describe("selectReplayOverview", () => {
  it("keeps Agent success and Benchmark failure independent", () => {
    const envelope = createReplayEnvelopeFixture();
    const overview = selectReplayOverview(envelope, projectReplay(envelope));
    expect(overview.agentStatus).toBe("success");
    expect(overview.benchmarkOutcome).toBe("fail");
    expect(overview.failureTarget?.kind).toBe("benchmark_evaluation");
    expect(overview.location).toBe("Benchmark evaluation");
    expect(overview.reason).toBe("目标状态未满足");
    expect(overview.reasonSource).toBe("benchmark_phase");
  });

  it("selects a formal activation failure before terminal fallback", () => {
    const base = createReplayEnvelopeFixture();
    const envelope = createReplayEnvelopeFixture({
      benchmark: null,
      result: { ...base.result, status: "failure", error: "动作执行失败" },
      moments: [
        base.moments[0]!,
        {
          ...base.moments[1]!,
          momentId: "reason-fail",
          kind: "failure",
          payload: { error: "动作执行失败" },
        },
      ],
    });
    const overview = selectReplayOverview(envelope, projectReplay(envelope));
    expect(overview.benchmarkOutcome).toBeNull();
    expect(overview.failureTarget?.kind).toBe("activation");
    expect(overview.location).toBe("reason");
    expect(overview.reason).toBe("动作执行失败");
  });

  it("summarizes an Agent-only limited-evidence run", () => {
    const base = createReplayEnvelopeFixture();
    const envelope = createReplayEnvelopeFixture({
      benchmark: null,
      snapshot: { ...base.snapshot, graphStatus: "not_captured", agentGraph: null },
      availability: {
        ...base.availability,
        screenshots: { state: "not_captured", reasonCode: "", detail: "" },
      },
    });
    const overview = selectReplayOverview(envelope, projectReplay(envelope));
    expect(overview.benchmarkOutcome).toBeNull();
    expect(overview.evidence.kind).toBe("fake-fixture");
    expect(overview.evidence.graphState).toBe("not_captured");
    expect(overview.evidence.screenshotState).toBe("not_captured");
  });

  it("labels historical real-Android projection without calling it fresh", () => {
    const envelope = createHistoricalAndroidReplayFixture();
    const overview = selectReplayOverview(envelope, projectReplay(envelope));
    expect(overview.evidence.kind).toBe("historical-real-source");
    expect(overview.evidence.label).toBe("真实 Android 历史回放");
    expect(overview.evidence.realDeviceEvidence).toBe(false);
  });
});
