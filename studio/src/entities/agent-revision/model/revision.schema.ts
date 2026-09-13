import {
  parseStudioAuthoringDocument,
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
    ? (cloneJson(value.compileSnapshot.diagnostics) as unknown as StudioDiagnostic[])
    : [];
  const sourceMap = Array.isArray(value.compileSnapshot.sourceMap)
    ? (cloneJson(value.compileSnapshot.sourceMap) as unknown as StudioSourceMapEntry[])
    : [];
  const compileSnapshot: AgentRevision["compileSnapshot"] = {
    status,
    diagnostics,
    sourceMap,
    projectionMap: Array.isArray(value.compileSnapshot.projectionMap)
      ? (cloneJson(value.compileSnapshot.projectionMap) as unknown as StudioProjectionEntry[])
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
