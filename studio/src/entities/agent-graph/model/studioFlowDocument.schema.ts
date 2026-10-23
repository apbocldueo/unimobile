import {
  cloneJson,
  isRecord,
  rejectUnknownKeys,
  requireNumber,
  requireString,
  type JsonValue,
} from "@/shared/lib";

export type StudioNodeKind =
  | "component"
  | "input"
  | "output"
  | "condition"
  | "router"
  | "state"
  | "loop"
  | "subgraph";
export type StudioNodeLifecycle =
  | "on_run_start"
  | "per_step"
  | "post_action"
  | "stateful"
  | "terminal";
export type StudioEdgeKind = "data" | "control" | "feedback";

export type StudioContractRef = { id: string; version: string };
export type StudioComponentCandidate = {
  namespace: string;
  name: string;
  version: string;
  params: Record<string, JsonValue>;
  dependencies: Record<string, JsonValue>;
};
export type StudioComponentBinding = {
  policy: "single" | "fallback";
  candidates: StudioComponentCandidate[];
};
export type StudioPredicate = {
  field: string;
  operator: string;
  value?: JsonValue;
};
export type StudioPortAddress = { canvasId: string; portId: string };

export type StudioSubgraphSpec = {
  document?: LegacyStudioFlowDocument;
  reference?: Record<string, JsonValue>;
  inputs: Record<string, string>;
  outputs: Record<string, string>;
  sharedState?: string[];
  maxActivations?: number;
  errorPolicy?: string;
};

export type StudioLoopSpec = {
  body: StudioSubgraphSpec;
  inputs: Record<string, string>;
  outputs: Record<string, string>;
  until: StudioPredicate;
  maxIterations: number;
  onExhausted: string;
  maxActivations?: number;
};

export type StudioNode = {
  canvasId: string;
  logicalId: string;
  kind: StudioNodeKind;
  lifecycle: StudioNodeLifecycle;
  role?: string;
  contract?: StudioContractRef;
  component?: StudioComponentBinding;
  primary?: boolean;
  predicate?: StudioPredicate;
  execution?: Record<string, JsonValue>;
  router?: Record<string, JsonValue>;
  state?: Record<string, JsonValue>;
  loop?: StudioLoopSpec;
  subgraph?: StudioSubgraphSpec;
  metadata?: Record<string, JsonValue>;
};

export type StudioEdge = {
  canvasId: string;
  source: StudioPortAddress;
  target: StudioPortAddress;
  kind: StudioEdgeKind;
  condition?: StudioPredicate;
  feedback?: Record<string, JsonValue>;
};

export type StudioNodePresentation = {
  x: number;
  y: number;
  label?: string;
  icon?: string;
  description?: string;
  collapsed?: boolean;
  renderMode?: StudioNodeRenderMode;
};

export type StudioNodeRenderMode = "card" | "inline" | "boundary";

export type LegacyStudioFlowDocument = {
  schemaVersion: 2;
  contractVersion: "1.1";
  documentId: string;
  agentId: string;
  name: string;
  semantic: {
    profile: "mobile_agent";
    interface?: Record<string, JsonValue> | null;
    policies: Record<string, JsonValue>;
    nodes: StudioNode[];
    edges: StudioEdge[];
  };
  presentation: {
    nodes: Record<string, StudioNodePresentation>;
    viewport: { x: number; y: number; zoom: number };
    theme?: "light" | "dark" | "system" | null;
  };
  authoring: {
    description: string;
    createdAt: number;
    updatedAt: number;
  };
};

const NODE_KINDS = new Set<StudioNodeKind>([
  "component",
  "input",
  "output",
  "condition",
  "router",
  "state",
  "loop",
  "subgraph",
]);
const LIFECYCLES = new Set<StudioNodeLifecycle>([
  "on_run_start",
  "per_step",
  "post_action",
  "stateful",
  "terminal",
]);
const EDGE_KINDS = new Set<StudioEdgeKind>(["data", "control", "feedback"]);

function parseStringMap(value: unknown, path: string): Record<string, string> {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  const output: Record<string, string> = {};
  for (const [key, item] of Object.entries(value)) {
    output[key] = requireString(item, `${path}.${key}`);
  }
  return output;
}

