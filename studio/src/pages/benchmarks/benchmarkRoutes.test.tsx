import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { defaultExperimentProtocol } from "@/entities/experiment-preview";
import { BenchmarkDetailPage } from "@/pages/benchmark-detail";
import { BenchmarksPage } from "@/pages/benchmarks";
import { ExperimentCreatePage } from "@/pages/experiment-create";
import { useExperimentComposerStore } from "@/features/experiment-composer";

const entryId = `benchmark-entry-${"a".repeat(32)}`;
const hash = `sha256:${"b".repeat(64)}`;

/** Build one safe Catalog page used across the route journey. */
function catalogResponse() {
  return {
    schemaVersion: 1,
    items: [
      {
        catalogEntryId: entryId,
        packageIdentity: "tests/fixture@1.0.0",
        title: "Fixture Benchmark",
        version: "1.0.0",
        sourceKind: "catalog",
        platforms: ["android"],
        splits: [{ name: "test", taskCount: 1 }],
        availability: "available",
        warnings: [],
      },
    ],
    nextCursor: null,
  };
}

/** Build one safe Package detail response. */
function detailResponse() {
  return {
    schemaVersion: 1,
    catalogEntryId: entryId,
    packageIdentity: "tests/fixture@1.0.0",
    packageContentIdentity: hash,
    title: "Fixture Benchmark",
    version: "1.0.0",
    sourceKind: "catalog",
    availability: "available",
    platforms: ["android"],
    splits: [{ name: "test", taskCount: 1 }],
    requirements: [],
    resources: [],
    defaultProtocol: defaultExperimentProtocol(),
    diagnostics: [],
  };
}

/** Build one safe task page response. */
function taskResponse() {
  return {
    schemaVersion: 1,
    catalogEntryId: entryId,
    split: "test",
    items: [
      {
        taskId: "fixture-task",
        split: "test",
        instruction: "Open the fixture application",
        app: "fixture",
        taskType: "static",
        requiresLogin: false,
        maxSteps: 5,
        initializerCount: 1,
        evaluatorKind: "system_state",
      },
    ],
    nextCursor: null,
  };
}

/** Build the deterministic preview response for one exact definition. */
function previewResponse() {
  return {
    schemaVersion: 1,
    previewOnly: true,
    previewFingerprint: hash,
    identities: {
      package: "tests/fixture@1.0.0",
      packageContent: hash,
      benchmarkPlan: hash,
      experimentProtocol: hash,
    },
    agentRevisions: [
      { agentId: "agent-1", revisionId: "revision-1", agentGraph: hash },
    ],
    normalizedProtocol: defaultExperimentProtocol(),
    deviceProfileId: "local-android",
    executionLimits: {
      maxAgents: 1,
      maxSelectedTasks: 1,
      maxRepeats: 1,
      multiAgentComparison: false,
    },
    schedule: [
      {
        plannedEntryId: "planned-entry-1",
        agentId: "agent-1",
        revisionId: "revision-1",
        taskId: "fixture-task",
        repeat: 0,
        order: 0,
        derivedSeed: 42,
        taskInstance: {
          availability: "template_only",
          identity: null,
          parameters: null,
        },
      },
    ],
    diagnostics: [],
  };
}

