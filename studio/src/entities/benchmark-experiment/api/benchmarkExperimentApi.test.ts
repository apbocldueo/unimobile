import { afterEach, describe, expect, it, vi } from "vitest";
import { defaultExperimentProtocol } from "@/entities/experiment-preview";
import {
  benchmarkEventFixture,
  benchmarkExperimentFixture,
  benchmarkTaskRunFixture,
} from "../testing/benchmarkExperiment.fixtures";
import {
  cancelBenchmarkExperiment,
  createBenchmarkExperiment,
  getBenchmarkExperimentEvents,
  listBenchmarkExperiments,
  listBenchmarkTaskRuns,
} from "./benchmarkExperimentApi";

const experimentId = benchmarkExperimentFixture().experimentId;

/** Build one strict compact History response item for API parsing tests. */
function historyItem() {
  const base = `/studio/benchmark-experiments/${experimentId}`;
  return {
    schemaVersion: 1,
    experimentId,
    lifecycle: "running",
    terminalReason: null,
    source: {
      catalogEntryId: "catalog.one",
      packageIdentity: "package@1",
      split: "test",
    },
    agents: [{ agentId: "agent-one", revisionId: "revision-one" }],
    plannedTaskRunCount: 1,
    outcomeAvailability: "pending",
    reportAvailability: "pending",
    replayAvailability: "available",
    trajectoryAvailability: "not_produced",
    bundleAvailability: "pending",
    acceptedAt: 10,
    updatedAt: 11,
    terminalAt: null,
    links: {
      self: base,
      taskRuns: `${base}/task-runs`,
      artifacts: `${base}/artifacts`,
      report: null,
      bundle: null,
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Benchmark Experiment API", () => {
  it("maps create content and parses its strict wrapper", async () => {
    const requests: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        requests.push({
          url: String(input),
          body: JSON.parse(String(init?.body)),
        });
        return new Response(
          JSON.stringify({
            schemaVersion: 1,
            created: true,
            experiment: benchmarkExperimentFixture(),
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    const response = await createBenchmarkExperiment({
      schemaVersion: 1,
      clientRequestId: "create-intent-1",
      previewFingerprint: `sha256:${"c".repeat(64)}`,
      definition: {
        schemaVersion: 1,
        agentRevisions: [{ agentId: "agent-1", revisionId: "revision-1" }],
        benchmark: {
          catalogEntryId: "catalog-entry-1",
          split: "test",
          taskIds: ["task-1"],
        },
        protocol: defaultExperimentProtocol(),
        deviceProfileId: "local-android",
      },
    });
    expect(response.created).toBe(true);
    expect(requests[0]?.url).toContain("/studio/benchmark-experiments");
    expect(requests[0]?.body).toMatchObject({
      clientRequestId: "create-intent-1",
      definition: { benchmark: { taskIds: ["task-1"] } },
    });
  });

  it("maps bounded TaskRun and event queries", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        urls.push(url);
        const body = url.includes("/events?")
          ? {
              schemaVersion: 1,
              experimentId,
              items: [benchmarkEventFixture(1)],
              nextCursor: 1,
              highWaterMark: 1,
              terminal: false,
            }
          : {
              schemaVersion: 1,
              experimentId,
              items: [benchmarkTaskRunFixture()],
              nextCursor: null,
            };
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    await listBenchmarkTaskRuns(experimentId, null, 25);
    await getBenchmarkExperimentEvents(experimentId, 0, 50);
    expect(urls[0]).toContain("task-runs?limit=25");
    expect(urls[1]).toContain("events?after=0&limit=50");
  });

  it("serializes exact History filters and forwards cancellation", async () => {
    let url = "";
    let signal: AbortSignal | null | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        url = String(input);
        signal = init?.signal;
        return new Response(
          JSON.stringify({
            schemaVersion: 1,
            items: [historyItem()],
            nextCursor: "next-v2",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    const controller = new AbortController();
    const page = await listBenchmarkExperiments(
      "opaque-v2",
      25,
      {
        lifecycle: "running",
        catalogEntryId: "catalog.one",
        agentId: "agent-one",
        acceptedFrom: 10,
        acceptedBefore: 20,
      },
      controller.signal,
    );
    const query = new URL(url, "http://studio.invalid").searchParams;
    expect(Object.fromEntries(query)).toEqual({
      limit: "25",
      cursor: "opaque-v2",
      lifecycle: "running",
      catalogEntryId: "catalog.one",
      agentId: "agent-one",
      acceptedFrom: "10",
      acceptedBefore: "20",
    });
    expect(signal).toBe(controller.signal);
    expect(page.nextCursor).toBe("next-v2");
  });

  it("sends an explicit idempotent cancel identity", async () => {
    let body: Record<string, unknown> | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return new Response(JSON.stringify(benchmarkExperimentFixture()), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    await cancelBenchmarkExperiment({
      experimentId,
      clientRequestId: "cancel-1",
    });
    expect(body).toEqual({
      schemaVersion: 1,
      clientRequestId: "cancel-1",
      reasonCode: "user_requested",
    });
  });
});
