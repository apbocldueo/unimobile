import { create } from "zustand";
import type { BenchmarkDraft } from "@/domain/benchmark/types";

type BenchmarkState = {
  draft: BenchmarkDraft;
  setAgentConfigId: (id: string | null) => void;
};

/** 试车场专用 Store；与 agentBuilderStore 互不污染。 */
export const useBenchmarkStore = create<BenchmarkState>((set) => ({
  draft: { agentConfigId: null, pipeline: [] },
  setAgentConfigId: (id) =>
    set((s) => ({ draft: { ...s.draft, agentConfigId: id } })),
}));
