import type { Edge, Node } from "@xyflow/react";
import { getRegistrySlotIdForFlowStudioCard } from "@/components/flow-studio-cards/blueprintIndex";
import { getDefaultSlotParamValues } from "@/domain/agent/pluginParamUi";
import type { FlowDataType } from "./flowDataTypes";
import { createPortsForComponent } from "./flowPortBlueprint";
import { primaryOutputType, validateConnection } from "./flowConnection";
import type { FlowPaletteNodeData } from "./flowNodeData";
import { IF_ELSE_BRANCH_MAPPING } from "./flowNodeData";

export type SerializedFlowPort = {
  portRole: string;
  /** 导出时的 handle id，导入时用于映射 */
  portId: string;
  portName: string;
  portType: "input" | "output";
  dataType: string;
  supportDataTypes?: string[];
};

/** JSON 中与算法/注册表对齐的可选字段（snake_case 便于与 Python 侧对齐）。 */
export type SerializedFlowNodePluginSlice = {
  registry_slot_id?: string;
  selected_plugin_id?: string | null;
  selected_plugin_title?: string | null;
  plugin_params?: Record<string, string>;
};

export type SerializedFlowNode = {
  nodeId: string;
  nodeType: string;
  position: { x: number; y: number };
  data: {
    label: string;
    icon: string;
    desc: string;
    ports: SerializedFlowPort[];
    operator_value?: "use" | "not_use";
    condition_note?: string;
    branch_mapping?: { upperPort: string; lowerPort: string };
  } & SerializedFlowNodePluginSlice;
};

export type SerializedFlowEdge = {
  edgeId: string;
  sourceNodeId: string;
  sourcePortId: string;
  targetNodeId: string;
  targetPortId: string;
  dataType: string;
};

export type FlowDocumentV1 = {
  flowId: string;
  flowName: string;
  createTime: number;
  updateTime: number;
  nodes: SerializedFlowNode[];
  edges: SerializedFlowEdge[];
};

function flowId(): string {
  return `flow_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function newEdgeId(): string {
  return `edge_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function serializePluginSlice(d: FlowPaletteNodeData): SerializedFlowNodePluginSlice {
  const out: SerializedFlowNodePluginSlice = {};
  if (d.registrySlotId) out.registry_slot_id = d.registrySlotId;
  if (d.selectedPluginId) {
    out.selected_plugin_id = d.selectedPluginId;
    out.selected_plugin_title = d.selectedPluginTitle ?? null;
  }
  if (d.pluginParamValues && Object.keys(d.pluginParamValues).length > 0) {
    out.plugin_params = { ...d.pluginParamValues };
  }
  return out;
}

export function serializeFlowDocument(
  flowName: string,
  existingFlowId: string | undefined,
  nodes: Node[],
  edges: Edge[],
  now = Date.now(),
): FlowDocumentV1 {
  const paletteNodes = nodes.filter((n) => n.type === "studioPalette" || n.type === "ifElseFlow");
  const serNodes: SerializedFlowNode[] = paletteNodes.map((n) => {
    const d = n.data as FlowPaletteNodeData;
    const ports: SerializedFlowPort[] = (d.ports ?? []).map((p) => ({
      portRole: p.role,
      portId: p.portId,
      portName: p.portName,
      portType: p.portKind,
      dataType: p.dataTypes[0] ?? "plan",
      supportDataTypes: p.dataTypes.length > 1 ? p.dataTypes : undefined,
    }));
    const isIfElse = d.componentId === "ifelse" || n.type === "ifElseFlow";
    const base = {
      nodeId: n.id,
      nodeType: d.componentId,
      position: { ...n.position },
      data: {
        label: d.label,
        icon: d.icon,
        desc: d.desc,
        ports,
        ...(isIfElse
          ? {
              operator_value: d.operator_value ?? "not_use",
              condition_note: d.condition_note ?? "",
              branch_mapping: { ...IF_ELSE_BRANCH_MAPPING },
            }
          : serializePluginSlice(d)),
      },
    };
    return base;
  });

  const serEdges: SerializedFlowEdge[] = edges.map((e) => {
    const sn = nodes.find((x) => x.id === e.source);
    const sp =
      sn?.type === "studioPalette" || sn?.type === "ifElseFlow"
        ? (sn.data as FlowPaletteNodeData).ports?.find((p) => p.portId === e.sourceHandle)
        : undefined;
    const dt = (e.data as { dataType?: FlowDataType } | undefined)?.dataType ?? (sp ? primaryOutputType(sp) : "plan");
    return {
      edgeId: e.id,
      sourceNodeId: e.source,
      sourcePortId: e.sourceHandle ?? "",
      targetNodeId: e.target,
      targetPortId: e.targetHandle ?? "",
      dataType: dt,
    };
  });

  return {
    flowId: existingFlowId ?? flowId(),
    flowName: flowName || "未命名流程",
    createTime: now,
    updateTime: now,
    nodes: serNodes,
    edges: serEdges,
  };
}

export type FlowValidationIssue = { message: string; edgeId?: string };

export function validateFlowForExport(nodes: Node[], edges: Edge[]): FlowValidationIssue[] {
  const issues: FlowValidationIssue[] = [];
  const targetKeyCount = new Map<string, number>();

  for (const e of edges) {
    const c = validateConnection(nodes, {
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? null,
      targetHandle: e.targetHandle ?? null,
    });
    if (!c.ok) {
      const detail =
        c.reason === "type"
          ? "数据类型不匹配"
          : c.reason === "self"
            ? "不可连接自身节点"
            : c.reason === "direction"
              ? "方向错误（需输出→输入）"
              : "非法连线";
      issues.push({ edgeId: e.id, message: `连线 ${e.source.slice(0, 12)}… → ${e.target.slice(0, 12)}…：${detail}` });
    }
    const k = `${e.target}::${e.targetHandle ?? ""}`;
    targetKeyCount.set(k, (targetKeyCount.get(k) ?? 0) + 1);
  }

  for (const [k, n] of targetKeyCount) {
    if (n > 1) issues.push({ message: `同一输入端口存在 ${n} 条连线：${k}` });
  }

  return issues;
}

function parseDoc(raw: unknown): FlowDocumentV1 | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  if (!Array.isArray(o.nodes) || !Array.isArray(o.edges)) return null;
  if (typeof o.flowName !== "string") return null;
  return raw as FlowDocumentV1;
}

