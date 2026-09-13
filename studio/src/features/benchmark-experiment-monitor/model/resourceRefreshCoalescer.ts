export type ResourceRefreshCoalescerDependencies = {
  refresh: () => void | Promise<void>;
  setTimer?: (
    callback: () => void,
    delayMs: number,
  ) => ReturnType<typeof setTimeout>;
  clearTimer?: (timer: ReturnType<typeof setTimeout>) => void;
  delayMs?: number;
};

/** Coalesce a burst of committed journal progress into one resource refresh. */
export class ResourceRefreshCoalescer {
  private readonly refresh: () => void | Promise<void>;
  private readonly setTimer: (
    callback: () => void,
    delayMs: number,
  ) => ReturnType<typeof setTimeout>;
  private readonly clearTimer: (timer: ReturnType<typeof setTimeout>) => void;
  private readonly delayMs: number;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private disposed = false;

  constructor(dependencies: ResourceRefreshCoalescerDependencies) {
    this.refresh = dependencies.refresh;
    this.setTimer =
      dependencies.setTimer
      ?? ((callback, delayMs) => globalThis.setTimeout(callback, delayMs));
    this.clearTimer =
      dependencies.clearTimer
      ?? ((timer) => globalThis.clearTimeout(timer));
    this.delayMs = dependencies.delayMs ?? 40;
  }

  /** Schedule one refresh unless the current journal burst already has one. */
  request(): void {
    if (this.disposed || this.timer) return;
    this.timer = this.setTimer(() => {
      this.timer = null;
      if (!this.disposed) void this.refresh();
    }, this.delayMs);
  }

  /** Cancel a pending refresh when the owning Monitor unmounts. */
  dispose(): void {
    this.disposed = true;
    if (!this.timer) return;
    this.clearTimer(this.timer);
    this.timer = null;
  }
}