/** Build one accepted durable Experiment create response. */
function createResponse() {
  const experimentId = `experiment-${"c".repeat(32)}`;
  return {
    schemaVersion: 1,
    created: true,
    experiment: {
      schemaVersion: 1,
      experimentId,
      clientRequestId: "fixture-create",
      definition: {
        schemaVersion: 1,
        previewFingerprint: hash,
        snapshotFingerprint: hash,
        source: {
          sourceId: "workspace-benchmarks",
          sourceKind: "catalog",
          relativeKey: "fixture",
          catalogEntryId: entryId,
          packageIdentity: "tests/fixture@1.0.0",
          packageContentIdentity: hash,
          benchmarkPlanIdentity: hash,
          experimentProtocolIdentity: hash,
        },
        agentSnapshots: [
          {
            schemaVersion: 1,
            agentId: "agent-1",
            revisionId: "revision-1",
            contractVersion: "1.1",
            compileContractVersion: "studio-compile-v1",
            canonicalHash: hash,
            agentGraph: { schemaVersion: "1.1", nodes: [], edges: [] },
            presentation: {},
            sourceMap: [],
            providerIdentities: [],
          },
        ],
        benchmarkPlan: {},
        protocol: defaultExperimentProtocol(),
        split: "test",
        taskIds: ["fixture-task"],
        schedule: previewResponse().schedule,
        deviceProfileId: "local-android",
        executionLimits: previewResponse().executionLimits,
      },
      lifecycle: "accepted",
      terminalReason: null,
      cancellation: null,
      outcomeAvailability: "pending",
      reportAvailability: "pending",
      replayAvailability: "pending",
      trajectoryAvailability: "pending",
      bundleAvailability: "pending",
      publicationDiagnostics: [],
      eventHighWaterMark: 1,
      acceptedAt: 1,
      updatedAt: 1,
      terminalAt: null,
      capabilities: {
        executes: true,
        cancelAccepted: true,
        cancelActive: true,
        eventStream: true,
        replay: true,
        reports: true,
      },
      links: {
        self: `/studio/benchmark-experiments/${experimentId}`,
        cancel: `/studio/benchmark-experiments/${experimentId}/cancel`,
        taskRuns: `/studio/benchmark-experiments/${experimentId}/task-runs`,
        events: `/studio/benchmark-experiments/${experimentId}/events`,
        eventStream: `/studio/benchmark-experiments/${experimentId}/events/stream`,
        report: null,
        bundle: null,
      },
    },
  };
}

/** Return a JSON response with the shared content type. */
function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Install one fake backend covering Catalog through preview. */
function installFakeBackend(
  createFailures = 0,
  createConflict = false,
  emptyProfiles = false,
) {
  const requests: Array<{ url: string; method: string; body: unknown }> = [];
  let remainingCreateFailures = createFailures;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      requests.push({ url, method, body });
      if (
        url.endsWith("/studio/benchmark-experiments")
        && method === "POST"
      ) {
        if (remainingCreateFailures > 0) {
          remainingCreateFailures -= 1;
          return jsonResponse(
            {
              schemaVersion: 1,
              error: {
                code: "studio.http.unreachable",
                message: "result unknown",
              },
            },
            503,
          );
        }
        if (createConflict) {
          return jsonResponse(
            {
              schemaVersion: 1,
              error: {
                code: "studio.benchmark_experiment.preview_conflict",
                message: "preview fingerprint conflict",
              },
            },
            409,
          );
        }
        return jsonResponse(createResponse(), 202);
      }
      if (url.endsWith("/studio/benchmark-experiments/preview")) {
        return jsonResponse(previewResponse());
      }
      if (url.endsWith(`/studio/benchmarks/${entryId}/validate`)) {
        return jsonResponse({
          schemaVersion: 1,
          catalogEntryId: entryId,
          valid: true,
          identities: {
            package: "tests/fixture@1.0.0",
            packageContent: hash,
            benchmarkPlan: hash,
            experimentProtocol: hash,
          },
          diagnostics: [],
        });
      }
      if (url.includes("/studio/agents?")) {
        return jsonResponse({
          schemaVersion: 1,
          items: [
            {
              agentId: "agent-1",
              name: "Fixture Agent",
              currentRevisionId: "revision-1",
              createdAt: 1,
              updatedAt: 1,
            },
          ],
          nextCursor: null,
        });
      }
      if (url.endsWith("/studio/device-profiles")) {
        return jsonResponse({
          schemaVersion: 1,
          items: emptyProfiles
            ? []
            : [
                {
                  deviceProfileId: "local-android",
                  label: "Local Android",
                  platform: "android",
                  availability: "configured",
                },
              ],
        });
      }
      if (url.includes(`/studio/benchmarks/${entryId}/tasks?`)) {
        return jsonResponse(taskResponse());
      }
      if (url.endsWith(`/studio/benchmarks/${entryId}`)) {
        return jsonResponse(detailResponse());
      }
      if (url.includes("/studio/benchmarks?")) {
        return jsonResponse(catalogResponse());
      }
      return jsonResponse(
        {
          schemaVersion: 1,
          error: { code: "test.not_found", message: `No fixture for ${url}` },
        },
        404,
      );
    }),
  );
  return requests;
}

