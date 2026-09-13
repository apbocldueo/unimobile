import {
  cloneJson,
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
  type JsonValue,
} from "@/shared/lib";
import {
  parseExecutionEvidenceOrigin,
  type ExecutionEvidenceOrigin,
} from "@/entities/evidence-origin";
import {
  parseStudioAuthoringDocument,
  parseStudioProjectionMap,
  type StudioAuthoringDocument,
  type StudioProjectionEntry,
} from "@/entities/agent-graph";

export type EvidenceAvailabilityState =
  | "available"
  | "not_captured"
  | "excluded"
  | "hidden"
  | "missing"
  | "corrupt"
  | "redacted"
  | "truncated";

export type ReplayIntegrityState = "complete" | "partial" | "corrupt";

export type EvidenceAvailability = {
  state: EvidenceAvailabilityState;
  reasonCode: string;
  detail: string;
};

export type ReplayGraphNode = {
  id: string;
  kind: string;
  role: string;
  lifecycle: string;
  primary: boolean;
};

export type ReplayGraphEdge = {
  id: string;
  sourceNode: string;
  targetNode: string;
  kind: string;
};

export type RunSnapshot = {
  agentId: string;
  revisionId: string | null;
  contractVersion: string;
  canonicalHash: string | null;
  graphStatus: EvidenceAvailabilityState;
  agentGraph: JsonValue | null;
  graphNodes: ReplayGraphNode[];
  graphEdges: ReplayGraphEdge[];
  presentation: JsonValue | null;
  sourceMap: JsonValue[];
  authoringPolicy?: string | null;
  loweringProfile?: string | null;
  capabilityHash?: string | null;
  capabilityDocument?: StudioAuthoringDocument | null;
  projectionMap?: StudioProjectionEntry[];
  providerIdentities: string[];
};

export type RunResultSummary = {
  status: string;
  kernelStatus: string;
  error: string;
  stepCount: number;
  activationCount: number;
  interactionCount: number;
  usage: JsonValue;
};

export type ReplayListItem = {
  runId: string;
  agentId: string;
  agentStatus: string;
  benchmarkOutcome: string | null;
  provenance:
    | "real_android_excerpt"
    | "fake_contract_fixture"
    | "native_benchmark_task_run"
    | "native_replay_package"
    | "native_studio_run"
    | "legacy_benchmark_import";
  evidenceOrigin: ExecutionEvidenceOrigin;
  integrityState: ReplayIntegrityState;
  evidenceCompleteness: number;
  importedAt: number;
};

const AVAILABILITY = new Set<EvidenceAvailabilityState>([
  "available",
  "not_captured",
  "excluded",
  "hidden",
  "missing",
  "corrupt",
  "redacted",
  "truncated",
]);

/** Parse one strict evidence-availability state. */
export function parseAvailabilityState(
  value: unknown,
  path: string,
): EvidenceAvailabilityState {
  if (typeof value !== "string" || !AVAILABILITY.has(value as EvidenceAvailabilityState)) {
    throw new Error(`${path} has an unsupported availability state`);
  }
  return value as EvidenceAvailabilityState;
}

/** Parse one evidence availability record. */
export function parseEvidenceAvailability(
  value: unknown,
  path: string,
): EvidenceAvailability {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["state", "reasonCode", "detail"], path);
  return {
    state: parseAvailabilityState(value.state, `${path}.state`),
    reasonCode: typeof value.reasonCode === "string" ? value.reasonCode : "",
    detail: typeof value.detail === "string" ? value.detail : "",
  };
}

