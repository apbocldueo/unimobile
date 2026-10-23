import {
  StudioBoundedByteError,
  studioApiUrl,
  studioBoundedByteRequest,
} from "@/shared/api";
import type { BenchmarkArtifactInventoryItem } from "../model/benchmarkReport.schema";

export const BENCHMARK_EVIDENCE_TEXT_MAX_BYTES = 2 * 1024 * 1024;
export const BENCHMARK_EVIDENCE_PNG_MAX_BYTES = 8 * 1024 * 1024;
export const BENCHMARK_EVIDENCE_PNG_MAX_AXIS = 4096;
export const BENCHMARK_EVIDENCE_PNG_MAX_PIXELS = 16_777_216;

export type BenchmarkEvidencePreviewErrorKind =
  | "oversized"
  | "size-mismatch"
  | "mime-mismatch"
  | "invalid-content"
  | "request-failed";

export class BenchmarkEvidencePreviewError extends Error {
  readonly kind: BenchmarkEvidencePreviewErrorKind;

  constructor(kind: BenchmarkEvidencePreviewErrorKind) {
    super("Benchmark evidence could not be previewed safely.");
    this.name = "BenchmarkEvidencePreviewError";
    this.kind = kind;
  }
}

export type BenchmarkEvidencePreview =
  | {
      kind: "ready-text";
      text: string;
      language: "json" | "ndjson" | "xml" | "text";
    }
  | {
      kind: "ready-image";
      objectUrl: string;
      width: number;
      height: number;
    }
  | {
      kind: "download-only";
      url: string;
      contentType: string;
    };

const TEXT_MEDIA = new Map<string, "json" | "ndjson" | "xml" | "text">([
  ["application/json", "json"],
  ["application/x-ndjson", "ndjson"],
  ["application/xml", "xml"],
  ["text/plain", "text"],
]);
const ALLOWED_MEDIA = new Set([
  ...TEXT_MEDIA.keys(),
  "application/zip",
  "image/png",
]);

/** Load and adapt one already parsed Benchmark inventory capability.
 *
 * Args:
 *   item: Strict visible inventory item carrying the sole content capability.
 *   signal: Selection-owned cancellation signal.
 *
 * Raises:
 *   BenchmarkEvidencePreviewError: Preview policy or content is invalid.
 *   StudioApiError: The authoritative backend rejected the capability.
 *   DOMException: The selection was aborted.
 *
 * Returns:
 *   Escaped text, a bounded temporary PNG URL, or an unfetched browser
 *   download handoff.
 */
export async function loadBenchmarkEvidencePreview(
  item: BenchmarkArtifactInventoryItem,
  signal: AbortSignal,
): Promise<BenchmarkEvidencePreview> {
  const capability = item.links.content;
  if (capability === null) {
    throw new BenchmarkEvidencePreviewError("request-failed");
  }
  const mediaType = normalizeMediaType(item.descriptor.contentType);
  const textLanguage = TEXT_MEDIA.get(mediaType);
  if (textLanguage !== undefined) {
    const bytes = await loadBytes(
      item,
      capability,
      BENCHMARK_EVIDENCE_TEXT_MAX_BYTES,
      signal,
    );
    const source = decodeUtf8(bytes);
    return {
      kind: "ready-text",
      text: formatTextEvidence(source, textLanguage),
      language: textLanguage,
    };
  }
  if (mediaType === "image/png") {
    const bytes = await loadBytes(
      item,
      capability,
      BENCHMARK_EVIDENCE_PNG_MAX_BYTES,
      signal,
    );
    const dimensions = parsePngDimensions(bytes);
    let objectUrl: string;
    try {
      objectUrl = URL.createObjectURL(new Blob([bytes], { type: "image/png" }));
    } catch {
      throw new BenchmarkEvidencePreviewError("invalid-content");
    }
    return { kind: "ready-image", objectUrl, ...dimensions };
  }
  if (!ALLOWED_MEDIA.has(mediaType)) {
    throw new BenchmarkEvidencePreviewError("invalid-content");
  }
  return {
    kind: "download-only",
    url: studioApiUrl(capability),
    contentType: mediaType,
  };
}

/** Read bytes through the shared exact response contract. */
async function loadBytes(
  item: BenchmarkArtifactInventoryItem,
  capability: string,
  maxBytes: number,
  signal: AbortSignal,
): Promise<Uint8Array> {
  if (item.descriptor.size > maxBytes) {
    throw new BenchmarkEvidencePreviewError("oversized");
  }
  try {
    return await studioBoundedByteRequest(capability, {
      signal,
      expectedContentType: item.descriptor.contentType,
      expectedBytes: item.descriptor.size,
      maxBytes,
    });
  } catch (error) {
    if (error instanceof StudioBoundedByteError) {
      const kind = error.kind;
      if (kind === "oversized") {
        throw new BenchmarkEvidencePreviewError("oversized");
      }
      if (kind === "mime-mismatch") {
        throw new BenchmarkEvidencePreviewError("mime-mismatch");
      }
      if (kind === "size-mismatch") {
        throw new BenchmarkEvidencePreviewError("size-mismatch");
      }
      throw new BenchmarkEvidencePreviewError("request-failed");
    }
    throw error;
  }
}

/** Decode exact UTF-8 and fail instead of replacing malformed bytes. */
function decodeUtf8(bytes: Uint8Array): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new BenchmarkEvidencePreviewError("invalid-content");
  }
}

/** Validate and deterministically format one supported textual medium. */
function formatTextEvidence(
  source: string,
  language: "json" | "ndjson" | "xml" | "text",
): string {
  if (language === "json") {
    try {
      return JSON.stringify(JSON.parse(source), null, 2);
    } catch {
      throw new BenchmarkEvidencePreviewError("invalid-content");
    }
  }
  if (language === "ndjson") {
    try {
      return source
        .split(/\r?\n/)
        .filter((line) => line.trim().length > 0)
        .map((line) => JSON.stringify(JSON.parse(line)))
        .join("\n");
    } catch {
      throw new BenchmarkEvidencePreviewError("invalid-content");
    }
  }
  return source;
}

/** Validate PNG signature/IHDR and browser-memory dimension ceilings. */
function parsePngDimensions(
  bytes: Uint8Array,
): { width: number; height: number } {
  const signature = [137, 80, 78, 71, 13, 10, 26, 10];
  if (
    bytes.byteLength < 24
    || signature.some((value, index) => bytes[index] !== value)
    || readUint32(bytes, 8) !== 13
    || String.fromCharCode(...bytes.slice(12, 16)) !== "IHDR"
  ) {
    throw new BenchmarkEvidencePreviewError("invalid-content");
  }
  const width = readUint32(bytes, 16);
  const height = readUint32(bytes, 20);
  if (
    width === 0
    || height === 0
    || width > BENCHMARK_EVIDENCE_PNG_MAX_AXIS
    || height > BENCHMARK_EVIDENCE_PNG_MAX_AXIS
    || width * height > BENCHMARK_EVIDENCE_PNG_MAX_PIXELS
  ) {
    throw new BenchmarkEvidencePreviewError("invalid-content");
  }
  return { width, height };
}

/** Read one unsigned big-endian 32-bit integer from bounded PNG bytes. */
function readUint32(bytes: Uint8Array, offset: number): number {
  return new DataView(
    bytes.buffer,
    bytes.byteOffset,
    bytes.byteLength,
  ).getUint32(offset);
}

/** Normalize a descriptor media type for adapter dispatch. */
function normalizeMediaType(value: string): string {
  return value.split(";", 1)[0]!.trim().toLowerCase();
}
