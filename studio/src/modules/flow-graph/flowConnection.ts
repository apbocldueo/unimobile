import type { Connection, Node } from "@xyflow/react";
import type { FlowDataType } from "./flowDataTypes";
import { WILDCARD_FLOW_TYPE, formatTypesForTooltip } from "./flowDataTypes";
import type { FlowPortInstance } from "./flowPortBlueprint";
import type { FlowPaletteNodeData } from "./flowNodeData";

function getPort(nodes: Node[], nodeId: string, handleId: string | null): FlowPortInstance | null {
  if (!handleId) return null;
  const n = nodes.find((x) => x.id === nodeId);
  if (!n || (n.type !== "studioPalette" && n.type !== "ifElseFlow")) return null;
  const data = n.data as FlowPaletteNodeData;
  const p = data.ports?.find((q) => q.portId === handleId);
  return p ?? null;
}

/** 输出端口对外发射的主类型（用于边颜色与序列化）。 */
export function primaryOutputType(port: FlowPortInstance): FlowDataType {
  return port.dataTypes[0] ?? "plan";
}

function isWildcardOutput(port: FlowPortInstance): boolean {
  return port.portKind === "output" && port.dataTypes.includes(WILDCARD_FLOW_TYPE);
}

/**
 * 校验：输出 → 输入；类型：单类型精确匹配；多类型：source ∈ target.accepts；
 * 通配输出：可连任意「非仅 condition」的输入（True/False 分支语义）。
 */
export function isCompatibleTypes(sourcePort: FlowPortInstance, targetPort: FlowPortInstance): boolean {
  if (sourcePort.portKind !== "output" || targetPort.portKind !== "input") return false;

  const outT = primaryOutputType(sourcePort);
  const accepts = targetPort.dataTypes;

  if (isWildcardOutput(sourcePort)) {
    if (accepts.length === 1 && accepts[0] === "condition") return false;
    return true;
  }

  return accepts.some((a) => a === outT);
}

export function validateConnection(nodes: Node[], connection: Pick<Connection, "source" | "target" | "sourceHandle" | "targetHandle">): {
  ok: boolean;
  reason?: "self" | "direction" | "type" | "missing";
} {
  const { source, target, sourceHandle, targetHandle } = connection;
  if (!sourceHandle || !targetHandle) return { ok: false, reason: "missing" };
  if (source === target) return { ok: false, reason: "self" };

  const sp = getPort(nodes, source, sourceHandle);
  const tp = getPort(nodes, target, targetHandle);
  if (!sp || !tp) return { ok: false, reason: "missing" };
  if (sp.portKind !== "output" || tp.portKind !== "input") return { ok: false, reason: "direction" };

  if (!isCompatibleTypes(sp, tp)) return { ok: false, reason: "type" };

  return { ok: true };
}

export function explainReject(nodes: Node[], connection: Connection): string {
  const r = validateConnection(nodes, connection);
  if (r.ok) return "";
  if (r.reason === "self") return "不可将节点输出连到自身输入";
  if (r.reason === "direction") return "仅支持从输出端口连到输入端口";
  if (r.reason === "missing") return "端口无效或缺失";
  const tp = getPort(nodes, connection.target ?? "", connection.targetHandle ?? null);
  const sp = getPort(nodes, connection.source ?? "", connection.sourceHandle ?? null);
  if (r.reason === "type" && sp && tp) {
    return `数据类型不匹配；该输入支持：${formatTypesForTooltip(tp.dataTypes)}`;
  }
  return "无法创建连线";
}
