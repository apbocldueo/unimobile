import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  parseBenchmarkArtifactInventoryPage,
  reportExperimentId,
  reportTaskRunId,
  type BenchmarkArtifactInventoryItem,
  type BenchmarkArtifactInventoryPage,
} from "@/entities/benchmark-report";
import type {
  BenchmarkExperimentResource,
  BenchmarkTaskRun,
} from "@/entities/benchmark-experiment";
import {
  projectBenchmarkExportMaterials,
  type BenchmarkExportMaterial,
} from "./benchmarkExportMaterials";
import type {
  BenchmarkExportMetadataSnapshot,
} from "./useBenchmarkExperimentReport";
import { useBenchmarkExport } from "./useBenchmarkExport";

const HASH = `sha256:${"a".repeat(64)}`;
const MANIFEST_ID = `artifact-${"1".repeat(32)}`;
const BUNDLE_ID = `artifact-${"2".repeat(32)}`;
const REPORT_ID = `artifact-${"3".repeat(32)}`;

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** Build one strict readable Export inventory item. */
function item(
  artifactId: string,
  kind: string,
  contentType: string,
  size: number,
): BenchmarkArtifactInventoryItem {
  return {
    schemaVersion: 1,
    descriptor: {
      schemaVersion: 1,
      artifactId,
      experimentId: reportExperimentId,
      taskRunId: null,
      kind,
      availability: "available",
      contentType,
      size,
      sha256: HASH,
      provenance: "fixture",
      causalIdentity: `${kind}.json`,
      hidden: false,
    },
    links: {
      content:
        `/studio/benchmark-experiments/${reportExperimentId}/artifacts/`
        + artifactId,
    },
  };
}

/** Parse one closed strict Export inventory. */
function inventory(
  items: BenchmarkArtifactInventoryItem[],
): BenchmarkArtifactInventoryPage {
  return parseBenchmarkArtifactInventoryPage({
    schemaVersion: 1,
    experimentId: reportExperimentId,
    items,
    hiddenCount: 1,
    nextCursor: null,
  });
}

/** Build the metadata-only refresh result used by the hook. */
function snapshot(
  value: BenchmarkArtifactInventoryPage,
): BenchmarkExportMetadataSnapshot {
  return {
    experiment: {
      experimentId: reportExperimentId,
    } as BenchmarkExperimentResource,
    taskRuns: [
      { taskRunId: reportTaskRunId } as BenchmarkTaskRun,
    ],
    inventory: value,
  };
}

/** Return the sole projected bundle material. */
function bundleMaterial(
  value: BenchmarkArtifactInventoryPage,
): BenchmarkExportMaterial {
  return projectBenchmarkExportMaterials(
    reportExperimentId,
    value,
  ).experimentBundle!;
}

/** Build a successful no-body HEAD response. */
function headResponse(
  material: BenchmarkExportMaterial,
  patch: Record<string, string> = {},
): Response {
  return new Response(null, {
    status: 200,
    headers: {
      "Content-Type": material.item.descriptor.contentType,
      "Content-Length": String(material.item.descriptor.size),
      "Content-Disposition":
        `attachment; filename="${material.item.descriptor.artifactId}"`,
      ...patch,
    },
  });
}

