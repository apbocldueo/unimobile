import {
  parseBenchmarkArtifactInventoryItem,
  type BenchmarkArtifactInventoryItem,
  type BenchmarkArtifactInventoryPage,
} from "@/entities/benchmark-report";

export const BENCHMARK_EXPORT_MAX_MATERIALS = 2000;

export type BenchmarkExportMaterialCategory =
  | "experiment-report"
  | "experiment-bundle"
  | "publication-manifest"
  | "task-report"
  | "task-trajectory"
  | "other-evidence";

export type BenchmarkExportMaterial = {
  key: string;
  category: BenchmarkExportMaterialCategory;
  item: BenchmarkArtifactInventoryItem;
};

export type BenchmarkExportMaterialProjection = {
  experimentId: string;
  experimentReport: BenchmarkExportMaterial | null;
  experimentBundle: BenchmarkExportMaterial | null;
  publicationManifest: BenchmarkExportMaterial | null;
  taskMaterials: Map<string, BenchmarkExportMaterial[]>;
  otherEvidence: BenchmarkExportMaterial[];
  unavailable: BenchmarkExportMaterial[];
  hiddenCount: number;
};

const SINGLETON_CATEGORIES = new Map<string, BenchmarkExportMaterialCategory>([
  ["experiment_report", "experiment-report"],
  ["experiment_bundle", "experiment-bundle"],
  ["studio_publication_manifest", "publication-manifest"],
]);
const TASK_CATEGORIES = new Map<string, BenchmarkExportMaterialCategory>([
  ["task_report", "task-report"],
  ["task_trajectory", "task-trajectory"],
]);
const READABLE = new Set(["available", "redacted", "truncated"]);

/** Build one stable target key from immutable descriptor and capability facts. */
export function benchmarkExportTargetKey(
  item: BenchmarkArtifactInventoryItem,
): string {
  const descriptor = item.descriptor;
  return [
    descriptor.experimentId,
    descriptor.taskRunId ?? "-",
    descriptor.artifactId,
    descriptor.sha256 ?? "-",
    String(descriptor.size),
    item.links.content ?? "-",
  ].join("|");
}

/** Project a complete authoritative inventory into fail-closed export materials.
 *
 * Args:
 *   experimentId: Current durable Experiment identity.
 *   inventory: Fully collected and strictly parsed artifact inventory.
 *
 * Raises:
 *   Error: Inventory is incomplete, cross-scope, duplicated, or structurally
 *     incompatible with singleton and TaskRun publication ownership.
 *
 * Returns:
 *   Independently available Experiment, TaskRun, and evidence materials.
 */
export function projectBenchmarkExportMaterials(
  experimentId: string,
  inventory: BenchmarkArtifactInventoryPage,
): BenchmarkExportMaterialProjection {
  if (
    inventory.experimentId !== experimentId
    || inventory.nextCursor !== null
    || inventory.items.length > BENCHMARK_EXPORT_MAX_MATERIALS
  ) {
    throw new Error("Benchmark export inventory is not fully closed");
  }
  const seenIds = new Set<string>();
  const taskMaterials = new Map<string, BenchmarkExportMaterial[]>();
  const otherEvidence: BenchmarkExportMaterial[] = [];
  const unavailable: BenchmarkExportMaterial[] = [];
  let experimentReport: BenchmarkExportMaterial | null = null;
  let experimentBundle: BenchmarkExportMaterial | null = null;
  let publicationManifest: BenchmarkExportMaterial | null = null;

  for (const raw of inventory.items) {
    const item = parseBenchmarkArtifactInventoryItem(
      raw,
      experimentId,
      "exportMaterial",
    );
    if (seenIds.has(item.descriptor.artifactId)) {
      throw new Error("Benchmark export inventory has duplicate artifacts");
    }
    seenIds.add(item.descriptor.artifactId);
    const singletonCategory = SINGLETON_CATEGORIES.get(item.descriptor.kind);
    const taskCategory = TASK_CATEGORIES.get(item.descriptor.kind);
    let category: BenchmarkExportMaterialCategory =
      singletonCategory ?? taskCategory ?? "other-evidence";
    if (singletonCategory && item.descriptor.taskRunId !== null) {
      throw new Error("Experiment export singleton has TaskRun scope");
    }
    if (taskCategory && item.descriptor.taskRunId === null) {
      throw new Error("TaskRun export material has Experiment scope");
    }
    const material: BenchmarkExportMaterial = {
      key: benchmarkExportTargetKey(item),
      category,
      item,
    };
    if (!READABLE.has(item.descriptor.availability)) {
      unavailable.push(material);
      continue;
    }
    if (singletonCategory) {
      if (singletonCategory === "experiment-report") {
        if (experimentReport) throw new Error("Duplicate Experiment report");
        experimentReport = material;
      } else if (singletonCategory === "experiment-bundle") {
        if (experimentBundle) throw new Error("Duplicate Experiment bundle");
        experimentBundle = material;
      } else {
        if (publicationManifest) {
          throw new Error("Duplicate publication manifest");
        }
        publicationManifest = material;
      }
      continue;
    }
    if (taskCategory) {
      const taskRunId = item.descriptor.taskRunId!;
      const existing = taskMaterials.get(taskRunId) ?? [];
      existing.push(material);
      taskMaterials.set(taskRunId, existing);
      continue;
    }
    category = "other-evidence";
    otherEvidence.push({ ...material, category });
  }

  return {
    experimentId,
    experimentReport,
    experimentBundle,
    publicationManifest,
    taskMaterials,
    otherEvidence,
    unavailable,
    hiddenCount: inventory.hiddenCount,
  };
}
