import {
  type BenchmarkArtifactInventoryPage,
  type BenchmarkArtifactInventoryItem,
} from "@/entities/benchmark-report";

export const BENCHMARK_REPORT_INVENTORY_LIMIT = 2_000;
export const BENCHMARK_REPORT_INVENTORY_PAGE_SIZE = 100;

export type BenchmarkInventoryPageLoader = (
  cursor: string | null,
  limit: number,
) => Promise<BenchmarkArtifactInventoryPage>;

/** Follow bounded opaque inventory cursors and reject unstable page closure. */
export async function collectBenchmarkReportInventory(
  experimentId: string,
  loadPage: BenchmarkInventoryPageLoader,
): Promise<BenchmarkArtifactInventoryPage> {
  const items: BenchmarkArtifactInventoryItem[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | null = null;
  let hiddenCount: number | null = null;
  let previousArtifactId: string | null = null;

  do {
    if (cursor !== null) {
      if (seenCursors.has(cursor)) {
        throw new Error("Artifact inventory cursor did not advance");
      }
      seenCursors.add(cursor);
    }
    const page = await loadPage(cursor, BENCHMARK_REPORT_INVENTORY_PAGE_SIZE);
    if (page.experimentId !== experimentId) {
      throw new Error("Artifact inventory crossed Experiment scope");
    }
    if (hiddenCount !== null && page.hiddenCount !== hiddenCount) {
      throw new Error("Artifact inventory hidden count changed across pages");
    }
    hiddenCount ??= page.hiddenCount;
    for (const item of page.items) {
      const artifactId = item.descriptor.artifactId;
      if (previousArtifactId !== null && artifactId <= previousArtifactId) {
        throw new Error("Artifact inventory order changed across pages");
      }
      items.push(item);
      previousArtifactId = artifactId;
      if (items.length > BENCHMARK_REPORT_INVENTORY_LIMIT) {
        throw new Error("Artifact inventory exceeds the report member limit");
      }
    }
    cursor = page.nextCursor;
  } while (cursor !== null);

  return {
    schemaVersion: 1,
    experimentId,
    items,
    hiddenCount: hiddenCount ?? 0,
    nextCursor: null,
  };
}
