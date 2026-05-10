import type { FlowDocumentV1, SerializedFlowEdge, SerializedFlowNode, SerializedFlowPort } from "@/modules/flow-graph/flowDocument";
import { createPortsForComponent, type FlowPortInstance } from "@/modules/flow-graph/flowPortBlueprint";
import { FLOW_NODE_CATALOG } from "@/components/flow-studio-cards";

function flatComponents() {
  return Object.values(FLOW_NODE_CATALOG).flat();
}

function meta(componentId: string) {
  const c = flatComponents().find((x) => x.id === componentId);
  return {
    label: c?.label ?? componentId,
    icon: c?.icon ?? "📦",
    desc: c?.desc ?? "",
  };
}

function serPorts(ports: FlowPortInstance[]): SerializedFlowPort[] {
  return ports.map((p) => ({
    portRole: p.role,
    portId: p.portId,
    portName: p.portName,
    portType: p.portKind,
    dataType: p.dataTypes[0] ?? "plan",
    supportDataTypes: p.dataTypes.length > 1 ? p.dataTypes : undefined,
  }));
}

function findPort(ports: FlowPortInstance[], role: string) {
  return ports.find((p) => p.role === role)?.portId ?? "";
}

/** 空白画布：从模板加载后自行拖拽搭建。 */
export function buildEmptyFlowDocument(): FlowDocumentV1 {
  return {
    flowId: "tpl_empty_v1",
    flowName: "空白流程",
    createTime: Date.now(),
    updateTime: Date.now(),
    nodes: [],
    edges: [],
  };
}

/**
 * 预设：Input → Planner → Reasoning → Output。
 * Action 执行节点无输出端口，无法在同一主干上再连 Output；故主干以 Reasoning 的 action 输出对接 Output（与「设备输出接收动作」语义一致）。
 */
export function buildModularBaselineTemplate(): FlowDocumentV1 {
  const ids = {
    input: "tpl_input",
    planner: "tpl_planner",
    reasoning: "tpl_reasoning",
    output: "tpl_output",
  };

  const pInput = createPortsForComponent("input", ids.input);
  const pPlanner = createPortsForComponent("planner", ids.planner);
  const pReason = createPortsForComponent("reasoning", ids.reasoning);
  const pOutput = createPortsForComponent("output", ids.output);

  const nodes: SerializedFlowNode[] = [
    {
      nodeId: ids.input,
      nodeType: "input",
      position: { x: 40, y: 120 },
      data: { ...meta("input"), ports: serPorts(pInput) },
    },
    {
      nodeId: ids.planner,
      nodeType: "planner",
      position: { x: 340, y: 120 },
      data: { ...meta("planner"), ports: serPorts(pPlanner) },
    },
    {
      nodeId: ids.reasoning,
      nodeType: "reasoning",
      position: { x: 640, y: 120 },
      data: { ...meta("reasoning"), ports: serPorts(pReason) },
    },
    {
      nodeId: ids.output,
      nodeType: "output",
      position: { x: 940, y: 120 },
      data: { ...meta("output"), ports: serPorts(pOutput) },
    },
  ];

  const oTask = findPort(pInput, "out_task");
  const inTask = findPort(pPlanner, "in_task");
  const oPlan = findPort(pPlanner, "out_plan");
  const inPlan = findPort(pReason, "in_plan");
  const oAct = findPort(pReason, "out_action");
  const inActO = findPort(pOutput, "in_action");

  const edges: SerializedFlowEdge[] = [
    {
      edgeId: "tpl_e1",
      sourceNodeId: ids.input,
      sourcePortId: oTask,
      targetNodeId: ids.planner,
      targetPortId: inTask,
      dataType: "taskInput",
    },
    {
      edgeId: "tpl_e2",
      sourceNodeId: ids.planner,
      sourcePortId: oPlan,
      targetNodeId: ids.reasoning,
      targetPortId: inPlan,
      dataType: "plan",
    },
    {
      edgeId: "tpl_e3",
      sourceNodeId: ids.reasoning,
      sourcePortId: oAct,
      targetNodeId: ids.output,
      targetPortId: inActO,
      dataType: "action",
    },
  ];

  return {
    flowId: "tpl_modular_baseline_v1",
    flowName: "ModularAgent 模板（线性主干）",
    createTime: Date.now(),
    updateTime: Date.now(),
    nodes,
    edges,
  };
}

/**
 * 兵工厂画布模板与开始页弹窗共用：非 `empty` 项会出现在开始页「预设模板」列表；新增模板时在此追加一项即可。
 */
export const AGENT_STUDIO_FLOW_PRESETS: { id: string; name: string; description: string; build: () => FlowDocumentV1 }[] = [
  {
    id: "empty",
    name: "空白流程",
    description: "无预置节点；从左侧拖拽组件到画布开始搭建",
    build: buildEmptyFlowDocument,
  },
  {
    id: "modular_baseline",
    name: "ModularAgent 模板（线性主干）",
    description: "与 Modular 主干语义一致的线性参考：Input → Planner → Reasoning → Output（Action 对接设备输出）",
    build: buildModularBaselineTemplate,
  },
];
