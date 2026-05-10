import { create } from "zustand";
import type { StudioAgentRegistryDTO } from "@/domain/agent/agentRegistryTypes";
import { fetchAgentBuilderRegistry, getStudioApiBase } from "@/services/studioRegistryClient";

type StudioAgentRegistryState = {
  data: StudioAgentRegistryDTO | null;
  status: "idle" | "loading" | "ok" | "error";
  error: string | null;
  /** 与 Studio 全局 bootstrap 一并调用，或在兵工厂画布挂载时重试 */
  refresh: () => Promise<void>;
};

export const useStudioAgentRegistryStore = create<StudioAgentRegistryState>((set) => ({
  data: null,
  status: "idle",
  error: null,

  refresh: async () => {
    if (!getStudioApiBase()) {
      set({ data: null, status: "idle", error: null });
      return;
    }
    set({ status: "loading", error: null });
    try {
      const data = await fetchAgentBuilderRegistry();
      if (data) set({ data, status: "ok", error: null });
      else set({ data: null, status: "error", error: "agent_registry_empty_or_invalid" });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "agent_registry_failed";
      set({ data: null, status: "error", error: msg });
    }
  },
}));
