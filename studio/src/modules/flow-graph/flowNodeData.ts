import type { FlowPortInstance } from "./flowPortBlueprint";

export type IfElseOperatorValue = "use" | "not_use";

/** 画布节点 data：业务节点与 If-Else 共用端口列表；If-Else 扩展算子与备注。 */
export type FlowPaletteNodeData = {
  componentId: string;
  label: string;
  icon: string;
  desc: string;
  /** 端口实例；拖入画布时由画布写入 */
  ports?: FlowPortInstance[];
  /** If-Else：对应 JSON ``operator_value`` */
  operator_value?: IfElseOperatorValue;
  /** If-Else：条件说明（用户备注） */
  condition_note?: string;
  /** 与 Modular 注册表 ``pluginsBySlot`` 对齐；无则不在检查器展示算法目录 */
  registrySlotId?: string;
  selectedPluginId?: string | null;
  selectedPluginTitle?: string | null;
  pluginParamValues?: Record<string, string>;
};

/** 导出 JSON 约定：页脚「上 True / 下 False」与 branch_mapping 一致（与端口 role 无关，仅描述垂直顺序）。 */
export const IF_ELSE_BRANCH_MAPPING = { upperPort: "true", lowerPort: "false" } as const;
