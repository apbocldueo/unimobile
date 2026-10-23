import { queryOptions } from "@tanstack/react-query";
import type { BenchmarkRunReportScope } from "../model/benchmarkReport.schema";
import {
  getBenchmarkExperimentReport,
  getBenchmarkRunReport,
  listBenchmarkArtifactInventory,
} from "./benchmarkReportApi";

export const benchmarkReportKeys = {
  all: ["studio", "benchmark-reports"] as const,
  inventory: (
    experimentId: string,
    link: string,
    limit: number,
    cursor: string | null,
  ) => [
    "studio",
    "benchmark-report",
    experimentId,
    "inventory",
    link,
    limit,
    cursor,
  ] as const,
  experiment: (experimentId: string, link: string) =>
    ["studio", "benchmark-report", experimentId, "experiment", link] as const,
  run: (scope: BenchmarkRunReportScope, link: string) => [
    "studio",
    "benchmark-report",
    scope.experimentId,
    scope.taskRunId,
    scope.coreTaskRunId,
    scope.taskId,
    scope.agentId,
    scope.repeat,
    "run",
    link,
  ] as const,
};

/** Build a reconstructible artifact inventory query configuration. */
export function benchmarkArtifactInventoryQueryOptions(
  experimentId: string,
  link: string,
  limit = 50,
  cursor: string | null = null,
) {
  return queryOptions({
    queryKey: benchmarkReportKeys.inventory(
      experimentId,
      link,
      limit,
      cursor,
    ),
    queryFn: () =>
      listBenchmarkArtifactInventory(experimentId, link, cursor, limit),
    enabled: experimentId.length > 0 && link.length > 0,
  });
}

/** Build a bounded immutable Experiment report query configuration. */
export function benchmarkExperimentReportQueryOptions(
  experimentId: string,
  link: string,
) {
  return queryOptions({
    queryKey: benchmarkReportKeys.experiment(experimentId, link),
    queryFn: () => getBenchmarkExperimentReport(experimentId, link),
    enabled: experimentId.length > 0 && link.length > 0,
  });
}

/** Build a bounded immutable TaskRun report query configuration. */
export function benchmarkRunReportQueryOptions(
  scope: BenchmarkRunReportScope,
  link: string,
) {
  return queryOptions({
    queryKey: benchmarkReportKeys.run(scope, link),
    queryFn: () => getBenchmarkRunReport(scope, link),
    enabled: scope.experimentId.length > 0
      && scope.taskRunId.length > 0
      && link.length > 0,
  });
}
