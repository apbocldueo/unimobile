import { describe, expect, it, vi } from "vitest";
import {
  parseBenchmarkExperimentEvent,
  type BenchmarkExperimentEvent,
  type BenchmarkExperimentEventPage,
} from "@/entities/benchmark-experiment";
import {
  BenchmarkEventSession,
  classifyBenchmarkEvent,
  type BenchmarkEventSessionSnapshot,
  type BenchmarkEventSourceEvent,
  type BenchmarkEventSourceLike,
} from "./benchmarkEventSession";

const experimentId = `experiment-${"a".repeat(32)}`;

/** Build one strict event with deterministic Experiment-local identity. */
function event(
  sequence: number,
  kind = "benchmark.phase.completed.v1",
): BenchmarkExperimentEvent {
  const suffix = sequence.toString(16).padStart(32, "0");
  return parseBenchmarkExperimentEvent({
    schemaVersion: 1,
    eventId: `benchmark-event-${suffix}`,
    timestamp: sequence,
    source: kind === "experiment.terminal" ? "service" : "worker",
    kind,
    taskRunId: `task-run-${"b".repeat(32)}`,
    sourceSequence: sequence,
    phase: "execute",
    payload: { safe: true },
    experimentId,
    sequence,
    fingerprint: `sha256:${sequence.toString(16).padStart(64, "0")}`,
  });
}

/** Build one backend-shaped page whose empty cursor remains exclusive. */
function page(
  items: BenchmarkExperimentEvent[],
  highWaterMark: number,
  terminal = false,
  after = 0,
): BenchmarkExperimentEventPage {
  return {
    schemaVersion: 1,
    experimentId,
    items,
    nextCursor: items.at(-1)?.sequence ?? after,
    highWaterMark,
    terminal,
  };
}

class FakeEventSource implements BenchmarkEventSourceLike {
  readonly url: string;
  closed = false;
  private listeners = new Map<
    string,
    Array<(frame: BenchmarkEventSourceEvent) => void>
  >();

  constructor(url: string) {
    this.url = url;
  }

  /** Register one named EventSource listener for deterministic delivery. */
  addEventListener(
    type: "open" | "error" | "journal" | "heartbeat",
    listener: (event: BenchmarkEventSourceEvent) => void,
  ): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  /** Record explicit closure so tests can reject browser-owned auto-retry. */
  close(): void {
    this.closed = true;
  }

  /** Deliver one named frame to every listener registered for that event. */
  emit(
    type: "open" | "error" | "journal" | "heartbeat",
    data?: string,
  ): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data });
    }
  }
}

/** Flush chained session promise continuations without advancing timers. */
async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe("classifyBenchmarkEvent", () => {
  it("distinguishes next, gap, exact duplicate, and canonical conflict", () => {
    const accepted = event(1);
    const identity = {
      sequence: accepted.sequence,
      eventId: accepted.eventId,
      fingerprint: accepted.fingerprint,
    };
    const index = {
      cursor: 1,
      bySequence: new Map([[1, identity]]),
      byIdentity: new Map([[identity.eventId, identity]]),
    };
    expect(classifyBenchmarkEvent(event(2, "future.kind.v9"), index)).toEqual({
      disposition: "next",
    });
    expect(classifyBenchmarkEvent(event(3), index)).toEqual({
      disposition: "gap",
      missingAfter: 1,
    });
    expect(classifyBenchmarkEvent(accepted, index)).toEqual({
      disposition: "duplicate",
    });
    expect(
      classifyBenchmarkEvent(
        {
          ...accepted,
          fingerprint: `sha256:${"f".repeat(64)}`,
        },
        index,
      ).disposition,
    ).toBe("conflict");
  });
});

