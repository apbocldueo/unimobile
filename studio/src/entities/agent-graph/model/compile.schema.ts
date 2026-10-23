import { cloneJson, isRecord, requireNumber, requireString, type JsonValue } from "@/shared/lib";

export type StudioDiagnostic = {
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  path?: (string | number)[];
  sourceId?: string;
  nodeId?: string;
  edgeIndex?: number;
  portId?: string;
  details?: Record<string, JsonValue>;
};

export type StudioSourceMapEntry = {
  sourceId?: string;
  sourceKind?: string;
  sourcePath?: string;
  documentId?: string;
  canvasPath?: string[];
  canvasNodeId?: string;
  canvasEdgeId?: string;
  logicalNodePath?: string | string[];
  contractPortId?: string;
  propertyPath?: string | (string | number)[];
  [key: string]: JsonValue | undefined;
};

/** Preserve a structural path without dropping malformed segments.
 * Args: value is an optional transport path; label identifies only the field.
 * Raises: A value-free error on non-array paths or invalid indices.
 * Returns: A fresh path with nonnegative integer indices.
 */
function structuralPath(value: unknown, label: string): (string | number)[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array`);
  return value.map((part) => {
    if (typeof part !== "string" && !(typeof part === "number" && Number.isSafeInteger(part) && part >= 0)) throw new Error(`${label} has an invalid segment`);
    return part;
  });
}

export type StudioProjectionEntry = {
  graphKind: "node" | "edge" | "path";
  graphId: string;
  owner: {
    kind: "capability" | "relation" | "input" | "output" | "graph_policy" | "unmapped";
    ownerId?: string;
  };
  propertyPath: (string | number)[];
};

export type StudioCompileResult = {
  schemaVersion: 1;
  isSuccess: boolean;
  contractVersion: "1.1";
  catalogVersion: string;
  canonicalHash: string | null;
  agentGraph: Record<string, JsonValue> | null;
  diagnostics: StudioDiagnostic[];
  sourceMap: StudioSourceMapEntry[];
  authoringPolicy?: string | null;
  loweringProfile?: string | null;
  capabilityHash?: string | null;
  projectionMap?: StudioProjectionEntry[];
  summary: {
    errorCount: number;
    warningCount: number;
    nodeCount: number;
    edgeCount: number;
  };
};

/** Parse the persisted runtime-to-authoring projection without guessing owners. */
export function parseStudioProjectionMap(
  value: unknown,
  path = "projectionMap",
): StudioProjectionEntry[] {
  if (!Array.isArray(value)) throw new Error(`${path} must be an array`);
  return value.map((item, index) => {
    const itemPath = `${path}[${index}]`;
    if (!isRecord(item) || !isRecord(item.owner)) throw new Error(`${itemPath} must be an object`);
    if (typeof item.graphKind !== 'string' || !['node', 'edge', 'path'].includes(item.graphKind)) {
      throw new Error(`${itemPath}.graphKind is unsupported`);
    }
    if (typeof item.owner.kind !== 'string' || !['capability', 'relation', 'input', 'output', 'graph_policy', 'unmapped'].includes(item.owner.kind)) {
      throw new Error(`${itemPath}.owner.kind is unsupported`);
    }
    return {
      graphKind: item.graphKind as StudioProjectionEntry['graphKind'],
      graphId: requireString(item.graphId, `${itemPath}.graphId`),
      owner: {
        kind: item.owner.kind as StudioProjectionEntry['owner']['kind'],
        ...(item.owner.ownerId == null ? {} : { ownerId: requireString(item.owner.ownerId, `${itemPath}.owner.ownerId`) }),
      },
      propertyPath: item.propertyPath == null ? [] : structuralPath(item.propertyPath, `${itemPath}.propertyPath`),
    };
  });
}

/** Parse optional snake/camel locator aliases without silently dropping malformed data.
 * Raises: A field-only error on conflicting or malformed aliases.
 * Returns: A normalized string or nonnegative integer, or undefined when absent.
 */
function locator(value: Record<string, unknown>, snake: string, camel: string, numeric = false): string | number | undefined {
  const left = value[snake];
  const right = value[camel];
  if (left != null && right != null && left !== right) throw new Error(`diagnostic.${camel} aliases conflict`);
  const result = left ?? right;
  if (result == null) return undefined;
  if (numeric ? typeof result !== "number" || !Number.isSafeInteger(result) || result < 0 : typeof result !== "string" || !result.length) {
    throw new Error(`diagnostic.${camel} is invalid`);
  }
  return result as string | number;
}

/** Parse a safe diagnostic and preserve the backend's explicit location contract. */
export function parseDiagnostic(value: unknown, index: number): StudioDiagnostic {
  if (!isRecord(value)) throw new Error(`diagnostics[${index}] must be an object`);
  const severity = value.severity;
  if (severity !== "error" && severity !== "warning" && severity !== "info") {
    throw new Error(`diagnostics[${index}].severity is unsupported`);
  }
  const nodeId = locator(value, "node_id", "nodeId") as string | undefined;
  const edgeIndex = locator(value, "edge_index", "edgeIndex", true) as number | undefined;
  const portId = locator(value, "port_id", "portId") as string | undefined;
  const sourceId = locator(value, "source_id", "sourceId") as string | undefined;
  return {
    code: requireString(value.code, `diagnostics[${index}].code`),
    severity,
    message: requireString(value.message, `diagnostics[${index}].message`),
    ...(nodeId === undefined ? {} : { nodeId }),
    ...(edgeIndex === undefined ? {} : { edgeIndex }),
    ...(portId === undefined ? {} : { portId }),
    ...(sourceId === undefined ? {} : { sourceId }),
    ...(value.path == null ? {} : { path: structuralPath(value.path, `diagnostics[${index}].path`) }),
    ...(isRecord(value.details)
      ? { details: cloneJson(value.details) as Record<string, JsonValue> }
      : {}),
  };
}

/** Normalize source maps identically for live compilation and immutable revisions.
 * Args: value is the source-map array from either transport.
 * Raises: Field-only errors for malformed structural paths or identities.
 * Returns: Normalized entries without guessing a locator.
 */
export function parseStudioSourceMap(value: unknown): StudioSourceMapEntry[] {
  if (!Array.isArray(value)) throw new Error("sourceMap must be an array");
  return value.map((item, index) => {
      if (!isRecord(item)) throw new Error(`sourceMap[${index}] must be an object`);
      const cloned = cloneJson(item, `sourceMap[${index}]`) as Record<string, JsonValue>;
      /** Normalize current tuple paths while retaining legacy string paths. */
      const sourcePath = (snake: string, camel: string, stringsOnly: boolean) => {
        if (item[snake] != null && item[camel] != null && JSON.stringify(item[snake]) !== JSON.stringify(item[camel])) throw new Error(`sourceMap[${index}].${camel} aliases conflict`);
        const value = item[snake] ?? item[camel];
        if (value == null) return undefined;
        if (typeof value === "string" && camel !== "canvasPath") return value;
        const parts = structuralPath(value, `sourceMap[${index}].${camel}`);
        if (stringsOnly && parts.some((part) => typeof part !== "string")) throw new Error(`sourceMap[${index}].${camel} is invalid`);
        return parts;
      };
      const canvasPath = sourcePath("canvas_path", "canvasPath", true) as string[] | undefined;
      const logicalNodePath = sourcePath("logical_node_path", "logicalNodePath", true) as string | string[] | undefined;
      const propertyPath = sourcePath("property_path", "propertyPath", false);
      const identities: Record<string, string> = {};
      for (const [snake, camel] of [["source_id", "sourceId"], ["document_id", "documentId"], ["canvas_node_id", "canvasNodeId"], ["canvas_edge_id", "canvasEdgeId"], ["contract_port_id", "contractPortId"]] as const) {
        const identity = locator(item, snake, camel);
        if (identity !== undefined) identities[camel] = identity as string;
      }
      return {
        ...cloned,
        ...identities,
        ...(typeof item.source_id === "string" ? { sourceId: item.source_id } : {}),
        ...(typeof item.source_kind === "string" ? { sourceKind: item.source_kind } : {}),
        ...(typeof item.source_path === "string" ? { sourcePath: item.source_path } : {}),
        ...(typeof item.document_id === "string" ? { documentId: item.document_id } : {}),
        ...(canvasPath === undefined ? {} : { canvasPath }),
        ...(typeof item.canvas_node_id === "string"
          ? { canvasNodeId: item.canvas_node_id }
          : {}),
        ...(typeof item.canvas_edge_id === "string"
          ? { canvasEdgeId: item.canvas_edge_id }
          : {}),
        ...(logicalNodePath === undefined ? {} : { logicalNodePath }),
        ...(typeof item.contract_port_id === "string"
          ? { contractPortId: item.contract_port_id }
          : {}),
        ...(propertyPath === undefined ? {} : { propertyPath }),
      };
    });
}

/** Parse the authoritative versioned compile response. */
export function parseStudioCompileResult(value: unknown): StudioCompileResult {
  if (!isRecord(value) || value.schemaVersion !== 1) {
    throw new Error("compile response schemaVersion must be 1");
  }
  if (typeof value.isSuccess !== "boolean") {
    throw new Error("compile response isSuccess must be boolean");
  }
  if (!Array.isArray(value.diagnostics) || !Array.isArray(value.sourceMap) || !Array.isArray(value.projectionMap)) {
    throw new Error("compile response diagnostics, sourceMap and projectionMap must be arrays");
  }
  if (!isRecord(value.summary)) throw new Error("compile response summary must be an object");
  return {
    schemaVersion: 1,
    isSuccess: value.isSuccess,
    contractVersion: "1.1",
    catalogVersion: requireString(value.catalogVersion, "compile.catalogVersion"),
    canonicalHash:
      value.canonicalHash === null
        ? null
        : requireString(value.canonicalHash, "compile.canonicalHash"),
    agentGraph:
      value.agentGraph === null
        ? null
        : (cloneJson(value.agentGraph, "compile.agentGraph") as Record<string, JsonValue>),
    diagnostics: value.diagnostics.map(parseDiagnostic),
    sourceMap: parseStudioSourceMap(value.sourceMap),
    authoringPolicy:
      value.authoringPolicy === null || value.authoringPolicy === undefined
        ? null
        : requireString(value.authoringPolicy, "compile.authoringPolicy"),
    loweringProfile:
      value.loweringProfile === null || value.loweringProfile === undefined
        ? null
        : requireString(value.loweringProfile, "compile.loweringProfile"),
    capabilityHash:
      value.capabilityHash === null || value.capabilityHash === undefined
        ? null
        : requireString(value.capabilityHash, "compile.capabilityHash"),
    projectionMap: parseStudioProjectionMap(value.projectionMap),
    summary: {
      errorCount: requireNumber(value.summary.errorCount, "summary.errorCount"),
      warningCount: requireNumber(value.summary.warningCount, "summary.warningCount"),
      nodeCount: requireNumber(value.summary.nodeCount, "summary.nodeCount"),
      edgeCount: requireNumber(value.summary.edgeCount, "summary.edgeCount"),
    },
  };
}
