import { describe, expect, it } from "vitest";
import {
  parseBenchmarkArtifactInventoryPage,
  reportExperimentId,
  reportTaskRunId,
  type BenchmarkArtifactInventoryItem,
  type BenchmarkArtifactInventoryPage,
} from "@/entities/benchmark-report";
import {
  benchmarkExportTargetKey,
  projectBenchmarkExportMaterials,
} from "./benchmarkExportMaterials";

const HASH = `sha256:${"d".repeat(64)}`;

/** Build one visible strict inventory item for Export projection tests. */
function item(
  ordinal: number,
  kind: string,
  taskRunId: string | null,
  availability = "available",
): BenchmarkArtifactInventoryItem {
  const artifactId = `artifact-${ordinal.toString(16).padStart(32, "0")}`;
  const content = taskRunId === null
    ? `/studio/benchmark-experiments/${reportExperimentId}/artifacts/${artifactId}`
    : `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
      + `${taskRunId}/artifacts/${artifactId}`;
  return {
    schemaVersion: 1,
    descriptor: {
      schemaVersion: 1,
      artifactId,
      experimentId: reportExperimentId,
      taskRunId,
      kind,
      availability: availability as "available",
      contentType: availability === "available" ? "application/json" : "",
      size: availability === "available" ? ordinal : 0,
      sha256: availability === "available" ? HASH : null,
      provenance: "fixture",
      causalIdentity: `member-${ordinal}.json`,
      hidden: false,
    },
    links: { content: availability === "available" ? content : null },
  };
}

/** Parse a closed strict inventory from deterministic items. */
function inventory(
  items: BenchmarkArtifactInventoryItem[],
): BenchmarkArtifactInventoryPage {
  return parseBenchmarkArtifactInventoryPage({
    schemaVersion: 1,
    experimentId: reportExperimentId,
    items,
    hiddenCount: 2,
    nextCursor: null,
  });
}

describe("projectBenchmarkExportMaterials", () => {
  it("projects independent singletons, TaskRun material, evidence, and hidden facts", () => {
    const report = item(1, "experiment_report", null);
    const bundle = {
      ...item(2, "experiment_bundle", null),
      descriptor: {
        ...item(2, "experiment_bundle", null).descriptor,
        contentType: "application/zip",
      },
    };
    const manifest = item(3, "studio_publication_manifest", null);
    const taskReport = item(4, "task_report", reportTaskRunId);
    const trajectory = item(5, "task_trajectory", reportTaskRunId);
    const evidence = item(6, "model_response", reportTaskRunId);
    const missing = item(7, "screenshot", reportTaskRunId, "missing");
    const projection = projectBenchmarkExportMaterials(
      reportExperimentId,
      inventory([
        report,
        bundle,
        manifest,
        taskReport,
        trajectory,
        evidence,
        missing,
      ]),
    );
    expect(projection.experimentReport?.item.descriptor.artifactId).toBe(
      report.descriptor.artifactId,
    );
    expect(projection.experimentBundle?.category).toBe("experiment-bundle");
    expect(projection.publicationManifest?.category).toBe(
      "publication-manifest",
    );
    expect(projection.taskMaterials.get(reportTaskRunId)).toHaveLength(2);
    expect(projection.otherEvidence).toHaveLength(1);
    expect(projection.unavailable).toHaveLength(1);
    expect(projection.hiddenCount).toBe(2);
    expect(benchmarkExportTargetKey(report)).toContain(report.descriptor.sha256!);
  });

  it("fails closed for incomplete, cross-scope, duplicate, and invalid ownership", () => {
    const report = item(1, "experiment_report", null);
    expect(() =>
      projectBenchmarkExportMaterials(reportExperimentId, {
        ...inventory([report]),
        nextCursor: "more",
      })
    ).toThrow(/closed/);
    expect(() =>
      projectBenchmarkExportMaterials(
        `experiment-${"f".repeat(32)}`,
        inventory([report]),
      )
    ).toThrow(/closed/);
    expect(() =>
      projectBenchmarkExportMaterials(
        reportExperimentId,
        inventory([report, item(2, "experiment_report", null)]),
      )
    ).toThrow(/Duplicate Experiment report/);
    expect(() =>
      projectBenchmarkExportMaterials(
        reportExperimentId,
        inventory([item(1, "task_trajectory", null)]),
      )
    ).toThrow(/TaskRun export material/);
  });

  it("retains persisted partial availability without inventing a capability", () => {
    const corrupt = item(1, "experiment_bundle", null, "corrupt");
    const projection = projectBenchmarkExportMaterials(
      reportExperimentId,
      inventory([corrupt]),
    );
    expect(projection.experimentBundle).toBeNull();
    expect(projection.unavailable[0]?.item.links.content).toBeNull();
    expect(projection.unavailable[0]?.item.descriptor.availability).toBe(
      "corrupt",
    );
  });
});
