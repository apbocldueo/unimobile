import { describe, expect, it, vi } from "vitest";
import {
  parseStudioRunEvent,
  type StudioRunEvent,
  type StudioRunEventPage,
} from "@/entities/run";
import { HighlightQueue } from "./highlightQueue";
import {
  LiveRunSession,
  type EventSourceEvent,
  type EventSourceLike,
  type LiveRunSessionSnapshot,
} from "./liveRunSession";

const runId = `run-${"a".repeat(32)}`;

/** Build one strict event with stable identity and fingerprint. */
function event(sequence: number, kind = "complete"): StudioRunEvent {
  return parseStudioRunEvent({
    schemaVersion: 1,
    eventId: `event-${sequence}`,
    timestamp: sequence,
    source: kind === "run.terminal" ? "result" : "runtime",
    kind,
    payload: {},
    runtimeSequence: sequence,
    nodePath: "reasoning",
    activationId: "activation-1",
    interactionStep: 0,
    runId,
    sequence,
    fingerprint: `sha256:${String(sequence).padStart(64, "0")}`,
  });
}

/** Build one backend-shaped bounded page. */
function page(
  items: StudioRunEvent[],
  highWaterMark: number,
  terminal = false,
): StudioRunEventPage {
  return {
    schemaVersion: 1,
    runId,
    items,
    nextCursor: items.at(-1)?.sequence ?? 0,
    highWaterMark,
    terminal,
  };
}

class FakeEventSource implements EventSourceLike {
  readonly url: string;
  closed = false;
  private listeners = new Map<string, Array<(event: EventSourceEvent) => void>>();

  constructor(url: string) {
    this.url = url;
  }

  /** Register one deterministic EventSource callback. */
  addEventListener(
    type: "open" | "error" | "journal" | "heartbeat",
    listener: (event: EventSourceEvent) => void,
  ): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  /** Close this exact source so browser auto-reconnect cannot race the cursor. */
  close(): void {
    this.closed = true;
  }

  /** Deliver one test frame to registered listeners. */
  emit(type: "open" | "error" | "journal" | "heartbeat", data?: string): void {
    for (const listener of this.listeners.get(type) ?? []) listener({ data });
  }
}

/** Flush controller promise continuations without advancing timers. */
async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

describe("LiveRunSession", () => {
  it("backfills continuously, connects from confirmed cursor, and accepts live data", async () => {
    const sources: FakeEventSource[] = [];
    const snapshots: LiveRunSessionSnapshot[] = [];
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([event(1)], 2))
      .mockResolvedValueOnce(page([event(2)], 2));
    const session = new LiveRunSession(runId, {
      fetchPage,
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
      onChange: (snapshot) => snapshots.push(snapshot),
    });
    await session.start();
    expect(fetchPage).toHaveBeenNthCalledWith(1, runId, 0, 100);
    expect(fetchPage).toHaveBeenNthCalledWith(2, runId, 1, 100);
    expect(sources[0]?.url).toContain("after=2");
    sources[0]?.emit("open");
    sources[0]?.emit("heartbeat", '{"schemaVersion":1}');
    expect(session.current().cursor).toBe(2);
    sources[0]?.emit("journal", JSON.stringify(event(3)));
    expect(session.current()).toMatchObject({
      connection: "open",
      cursor: 3,
      deliveryMode: "live",
    });
    expect(snapshots.at(-1)?.events).toHaveLength(3);
  });

  it("ignores exact boundary duplicates and freezes on identity conflict", async () => {
    const sources: FakeEventSource[] = [];
    const session = new LiveRunSession(runId, {
      fetchPage: vi.fn().mockResolvedValue(page([event(1)], 1)),
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
      onChange: vi.fn(),
    });
    await session.start();
    sources[0]?.emit("journal", JSON.stringify(event(1)));
    expect(session.current().events).toHaveLength(1);
    sources[0]?.emit(
      "journal",
      JSON.stringify({
        ...event(1),
        fingerprint: `sha256:${"f".repeat(64)}`,
      }),
    );
    expect(session.current().connection).toBe("integrity-error");
    expect(session.current().events).toHaveLength(1);
    expect(sources[0]?.closed).toBe(true);
  });

  it("closes the old source, backfills latest cursor, and reconnects manually", async () => {
    const sources: FakeEventSource[] = [];
    const timers: Array<() => void> = [];
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([event(1)], 1))
      .mockResolvedValueOnce(page([event(2)], 2));
    const session = new LiveRunSession(runId, {
      fetchPage,
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
      setTimer: (callback) => {
        timers.push(callback);
        return timers.length as unknown as ReturnType<typeof setTimeout>;
      },
      clearTimer: vi.fn(),
      reconnectDelaysMs: [1],
      onChange: vi.fn(),
    });
    await session.start();
    sources[0]?.emit("error");
    expect(sources[0]?.closed).toBe(true);
    expect(session.current().connection).toBe("reconnecting");
    timers.shift()?.();
    await flush();
    expect(fetchPage).toHaveBeenLastCalledWith(runId, 1, 100);
    expect(sources[1]?.url).toContain("after=2");
  });

  it("uses backfill to resolve an SSE gap and stops uniquely at terminal", async () => {
    const sources: FakeEventSource[] = [];
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([event(1)], 1))
      .mockResolvedValueOnce(page([event(2), event(3)], 3));
    const session = new LiveRunSession(runId, {
      fetchPage,
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
      onChange: vi.fn(),
    });
    await session.start();
    sources[0]?.emit("journal", JSON.stringify(event(3)));
    await flush();
    expect(session.current().cursor).toBe(3);
    expect(sources[1]?.url).toContain("after=3");
    sources[1]?.emit("journal", JSON.stringify(event(4, "run.terminal")));
    expect(session.current().connection).toBe("terminal");
    expect(sources[1]?.closed).toBe(true);
    session.stop();
    expect(session.current().connection).toBe("stopped");
  });

  it("freezes the verified prefix when HTTP cannot fill a declared gap", async () => {
    const session = new LiveRunSession(runId, {
      fetchPage: vi.fn().mockResolvedValue(page([], 2)),
      createEventSource: vi.fn(),
      onChange: vi.fn(),
    });
    await session.start();
    expect(session.current()).toMatchObject({
      cursor: 0,
      connection: "integrity-error",
    });
  });
});

describe("HighlightQueue", () => {
  it("skips backfill animation, queues live highlights, and preempts on failure", () => {
    const visible: Array<string | null> = [];
    const timers: Array<() => void> = [];
    const queue = new HighlightQueue({
      onChange: (activationId) => visible.push(activationId),
      setTimer: (callback) => {
        timers.push(callback);
        return timers.length as unknown as ReturnType<typeof setTimeout>;
      },
      clearTimer: vi.fn(),
      minimumMs: 1,
    });
    queue.restore("backfilled-latest");
    queue.enqueue("fast-1");
    queue.enqueue("fast-2");
    expect(visible).toEqual(["backfilled-latest", "fast-1"]);
    timers.shift()?.();
    expect(visible.at(-1)).toBe("fast-2");
    queue.preempt("failed");
    expect(visible.at(-1)).toBe("failed");
    queue.dispose();
    expect(visible.at(-1)).toBeNull();
  });
});
