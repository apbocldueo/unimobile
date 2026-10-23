import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cancelStudioRun,
  createStudioRun,
  getStudioRunEvents,
} from "@/entities/run";
import { StudioApiError } from "@/shared/api";

const runId = `run-${"a".repeat(32)}`;
const hash = `sha256:${"b".repeat(64)}`;

/** Build one backend-shaped running Run response. */
function runningResource() {
  return {
    schemaVersion: 1,
    runId,
    clientRequestId: "request-1",
    agentId: "agent-1",
    revisionId: "revision-1",
    canonicalHash: hash,
    task: { text: "Open Settings", metadata: {} },
    deviceProfileId: "local-android",
    lifecycle: "running",
    cancellationRequested: false,
    resultAvailability: "not_captured",
    result: null,
    replayAvailability: "not_captured",
    eventHighWaterMark: 0,
    acceptedAt: 1,
    startedAt: 2,
    updatedAt: 2,
    terminalAt: null,
    storageWarnings: [],
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("live Run APIs", () => {
  it("posts the idempotent create contract and parses the response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...runningResource(), created: true }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const response = await createStudioRun({
      schemaVersion: 1,
      clientRequestId: "request-1",
      agentId: "agent-1",
      revisionId: "revision-1",
      task: { text: "Open Settings", metadata: {} },
      deviceProfileId: "local-android",
      runtimeKind: "android",
    });
    expect(response.created).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "/zhixing-studio/api/studio/runs",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("preserves create conflict and cancellation response semantics", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            schemaVersion: 1,
            error: {
              code: "studio.run.client_request_conflict",
              message: "request identity already has different content",
            },
          }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ...runningResource(),
            lifecycle: "cancelling",
            cancellationRequested: true,
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      createStudioRun({
        schemaVersion: 1,
        clientRequestId: "request-1",
        agentId: "agent-1",
        revisionId: "revision-1",
        task: { text: "Different", metadata: {} },
        deviceProfileId: "local-android",
        runtimeKind: "android",
      }),
    ).rejects.toMatchObject({
      status: 409,
      code: "studio.run.client_request_conflict",
    } satisfies Partial<StudioApiError>);
    expect((await cancelStudioRun(runId)).lifecycle).toBe("cancelling");
  });

  it("rejects invalid cursors before issuing a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(getStudioRunEvents(runId, -1)).rejects.toThrow(/after/);
    await expect(getStudioRunEvents(runId, 0, 501)).rejects.toThrow(/limit/);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
