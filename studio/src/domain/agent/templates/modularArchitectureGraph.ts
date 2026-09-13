/**
 * Modular 策略架构图：与 ``ModularAgent.reset()`` / ``ModularAgent.step()`` 对齐。
 * 上栏为「初始化仅 1 次」，下栏为「主循环每步」；Planner 不在循环入口；Verifier 在 Perception 前且可选；
 * Perception 后经 Memory 短路直连输出或进入 Reasoning；Memory ↔ Reasoning 为读上下文 / 更新闭环。
 */
import type { Edge, Node } from "@xyflow/react";
import type { FlowAnchorNodeData, IfElseNodeData } from "@/domain/agent/types";
import type { ModularSlotNode } from "@/domain/agent/templates/modularTemplate";

export type ModularFlowAnchorNode = Node<FlowAnchorNodeData, "flowAnchor">;

export type IfElseFlowNode = Node<IfElseNodeData, "ifElse">;

/** 兵工厂进度与 YAML components 角色一致 */
export const MODULAR_PLUGIN_SLOT_IDS = ["planner", "verifier", "perception", "reasoning", "memory"] as const;

const STEP_TOTAL = 5;
const CARD = 290;
const GAP = 48;
const BASE = 40;

const col = (i: number) => BASE + i * (CARD + GAP);

function slot(
  slotId: (typeof MODULAR_PLUGIN_SLOT_IDS)[number],
  title: string,
  roleLabel: string,
  stepIndex: number,
  x: number,
  y: number,
): ModularSlotNode {
  return {
    id: `slot-${slotId}`,
    type: "slot",
    position: { x, y },
    data: { slotId, title, roleLabel, stepIndex, stepTotal: STEP_TOTAL, graphLayout: "canvas" },
  };
}

function anchor(kind: FlowAnchorNodeData["kind"], id: string, title: string, subtitle: string | undefined, x: number, y: number): ModularFlowAnchorNode {
  return {
    id,
    type: "flowAnchor",
    position: { x, y },
    data: { kind, title, subtitle },
  };
}

function flowEdge(
  id: string,
  source: string,
  target: string,
  opts?: {
    label?: string;
    /** 非主流程：更细、更淡的实线（不再用虚线，减少杂乱） */
    muted?: boolean;
    animated?: boolean;
    sourceHandle?: string;
    targetHandle?: string;
  },
): Edge {
  const muted = opts?.muted ?? false;
  return {
    id,
    source,
    target,
    type: "flowBezier",
    sourceHandle: opts?.sourceHandle,
    targetHandle: opts?.targetHandle,
    label: opts?.label,
    labelStyle: { fill: "rgba(200,208,220,0.88)", fontSize: 11 },
    style: muted
      ? { stroke: "rgba(160, 160, 170, 0.5)", strokeWidth: 1.5, strokeOpacity: 0.95 }
      : { stroke: "#999999", strokeWidth: 2 },
    animated: opts?.animated ?? false,
  };
}

/**
 * 初始化行 y≈156；主循环行 y≈508；Memory 单列与 Perception 同 x 便于表达「读 / 写」与短路语义。
 */
export const modularArchitectureNodes: Array<ModularFlowAnchorNode | ModularSlotNode> = [
  anchor("phase", "flow-phase-init", "初始化（agent.reset）", "仅执行 1 次：任务、清空 Memory、Planner 生成 Plan 并存入 Memory", BASE, 24),
  anchor("input", "flow-input", "Input", "任务指令（instruction）", col(0), 156),
  slot("planner", "Planner", "规划", 0, col(1), 156),
  slot("memory", "Memory", "记忆", 4, col(2), 156),
  anchor("phase", "flow-phase-loop", "主循环（agent.step）", "每步：可选 Verifier → Perception → Memory 命中则短路，否则 Reasoning 并回写 Memory", BASE, 364),
  anchor("input", "flow-step-screenshot", "每步入口", "当前截图与宽高（step 入参）", col(0), 508),
  slot("verifier", "Verifier", "校验", 1, col(1), 508),
  slot("perception", "Perception", "感知", 2, col(2), 508),
  slot("reasoning", "Reasoning", "推理", 3, col(3), 508),
  anchor("output", "flow-output", "Device output", "执行返回的 Action", col(4), 508),
];

export const modularArchitectureEdges: Edge[] = [
  flowEdge("e-init-in-pl", "flow-input", "slot-planner", { sourceHandle: "out", targetHandle: "in-l" }),
  flowEdge("e-init-pl-mem", "slot-planner", "slot-memory", { label: "Plan 写入 Memory", sourceHandle: "out-r", targetHandle: "in-l" }),
  flowEdge("e-loop-shot-ve", "flow-step-screenshot", "slot-verifier", {
    muted: true,
    label: "可选：已配置 Verifier 且上一步有 Action 时执行",
    sourceHandle: "out",
    targetHandle: "in-l",
  }),
  flowEdge("e-loop-shot-pe", "flow-step-screenshot", "slot-perception", {
    muted: true,
    label: "未进入 Verifier 块时（无组件或未触发条件）",
    sourceHandle: "out",
    targetHandle: "in-l",
  }),
  flowEdge("e-loop-ve-pe", "slot-verifier", "slot-perception", { label: "校验后", sourceHandle: "out-r", targetHandle: "in-l" }),
  flowEdge("e-loop-pe-out-hit", "slot-perception", "flow-output", {
    muted: true,
    label: "缓存命中：短路 Reasoning",
    sourceHandle: "out-r",
    targetHandle: "in",
  }),
  flowEdge("e-loop-pe-re", "slot-perception", "slot-reasoning", {
    label: "未命中缓存",
    sourceHandle: "out-r",
    targetHandle: "in-l",
  }),
  flowEdge("e-loop-mem-re", "slot-memory", "slot-reasoning", {
    muted: true,
    animated: true,
    label: "读 working 上下文",
    sourceHandle: "out-r",
    targetHandle: "in-l",
  }),
  flowEdge("e-loop-re-mem", "slot-reasoning", "slot-memory", {
    label: "更新上下文",
    sourceHandle: "out-r",
    targetHandle: "in-l",
  }),
  flowEdge("e-loop-mem-out", "slot-memory", "flow-output", {
    label: "返回 Action",
    sourceHandle: "out-r",
    targetHandle: "in",
  }),
];
