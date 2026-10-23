import { uiText } from "@/shared/i18n";
import type { StudioCompileResult, StudioDiagnostic, StudioFlowDocument } from "@/entities/agent-graph";

export type DiagnosticTarget = { kind: "node" | "edge"; id: string };

// This early compiler phase uses authoring logical IDs before lowering creates
// maps. Keep the list evidence-backed; Core node IDs have a different namespace.
const AUTHORING_NODE_DIAGNOSTICS = new Set(["graph.studio.component_dependency_required"]);

/** Resolve only unambiguous current-snapshot evidence, including invalid graphs.
 * Args: diagnostic and compile must belong to document's current edit generation.
 * Returns: A verified authoring target or null, never a guessed field location.
 */
export function diagnosticTarget(diagnostic: StudioDiagnostic, document: StudioFlowDocument, compile: StudioCompileResult): DiagnosticTarget | null {
  const candidates: DiagnosticTarget[] = [];
  const objects = [document.input, ...document.capabilities, document.output];
  /** Accept a node only when its exact canvas identity still exists. */
  const node = (id: string | undefined) => {
    if (id && objects.some((item) => item.canvasId === id)) candidates.push({ kind: "node", id });
  };
  /** Accept a relation only when its exact canvas identity still exists. */
  const edge = (id: string | undefined) => {
    if (id && document.relations.some((item) => item.canvasId === id)) candidates.push({ kind: "edge", id });
  };
  const path = diagnostic.path ?? [];
  if (AUTHORING_NODE_DIAGNOSTICS.has(diagnostic.code) && diagnostic.nodeId) {
    const owners = document.capabilities.filter((item) => item.logicalId === diagnostic.nodeId);
    if (owners.length !== 1) return null;
    node(owners[0]!.canvasId);
  }
  if (path[0] === "capabilities" && Number.isSafeInteger(path[1])) node(document.capabilities[path[1] as number]?.canvasId);
  if (path[0] === "relations" && Number.isSafeInteger(path[1])) edge(document.relations[path[1] as number]?.canvasId);
  if (path[0] === "input") node(document.input.canvasId);
  if (path[0] === "output") node(document.output.canvasId);
  for (const source of compile.sourceMap) {
    if (!diagnostic.sourceId || source.sourceId !== diagnostic.sourceId || (source.documentId && source.documentId !== document.documentId)) continue;
    node(source.canvasNodeId);
    edge(source.canvasEdgeId);
  }
  for (const projection of compile.projectionMap ?? []) {
    // edge.NNNN is the existing compiler projection contract, not a label guess.
    const matches = projection.graphKind === "node" && projection.graphId === diagnostic.nodeId
      || projection.graphKind === "edge" && diagnostic.edgeIndex !== undefined && projection.graphId === `edge.${String(diagnostic.edgeIndex).padStart(4, "0")}`;
    if (!matches) continue;
    if (projection.owner.kind === "relation") edge(document.relations.find((item) => item.canvasId === projection.owner.ownerId)?.canvasId);
    else if (["capability", "input", "output"].includes(projection.owner.kind)) {
      const owners = objects.filter((item) => item.logicalId === projection.owner.ownerId);
      if (owners.length !== 1) return null;
      node(owners[0]!.canvasId);
    }
  }
  const unique = new Map(candidates.map((item) => [`${item.kind}:${item.id}`, item]));
  return unique.size === 1 ? [...unique.values()][0]! : null;
}

/** Explain known compiler failures without interpreting human messages as commands. */
export function diagnosticAdvice(code: string, context: { nodeId?: string; portId?: string } = {}): string {
  switch (code) {
    case "graph.studio.component_dependency_required":
      return "Add the required dependency in this capability's Inspector. For an LLM dependency, choose its implementation, model and SecretRef identities, then validate again.";
    case "graph.studio.component_dependency_invalid":
    case "graph.studio.component_dependency_config_invalid":
      return "Check the dependency configuration against its component contract. Correct the configuration in the Inspector and validate again.";
    case "graph.studio.capability_implementation_unavailable":
      return "Select an available implementation in the Inspector, then validate again.";
    case "graph.reachability.unreachable_node":
      return uiText("把 Input.task 接到 Reasoning，再把 Reasoning.action 接到 Action Executor；孤立能力不会收到输入。");
    case "graph.port.required_missing":
      if (context.portId === "perception") return uiText("添加 Perception，并把它的 perception 输出连到 Reasoning.perception。设备 observation 由运行时自动提供，不要把 Input 直接连到 Perception。");
      if (context.portId === "task") return uiText("把 Input 的 task 输出连到这个能力的 task 输入。");
      if (context.portId === "action") return uiText("把 Reasoning 的 action 输出连到 Action Executor 的 action 输入。");
      return uiText("补齐这个必需输入端口的来源，再重新 Validate。");
    case "graph.port.cardinality_exceeded":
      if (context.portId === "observation") return uiText("设备 observation 由运行时自动提供。删除手动 observation 连线，只保留能力之间的业务连线。");
      return uiText("这个输入只能接收一条连线。删除重复连线后再 Validate。");
    case "graph.studio.termination_source_forbidden":
      return uiText("只有 Action Executor 可以结束 Agent。请把 Reasoning.action 连到 Action Executor，再把 Action Executor.result 连到 Output。");
    default:
      return "Review the configuration and connections, then validate again. Technical details retain the compiler message; an automatic fix is not available.";
  }
}