/** Render the three Benchmark routes with one authoritative Query cache. */
function renderBenchmarkRoutes() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/benchmarks"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/benchmarks" element={<BenchmarksPage />} />
          <Route path="/benchmarks/:benchmarkId" element={<BenchmarkDetailPage />} />
          <Route path="/experiments/new" element={<ExperimentCreatePage />} />
          <Route
            path="/experiments/:experimentId"
            element={<output>Monitor route</output>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.documentElement.dataset.zxTheme = "dark";
  useExperimentComposerStore.getState().reset();
});

describe("Benchmark Catalog and Composer routes", () => {
  it("keeps Catalog readable and execution selection disabled without profiles", async () => {
    installFakeBackend(0, false, true);
    renderBenchmarkRoutes();
    fireEvent.click(
      await screen.findByRole("link", { name: /Fixture Benchmark/ }),
    );
    expect(await screen.findByText("Open the fixture application")).not.toBeNull();
    fireEvent.click(screen.getByRole("link", { name: "使用此任务" }));
    expect(await screen.findByText("Experiment Composer")).not.toBeNull();
    await screen.findByRole("option", { name: /Fixture Agent/ });
    expect(screen.queryByRole("option", { name: /Local Android/ })).toBeNull();
    expect(screen.getByRole("option", { name: "请选择安全 profile" })).not.toBeNull();
    expect(
      screen.getByRole("button", { name: "2. 生成确定性预览" }),
    ).toHaveProperty("disabled", true);
  });

  it("completes Catalog → task → revision → validate → preview and stales it", async () => {
    const requests = installFakeBackend();
    document.documentElement.dataset.zxTheme = "light";
    renderBenchmarkRoutes();
    const packageLink = await screen.findByRole("link", {
      name: /Fixture Benchmark/,
    });
    fireEvent.click(packageLink);
    expect(await screen.findByText("Open the fixture application")).not.toBeNull();
    document.documentElement.dataset.zxTheme = "dark";
    fireEvent.click(screen.getByRole("link", { name: "使用此任务" }));
    expect(await screen.findByText("Experiment Composer")).not.toBeNull();
    await screen.findByRole("option", { name: /Fixture Agent/ });
    await screen.findByRole("option", { name: /Local Android/ });
    fireEvent.change(await screen.findByLabelText("Agent revision"), {
      target: { value: "agent-1" },
    });
    fireEvent.change(await screen.findByLabelText("Device profile"), {
      target: { value: "local-android" },
    });
    fireEvent.click(screen.getByRole("button", { name: "1. 验证定义" }));
    expect(await screen.findByText("当前定义已验证")).not.toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "2. 生成确定性预览" }),
    );
    expect(await screen.findByText("定义可以进入下一阶段复核")).not.toBeNull();
    expect(screen.getByText(/seed 42/)).not.toBeNull();
    fireEvent.change(screen.getByLabelText("Seed"), {
      target: { value: "43" },
    });
    expect(await screen.findByText("Preview 已过期")).not.toBeNull();
    expect(
      requests.filter((item) =>
        item.url.endsWith("/studio/benchmark-experiments/preview"),
      ),
    ).toHaveLength(1);
    expect(
      requests.some((item) => item.url.includes("/studio/runs")),
    ).toBe(false);
    expect(
      requests.some((item) =>
        item.url.includes("/tasks?split=test&limit=100"),
      ),
    ).toBe(true);
  });

  it("renders loading and empty Catalog states without inventing entries", async () => {
    let resolveResponse: ((value: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolveResponse = resolve;
          }),
      ),
    );
    renderBenchmarkRoutes();
    expect(screen.getByText("正在读取 Catalog…")).not.toBeNull();
    resolveResponse?.(
      jsonResponse({ schemaVersion: 1, items: [], nextCursor: null }),
    );
    expect(await screen.findByText("没有匹配的 Benchmark")).not.toBeNull();
    await waitFor(() =>
      expect(screen.queryByText("正在读取 Catalog…")).toBeNull(),
    );
  });

  it("reuses an unknown-result create identity and replaces it after a stale preview", async () => {
    const requests = installFakeBackend(2);
    renderBenchmarkRoutes();
    fireEvent.click(
      await screen.findByRole("link", { name: /Fixture Benchmark/ }),
    );
    fireEvent.click(await screen.findByRole("link", { name: "使用此任务" }));
    await screen.findByRole("option", { name: /Fixture Agent/ });
    await screen.findByRole("option", { name: /Local Android/ });
    fireEvent.change(await screen.findByLabelText("Agent revision"), {
      target: { value: "agent-1" },
    });
    fireEvent.change(await screen.findByLabelText("Device profile"), {
      target: { value: "local-android" },
    });
    fireEvent.click(screen.getByRole("button", { name: "1. 验证定义" }));
    await screen.findByText("当前定义已验证");
    fireEvent.click(
      screen.getByRole("button", { name: "2. 生成确定性预览" }),
    );
    await screen.findByText("定义可以进入下一阶段复核");

    let createButton = screen.getByRole("button", {
      name: "3. 创建并打开 Experiment",
    });
    fireEvent.click(createButton);
    await screen.findByText("result unknown");
    fireEvent.click(createButton);
    await waitFor(() => {
      expect(
        requests.filter(
          (item) =>
            item.url.endsWith("/studio/benchmark-experiments")
            && item.method === "POST",
        ),
      ).toHaveLength(2);
    });
    const firstTwo = requests.filter(
      (item) =>
        item.url.endsWith("/studio/benchmark-experiments")
        && item.method === "POST",
    );
    expect(
      (firstTwo[0]?.body as { clientRequestId: string }).clientRequestId,
    ).toBe((firstTwo[1]?.body as { clientRequestId: string }).clientRequestId);

    fireEvent.change(screen.getByLabelText("Seed"), {
      target: { value: "43" },
    });
    await screen.findByText("Preview 已过期");
    expect(
      screen.queryByRole("button", { name: "3. 创建并打开 Experiment" }),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "1. 验证定义" }));
    await screen.findByText("当前定义已验证");
    fireEvent.click(
      screen.getByRole("button", { name: "2. 生成确定性预览" }),
    );
    createButton = await screen.findByRole("button", {
      name: "3. 创建并打开 Experiment",
    });
    await waitFor(() => expect(createButton).toHaveProperty("disabled", false));
    fireEvent.click(createButton);
    expect(await screen.findByText("Monitor route")).not.toBeNull();

    const createRequests = requests.filter(
      (item) =>
        item.url.endsWith("/studio/benchmark-experiments")
        && item.method === "POST",
    );
    expect(createRequests).toHaveLength(3);
    expect(
      (createRequests[2]?.body as { clientRequestId: string }).clientRequestId,
    ).not.toBe(
      (createRequests[1]?.body as { clientRequestId: string }).clientRequestId,
    );
  });

  it("keeps Composer inputs and invalidates create eligibility on conflict", async () => {
    installFakeBackend(0, true);
    renderBenchmarkRoutes();
    fireEvent.click(
      await screen.findByRole("link", { name: /Fixture Benchmark/ }),
    );
    fireEvent.click(await screen.findByRole("link", { name: "使用此任务" }));
    await screen.findByRole("option", { name: /Fixture Agent/ });
    await screen.findByRole("option", { name: /Local Android/ });
    fireEvent.change(screen.getByLabelText("Agent revision"), {
      target: { value: "agent-1" },
    });
    fireEvent.change(screen.getByLabelText("Device profile"), {
      target: { value: "local-android" },
    });
    fireEvent.click(screen.getByRole("button", { name: "1. 验证定义" }));
    await screen.findByText("当前定义已验证");
    fireEvent.click(
      screen.getByRole("button", { name: "2. 生成确定性预览" }),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "3. 创建并打开 Experiment",
      }),
    );
    expect(await screen.findByText("Preview 已过期")).not.toBeNull();
    expect(screen.getByLabelText("Seed")).toHaveProperty("value", "42");
    expect(screen.getByText("Experiment Composer")).not.toBeNull();
  });
});
