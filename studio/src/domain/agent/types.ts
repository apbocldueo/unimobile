/** 画布槽位节点携带的数据（与后端 components 角色对应）。 */
export type SlotNodeData = {
  slotId: string;
  roleLabel: string;
  title: string;
  /** 0-based，与执行顺序一致（横向从左到右）。 */
  stepIndex: number;
  stepTotal: number;
  /** 架构画布：多入多出连线，四角保留 Handle；缺省为链式左右 Handle（紧凑模板）。 */
  graphLayout?: "canvas" | "chain";
};

/** 只读流程锚点：输入 / 输出 / 阶段标题条（不参与插件选择）。 */
export type FlowAnchorNodeData = {
  kind: "input" | "output" | "phase";
  title: string;
  subtitle?: string;
};

/** If-Else 分支卡片：条件 UI 仅前端展示，拓扑与后端逻辑不变。 */
export type IfElseNodeData = {
  subtitle?: string;
};

/** 持久化用的 Agent 草稿结构（后续与 YAML / JSON 契约对齐）。 */
export type AgentDraft = {
  strategyId: string;
  /** 各槽位已选插件 id 与参数 */
  slots: Record<string, { pluginId: string; params: Record<string, unknown> }>;
};