function parseJsonRecord(value: unknown, path: string): Record<string, JsonValue> {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  const output = cloneJson(value, path) as Record<string, JsonValue>;
  assertAuthoringValueSafe(output, path);
  return output;
}

const RAW_SECRET_KEY = /(?:^|_)(?:api_key|access_token|auth_token|authorization|password|secret|secret_key)$/i;
const SECRET_REFERENCE = /^[A-Za-z][A-Za-z0-9_.-]{0,127}$/;
const WINDOWS_ABSOLUTE_PATH = /^[A-Za-z]:[\\/]/;

/** Reject resolved credentials and host paths before authoring JSON is retained. */
function assertAuthoringValueSafe(value: unknown, path: string): void {
  if (typeof value === "string") {
    if (value.startsWith("/") || value.startsWith("\\\\") || WINDOWS_ABSOLUTE_PATH.test(value)) {
      throw new Error(`${path} must not contain a host absolute path`);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertAuthoringValueSafe(item, `${path}[${index}]`));
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, item] of Object.entries(value)) {
    if (RAW_SECRET_KEY.test(key)) {
      const safeObject = isRecord(item) && Object.keys(item).length === 1 &&
        SECRET_REFERENCE.test(String(item.secret_ref ?? ""));
      const safeVariable = typeof item === "string" && /^\$\{[A-Za-z_][A-Za-z0-9_.-]*\}$/.test(item);
      if (!safeObject && !safeVariable) {
        throw new Error(`${path}.${key} must use a secret reference`);
      }
    }
    assertAuthoringValueSafe(item, `${path}.${key}`);
  }
}

function parsePredicate(value: unknown, path: string): StudioPredicate {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["field", "operator", "value"], path);
  const predicate: StudioPredicate = {
    field: requireString(value.field, `${path}.field`),
    operator: requireString(value.operator, `${path}.operator`),
  };
  if ("value" in value) predicate.value = cloneJson(value.value, `${path}.value`);
  return predicate;
}

function parseContract(value: unknown, path: string): StudioContractRef {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["id", "version"], path);
  return {
    id: requireString(value.id, `${path}.id`),
    version: requireString(value.version, `${path}.version`),
  };
}

function parseBinding(value: unknown, path: string): StudioComponentBinding {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["policy", "candidates"], path);
  if (value.policy !== "single" && value.policy !== "fallback") {
    throw new Error(`${path}.policy is unsupported`);
  }
  if (!Array.isArray(value.candidates) || value.candidates.length === 0) {
    throw new Error(`${path}.candidates must be a non-empty array`);
  }
  if (value.policy === "single" && value.candidates.length !== 1) {
    throw new Error(`${path}.candidates must contain exactly one single implementation`);
  }
  if (value.policy === "fallback" && value.candidates.length < 2) {
    throw new Error(`${path}.candidates must contain at least two fallback implementations`);
  }
  const candidates = value.candidates.map((candidate, index) => {
    const candidatePath = `${path}.candidates[${index}]`;
    if (!isRecord(candidate)) throw new Error(`${candidatePath} must be an object`);
    rejectUnknownKeys(
      candidate,
      ["namespace", "name", "version", "params", "dependencies"],
      candidatePath,
    );
    return {
      namespace: requireString(candidate.namespace, `${candidatePath}.namespace`),
      name: requireString(candidate.name, `${candidatePath}.name`),
      version: requireString(candidate.version, `${candidatePath}.version`),
      params: parseJsonRecord(candidate.params ?? {}, `${candidatePath}.params`),
      dependencies: parseJsonRecord(
        candidate.dependencies ?? {},
        `${candidatePath}.dependencies`,
      ),
    };
  });
  return { policy: value.policy, candidates };
}

