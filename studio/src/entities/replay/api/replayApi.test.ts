import { afterEach, describe, expect, it, vi } from "vitest";
import { listReplays } from "./replayApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Replay list API", () => {
  it("sends an exact encoded Agent filter without changing the page DTO", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => new Response(JSON.stringify({
      schemaVersion: 1,
      items: [],
      nextCursor: null,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const page = await listReplays(30, "cursor-1", "agent:research-1");

    expect(page.items).toEqual([]);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      "/api/studio/replays?limit=30&cursor=cursor-1&agentId=agent%3Aresearch-1",
    );
  });
});
