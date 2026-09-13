export type HighlightQueueDependencies = {
  onChange: (activationId: string | null) => void;
  setTimer?: (callback: () => void, delayMs: number) => ReturnType<typeof setTimeout>;
  clearTimer?: (timer: ReturnType<typeof setTimeout>) => void;
  minimumMs?: number;
};

/** Present fast live activations without delaying the factual Run projection. */
export class HighlightQueue {
  private readonly onChange: (activationId: string | null) => void;
  private readonly setTimer: NonNullable<HighlightQueueDependencies["setTimer"]>;
  private readonly clearTimer: NonNullable<HighlightQueueDependencies["clearTimer"]>;
  private readonly minimumMs: number;
  private queue: string[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private current: string | null = null;

  constructor(dependencies: HighlightQueueDependencies) {
    this.onChange = dependencies.onChange;
    this.setTimer =
      dependencies.setTimer
      ?? ((callback, delayMs) => globalThis.setTimeout(callback, delayMs));
    this.clearTimer =
      dependencies.clearTimer
      ?? ((timer) => globalThis.clearTimeout(timer));
    this.minimumMs = dependencies.minimumMs ?? 180;
  }

  /** Queue one newly streamed activation for a bounded minimum highlight. */
  enqueue(activationId: string): void {
    if (activationId === this.current || this.queue.includes(activationId)) return;
    this.queue.push(activationId);
    this.advance();
  }

  /** Skip animation during backfill and show only the latest factual activation. */
  restore(activationId: string | null): void {
    this.queue = [];
    if (this.timer) this.clearTimer(this.timer);
    this.timer = null;
    this.current = activationId;
    this.onChange(activationId);
  }

  /** Let failure or terminal facts preempt stale presentation backlog. */
  preempt(activationId: string | null): void {
    this.restore(activationId);
  }

  /** Release the visual timer on route change or unmount. */
  dispose(): void {
    this.restore(null);
  }

  /** Advance presentation independently from the factual reducer cursor. */
  private advance(): void {
    if (this.timer || this.queue.length === 0) return;
    this.current = this.queue.shift() ?? null;
    this.onChange(this.current);
    this.timer = this.setTimer(() => {
      this.timer = null;
      this.advance();
    }, this.minimumMs);
  }
}
