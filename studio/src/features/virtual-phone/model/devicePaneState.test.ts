import { describe, expect, it } from "vitest";
import { selectDevicePaneState } from "./devicePaneState";

describe("selectDevicePaneState", () => {
  it("never infers offline from absent screenshot evidence", () => {
    expect(selectDevicePaneState({
      hasRun: false,
      readinessReady: true,
      frameState: "not_captured",
      hasObservation: false,
    }).kind).toBe("not_started");
    expect(selectDevicePaneState({
      hasRun: true,
      lifecycle: "terminal",
      frameState: "not_captured",
      hasObservation: false,
    }).kind).toBe("early_failure");
    expect(selectDevicePaneState({
      hasRun: true,
      lifecycle: "running",
      frameState: "not_captured",
      hasObservation: false,
    }).kind).toBe("waiting");
  });

  it("keeps stale, artifact, and authoritative device failures distinct", () => {
    expect(selectDevicePaneState({
      hasRun: true,
      lifecycle: "running",
      frameState: "stale",
      hasObservation: true,
    }).kind).toBe("stale");
    expect(selectDevicePaneState({
      hasRun: true,
      lifecycle: "terminal",
      frameState: "missing",
      hasObservation: true,
    }).kind).toBe("artifact_missing");
    expect(selectDevicePaneState({
      hasRun: true,
      lifecycle: "terminal",
      errorCode: "studio.device.target_offline",
      frameState: "not_captured",
      hasObservation: false,
    }).kind).toBe("offline");
    expect(selectDevicePaneState({
      hasRun: true,
      lifecycle: "terminal",
      errorCode: "studio.device.target_unauthorized",
      frameState: "not_captured",
      hasObservation: false,
    }).kind).toBe("unauthorized");
  });
});
