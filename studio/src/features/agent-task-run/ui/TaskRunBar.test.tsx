import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { StudioRunResource } from "@/entities/run";
import { ActiveRunBar, TaskRunBar } from "./TaskRunBar";

const runId = `run-${"a".repeat(32)}`;
const hash = `sha256:${"b".repeat(64)}`;

/** Build one authoritative active Run for task-control tests. */
function run(): StudioRunResource {
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

/** Render one task control under a fresh server-state provider. */
function renderControl(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("Task Run Bar", () => {
  it("blocks an invalid revision without exposing internal flow-control guidance", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/studio/device-profiles")) {
          return new Response(
            JSON.stringify({
              schemaVersion: 1,
              items: [{
                deviceProfileId: "local-android",
                label: "Local Android",
                platform: "android",
                availability: "configured",
              }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/run-readiness")) {
          return new Response(
            JSON.stringify({
              schemaVersion: 1,
              agentId: "agent-1",
              revisionId: "revision-1",
              canonicalHash: hash,
              deviceProfileId: "local-android",
              ready: false,
              diagnostics: [{
                code: "studio.readiness.topology_observation_missing",
                category: "topology",
                message: "Android Run requires a reachable DeviceObserve contract",
                subjectIdentity: "zhixing.service.device_observe@2.0",
                nodeId: null,
                remediationKey: "repair-studio-android-topology",
              }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );

    renderControl(
      <TaskRunBar
        target={{ agentId: "agent-1", revisionId: "revision-1", canonicalHash: hash }}
        onCreated={vi.fn()}
      />,
    );

    expect(await screen.findByText(/内部运行图缺少设备观察入口/)).not.toBeNull();
    expect(screen.getByText(/studio\.readiness\.topology_observation_missing/)).not.toBeNull();
    expect(screen.getByText(/点击“运行”会立即使用后端实时状态重新检查/)).not.toBeNull();
    expect(screen.queryByText(/DONE|FAIL|DeviceObserve|bounded feedback/)).toBeNull();
    const runButton = screen.getByRole("button", { name: "运行" });
    expect((runButton as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(runButton);
    expect(await screen.findByText(/请输入普通 Agent task/)).not.toBeNull();
  });

  it("rechecks stale blocked readiness on click and creates the Run when the backend is ready", async () => {
    let readinessCalls = 0;
    const onCreated = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/studio/device-profiles")) {
          return new Response(
            JSON.stringify({
              schemaVersion: 1,
              items: [{
                deviceProfileId: "local-android",
                label: "Local Android",
                platform: "android",
                availability: "configured",
              }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/run-readiness")) {
          readinessCalls += 1;
          return new Response(
            JSON.stringify({
              schemaVersion: 1,
              agentId: "agent-1",
              revisionId: "revision-1",
              canonicalHash: hash,
              deviceProfileId: "local-android",
              ready: readinessCalls > 1,
              diagnostics: readinessCalls > 1 ? [] : [{
                code: "studio.readiness.topology_feedback_missing",
                category: "topology",
                message: "internal stale diagnostic",
                subjectIdentity: null,
                nodeId: null,
                remediationKey: "repair-studio-android-topology",
              }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/api/studio/runs")) {
          return new Response(
            JSON.stringify({ ...run(), created: true, lifecycle: "accepted" }),
            { status: 201, headers: { "Content-Type": "application/json" } },
          );
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );

    renderControl(
      <TaskRunBar
        target={{ agentId: "agent-1", revisionId: "revision-1", canonicalHash: hash }}
        onCreated={onCreated}
      />,
    );

    expect(await screen.findByText(/内部运行图没有形成受限的下一轮执行路径/)).not.toBeNull();
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "Open Camera" } });
    fireEvent.click(screen.getByRole("button", { name: "运行" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(readinessCalls).toBeGreaterThanOrEqual(2);
  });

  it("clears a stale preference and requires an explicit choice among profiles", async () => {
    window.localStorage.setItem("zx-studio-run-profile-v1", "removed-profile");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/studio/device-profiles")) {
          return new Response(
            JSON.stringify({
              schemaVersion: 1,
              items: [
                {
                  deviceProfileId: "research-a",
                  label: "Research A",
                  platform: "android",
                  availability: "configured",
                },
                {
                  deviceProfileId: "research-b",
                  label: "Research B",
                  platform: "android",
                  availability: "configured",
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/run-readiness")) {
          return new Response(
            JSON.stringify({
              schemaVersion: 1,
              agentId: "agent-1",
              revisionId: "revision-1",
              canonicalHash: hash,
              deviceProfileId: "research-a",
              ready: true,
              diagnostics: [],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        throw new Error(`unexpected request: ${url}`);
      }),
    );
    renderControl(
      <TaskRunBar
        target={{ agentId: "agent-1", revisionId: "revision-1", canonicalHash: hash }}
        onCreated={vi.fn()}
      />,
    );

    const profile = await screen.findByLabelText("Device Profile");
    await waitFor(() => {
      expect((profile as HTMLSelectElement).value).toBe("");
      expect(window.localStorage.getItem("zx-studio-run-profile-v1")).toBeNull();
    });
    expect((screen.getByRole("button", { name: "运行" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(profile, { target: { value: "research-a" } });
    await waitFor(() => {
      expect(window.localStorage.getItem("zx-studio-run-profile-v1")).toBe("research-a");
    });
  });

  it("retains an uncertain draft without persisting it in localStorage", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/studio/device-profiles")) {
          return new Response(
            JSON.stringify({
              schemaVersion: 1,
              items: [{
                deviceProfileId: "local-android",
                label: "Local Android",
                platform: "android",
                availability: "configured",
              }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/run-readiness")) {
          return new Response(
            JSON.stringify({
              schemaVersion: 1,
              agentId: "agent-1",
              revisionId: "revision-1",
              canonicalHash: hash,
              deviceProfileId: "local-android",
              ready: true,
              diagnostics: [],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(
          JSON.stringify({ error: { code: "studio.http.unreachable", message: "offline" } }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    renderControl(
      <TaskRunBar
        target={{ agentId: "agent-1", revisionId: "revision-1", canonicalHash: hash }}
        onCreated={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "Open Display" } });
    await waitFor(() => {
      expect((screen.getByRole("button", { name: "运行" }) as HTMLButtonElement).disabled).toBe(false);
    });
    fireEvent.click(screen.getByRole("button", { name: "运行" }));
    await screen.findByText(/Run 创建失败/);
    expect((screen.getByLabelText("Task") as HTMLTextAreaElement).value).toBe("Open Display");
    expect(JSON.stringify(window.localStorage)).not.toContain("Open Display");
  });

  it("shows the persisted active task and only cooperative Cancel", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({ ...run(), lifecycle: "cancelling", cancellationRequested: true }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderControl(<ActiveRunBar run={run()} />);
    expect(screen.getByText("Open Settings")).not.toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByText(/Pause|Checkpoint|Retry node/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });
});
