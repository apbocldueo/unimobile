import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import {
  benchmarkDefinitionFixture,
  benchmarkExperimentFixture,
  benchmarkTaskRunFixture,
} from "@/entities/benchmark-experiment";
import {
  benchmarkReportInventoryFixture,
  benchmarkRunReportFixture,
  multiAgentExperimentReportFixture,
  reportCoreTaskRunId,
  reportExperimentId,
  reportTaskRunId,
  type BenchmarkArtifactInventoryItem,
} from "@/entities/benchmark-report";
import { ExperimentReportPage } from "./ExperimentReportPage";

const secondCoreTaskRunId = "e".repeat(32);
const secondTaskRunId = `task-run-${"e".repeat(32)}`;
const secondArtifactId = `artifact-${"e".repeat(32)}`;
const evidenceArtifactId = `artifact-${"1".repeat(32)}`;
const evidenceReference = "runs/evaluator-evidence.json";
const evidenceSource = '{"safe":"<script>fixture</script>","matched":true}';
const evidenceBytes = new TextEncoder().encode(evidenceSource);
const exportReportArtifactId = `artifact-${"1".padStart(32, "0")}`;
const exportBundleArtifactId = `artifact-${"2".padStart(32, "0")}`;
const exportManifestArtifactId = `artifact-${"3".padStart(32, "0")}`;
const exportTrajectoryArtifactId = `artifact-${"4".padStart(32, "0")}`;
const exportManifestBytes = new TextEncoder().encode(JSON.stringify({
  schemaVersion: 1,
  kind: "studio_benchmark_publication_manifest",
  experimentId: reportExperimentId,
  taskRunId: reportTaskRunId,
  members: [
    {
      reference: `runs/${reportCoreTaskRunId}/run-report.json`,
      kind: "task_report",
      contentType: "application/json",
      size: 128,
      sha256: `sha256:${"a".repeat(64)}`,
      scope: {
        experimentId: reportExperimentId,
        taskRunId: reportTaskRunId,
      },
      availability: "available",
      exclusionReason: "",
    },
  ],
  excludedEvidence: [
    {
      kind: "prompt",
      availability: "hidden",
      reason: "hidden_by_default_policy",
    },
  ],
}));

/** Build one terminal multi-Agent resource matching the report identities. */
function experimentFixture() {
  const fixture = benchmarkExperimentFixture();
  const definition = benchmarkDefinitionFixture();
  const hash = benchmarkRunReportFixture().identities.benchmark_plan;
  definition.source.benchmarkPlanIdentity = hash;
  definition.source.experimentProtocolIdentity = hash;
  definition.agentSnapshots[0]!.canonicalHash = hash;
  definition.agentSnapshots.push({
    ...structuredClone(definition.agentSnapshots[0]!),
    agentId: "agent-2",
    revisionId: "revision-2",
  });
  return {
    ...fixture,
    definition,
    lifecycle: "terminal",
    terminalReason: "completed",
    terminalAt: 9,
    reportAvailability: "available",
    capabilities: { ...fixture.capabilities, cancelActive: false },
    links: {
      ...fixture.links,
      cancel: null,
      artifacts:
        `/studio/benchmark-experiments/${reportExperimentId}/artifacts`,
      report:
        `/studio/benchmark-experiments/${reportExperimentId}/report`,
    },
  };
}

/** Build two stable Studio TaskRuns bridged to independent Core identities. */
function taskRunsFixture() {
  const hash = benchmarkRunReportFixture().identities.task_instance;
  const firstReplay = `benchmark-replay-${"d".repeat(32)}`;
  const secondReplay = `benchmark-replay-${"e".repeat(32)}`;
  const first = {
    ...benchmarkTaskRunFixture(0),
    lifecycle: "terminal",
    terminalReason: "completed",
    terminalAt: 9,
    coreTaskRunId: reportCoreTaskRunId,
    taskInstanceIdentity: hash,
    agentStatus: "success",
    benchmarkOutcome: "pass",
    outcomeAvailability: "available",
    resultAvailability: "available",
    result: {
      evidenceOrigin: {
        schemaVersion: 1,
        acquisition: "fresh_execution",
        environment: "real_android",
        deviceProfileId: "pixel-safe",
        deviceChecks: [],
        realDeviceEvidence: true,
      },
    },
    reportAvailability: "available",
    replayAvailability: "available",
    replayId: firstReplay,
    links: {
      ...benchmarkTaskRunFixture(0).links,
      artifacts:
        `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
        + `${reportTaskRunId}/artifacts`,
      replay: `/studio/replays/${firstReplay}`,
    },
  };
  const second = {
    ...benchmarkTaskRunFixture(1),
    taskRunId: secondTaskRunId,
    agentId: "agent-2",
    revisionId: "revision-2",
    lifecycle: "terminal",
    terminalReason: "completed",
    terminalAt: 9,
    coreTaskRunId: secondCoreTaskRunId,
    taskInstanceIdentity: hash,
    agentStatus: "failed",
    benchmarkOutcome: "fail",
    outcomeAvailability: "available",
    resultAvailability: "available",
    result: {
      evidenceOrigin: {
        schemaVersion: 1,
        acquisition: "contract_fixture",
        environment: "fake_device",
        deviceProfileId: "acceptance-fake",
        deviceChecks: [],
        realDeviceEvidence: false,
      },
    },
    reportAvailability: "available",
    replayAvailability: "available",
    replayId: secondReplay,
    links: {
      ...benchmarkTaskRunFixture(1).links,
      artifacts:
        `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
        + `${secondTaskRunId}/artifacts`,
      replay: `/studio/replays/${secondReplay}`,
    },
  };
  return [first, second];
}

