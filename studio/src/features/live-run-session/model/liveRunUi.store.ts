import { create } from "zustand";

type LiveRunUiState = {
  runId: string | null;
  selectedActivationId: string | null;
  visualActivationId: string | null;
  failureActivationId: string | null;
  initialize: (runId: string) => void;
  lockActivation: (activationId: string | null) => void;
  returnToCurrent: () => void;
  setVisualActivation: (activationId: string | null) => void;
  notifyFailure: (activationId: string | null) => void;
  clear: () => void;
};

/** Own only ephemeral Live selection and presentation state, never Run facts. */
export const useLiveRunUiStore = create<LiveRunUiState>((set, get) => ({
  runId: null,
  selectedActivationId: null,
  visualActivationId: null,
  failureActivationId: null,
  initialize: (runId) => {
    if (get().runId === runId) return;
    set({
      runId,
      selectedActivationId: null,
      visualActivationId: null,
      failureActivationId: null,
    });
  },
  lockActivation: (selectedActivationId) => set({ selectedActivationId }),
  returnToCurrent: () =>
    set({ selectedActivationId: null, failureActivationId: null }),
  setVisualActivation: (visualActivationId) => set({ visualActivationId }),
  notifyFailure: (failureActivationId) => set({ failureActivationId }),
  clear: () =>
    set({
      runId: null,
      selectedActivationId: null,
      visualActivationId: null,
      failureActivationId: null,
    }),
}));
