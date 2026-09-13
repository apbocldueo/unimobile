import { afterEach, describe, expect, it, vi } from "vitest";
import {
  StudioApiError,
  StudioBoundedByteError,
  StudioHeadContractError,
  studioBoundedByteRequest,
  studioHeadRequest,
  studioRawJsonRequest,
} from "./httpClient";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Build one exact response for bounded transport tests. */
function byteResponse(
  bytes: Uint8Array | null,
  contentType = "application/json; charset=utf-8",
  contentLength: string | null = bytes === null ? "0" : String(bytes.byteLength),
): Response {
  const headers = new Headers({ "Content-Type": contentType });
  if (contentLength !== null) headers.set("Content-Length", contentLength);
  return new Response(bytes, { status: 200, headers });
}

/** Build one JSON response for raw command transport tests. */
function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("studioRawJsonRequest", () => {
  it("sends a raw body without setting Content-Length", async () => {
    const controller = new AbortController();
    const body = new Blob(["fixture"], { type: "text/plain" });
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(init).toMatchObject({
        method: "POST",
        body,
        signal: controller.signal,
      });
      expect(headers.get("Accept")).toBe("application/json");
      expect(headers.get("Content-Type")).toBe("text/plain");
      expect(headers.has("Content-Length")).toBe(false);
      return jsonResponse({ schemaVersion: 1, ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      studioRawJsonRequest("/studio/raw-command", {
        body,
        contentType: "text/plain",
        signal: controller.signal,
      }),
    ).resolves.toEqual({ schemaVersion: 1, ok: true });
  });

  it("preserves the bounded Studio error envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          {
            schemaVersion: 1,
            error: {
              code: "benchmark.authoring.revision_conflict",
              message: "Current revision changed",
              currentRevisionId: "revision-current",
            },
          },
          409,
        )),
    );

    await expect(
      studioRawJsonRequest("/studio/raw-command"),
    ).rejects.toMatchObject({
      status: 409,
      code: "benchmark.authoring.revision_conflict",
      currentRevisionId: "revision-current",
    } satisfies Partial<StudioApiError>);
  });
});

describe("studioBoundedByteRequest", () => {
  it("reads an exact normalized MIME response incrementally", async () => {
    const source = new TextEncoder().encode('{"ok":true}');
    vi.stubGlobal("fetch", vi.fn(async () => byteResponse(source)));

    const bytes = await studioBoundedByteRequest("/studio/evidence", {
      expectedContentType: "application/json",
      expectedBytes: source.byteLength,
      maxBytes: 1024,
    });

    expect(new TextDecoder().decode(bytes)).toBe('{"ok":true}');
  });

  it.each([
    ["missing length", byteResponse(new Uint8Array([1]), "text/plain", null), "size-mismatch"],
    ["invalid length", byteResponse(new Uint8Array([1]), "text/plain", "1.0"), "size-mismatch"],
    ["wrong length", byteResponse(new Uint8Array([1]), "text/plain", "2"), "size-mismatch"],
    ["wrong MIME", byteResponse(new Uint8Array([1]), "application/json"), "mime-mismatch"],
    ["missing body", byteResponse(null, "text/plain", "0"), "body-unavailable"],
  ])("fails closed for %s", async (_label, response, kind) => {
    vi.stubGlobal("fetch", vi.fn(async () => response));
    await expect(
      studioBoundedByteRequest("/studio/evidence", {
        expectedContentType: "text/plain",
        expectedBytes: kind === "body-unavailable" ? 0 : 1,
        maxBytes: 8,
      }),
    ).rejects.toMatchObject({ kind });
  });

  it("rejects dishonest streamed bytes above the exact descriptor size", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        byteResponse(new Uint8Array([1, 2]), "application/octet-stream", "1")),
    );
    await expect(
      studioBoundedByteRequest("/studio/evidence", {
        expectedContentType: "application/octet-stream",
        expectedBytes: 1,
        maxBytes: 8,
      }),
    ).rejects.toMatchObject({ kind: "size-mismatch" });
  });

  it("rejects descriptor bytes above policy before issuing a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      studioBoundedByteRequest("/studio/evidence", {
        expectedContentType: "text/plain",
        expectedBytes: 9,
        maxBytes: 8,
      }),
    ).rejects.toBeInstanceOf(StudioBoundedByteError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("passes the caller AbortSignal and preserves abort semantics", async () => {
    const controller = new AbortController();
    controller.abort();
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init?.signal).toBe(controller.signal);
      throw new DOMException("aborted", "AbortError");
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      studioBoundedByteRequest("/studio/evidence", {
        expectedContentType: "text/plain",
        expectedBytes: 1,
        maxBytes: 8,
        signal: controller.signal,
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("studioHeadRequest", () => {
  it("prepares an exact attachment without reading response bytes", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init?.method).toBe("HEAD");
      return new Response(null, {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Length": "128",
          "Content-Disposition": 'attachment; filename="experiment.zip"',
        },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      studioHeadRequest("/studio/benchmark-experiments/one/bundle", {
        expectedContentType: "application/zip",
        expectedBytes: 128,
      }),
    ).resolves.toEqual({
      contentType: "application/zip",
      contentLength: 128,
      filename: "experiment.zip",
    });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it.each([
    ["absolute URL", "https://example.com/studio/file", "invalid-capability"],
    ["query", "/studio/file?download=1", "invalid-capability"],
    ["traversal", "/studio/files/../secret", "invalid-capability"],
  ])("rejects %s before issuing HEAD", async (_label, path, kind) => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      studioHeadRequest(path, {
        expectedContentType: "application/json",
        expectedBytes: 1,
      }),
    ).rejects.toMatchObject({ kind });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    [
      "MIME",
      {
        "Content-Type": "text/plain",
        "Content-Length": "1",
        "Content-Disposition": 'attachment; filename="evidence.json"',
      },
      "mime-mismatch",
    ],
    [
      "length",
      {
        "Content-Type": "application/json",
        "Content-Length": "2",
        "Content-Disposition": 'attachment; filename="evidence.json"',
      },
      "size-mismatch",
    ],
    [
      "disposition",
      {
        "Content-Type": "application/json",
        "Content-Length": "1",
        "Content-Disposition": 'inline; filename="evidence.json"',
      },
      "disposition-mismatch",
    ],
  ])("fails closed on %s conflict", async (_label, headers, kind) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 200, headers })),
    );
    await expect(
      studioHeadRequest("/studio/evidence", {
        expectedContentType: "application/json",
        expectedBytes: 1,
      }),
    ).rejects.toMatchObject({ kind });
  });

  it("passes cancellation through to fetch", async () => {
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
      studioHeadRequest("/studio/evidence", {
        expectedContentType: "application/json",
        expectedBytes: 1,
        signal: controller.signal,
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
  });

  it("uses a dedicated safe contract error type", () => {
    expect(new StudioHeadContractError("invalid-contract")).toBeInstanceOf(
      StudioHeadContractError,
    );
  });
});