function parseSubgraph(value: unknown, path: string): StudioSubgraphSpec {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "document",
      "reference",
      "inputs",
      "outputs",
      "sharedState",
      "maxActivations",
      "errorPolicy",
    ],
    path,
  );
  const output: StudioSubgraphSpec = {
    inputs: parseStringMap(value.inputs ?? {}, `${path}.inputs`),
    outputs: parseStringMap(value.outputs ?? {}, `${path}.outputs`),
  };
  if (value.document !== undefined) output.document = parseLegacyStudioFlowDocument(value.document);
  if (value.reference !== undefined) {
    output.reference = parseJsonRecord(value.reference, `${path}.reference`);
  }
  if ((output.document === undefined) === (output.reference === undefined)) {
    throw new Error(`${path} requires exactly one document or reference`);
  }
  if (value.sharedState !== undefined) {
    if (!Array.isArray(value.sharedState)) throw new Error(`${path}.sharedState must be an array`);
    output.sharedState = value.sharedState.map((item, index) =>
      requireString(item, `${path}.sharedState[${index}]`),
    );
  }
  if (value.maxActivations !== undefined) {
    output.maxActivations = requireNumber(value.maxActivations, `${path}.maxActivations`);
  }
  if (value.errorPolicy !== undefined) {
    output.errorPolicy = requireString(value.errorPolicy, `${path}.errorPolicy`);
  }
  return output;
}

function parseLoop(value: unknown, path: string): StudioLoopSpec {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["body", "inputs", "outputs", "until", "maxIterations", "onExhausted", "maxActivations"],
    path,
  );
  const output: StudioLoopSpec = {
    body: parseSubgraph(value.body, `${path}.body`),
    inputs: parseStringMap(value.inputs ?? {}, `${path}.inputs`),
    outputs: parseStringMap(value.outputs ?? {}, `${path}.outputs`),
    until: parsePredicate(value.until, `${path}.until`),
    maxIterations: requireNumber(value.maxIterations, `${path}.maxIterations`),
    onExhausted: requireString(value.onExhausted, `${path}.onExhausted`),
  };
  if (value.maxActivations !== undefined) {
    output.maxActivations = requireNumber(value.maxActivations, `${path}.maxActivations`);
  }
  return output;
}

function parseNode(value: unknown, index: number): StudioNode {
  const path = `semantic.nodes[${index}]`;
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    [
      "canvasId",
      "logicalId",
      "kind",
      "lifecycle",
      "role",
      "contract",
      "component",
      "primary",
      "predicate",
      "execution",
      "router",
      "state",
      "loop",
      "subgraph",
      "metadata",
    ],
    path,
  );
  if (typeof value.kind !== "string" || !NODE_KINDS.has(value.kind as StudioNodeKind)) {
    throw new Error(`${path}.kind is unsupported`);
  }
  if (
    typeof value.lifecycle !== "string" ||
    !LIFECYCLES.has(value.lifecycle as StudioNodeLifecycle)
  ) {
    throw new Error(`${path}.lifecycle is unsupported`);
  }
  const node: StudioNode = {
    canvasId: requireString(value.canvasId, `${path}.canvasId`),
    logicalId: requireString(value.logicalId, `${path}.logicalId`),
    kind: value.kind as StudioNodeKind,
    lifecycle: value.lifecycle as StudioNodeLifecycle,
  };
  if (value.role !== undefined) node.role = requireString(value.role, `${path}.role`);
  if (value.contract !== undefined) node.contract = parseContract(value.contract, `${path}.contract`);
  if (value.component !== undefined) {
    node.component = parseBinding(value.component, `${path}.component`);
  }
  if (value.primary !== undefined) {
    if (typeof value.primary !== "boolean") throw new Error(`${path}.primary must be boolean`);
    node.primary = value.primary;
  }
  if (value.predicate !== undefined) {
    node.predicate = parsePredicate(value.predicate, `${path}.predicate`);
  }
  for (const field of ["execution", "router", "state", "metadata"] as const) {
    if (value[field] !== undefined) {
      node[field] = parseJsonRecord(value[field], `${path}.${field}`);
    }
  }
  if (value.loop !== undefined) node.loop = parseLoop(value.loop, `${path}.loop`);
  if (value.subgraph !== undefined) {
    node.subgraph = parseSubgraph(value.subgraph, `${path}.subgraph`);
  }
  if (
    node.kind === "component" &&
    ((!node.role && !node.contract) || !node.component)
  ) {
    throw new Error(`${path} component requires role or contract and component binding`);
  }
  if (node.kind === "condition" && !node.predicate) {
    throw new Error(`${path} condition requires predicate`);
  }
  if (node.kind === "router" && !node.router) throw new Error(`${path} router requires router`);
  if (node.kind === "state" && !node.state) throw new Error(`${path} state requires state`);
  if (node.kind === "loop" && !node.loop) throw new Error(`${path} loop requires loop`);
  if (node.kind === "subgraph" && !node.subgraph) {
    throw new Error(`${path} subgraph requires subgraph`);
  }
  return node;
}

