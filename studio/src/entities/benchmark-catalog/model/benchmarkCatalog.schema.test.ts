import { describe, expect, it } from "vitest";
import {
  benchmarkCatalogKeys,
  parseBenchmarkCatalogPage,
  parseDeviceProfilePage,
} from "@/entities/benchmark-catalog";

/** Build one backend-shaped Catalog item. */
function catalogItem() {
  return {
    catalogEntryId: `benchmark-entry-${"a".repeat(32)}`,
    packageIdentity: "tests/fixture@1.0.0",
    title: "Fixture Benchmark",
    version: "1.0.0",
    sourceKind: "catalog",
    platforms: ["android"],
    splits: [{ name: "test", taskCount: 1 }],
    availability: "available",
    warnings: [],
  };
}

describe("Benchmark Catalog browser contracts", () => {
  it("parses strict pages and keeps filters in query-cache identity", () => {
    const page = parseBenchmarkCatalogPage({
      schemaVersion: 1,
      items: [catalogItem()],
      nextCursor: "opaque",
    });
    expect(page.items[0]?.packageIdentity).toBe("tests/fixture@1.0.0");
    expect(
      benchmarkCatalogKeys.list({ query: "fixture", platform: "android" }),
    ).not.toEqual(
      benchmarkCatalogKeys.list({ query: "fixture", platform: "harmonyos" }),
    );
  });

  it("rejects unknown fields and unsafe device-profile expansions", () => {
    expect(() =>
      parseBenchmarkCatalogPage({
        schemaVersion: 1,
        items: [{ ...catalogItem(), hostPath: "/private/fixture" }],
      }),
    ).toThrow(/hostPath/);
    expect(() =>
      parseDeviceProfilePage({
        schemaVersion: 1,
        items: [
          {
            deviceProfileId: "local-android",
            label: "Local Android",
            platform: "android",
            availability: "configured",
            serial: "emulator-5554",
          },
        ],
      }),
    ).toThrow(/serial/);
  });
});
