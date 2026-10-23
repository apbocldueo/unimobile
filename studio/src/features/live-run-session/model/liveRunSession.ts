import {
  getStudioRunEvents,
  parseStudioRunEvent,
  type StudioRunEvent,
  type StudioRunEventPage,
} from "@/entities/run";
import { studioApiUrl } from "@/shared/api";

export type LiveConnectionState =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "stale"
  | "terminal"
  | "integrity-error"
  | "stopped";

export type LiveDeliveryMode = "backfill" | "live";

export type LiveRunSessionSnapshot = {
  runId: string;
  connection: LiveConnectionState;
  cursor: number;
  highWaterMark: number;
  events: StudioRunEvent[];
  lastFreshAt: number | null;
  integrityError: string | null;
  deliveryMode: LiveDeliveryMode;
  deliveryVersion: number;
};

export type EventSourceEvent = { data?: string };

export interface EventSourceLike {
  addEventListener(
    type: "open" | "error" | "journal" | "heartbeat",
    listener: (event: EventSourceEvent) => void,
  ): void;
  close(): void;
}

export type LiveRunSessionDependencies = {
  fetchPage?: (
    runId: string,
    after: number,
    limit: number,
  ) => Promise<StudioRunEventPage>;
  createEventSource?: (url: string) => EventSourceLike;
  onChange: (snapshot: LiveRunSessionSnapshot) => void;
  now?: () => number;
  setTimer?: (callback: () => void, delayMs: number) => ReturnType<typeof setTimeout>;
  clearTimer?: (timer: ReturnType<typeof setTimeout>) => void;
  reconnectDelaysMs?: number[];
  staleAfterMs?: number;
};

/** Own one durable Run cursor across HTTP backfill and explicit SSE reconnects. */
export class LiveRunSession {
  readonly runId: string;
  private readonly dependencies: Required<LiveRunSessionDependencies>;
  private snapshot: LiveRunSessionSnapshot;
  private source: EventSourceLike | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private staleTimer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  private generation = 0;
  private reconnectAttempt = 0;
  private readonly bySequence = new Map<number, StudioRunEvent>();
  private readonly byIdentity = new Map<string, StudioRunEvent>();

  constructor(runId: string, dependencies: LiveRunSessionDependencies) {
    this.runId = runId;
    this.dependencies = {
      fetchPage: dependencies.fetchPage ?? getStudioRunEvents,
      createEventSource:
        dependencies.createEventSource
        ?? ((url) => new EventSource(url) as unknown as EventSourceLike),
      onChange: dependencies.onChange,
      now: dependencies.now ?? Date.now,
      setTimer:
        dependencies.setTimer
        ?? ((callback, delayMs) => globalThis.setTimeout(callback, delayMs)),
      clearTimer:
        dependencies.clearTimer
        ?? ((timer) => globalThis.clearTimeout(timer)),
      reconnectDelaysMs: dependencies.reconnectDelaysMs ?? [
        250,
        500,
        1000,
        2000,
        5000,
      ],
      staleAfterMs: dependencies.staleAfterMs ?? 15_000,
    };
    this.snapshot = {
      runId,
      connection: "idle",
      cursor: 0,
      highWaterMark: 0,
      events: [],
      lastFreshAt: null,
      integrityError: null,
      deliveryMode: "backfill",
      deliveryVersion: 0,
    };
  }

  /** Start initial durable backfill followed by a cursor-bound SSE stream. */
  async start(): Promise<void> {
    if (this.stopped) return;
    this.update({ connection: "connecting" });
    await this.backfillAndConnect("backfill");
  }

  /** Close EventSource and every reconnect/freshness timer permanently. */
  stop(): void {
    this.stopped = true;
    this.generation += 1;
    this.closeSource();
    this.clearTimers();
    this.update({ connection: "stopped" });
  }

  /** Read the current detached state for tests and consumers. */
  current(): LiveRunSessionSnapshot {
    return {
      ...this.snapshot,
      events: [...this.snapshot.events],
    };
  }

  /** Backfill continuously through each returned high-water mark, then connect. */
  private async backfillAndConnect(mode: LiveDeliveryMode): Promise<void> {
    const generation = ++this.generation;
    try {
      while (!this.stopped && generation === this.generation) {
        const page = await this.dependencies.fetchPage(
          this.runId,
          this.snapshot.cursor,
          100,
        );
        if (page.runId !== this.runId) {
          this.failIntegrity("Event page belongs to a different Run");
          return;
        }
        const before = this.snapshot.cursor;
        for (const event of page.items) {
          if (!this.accept(event, mode)) return;
        }
        this.update({ highWaterMark: page.highWaterMark });
        if (this.snapshot.cursor >= page.highWaterMark) break;
        if (this.snapshot.cursor === before) {
          this.failIntegrity("HTTP backfill could not fill the journal gap");
          return;
        }
      }
      if (
        !this.stopped
        && generation === this.generation
        && this.snapshot.connection !== "terminal"
        && this.snapshot.connection !== "integrity-error"
      ) {
        this.connect();
      }
    } catch (error) {
      if (generation !== this.generation || this.stopped) return;
      this.scheduleReconnect(
        error instanceof Error ? error.message : "Run journal backfill failed",
      );
    }
  }