export function tryParseFlowDocument(json: string): { ok: true; doc: FlowDocumentV1 } | { ok: false; error: string } {
  try {
    const raw = JSON.parse(json) as unknown;
    const doc = parseDoc(raw);
    if (!doc) return { ok: false, error: "JSON 结构不符合流程格式（需含 flowName、nodes、edges）" };
    return { ok: true, doc };
  } catch {
    return { ok: false, error: "JSON 解析失败" };
  }
}

function readPluginParams(raw: SerializedFlowNode["data"]): Record<string, string> {
  const p = raw.plugin_params;
  if (!p || typeof p !== "object" || Array.isArray(p)) return {};
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(p)) {
    if (typeof v === "string") out[k] = v;
    else if (typeof v === "number" || typeof v === "boolean") out[k] = String(v);
  }
  return out;
}

/**
 * 由 JSON 文档生成画布状态：按 node 顺序重建节点与端口，并用 portRole / 旧 portId 映射连线。
 */
export function applyFlowDocument(doc: FlowDocumentV1): { nodes: Node[]; edges: Edge[] } {
  if (!doc.nodes.length) return { nodes: [], edges: [] };

  const oldNodeIdToNew = new Map<string, string>();
  const oldPortIdToNew = new Map<string, string>();

  const nodes: Node[] = doc.nodes.map((sn, idx) => {
    const newId = `node_${Date.now()}_${idx}_${Math.random().toString(36).slice(2, 8)}`;
    oldNodeIdToNew.set(sn.nodeId, newId);

    const ports = createPortsForComponent(sn.nodeType, newId);
    for (const op of sn.data.ports) {
      const np = ports.find((p) => p.role === op.portRole);
      if (!np) continue;
      oldPortIdToNew.set(op.portId, np.portId);
      oldPortIdToNew.set(`${sn.nodeId}|${op.portRole}`, np.portId);
    }

    const isIfElse = sn.nodeType === "ifelse";
    const slotFromFile = typeof sn.data.registry_slot_id === "string" ? sn.data.registry_slot_id : undefined;
    const registrySlotId = slotFromFile ?? getRegistrySlotIdForFlowStudioCard(sn.nodeType);
    const selectedPluginId =
      typeof sn.data.selected_plugin_id === "string" && sn.data.selected_plugin_id.length > 0
        ? sn.data.selected_plugin_id
        : null;
    const selectedPluginTitle =
      typeof sn.data.selected_plugin_title === "string" ? sn.data.selected_plugin_title : null;
    const fileParams = readPluginParams(sn.data);
    const mergedParams =
      selectedPluginId ? { ...getDefaultSlotParamValues(selectedPluginId), ...fileParams } : fileParams;

    const data: FlowPaletteNodeData = {
      componentId: sn.nodeType,
      label: sn.data.label,
      icon: sn.data.icon,
      desc: sn.data.desc,
      ports,
      ...(isIfElse
        ? {
            operator_value: sn.data.operator_value === "use" ? "use" : "not_use",
            condition_note: typeof sn.data.condition_note === "string" ? sn.data.condition_note : "",
          }
        : {
            ...(registrySlotId ? { registrySlotId } : {}),
            selectedPluginId,
            selectedPluginTitle,
            pluginParamValues: mergedParams,
          }),
    };

    return {
      id: newId,
      type: isIfElse ? "ifElseFlow" : "studioPalette",
      position: { x: sn.position.x, y: sn.position.y },
      data,
    };
  });

  const edges: Edge[] = doc.edges
    .map((se) => {
      const ns = oldNodeIdToNew.get(se.sourceNodeId);
      const nt = oldNodeIdToNew.get(se.targetNodeId);
      if (!ns || !nt) return null;

      let newSh =
        oldPortIdToNew.get(se.sourcePortId) ?? oldPortIdToNew.get(`${se.sourceNodeId}|${se.sourcePortId}`);
      let newTh =
        oldPortIdToNew.get(se.targetPortId) ?? oldPortIdToNew.get(`${se.targetNodeId}|${se.targetPortId}`);

      const sNode = nodes.find((n) => n.id === ns);
      const tNode = nodes.find((n) => n.id === nt);
      const sd = sNode?.data as FlowPaletteNodeData | undefined;
      const td = tNode?.data as FlowPaletteNodeData | undefined;
      if (!newSh && sd?.ports) newSh = sd.ports.find((p) => p.role === se.sourcePortId)?.portId;
      if (!newTh && td?.ports) newTh = td.ports.find((p) => p.role === se.targetPortId)?.portId;
      if (!newSh || !newTh) return null;

      const sp = sd?.ports?.find((p) => p.portId === newSh);
      const dtype = (sp ? primaryOutputType(sp) : (se.dataType as FlowDataType)) ?? "plan";
      return {
        id: newEdgeId(),
        source: ns,
        target: nt,
        sourceHandle: newSh,
        targetHandle: newTh,
        type: "flowTyped" as const,
        data: { dataType: dtype },
      };
    })
    .filter(Boolean) as Edge[];

  return { nodes, edges };
}
