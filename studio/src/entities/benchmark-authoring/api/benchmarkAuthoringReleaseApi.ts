import {
  studioApiUrl,
  studioHeadRequest,
  studioRequest,
  type StudioHeadResponse,
} from "@/shared/api";
import {
  parseBenchmarkExportResult,
  parseBenchmarkFreezeResult,
  parseBenchmarkPackageExport,
  parseBenchmarkPackagePublication,
  parseBenchmarkPackageRevisionPage,
  parseBenchmarkPublicationResult,
  parseBenchmarkReleaseCommand,
  type BenchmarkExportResult,
  type BenchmarkFreezeResult,
  type BenchmarkPackageExport,
  type BenchmarkPackagePublication,
  type BenchmarkPackageRevisionPage,
  type BenchmarkPublicationResult,
  type BenchmarkReleaseCommand,
} from "../model/benchmarkAuthoringRelease.schema";

export type BenchmarkPackageRevisionListInput = {
  draftId: string;
  limit?: number;
  cursor?: string | null;
};

export type FreezeBenchmarkDraftInput = {
  draftId: string;
  revisionId: string;
  command: BenchmarkReleaseCommand;
  signal?: AbortSignal;
};

export type BenchmarkPackageReleaseInput = {
  draftId: string;
  packageRevisionId: string;
  command: BenchmarkReleaseCommand;
  signal?: AbortSignal;
};

export type BenchmarkPublicationReadInput = {
  draftId: string;
  packageRevisionId: string;
  publicationId: string;
};

export type BenchmarkExportReadInput = {
  draftId: string;
  packageRevisionId: string;
  exportId: string;
};

/** Build the exact immutable Package-revision route under its owning draft. */
function packageRevisionPath(draftId: string, packageRevisionId?: string) {
  const collection =
    `/studio/benchmark-authoring/drafts/${encodeURIComponent(draftId)}`
    + "/package-revisions";
  return packageRevisionId
    ? `${collection}/${encodeURIComponent(packageRevisionId)}`
    : collection;
}

/** List one bounded draft-scoped page of immutable release candidates. */
export async function listBenchmarkPackageRevisions(
  input: BenchmarkPackageRevisionListInput,
  signal?: AbortSignal,
): Promise<BenchmarkPackageRevisionPage> {
  const query = new URLSearchParams({ limit: String(input.limit ?? 30) });
  if (input.cursor) query.set("cursor", input.cursor);
  return parseBenchmarkPackageRevisionPage(
    await studioRequest(
      `${packageRevisionPath(input.draftId)}?${query.toString()}`,
      { signal },
    ),
  );
}

/** Freeze one clean exact-current authoring revision without publishing it. */
export async function freezeBenchmarkDraft(
  input: FreezeBenchmarkDraftInput,
): Promise<BenchmarkFreezeResult> {
  const command = parseBenchmarkReleaseCommand(input.command);
  return parseBenchmarkFreezeResult(
    await studioRequest(packageRevisionPath(input.draftId), {
      method: "POST",
      body: JSON.stringify({ ...command, revisionId: input.revisionId }),
      signal: input.signal,
    }),
  );
}

/** Publish one exact immutable Package revision to managed Catalog. */
export async function publishBenchmarkPackage(
  input: BenchmarkPackageReleaseInput,
): Promise<BenchmarkPublicationResult> {
  const command = parseBenchmarkReleaseCommand(input.command);
  return parseBenchmarkPublicationResult(
    await studioRequest(
      `${packageRevisionPath(input.draftId, input.packageRevisionId)}/publications`,
      {
        method: "POST",
        body: JSON.stringify(command),
        signal: input.signal,
      },
    ),
  );
}

/** Export one exact immutable Package revision as deterministic ZIP bytes. */
export async function exportBenchmarkPackage(
  input: BenchmarkPackageReleaseInput,
): Promise<BenchmarkExportResult> {
  const command = parseBenchmarkReleaseCommand(input.command);
  return parseBenchmarkExportResult(
    await studioRequest(
      `${packageRevisionPath(input.draftId, input.packageRevisionId)}/exports`,
      {
        method: "POST",
        body: JSON.stringify(command),
        signal: input.signal,
      },
    ),
  );
}

/** Read one exact scoped managed publication. */
export async function getBenchmarkPackagePublication(
  input: BenchmarkPublicationReadInput,
  signal?: AbortSignal,
): Promise<BenchmarkPackagePublication> {
  return parseBenchmarkPackagePublication(
    await studioRequest(
      `${packageRevisionPath(input.draftId, input.packageRevisionId)}`
      + `/publications/${encodeURIComponent(input.publicationId)}`,
      { signal },
    ),
  );
}

/** Read one exact scoped deterministic export descriptor. */
export async function getBenchmarkPackageExport(
  input: BenchmarkExportReadInput,
  signal?: AbortSignal,
): Promise<BenchmarkPackageExport> {
  return parseBenchmarkPackageExport(
    await studioRequest(
      `${packageRevisionPath(input.draftId, input.packageRevisionId)}`
      + `/exports/${encodeURIComponent(input.exportId)}`,
      { signal },
    ),
  );
}

/** Verify exact export headers before native browser download handoff. */
export async function prepareBenchmarkPackageDownload(
  packageExport: BenchmarkPackageExport,
  signal?: AbortSignal,
): Promise<StudioHeadResponse> {
  const prepared = await studioHeadRequest(packageExport.contentLink, {
    expectedContentType: packageExport.archiveMediaType,
    expectedBytes: packageExport.size,
    expectedSha256: packageExport.sha256,
    signal,
  });
  if (prepared.filename !== packageExport.filename) {
    throw new Error("Prepared Benchmark Package filename differs from metadata");
  }
  return prepared;
}

/** Hand an exact server-provided capability to the browser download manager. */
export function handoffBenchmarkPackageDownload(
  packageExport: BenchmarkPackageExport,
): void {
  const verified = parseBenchmarkPackageExport(packageExport);
  const anchor = document.createElement("a");
  anchor.href = studioApiUrl(verified.contentLink);
  anchor.rel = "noopener";
  anchor.download = "";
  anchor.click();
}
