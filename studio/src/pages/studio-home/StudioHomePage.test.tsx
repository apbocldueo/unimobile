import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { StudioHomePage } from "./StudioHomePage";

/** Return a strict JSON response for Home projection fixtures. */
function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

/** Render Home with independent resource-query ownership. */
function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <StudioHomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => window.localStorage.clear());

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Studio Home", () => {
  it("shows a truthful no-device first-use path without fabricating work", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/studio/agents?")) return jsonResponse({ schemaVersion: 1, items: [], nextCursor: null });
      if (url.includes("/api/studio/replays?")) return jsonResponse({ schemaVersion: 1, items: [], nextCursor: null });
      if (url.includes("/studio/benchmark-experiments?")) return jsonResponse({ schemaVersion: 1, items: [], nextCursor: null });
      if (url.includes("/studio/runtime-readiness")) return jsonResponse({
        schemaVersion: 1,
        ready: false,
        providers: [],
        secrets: [],
        deviceProfiles: [],
        diagnostics: [{ code: "studio.runtime.profile_missing", category: "profile", message: "请配置安全 Device Profile", subjectIdentity: null, nodeId: null, remediationKey: "configure_device_profile" }],
      });
      throw new Error(`unexpected request: ${url}`);
    }));

    renderHome();

    expect(await screen.findByText("请配置安全 Device Profile")).not.toBeNull();
    expect(screen.getByRole("link", { name: "创建 Agent" })).not.toBeNull();
    expect(screen.getByText("还没有 Agent。")).not.toBeNull();
    expect(screen.getByText("还没有可回放的普通 Run。")).not.toBeNull();
    expect(screen.getByText("还没有 Benchmark Experiment。")).not.toBeNull();
    expect(screen.getByText(/不会创建假 Run/)).not.toBeNull();
  });

  it("isolates a failed recent query and persists only guide dismissal", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/studio/agents?")) return jsonResponse({ schemaVersion: 1, error: { code: "studio.agent.unavailable", message: "Agent directory unavailable" } }, 503);
      if (url.includes("/api/studio/replays?")) return jsonResponse({ schemaVersion: 1, items: [], nextCursor: null });
      if (url.includes("/studio/benchmark-experiments?")) return jsonResponse({ schemaVersion: 1, items: [], nextCursor: null });
      if (url.includes("/studio/runtime-readiness")) return jsonResponse({ schemaVersion: 1, ready: true, providers: [], secrets: [], deviceProfiles: [], diagnostics: [] });
      throw new Error(`unexpected request: ${url}`);
    }));

    renderHome();

    expect(await screen.findByText(/Agent directory unavailable/)).not.toBeNull();
    expect(screen.getAllByText("已就绪").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "暂时隐藏" }));
    expect(window.localStorage.getItem("zx-studio-onboarding-dismissed-v1")).toBe("1");
    expect(screen.getByRole("button", { name: "重新打开首次使用引导" })).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重新打开首次使用引导" }));
    expect(screen.getByRole("heading", { name: "完成一次 Mobile Agent 研究闭环" })).not.toBeNull();
  });

  it("continues from bounded durable metadata without exposing deleted identities", async () => {
    const experimentId = `experiment-${"9".repeat(32)}`;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/studio/agents?")) return jsonResponse({ schemaVersion: 1, items: [{ agentId: "agent-returning", name: "Returning Research Agent", currentRevisionId: "revision-1", createdAt: 1, updatedAt: 20 }], nextCursor: null });
      if (url.includes("/api/studio/replays?")) return jsonResponse({ schemaVersion: 1, items: [{ runId: "run-returning", agentId: "agent-returning", agentStatus: "success", benchmarkOutcome: null, provenance: "native_studio_run", evidenceOrigin: { schemaVersion: 1, acquisition: "replay_projection", environment: "fake_device", deviceProfileId: null, deviceChecks: [], realDeviceEvidence: false }, integrityState: "complete", evidenceCompleteness: 100, importedAt: 19 }], nextCursor: null });
      if (url.includes("/studio/benchmark-experiments?")) return jsonResponse({ schemaVersion: 1, items: [{ schemaVersion: 1, experimentId, lifecycle: "terminal", terminalReason: "completed", source: { catalogEntryId: "deleted-catalog-id", packageIdentity: "deleted/package@1", split: "test" }, agents: [{ agentId: "deleted-agent-id", revisionId: "deleted-revision-id" }], plannedTaskRunCount: 1, outcomeAvailability: "available", reportAvailability: "available", replayAvailability: "available", trajectoryAvailability: "available", bundleAvailability: "available", acceptedAt: 10, updatedAt: 18, terminalAt: 18, links: { self: `/studio/benchmark-experiments/${experimentId}`, taskRuns: `/studio/benchmark-experiments/${experimentId}/task-runs`, artifacts: `/studio/benchmark-experiments/${experimentId}/artifacts`, report: `/studio/benchmark-experiments/${experimentId}/report`, bundle: `/studio/benchmark-experiments/${experimentId}/bundle` } }], nextCursor: null });
      if (url.includes("/studio/runtime-readiness")) return jsonResponse({ schemaVersion: 1, ready: true, providers: [], secrets: [], deviceProfiles: [], diagnostics: [] });
      throw new Error(`unexpected request: ${url}`);
    }));

    const view = renderHome();

    expect(await screen.findByText("Returning Research Agent")).not.toBeNull();
    expect(screen.getByText("deleted/package@1")).not.toBeNull();
    expect(view.container.textContent).not.toContain("deleted-agent-id");
    expect(view.container.querySelector('a[href="/runs/run-returning/replay"]')).not.toBeNull();
    expect(view.container.querySelector(`a[href="/experiments/${experimentId}"]`)).not.toBeNull();
  });
});
