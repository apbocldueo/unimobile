import { afterEach, describe, expect, it, vi } from "vitest";
import {
  listBenchmarkCatalog,
  validateBenchmark,
} from "@/entities/benchmark-catalog";
import { StudioApiError } from "@/shared/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Benchmark Catalog API", () => {
  it("forwards filters and AbortSignal through the shared transport", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ schemaVersion: 1, items: [], nextCursor: null }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    await listBenchmarkCatalog(
      {
        query: "fixture",
        platform: "android",
        sourceKind: "catalog",
        cursor: "opaque",
      },
      controller.signal,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("query=fixture"),
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it("projects structured validation errors without losing stable codes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            schemaVersion: 1,
            error: {
              code: "benchmark.catalog.not_found",
              message: "Benchmark Catalog entry was not found",
            },
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    await expect(
      validateBenchmark(`benchmark-entry-${"a".repeat(32)}`, "test"),
    ).rejects.toMatchObject({
      status: 404,
      code: "benchmark.catalog.not_found",
    } satisfies Partial<StudioApiError>);
  });
});
