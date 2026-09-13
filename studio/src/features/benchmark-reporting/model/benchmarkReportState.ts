import type {
  BenchmarkAvailability,
  BenchmarkExperimentResource,
} from "@/entities/benchmark-experiment";
import { StudioApiError } from "@/shared/api";

export type BenchmarkReportStateKind =
  | "idle"
  | "loading"
  | "available"
  | "not_found"
  | "non_terminal"
  | "pending"
  | "not_produced"
  | "failed"
  | "missing"
  | "corrupt"
  | "compatibility"
  | "integrity"
  | "unavailable";

export type BenchmarkReportComponentState = {
  kind: BenchmarkReportStateKind;
  message: string;
  retryable: boolean;
};

/** Build one display-safe component state without exposing raw responses. */
export function benchmarkReportState(
  kind: BenchmarkReportStateKind,
  message: string,
  retryable = false,
): BenchmarkReportComponentState {
  return { kind, message, retryable };
}

/** Classify a bounded report request failure into a safe local state. */
export function classifyBenchmarkReportError(
  error: unknown,
  missingMessage: string,
): BenchmarkReportComponentState {
  if (error instanceof StudioApiError) {
    if (error.code.includes("corrupt") || error.status === 409) {
      return benchmarkReportState(
        "corrupt",
        "Published evidence failed its integrity check.",
        true,
      );
    }
    if (error.code.includes("missing") || error.status === 404) {
      return benchmarkReportState("missing", missingMessage, true);
    }
    return benchmarkReportState(
      "failed",
      "The report resource could not be loaded.",
      true,
    );
  }
  return benchmarkReportState(
    "compatibility",
    "The published report is not compatible with this Studio version.",
    true,
  );
}

/** Classify the Experiment publication gate before following report links. */
export function classifyExperimentPublication(
  experiment: BenchmarkExperimentResource,
  availability: BenchmarkAvailability,
  link: string | null,
): BenchmarkReportComponentState {
  if (experiment.lifecycle !== "terminal") {
    return benchmarkReportState(
      "non_terminal",
      `Experiment is ${experiment.lifecycle}; no committed report is assumed.`,
    );
  }
  if (availability === "pending") {
    return benchmarkReportState(
      "pending",
      "Report publication is still pending.",
      true,
    );
  }
  if (availability === "not_produced") {
    return benchmarkReportState(
      "not_produced",
      "This Experiment did not produce a report.",
    );
  }
  if (availability === "failed") {
    return benchmarkReportState(
      "failed",
      "Report publication failed.",
      true,
    );
  }
  if (link === null) {
    return benchmarkReportState(
      "integrity",
      "Report availability has no matching scoped capability.",
      true,
    );
  }
  return benchmarkReportState("loading", "Loading the published report…");
}