/** Parse the immutable run snapshot and derive a stable read-only topology. */
export function parseRunSnapshot(value: unknown, path = "snapshot"): RunSnapshot {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "agentId",
      "revisionId",
      "contractVersion",
      "canonicalHash",
      "graphStatus",
      "agentGraph",
      "presentation",
      "sourceMap",
      "authoringPolicy",
      "loweringProfile",
      "capabilityHash",
      "capabilityDocument",
      "projectionMap",
      "providerIdentities",
    ],
    path,
  );
  const rawGraph = value.agentGraph === null || value.agentGraph === undefined
    ? null
    : cloneJson(value.agentGraph, `${path}.agentGraph`);
  const graphRecord = isRecord(value.agentGraph) ? value.agentGraph : null;
  const rawNodes = graphRecord && Array.isArray(graphRecord.nodes) ? graphRecord.nodes : [];
  const graphNodes = rawNodes.map((node, index): ReplayGraphNode => {
    if (!isRecord(node)) throw new Error(`${path}.agentGraph.nodes[${index}] must be an object`);
    return {
      id: requireString(node.id, `${path}.agentGraph.nodes[${index}].id`),
      kind: typeof node.kind === "string" ? node.kind : "component",
      role: typeof node.role === "string" ? node.role : "",
      lifecycle: typeof node.lifecycle === "string" ? node.lifecycle : "",
      primary: node.primary === true,
    };
  });
  const rawEdges = graphRecord && Array.isArray(graphRecord.edges) ? graphRecord.edges : [];
  const graphEdges = rawEdges.map((edge, index): ReplayGraphEdge => {
    if (!isRecord(edge)) throw new Error(`${path}.agentGraph.edges[${index}] must be an object`);
    if (!isRecord(edge.source) || !isRecord(edge.target)) {
      throw new Error(`${path}.agentGraph.edges[${index}] endpoints are invalid`);
    }
    const sourceNode = requireString(edge.source.node, `${path}.agentGraph.edges[${index}].source.node`);
    const targetNode = requireString(edge.target.node, `${path}.agentGraph.edges[${index}].target.node`);
    return {
      id: `${sourceNode}:${String(edge.source.port ?? "")}->${targetNode}:${String(edge.target.port ?? "")}:${index}`,
      sourceNode,
      targetNode,
      kind: typeof edge.kind === "string" ? edge.kind : "data",
    };
  });
  return {
    agentId: typeof value.agentId === "string" ? value.agentId : "",
    revisionId: typeof value.revisionId === "string" ? value.revisionId : null,
    contractVersion: requireString(value.contractVersion, `${path}.contractVersion`),
    canonicalHash: typeof value.canonicalHash === "string" ? value.canonicalHash : null,
    graphStatus: parseAvailabilityState(value.graphStatus, `${path}.graphStatus`),
    agentGraph: rawGraph,
    graphNodes,
    graphEdges,
    presentation:
      value.presentation === null || value.presentation === undefined
        ? null
        : cloneJson(value.presentation, `${path}.presentation`),
    sourceMap: Array.isArray(value.sourceMap)
      ? value.sourceMap.map((item, index) => cloneJson(item, `${path}.sourceMap[${index}]`))
      : [],
    authoringPolicy: typeof value.authoringPolicy === "string" ? value.authoringPolicy : null,
    loweringProfile: typeof value.loweringProfile === "string" ? value.loweringProfile : null,
    capabilityHash: typeof value.capabilityHash === "string" ? value.capabilityHash : null,
    capabilityDocument:
      value.capabilityDocument === null || value.capabilityDocument === undefined
        ? null
        : parseStudioAuthoringDocument(value.capabilityDocument),
    projectionMap:
      value.projectionMap === undefined ? [] : parseStudioProjectionMap(value.projectionMap, `${path}.projectionMap`),
    providerIdentities: Array.isArray(value.providerIdentities)
      ? value.providerIdentities.map((item, index) =>
          requireString(item, `${path}.providerIdentities[${index}]`),
        )
      : [],
  };
}

/** Parse the safe terminal Agent run result independently from Benchmark. */
export function parseRunResult(
  value: unknown,
  path = "result",
): RunResultSummary {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "status",
      "kernelStatus",
      "error",
      "stepCount",
      "activationCount",
      "interactionCount",
      "usage",
    ],
    path,
  );
  return {
    status: requireString(value.status, `${path}.status`),
    kernelStatus: typeof value.kernelStatus === "string" ? value.kernelStatus : "",
    error: typeof value.error === "string" ? value.error : "",
    stepCount: requireNumber(value.stepCount, `${path}.stepCount`),
    activationCount: requireNumber(value.activationCount, `${path}.activationCount`),
    interactionCount: requireNumber(value.interactionCount, `${path}.interactionCount`),
    usage: cloneJson(value.usage ?? {}, `${path}.usage`),
  };
}

/** Parse one compact History row with independent Agent and Benchmark results. */
export function parseReplayListItem(
  value: unknown,
  path = "replay",
): ReplayListItem {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "runId",
      "agentId",
      "agentStatus",
      "benchmarkOutcome",
      "provenance",
      "evidenceOrigin",
      "integrityState",
      "evidenceCompleteness",
      "importedAt",
    ],
    path,
  );
  const provenance = requireString(value.provenance, `${path}.provenance`);
  if (
    ![
      "real_android_excerpt",
      "fake_contract_fixture",
      "native_benchmark_task_run",
      "native_replay_package",
      "native_studio_run",
      "legacy_benchmark_import",
    ].includes(provenance)
  ) {
    throw new Error(`${path}.provenance is unsupported`);
  }
  const integrityState = requireString(value.integrityState, `${path}.integrityState`);
  if (!["complete", "partial", "corrupt"].includes(integrityState)) {
    throw new Error(`${path}.integrityState is unsupported`);
  }
  return {
    runId: requireString(value.runId, `${path}.runId`),
    agentId: typeof value.agentId === "string" ? value.agentId : "",
    agentStatus: requireString(value.agentStatus, `${path}.agentStatus`),
    benchmarkOutcome:
      typeof value.benchmarkOutcome === "string" ? value.benchmarkOutcome : null,
    provenance: provenance as ReplayListItem["provenance"],
    evidenceOrigin: parseExecutionEvidenceOrigin(
      value.evidenceOrigin,
      `${path}.evidenceOrigin`,
      provenance,
    ),
    integrityState: integrityState as ReplayIntegrityState,
    evidenceCompleteness: requireNumber(
      value.evidenceCompleteness,
      `${path}.evidenceCompleteness`,
    ),
    importedAt: requireNumber(value.importedAt, `${path}.importedAt`),
  };
}
