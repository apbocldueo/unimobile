import {
  parseBenchmarkAuthoringDocument,
  type BenchmarkAuthoringDocument,
} from "@/entities/benchmark-authoring";
import { cloneJson, isRecord, type JsonValue } from "@/shared/lib";

export type BenchmarkPackageMember =
  | { kind: "manifest"; key: "manifest"; label: "benchmark.yaml" }
  | { kind: "task"; key: string; label: string; path: string }
  | { kind: "protocol"; key: string; label: string; path: string }
  | { kind: "resource"; key: string; label: string; resourceId: string };

/** Clone and revalidate one complete authoring document. */
export function cloneAuthoringDocument(
  document: BenchmarkAuthoringDocument,
): BenchmarkAuthoringDocument {
  return parseBenchmarkAuthoringDocument(document);
}

/** Canonically order JSON mapping keys for deterministic comparison only. */
function canonicalJson(value: JsonValue): JsonValue {
  if (Array.isArray(value)) return value.map(canonicalJson);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonicalJson(item)]),
    );
  }
  return value;
}

/** Compare safe JSON by semantic content instead of insertion order. */
export function equalJson(left: JsonValue, right: JsonValue): boolean {
  return JSON.stringify(canonicalJson(left)) === JSON.stringify(canonicalJson(right));
}

/** Normalize backend-required inventory ordering without rebuilding mappings. */
export function normalizeAuthoringInventory(
  document: BenchmarkAuthoringDocument,
): BenchmarkAuthoringDocument {
  const cloned = cloneJson(document) as unknown as BenchmarkAuthoringDocument;
  cloned.taskFiles.sort((left, right) => left.path.localeCompare(right.path));
  cloned.protocolFiles.sort((left, right) => left.path.localeCompare(right.path));
  cloned.resources.sort((left, right) => left.path.localeCompare(right.path));
  return parseBenchmarkAuthoringDocument(cloned);
}

/** Enumerate stable keys for every selectable definition member. */
export function authoringMembers(
  document: BenchmarkAuthoringDocument,
): BenchmarkPackageMember[] {
  return [
    { kind: "manifest", key: "manifest", label: "benchmark.yaml" },
    ...document.taskFiles.map((file) => ({
      kind: "task" as const,
      key: `task:${file.path}`,
      label: file.path,
      path: file.path,
    })),
    ...document.protocolFiles.map((file) => ({
      kind: "protocol" as const,
      key: `protocol:${file.path}`,
      label: file.path,
      path: file.path,
    })),
    ...document.resources.map((resource) => ({
      kind: "resource" as const,
      key: `resource:${resource.id}`,
      label: resource.path,
      resourceId: resource.id,
    })),
  ];
}

/** Return a stable selected member or fall back to the manifest. */
export function selectedAuthoringMember(
  document: BenchmarkAuthoringDocument,
  selectedKey: string,
): BenchmarkPackageMember {
  return (
    authoringMembers(document).find((member) => member.key === selectedKey)
    ?? { kind: "manifest", key: "manifest", label: "benchmark.yaml" }
  );
}

/** Immutably replace one nested path while preserving untouched JSON siblings.
 *
 * Args:
 *   source: Safe JSON root.
 *   path: Existing or new object/array path to replace.
 *   value: Safe replacement value.
 *
 * Raises:
 *   Error: A path segment traverses a primitive or an invalid array index.
 *
 * Returns:
 *   A detached JSON root with only the selected path replaced.
 */
export function patchJsonPath(
  source: JsonValue,
  path: readonly (string | number)[],
  value: JsonValue,
): JsonValue {
  if (path.length === 0) return cloneJson(value);
  const [head, ...tail] = path;
  if (typeof head === "number") {
    if (!Array.isArray(source) || !Number.isSafeInteger(head) || head < 0) {
      throw new Error("JSON path does not address an array index");
    }
    const output = source.map((item) => cloneJson(item));
    if (head > output.length) throw new Error("JSON array path is out of range");
    const current = output[head] ?? null;
    output[head] = patchJsonPath(current, tail, value);
    return output;
  }
  if (!isRecord(source)) {
    throw new Error("JSON path does not address an object field");
  }
  const output = cloneJson(source);
  if (!isRecord(output)) throw new Error("JSON object clone failed");
  output[head] = patchJsonPath(output[head] ?? null, tail, value);
  return output as Record<string, JsonValue>;
}

/** Patch one known manifest path without closing its extension mapping. */
export function patchManifest(
  document: BenchmarkAuthoringDocument,
  path: readonly (string | number)[],
  value: JsonValue,
): BenchmarkAuthoringDocument {
  const cloned = cloneAuthoringDocument(document);
  const patched = patchJsonPath(cloned.manifest.document, path, value);
  if (!isRecord(patched)) throw new Error("manifest must remain a mapping");
  cloned.manifest.document = patched as Record<string, JsonValue>;
  return parseBenchmarkAuthoringDocument(cloned);
}

/** Patch one known Protocol path while retaining unknown safe fields. */
export function patchProtocol(
  document: BenchmarkAuthoringDocument,
  protocolPath: string,
  path: readonly (string | number)[],
  value: JsonValue,
): BenchmarkAuthoringDocument {
  const cloned = cloneAuthoringDocument(document);
  const protocol = cloned.protocolFiles.find((item) => item.path === protocolPath);
  if (!protocol) throw new Error("Protocol member does not exist");
  const patched = patchJsonPath(protocol.document, path, value);
  if (!isRecord(patched)) throw new Error("Protocol must remain a mapping");
  protocol.document = patched as Record<string, JsonValue>;
  return parseBenchmarkAuthoringDocument(cloned);
}

/** Replace one parsed task-file array and preserve all other members. */
export function replaceTaskFileTasks(
  document: BenchmarkAuthoringDocument,
  taskPath: string,
  tasks: JsonValue[],
): BenchmarkAuthoringDocument {
  const cloned = cloneAuthoringDocument(document);
  const taskFile = cloned.taskFiles.find((item) => item.path === taskPath);
  if (!taskFile) throw new Error("Task member does not exist");
  taskFile.tasks = tasks.map((task) => cloneJson(task));
  return parseBenchmarkAuthoringDocument(cloned);
}
