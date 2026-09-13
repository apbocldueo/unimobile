import {
  getBenchmarkExperimentEvents,
  parseBenchmarkExperimentEvent,
  type BenchmarkExperimentEvent,
  type BenchmarkExperimentEventPage,
} from "@/entities/benchmark-experiment";
import { studioApiUrl } from "@/shared/api";

export type BenchmarkEventConnectionState =
  | "idle"
  | "backfilling"
  | "connecting"
  | "live"
  | "reconnecting"
  | "terminal"
  | "frozen"
  | "stopped";

export type BenchmarkEventDeliveryMode = "backfill" | "live";

export type BenchmarkEventAuditSummary = Pick<
  BenchmarkExperimentEvent,
  | "schemaVersion"
  | "eventId"
  | "timestamp"
  | "source"
  | "kind"
  | "taskRunId"
  | "sourceSequence"
  | "phase"
  | "experimentId"
  | "sequence"
  | "fingerprint"
>;

export type BenchmarkEventSessionSnapshot = {
  experimentId: string;
  connection: BenchmarkEventConnectionState;
  cursor: number;
  highWaterMark: number;
  events: BenchmarkEventAuditSummary[];
  lastFreshAt: number | null;
  integrityError: string | null;
  deliveryMode: BenchmarkEventDeliveryMode;
  deliveryVersion: number;
};

export type BenchmarkEventAcceptance =
  | { disposition: "next" }
  | { disposition: "duplicate" }
  | { disposition: "gap"; missingAfter: number }
  | { disposition: "conflict"; message: string };

type AcceptedEventIdentity = {
  sequence: number;
  eventId: string;
  fingerprint: string;
};

export type BenchmarkEventAcceptanceIndex = {
  cursor: number;
  bySequence: ReadonlyMap<number, AcceptedEventIdentity>;
  byIdentity: ReadonlyMap<string, AcceptedEventIdentity>;
};

export type BenchmarkEventSourceEvent = { data?: string };

export interface BenchmarkEventSourceLike {
  addEventListener(
    type: "open" | "error" | "journal" | "heartbeat",
    listener: (event: BenchmarkEventSourceEvent) => void,
  ): void;
  close(): void;
}

export type BenchmarkEventSessionDependencies = {
  fetchPage?: (
    experimentId: string,
    after: number,
    limit: number,
  ) => Promise<BenchmarkExperimentEventPage>;
  createEventSource?: (url: string) => BenchmarkEventSourceLike;
  onChange: (snapshot: BenchmarkEventSessionSnapshot) => void;
  onProgress?: (snapshot: BenchmarkEventSessionSnapshot) => void;
  now?: () => number;
  setTimer?: (
    callback: () => void,
    delayMs: number,
  ) => ReturnType<typeof setTimeout>;
  clearTimer?: (timer: ReturnType<typeof setTimeout>) => void;
  reconnectDelaysMs?: number[];
  retainedEventLimit?: number;
  retainedIdentityLimit?: number;
};

/** Classify one validated envelope against the last verified journal prefix.
 *
 * Args:
 *   event: Strict, versioned Benchmark journal envelope.
 *   index: Current cursor and bounded accepted-identity indexes.
 *
 * Returns:
 *   A pure next, duplicate, gap, or integrity-conflict decision.
 */
export function classifyBenchmarkEvent(
  event: BenchmarkExperimentEvent,
  index: BenchmarkEventAcceptanceIndex,
): BenchmarkEventAcceptance {
  const bySequence = index.bySequence.get(event.sequence);
  const byIdentity = index.byIdentity.get(event.eventId);
  if (bySequence || byIdentity) {
    const existing = bySequence ?? byIdentity!;
    if (
      existing.sequence === event.sequence
      && existing.eventId === event.eventId
      && existing.fingerprint === event.fingerprint
      && bySequence?.eventId === event.eventId
      && byIdentity?.sequence === event.sequence
    ) {
      return { disposition: "duplicate" };
    }
    return {
      disposition: "conflict",
      message: "Journal event identity, sequence, or fingerprint conflicts",
    };
  }
  if (event.sequence <= index.cursor) {
    return {
      disposition: "conflict",
      message: "An old journal event is outside the retained verification window",
    };
  }
  if (event.sequence > index.cursor + 1) {
    return { disposition: "gap", missingAfter: index.cursor };
  }
  return { disposition: "next" };
}

