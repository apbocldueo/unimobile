import { afterEach, describe, expect, it, vi } from "vitest";
import {
  parseBenchmarkArtifactInventoryPage,
  reportExperimentId,
  reportTaskRunId,
  type BenchmarkArtifactInventoryItem,
} from "@/entities/benchmark-report";
import {
  BENCHMARK_PUBLICATION_MANIFEST_MAX_BYTES,
} from "../model/benchmarkExport.schema";
import {
  loadBenchmarkPublicationManifest,
  prepareBenchmarkExportTarget,
} from "./benchmarkExportApi";

const MANIFEST_ID = `artifact-${"1".repeat(32)}`;
const HASH = `sha256:${"a".repeat(64)}`;

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** Build one strict Experiment-scoped manifest inventory item. */
function manifestItem(size: number): BenchmarkArtifactInventoryItem {
  return parseBenchmarkArtifactInventoryPage({
    schemaVersion: 1,
    experimentId: reportExperimentId,
    items: [
      {
        schemaVersion: 1,
        descriptor: {
          schemaVersion: 1,
          artifactId: MANIFEST_ID,
          experimentId: reportExperimentId,
          taskRunId: null,
          kind: "studio_publication_manifest",
          availability: "available",
          contentType: "application/json",
          size,
          sha256: HASH,
          provenance: "fixture",
          causalIdentity: "studio-publication-manifest.json",
          hidden: false,
        },
        links: {
          content:
            `/studio/benchmark-experiments/${reportExperimentId}/artifacts/`
            + MANIFEST_ID,
        },
      },
    ],
    hiddenCount: 0,
    nextCursor: null,
  }).items[0]!;
}

/** Build one valid encoded publication manifest. */
function encodedManifest(): Uint8Array {
  return new TextEncoder().encode(JSON.stringify({
    schemaVersion: 1,
    kind: "studio_benchmark_publication_manifest",
    experimentId: reportExperimentId,
    taskRunId: reportTaskRunId,
    members: [
      {
        reference: "experiment-report.json",
        kind: "experiment_report",
        contentType: "application/json",
        size: 1,
        sha256: HASH,
        scope: { experimentId: reportExperimentId },
        availability: "available",
        exclusionReason: "",
      },
    ],
    excludedEvidence: [
      {
        kind: "prompt",
        availability: "hidden",
        reason: "hidden_by_default_policy",
      },
    ],
  }));
}

describe("Benchmark Export API", () => {
  it("loads strict bounded manifest facts and never opens a ZIP", async () => {
    const bytes = encodedManifest();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(bytes, {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Content-Length": String(bytes.byteLength),
        },
      })),
    );
    await expect(
      loadBenchmarkPublicationManifest(
        manifestItem(bytes.byteLength),
        new Set([reportTaskRunId]),
        new AbortController().signal,
      ),
    ).resolves.toMatchObject({
      experimentId: reportExperimentId,
      taskRunId: reportTaskRunId,
      members: [{ reference: "experiment-report.json" }],
    });
  });

  it("rejects oversized manifest metadata before fetching", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      loadBenchmarkPublicationManifest(
        manifestItem(BENCHMARK_PUBLICATION_MANIFEST_MAX_BYTES + 1),
        new Set([reportTaskRunId]),
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ kind: "oversized" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("passes manifest cancellation through the short-lived loader", async () => {
    const bytes = encodedManifest();
    const controller = new AbortController();
    controller.abort();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        expect(init?.signal).toBe(controller.signal);
        throw new DOMException("aborted", "AbortError");
      }),
    );
    await expect(
      loadBenchmarkPublicationManifest(
        manifestItem(bytes.byteLength),
        new Set([reportTaskRunId]),
        controller.signal,
      ),
    ).rejects.toMatchObject({ name: "AbortError" });
  });

  it("prepares an exact readable target through HEAD", async () => {
    const item = manifestItem(42);
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init?.method).toBe("HEAD");
      return new Response(null, {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Content-Length": "42",
          "Content-Disposition": `attachment; filename="${MANIFEST_ID}"`,
        },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      prepareBenchmarkExportTarget(item, new AbortController().signal),
    ).resolves.toMatchObject({ contentLength: 42, filename: MANIFEST_ID });
  });
});
