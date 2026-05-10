import { create } from "zustand";

/** 与 `loadFromStorage` / `persist` 使用同一键，便于日后迁移或与后端同步时引用。 */
export const STUDIO_HOME_SAVED_FLOWS_STORAGE_KEY = "zx-studio-home-saved-flows-v1";

/**
 * 开始页侧栏「我的流程 / 项目」中的单条记录。
 *
 * 当「兵工厂内完成流程并保存」实现后，在保存成功回调里追加一条即可，例如：
 *
 * ```ts
 * import { useStudioHomeFlowListStore } from "@/features/studio-home/studioHomeFlowListStore";
 *
 * useStudioHomeFlowListStore.getState().addSavedFlow({
 *   label: doc.flowName,
 *   targetPath: "/builder",
 *   id: doc.flowId,
 * });
 * ```
 *
 * 若保存接口返回稳定 id，请传入 `id`，便于日后「打开该流程」与去重；不传则自动生成。
 */
export type StudioHomeSavedFlowItem = {
  id: string;
  label: string;
  /** 一般为 `/builder`；若以后支持 deep link 可改为带 query 的路径 */
  targetPath: string;
};

function isItem(x: unknown): x is StudioHomeSavedFlowItem {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return typeof o.id === "string" && typeof o.label === "string" && typeof o.targetPath === "string";
}

function loadFromStorage(): StudioHomeSavedFlowItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STUDIO_HOME_SAVED_FLOWS_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isItem);
  } catch {
    return [];
  }
}

function persist(items: StudioHomeSavedFlowItem[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STUDIO_HOME_SAVED_FLOWS_STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* private mode / quota */
  }
}

type StudioHomeFlowListState = {
  items: StudioHomeSavedFlowItem[];
  /** 追加一条（持久化到 localStorage）。保存流程成功处调用。 */
  addSavedFlow: (input: { label: string; targetPath: string; id?: string }) => string;
  removeSavedFlow: (id: string) => void;
  /** 批量替换（例如从云端同步）；一般保存单条用 addSavedFlow 即可 */
  replaceSavedFlows: (items: StudioHomeSavedFlowItem[]) => void;
};

export const useStudioHomeFlowListStore = create<StudioHomeFlowListState>((set, get) => ({
  items: loadFromStorage(),

  addSavedFlow: (input) => {
    const id =
      input.id?.trim() ||
      `flow_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    const nextItem: StudioHomeSavedFlowItem = {
      id,
      label: input.label.trim() || "未命名流程",
      targetPath: input.targetPath,
    };
    const withoutDup = get().items.filter((i) => i.id !== id);
    const items = [...withoutDup, nextItem];
    set({ items });
    persist(items);
    return id;
  },

  removeSavedFlow: (id) => {
    const items = get().items.filter((i) => i.id !== id);
    set({ items });
    persist(items);
  },

  replaceSavedFlows: (items) => {
    const safe = items.filter(isItem);
    set({ items: safe });
    persist(safe);
  },
}));