/** Strip payload content while retaining the safe envelope audit fields. */
export function summarizeBenchmarkEvent(
  event: BenchmarkExperimentEvent,
): BenchmarkEventAuditSummary {
  return {
    schemaVersion: event.schemaVersion,
    eventId: event.eventId,
    timestamp: event.timestamp,
    source: event.source,
    kind: event.kind,
    taskRunId: event.taskRunId,
    sourceSequence: event.sourceSequence,
    phase: event.phase,
    experimentId: event.experimentId,
    sequence: event.sequence,
    fingerprint: event.fingerprint,
  };
}

/** Own one verified Experiment-local cursor across bounded HTTP and named SSE. */
export class BenchmarkEventSession {
  readonly experimentId: string;
  private readonly dependencies: Required<BenchmarkEventSessionDependencies>;
  private snapshot: BenchmarkEventSessionSnapshot;
  private source: BenchmarkEventSourceLike | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  private generation = 0;
  private reconnectAttempt = 0;
  private readonly bySequence = new Map<number, AcceptedEventIdentity>();
  private readonly byIdentity = new Map<string, AcceptedEventIdentity>();
  private readonly identityOrder: AcceptedEventIdentity[] = [];

  constructor(
    experimentId: string,
    dependencies: BenchmarkEventSessionDependencies,
  ) {
    this.experimentId = experimentId;
    this.dependencies = {
      fetchPage: dependencies.fetchPage ?? getBenchmarkExperimentEvents,
      createEventSource:
        dependencies.createEventSource
        ?? ((url) => new EventSource(url) as unknown as BenchmarkEventSourceLike),
      onChange: dependencies.onChange,
      onProgress: dependencies.onProgress ?? (() => undefined),
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
      retainedEventLimit: dependencies.retainedEventLimit ?? 250,
      retainedIdentityLimit: dependencies.retainedIdentityLimit ?? 1000,
    };
    if (
      this.dependencies.retainedEventLimit < 1
      || this.dependencies.retainedIdentityLimit
        < this.dependencies.retainedEventLimit
    ) {
      throw new Error(
        "retained identity limit must be at least the positive event limit",
      );
    }
    this.snapshot = {
      experimentId,
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

  /** Start initial page backfill to one captured high-water, then connect SSE. */
  async start(): Promise<void> {
    if (this.stopped) return;
    await this.backfillAndConnect("connecting");
  }

  /** Retry from the last verified cursor after transport or integrity failure. */
  async retry(): Promise<void> {
    if (this.stopped) return;
    this.closeSource();
    this.clearReconnectTimer();
    this.snapshot = {
      ...this.snapshot,
      connection: "reconnecting",
      integrityError: null,
    };
    this.emit();
    await this.backfillAndConnect("reconnecting");
  }

  /** Close the active transport and ignore every in-flight completion. */
  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    this.generation += 1;
    this.closeSource();
    this.clearReconnectTimer();
    this.update({ connection: "stopped" });
  }

  /** Read one detached session snapshot for React and deterministic tests. */
  current(): BenchmarkEventSessionSnapshot {
    return {
      ...this.snapshot,
      events: [...this.snapshot.events],
    };
  }

  /** Backfill to the first page's captured high-water before opening SSE. */
  private async backfillAndConnect(
    origin: "connecting" | "reconnecting",
  ): Promise<void> {
    const generation = ++this.generation;
    this.update({ connection: "backfilling", deliveryMode: "backfill" });
    try {
      let capturedHighWater: number | null = null;
      while (!this.stopped && generation === this.generation) {
        const page = await this.dependencies.fetchPage(
          this.experimentId,
          this.snapshot.cursor,
          100,
        );
        if (this.stopped || generation !== this.generation) return;
        if (!this.validatePage(page)) return;
        capturedHighWater ??= page.highWaterMark;
        const before = this.snapshot.cursor;
        for (const event of page.items) {
          const accepted = this.accept(event, "backfill");
          if (!accepted) return;
        }
        this.update({
          highWaterMark: Math.max(
            this.snapshot.highWaterMark,
            page.highWaterMark,
          ),
        });
        if (page.terminal && this.snapshot.cursor >= page.highWaterMark) {
          this.finishTerminal();
          return;
        }
        if (this.snapshot.cursor >= capturedHighWater) break;
        if (this.snapshot.cursor === before) {
          this.failIntegrity("HTTP backfill could not fill the journal gap");
          return;
        }
      }
      if (
        !this.stopped
        && generation === this.generation
        && this.snapshot.connection !== "terminal"
        && this.snapshot.connection !== "frozen"
      ) {
        this.connect(origin);
      }
    } catch (error) {
      if (this.stopped || generation !== this.generation) return;
      this.scheduleReconnect(
        error instanceof Error
          ? error.message
          : "Benchmark journal backfill failed",
      );
    }
  }

  /** Validate page scope and exclusive-cursor continuity against local state. */
  private validatePage(page: BenchmarkExperimentEventPage): boolean {
    if (page.experimentId !== this.experimentId) {
      this.failIntegrity("Event page belongs to a different Experiment");
      return false;
    }
    if (
      page.items.length > 0
      && page.items[0]!.sequence !== this.snapshot.cursor + 1
    ) {
      this.failIntegrity("HTTP event page starts after a journal gap");
      return false;
    }
    if (
      (page.items.length > 0
        && page.items.at(-1)!.sequence !== page.nextCursor)
      || (page.items.length === 0 && page.nextCursor !== this.snapshot.cursor)
      || page.nextCursor > page.highWaterMark
    ) {
      this.failIntegrity("HTTP event page returned an invalid cursor");
      return false;
    }
    if (page.nextCursor < this.snapshot.cursor) {
      this.failIntegrity("HTTP event page cursor moved backwards");
      return false;
    }
    return true;
  }

  /** Open named SSE from the latest explicitly verified exclusive cursor. */
  private connect(origin: "connecting" | "reconnecting"): void {
    this.closeSource();
    const source = this.dependencies.createEventSource(
      studioApiUrl(
        `/studio/benchmark-experiments/${encodeURIComponent(this.experimentId)}/events/stream?after=${this.snapshot.cursor}`,
      ),
    );
    this.source = source;
    source.addEventListener("open", () => {
      if (!this.isCurrentSource(source)) return;
      this.reconnectAttempt = 0;
      this.update({
        connection: "live",
        lastFreshAt: this.dependencies.now(),
      });
    });
    source.addEventListener("heartbeat", () => {
      if (!this.isCurrentSource(source)) return;
      this.update({ lastFreshAt: this.dependencies.now() });
    });
    source.addEventListener("journal", (frame) => {
      if (!this.isCurrentSource(source)) return;
      this.receiveJournalFrame(frame);
    });
    source.addEventListener("error", () => {
      if (!this.isCurrentSource(source)) return;
      this.scheduleReconnect("EventSource disconnected");
    });
    this.update({
      connection: origin === "connecting" ? "connecting" : "reconnecting",
    });
  }

  /** Parse one SSE frame, repair future gaps, and terminal-drain through HTTP. */
  private receiveJournalFrame(frame: BenchmarkEventSourceEvent): void {
    try {
      const event = parseBenchmarkExperimentEvent(
        JSON.parse(frame.data ?? ""),
      );
      const decision = classifyBenchmarkEvent(event, this.acceptanceIndex());
      if (decision.disposition === "gap") {
        this.closeSource();
        this.update({ connection: "reconnecting" });
        void this.recoverGapAndConnect(event);
        return;
      }
      if (decision.disposition === "conflict") {
        this.failIntegrity(decision.message);
        return;
      }
      if (decision.disposition === "duplicate") {
        this.update({ lastFreshAt: this.dependencies.now() });
        return;
      }
      if (!this.accept(event, "live")) return;
      this.update({ lastFreshAt: this.dependencies.now() });
      if (event.kind === "experiment.terminal") {
        this.closeSource();
        void this.drainTerminal();
      }
    } catch (error) {
      this.failIntegrity(
        error instanceof Error ? error.message : "Invalid SSE journal frame",
      );
    }
  }

  /** Fill a detected SSE gap, accept the triggering frame, then reconnect. */
  private async recoverGapAndConnect(
    triggeringEvent: BenchmarkExperimentEvent,
  ): Promise<void> {
    const generation = ++this.generation;
    try {
      while (
        !this.stopped
        && generation === this.generation
        && this.snapshot.cursor < triggeringEvent.sequence - 1
      ) {
        const page = await this.dependencies.fetchPage(
          this.experimentId,
          this.snapshot.cursor,
          100,
        );
        if (this.stopped || generation !== this.generation) return;
        if (!this.validatePage(page)) return;
        const before = this.snapshot.cursor;
        for (const event of page.items) {
          if (!this.accept(event, "backfill")) return;
        }
        this.update({
          highWaterMark: Math.max(
            this.snapshot.highWaterMark,
            page.highWaterMark,
          ),
        });
        if (this.snapshot.cursor === before) {
          this.failIntegrity("HTTP gap repair did not advance the journal");
          return;
        }
      }
      if (this.stopped || generation !== this.generation) return;
      const decision = classifyBenchmarkEvent(
        triggeringEvent,
        this.acceptanceIndex(),
      );
      if (decision.disposition === "next") {
        if (!this.accept(triggeringEvent, "live")) return;
      } else if (decision.disposition === "conflict") {
        this.failIntegrity(decision.message);
        return;
      } else if (decision.disposition === "gap") {
        this.failIntegrity("HTTP gap repair did not reach the triggering event");
        return;
      }
      if (triggeringEvent.kind === "experiment.terminal") {
        await this.drainTerminal();
        return;
      }
      this.connect("reconnecting");
    } catch (error) {
      if (this.stopped || generation !== this.generation) return;
      this.scheduleReconnect(
        error instanceof Error ? error.message : "Journal gap repair failed",
      );
    }
  }

  /** Query after a delivered terminal event until the service confirms drain. */
  private async drainTerminal(): Promise<void> {
    const generation = ++this.generation;
    this.update({ connection: "backfilling", deliveryMode: "backfill" });
    try {
      while (!this.stopped && generation === this.generation) {
        const page = await this.dependencies.fetchPage(
          this.experimentId,
          this.snapshot.cursor,
          100,
        );
        if (this.stopped || generation !== this.generation) return;
        if (!this.validatePage(page)) return;
        const before = this.snapshot.cursor;
        for (const event of page.items) {
          if (!this.accept(event, "backfill")) return;
        }
        this.update({
          highWaterMark: Math.max(
            this.snapshot.highWaterMark,
            page.highWaterMark,
          ),
        });
        if (page.terminal && this.snapshot.cursor >= page.highWaterMark) {
          this.finishTerminal();
          return;
        }
        if (this.snapshot.cursor === before) {
          this.failIntegrity(
            "Terminal event was delivered but final drain was not confirmed",
          );
          return;
        }
      }
    } catch (error) {
      if (this.stopped || generation !== this.generation) return;
      this.scheduleReconnect(
        error instanceof Error ? error.message : "Terminal drain failed",
      );
    }
  }

  /** Accept one continuous event and publish only a bounded safe audit summary. */
  private accept(
    event: BenchmarkExperimentEvent,
    deliveryMode: BenchmarkEventDeliveryMode,
  ): boolean {
    if (event.experimentId !== this.experimentId) {
      this.failIntegrity("Journal event belongs to a different Experiment");
      return false;
    }
    const decision = classifyBenchmarkEvent(event, this.acceptanceIndex());
    if (decision.disposition === "duplicate") return true;
    if (decision.disposition === "conflict") {
      this.failIntegrity(decision.message);
      return false;
    }
    if (decision.disposition === "gap") {
      this.failIntegrity("Journal sequence is not continuous");
      return false;
    }
    const identity = {
      sequence: event.sequence,
      eventId: event.eventId,
      fingerprint: event.fingerprint,
    };
    this.bySequence.set(identity.sequence, identity);
    this.byIdentity.set(identity.eventId, identity);
    this.identityOrder.push(identity);
    this.trimIdentityIndex();
    const events = [
      ...this.snapshot.events,
      summarizeBenchmarkEvent(event),
    ].slice(-this.dependencies.retainedEventLimit);
    this.snapshot = {
      ...this.snapshot,
      cursor: event.sequence,
      highWaterMark: Math.max(this.snapshot.highWaterMark, event.sequence),
      events,
      deliveryMode,
      deliveryVersion: this.snapshot.deliveryVersion + 1,
      lastFreshAt: this.dependencies.now(),
    };
    this.emit();
    this.dependencies.onProgress(this.current());
    return true;
  }

  /** Remove oldest verification identities after the configured memory bound. */
  private trimIdentityIndex(): void {
    while (
      this.identityOrder.length > this.dependencies.retainedIdentityLimit
    ) {
      const removed = this.identityOrder.shift();
      if (!removed) return;
      this.bySequence.delete(removed.sequence);
      this.byIdentity.delete(removed.eventId);
    }
  }

  /** Return read-only indexes for the pure acceptance classifier. */
  private acceptanceIndex(): BenchmarkEventAcceptanceIndex {
    return {
      cursor: this.snapshot.cursor,
      bySequence: this.bySequence,
      byIdentity: this.byIdentity,
    };
  }

  /** Schedule a bounded explicit backfill reconnect from confirmed cursor. */
  private scheduleReconnect(_reason: string): void {
    if (
      this.stopped
      || this.snapshot.connection === "terminal"
      || this.snapshot.connection === "frozen"
    ) {
      return;
    }
    this.generation += 1;
    this.closeSource();
    this.clearReconnectTimer();
    this.update({ connection: "reconnecting" });
    const delays = this.dependencies.reconnectDelaysMs;
    const delay = delays[
      Math.min(this.reconnectAttempt, delays.length - 1)
    ] ?? 5000;
    this.reconnectAttempt += 1;
    this.reconnectTimer = this.dependencies.setTimer(() => {
      this.reconnectTimer = null;
      if (!this.stopped) void this.backfillAndConnect("reconnecting");
    }, delay);
  }

  /** Freeze the last verified prefix after an unrecoverable integrity fault. */
  private failIntegrity(message: string): void {
    this.generation += 1;
    this.closeSource();
    this.clearReconnectTimer();
    this.update({ connection: "frozen", integrityError: message });
  }

  /** Enter terminal-complete only after a terminal page confirms final drain. */
  private finishTerminal(): void {
    this.generation += 1;
    this.closeSource();
    this.clearReconnectTimer();
    this.update({ connection: "terminal" });
  }

  /** Test whether an asynchronous browser callback still owns the transport. */
  private isCurrentSource(source: BenchmarkEventSourceLike): boolean {
    return this.source === source && !this.stopped;
  }

  /** Apply one state patch and publish a detached snapshot. */
  private update(patch: Partial<BenchmarkEventSessionSnapshot>): void {
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

  /** Clear the single scheduled manual reconnect, if one exists. */
  private clearReconnectTimer(): void {
    if (!this.reconnectTimer) return;
    this.dependencies.clearTimer(this.reconnectTimer);
    this.reconnectTimer = null;
  }
}
