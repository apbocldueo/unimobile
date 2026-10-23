import { afterEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkReportInventoryFixture,
  parseBenchmarkArtifactInventoryPage,
  type BenchmarkArtifactInventoryItem,
} from "@/entities/benchmark-report";
import {
  BENCHMARK_EVIDENCE_TEXT_MAX_BYTES,
  BenchmarkEvidencePreviewError,
  loadBenchmarkEvidencePreview,
} from "./benchmarkEvidenceApi";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** Build one strict readable inventory capability for adapter tests. */
function itemFor(
  contentType: string,
  size: number,
): BenchmarkArtifactInventoryItem {
  const raw = benchmarkReportInventoryFixture();
  raw.items[0]!.descriptor.contentType = contentType;
  raw.items[0]!.descriptor.size = size;
  return parseBenchmarkArtifactInventoryPage(raw).items[0]!;
}

/** Install one exact body response and return the fetch spy. */
function serve(
  bytes: Uint8Array,
  contentType: string,
  declaredSize = bytes.byteLength,
) {
  const fetchMock = vi.fn(async () =>
    new Response(bytes, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Length": String(declaredSize),
      },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("loadBenchmarkEvidencePreview", () => {
  it("formats a valid JSON value deterministically", async () => {
    const bytes = new TextEncoder().encode('{"script":"<script>x</script>","n":1}');
    serve(bytes, "application/json; charset=utf-8");
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor("application/json", bytes.byteLength),
        new AbortController().signal,
      ),
    ).resolves.toEqual({
      kind: "ready-text",
      language: "json",
      text: '{\n  "script": "<script>x</script>",\n  "n": 1\n}',
    });
  });

  it("validates every non-empty NDJSON line and preserves order", async () => {
    const bytes = new TextEncoder().encode('{"n":1}\n\n{"n":2}\n');
    serve(bytes, "application/x-ndjson");
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor("application/x-ndjson", bytes.byteLength),
        new AbortController().signal,
      ),
    ).resolves.toMatchObject({
      kind: "ready-text",
      language: "ndjson",
      text: '{"n":1}\n{"n":2}',
    });
  });

  it.each([
    ["application/json", '{"partial":'],
    ["application/x-ndjson", '{"ok":1}\nnot-json\n{"late":2}'],
  ])("rejects malformed %s without a partial preview", async (media, source) => {
    const bytes = new TextEncoder().encode(source);
    serve(bytes, media);
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor(media, bytes.byteLength),
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ kind: "invalid-content" });
  });

  it.each([
    ["application/xml", "<root><![CDATA[<script>x</script>]]>&entity;</root>"],
    ["text/plain", "/private/path\nTOKEN=<script>x</script>"],
  ])("returns %s source as inert text", async (media, source) => {
    const bytes = new TextEncoder().encode(source);
    serve(bytes, media);
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor(media, bytes.byteLength),
        new AbortController().signal,
      ),
    ).resolves.toMatchObject({
      kind: "ready-text",
      text: source,
    });
  });

  it("rejects text above the preview ceiling before fetching", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor("text/plain", BENCHMARK_EVIDENCE_TEXT_MAX_BYTES + 1),
        new AbortController().signal,
      ),
    ).rejects.toBeInstanceOf(BenchmarkEvidencePreviewError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("validates PNG signature and IHDR dimensions before creating a URL", async () => {
    const bytes = pngHeader(640, 480);
    serve(bytes, "image/png");
    const createObjectURL = vi.fn(() => "blob:bounded-preview");
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL: vi.fn(),
    });
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor("image/png", bytes.byteLength),
        new AbortController().signal,
      ),
    ).resolves.toMatchObject({
      kind: "ready-image",
      objectUrl: "blob:bounded-preview",
      width: 640,
      height: 480,
    });
    expect(createObjectURL).toHaveBeenCalledOnce();
  });

  it.each([
    ["bad signature", new Uint8Array(24)],
    ["truncated header", pngHeader(1, 1).slice(0, 23)],
    ["axis overflow", pngHeader(4097, 1)],
    ["pixel overflow", pngHeader(4096, 4097)],
  ])("rejects PNG %s deterministically", async (_label, bytes) => {
    serve(bytes, "image/png");
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor("image/png", bytes.byteLength),
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ kind: "invalid-content" });
  });

  it("rejects object URL creation failure", async () => {
    const bytes = pngHeader(1, 1);
    serve(bytes, "image/png");
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => {
        throw new Error("unavailable");
      }),
      revokeObjectURL: vi.fn(),
    });
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor("image/png", bytes.byteLength),
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ kind: "invalid-content" });
  });

  it("fails on response MIME mismatch", async () => {
    const bytes = new TextEncoder().encode("plain");
    serve(bytes, "application/json");
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor("text/plain", bytes.byteLength),
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ kind: "mime-mismatch" });
  });

  it("classifies ZIP as download-only without fetching or inspecting it", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor("application/zip", 500),
        new AbortController().signal,
      ),
    ).resolves.toMatchObject({
      kind: "download-only",
      contentType: "application/zip",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects non-allowlisted media instead of creating an active download", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      loadBenchmarkEvidencePreview(
        itemFor("text/html", 20),
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ kind: "invalid-content" });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

/** Build the minimal PNG prefix required for signature/IHDR bounds checks. */
function pngHeader(width: number, height: number): Uint8Array {
  const bytes = new Uint8Array(24);
  bytes.set([137, 80, 78, 71, 13, 10, 26, 10], 0);
  const view = new DataView(bytes.buffer);
  view.setUint32(8, 13);
  bytes.set(new TextEncoder().encode("IHDR"), 12);
  view.setUint32(16, width);
  view.setUint32(20, height);
  return bytes;
}