/** Build an ordered inventory for both published TaskRun reports. */
function inventoryFixture() {
  const fixture = benchmarkReportInventoryFixture();
  const exportTemplate =
    fixture.items[0]! as BenchmarkArtifactInventoryItem;
  const evidence = structuredClone(fixture.items[0]!);
  evidence.descriptor.artifactId = evidenceArtifactId;
  evidence.descriptor.kind = "evaluator_evidence";
  evidence.descriptor.causalIdentity = evidenceReference;
  evidence.descriptor.contentType = "application/json";
  evidence.descriptor.size = evidenceBytes.byteLength;
  evidence.descriptor.availability = "redacted";
  evidence.links.content =
    `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
    + `${reportTaskRunId}/artifacts/${evidenceArtifactId}`;
  const second = structuredClone(fixture.items[0]!);
  second.descriptor.artifactId = secondArtifactId;
  second.descriptor.taskRunId = secondTaskRunId;
  second.descriptor.causalIdentity =
    `runs/${secondCoreTaskRunId}/run-report.json`;
  second.links.content =
    `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
    + `${secondTaskRunId}/artifacts/${secondArtifactId}`;
  const exportReport = exportItem(
    exportTemplate,
    exportReportArtifactId,
    "experiment_report",
    null,
    "application/json",
    256,
  );
  const bundle = exportItem(
    exportTemplate,
    exportBundleArtifactId,
    "experiment_bundle",
    null,
    "application/zip",
    128 * 1024 * 1024,
  );
  const manifest = exportItem(
    exportTemplate,
    exportManifestArtifactId,
    "studio_publication_manifest",
    null,
    "application/json",
    exportManifestBytes.byteLength,
  );
  const trajectory = exportItem(
    exportTemplate,
    exportTrajectoryArtifactId,
    "task_trajectory",
    reportTaskRunId,
    "application/x-ndjson",
    512,
  );
  const items = [
    exportReport,
    bundle,
    manifest,
    trajectory,
    evidence,
    ...fixture.items,
    second,
  ].sort((left, right) =>
    left.descriptor.artifactId.localeCompare(right.descriptor.artifactId)
  );
  return { ...fixture, hiddenCount: 1, items };
}

/** Clone one fixture descriptor into an exact Export material capability. */
function exportItem(
  source: BenchmarkArtifactInventoryItem,
  artifactId: string,
  kind: string,
  taskRunId: string | null,
  contentType: string,
  size: number,
): BenchmarkArtifactInventoryItem {
  const item: BenchmarkArtifactInventoryItem = structuredClone(source);
  item.descriptor.artifactId = artifactId;
  item.descriptor.taskRunId = taskRunId;
  item.descriptor.kind = kind;
  item.descriptor.causalIdentity = `${kind}.fixture`;
  item.descriptor.contentType = contentType;
  item.descriptor.size = size;
  item.descriptor.sha256 = `sha256:${"a".repeat(64)}`;
  item.descriptor.availability = "available";
  item.links.content = taskRunId === null
    ? `/studio/benchmark-experiments/${reportExperimentId}/artifacts/${artifactId}`
    : `/studio/benchmark-experiments/${reportExperimentId}/task-runs/`
      + `${taskRunId}/artifacts/${artifactId}`;
  return item;
}

/** Build the selected Core TaskRun report for one content capability. */
function runReportFixture(second: boolean) {
  const fixture = benchmarkRunReportFixture();
  if (!second) {
    fixture.evaluation.children[0]!.evaluator_result.evidence[0]!.artifact_ref =
      evidenceReference;
    return fixture;
  }
  return {
    ...fixture,
    task_run_id: secondCoreTaskRunId,
    task_id: "task-2",
    agent_id: "agent-2",
    outcome: "fail",
    artifact_namespace: secondCoreTaskRunId,
    evaluation: {
      ...fixture.evaluation,
      is_pass: false,
      status: "failure",
      reason: "fixture mismatch",
    },
  };
}

