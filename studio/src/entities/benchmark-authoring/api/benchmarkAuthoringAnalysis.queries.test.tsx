import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkDryRunResultFixture,
  benchmarkValidationResultFixture,
  useDryRunBenchmarkDraft,
  useValidateBenchmarkDraft,
} from "@/entities/benchmark-authoring";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Build a Query provider whose cache can be inspected after a mutation. */
function wrapper(client: QueryClient) {
  return function QueryWrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("Benchmark analysis mutations", () => {
  it("returns transient validation without creating a durable query", async () => {
    const resultFixture = benchmarkValidationResultFixture();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(resultFixture), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const client = new QueryClient();
    const { result } = renderHook(() => useValidateBenchmarkDraft(), {
      wrapper: wrapper(client),
    });

    let response: unknown;
    await act(async () => {
      response = await result.current.mutateAsync({
        draftId: resultFixture.draftId,
        request: {
          schemaVersion: 1,
          revisionId: resultFixture.revisionId,
          split: resultFixture.split,
        },
      });
    });

    expect(response).toEqual(resultFixture);
    expect(client.getQueryCache().getAll()).toHaveLength(0);
  });

  it("forwards dry-run cancellation without caching planning facts", async () => {
    const resultFixture = benchmarkDryRunResultFixture();
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      expect(init?.signal).toBeInstanceOf(AbortSignal);
      return Promise.resolve(
        new Response(JSON.stringify(resultFixture), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient();
    const { result } = renderHook(() => useDryRunBenchmarkDraft(), {
      wrapper: wrapper(client),
    });
    const controller = new AbortController();

    await act(async () => {
      await result.current.mutateAsync({
        draftId: resultFixture.draftId,
        request: {
          schemaVersion: 1,
          revisionId: resultFixture.revisionId,
          split: resultFixture.split,
          taskIds: [],
          agentRevisions: resultFixture.agentRevisions.map((item) => ({
            agentId: item.agentId,
            revisionId: item.revisionId,
          })),
        },
        signal: controller.signal,
      });
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(client.getQueryCache().getAll()).toHaveLength(0);
  });
});