function parseAddress(value: unknown, path: string): StudioPortAddress {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["canvasId", "portId"], path);
  return {
    canvasId: requireString(value.canvasId, `${path}.canvasId`),
    portId: requireString(value.portId, `${path}.portId`),
  };
}

function parseEdge(value: unknown, index: number): StudioEdge {
  const path = `semantic.edges[${index}]`;
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["canvasId", "source", "target", "kind", "condition", "feedback"], path);
  if (typeof value.kind !== "string" || !EDGE_KINDS.has(value.kind as StudioEdgeKind)) {
    throw new Error(`${path}.kind is unsupported`);
  }
  const edge: StudioEdge = {
    canvasId: requireString(value.canvasId, `${path}.canvasId`),
    source: parseAddress(value.source, `${path}.source`),
    target: parseAddress(value.target, `${path}.target`),
    kind: value.kind as StudioEdgeKind,
  };
  if (value.condition !== undefined) {
    edge.condition = parsePredicate(value.condition, `${path}.condition`);
  }
  if (value.feedback !== undefined) {
    edge.feedback = parseJsonRecord(value.feedback, `${path}.feedback`);
  }
  return edge;
}

function parsePresentation(value: unknown): LegacyStudioFlowDocument["presentation"] {
  if (!isRecord(value)) throw new Error("presentation must be an object");
  rejectUnknownKeys(value, ["nodes", "viewport", "theme"], "presentation");
  if (!isRecord(value.nodes)) throw new Error("presentation.nodes must be an object");
  const nodes: Record<string, StudioNodePresentation> = {};
  for (const [canvasId, raw] of Object.entries(value.nodes)) {
    if (!isRecord(raw)) throw new Error(`presentation.nodes.${canvasId} must be an object`);
    rejectUnknownKeys(
      raw,
      ["x", "y", "label", "icon", "description", "collapsed", "renderMode"],
      `presentation.nodes.${canvasId}`,
    );
    if (
      raw.renderMode !== undefined &&
      raw.renderMode !== "card" &&
      raw.renderMode !== "inline" &&
      raw.renderMode !== "boundary"
    ) {
      throw new Error(`presentation.nodes.${canvasId}.renderMode is unsupported`);
    }
    nodes[canvasId] = {
      x: requireNumber(raw.x ?? 0, `presentation.nodes.${canvasId}.x`),
      y: requireNumber(raw.y ?? 0, `presentation.nodes.${canvasId}.y`),
      ...(typeof raw.label === "string" ? { label: raw.label } : {}),
      ...(typeof raw.icon === "string" ? { icon: raw.icon } : {}),
      ...(typeof raw.description === "string" ? { description: raw.description } : {}),
      ...(typeof raw.collapsed === "boolean" ? { collapsed: raw.collapsed } : {}),
      ...(typeof raw.renderMode === "string"
        ? { renderMode: raw.renderMode as StudioNodeRenderMode }
        : {}),
    };
  }
  if (!isRecord(value.viewport)) throw new Error("presentation.viewport must be an object");
  rejectUnknownKeys(value.viewport, ["x", "y", "zoom"], "presentation.viewport");
  const theme =
    value.theme === "light" || value.theme === "dark" || value.theme === "system"
      ? value.theme
      : value.theme === null || value.theme === undefined
        ? undefined
        : (() => {
            throw new Error("presentation.theme is unsupported");
          })();
  return {
    nodes,
    viewport: {
      x: requireNumber(value.viewport.x ?? 0, "presentation.viewport.x"),
      y: requireNumber(value.viewport.y ?? 0, "presentation.viewport.y"),
      zoom: requireNumber(value.viewport.zoom ?? 1, "presentation.viewport.zoom"),
    },
    ...(theme ? { theme } : {}),
  };
}

