import { create } from "zustand";
import type { CanvasPoint } from "./visiblePlacement";

/** A disposable view port, never a second document or persisted XYFlow instance. */
export type CanvasInteractionPort = {
  sessionId: number;
  placement: () => CanvasPoint | null;
  reveal: (canvasId: string) => void;
};

type CanvasInteractionState = {
  port: CanvasInteractionPort | null;
  register: (port: CanvasInteractionPort) => () => void;
};

/** Share only current-canvas commands between Palette and Inspector. */
export const useCanvasInteractionStore = create<CanvasInteractionState>((set, get) => ({
  port: null,
  /** Register a session-bound port; cleanup cannot remove a newer canvas. */
  register: (port) => {
    set({ port });
    return () => { if (get().port === port) set({ port: null }); };
  },
}));
