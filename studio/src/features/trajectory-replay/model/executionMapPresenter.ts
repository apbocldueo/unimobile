import {
  canvasSafeText,
  STUDIO_CAPABILITY_AUTHORING_POLICY,
  STUDIO_CAPABILITY_LOWERING_PROFILE,
  type StudioCapabilityRelationKind,
  type StudioProjectionEntry,
} from "@/entities/agent-graph";
import type {
  NodeProjection,
  ReplayGraphEdge,
  ReplayGraphNode,
  ReplayProjection,
  RunSnapshot,
} from "@/entities/run";
import { isRecord } from "@/shared/lib";

export type ExecutionMapViewMode = "path" | "relations";
export type ExecutionMapSource = "capability" | "legacy" | "generic";
export type ExecutionMapOwner = StudioProjectionEntry["owner"];

export type ExecutionMapNode = ReplayGraphNode & {
  canvasId: string;
  label: string;
  runtimeNodeIds: string[];
  aggregate: NodeProjection;
  current: boolean;
  selected: boolean;
  failed: boolean;
  dependencyOwnerIds: string[];
};

export type ExecutionMapRelation = {
  id: string;
  sourceNode: string;
  targetNode: string;
  kind: string;
  current: boolean;
};

export type ExecutionMapModel = {
  source: ExecutionMapSource;
  nodes: ExecutionMapNode[];
  relations: ExecutionMapRelation[];
  visibleRelations: ExecutionMapRelation[];
  currentNodeId: string | null;
  currentRelationId: string | null;
  selectedNodeId: string | null;
  failureNodeId: string | null;
  runtimeOwnerByNodeId: Record<string, ExecutionMapOwner>;
  verticalFirst: boolean;
  supportsRelationDisclosure: boolean;
};

type PresentExecutionMapInput = {
  snapshot: RunSnapshot;
  projection: ReplayProjection;
  displayActivationId: string | null;
  selectedActivationId: string | null;
  failureActivationId?: string | null;
  viewMode: ExecutionMapViewMode;
};

type TopologyNode = ReplayGraphNode & {
  canvasId: string;
  label: string;
  runtimeNodeIds: string[];
};

type TopologyRelation = ReplayGraphEdge & {
  kind: string;
};

type ExecutionTopology = {
  source: ExecutionMapSource;
  nodes: TopologyNode[];
  relations: TopologyRelation[];
  runtimeOwnerByNodeId: Record<string, ExecutionMapOwner>;
};

const LEGACY_CAPABILITY_ROLES = new Set([
  "perception",
  "planner",
  "reasoning",
  "memory",
  "action_executor",
  "verifier",
  "grounder",
  "tool",
]);

const STATUS_PRIORITY: Record<NodeProjection["status"], number> = {
  not_observed: 0,
  skipped: 1,
  success: 2,
  running: 3,
  failure: 4,
};

/** Aggregate exact runtime node facts into one visible execution-map card. */
function aggregateNode(
  node: TopologyNode,
  projection: ReplayProjection,
): NodeProjection {
  const facts = node.runtimeNodeIds
    .map((runtimeId) => projection.nodesById[runtimeId])
    .filter((item): item is NodeProjection => Boolean(item));
  return facts.reduce<NodeProjection>((current, item) => ({
    nodeId: node.id,
    status: STATUS_PRIORITY[item.status] > STATUS_PRIORITY[current.status]
      ? item.status
      : current.status,
    activationIds: [...current.activationIds, ...item.activationIds],
    executionCount: current.executionCount + item.executionCount,
    feedbackCount: current.feedbackCount + item.feedbackCount,
    badges: [...new Set(
      [...current.badges, ...item.badges]
        .map((badge) => canvasSafeText(badge))
        .filter(Boolean),
    )],
  }), {
    nodeId: node.id,
    status: "not_observed",
    activationIds: [],
    executionCount: 0,
    feedbackCount: 0,
    badges: [],
  });
}

/** Resolve the exact runtime node that owns one activation without title guessing. */
function runtimeNodeForActivation(
  projection: ReplayProjection,
  activationId: string | null,
): string | null {
  if (!activationId) return null;
  const activation = projection.activationsById[activationId];
  if (activation) return activation.nodeId;
  return Object.values(projection.nodesById).find(
    (node) => node.activationIds.includes(activationId),
  )?.nodeId ?? null;
}

