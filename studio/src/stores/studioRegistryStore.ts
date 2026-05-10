import { create } from "zustand";
import type { FlowComponentDef } from "@/domain/agent/flowComponents";
import type { StudioModuleConfigDTO, StudioNavModuleDTO } from "@/domain/studio/registryTypes";
import {
  getStudioApiBase,
  STUDIO_DEFAULT_NAV_MODULES,
  fetchBuilderFlowCatalog,
  fetchModuleConfig,
  fetchNavModules,
} from "@/services/studioRegistryClient";
import { useStudioAgentRegistryStore } from "@/stores/studioAgentRegistryStore";

const CONFIG_TTL_MS = 60_000;

type CachedConfig = { at: number; data: StudioModuleConfigDTO };

type StudioRegistryState = {
  navModules: StudioNavModuleDTO[];
  navLoading: boolean;
  navLoadError: string | null;
  navSource: "remote" | "fallback" | "idle";
  moduleConfigCache: Record<string, CachedConfig>;
  builderFlowCatalog: FlowComponentDef[] | null;
  bootstrap: () => Promise<void>;
  loadNavModules: (opts?: { force?: boolean }) => Promise<void>;
  ensureModuleConfig: (moduleId: string, opts?: { force?: boolean }) => Promise<StudioModuleConfigDTO | null>;
  touchModuleConfigForPath: (path: string) => void;
  invalidateModuleConfig: (moduleId: string) => void;
};

function sortNav(m: StudioNavModuleDTO[]) {
  return [...m].sort((a, b) => a.order - b.order);
}

function hasApiBase() {
  return Boolean(getStudioApiBase());
}

export const useStudioRegistryStore = create<StudioRegistryState>((set, get) => ({
  navModules: sortNav(STUDIO_DEFAULT_NAV_MODULES),
  navLoading: false,
  navLoadError: null,
  navSource: "idle",
  moduleConfigCache: {},
  builderFlowCatalog: null,

  bootstrap: async () => {
    await get().loadNavModules({ force: true });
    try {
      const flows = await fetchBuilderFlowCatalog();
      set({ builderFlowCatalog: flows });
    } catch {
      set({ builderFlowCatalog: null });
    }
    void useStudioAgentRegistryStore.getState().refresh();
  },

  loadNavModules: async (opts) => {
    if (get().navLoading && !opts?.force) return;
    set({ navLoading: true, navLoadError: null });
    const { modules, source } = await fetchNavModules();
    set({
      navModules: sortNav(modules),
      navSource: source,
      navLoading: false,
      navLoadError: hasApiBase() && source === "fallback" ? "导航接口不可用，已回退内置模块（可重试）" : null,
    });
  },

  ensureModuleConfig: async (moduleId, opts) => {
    if (!moduleId) return null;
    const cached = get().moduleConfigCache[moduleId];
    const fresh = cached && Date.now() - cached.at < CONFIG_TTL_MS;
    if (fresh && !opts?.force) return cached.data;
    try {
      const data = await fetchModuleConfig(moduleId);
      set((s) => ({
        moduleConfigCache: { ...s.moduleConfigCache, [moduleId]: { at: Date.now(), data } },
      }));
      return data;
    } catch {
      return null;
    }
  },

  touchModuleConfigForPath: (path) => {
    const mods = get().navModules;
    const hit =
      mods.find((m) => {
        if (m.path === "/builder") return path.startsWith("/builder");
        return path === m.path || path.startsWith(`${m.path}/`);
      }) ?? null;
    if (!hit) return;
    void get().ensureModuleConfig(hit.id);
  },

  invalidateModuleConfig: (moduleId) => {
    set((s) => {
      const { [moduleId]: _, ...rest } = s.moduleConfigCache;
      return { moduleConfigCache: rest };
    });
  },
}));
