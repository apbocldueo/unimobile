import { create } from "zustand";

export type ToastTone = "success" | "info" | "warning" | "error";

export type ToastItem = {
  id: string;
  message: string;
  tone?: ToastTone;
};

const dismissTimers = new Map<string, ReturnType<typeof setTimeout>>();
const DEFAULT_MS = 4000;

type ToastState = {
  toasts: ToastItem[];
  pushToast: (payload: Omit<ToastItem, "id"> & { id?: string; durationMs?: number }) => void;
  dismiss: (id: string) => void;
};

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],

  dismiss: (id) => {
    const t = dismissTimers.get(id);
    if (t) clearTimeout(t);
    dismissTimers.delete(id);
    set({ toasts: get().toasts.filter((x) => x.id !== id) });
  },

  pushToast: (payload) => {
    const id = payload.id ?? `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    const item: ToastItem = { id, message: payload.message, tone: payload.tone ?? "info" };
    set({ toasts: [...get().toasts, item] });
    const ms = payload.durationMs ?? DEFAULT_MS;
    const tid = setTimeout(() => get().dismiss(id), ms);
    dismissTimers.set(id, tid);
  },
}));
