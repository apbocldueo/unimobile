import type { FlowDocumentV1 } from "@/modules/flow-graph/flowDocument";

/** Build an honest empty canvas when the authoritative template API is absent. */
export function buildEmptyFlowDocument(): FlowDocumentV1 {
  return {
    schemaVersion: 1,
    contractVersion: "1.0",
    flowId: "tpl_empty_v1",
    flowName: "空白流程",
    createTime: Date.now(),
    updateTime: Date.now(),
    nodes: [],
    edges: [],
  };
}

/**
 * Keep only non-runnable local fallbacks here. Runnable templates are served
 * from the backend manifest so every Studio creation path uses one semantic
 * document instead of drifting frontend copies.
 */
export const AGENT_STUDIO_FLOW_PRESETS: {
  id: string;
  name: string;
  description: string;
  build: () => FlowDocumentV1;
}[] = [
  {
    id: "empty",
    name: "空白流程",
    description: "无预置节点；从左侧拖拽组件到画布开始搭建",
    build: buildEmptyFlowDocument,
  },
];
