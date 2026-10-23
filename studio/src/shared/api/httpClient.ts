export type StudioApiErrorShape = {
  schemaVersion?: number;
  error?: {
    code?: string;
    message?: string;
    currentRevisionId?: string | null;
  };
};

export class StudioApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly currentRevisionId: string | null;

  constructor(status: number, payload: StudioApiErrorShape) {
    const message = payload.error?.message ?? `Studio API request failed (${status})`;
    super(message);
    this.name = "StudioApiError";
    this.status = status;
    this.code = payload.error?.code ?? "studio.http.unknown";
    this.currentRevisionId = payload.error?.currentRevisionId ?? null;
  }
}

export type StudioBoundedByteErrorKind =
  | "invalid-contract"
  | "oversized"
  | "mime-mismatch"
  | "size-mismatch"
  | "body-unavailable";

export type StudioBoundedByteRequest = {
  signal?: AbortSignal;
  expectedContentType: string;
  expectedBytes: number;
  maxBytes: number;
  accept?: string;
};

export type StudioHeadRequest = {
  signal?: AbortSignal;
  expectedContentType: string;
  expectedBytes: number;
  expectedSha256?: string;
};

export type StudioHeadResponse = {
  contentType: string;
  contentLength: number;
  filename: string;
  sha256?: string;
};

export type StudioRawJsonRequest = {
  body?: BodyInit | null;
  contentType?: string;
  signal?: AbortSignal;
};

export type StudioHeadContractErrorKind =
  | "invalid-capability"
  | "invalid-contract"
  | "mime-mismatch"
  | "size-mismatch"
  | "disposition-mismatch"
  | "digest-mismatch";

/** Describe a safe HEAD preparation contract violation. */
export class StudioHeadContractError extends Error {
  readonly kind: StudioHeadContractErrorKind;

  constructor(kind: StudioHeadContractErrorKind) {
    super("Studio download headers did not satisfy the preparation contract.");
    this.name = "StudioHeadContractError";
    this.kind = kind;
  }
}

/** Describe a fail-closed bounded-response contract violation safely. */
export class StudioBoundedByteError extends Error {
  readonly kind: StudioBoundedByteErrorKind;

  constructor(kind: StudioBoundedByteErrorKind) {
    super("Studio evidence did not satisfy the bounded response contract.");
    this.name = "StudioBoundedByteError";
    this.kind = kind;
  }
}

/** Resolve the configured Studio API URL for one versioned route. */
export function studioApiUrl(path: string): string {
  const configured =
    typeof import.meta !== "undefined"
      ? (import.meta.env?.VITE_STUDIO_API_BASE as string | undefined)
      : undefined;
  const base = configured?.trim().replace(/\/+$/, "") || (import.meta.env?.DEV ? "/zhixing-studio" : "");
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

/** Send one bounded JSON request and surface the stable backend error envelope. */
export async function studioRequest(
  path: string,
  init: RequestInit = {},
): Promise<unknown> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(studioApiUrl(path), { ...init, headers });
  const payload = (await response.json().catch(() => ({}))) as StudioApiErrorShape;
  if (!response.ok) throw new StudioApiError(response.status, payload);
  return payload;
}

/** Send one raw-body Studio command and parse its bounded JSON result.
 *
 * Args:
 *   path: Versioned Studio route owned and validated by an entity API.
 *   options: Optional raw body, media type, and cancellation signal.
 *
 * Raises:
 *   StudioApiError: The backend returned its stable error envelope.
 *   DOMException: The caller aborted the request.
 *
 * Returns:
 *   The untrusted JSON payload for strict entity parsing.
 */
export async function studioRawJsonRequest(
  path: string,
  options: StudioRawJsonRequest = {},
): Promise<unknown> {
  const headers = new Headers({ Accept: "application/json" });
  if (options.contentType !== undefined) {
    headers.set("Content-Type", options.contentType);
  }
  const response = await fetch(studioApiUrl(path), {
    method: "POST",
    body: options.body,
    headers,
    signal: options.signal,
  });
  const payload = (await response.json().catch(() => ({}))) as StudioApiErrorShape;
  if (!response.ok) throw new StudioApiError(response.status, payload);
  return payload;
}

/** Fetch bounded text evidence while preserving the backend error envelope.
 *
 * The caller supplies only a versioned Studio route. Binary or oversized
 * evidence remains outside this helper so model responses cannot accidentally
 * become an unbounded browser allocation.
 */