/** Choose the visible card associated with one formal projection owner. */
function visibleNodeForOwner(
  owner: ExecutionMapOwner | undefined,
  relationsById: Record<string, TopologyRelation>,
  purpose: "current" | "failure" | "history",
): string | null {
  if (!owner?.ownerId || owner.kind === "unmapped" || owner.kind === "graph_policy") {
    return null;
  }
  if (["capability", "input", "output"].includes(owner.kind)) {
    return owner.ownerId;
  }
  if (owner.kind !== "relation") return null;
  const relation = relationsById[owner.ownerId];
  if (!relation) return null;
  if (purpose === "failure") return relation.sourceNode;
  if (purpose === "current") return relation.targetNode;
  return relation.kind === "data" || relation.kind === "activation"
    ? relation.targetNode
    : relation.sourceNode;
}

/** Build the exact schema-3 capability topology and preserve relation ownership. */
function capabilityTopology(snapshot: RunSnapshot): ExecutionTopology | null {
  const document = snapshot.capabilityDocument;
  const projectionMap = snapshot.projectionMap ?? [];
  if (
    document?.schemaVersion !== 3
    || snapshot.authoringPolicy !== STUDIO_CAPABILITY_AUTHORING_POLICY
    || snapshot.loweringProfile !== STUDIO_CAPABILITY_LOWERING_PROFILE
    || projectionMap.length === 0
  ) {
    return null;
  }
  if (snapshot.graphNodes.some((node) => !projectionMap.some(
    (entry) => entry.graphKind === "node" && entry.graphId === node.id,
  ))) {
    return null;
  }

  const presentation = isRecord(snapshot.presentation) && isRecord(snapshot.presentation.nodes)
    ? snapshot.presentation.nodes
    : {};
  const presentationLabel = (canvasId: string, fallback: string): string => {
    const item = presentation[canvasId];
    return canvasSafeText(
      isRecord(item) && typeof item.label === "string" ? item.label : undefined,
      fallback,
    );
  };
  const relations: TopologyRelation[] = document.relations.map((relation) => ({
    id: relation.canvasId,
    sourceNode: relation.source.ownerId,
    targetNode: relation.target.ownerId,
    kind: relation.kind,
  }));
  const relationsById = Object.fromEntries(relations.map((relation) => [relation.id, relation]));
  const runtimeOwnerByNodeId = Object.fromEntries(
    projectionMap
      .filter((entry) => entry.graphKind === "node")
      .map((entry) => [entry.graphId, entry.owner]),
  );
  const rawNodes: Array<{
    id: string;
    canvasId: string;
    label: string;
    role: string;
    lifecycle: string;
    primary: boolean;
  }> = [
    {
      id: document.input.logicalId,
      canvasId: document.input.canvasId,
      label: "Input",
      role: "input",
      lifecycle: "on_run_start",
      primary: false,
    },
    ...document.capabilities.map((capability) => ({
      id: capability.logicalId,
      canvasId: capability.canvasId,
      label: presentationLabel(capability.canvasId, capability.family),
      role: capability.family,
      lifecycle: capability.lifecycle,
      primary: capability.primary === true,
    })),
    {
      id: document.output.logicalId,
      canvasId: document.output.canvasId,
      label: "Output",
      role: "output",
      lifecycle: "terminal",
      primary: false,
    },
  ];
  const nodes: TopologyNode[] = rawNodes.map((node) => ({
    ...node,
    kind: node.role === "input" || node.role === "output" ? node.role : "component",
    runtimeNodeIds: Object.entries(runtimeOwnerByNodeId)
      .filter(([, owner]) => visibleNodeForOwner(owner, relationsById, "history") === node.id)
      .map(([runtimeId]) => runtimeId),
  }));
  return {
    source: "capability",
    nodes,
    relations,
    runtimeOwnerByNodeId,
  };
}

