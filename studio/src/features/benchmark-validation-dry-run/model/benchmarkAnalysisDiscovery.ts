import type { BenchmarkAuthoringDocument } from "@/entities/benchmark-authoring";
import { isRecord } from "@/shared/lib";

const SPLIT = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;

/**
 * Discover bounded split suggestions without asserting manifest validity.
 *
 * Args:
 *   document: Current authoring document used only for best-effort suggestions.
 *
 * Returns:
 *   Sorted safe split names; malformed or open data is omitted.
 */
export function discoverBenchmarkSplits(
  document: BenchmarkAuthoringDocument,
): string[] {
  const splits = document.manifest.document.splits;
  if (!isRecord(splits)) return [];
  return Object.keys(splits).filter((item) => SPLIT.test(item)).sort();
}

/**
 * Discover stable task IDs declared by one best-effort split file list.
 *
 * Args:
 *   document: Current authoring document.
 *   split: Explicit split whose referenced task members should be inspected.
 *
 * Returns:
 *   Unique bounded task IDs in document order; Core validation remains
 *   authoritative for malformed or missing membership.
 */
export function discoverBenchmarkTaskIds(
  document: BenchmarkAuthoringDocument,
  split: string,
): string[] {
  const splits = document.manifest.document.splits;
  if (!isRecord(splits) || !isRecord(splits[split])) return [];
  const files = splits[split].files;
  if (!Array.isArray(files)) return [];
  const selectedFiles = new Set(
    files.filter((item): item is string => typeof item === "string"),
  );
  const discovered: string[] = [];
  const seen = new Set<string>();
  for (const file of document.taskFiles) {
    if (!selectedFiles.has(file.path)) continue;
    for (const task of file.tasks) {
      if (!isRecord(task) || typeof task.id !== "string") continue;
      const id = task.id;
      if (id.length === 0 || id.length > 256 || seen.has(id)) continue;
      seen.add(id);
      discovered.push(id);
    }
  }
  return discovered;
}
