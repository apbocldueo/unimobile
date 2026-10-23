import { create } from "zustand";
import {
  defaultExperimentProtocol,
  type ExperimentProtocol,
} from "@/entities/experiment-preview";

export type ExperimentComposerDraft = {
  catalogEntryId: string;
  split: string;
  taskId: string;
  agentId: string;
  revisionId: string;
  deviceProfileId: string;
  protocol: ExperimentProtocol;
};

type ExperimentComposerState = {
  draft: ExperimentComposerDraft;
  semanticVersion: number;
  patchDraft: (patch: Partial<ExperimentComposerDraft>) => void;
  patchProtocol: (patch: Partial<ExperimentProtocol>) => void;
  patchBudget: (patch: Partial<ExperimentProtocol["budget"]>) => void;
  reset: (patch?: Partial<ExperimentComposerDraft>) => void;
};

/** Create a new isolated Composer draft with explicit formal defaults. */
function initialDraft(
  patch: Partial<ExperimentComposerDraft> = {},
): ExperimentComposerDraft {
  return {
    catalogEntryId: "",
    split: "test",
    taskId: "",
    agentId: "",
    revisionId: "",
    deviceProfileId: "",
    protocol: defaultExperimentProtocol(),
    ...patch,
  };
}

/** Own only unsaved semantic Composer form state; server facts stay in Query. */
export const useExperimentComposerStore = create<ExperimentComposerState>(
  (set) => ({
    draft: initialDraft(),
    semanticVersion: 0,
    patchDraft: (patch) =>
      set((state) => ({
        draft: { ...state.draft, ...patch },
        semanticVersion: state.semanticVersion + 1,
      })),
    patchProtocol: (patch) =>
      set((state) => ({
        draft: {
          ...state.draft,
          protocol: { ...state.draft.protocol, ...patch },
        },
        semanticVersion: state.semanticVersion + 1,
      })),
    patchBudget: (patch) =>
      set((state) => ({
        draft: {
          ...state.draft,
          protocol: {
            ...state.draft.protocol,
            budget: { ...state.draft.protocol.budget, ...patch },
          },
        },
        semanticVersion: state.semanticVersion + 1,
      })),
    reset: (patch) =>
      set((state) => ({
        draft: initialDraft(patch),
        semanticVersion: state.semanticVersion + 1,
      })),
  }),
);