/** Collapse one recognized schema-2 Studio graph without exposing runtime glue. */
function legacyTopology(snapshot: RunSnapshot): ExecutionTopology | null {
  const document = snapshot.capabilityDocument;
  if (document?.schemaVersion !== 2 || (snapshot.projectionMap?.length ?? 0) > 0) return null;
  const documentIds = new Set(document.semantic.nodes.map((node) => node.logicalId));
  const runtimeIds = new Set(snapshot.graphNodes.map((node) => node.id));
  if (
    documentIds.size !== runtimeIds.size
    || [...documentIds].some((nodeId) => !runtimeIds.has(nodeId))
  ) {
    return null;
  }
  const visible = document.semantic.nodes.filter((node) => {
    if (node.kind === "input" || node.kind === "output") return true;
    if (node.kind !== "component" || !LEGACY_CAPABILITY_ROLES.has(node.role ?? "")) return false;
    return !node.component?.candidates.some(
      (candidate) => candidate.namespace === "zhixing.runtime",
    );
  });
  if (
    visible.filter((node) => node.kind === "input").length !== 1
    || visible.filter((node) => node.kind === "output").length !== 1
    || visible.length <= 2
  ) {
    return null;
  }
  const visibleIds = new Set(visible.map((node) => node.logicalId));
  const capabilityIds = new Set(
    visible.filter((node) => node.kind === "component").map((node) => node.logicalId),
  );
  const incoming = new Map<string, string[]>();
  const outgoing = new Map<string, string[]>();
  for (const edge of snapshot.graphEdges) {
    incoming.set(edge.targetNode, [...(incoming.get(edge.targetNode) ?? []), edge.sourceNode]);
    outgoing.set(edge.sourceNode, [...(outgoing.get(edge.sourceNode) ?? []), edge.targetNode]);
  }
  const nearestVisible = (
    startId: string,
    direction: "incoming" | "outgoing",
  ): string | null => {
    const adjacency = direction === "incoming" ? incoming : outgoing;
    const visited = new Set([startId]);
    let frontier = [startId];
    while (frontier.length > 0) {
      const next = [...new Set(frontier.flatMap((nodeId) => adjacency.get(nodeId) ?? []))]
        .filter((nodeId) => !visited.has(nodeId))
        .sort();
      const capability = next.find((nodeId) => capabilityIds.has(nodeId));
      if (capability) return capability;
      next.forEach((nodeId) => visited.add(nodeId));
      frontier = next.filter((nodeId) => !visibleIds.has(nodeId));
    }
    return null;
  };
  const runtimeVisibleOwner = Object.fromEntries(snapshot.graphNodes.map((node) => [
    node.id,
    visibleIds.has(node.id)
      ? node.id
      : nearestVisible(node.id, "incoming") ?? nearestVisible(node.id, "outgoing") ?? "",
  ]));
  if (Object.values(runtimeVisibleOwner).some((ownerId) => !ownerId)) return null;
  const presentation = document.presentation.nodes;
  const nodes: TopologyNode[] = visible.map((node) => ({
    id: node.logicalId,
    canvasId: node.canvasId,
    kind: node.kind,
    label: canvasSafeText(
      presentation[node.canvasId]?.label,
      node.kind === "input" ? "Input" : node.kind === "output" ? "Output" : node.role ?? "capability",
    ),
    role: node.kind === "input" || node.kind === "output" ? node.kind : node.role ?? "capability",
    lifecycle: node.lifecycle,
    primary: node.primary === true,
    runtimeNodeIds: Object.entries(runtimeVisibleOwner)
      .filter(([, ownerId]) => ownerId === node.logicalId)
      .map(([runtimeId]) => runtimeId),
  }));
  const projectedRelations = new Map<string, TopologyRelation>();
  for (const source of [...visibleIds].sort()) {
    const queue = [...(outgoing.get(source) ?? [])].sort();
    const visited = new Set([source]);
    while (queue.length > 0) {
      const target = queue.shift();
      if (!target || visited.has(target)) continue;
      visited.add(target);
      if (visibleIds.has(target)) {
        const relationId = `legacy:${source}->${target}`;
        projectedRelations.set(relationId, {
          id: relationId,
          sourceNode: source,
          targetNode: target,
          kind: snapshot.graphEdges.some(
            (edge) => edge.sourceNode === source
              && edge.targetNode === target
              && edge.kind === "feedback",
          ) ? "feedback" : "data",
        });
        continue;
      }
      queue.push(...[...(outgoing.get(target) ?? [])].sort());
    }
  }
  return {
    source: "legacy",
    nodes,
    relations: [...projectedRelations.values()],
    runtimeOwnerByNodeId: Object.fromEntries(Object.entries(runtimeVisibleOwner).map(
      ([runtimeId, ownerId]) => [runtimeId, { kind: "capability", ownerId } as ExecutionMapOwner],
    )),
  };
}

