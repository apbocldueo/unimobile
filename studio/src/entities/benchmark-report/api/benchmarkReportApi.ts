import { studioRequest, studioTextRequest } from "@/shared/api";
import {
  parseBenchmarkArtifactInventoryPage,
  parseBenchmarkExperimentReport,
  parseBenchmarkRunReport,
  type BenchmarkArtifactInventoryPage,
  type BenchmarkExperimentReport,
  type BenchmarkRunReport,
  type BenchmarkRunReportScope,
} from "../model/benchmarkReport.schema";

export const BENCHMARK_REPORT_MAX_BYTES = 2 * 1024 * 1024;

/** Load one bounded metadata-only Experiment artifact inventory page. */
export async function listBenchmarkArtifactInventory(
  experimentId: string,
  link: string,
  cursor: string | null = null,
  limit = 50,
): Promise<BenchmarkArtifactInventoryPage> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error("limit must be an integer from 1 through 100");
  }
  const expected = `/studio/benchmark-experiments/${experimentId}/artifacts`;
  const normalized = link.startsWith("/api/") ? link.slice(4) : link;
  if (normalized !== expected) {
    throw new Error("artifact inventory link conflicts with Experiment scope");
  }
  const query = new URLSearchParams({ limit: String(limit) });
  if (cursor) query.set("cursor", cursor);
  return parseBenchmarkArtifactInventoryPage(
    await studioRequest(`${link}?${query.toString()}`),
  );
}

/** Follow an explicit link and parse a bounded Core Experiment report. */
export async function getBenchmarkExperimentReport(
  experimentId: string,
  link: string,
): Promise<BenchmarkExperimentReport> {
  const expected = `/studio/benchmark-experiments/${experimentId}/report`;
  const normalized = link.startsWith("/api/") ? link.slice(4) : link;
  if (normalized !== expected) {
    throw new Error("Experiment report link conflicts with selected scope");
  }
  const text = await studioTextRequest(link, BENCHMARK_REPORT_MAX_BYTES);
  return parseBenchmarkExperimentReport(JSON.parse(text), experimentId);
}

/** Follow one inventory capability and parse a bounded Core TaskRun report. */
export async function getBenchmarkRunReport(
  scope: BenchmarkRunReportScope,
  link: string,
): Promise<BenchmarkRunReport> {
  const prefix =
    `/studio/benchmark-experiments/${scope.experimentId}/task-runs/`
    + `${scope.taskRunId}/artifacts/`;
  const normalized = link.startsWith("/api/") ? link.slice(4) : link;
  const artifactId = normalized.slice(prefix.length);
  if (
    !normalized.startsWith(prefix)
    || !/^artifact-[a-f0-9]{32}$/.test(artifactId)
  ) {
    throw new Error("TaskRun report link conflicts with selected scope");
  }
  const text = await studioTextRequest(link, BENCHMARK_REPORT_MAX_BYTES);
  return parseBenchmarkRunReport(JSON.parse(text), scope);
}
