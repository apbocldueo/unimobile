import { describe, expect, it } from "vitest";
import {
  benchmarkExperimentFixture,
  parseBenchmarkExperimentResource,
} from "@/entities/benchmark-experiment";
import { StudioApiError } from "@/shared/api";
import {
  classifyBenchmarkReportError,
  classifyExperimentPublication,
} from "./benchmarkReportState";

/** Build one valid Experiment with an explicit lifecycle/publication state. */
function experiment(
  lifecycle: "accepted" | "terminal",
  reportAvailability: "pending" | "not_produced" | "available" | "failed",
  reportLink: string | null,
) {
  const fixture = benchmarkExperimentFixture();
  return parseBenchmarkExperimentResource({
    ...fixture,
    lifecycle,
    terminalReason: lifecycle === "terminal" ? "completed" : null,
    terminalAt: lifecycle === "terminal" ? 9 : null,
    reportAvailability,
    capabilities: {
      ...fixture.capabilities,
      cancelActive: lifecycle !== "terminal",
    },
    links: {
      ...fixture.links,
      cancel: lifecycle === "terminal" ? null : fixture.links.cancel,
      report: reportLink,
    },
  });
}

describe("Benchmark Report state classification", () => {
  it("keeps non-terminal, pending, not-produced, failed, and integrity states explicit", () => {
    expect(
      classifyExperimentPublication(
        experiment("accepted", "pending", null),
        "pending",
        null,
      ).kind,
    ).toBe("non_terminal");
    for (const availability of [
      "pending",
      "not_produced",
      "failed",
    ] as const) {
      expect(
        classifyExperimentPublication(
          experiment("terminal", availability, null),
          availability,
          null,
        ).kind,
      ).toBe(availability);
    }
    expect(
      classifyExperimentPublication(
        experiment("terminal", "available", null),
        "available",
        null,
      ).kind,
    ).toBe("integrity");
  });

  it("maps transport closure without leaking raw response details", () => {
    expect(
      classifyBenchmarkReportError(
        new StudioApiError(404, {
          error: { code: "benchmark.artifact.missing", message: "/secret" },
        }),
        "Evidence is missing.",
      ),
    ).toMatchObject({ kind: "missing", message: "Evidence is missing." });
    expect(
      classifyBenchmarkReportError(
        new StudioApiError(409, {
          error: { code: "benchmark.artifact.corrupt", message: "/secret" },
        }),
        "Evidence is missing.",
      ).kind,
    ).toBe("corrupt");
    expect(
      classifyBenchmarkReportError(
        new Error("raw parser payload"),
        "Evidence is missing.",
      ).message,
    ).not.toContain("raw parser payload");
  });
});