/** Preserve exact generic topology when no Studio capability mapping exists. */
function genericTopology(snapshot: RunSnapshot): ExecutionTopology | null {
  if (
    snapshot.capabilityDocument
    || (snapshot.projectionMap?.length ?? 0) > 0
    || snapshot.sourceMap.length > 0
  ) {
    return null;
  }
  return {
    source: "generic",
    nodes: snapshot.graphNodes.map((node) => ({
      ...node,
      canvasId: node.id,
      label: canvasSafeText(node.id, canvasSafeText(node.kind, "runtime")),
      role: canvasSafeText(node.role, "runtime"),
      runtimeNodeIds: [node.id],
    })),
    relations: snapshot.graphEdges.map((edge) => ({ ...edge })),
    runtimeOwnerByNodeId: Object.fromEntries(snapshot.graphNodes.map((node) => [
      node.id,
      { kind: "capability", ownerId: node.id } as ExecutionMapOwner,
    ])),
  };
}

/** Present one immutable Run/Replay prefix as a readable execution map. */
export function presentRunExecutionMap({
  snapshot,
  projection,
  displayActivationId,
  selectedActivationId,
  failureActivationId = projection.failureTargets.at(-1)?.activationId ?? null,
  viewMode,
}: PresentExecutionMapInput): ExecutionMapModel | null {
  if (snapshot.graphStatus !== "available" || snapshot.graphNodes.length === 0) return null;
  const topology = capabilityTopology(snapshot)
    ?? legacyTopology(snapshot)
    ?? genericTopology(snapshot);
  if (!topology) return null;

  const relationsById = Object.fromEntries(
    topology.relations.map((relation) => [relation.id, relation]),
  );
  const ownerForActivation = (activationId: string | null): ExecutionMapOwner | undefined => {
    const runtimeNodeId = runtimeNodeForActivation(projection, activationId);
    return runtimeNodeId ? topology.runtimeOwnerByNodeId[runtimeNodeId] : undefined;
  };
  const displayOwner = ownerForActivation(displayActivationId);
  const selectedOwner = ownerForActivation(selectedActivationId);
  const failureOwner = ownerForActivation(failureActivationId);
  const displayNodeId = visibleNodeForOwner(displayOwner, relationsById, "current");
  const failureNodeId = visibleNodeForOwner(failureOwner, relationsById, "failure");
  // Failure is an evidence axis, not a replacement for the display-current axis.
  const currentNodeId = displayNodeId;
  const selectedNodeId = visibleNodeForOwner(selectedOwner, relationsById, "history");
  const currentRelationId = displayOwner?.kind === "relation"
    ? displayOwner.ownerId ?? null
    : null;
  const aggregates = Object.fromEntries(
    topology.nodes.map((node) => [node.id, aggregateNode(node, projection)]),
  );
  const observed = new Set(
    topology.nodes
      .filter((node) => aggregates[node.id]?.status !== "not_observed")
      .map((node) => node.id),
  );
  if (currentNodeId) observed.add(currentNodeId);
  const relations: ExecutionMapRelation[] = topology.relations.map((relation) => ({
    ...relation,
    kind: canvasSafeText(
      relation.kind,
      "data",
    ) as StudioCapabilityRelationKind | string,
    current: relation.id === currentRelationId,
  }));
  const pathRelations = topology.source === "capability"
    ? relations.filter((relation) => {
        if (relation.kind === "feedback") return false;
        if (relation.current) return true;
        if (!currentNodeId) return false;
        const incident = relation.sourceNode === currentNodeId
          || relation.targetNode === currentNodeId;
        return incident
          && (observed.has(relation.sourceNode) || observed.has(relation.targetNode));
      })
    : relations;
  const dependenciesByTarget = new Map<string, string[]>();
  for (const relation of topology.relations) {
    if (relation.kind !== "data") continue;
    dependenciesByTarget.set(relation.targetNode, [
      ...(dependenciesByTarget.get(relation.targetNode) ?? []),
      relation.sourceNode,
    ]);
  }
  const nodes: ExecutionMapNode[] = topology.nodes.map((node) => ({
    ...node,
    aggregate: aggregates[node.id]!,
    current: node.id === currentNodeId,
    selected: node.id === selectedNodeId,
    failed: node.id === failureNodeId,
    dependencyOwnerIds: [...new Set(dependenciesByTarget.get(node.id) ?? [])].sort(),
  }));
  return {
    source: topology.source,
    nodes,
    relations,
    visibleRelations: viewMode === "relations" ? relations : pathRelations,
    currentNodeId,
    currentRelationId,
    selectedNodeId,
    failureNodeId,
    runtimeOwnerByNodeId: topology.runtimeOwnerByNodeId,
    verticalFirst: topology.source === "capability",
    supportsRelationDisclosure: topology.source === "capability",
  };
}