/** Build a two-run Experiment report aligned to the fixture plan order. */
function experimentReportFixture() {
  const fixture = multiAgentExperimentReportFixture();
  fixture.run_summaries[1]!.task_id = "task-2";
  return fixture;
}

/** Return one strict JSON response for the Report route backend. */
function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Install the deterministic two-run publication backend. */
function installBackend(options: { runCorrupt?: boolean } = {}) {
  const requests: string[] = [];
  const methods: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      requests.push(url);
      methods.push(`${method} ${url}`);
      if (method === "HEAD") {
        const target = inventoryFixture().items.find(
          (item) => item.links.content && url.endsWith(item.descriptor.artifactId),
        );
        if (!target) return response({ error: {} }, 404);
        return new Response(null, {
          status: 200,
          headers: {
            "Content-Type": target.descriptor.contentType,
            "Content-Length": String(target.descriptor.size),
            "Content-Disposition":
              `attachment; filename="${target.descriptor.artifactId}"`,
          },
        });
      }
      if (url.endsWith(`/artifacts/${exportManifestArtifactId}`)) {
        return new Response(exportManifestBytes, {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Content-Length": String(exportManifestBytes.byteLength),
          },
        });
      }
      if (url.endsWith(`/artifacts/${evidenceArtifactId}`)) {
        return new Response(evidenceBytes, {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Content-Length": String(evidenceBytes.byteLength),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
          },
        });
      }
      if (url.includes("/task-runs/") && url.includes("/artifacts/")) {
        if (options.runCorrupt) {
          return response(
            {
              error: {
                code: "benchmark.artifact.corrupt",
                message: "raw fixture detail is not rendered",
              },
            },
            409,
          );
        }
        return response(runReportFixture(url.includes(secondTaskRunId)));
      }
      if (url.includes("/task-runs")) {
        return response({
          schemaVersion: 1,
          experimentId: reportExperimentId,
          items: taskRunsFixture(),
          nextCursor: null,
        });
      }
      if (url.includes("/artifacts?")) return response(inventoryFixture());
      if (url.endsWith("/report")) {
        return response(experimentReportFixture());
      }
      return response(experimentFixture());
    }),
  );
  return { requests, methods };
}

/** Expose current location for URL selection and handoff assertions. */
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}{location.search}</output>;
}

