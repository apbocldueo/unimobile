import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  benchmarkAuthoringRevisionFixture,
  benchmarkContractProfilePageFixture,
  benchmarkContractTestResultFixture,
} from "@/entities/benchmark-authoring";
import { BenchmarkContractTestsView } from "./BenchmarkContractTestsView";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Return one JSON response for a fake Studio exchange. */
function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Render the Contract Test feature with a clean authoritative baseline. */
function renderView(onNavigate = vi.fn(), onStaleConflict = vi.fn()) {
  const revision = benchmarkAuthoringRevisionFixture();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <BenchmarkContractTestsView
        revision={revision}
        gateInput={{
          definitionStatus: {
            dirty: false,
            hasBufferError: false,
            hasUnappliedBuffer: false,
            savePending: false,
          },
          baselineRevisionId: revision.revisionId,
          queryCurrentRevisionId: revision.revisionId,
          conflictRevisionId: null,
          remoteMayBeNewer: false,
          contentPending: false,
          peerAnalysisPending: false,
        }}
        onPendingChange={vi.fn()}
        onDiagnosticNavigate={onNavigate}
        onStaleConflict={onStaleConflict}
      />
    </QueryClientProvider>,
  );
}

/** Install the profile metadata exchange plus one explicit command result. */
function installResultBackend(result: object, status = 200) {
  const fetchMock = vi.fn().mockImplementation((request: string, init?: RequestInit) => {
    const url = String(request);
    if (url.endsWith("/contract-test-profiles")) {
      return Promise.resolve(jsonResponse(benchmarkContractProfilePageFixture()));
    }
    if (url.endsWith("/contract-tests") && init?.method === "POST") {
      return Promise.resolve(jsonResponse(result, status));
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Build one internally consistent single-case presentation status. */
function resultForStatus(status: "passed" | "failed" | "skipped") {
  const result = benchmarkContractTestResultFixture();
  result.seed = 0;
  const item = result.cases[0]!;
  if (status === "failed") {
    result.coverage = {
      total: 1, passed: 0, failed: 1, skipped: 0,
      complete: true, executedChecksPassed: false,
    };
    item.status = "failed";
    item.diagnostics = [{
      code: "benchmark.ctk.output_not_deterministic",
      message: "Evaluator fake fixture failed.",
      memberKind: "task",
      memberPath: "tasks/test.json",
      fieldPath: [0, "evaluator"],
      taskId: "fixture-task",
    }];
  } else if (status === "skipped") {
    result.coverage = {
      total: 1, passed: 0, failed: 0, skipped: 1,
      complete: false, executedChecksPassed: true,
    };
    item.status = "skipped";
    item.fixtureId = null;
    item.fixtureVersion = null;
    item.checks = [];
    item.skipped = ["fixture:not-registered"];
  }
  return result;
}

describe("Benchmark Contract Tests view", () => {
  it("does not auto-run and presents mixed coverage plus safety limits", async () => {
    const result = benchmarkContractTestResultFixture();
    result.seed = 0;
    result.coverage = {
      total: 2,
      passed: 1,
      failed: 0,
      skipped: 1,
      complete: false,
      executedChecksPassed: true,
    };
    result.cases.push({
      ...result.cases[0]!,
      caseId: `sha256:${"6".repeat(64)}`,
      kind: "environment",
      logicalName: "third_party_setup",
      status: "skipped",
      fixtureId: null,
      fixtureVersion: null,
      checks: [],
      skipped: ["fixture:not-registered"],
      diagnostics: [{
        code: "benchmark.ctk.fixture_missing",
        message: "No explicit environment fake fixture is registered.",
        memberKind: "task",
        memberPath: "tasks/test.json",
        fieldPath: [0, "environment_initializer", 0],
        taskId: "fixture-task",
      }],
    });
    const fetchMock = vi.fn().mockImplementation((request: string, init?: RequestInit) => {
      const url = String(request);
      if (url.endsWith("/contract-test-profiles")) {
        return Promise.resolve(jsonResponse(benchmarkContractProfilePageFixture()));
      }
      if (url.endsWith("/contract-tests") && init?.method === "POST") {
        return Promise.resolve(jsonResponse(result));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const navigate = vi.fn();
    renderView(navigate);

    expect(await screen.findByText("Not run")).toBeTruthy();
    await waitFor(() => expect(
      (screen.getByRole("button", { name: "Run Contract Tests" }) as HTMLButtonElement).disabled,
    ).toBe(false));
    expect(fetchMock.mock.calls.filter((call) => call[1]?.method === "POST")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Run Contract Tests" }));
    await waitFor(() => expect(
      fetchMock.mock.calls.filter((call) => call[1]?.method === "POST"),
    ).toHaveLength(1));
    expect(await screen.findByText("Executed checks passed; coverage incomplete")).toBeTruthy();
    expect(screen.getByText(/This is not a process sandbox/)).toBeTruthy();
    expect(screen.getByText(/revision remains unvalidated/)).toBeTruthy();
    fireEvent.click(screen.getByText(/benchmark.ctk.fixture_missing/));
    expect(navigate).toHaveBeenCalledWith(expect.objectContaining({
      memberPath: "tasks/test.json",
      fieldPath: [0, "environment_initializer", 0],
    }));
    fireEvent.change(screen.getByLabelText("Contract status filter"), { target: { value: "skipped" } });
    await waitFor(() => expect(screen.getByText("1 matching cases")).toBeTruthy());
  });

  it.each([
    ["passed", "All covered fake-fixture checks passed"],
    ["failed", "Executed contract checks failed"],
    ["skipped", "Executed checks passed; coverage incomplete"],
  ] as const)("presents the %s aggregate state truthfully", async (status, title) => {
    installResultBackend(resultForStatus(status));
    renderView();
    const button = await screen.findByRole("button", { name: "Run Contract Tests" });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    expect(await screen.findByText(title)).toBeTruthy();
  });

  it("distinguishes capacity and stale-current failures", async () => {
    installResultBackend({
      schemaVersion: 1,
      error: {
        code: "benchmark.authoring.contract_test_too_large",
        message: "Contract Test exceeds its safe limit",
      },
    }, 413);
    renderView();
    const button = await screen.findByRole("button", { name: "Run Contract Tests" });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    expect(await screen.findByText("Contract Test capacity exceeded")).toBeTruthy();

    cleanup();
    const stale = vi.fn();
    installResultBackend({
      schemaVersion: 1,
      error: {
        code: "benchmark.authoring.analysis_revision_stale",
        message: "Current revision changed",
        currentRevisionId: `benchmark-authoring-revision-${"c".repeat(32)}`,
      },
    }, 409);
    renderView(vi.fn(), stale);
    const staleButton = await screen.findByRole("button", { name: "Run Contract Tests" });
    await waitFor(() => expect((staleButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(staleButton);
    expect(await screen.findByText("Result stale")).toBeTruthy();
    expect(stale).toHaveBeenCalledWith(
      `benchmark-authoring-revision-${"c".repeat(32)}`,
    );
  });

  it("paginates bounded cases without changing aggregate facts", async () => {
    const result = benchmarkContractTestResultFixture();
    result.seed = 0;
    result.cases = Array.from({ length: 26 }, (_, index) => ({
      ...result.cases[0]!,
      caseId: `sha256:${index.toString(16).padStart(64, "0")}`,
      logicalName: `file_exist_${index}`,
    }));
    result.coverage = {
      total: 26, passed: 26, failed: 0, skipped: 0,
      complete: true, executedChecksPassed: true,
    };
    installResultBackend(result);
    renderView();
    const button = await screen.findByRole("button", { name: "Run Contract Tests" });
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    expect(await screen.findByText("26 matching cases")).toBeTruthy();
    expect(screen.getByText("Page 1 / 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Page 2 / 2")).toBeTruthy();
  });
});
