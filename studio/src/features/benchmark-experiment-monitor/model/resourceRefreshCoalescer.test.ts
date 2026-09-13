import { describe, expect, it, vi } from "vitest";
import { ResourceRefreshCoalescer } from "./resourceRefreshCoalescer";

describe("ResourceRefreshCoalescer", () => {
  it("coalesces progress and cancels pending refresh after disposal", () => {
    const refresh = vi.fn();
    const timers: Array<() => void> = [];
    const coalescer = new ResourceRefreshCoalescer({
      refresh,
      setTimer: (callback) => {
        timers.push(callback);
        return timers.length as unknown as ReturnType<typeof setTimeout>;
      },
      clearTimer: vi.fn(),
    });
    coalescer.request();
    coalescer.request();
    expect(timers).toHaveLength(1);
    timers.shift()?.();
    expect(refresh).toHaveBeenCalledTimes(1);
    coalescer.request();
    coalescer.dispose();
    timers.shift()?.();
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
