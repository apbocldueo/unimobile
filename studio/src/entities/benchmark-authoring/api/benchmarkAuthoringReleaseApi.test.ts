import { afterEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkArchiveFixture,
  benchmarkPackageExportFixture,
  benchmarkPackageRevisionFixtureId,
} from "../testing/benchmarkAuthoringRelease.fixtures";
import { benchmarkDraftFixtureId } from "../testing/benchmarkAuthoring.fixtures";
import {
  handoffBenchmarkPackageDownload,
  prepareBenchmarkPackageDownload,
} from "./benchmarkAuthoringReleaseApi";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Benchmark Package export browser boundary", () => {
  it("requires exact MIME, length, filename, and digest during HEAD", async () => {
    const packageExport = benchmarkPackageExportFixture();
    vi.stubGlobal("fetch", vi.fn(async (_request: string, init?: RequestInit) => {
      expect(init?.method).toBe("HEAD");
      return new Response(null, {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Length": String(packageExport.size),
          "Content-Disposition": `attachment; filename="${packageExport.filename}"`,
          "X-Content-SHA256": benchmarkArchiveFixture,
        },
      });
    }));
    await expect(prepareBenchmarkPackageDownload(packageExport)).resolves.toEqual({
      contentType: "application/zip",
      contentLength: packageExport.size,
      filename: packageExport.filename,
      sha256: packageExport.sha256,
    });
  });

  it("fails closed on digest drift and hands only parsed capabilities to an anchor", async () => {
    const packageExport = benchmarkPackageExportFixture();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, {
      status: 200,
      headers: {
        "Content-Type": "application/zip",
        "Content-Length": String(packageExport.size),
        "Content-Disposition": `attachment; filename="${packageExport.filename}"`,
        "X-Content-SHA256": `sha256:${"0".repeat(64)}`,
      },
    })));
    await expect(prepareBenchmarkPackageDownload(packageExport)).rejects.toMatchObject({
      kind: "digest-mismatch",
    });

    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    handoffBenchmarkPackageDownload(packageExport);
    expect(click).toHaveBeenCalledOnce();
    expect(packageExport.contentLink).toContain(benchmarkDraftFixtureId);
    expect(packageExport.contentLink).toContain(benchmarkPackageRevisionFixtureId);
    expect(() => handoffBenchmarkPackageDownload({
      ...packageExport,
      contentLink: "https://attacker.example/package.zip",
    })).toThrow();
  });
});
