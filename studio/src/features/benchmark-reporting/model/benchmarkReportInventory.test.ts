import { describe, expect, it } from "vitest";
import {
  benchmarkReportInventoryFixture,
  parseBenchmarkArtifactInventoryPage,
  reportExperimentId,
  type BenchmarkArtifactInventoryPage,
} from "@/entities/benchmark-report";
import {
  BENCHMARK_REPORT_INVENTORY_LIMIT,
  collectBenchmarkReportInventory,
} from "./benchmarkReportInventory";

/** Build one valid inventory page with deterministic artifact identities. */
function page(
  start: number,
  count: number,
  nextCursor: string | null,
): BenchmarkArtifactInventoryPage {
  const fixture = benchmarkReportInventoryFixture();
  return parseBenchmarkArtifactInventoryPage({
    ...fixture,
    items: Array.from({ length: count }, (_, offset) => {
      const sequence = start + offset;
      const item = structuredClone(fixture.items[0]!);
      item.descriptor.artifactId =
        `artifact-${sequence.toString(16).padStart(32, "0")}`;
      item.links.content =
        `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
        + `${item.descriptor.taskRunId}/artifacts/`
        + `${item.descriptor.artifactId}`;
      return item;
    }),
    nextCursor,
  });
}

describe("collectBenchmarkReportInventory", () => {
  it("follows opaque cursors and returns one stable bounded inventory", async () => {
    const cursors: Array<string | null> = [];
    const inventory = await collectBenchmarkReportInventory(
      reportExperimentId,
      async (cursor) => {
        cursors.push(cursor);
        return cursor === null
          ? page(1, 2, "opaque-next")
          : page(3, 1, null);
      },
    );
    expect(cursors).toEqual([null, "opaque-next"]);
    expect(inventory.items).toHaveLength(3);
    expect(inventory.nextCursor).toBeNull();
  });

  it("rejects repeated cursors, cross-page disorder, and oversized inventories", async () => {
    await expect(
      collectBenchmarkReportInventory(
        reportExperimentId,
        async () => page(1, 0, "same"),
      ),
    ).rejects.toThrow(/cursor/);

    let disorderCalls = 0;
    await expect(
      collectBenchmarkReportInventory(
        reportExperimentId,
        async () => {
          disorderCalls += 1;
          return disorderCalls === 1
            ? page(2, 1, "next")
            : page(1, 1, null);
        },
      ),
    ).rejects.toThrow(/order/);

    let remaining = BENCHMARK_REPORT_INVENTORY_LIMIT + 1;
    await expect(
      collectBenchmarkReportInventory(
        reportExperimentId,
        async (cursor) => {
          const count = Math.min(100, remaining);
          const start = BENCHMARK_REPORT_INVENTORY_LIMIT + 2 - remaining;
          remaining -= count;
          return page(
            start,
            count,
            remaining > 0 ? `cursor-${cursor ?? "first"}-${start}` : null,
          );
        },
      ),
    ).rejects.toThrow(/member limit/);
  });
});
