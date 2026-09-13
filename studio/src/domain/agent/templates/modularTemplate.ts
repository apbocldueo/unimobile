import type { Edge, Node } from "@xyflow/react";
import type { SlotNodeData } from "../types";

export type ModularSlotNode = Node<SlotNodeData, "slot">;

/** 横向：卡片宽 + 间距（配置态槽位卡片 290px） */
const CARD_W = 290;
const CARD_GAP = 36;
const ORIGIN_X = 28;
const ORIGIN_Y = 96;

export type ModularSlotSpec = { slotId: string; title: string; roleLabel: string };

/** 由槽位顺序生成节点（与后端 ``slots`` 数组顺序一致时可无缝替换画布骨架）。 */
export function layoutModularSlotNodes(specs: ModularSlotSpec[]): ModularSlotNode[] {
  const stepTotal = specs.length;
  return specs.map((s, stepIndex) => ({
    id: `slot-${s.slotId}`,
    type: "slot" as const,
    position: { x: ORIGIN_X + stepIndex * (CARD_W + CARD_GAP), y: ORIGIN_Y },
    data: {
      slotId: s.slotId,
      roleLabel: s.roleLabel,
      title: s.title,
      stepIndex,
      stepTotal,
    },
  }));
}

export function buildModularEdgesForNodes(nodes: ModularSlotNode[]): Edge[] {
  const edges: Edge[] = [];
  for (let i = 0; i < nodes.length - 1; i++) {
    const a = nodes[i];
    const b = nodes[i + 1];
    edges.push({
      id: `e-${a.id}-${b.id}`,
      source: a.id,
      target: b.id,
      type: "flowBezier",
    });
  }
  return edges;
}

/** 与 YAML 组件角色顺序一致（兵工厂主画布见 ``modularArchitectureGraph``）。 */
const DEFAULT_MODULAR_SPECS: ModularSlotSpec[] = [
  { slotId: "planner", title: "Planner", roleLabel: "规划" },
  { slotId: "verifier", title: "Verifier", roleLabel: "校验" },
  { slotId: "perception", title: "Perception", roleLabel: "感知" },
  { slotId: "reasoning", title: "Reasoning", roleLabel: "推理" },
  { slotId: "memory", title: "Memory", roleLabel: "记忆" },
];

/**
 * Modular 只读骨架：按执行顺序横向排布；连线为自定义贝塞尔（见画布 edgeTypes）。
 */
export const modularInitialNodes: ModularSlotNode[] = layoutModularSlotNodes(DEFAULT_MODULAR_SPECS);

export const modularInitialEdges: Edge[] = buildModularEdgesForNodes(modularInitialNodes);
