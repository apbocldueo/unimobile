import { create } from "zustand";
import type { AgentDrawerMode } from "@/features/agent-studio/panels/drawerTypes";
import type { BuilderStrategyId } from "@/domain/agent/builderStrategies";
import { STRATEGY_LABELS } from "@/domain/agent/builderStrategies";
import { FLOW_COMPONENT_CATALOG } from "@/domain/agent/flowComponents";
import { getDefaultSlotParamValues } from "@/domain/agent/pluginParamUi";
import { useToastStore } from "@/stores/toastStore";

let lastParamChangeToastAt = 0;

export type { BuilderStrategyId } from "@/domain/agent/builderStrategies";

type SlotAssignment = { pluginId: string; pluginTitle: string };

export type FlowWorkbenchPhase = "flow_picker" | "flow_editor";

type AgentBuilderState = {
  /** 流程编辑：列表选流程 vs 画布配置（右栏仅在配置态展示）。 */
  flowWorkbenchPhase: FlowWorkbenchPhase;
  /** 回到流程组件列表；收起抽屉与节点焦点，不自动清空已选策略与挂载。 */
  enterFlowPicker: () => void;
  /** 从列表进入配置：应用策略、清空草稿并进入画布。 */
  enterFlowEditorFromPicker: (strategyId: BuilderStrategyId) => void;

  /** 当前流程策略（画布内切换；切换时会清空挂载与参数草稿）。 */
  selectedStrategyId: BuilderStrategyId;
  selectBuilderStrategy: (id: BuilderStrategyId) => void;
  /** 切换策略并重置草稿（节点/连线由画布根据 id 同步）。 */
  applyBuilderStrategy: (id: BuilderStrategyId) => void;
  drawerMode: AgentDrawerMode;
  /** 橱窗/配置流程中的槽位 */
  selectedSlotId: string | null;
  /** 画布上当前选中的槽位（用于右栏标题与引导，可与 selected 同步） */
  focusedSlotId: string | null;
  activePluginId: string | null;
  assignments: Record<string, SlotAssignment>;
  /** 槽位内超参数草稿（字符串化便于控件绑定）。 */
  slotParamValues: Record<string, Record<string, string>>;
  /** 用户是否已编辑过该槽位参数（用于「待配置参数」提示）。 */
  slotParamsTouched: Record<string, boolean>;
  setSlotParamValue: (slotId: string, paramId: string, value: string) => void;
  setFocusedSlot: (slotId: string | null) => void;
  openPluginShowcase: (slotId: string) => void;
  pickPluginPlaceholder: (pluginId: string, pluginTitle?: string, slotId?: string) => void;
  backToPluginShowcase: () => void;
  closeDrawer: () => void;
  /** 清空槽位挂载与超参数草稿（保留已选策略）。 */
  resetBuilderDraft: () => void;
  /** 占位：将当前槽位参数标记为已保存（后续接持久化）。 */
  persistSlotParamSnapshot: (slotId: string) => void;
};

/** 兵工厂专用 Store，与 benchmarkStore 隔离。 */
export const useAgentBuilderStore = create<AgentBuilderState>((set) => ({
  flowWorkbenchPhase: "flow_picker",

  enterFlowPicker: () =>
    set({
      flowWorkbenchPhase: "flow_picker",
      drawerMode: "idle",
      selectedSlotId: null,
      focusedSlotId: null,
      activePluginId: null,
    }),

  enterFlowEditorFromPicker: (strategyId) => {
    const catalogTitle = FLOW_COMPONENT_CATALOG.find((c) => c.strategyId === strategyId)?.title;
    const label = catalogTitle ?? STRATEGY_LABELS[strategyId];
    useToastStore.getState().pushToast({
      message: `进入「${label}」流程配置`,
      tone: "success",
      durationMs: 3800,
    });
    set({
      flowWorkbenchPhase: "flow_editor",
      selectedStrategyId: strategyId,
      assignments: {},
      slotParamValues: {},
      slotParamsTouched: {},
      drawerMode: "idle",
      selectedSlotId: null,
      focusedSlotId: null,
      activePluginId: null,
    });
  },

  selectedStrategyId: "modular",
  selectBuilderStrategy: (id) => set({ selectedStrategyId: id }),

  applyBuilderStrategy: (id) =>
    set({
      selectedStrategyId: id,
      assignments: {},
      slotParamValues: {},
      slotParamsTouched: {},
      drawerMode: "idle",
      selectedSlotId: null,
      focusedSlotId: null,
      activePluginId: null,
    }),

  drawerMode: "idle",
  selectedSlotId: null,
  focusedSlotId: null,
  activePluginId: null,
  assignments: {},
  slotParamValues: {},
  slotParamsTouched: {},

  setFocusedSlot: (slotId) => set({ focusedSlotId: slotId }),

  setSlotParamValue: (slotId, paramId, value) =>
    set((s) => {
      const pluginId = s.assignments[slotId]?.pluginId;
      const defaults = pluginId ? getDefaultSlotParamValues(pluginId) : {};
      const cur = { ...defaults, ...(s.slotParamValues[slotId] ?? {}) };
      const now = Date.now();
      if (now - lastParamChangeToastAt > 2000) {
        lastParamChangeToastAt = now;
        queueMicrotask(() =>
          useToastStore.getState().pushToast({
            message: "参数修改成功",
            tone: "success",
            durationMs: 3400,
          }),
        );
      }
      return {
        slotParamValues: {
          ...s.slotParamValues,
          [slotId]: { ...cur, [paramId]: value },
        },
        slotParamsTouched: { ...s.slotParamsTouched, [slotId]: true },
      };
    }),

  openPluginShowcase: (slotId) =>
    set({
      drawerMode: "plugin_showcase",
      selectedSlotId: slotId,
      focusedSlotId: slotId,
      activePluginId: null,
    }),

  pickPluginPlaceholder: (pluginId, pluginTitle = "Grid Perception", slotId) =>
    set((s) => {
      const sid = slotId ?? s.selectedSlotId;
      if (!sid) return s;
      const defaults = getDefaultSlotParamValues(pluginId);
      useToastStore.getState().pushToast({
        message: `已选择算法「${pluginTitle}」`,
        tone: "success",
        durationMs: 3800,
      });
      return {
        drawerMode: "idle",
        activePluginId: null,
        focusedSlotId: sid,
        selectedSlotId: sid,
        assignments: {
          ...s.assignments,
          [sid]: { pluginId, pluginTitle },
        },
        slotParamValues: {
          ...s.slotParamValues,
          [sid]: { ...defaults },
        },
        slotParamsTouched: { ...s.slotParamsTouched, [sid]: false },
      };
    }),

  persistSlotParamSnapshot: (_slotId) => {
    useToastStore.getState().pushToast({
      message: "保存参数成功",
      tone: "success",
      durationMs: 4200,
    });
  },

  backToPluginShowcase: () =>
    set((s) => ({
      drawerMode: "plugin_showcase",
      activePluginId: null,
      selectedSlotId: s.selectedSlotId,
      focusedSlotId: s.selectedSlotId ?? s.focusedSlotId,
    })),

  closeDrawer: () =>
    set({
      drawerMode: "idle",
      selectedSlotId: null,
      focusedSlotId: null,
      activePluginId: null,
    }),

  resetBuilderDraft: () =>
    set({
      assignments: {},
      slotParamValues: {},
      slotParamsTouched: {},
      drawerMode: "idle",
      selectedSlotId: null,
      focusedSlotId: null,
      activePluginId: null,
    }),
}));
