import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkAgentFixtureId,
  benchmarkAgentRevisionFixtureId,
  benchmarkAuthoringRevisionFixture,
  benchmarkDryRunResultFixture,
  benchmarkValidationResultFixture,
} from "@/entities/benchmark-authoring";
import { BenchmarkValidationDryRunView, type BenchmarkValidationDryRunViewProps } from "@/features/benchmark-validation-dry-run";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Build one JSON response for the in-browser no-device entity boundary. */
function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Build clean default view props with observable public callbacks. */
function props(
  overrides: Partial<BenchmarkValidationDryRunViewProps> = {},
): BenchmarkValidationDryRunViewProps {
  return {
    revision: benchmarkAuthoringRevisionFixture(),
    gateInput: {
      definitionStatus: {
        dirty: false,
        hasBufferError: false,
        hasUnappliedBuffer: false,
        savePending: false,
      },
      baselineRevisionId: benchmarkAuthoringRevisionFixture().revisionId,
      queryCurrentRevisionId: benchmarkAuthoringRevisionFixture().revisionId,
      conflictRevisionId: null,
      remoteMayBeNewer: false,
      contentPending: false,
    },
    navigationRequest: null,
    onAnalysisPendingChange: vi.fn(),
    onDiagnosticNavigate: vi.fn(),
    onStaleConflict: vi.fn(),
    ...overrides,
  };
}

/** Render the view with an isolated non-retrying Query client. */
function renderView(input: BenchmarkValidationDryRunViewProps) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <BenchmarkValidationDryRunView {...input} />
    </QueryClientProvider>,
  );
}

/** Return one bounded Agent candidate page. */
function agentPage() {
  return {
    schemaVersion: 1,
    items: [
      {
        agentId: benchmarkAgentFixtureId,
        name: "Analysis Agent",
        currentRevisionId: benchmarkAgentRevisionFixtureId,
        createdAt: 1,
        updatedAt: 1,
      },
      {
        agentId: "agent-without-revision",
        name: "Unsaved Agent",
        currentRevisionId: null,
        createdAt: 1,
        updatedAt: 1,
      },
    ],
    nextCursor: null,
  };
}

describe("BenchmarkValidationDryRunView", () => {
  it("starts no analysis automatically and blocks a dirty baseline truthfully", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(agentPage()));
    vi.stubGlobal("fetch", fetchMock);
    renderView(props({
      gateInput: {
        ...props().gateInput,
        definitionStatus: {
          ...props().gateInput.definitionStatus,
          dirty: true,
        },
      },
    }));

    await screen.findByText("Analysis Agent");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/studio/agents?");
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Validate" }).disabled).toBe(true);
    expect(screen.getByText(/请先保存或 Reset/)).not.toBeNull();
    expect(screen.getByText("executionEvidence = false")).not.toBeNull();
  });

  it("shows partial identities and emits one member navigation intent", async () => {
    const onNavigate = vi.fn();
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/studio/agents?")) return Promise.resolve(jsonResponse(agentPage()));
      return Promise.resolve(jsonResponse(benchmarkValidationResultFixture()));
    }));
    renderView(props({ onDiagnosticNavigate: onNavigate }));

    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    await screen.findByText("Definition invalid");
    expect(screen.getAllByText("not established")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Navigate" }));
    expect(onNavigate).toHaveBeenCalledWith(expect.objectContaining({
      target: "definition",
      memberKind: "task",
      memberPath: "tasks/test.json",
      fieldPath: [0, "id"],
    }));
  });

  it("freezes an Agent and renders only one 50-row schedule page", async () => {
    const dryRun = benchmarkDryRunResultFixture();
    dryRun.schedule = Array.from({ length: 10_000 }, (_, index) => ({
      ...dryRun.schedule[0]!,
      repeat: index,
      seed: index,
      sharedInstanceKey: `fixture:${index}`,
    }));
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/studio/agents?")) return Promise.resolve(jsonResponse(agentPage()));
      return Promise.resolve(jsonResponse(dryRun));
    }));
    const rendered = renderView(props());

    await screen.findByText("Analysis Agent");
    const freezeButton = screen
      .getAllByRole<HTMLButtonElement>("button", { name: "Freeze" })
      .find((button) => !button.disabled);
    expect(freezeButton).toBeDefined();
    fireEvent.click(freezeButton!);
    fireEvent.click(screen.getByRole("button", { name: "Dry-run" }));
    await screen.findByText("Complete bounded plan projected");
    expect(screen.getByText(/Complete schedule · 10000 entries/)).not.toBeNull();
    expect(rendered.container.querySelectorAll("tbody tr")).toHaveLength(50);
    expect(screen.getByText(/not fairness proof/)).not.toBeNull();
    expect(screen.getByText(/current-worker-cardinality/)).not.toBeNull();
    expect(screen.queryByRole("button", { name: /Publish|Run|Migrate|Contract Test/ })).toBeNull();
  });

  it("surfaces stale-current as Reload Remote ownership without a result", async () => {
    const onConflict = vi.fn();
    const currentRevisionId = `benchmark-authoring-revision-${"9".repeat(32)}`;
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/studio/agents?")) return Promise.resolve(jsonResponse(agentPage()));
      return Promise.resolve(jsonResponse({
        schemaVersion: 1,
        error: {
          code: "benchmark.authoring.revision_conflict",
          message: "Current revision changed",
          currentRevisionId,
        },
      }, 409));
    }));
    renderView(props({ onStaleConflict: onConflict }));

    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    await waitFor(() => expect(onConflict).toHaveBeenCalledWith(currentRevisionId));
    expect(screen.getByText(/请 Reload Remote/)).not.toBeNull();
    expect(screen.queryByText("Definition valid for selected split")).toBeNull();
  });

  it("keeps a bounded capacity rejection as a non-result transport state", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.includes("/studio/agents?")) return Promise.resolve(jsonResponse(agentPage()));
      return Promise.resolve(jsonResponse({
        schemaVersion: 1,
        error: {
          code: "benchmark.authoring.analysis_capacity",
          message: "Schedule exceeds the bounded preview capacity",
          currentRevisionId: null,
        },
      }, 413));
    }));
    renderView(props());

    fireEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText(
      "Transport failure: Schedule exceeds the bounded preview capacity",
    )).not.toBeNull();
    expect(screen.queryByText("Definition valid for selected split")).toBeNull();
  });

  it("reveals a workbench-owned frozen-Agent diagnostic without changing selection", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(agentPage())));
    const initial = props();
    const rendered = renderView(initial);
    await screen.findByText("Analysis Agent");
    rendered.rerender(
      <QueryClientProvider client={new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })}>
        <BenchmarkValidationDryRunView
          {...initial}
          navigationRequest={{
            requestId: 1,
            agentId: benchmarkAgentFixtureId,
            fieldPath: ["graph", "nodes", 0],
          }}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText(benchmarkAgentFixtureId)).not.toBeNull();
    expect(screen.getByText(".graph.nodes[0]")).not.toBeNull();
    expect(screen.getByText(/Frozen Agent revisions \(0\/16\)/)).not.toBeNull();
  });
});
