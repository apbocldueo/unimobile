import type { Edge, Node } from "@xyflow/react";
import type { SlotNodeData } from "../types";

export type CompactSlotNode = Node<SlotNodeData, "slot">;

const CARD_W = 290;
const CARD_GAP = 40;
const STEP_TOTAL = 3;
const ORIGIN_X = 80;
const ORIGIN_Y = 96;

/** 示例：三槽横向链，用于验证策略切换时画布与计数联动。 */
export const compactInitialNodes: CompactSlotNode[] = [
  slot("perception", "Perception", "感知", 0),
  slot("memory", "Memory", "记忆", 1),
  slot("verifier", "Verifier", "校验", 2),
];

export const compactInitialEdges: Edge[] = [
  e("c-p-m", "slot-perception", "slot-memory"),
  e("c-m-v", "slot-memory", "slot-verifier"),
];

function slot(id: string, title: string, roleLabel: string, stepIndex: number): CompactSlotNode {
  return {
    id: `slot-${id}`,
    type: "slot",
    position: { x: ORIGIN_X + stepIndex * (CARD_W + CARD_GAP), y: ORIGIN_Y },
    data: {
      slotId: id,
      roleLabel,
      title,
      stepIndex,
      stepTotal: STEP_TOTAL,
    },
  };
}

function e(id: string, source: string, target: string): Edge {
  return {
    id,
    source,
    target,
    type: "flowBezier",
  };
}
