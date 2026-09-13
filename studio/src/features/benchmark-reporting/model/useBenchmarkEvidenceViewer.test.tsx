import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkReportInventoryFixture,
  benchmarkRunReportFixture,
  parseBenchmarkArtifactInventoryPage,
  parseBenchmarkRunReport,
  reportExperimentId,
  reportTaskRunId,
  type BenchmarkEvidenceSelection,
} from "@/entities/benchmark-report";
import { useBenchmarkEvidenceViewer } from "./useBenchmarkEvidenceViewer";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const source = new TextEncoder().encode("bounded evidence");

/** Build one strict selection and inventory for disposable hook tests. */
function fixture() {
  const report = parseBenchmarkRunReport(benchmarkRunReportFixture());
  const evidence = {
    ...report.evaluation!.children[0]!.evaluatorResult!.evidence[0]!,
    artifactRef: "runs/evidence.txt",
  };
  const raw = benchmarkReportInventoryFixture();
  raw.items[0]!.descriptor.kind = "evaluator_evidence";
  raw.items[0]!.descriptor.contentType = "text/plain";
  raw.items[0]!.descriptor.size = source.byteLength;
  raw.items[0]!.descriptor.causalIdentity = evidence.artifactRef;
  return {
    selection: {
      leafPath: "root/leaf",
      evidenceIndex: 0,
      evidence,
    } satisfies BenchmarkEvidenceSelection,
    inventory: parseBenchmarkArtifactInventoryPage(raw),
    scope: {
      experimentId: reportExperimentId,
      taskRunId: reportTaskRunId,
    },
  };
}

/** Build one exact text response for the selected descriptor. */
function textResponse() {
  return new Response(source, {
    headers: {
      "Content-Type": "text/plain",
      "Content-Length": String(source.byteLength),
    },
  });
}

describe("useBenchmarkEvidenceViewer", () => {
  it("does not prefetch without explicit selection and loads after selection", async () => {
    const value = fixture();
    const fetchMock = vi.fn(async () => textResponse());
    vi.stubGlobal("fetch", fetchMock);
    const { result, rerender } = renderHook(
      ({ selection }: { selection: BenchmarkEvidenceSelection | null }) =>
        useBenchmarkEvidenceViewer(selection, value.scope, value.inventory),
      {
        initialProps: {
          selection: null as BenchmarkEvidenceSelection | null,
        },
      },
    );
    expect(result.current.state.kind).toBe("idle");
    expect(fetchMock).not.toHaveBeenCalled();

    rerender({ selection: value.selection });
    await waitFor(() => expect(result.current.state.kind).toBe("ready-text"));
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("aborts on close and ignores a late completion", async () => {
    const value = fixture();
    let resolveResponse!: (response: Response) => void;
    const responsePromise = new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    });
    const captured: { signal: AbortSignal | null } = { signal: null };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        captured.signal = init?.signal as AbortSignal;
        return responsePromise;
      }),
    );
    const { result, rerender } = renderHook(
      ({ selection }: { selection: BenchmarkEvidenceSelection | null }) =>
        useBenchmarkEvidenceViewer(selection, value.scope, value.inventory),
      {
        initialProps: {
          selection: value.selection as BenchmarkEvidenceSelection | null,
        },
      },
    );
    await waitFor(() => expect(result.current.state.kind).toBe("loading"));
    rerender({ selection: null });
    expect(captured.signal?.aborted).toBe(true);
    resolveResponse(textResponse());
    await waitFor(() => expect(result.current.state.kind).toBe("idle"));
  });

  it("retries only after an explicit retry action", async () => {
    const value = fixture();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: {
              code: "fixture.failed",
              message: "SECRET RAW BACKEND DETAIL",
            },
          }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(textResponse());
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() =>
      useBenchmarkEvidenceViewer(
        value.selection,
        value.scope,
        value.inventory,
      ),
    );
    await waitFor(() =>
      expect(result.current.state.kind).toBe("request-failed"),
    );
    expect(fetchMock).toHaveBeenCalledOnce();
    result.current.retry();
    await waitFor(() => expect(result.current.state.kind).toBe("ready-text"));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("revokes each owned image URL on replacement and unmount", async () => {
    const value = fixture();
    const png = new Uint8Array(24);
    png.set([137, 80, 78, 71, 13, 10, 26, 10], 0);
    const view = new DataView(png.buffer);
    view.setUint32(8, 13);
    png.set(new TextEncoder().encode("IHDR"), 12);
    view.setUint32(16, 1);
    view.setUint32(20, 1);
    value.inventory.items[0]!.descriptor.contentType = "image/png";
    value.inventory.items[0]!.descriptor.size = png.byteLength;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(png, {
          headers: {
            "Content-Type": "image/png",
            "Content-Length": String(png.byteLength),
          },
        }),
      ),
    );
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:owned"),
      revokeObjectURL,
    });
    const { result, unmount } = renderHook(() =>
      useBenchmarkEvidenceViewer(
        value.selection,
        value.scope,
        value.inventory,
      ),
    );
    await waitFor(() => expect(result.current.state.kind).toBe("ready-image"));
    unmount();
    expect(revokeObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:owned");
  });
});
