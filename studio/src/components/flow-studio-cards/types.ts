import type { Node, NodeProps } from "@xyflow/react";
import type { PortBlueprint } from "@/modules/flow-graph/flowPortBlueprint";
import type { FlowPaletteNodeData } from "@/modules/flow-graph/flowNodeData";

export type FlowComponentGroup = "core" | "io" | "flow";

/** 侧栏与拖拽 MIME 使用的轻量描述（无端口）。 */
export type FlowComponentDef = {
  id: string;
  label: string;
  desc: string;
  icon: string;
};

/** 单张流程卡片：展示信息 + 端口蓝图 + 注册表槽位（可选）+ 画布挂载方式。 */
export type FlowStudioCardDefinition = {
  id: string;
  group: FlowComponentGroup;
  label: string;
  desc: string;
  icon: string;
  portBlueprints: PortBlueprint[];
  /** 有值则在画布节点内展示该槽位的算法 / 插件选择。 */
  registrySlotId?: string;
  /**
   * `studioPalette`：由通用 `studioPalette` 节点类型 + 本目录下对应 React 卡片渲染。
   * `custom`：使用独立 React Flow 节点类型（如 If-Else），此处仅提供目录与端口元数据。
   */
  canvasPresentation: "studioPalette" | "custom";
};

export type FlowStudioPaletteReactFlowNode = Node<FlowPaletteNodeData, "studioPalette">;

export type FlowStudioPaletteCardProps = NodeProps<FlowStudioPaletteReactFlowNode>;