/** Strictly parse a schema 2 Studio document without mutating the input. */
export function parseLegacyStudioFlowDocument(value: unknown): LegacyStudioFlowDocument {
  if (!isRecord(value)) throw new Error("document must be an object");
  rejectUnknownKeys(
    value,
    [
      "schemaVersion",
      "contractVersion",
      "documentId",
      "agentId",
      "name",
      "semantic",
      "presentation",
      "authoring",
    ],
    "document",
  );
  if (value.schemaVersion !== 2) throw new Error("document.schemaVersion must be 2");
  if (value.contractVersion !== "1.1") throw new Error("document.contractVersion must be 1.1");
  if (!isRecord(value.semantic)) throw new Error("document.semantic must be an object");
  rejectUnknownKeys(value.semantic, ["profile", "interface", "policies", "nodes", "edges"], "semantic");
  if (value.semantic.profile !== "mobile_agent") {
    throw new Error("semantic.profile must be mobile_agent");
  }
  if (!Array.isArray(value.semantic.nodes) || !Array.isArray(value.semantic.edges)) {
    throw new Error("semantic.nodes and semantic.edges must be arrays");
  }
  if (!isRecord(value.authoring)) throw new Error("document.authoring must be an object");
  rejectUnknownKeys(value.authoring, ["description", "createdAt", "updatedAt"], "authoring");
  const nodes = value.semantic.nodes.map(parseNode);
  const edges = value.semantic.edges.map(parseEdge);
  const canvasIds = new Set(nodes.map((node) => node.canvasId));
  const logicalIds = new Set(nodes.map((node) => node.logicalId));
  if (canvasIds.size !== nodes.length || logicalIds.size !== nodes.length) {
    throw new Error("semantic node canvasId and logicalId values must be unique");
  }
  return {
    schemaVersion: 2,
    contractVersion: "1.1",
    documentId: requireString(value.documentId, "document.documentId"),
    agentId: requireString(value.agentId, "document.agentId"),
    name: requireString(value.name, "document.name"),
    semantic: {
      profile: "mobile_agent",
      ...(value.semantic.interface !== undefined
        ? {
            interface:
              value.semantic.interface === null
                ? null
                : parseJsonRecord(value.semantic.interface, "semantic.interface"),
          }
        : {}),
      policies: parseJsonRecord(value.semantic.policies ?? {}, "semantic.policies"),
      nodes,
      edges,
    },
    presentation: parsePresentation(value.presentation),
    authoring: {
      description:
        typeof value.authoring.description === "string" ? value.authoring.description : "",
      createdAt: requireNumber(value.authoring.createdAt ?? 0, "authoring.createdAt"),
      updatedAt: requireNumber(value.authoring.updatedAt ?? 0, "authoring.updatedAt"),
    },
  };
}

/** Create the structurally valid empty schema 2 draft used by Agent creation. */
export function createEmptyLegacyStudioDocument(
  agentId: string,
  name: string,
  documentId: string,
): LegacyStudioFlowDocument {
  return {
    schemaVersion: 2,
    contractVersion: "1.1",
    documentId,
    agentId,
    name,
    semantic: {
      profile: "mobile_agent",
      policies: {},
      nodes: [],
      edges: [],
    },
    presentation: {
      nodes: {},
      viewport: { x: 0, y: 0, zoom: 1 },
    },
    authoring: {
      description: "",
      createdAt: 0,
      updatedAt: 0,
    },
  };
}

export const STUDIO_CAPABILITY_AUTHORING_POLICY = "studio.capability-authoring@1" as const;
export const STUDIO_CAPABILITY_LOWERING_PROFILE = "studio.mobile-agent-lowering@1" as const;
export const STUDIO_GENERATED_ID_PREFIX = "studio_generated." as const;

export type StudioCapabilityFamily =
  | "perception"
  | "planner"
  | "reasoning"
  | "memory"
  | "action_executor"
  | "verifier"
  | "grounder"
  | "tool";
export type StudioCapabilityRelationKind =
  | "data"
  | "activation"
  | "feedback"
  | "termination";
