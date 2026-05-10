import { create } from "zustand";

/** Agent Studio 画布：当前选中节点（用于右侧 If-Else 等属性面板）。 */
type AgentStudioFlowState = {
  selectedNodeIds: string[];
  setSelectedNodeIds: (ids: string[]) => void;
};

export const useAgentStudioFlowStore = create<AgentStudioFlowState>((set) => ({
  selectedNodeIds: [],
  setSelectedNodeIds: (ids) => set({ selectedNodeIds: ids }),
}));
