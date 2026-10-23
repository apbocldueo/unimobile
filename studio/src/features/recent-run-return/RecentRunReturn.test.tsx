import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { studioRunKeys, type StudioRunResource } from "@/entities/run";
import { RecentRunReturn } from "./RecentRunReturn";

const run: StudioRunResource = {
  schemaVersion: 1, runId: "run-active", clientRequestId: "request-1", agentId: "agent-1",
  revisionId: "revision-1", canonicalHash: `sha256:${"a".repeat(64)}`,
  task: { text: "确认设置首页", metadata: {} }, deviceProfileId: "local-android",
  lifecycle: "running", cancellationRequested: false, resultAvailability: "not_captured",
  result: null, replayAvailability: "not_captured", eventHighWaterMark: 0,
  acceptedAt: 1, startedAt: 2, updatedAt: 2, terminalAt: null, storageWarnings: [],
};

/** Render only the return feature with optional server-owned cached Run data. */
function renderReturn(seed = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (seed) client.setQueryData(studioRunKeys.detail(run.runId), run);
  render(<QueryClientProvider client={client}><MemoryRouter><RecentRunReturn /></MemoryRouter></QueryClientProvider>);
  return client;
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("does not claim cached running status before fresh verification", async () => {
  let resolve!: (value: Response) => void;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((done) => { resolve = done; })));
  const client = renderReturn();
  expect(screen.queryByText(/正在运行/)).toBeNull();
  expect(screen.getByText(/正在确认状态/)).not.toBeNull();
  resolve(new Response(JSON.stringify(run), { headers: { "Content-Type": "application/json" } }));
  expect(await screen.findByText(/确认设置首页 · 正在运行/)).not.toBeNull();
  expect(screen.getByRole("link", { name: "查看进度 →" }).getAttribute("href")).toBe("/agents/agent-1/run?runId=run-active");
  client.clear();
});

it("keeps a recovery link but reports failed verification honestly", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 503 })));
  const client = renderReturn();
  await waitFor(() => expect(screen.getByText(/状态检查失败/)).not.toBeNull());
  expect(screen.queryByText(/正在运行/)).toBeNull();
  expect(screen.getByRole("link", { name: "查看进度 →" })).not.toBeNull();
  client.clear();
});

it("does not invent an empty global task inventory or query unknown Runs", () => {
  const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  const client = renderReturn(false);
  expect(screen.queryByRole("region")).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
  client.clear();
});