export type StudioCapabilityBoundary = {
  canvasId: string;
  logicalId: string;
  kind: "input" | "output";
};
export type StudioCapabilityEndpoint = { ownerId: string; portId: string };
export type StudioCapabilityNode = {
  canvasId: string;
  logicalId: string;
  family: StudioCapabilityFamily;
  lifecycle: StudioNodeLifecycle;
  implementation: StudioComponentBinding;
  primary?: boolean;
  metadata?: Record<string, JsonValue>;
};
export type StudioCapabilityRelation = {
  canvasId: string;
  source: StudioCapabilityEndpoint;
  target: StudioCapabilityEndpoint;
  kind: StudioCapabilityRelationKind;
  feedback?: {
    predicate: StudioPredicate;
    maxIterations: number;
    onExhausted: "fail" | "continue" | "terminate";
  };
};
export type StudioFlowDocument = {
  schemaVersion: 3;
  contractVersion: "1.1";
  authoringPolicy: typeof STUDIO_CAPABILITY_AUTHORING_POLICY;
  loweringProfile: typeof STUDIO_CAPABILITY_LOWERING_PROFILE;
  documentId: string;
  agentId: string;
  name: string;
  input: StudioCapabilityBoundary;
  output: StudioCapabilityBoundary;
  capabilities: StudioCapabilityNode[];
  relations: StudioCapabilityRelation[];
  policies: { maxSteps: number; maxFeedbackIterations: number };
  presentation: LegacyStudioFlowDocument["presentation"];
  authoring: LegacyStudioFlowDocument["authoring"];
};
export type StudioAuthoringDocument = LegacyStudioFlowDocument | StudioFlowDocument;

const CAPABILITY_FAMILIES = new Set<StudioCapabilityFamily>([
  "perception",
  "planner",
  "reasoning",
  "memory",
  "action_executor",
  "verifier",
  "grounder",
  "tool",
]);
const CAPABILITY_RELATION_KINDS = new Set<StudioCapabilityRelationKind>([
  "data",
  "activation",
  "feedback",
  "termination",
]);
const STABLE_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/;

function requireUserIdentity(value: unknown, path: string): string {
  const identity = requireString(value, path);
  if (!STABLE_ID.test(identity) || identity.startsWith(STUDIO_GENERATED_ID_PREFIX)) {
    throw new Error(`${path} must be a stable user-owned identity`);
  }
  return identity;
}

function parseCapabilityBoundary(
  value: unknown,
  expected: "input" | "output",
): StudioCapabilityBoundary {
  const path = expected;
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["canvasId", "logicalId", "kind"], path);
  if (value.kind !== expected) throw new Error(`${path}.kind must be ${expected}`);
  return {
    canvasId: requireUserIdentity(value.canvasId, `${path}.canvasId`),
    logicalId: requireUserIdentity(value.logicalId, `${path}.logicalId`),
    kind: expected,
  };
}

function parseCapabilityNode(value: unknown, index: number): StudioCapabilityNode {
  const path = `capabilities[${index}]`;
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(
    value,
    ["canvasId", "logicalId", "family", "lifecycle", "implementation", "primary", "metadata"],
    path,
  );
  if (typeof value.family !== "string" || !CAPABILITY_FAMILIES.has(value.family as StudioCapabilityFamily)) {
    throw new Error(`${path}.family is unsupported`);
  }
  if (typeof value.lifecycle !== "string" || !LIFECYCLES.has(value.lifecycle as StudioNodeLifecycle)) {
    throw new Error(`${path}.lifecycle is unsupported`);
  }
  if (value.primary !== undefined && typeof value.primary !== "boolean") {
    throw new Error(`${path}.primary must be boolean`);
  }
  return {
    canvasId: requireUserIdentity(value.canvasId, `${path}.canvasId`),
    logicalId: requireUserIdentity(value.logicalId, `${path}.logicalId`),
    family: value.family as StudioCapabilityFamily,
    lifecycle: value.lifecycle as StudioNodeLifecycle,
    implementation: parseBinding(value.implementation, `${path}.implementation`),
    ...(typeof value.primary === "boolean" ? { primary: value.primary } : {}),
    ...(value.metadata === undefined
      ? {}
      : { metadata: parseJsonRecord(value.metadata, `${path}.metadata`) }),
  };
}

