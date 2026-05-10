/**
 * 开始页（`/`）入口配置：按「区块 → 入口项」组织，后续可增区块、增按钮或改路由，无需改页面结构。
 */
/** 卡片左侧图标：`bot` 兵工厂；`lineChart` 试车场（与顶栏模块图标一致） */
export type StudioHomeLaunchCardIcon = "bot" | "lineChart";

/**
 * `armory-flow-picker`：兵工厂专用扩展弹窗（模板 + 空白），见 `StudioHomeArmoryEntryModal`。
 * 若以后其它模块也要弹窗，可在此联合类型中追加 `kind`。
 */
export type StudioHomeLaunchGateModal = {
  kind: "armory-flow-picker";
};

export type StudioHomeLaunchItem = {
  id: string;
  /** 主文案 */
  label: string;
  /** 副文案，可选 */
  description?: string;
  /** 目标路由（须与 `routes.tsx` 一致） */
  to: string;
  /** 默认 `bot` */
  icon?: StudioHomeLaunchCardIcon;
  gateModal?: StudioHomeLaunchGateModal;
};

export type StudioHomeLaunchSection = {
  id: string;
  /** 有值时在区块上方显示小标题 */
  title?: string;
  items: StudioHomeLaunchItem[];
};

export const STUDIO_HOME_LAUNCH_SECTIONS: StudioHomeLaunchSection[] = [
  {
    id: "workspaces",
    items: [
      {
        id: "armory",
        label: "兵工厂",
        description: "编排 Agent 流程与画布",
        to: "/builder",
        gateModal: { kind: "armory-flow-picker" },
      },
      {
        id: "benchmark",
        label: "试车场",
        description: "运行 Benchmark 与性能对比",
        to: "/benchmark",
        icon: "lineChart",
      },
    ],
  },
];
