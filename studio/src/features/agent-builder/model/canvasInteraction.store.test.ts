import { afterEach, describe, expect, it, vi } from "vitest";
import { useCanvasInteractionStore } from "./canvasInteraction.store";

afterEach(() => useCanvasInteractionStore.setState({ port: null }));

describe("disposable canvas command ownership", () => {
  it("does not let an old canvas cleanup unregister a newer session", () => {
    const first = { sessionId: 1, placement: () => null, reveal: vi.fn() };
    const next = { sessionId: 2, placement: () => null, reveal: vi.fn() };
    const cleanFirst = useCanvasInteractionStore.getState().register(first);
    const cleanNext = useCanvasInteractionStore.getState().register(next);
    cleanFirst();
    expect(useCanvasInteractionStore.getState().port).toBe(next);
    cleanNext();
    expect(useCanvasInteractionStore.getState().port).toBeNull();
    expect(first.reveal).not.toHaveBeenCalled();
    expect(next.reveal).not.toHaveBeenCalled();
  });
});
