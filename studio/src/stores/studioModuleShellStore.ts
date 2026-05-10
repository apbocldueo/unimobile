import { create } from "zustand";

/** 试车场侧栏入口（第四章 4.2，后续可由接口填充；「帮助中心」为独立路由入口） */
export type BenchmarkSidebarKey = "tasks" | "benchmark" | "params";

/** 历史侧栏入口（第四章 4.3；「帮助中心」为独立路由入口） */
export type HistorySidebarKey = "runs" | "filters" | "export";

/** 设置侧栏入口（第四章 4.4） */
export type SettingsSidebarKey = "prefs" | "theme" | "shortcuts" | "account" | "about";

type StudioModuleShellState = {
  benchmarkSidebarKey: BenchmarkSidebarKey;
  historySidebarKey: HistorySidebarKey;
  settingsSidebarKey: SettingsSidebarKey;
  setBenchmarkSidebarKey: (k: BenchmarkSidebarKey) => void;
  setHistorySidebarKey: (k: HistorySidebarKey) => void;
  setSettingsSidebarKey: (k: SettingsSidebarKey) => void;
};

export const useStudioModuleShellStore = create<StudioModuleShellState>((set) => ({
  benchmarkSidebarKey: "tasks",
  historySidebarKey: "runs",
  settingsSidebarKey: "prefs",

  setBenchmarkSidebarKey: (k) => set({ benchmarkSidebarKey: k }),
  setHistorySidebarKey: (k) => set({ historySidebarKey: k }),
  setSettingsSidebarKey: (k) => set({ settingsSidebarKey: k }),
}));
