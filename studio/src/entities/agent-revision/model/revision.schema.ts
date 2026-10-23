import {
  parseStudioAuthoringDocument,
  parseDiagnostic,
  parseStudioSourceMap,
  parseStudioProjectionMap,
  type StudioAuthoringDocument,
  type StudioProjectionEntry,
  type StudioDiagnostic,
  type StudioSourceMapEntry,
} from "@/entities/agent-graph";
import { cloneJson, isRecord, requireNumber, requireString, type JsonValue } from "@/shared/lib";

export type AgentRevision = {
  revisionId: string;
  agentId: string;
  ordinal: number;
  parentRevisionId: string | null;
  document: StudioAuthoringDocument;
  compileSnapshot: {
    status: "valid" | "invalid";
    diagnostics: StudioDiagnostic[];
    sourceMap: StudioSourceMapEntry[];
    agentGraph?: Record<string, JsonValue>;
    canonicalHash?: string;
    authoringPolicy?: string;
    loweringProfile?: string;
    capabilityHash?: string;
    projectionMap?: StudioProjectionEntry[];
  };
  createdAt: number;
};

/** Parse one immutable Agent revision returned by the repository API. */
export function parseAgentRevision(value: unknown, path = "revision"): AgentRevision {
  if (!isRecord(value) || !isRecord(value.compileSnapshot)) {
    throw new Error(`${path} must contain compileSnapshot`);
  }
  const status = value.compileSnapshot.status;
  if (status !== "valid" && status !== "invalid") {
    throw new Error(`${path}.compileSnapshot.status is unsupported`);
  }
  const diagnostics = Array.isArray(value.compileSnapshot.diagnostics)
    ? value.compileSnapshot.diagnostics.map(parseDiagnostic)
    : [];
  const sourceMap = Array.isArray(value.compileSnapshot.sourceMap)
    ? parseStudioSourceMap(value.compileSnapshot.sourceMap)
    : [];
  const compileSnapshot: AgentRevision["compileSnapshot"] = {
    status,
    diagnostics,
    sourceMap,
    projectionMap: Array.isArray(value.compileSnapshot.projectionMap)
      ? parseStudioProjectionMap(value.compileSnapshot.projectionMap)
      : [],
  };
  if (isRecord(value.compileSnapshot.agentGraph)) {
    compileSnapshot.agentGraph = cloneJson(value.compileSnapshot.agentGraph) as Record<
      string,
      JsonValue
    >;
  }
  if (typeof value.compileSnapshot.canonicalHash === "string") {
    compileSnapshot.canonicalHash = value.compileSnapshot.canonicalHash;
  }
  for (const key of ["authoringPolicy", "loweringProfile", "capabilityHash"] as const) {
    if (typeof value.compileSnapshot[key] === "string") compileSnapshot[key] = value.compileSnapshot[key];
  }
  return {
    revisionId: requireString(value.revisionId, `${path}.revisionId`),
    agentId: requireString(value.agentId, `${path}.agentId`),
    ordinal: requireNumber(value.ordinal, `${path}.ordinal`),
    parentRevisionId:
      value.parentRevisionId === null || value.parentRevisionId === undefined
        ? null
        : requireString(value.parentRevisionId, `${path}.parentRevisionId`),
    document: parseStudioAuthoringDocument(value.document),
    compileSnapshot,
    createdAt: requireNumber(value.createdAt, `${path}.createdAt`),
  };
}
