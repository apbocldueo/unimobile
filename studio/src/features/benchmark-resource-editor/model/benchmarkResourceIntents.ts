export type BenchmarkResourceUploadSemantic = {
  operation: "upload";
  draftId: string;
  baseRevisionId: string;
  resourceId: string;
  kind: "asset" | "ground_truth";
  path: string;
  mediaType: string;
  file: File;
};

export type BenchmarkResourceReplaceSemantic = {
  operation: "replace";
  draftId: string;
  baseRevisionId: string;
  resourceId: string;
  mediaType: string;
  file: File;
};

export type BenchmarkResourceRemoveSemantic = {
  operation: "remove";
  draftId: string;
  baseRevisionId: string;
  resourceId: string;
};

export type BenchmarkResourceCommandSemantic =
  | BenchmarkResourceUploadSemantic
  | BenchmarkResourceReplaceSemantic
  | BenchmarkResourceRemoveSemantic;

export type BenchmarkResourceCommandIntent = {
  clientRequestId: string;
  semantic: BenchmarkResourceCommandSemantic;
};

/** Generate one browser-owned managed-content command identity. */
export function createBenchmarkResourceIntentId(): string {
  return `benchmark-resource-${crypto.randomUUID()}`;
}

/** Compare all semantic command inputs, including the exact selected File. */
function equalResourceSemantic(
  left: BenchmarkResourceCommandSemantic,
  right: BenchmarkResourceCommandSemantic,
): boolean {
  if (
    left.operation !== right.operation
    || left.draftId !== right.draftId
    || left.baseRevisionId !== right.baseRevisionId
    || left.resourceId !== right.resourceId
  ) {
    return false;
  }
  if (left.operation === "remove" || right.operation === "remove") {
    return left.operation === "remove" && right.operation === "remove";
  }
  if (
    left.mediaType !== right.mediaType
    || left.file !== right.file
  ) {
    return false;
  }
  if (left.operation === "replace" || right.operation === "replace") {
    return left.operation === "replace" && right.operation === "replace";
  }
  return left.kind === right.kind && left.path === right.path;
}

/**
 * Reuse only an unchanged uncertain resource command.
 *
 * Args:
 *   current: Previous unconfirmed intent, if any.
 *   semantic: Exact operation, owner, base, metadata, and selected file.
 *   createIdentity: Injectable durable identity generator.
 *
 * Returns:
 *   The reusable prior intent or a newly identified command.
 */
export function prepareBenchmarkResourceIntent(
  current: BenchmarkResourceCommandIntent | null,
  semantic: BenchmarkResourceCommandSemantic,
  createIdentity: () => string = createBenchmarkResourceIntentId,
): BenchmarkResourceCommandIntent {
  if (current && equalResourceSemantic(current.semantic, semantic)) {
    return current;
  }
  return { clientRequestId: createIdentity(), semantic };
}
