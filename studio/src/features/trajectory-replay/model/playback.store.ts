import { create } from "zustand";

export type ReplaySpeed = 0.5 | 1 | 2;

type PlaybackState = {
  runId: string | null;
  cursor: number;
  maxCursor: number;
  isPlaying: boolean;
  speed: ReplaySpeed;
  autoFollow: boolean;
  lockedActivationId: string | null;
  selectedMomentId: string | null;
  initialize: (runId: string, maxCursor: number) => void;
  play: () => void;
  pause: () => void;
  setSpeed: (speed: ReplaySpeed) => void;
  seek: (cursor: number) => void;
  step: (cursors: number[], direction: -1 | 1) => void;
  advance: () => void;
  lockActivation: (activationId: string | null) => void;
  selectMoment: (momentId: string | null) => void;
  returnToCurrent: () => void;
};

/** Clamp one causal cursor to the active Replay range. */
function clampCursor(cursor: number, maxCursor: number): number {
  return Math.min(Math.max(cursor, -1), Math.max(maxCursor, -1));
}

/** Own Replay-only interaction state; no runtime facts are copied here. */
export const useReplayPlaybackStore = create<PlaybackState>((set, get) => ({
  runId: null,
  cursor: -1,
  maxCursor: -1,
  isPlaying: false,
  speed: 1,
  autoFollow: true,
  lockedActivationId: null,
  selectedMomentId: null,
  initialize: (runId, maxCursor) =>
    set((state) =>
      state.runId === runId && state.maxCursor === maxCursor
        ? state
        : {
            runId,
            maxCursor,
            cursor: -1,
            isPlaying: false,
            autoFollow: true,
            lockedActivationId: null,
            selectedMomentId: null,
          },
    ),
  play: () =>
    set((state) => ({
      isPlaying: state.cursor < state.maxCursor,
      autoFollow: true,
      lockedActivationId: null,
    })),
  pause: () => set({ isPlaying: false }),
  setSpeed: (speed) => set({ speed }),
  seek: (cursor) =>
    set((state) => ({
      cursor: clampCursor(cursor, state.maxCursor),
      isPlaying: false,
      autoFollow: false,
    })),
  step: (cursors, direction) => {
    const state = get();
    const ordered = Array.from(new Set(cursors)).sort((left, right) => left - right);
    const target =
      direction === 1
        ? ordered.find((item) => item > state.cursor) ?? state.maxCursor
        : [...ordered].reverse().find((item) => item < state.cursor) ?? -1;
    set({
      cursor: clampCursor(target, state.maxCursor),
      isPlaying: false,
      autoFollow: true,
      lockedActivationId: null,
    });
  },
  advance: () =>
    set((state) => {
      const cursor = clampCursor(state.cursor + 1, state.maxCursor);
      return {
        cursor,
        isPlaying: cursor < state.maxCursor,
      };
    }),
  lockActivation: (activationId) =>
    set({
      lockedActivationId: activationId,
      autoFollow: activationId === null,
      isPlaying: false,
    }),
  selectMoment: (momentId) => set({ selectedMomentId: momentId, isPlaying: false }),
  returnToCurrent: () =>
    set({
      lockedActivationId: null,
      selectedMomentId: null,
      autoFollow: true,
    }),
}));