describe("useBenchmarkExport", () => {
  it("coalesces double Prepare and reaches ready-for-handoff", async () => {
    const value = inventory([
      item(
        BUNDLE_ID,
        "experiment_bundle",
        "application/zip",
        128 * 1024 * 1024,
      ),
    ]);
    const material = bundleMaterial(value);
    const refresh = vi.fn(async () => snapshot(value));
    const fetchMock = vi.fn(async (
      _url: string,
      _init?: RequestInit,
    ) => headResponse(material));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() =>
      useBenchmarkExport(
        reportExperimentId,
        value,
        [reportTaskRunId],
        refresh,
      ),
    );

    let first!: Promise<void>;
    let second!: Promise<void>;
    act(() => {
      first = result.current.prepare(material);
      second = result.current.prepare(material);
    });
    expect(first).toBe(second);
    await act(async () => first);

    expect(refresh).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: "HEAD" });
    expect(result.current.prepareStates.get(material.key)?.kind).toBe(
      "ready-for-handoff",
    );
    act(() => result.current.markHandedOff(material));
    expect(result.current.prepareStates.get(material.key)?.kind).toBe(
      "handed-off",
    );
  });

  it("prepares sibling materials independently and releases failure for retry", async () => {
    const value = inventory([
      item(BUNDLE_ID, "experiment_bundle", "application/zip", 128),
      item(REPORT_ID, "experiment_report", "application/json", 64),
    ]);
    const projection = projectBenchmarkExportMaterials(
      reportExperimentId,
      value,
    );
    const bundle = projection.experimentBundle!;
    const report = projection.experimentReport!;
    let failReport = true;
    const fetchMock = vi.fn(async (url: string) => {
      const material = url.includes(REPORT_ID) ? report : bundle;
      if (url.includes(REPORT_ID) && failReport) {
        failReport = false;
        throw new TypeError("network unavailable");
      }
      return headResponse(material);
    });
    vi.stubGlobal("fetch", fetchMock);
    const refresh = vi.fn(async () => snapshot(value));
    const { result } = renderHook(() =>
      useBenchmarkExport(
        reportExperimentId,
        value,
        [reportTaskRunId],
        refresh,
      ),
    );

    await act(async () => Promise.all([
      result.current.prepare(bundle),
      result.current.prepare(report),
    ]));
    expect(result.current.prepareStates.get(bundle.key)?.kind).toBe(
      "ready-for-handoff",
    );
    expect(result.current.prepareStates.get(report.key)).toMatchObject({
      kind: "failed",
      failure: "request-failed",
      retryable: true,
    });

    await act(async () => result.current.prepare(report));
    expect(result.current.prepareStates.get(report.key)?.kind).toBe(
      "ready-for-handoff",
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("rechecks authoritative availability after resolver closure failure", async () => {
    const value = inventory([
      item(BUNDLE_ID, "experiment_bundle", "application/zip", 128),
    ]);
    const material = bundleMaterial(value);
    const corrupt = inventory([
      {
        ...material.item,
        descriptor: {
          ...material.item.descriptor,
          availability: "corrupt",
          contentType: "",
          size: 0,
          sha256: null,
        },
        links: { content: null },
      },
    ]);
    let refreshCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 409 })),
    );
    const { result } = renderHook(() =>
      useBenchmarkExport(
        reportExperimentId,
        value,
        [reportTaskRunId],
        async () => {
          refreshCount += 1;
          return snapshot(refreshCount === 1 ? value : corrupt);
        },
      ),
    );
    await act(async () => result.current.prepare(material));
    expect(result.current.prepareStates.get(material.key)).toMatchObject({
      kind: "failed",
      failure: "unavailable",
      availability: "corrupt",
    });
  });

  it("aborts and ignores late preparation when the drawer resets", async () => {
    const value = inventory([
      item(BUNDLE_ID, "experiment_bundle", "application/zip", 128),
    ]);
    const material = bundleMaterial(value);
    let resolveHead!: (response: Response) => void;
    const aborted = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) =>
        new Promise<Response>((resolve, reject) => {
          resolveHead = resolve;
          init?.signal?.addEventListener("abort", () => {
            aborted();
            reject(new DOMException("aborted", "AbortError"));
          });
        })),
    );
    const { result } = renderHook(() =>
      useBenchmarkExport(
        reportExperimentId,
        value,
        [reportTaskRunId],
        async () => snapshot(value),
      ),
    );
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.prepare(material);
    });
    await waitFor(() =>
      expect(result.current.prepareStates.get(material.key)?.kind).toBe(
        "verifying-head",
      )
    );
    act(() => result.current.reset());
    resolveHead(headResponse(material));
    await act(async () => pending);
    expect(aborted).toHaveBeenCalledOnce();
    expect(result.current.prepareStates.size).toBe(0);
  });

  it("invalidates a target changed by authoritative metadata refresh", async () => {
    const value = inventory([
      item(BUNDLE_ID, "experiment_bundle", "application/zip", 128),
    ]);
    const material = bundleMaterial(value);
    const changed = inventory([
      {
        ...material.item,
        descriptor: { ...material.item.descriptor, size: 129 },
      },
    ]);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() =>
      useBenchmarkExport(
        reportExperimentId,
        value,
        [reportTaskRunId],
        async () => snapshot(changed),
      ),
    );
    await act(async () => result.current.prepare(material));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.prepareStates.get(material.key)).toMatchObject({
      kind: "failed",
      failure: "stale-target",
    });
  });

  it("keeps header conflicts local and retryable", async () => {
    const value = inventory([
      item(BUNDLE_ID, "experiment_bundle", "application/zip", 128),
    ]);
    const material = bundleMaterial(value);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        headResponse(material, {
          "Content-Disposition": 'inline; filename="bundle.zip"',
        })),
    );
    const { result } = renderHook(() =>
      useBenchmarkExport(
        reportExperimentId,
        value,
        [reportTaskRunId],
        async () => snapshot(value),
      ),
    );
    await act(async () => result.current.prepare(material));
    expect(result.current.prepareStates.get(material.key)).toMatchObject({
      kind: "failed",
      failure: "header-conflict",
      retryable: true,
    });
  });

  it("aborts obsolete HEAD when the Experiment scope changes", async () => {
    const value = inventory([
      item(BUNDLE_ID, "experiment_bundle", "application/zip", 128),
    ]);
    const material = bundleMaterial(value);
    const aborted = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            aborted();
            reject(new DOMException("aborted", "AbortError"));
          });
        })),
    );
    const { result, rerender } = renderHook(
      ({ experimentId }) =>
        useBenchmarkExport(
          experimentId,
          value,
          [reportTaskRunId],
          async () => snapshot(value),
        ),
      { initialProps: { experimentId: reportExperimentId } },
    );
    let pending!: Promise<void>;
    act(() => {
      pending = result.current.prepare(material);
    });
    await waitFor(() =>
      expect(result.current.prepareStates.get(material.key)?.kind).toBe(
        "verifying-head",
      )
    );
    rerender({ experimentId: `experiment-${"f".repeat(32)}` });
    await act(async () => pending);
    expect(aborted).toHaveBeenCalledOnce();
    expect(result.current.prepareStates.size).toBe(0);
  });

  it("loads and explicitly discards bounded manifest facts", async () => {
    const source = new TextEncoder().encode(JSON.stringify({
      schemaVersion: 1,
      kind: "studio_benchmark_publication_manifest",
      experimentId: reportExperimentId,
      taskRunId: reportTaskRunId,
      members: [],
      excludedEvidence: [
        {
          kind: "prompt",
          availability: "hidden",
          reason: "hidden_by_default_policy",
        },
      ],
    }));
    const value = inventory([
      item(
        MANIFEST_ID,
        "studio_publication_manifest",
        "application/json",
        source.byteLength,
      ),
    ]);
    const material = projectBenchmarkExportMaterials(
      reportExperimentId,
      value,
    ).publicationManifest!;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(source, {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Content-Length": String(source.byteLength),
        },
      })),
    );
    const { result } = renderHook(() =>
      useBenchmarkExport(
        reportExperimentId,
        value,
        [reportTaskRunId],
        async () => snapshot(value),
      ),
    );
    await act(async () => result.current.loadManifest(material));
    expect(result.current.manifestState).toMatchObject({
      kind: "ready",
      summary: {
        memberCount: 0,
        excludedEvidence: [{ kind: "prompt" }],
      },
    });
    act(() => result.current.closeManifest());
    expect(result.current.manifestState).toEqual({ kind: "idle" });
  });
});
