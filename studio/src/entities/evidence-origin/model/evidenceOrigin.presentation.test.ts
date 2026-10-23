import { describe, expect, it } from "vitest";
import { classifyEvidenceOrigin } from "./evidenceOrigin.presentation";
import type { ExecutionEvidenceOrigin } from "./evidenceOrigin.schema";

/** Build one parsed-origin-shaped fixture with explicit independent axes. */
function origin(
  overrides: Partial<ExecutionEvidenceOrigin> = {},
): ExecutionEvidenceOrigin {
  return {
    schemaVersion: 1,
    acquisition: "fresh_execution",
    environment: "unverified",
    deviceProfileId: null,
    deviceChecks: [],
    realDeviceEvidence: false,
    ...overrides,
  };
}

describe("classifyEvidenceOrigin", () => {
  it.each([
    [
      "fresh-real-source",
      origin({
        acquisition: "fresh_execution",
        environment: "real_android",
        realDeviceEvidence: true,
      }),
    ],
    [
      "historical-real-source",
      origin({
        acquisition: "replay_projection",
        environment: "real_android",
      }),
    ],
    [
      "fake-fixture",
      origin({
        acquisition: "contract_fixture",
        environment: "fake_device",
      }),
    ],
    ["unverified", origin()],
  ] as const)("classifies %s without changing source facts", (kind, value) => {
    const result = classifyEvidenceOrigin(value);
    expect(result.kind).toBe(kind);
    expect(result.origin).toBe(value);
  });

  it("does not upgrade a real-looking profile or device check", () => {
    const result = classifyEvidenceOrigin(origin({
      acquisition: "imported_excerpt",
      environment: "real_android",
      deviceProfileId: "real-android-production",
      deviceChecks: [{ name: "platform", passed: true, observed: "android" }],
    }));
    expect(result.kind).toBe("unverified");
    expect(result.origin.realDeviceEvidence).toBe(false);
  });
});
