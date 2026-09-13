import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { studioAgentKeys, useStudioAgent } from "./agent.queries";

afterEach(() => vi.unstubAllGlobals());

describe("Agent metadata queries", () => {
  it("parses a human-readable display name under an Agent-only cache key", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            schemaVersion: 1,
            agent: {
              agentId: "agent-1",
              name: "Research Assistant",
              currentRevisionId: "revision-current",
              createdAt: 1,
              updatedAt: 2,
            },
            currentRevision: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const rendered = renderHook(() => useStudioAgent("agent-1"), { wrapper });
    await waitFor(() => expect(rendered.result.current.isSuccess).toBe(true));
    expect(rendered.result.current.data?.agent.name).toBe("Research Assistant");
    expect(studioAgentKeys.detail("agent-1")).toEqual(["studio", "agent", "agent-1"]);
  });

  it("does not clear an authoritative Run cache entry when metadata fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ error: { code: "studio.agent.not_found", message: "missing" } }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const runFact = { runId: "run-1", agentId: "agent-1" };
    client.setQueryData(["studio", "run", "run-1"], runFact);
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const rendered = renderHook(() => useStudioAgent("agent-1"), { wrapper });
    await waitFor(() => expect(rendered.result.current.isError).toBe(true));
    expect(client.getQueryData(["studio", "run", "run-1"])).toBe(runFact);
  });
});