function parseCapabilityEndpoint(value: unknown, path: string): StudioCapabilityEndpoint {
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["ownerId", "portId"], path);
  return {
    ownerId: requireUserIdentity(value.ownerId, `${path}.ownerId`),
    portId: requireUserIdentity(value.portId, `${path}.portId`),
  };
}

function parseCapabilityRelation(value: unknown, index: number): StudioCapabilityRelation {
  const path = `relations[${index}]`;
  if (!isRecord(value)) throw new Error(`${path} must be an object`);
  rejectUnknownKeys(value, ["canvasId", "source", "target", "kind", "feedback"], path);
  if (
    typeof value.kind !== "string" ||
    !CAPABILITY_RELATION_KINDS.has(value.kind as StudioCapabilityRelationKind)
  ) {
    throw new Error(`${path}.kind is unsupported`);
  }
  let feedback: StudioCapabilityRelation["feedback"];
  if (value.kind === "feedback") {
    if (!isRecord(value.feedback)) throw new Error(`${path}.feedback is required`);
    rejectUnknownKeys(value.feedback, ["predicate", "maxIterations", "onExhausted"], `${path}.feedback`);
    const maxIterations = requireNumber(value.feedback.maxIterations, `${path}.feedback.maxIterations`);
    if (!Number.isInteger(maxIterations) || maxIterations < 1 || maxIterations > 10) {
      throw new Error(`${path}.feedback.maxIterations must be an integer from 1 to 10`);
    }
    if (!["fail", "continue", "terminate"].includes(String(value.feedback.onExhausted))) {
      throw new Error(`${path}.feedback.onExhausted is unsupported`);
    }
    feedback = {
      predicate: parsePredicate(value.feedback.predicate, `${path}.feedback.predicate`),
      maxIterations,
      onExhausted: value.feedback.onExhausted as "fail" | "continue" | "terminate",
    };
  } else if (value.feedback !== undefined) {
    throw new Error(`${path}.feedback is allowed only for feedback relations`);
  }
  return {
    canvasId: requireUserIdentity(value.canvasId, `${path}.canvasId`),
    source: parseCapabilityEndpoint(value.source, `${path}.source`),
    target: parseCapabilityEndpoint(value.target, `${path}.target`),
    kind: value.kind as StudioCapabilityRelationKind,
    ...(feedback ? { feedback } : {}),
  };
}