export async function studioTextRequest(
  path: string,
  maxBytes = 2 * 1024 * 1024,
): Promise<string> {
  const response = await fetch(studioApiUrl(path), {
    headers: { Accept: "text/plain, application/json;q=0.9" },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as StudioApiErrorShape;
    throw new StudioApiError(response.status, payload);
  }
  const declaredSize = Number(response.headers.get("Content-Length") ?? "0");
  if (Number.isFinite(declaredSize) && declaredSize > maxBytes) {
    throw new Error("Studio evidence exceeds the browser text limit");
  }
  const text = await response.text();
  if (new TextEncoder().encode(text).byteLength > maxBytes) {
    throw new Error("Studio evidence exceeds the browser text limit");
  }
  return text;
}

/** Fetch one exact bounded byte response without unbounded body helpers.
 *
 * Args:
 *   path: A caller-validated Studio capability path.
 *   options: Expected MIME/size, policy ceiling, optional Accept header, and
 *     cancellation signal.
 *
 * Raises:
 *   StudioApiError: The backend returned its stable error envelope.
 *   StudioBoundedByteError: Headers, stream, or byte counts fail closed.
 *   DOMException: The caller aborted the request.
 *
 * Returns:
 *   A newly owned byte array whose declared and actual sizes are exact.
 */
export async function studioBoundedByteRequest(
  path: string,
  options: StudioBoundedByteRequest,
): Promise<Uint8Array> {
  const expectedContentType = normalizeContentType(options.expectedContentType);
  if (
    expectedContentType.length === 0
    || !Number.isSafeInteger(options.expectedBytes)
    || options.expectedBytes < 0
    || !Number.isSafeInteger(options.maxBytes)
    || options.maxBytes < 0
  ) {
    throw new StudioBoundedByteError("invalid-contract");
  }
  if (options.expectedBytes > options.maxBytes) {
    throw new StudioBoundedByteError("oversized");
  }

  const response = await fetch(studioApiUrl(path), {
    headers: { Accept: options.accept ?? expectedContentType },
    signal: options.signal,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as StudioApiErrorShape;
    throw new StudioApiError(response.status, payload);
  }
  if (
    normalizeContentType(response.headers.get("Content-Type") ?? "")
    !== expectedContentType
  ) {
    await response.body?.cancel().catch(() => undefined);
    throw new StudioBoundedByteError("mime-mismatch");
  }

  const contentLength = response.headers.get("Content-Length");
  if (
    contentLength === null
    || !/^(0|[1-9]\d*)$/.test(contentLength)
    || Number(contentLength) !== options.expectedBytes
  ) {
    await response.body?.cancel().catch(() => undefined);
    throw new StudioBoundedByteError("size-mismatch");
  }
  if (response.body === null) {
    throw new StudioBoundedByteError("body-unavailable");
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  try {
    while (true) {
      const result = await reader.read();
      if (result.done) break;
      received += result.value.byteLength;
      if (
        received > options.expectedBytes
        || received > options.maxBytes
      ) {
        await reader.cancel().catch(() => undefined);
        throw new StudioBoundedByteError(
          received > options.maxBytes ? "oversized" : "size-mismatch",
        );
      }
      chunks.push(result.value);
    }
  } catch (error) {
    if (options.signal?.aborted) throw abortError();
    throw error;
  } finally {
    reader.releaseLock();
  }
  if (received !== options.expectedBytes) {
    throw new StudioBoundedByteError("size-mismatch");
  }

  const bytes = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

/** Verify one exact Studio capability through a no-body HEAD request.
 *
 * Args:
 *   path: A strict same-service Studio capability.
 *   options: Expected media, exact bytes, and optional cancellation signal.
 *
 * Raises:
 *   StudioApiError: The backend rejected the managed resource.
 *   StudioHeadContractError: Capability or response headers fail closed.
 *   DOMException: The caller aborted the request.
 *
 * Returns:
 *   Validated attachment metadata; no response body is read or allocated.
 */
export async function studioHeadRequest(
  path: string,
  options: StudioHeadRequest,
): Promise<StudioHeadResponse> {
  if (!isStrictStudioCapability(path)) {
    throw new StudioHeadContractError("invalid-capability");
  }
  const expectedContentType = normalizeContentType(options.expectedContentType);
  if (
    expectedContentType.length === 0
    || !Number.isSafeInteger(options.expectedBytes)
    || options.expectedBytes < 0
  ) {
    throw new StudioHeadContractError("invalid-contract");
  }
  const response = await fetch(studioApiUrl(path), {
    method: "HEAD",
    headers: { Accept: expectedContentType },
    signal: options.signal,
  });
  if (!response.ok) {
    throw new StudioApiError(response.status, {});
  }
  const contentType = normalizeContentType(
    response.headers.get("Content-Type") ?? "",
  );
  if (contentType !== expectedContentType) {
    throw new StudioHeadContractError("mime-mismatch");
  }
  const rawLength = response.headers.get("Content-Length");
  if (
    rawLength === null
    || !/^(0|[1-9]\d*)$/.test(rawLength)
    || Number(rawLength) !== options.expectedBytes
  ) {
    throw new StudioHeadContractError("size-mismatch");
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /^attachment; filename="([A-Za-z0-9][A-Za-z0-9._-]{0,199})"$/
    .exec(disposition);
  if (!match) {
    throw new StudioHeadContractError("disposition-mismatch");
  }
  const responseDigest = response.headers.get("X-Content-SHA256");
  if (
    options.expectedSha256 !== undefined
    && (
      !/^sha256:[a-f0-9]{64}$/.test(options.expectedSha256)
      || responseDigest !== options.expectedSha256
    )
  ) {
    throw new StudioHeadContractError("digest-mismatch");
  }
  return {
    contentType,
    contentLength: Number(rawLength),
    filename: match[1]!,
    ...(options.expectedSha256 === undefined
      ? {}
      : { sha256: options.expectedSha256 }),
  };
}

/** Normalize an HTTP media type while discarding optional parameters. */
function normalizeContentType(value: string): string {
  return value.split(";", 1)[0]!.trim().toLowerCase();
}

/** Accept only local versioned Studio paths without query or traversal syntax. */
function isStrictStudioCapability(path: string): boolean {
  const normalized = path.startsWith("/api/") ? path.slice(4) : path;
  return (
    normalized.startsWith("/studio/")
    && !normalized.includes("?")
    && !normalized.includes("#")
    && !normalized.includes("\\")
    && !normalized.split("/").includes("..")
  );
}

/** Build a browser-compatible abort exception without exposing response data. */
function abortError(): DOMException {
  return new DOMException("The request was aborted.", "AbortError");
}