  /** Create one EventSource whose URL contains the latest confirmed cursor. */
  private connect(): void {
    this.closeSource();
    const cursor = this.snapshot.cursor;
    const source = this.dependencies.createEventSource(
      studioApiUrl(
        `/api/studio/runs/${encodeURIComponent(this.runId)}/events/stream?after=${cursor}`,
      ),
    );
    this.source = source;
    source.addEventListener("open", () => {
      if (this.source !== source || this.stopped) return;
      this.reconnectAttempt = 0;
      this.markFresh("open");
    });
    source.addEventListener("heartbeat", () => {
      if (this.source !== source || this.stopped) return;
      this.markFresh(this.snapshot.connection);
    });
    source.addEventListener("journal", (frame) => {
      if (this.source !== source || this.stopped) return;
      try {
        const event = parseStudioRunEvent(JSON.parse(frame.data ?? ""));
        if (event.sequence > this.snapshot.cursor + 1) {
          this.closeSource();
          this.update({ connection: "reconnecting" });
          void this.backfillAndConnect("backfill");
          return;
        }
        this.accept(event, "live");
        this.markFresh(this.snapshot.connection);
      } catch (error) {
        this.failIntegrity(
          error instanceof Error ? error.message : "Invalid SSE journal frame",
        );
      }
    });
    source.addEventListener("error", () => {
      if (this.source !== source || this.stopped) return;
      this.closeSource();
      this.scheduleReconnect("EventSource disconnected");
    });
    this.update({
      connection:
        this.snapshot.connection === "connecting" ? "connecting" : "reconnecting",
    });
  }

  /** Accept exact duplicates while freezing on identity or sequence conflicts. */
  private accept(
    event: StudioRunEvent,
    deliveryMode: LiveDeliveryMode,
  ): boolean {
    if (event.runId !== this.runId) {
      this.failIntegrity("Journal event belongs to a different Run");
      return false;
    }
    const bySequence = this.bySequence.get(event.sequence);
    const byIdentity = this.byIdentity.get(event.eventId);
    if (bySequence || byIdentity) {
      const existing = bySequence ?? byIdentity!;
      if (
        existing.sequence === event.sequence
        && existing.eventId === event.eventId
        && existing.fingerprint === event.fingerprint
      ) {
        return true;
      }
      this.failIntegrity("Journal event identity or fingerprint conflict");
      return false;
    }
    if (event.sequence !== this.snapshot.cursor + 1) {
      this.failIntegrity("Journal sequence is not continuous");
      return false;
    }
    this.bySequence.set(event.sequence, event);
    this.byIdentity.set(event.eventId, event);
    this.snapshot = {
      ...this.snapshot,
      cursor: event.sequence,
      highWaterMark: Math.max(this.snapshot.highWaterMark, event.sequence),
      events: [...this.snapshot.events, event],
      deliveryMode,
      deliveryVersion: this.snapshot.deliveryVersion + 1,
      lastFreshAt: this.dependencies.now(),
    };
    if (event.kind === "run.terminal") {
      this.closeSource();
      this.clearTimers();
      this.snapshot = { ...this.snapshot, connection: "terminal" };
    }
    this.emit();
    return true;
  }

  /** Explicitly close and rebuild after bounded delay from confirmed cursor. */
  private scheduleReconnect(_reason: string): void {
    if (
      this.stopped
      || this.snapshot.connection === "terminal"
      || this.snapshot.connection === "integrity-error"
    ) {
      return;
    }
    this.closeSource();
    this.update({ connection: "reconnecting" });
    const delays = this.dependencies.reconnectDelaysMs;
    const delay = delays[Math.min(this.reconnectAttempt, delays.length - 1)] ?? 5000;
    this.reconnectAttempt += 1;
    this.reconnectTimer = this.dependencies.setTimer(() => {
      this.reconnectTimer = null;
      if (!this.stopped) void this.backfillAndConnect("backfill");
    }, delay);
  }

  /** Refresh connection freshness and arm a non-factual stale timer. */
  private markFresh(connection: LiveConnectionState): void {
    if (this.staleTimer) this.dependencies.clearTimer(this.staleTimer);
    this.update({
      connection: connection === "connecting" || connection === "reconnecting"
        ? "open"
        : connection,
      lastFreshAt: this.dependencies.now(),
    });
    this.staleTimer = this.dependencies.setTimer(() => {
      this.staleTimer = null;
      if (this.snapshot.connection === "open") {
        this.update({ connection: "stale" });
      }
    }, this.dependencies.staleAfterMs);
  }

  /** Freeze the last verified prefix after one contract-integrity failure. */
  private failIntegrity(message: string): void {
    this.closeSource();
    this.clearTimers();
    this.update({
      connection: "integrity-error",
      integrityError: message,
    });
  }

  /** Apply a state patch and publish a detached snapshot. */
  private update(patch: Partial<LiveRunSessionSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    this.emit();
  }

  /** Publish a detached snapshot to the owning React boundary. */
  private emit(): void {
    this.dependencies.onChange(this.current());
  }

  /** Close the active EventSource before any manual reconnect. */
  private closeSource(): void {
    this.source?.close();
    this.source = null;
  }

  /** Clear reconnect and stale timers during every terminal cleanup path. */
  private clearTimers(): void {
    if (this.reconnectTimer) {
      this.dependencies.clearTimer(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.staleTimer) {
      this.dependencies.clearTimer(this.staleTimer);
      this.staleTimer = null;
    }
  }
}