/** Strictly parse the current schema-3 capability authoring contract. */
export function parseStudioFlowDocument(value: unknown): StudioFlowDocument {
  if (!isRecord(value)) throw new Error("document must be an object");
  rejectUnknownKeys(
    value,
    [
      "schemaVersion", "contractVersion", "authoringPolicy", "loweringProfile",
      "documentId", "agentId", "name", "input", "output", "capabilities",
      "relations", "policies", "presentation", "authoring",
    ],
    "document",
  );
  if (value.schemaVersion !== 3) throw new Error("document.schemaVersion must be 3");
  if (value.contractVersion !== "1.1") throw new Error("document.contractVersion must be 1.1");
  if (value.authoringPolicy !== STUDIO_CAPABILITY_AUTHORING_POLICY) {
    throw new Error("document.authoringPolicy is unsupported");
  }
  if (value.loweringProfile !== STUDIO_CAPABILITY_LOWERING_PROFILE) {
    throw new Error("document.loweringProfile is unsupported");
  }
  if (!Array.isArray(value.capabilities) || !Array.isArray(value.relations)) {
    throw new Error("document capabilities and relations must be arrays");
  }
  if (!isRecord(value.policies)) throw new Error("document.policies must be an object");
  rejectUnknownKeys(value.policies, ["maxSteps", "maxFeedbackIterations"], "policies");
  const maxSteps = requireNumber(value.policies.maxSteps ?? 15, "policies.maxSteps");
  const maxFeedbackIterations = requireNumber(
    value.policies.maxFeedbackIterations ?? 10,
    "policies.maxFeedbackIterations",
  );
  if (!Number.isInteger(maxSteps) || maxSteps < 1 || maxSteps > 10_000) {
    throw new Error("policies.maxSteps must be a bounded positive integer");
  }
  if (
    !Number.isInteger(maxFeedbackIterations) ||
    maxFeedbackIterations < 0 ||
    maxFeedbackIterations > 1_000
  ) {
    throw new Error("policies.maxFeedbackIterations must be a bounded integer");
  }
  if (!isRecord(value.authoring)) throw new Error("document.authoring must be an object");
  rejectUnknownKeys(value.authoring, ["description", "createdAt", "updatedAt"], "authoring");
  const input = parseCapabilityBoundary(value.input, "input");
  const output = parseCapabilityBoundary(value.output, "output");
  const capabilities = value.capabilities.map(parseCapabilityNode);
  const relations = value.relations.map(parseCapabilityRelation);
  const objects = [input, output, ...capabilities];
  if (new Set(objects.map((item) => item.canvasId)).size !== objects.length) {
    throw new Error("capability canvas identities must be unique");
  }
  if (new Set(objects.map((item) => item.logicalId)).size !== objects.length) {
    throw new Error("capability logical identities must be unique");
  }
  if (new Set(relations.map((item) => item.canvasId)).size !== relations.length) {
    throw new Error("capability relation identities must be unique");
  }
  const known = new Set(objects.map((item) => item.logicalId));
  for (const relation of relations) {
    if (!known.has(relation.source.ownerId) || !known.has(relation.target.ownerId)) {
      throw new Error(`relation ${relation.canvasId} references an unknown owner`);
    }
    if (relation.target.ownerId === input.logicalId || relation.source.ownerId === output.logicalId) {
      throw new Error(`relation ${relation.canvasId} violates Input/Output direction`);
    }
    const touchesOutput = relation.target.ownerId === output.logicalId;
    if (touchesOutput !== (relation.kind === "termination")) {
      throw new Error("Output accepts only termination relations");
    }
  }
  const presentation = parsePresentation(value.presentation);
  const allowedPresentation = new Set(objects.map((item) => item.canvasId));
  if (Object.keys(presentation.nodes).some((item) => !allowedPresentation.has(item))) {
    throw new Error("presentation references an unknown capability object");
  }
  return {
    schemaVersion: 3,
    contractVersion: "1.1",
    authoringPolicy: STUDIO_CAPABILITY_AUTHORING_POLICY,
    loweringProfile: STUDIO_CAPABILITY_LOWERING_PROFILE,
    documentId: requireString(value.documentId, "document.documentId"),
    agentId: requireString(value.agentId, "document.agentId"),
    name: requireString(value.name, "document.name"),
    input,
    output,
    capabilities,
    relations,
    policies: { maxSteps, maxFeedbackIterations },
    presentation,
    authoring: {
      description: typeof value.authoring.description === "string" ? value.authoring.description : "",
      createdAt: requireNumber(value.authoring.createdAt ?? 0, "authoring.createdAt"),
      updatedAt: requireNumber(value.authoring.updatedAt ?? 0, "authoring.updatedAt"),
    },
  };
}

/** Parse a historical schema-2 or current schema-3 immutable document. */
export function parseStudioAuthoringDocument(value: unknown): StudioAuthoringDocument {
  if (isRecord(value) && value.schemaVersion === 2) return parseLegacyStudioFlowDocument(value);
  return parseStudioFlowDocument(value);
}

/** Create one current empty draft with system-provisioned Input and Output. */
export function createEmptyStudioDocument(
  agentId: string,
  name: string,
  documentId: string,
): StudioFlowDocument {
  return {
    schemaVersion: 3,
    contractVersion: "1.1",
    authoringPolicy: STUDIO_CAPABILITY_AUTHORING_POLICY,
    loweringProfile: STUDIO_CAPABILITY_LOWERING_PROFILE,
    documentId,
    agentId,
    name,
    input: { canvasId: "input", logicalId: "input", kind: "input" },
    output: { canvasId: "output", logicalId: "output", kind: "output" },
    capabilities: [],
    relations: [],
    policies: { maxSteps: 15, maxFeedbackIterations: 10 },
    presentation: {
      nodes: {
        input: { x: 0, y: 0, label: "Input", renderMode: "boundary" },
        output: { x: 400, y: 0, label: "Output", renderMode: "boundary" },
      },
      viewport: { x: 0, y: 0, zoom: 1 },
    },
    authoring: { description: "", createdAt: 0, updatedAt: 0 },
  };
}