describe("BenchmarkEventSession", () => {
  it("backfills multiple pages to captured high-water and closes the race with SSE", async () => {
    const sources: FakeEventSource[] = [];
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([event(1)], 2))
      .mockResolvedValueOnce(page([event(2)], 3, false, 1));
    const session = new BenchmarkEventSession(experimentId, {
      fetchPage,
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
      onChange: vi.fn(),
    });
    await session.start();
    expect(fetchPage).toHaveBeenNthCalledWith(1, experimentId, 0, 100);
    expect(fetchPage).toHaveBeenNthCalledWith(2, experimentId, 1, 100);
    expect(sources[0]?.url).toContain("after=2");
    sources[0]?.emit("open");
    sources[0]?.emit("journal", JSON.stringify(event(3)));
    expect(session.current()).toMatchObject({
      connection: "live",
      cursor: 3,
      deliveryMode: "live",
      deliveryVersion: 3,
    });
  });

  it("keeps heartbeat and exact duplicate transport-only, then freezes on conflict", async () => {
    const sources: FakeEventSource[] = [];
    const progress = vi.fn();
    let now = 10;
    const session = new BenchmarkEventSession(experimentId, {
      fetchPage: vi.fn().mockResolvedValue(page([event(1)], 1)),
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
      now: () => now,
      onChange: vi.fn(),
      onProgress: progress,
    });
    await session.start();
    expect(progress).toHaveBeenCalledTimes(1);
    sources[0]?.emit("open");
    now = 20;
    sources[0]?.emit("heartbeat", '{"schemaVersion":1}');
    expect(session.current().lastFreshAt).toBe(20);
    expect(session.current().deliveryVersion).toBe(1);
    sources[0]?.emit("journal", JSON.stringify(event(1)));
    expect(progress).toHaveBeenCalledTimes(1);
    sources[0]?.emit(
      "journal",
      JSON.stringify({
        ...event(1),
        fingerprint: `sha256:${"f".repeat(64)}`,
      }),
    );
    expect(session.current()).toMatchObject({
      connection: "frozen",
      cursor: 1,
      deliveryVersion: 1,
    });
    expect(sources[0]?.closed).toBe(true);
  });

  it("repairs an SSE gap, preserves an unknown kind, and reconnects explicitly", async () => {
    const sources: FakeEventSource[] = [];
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([event(1)], 1))
      .mockResolvedValueOnce(
        page([event(2), event(3, "future.kind.v7")], 4, false, 1),
      );
    const session = new BenchmarkEventSession(experimentId, {
      fetchPage,
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
      onChange: vi.fn(),
    });
    await session.start();
    sources[0]?.emit("journal", JSON.stringify(event(4)));
    await flush();
    expect(fetchPage).toHaveBeenLastCalledWith(experimentId, 1, 100);
    expect(session.current().events.map((item) => item.kind)).toContain(
      "future.kind.v7",
    );
    expect(session.current().cursor).toBe(4);
    expect(sources[1]?.url).toContain("after=4");
  });

  it("manually reconnects after disconnect without changing verified facts", async () => {
    const sources: FakeEventSource[] = [];
    const timers: Array<() => void> = [];
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([event(1)], 1))
      .mockResolvedValueOnce(page([], 1, false, 1));
    const session = new BenchmarkEventSession(experimentId, {
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
    expect(session.current()).toMatchObject({
      connection: "reconnecting",
      cursor: 1,
      deliveryVersion: 1,
    });
    timers.shift()?.();
    await flush();
    expect(fetchPage).toHaveBeenLastCalledWith(experimentId, 1, 100);
    expect(sources[1]?.url).toContain("after=1");
  });

  it("enters terminal only after the HTTP page confirms final drain", async () => {
    const sources: FakeEventSource[] = [];
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce(page([event(1)], 1))
      .mockResolvedValueOnce(page([], 2, true, 2));
    const session = new BenchmarkEventSession(experimentId, {
      fetchPage,
      createEventSource: (url) => {
        const source = new FakeEventSource(url);
        sources.push(source);
        return source;
      },
      onChange: vi.fn(),
    });
    await session.start();
    sources[0]?.emit(
      "journal",
      JSON.stringify(event(2, "experiment.terminal")),
    );
    await flush();
    expect(session.current()).toMatchObject({
      connection: "terminal",
      cursor: 2,
      highWaterMark: 2,
    });
    expect(sources[0]?.closed).toBe(true);
  });

  it("freezes invalid cursors and discards in-flight work after stop", async () => {
    const invalid = new BenchmarkEventSession(experimentId, {
      fetchPage: vi.fn().mockResolvedValue({
        ...page([event(1)], 1),
        nextCursor: 0,
      }),
      createEventSource: vi.fn(),
      onChange: vi.fn(),
    });
    await invalid.start();
    expect(invalid.current().connection).toBe("frozen");

    let resolvePage:
      | ((value: BenchmarkExperimentEventPage) => void)
      | undefined;
    const snapshots: BenchmarkEventSessionSnapshot[] = [];
    const pending = new BenchmarkEventSession(experimentId, {
      fetchPage: () =>
        new Promise((resolve) => {
          resolvePage = resolve;
        }),
      createEventSource: vi.fn(),
      onChange: (snapshot) => snapshots.push(snapshot),
    });
    const start = pending.start();
    pending.stop();
    resolvePage?.(page([event(1)], 1));
    await start;
    expect(pending.current()).toMatchObject({
      connection: "stopped",
      cursor: 0,
    });
    expect(snapshots.at(-1)?.connection).toBe("stopped");
  });
});
