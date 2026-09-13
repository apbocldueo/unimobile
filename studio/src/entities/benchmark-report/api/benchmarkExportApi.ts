import {
  studioBoundedByteRequest,
  studioHeadRequest,
  type StudioHeadResponse,
} from "@/shared/api";
import type { BenchmarkArtifactInventoryItem } from "../model/benchmarkReport.schema";
import {
  BENCHMARK_PUBLICATION_MANIFEST_MAX_BYTES,
  parseBenchmarkPublicationManifest,
  type BenchmarkPublicationManifest,
} from "../model/benchmarkExport.schema";

/** Load one strict publication manifest through its sole scoped capability.
 *
 * Args:
 *   item: Strict Experiment-scoped publication-manifest inventory item.
 *   knownTaskRunIds: Durable TaskRuns allowed by the owning Experiment.
 *   signal: Drawer-owned cancellation signal.
 *
 * Raises:
 *   Error: Descriptor, transport, JSON, schema, or identity facts conflict.
 *   DOMException: The drawer was closed or changed scope.
 *
 * Returns:
 *   Strict publication facts without any new content capability.
 */
export async function loadBenchmarkPublicationManifest(
  item: BenchmarkArtifactInventoryItem,
  knownTaskRunIds: ReadonlySet<string>,
  signal: AbortSignal,
): Promise<BenchmarkPublicationManifest> {
  if (
    item.descriptor.kind !== "studio_publication_manifest"
    || item.descriptor.taskRunId !== null
    || item.descriptor.contentType.toLowerCase() !== "application/json"
    || item.links.content === null
  ) {
    throw new Error("Publication manifest descriptor is not readable");
  }
  const bytes = await studioBoundedByteRequest(item.links.content, {
    signal,
    expectedContentType: "application/json",
    expectedBytes: item.descriptor.size,
    maxBytes: BENCHMARK_PUBLICATION_MANIFEST_MAX_BYTES,
    accept: "application/json",
  });
  let source: string;
  try {
    source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error("Publication manifest is not valid UTF-8");
  }
  let value: unknown;
  try {
    value = JSON.parse(source);
  } catch {
    throw new Error("Publication manifest is not valid JSON");
  }
  return parseBenchmarkPublicationManifest(
    value,
    item.descriptor.experimentId,
    knownTaskRunIds,
  );
}

/** Prepare one refreshed export target through the no-body HEAD contract. */
export async function prepareBenchmarkExportTarget(
  item: BenchmarkArtifactInventoryItem,
  signal: AbortSignal,
): Promise<StudioHeadResponse> {
  if (
    item.links.content === null
    || item.descriptor.sha256 === null
    || !["available", "redacted", "truncated"].includes(
      item.descriptor.availability,
    )
  ) {
    throw new Error("Benchmark export target is not readable");
  }
  return studioHeadRequest(item.links.content, {
    signal,
    expectedContentType: item.descriptor.contentType,
    expectedBytes: item.descriptor.size,
  });
}