/** Render Report with durable Monitor and Replay handoff targets. */
function renderReport(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path="/experiments/:experimentId/report"
            element={<ExperimentReportPage />}
          />
          <Route
            path="/experiments/:experimentId"
            element={<p>Durable Monitor route</p>}
          />
          <Route
            path="/runs/:runId/replay"
            element={<p>Durable Replay route</p>}
          />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ExperimentReportPage", () => {
  it("reconstructs a selected TaskRun deep link and synchronizes later selection", async () => {
    const { requests } = installBackend();
    renderReport(
      `/experiments/${reportExperimentId}/report?taskRun=${secondTaskRunId}`,
    );
    const secondButton = await screen.findByRole("button", {
      name: /task-2 · repeat 1/,
    });
    await waitFor(() => expect(secondButton.getAttribute("aria-pressed")).toBe("true"));
    const aggregateMetrics = await screen.findByRole("table", {
      name: "Per-Agent metrics",
    });
    expect(within(aggregateMetrics).getByText("agent-1")).not.toBeNull();
    expect(within(aggregateMetrics).getByText("agent-2")).not.toBeNull();
    expect(await screen.findByText(secondCoreTaskRunId)).not.toBeNull();
    expect(screen.getByText(/fixture mismatch/)).not.toBeNull();
    expect(screen.getByText("Supporting fake-device fixture")).not.toBeNull();
    expect(requests.some((url) => url.includes("/events"))).toBe(false);

    fireEvent.click(screen.getByRole("button", {
      name: /task-1 · repeat 1/,
    }));
    await waitFor(() => {
      expect(screen.getByLabelText("location").textContent).toContain(
        `taskRun=${encodeURIComponent(reportTaskRunId)}`,
      );
    });
    expect(await screen.findByText(reportCoreTaskRunId)).not.toBeNull();
    expect(screen.getByText("Fresh real-Android source")).not.toBeNull();
    expect(screen.getByRole("table", {
      name: "Per-Agent metrics",
    })).toBe(aggregateMetrics);
  });

  it("uses explicit Monitor and authoritative Replay handoffs", async () => {
    installBackend();
    renderReport(`/experiments/${reportExperimentId}/report`);
    const replay = await screen.findByRole("button", {
      name: "Open authoritative Replay",
    });
    fireEvent.click(replay);
    expect(await screen.findByText("Durable Replay route")).not.toBeNull();
  });

  it("loads evidence only after explicit action and disposes it on TaskRun switch", async () => {
    const { requests } = installBackend();
    renderReport(`/experiments/${reportExperimentId}/report`);
    const open = await screen.findByRole("button", { name: "Open evidence" });
    expect(
      requests.some((url) => url.endsWith(`/artifacts/${evidenceArtifactId}`)),
    ).toBe(false);

    fireEvent.click(open);
    expect(
      await screen.findByRole("dialog", {
        name: "Benchmark evidence viewer",
      }),
    ).not.toBeNull();
    expect(await screen.findByText(/<script>fixture<\/script>/)).not.toBeNull();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText("redacted")).not.toBeNull();
    expect(
      screen.getAllByText("Fresh real-Android source").length,
    ).toBeGreaterThanOrEqual(2);
    expect(
      requests.some((url) => url.endsWith(`/artifacts/${evidenceArtifactId}`)),
    ).toBe(true);
    expect(
      screen.getByRole("button", { name: "Open authoritative Replay" }),
    ).not.toBeNull();

    fireEvent.click(screen.getByRole("button", {
      name: /task-2 · repeat 1/,
    }));
    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", {
          name: "Benchmark evidence viewer",
        }),
      ).toBeNull();
    });
  });

  it("returns to the durable Monitor route without report browser state", async () => {
    installBackend();
    renderReport(`/experiments/${reportExperimentId}/report`);
    const back = await screen.findByRole("button", {
      name: "Back to Monitor",
    });
    fireEvent.click(back);
    expect(await screen.findByText("Durable Monitor route")).not.toBeNull();
    expect(screen.getByLabelText("location").textContent).toBe(
      `/experiments/${reportExperimentId}`,
    );
  });

  it("retains Experiment and run-summary facts when one TaskRun report is corrupt", async () => {
    installBackend({ runCorrupt: true });
    renderReport(`/experiments/${reportExperimentId}/report`);
    expect(
      (await screen.findAllByText(reportExperimentId)).length,
    ).toBeGreaterThan(0);
    expect(
      await screen.findByText(/Published evidence failed its integrity check/),
    ).not.toBeNull();
    expect(screen.getByText(/TaskRuns · 2/)).not.toBeNull();
    expect(
      screen.getByRole("table", { name: "Per-Agent metrics" }),
    ).not.toBeNull();
    expect(
      screen.getByText(
        "Descriptive results only. No statistical significance is claimed.",
      ),
    ).not.toBeNull();
    expect(screen.queryByText(/raw fixture detail/)).toBeNull();
  });

  it("reviews manifest and prepares an exact report before browser handoff", async () => {
    const { methods } = installBackend();
    renderReport(`/experiments/${reportExperimentId}/report`);
    const exportButton = await screen.findByRole("button", { name: "Export" });
    await waitFor(() =>
      expect((exportButton as HTMLButtonElement).disabled).toBe(false)
    );
    fireEvent.click(exportButton);
    const drawer = await screen.findByRole("dialog", {
      name: "Benchmark export",
    });
    expect(
      screen.getByRole("button", { name: "Open authoritative Replay" }),
    ).not.toBeNull();
    expect(within(drawer).getByText("Fresh real-Android source")).not.toBeNull();

    fireEvent.click(within(drawer).getByRole("button", {
      name: "Review manifest",
    }));
    expect(
      await within(drawer).findByRole("table", {
        name: "Publication manifest members",
      }),
    ).not.toBeNull();
    expect(within(drawer).getByText(/hidden_by_default_policy/)).not.toBeNull();

    const reportRow = drawer.querySelector(
      '[data-material-kind="experiment_report"]',
    );
    expect(reportRow).not.toBeNull();
    fireEvent.click(within(reportRow as HTMLElement).getByRole("button", {
      name: "Prepare export",
    }));
    const handoff = await within(reportRow as HTMLElement).findByRole("link", {
      name: "Hand off to browser",
    });
    expect(handoff.getAttribute("href")).toContain(exportReportArtifactId);
    expect(
      methods.some((entry) =>
        entry.startsWith("HEAD ") && entry.endsWith(exportReportArtifactId)
      ),
    ).toBe(true);
    fireEvent.click(handoff);
    expect(
      await within(reportRow as HTMLElement).findByText(/Link handed to the browser/),
    ).not.toBeNull();
    expect(screen.queryByText(/export complete/i)).toBeNull();
  });
});
