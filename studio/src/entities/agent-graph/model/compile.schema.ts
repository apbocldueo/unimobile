import { cloneJson, isRecord, requireNumber, requireString, type JsonValue } from "@/shared/lib";

export type StudioDiagnostic = {
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  path?: (string | number)[];
  sourceId?: string;
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
  logicalNodePath?: string;
  contractPortId?: string;
  propertyPath?: string;
  [key: string]: JsonValue | undefined;
};

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
    if (!['node', 'edge', 'path'].includes(String(item.graphKind))) {
      throw new Error(`${itemPath}.graphKind is unsupported`);
    }
    if (!['capability', 'relation', 'input', 'output', 'graph_policy', 'unmapped'].includes(String(item.owner.kind))) {
      throw new Error(`${itemPath}.owner.kind is unsupported`);
    }
    return {
      graphKind: item.graphKind as StudioProjectionEntry['graphKind'],
      graphId: requireString(item.graphId, `${itemPath}.graphId`),
      owner: {
        kind: item.owner.kind as StudioProjectionEntry['owner']['kind'],
        ...(typeof item.owner.ownerId === 'string' ? { ownerId: item.owner.ownerId } : {}),
      },
      propertyPath: Array.isArray(item.propertyPath)
        ? item.propertyPath.map((part) => {
            if (typeof part !== 'string' && typeof part !== 'number') {
              throw new Error(`${itemPath}.propertyPath is invalid`);
            }
            return part;
          })
        : [],
    };
  });
}

function parseDiagnostic(value: unknown, index: number): StudioDiagnostic {
  if (!isRecord(value)) throw new Error(`diagnostics[${index}] must be an object`);
  const severity = value.severity;
  if (severity !== "error" && severity !== "warning" && severity !== "info") {
    throw new Error(`diagnostics[${index}].severity is unsupported`);
  }
  return {
    code: requireString(value.code, `diagnostics[${index}].code`),
    severity,
    message: requireString(value.message, `diagnostics[${index}].message`),
    ...(Array.isArray(value.path)
      ? {
          path: value.path.map((item, pathIndex) => {
            if (typeof item !== "string" && typeof item !== "number") {
              throw new Error(`diagnostics[${index}].path[${pathIndex}] is invalid`);
            }
            return item;
          }),
        }
      : {}),
    ...(typeof value.source_id === "string"
      ? { sourceId: value.source_id }
      : typeof value.sourceId === "string"
        ? { sourceId: value.sourceId }
        : {}),
    ...(isRecord(value.details)
      ? { details: cloneJson(value.details) as Record<string, JsonValue> }
      : {}),
  };
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
    sourceMap: value.sourceMap.map((item, index) => {
      if (!isRecord(item)) throw new Error(`sourceMap[${index}] must be an object`);
      const cloned = cloneJson(item, `sourceMap[${index}]`) as Record<string, JsonValue>;
      return {
        ...cloned,
        ...(typeof item.source_id === "string" ? { sourceId: item.source_id } : {}),
        ...(typeof item.source_kind === "string" ? { sourceKind: item.source_kind } : {}),
        ...(typeof item.source_path === "string" ? { sourcePath: item.source_path } : {}),
        ...(typeof item.document_id === "string" ? { documentId: item.document_id } : {}),
        ...(Array.isArray(item.canvas_path)
          ? {
              canvasPath: item.canvas_path.filter(
                (part): part is string => typeof part === "string",
              ),
            }
          : {}),
        ...(typeof item.canvas_node_id === "string"
          ? { canvasNodeId: item.canvas_node_id }
          : {}),
        ...(typeof item.canvas_edge_id === "string"
          ? { canvasEdgeId: item.canvas_edge_id }
          : {}),
        ...(typeof item.logical_node_path === "string"
          ? { logicalNodePath: item.logical_node_path }
          : {}),
        ...(typeof item.contract_port_id === "string"
          ? { contractPortId: item.contract_port_id }
          : {}),
        ...(typeof item.property_path === "string"
          ? { propertyPath: item.property_path }
          : {}),
      };
    }),
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
