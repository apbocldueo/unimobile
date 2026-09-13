import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { ExperimentHistoryPage } from "./ExperimentHistoryPage";

const firstId = `experiment-${"b".repeat(32)}`;
const secondId = `experiment-${"a".repeat(32)}`;

/** Build one compact durable History item with independent availability. */
function historyItem(
  experimentId: string,
  acceptedAt: number,
  reportAvailable: boolean,
) {
  const base = `/studio/benchmark-experiments/${experimentId}`;
  return {
    schemaVersion: 1,
    experimentId,
    lifecycle: reportAvailable ? "terminal" : "running",
    terminalReason: reportAvailable ? "completed" : null,
    source: {
      catalogEntryId: "deleted-catalog",
      packageIdentity: "deleted-package@1",
      split: "test",
    },
    agents: [{ agentId: "deleted-agent", revisionId: "revision-durable" }],
    plannedTaskRunCount: 1,
    outcomeAvailability: reportAvailable ? "available" : "pending",
    reportAvailability: reportAvailable ? "available" : "not_produced",
    replayAvailability: "available",
    trajectoryAvailability: "failed",
    bundleAvailability: "pending",
    acceptedAt,
    updatedAt: acceptedAt,
    terminalAt: reportAvailable ? acceptedAt : null,
    links: {
      self: base,
      taskRuns: `${base}/task-runs`,
      artifacts: `${base}/artifacts`,
      report: reportAvailable ? `${base}/report` : null,
      bundle: null,
    },
  };
}

/** Return one JSON response with the Studio content type. */
function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Install deterministic History and optional suggestion endpoints. */
function installHistoryBackend(crossScope = false) {
  const requests: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url.includes("/studio/benchmarks?")) {
        return jsonResponse({
          schemaVersion: 1,
          items: [
            {
              catalogEntryId: "current-catalog",
              packageIdentity: "current@1",
              title: "Current Catalog",
              version: "1",
              sourceKind: "catalog",
              platforms: ["android"],
              splits: [{ name: "test", taskCount: 1 }],
              availability: "available",
              warnings: [],
            },
          ],
          nextCursor: null,
        });
      }
      if (url.includes("/studio/agents?")) {
        return jsonResponse({
          schemaVersion: 1,
          items: [
            {
              schemaVersion: 1,
              agentId: "current-agent",
              name: "Current Agent",
              currentRevisionId: null,
              createdAt: 1,
              updatedAt: 1,
            },
          ],
          nextCursor: null,
        });
      }
      const parsed = new URL(url, "http://studio.test");
      const cursor = parsed.searchParams.get("cursor");
      const first = historyItem(firstId, 20, true);
      if (crossScope) {
        first.links.self = `/studio/benchmark-experiments/${secondId}`;
      }
      return jsonResponse({
        schemaVersion: 1,
        items: cursor ? [historyItem(secondId, 10, false)] : [first],
        nextCursor: cursor ? null : "opaque-next",
      });
    }),
  );
  return requests;
}

/** Expose the current reconstructable location for route assertions. */
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}{location.search}</output>;
}

/** Render History with isolated query state and handoff targets. */
function renderHistory(path = "/experiments") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <LocationProbe />
        <Routes>
          <Route path="/experiments" element={<ExperimentHistoryPage />} />
          <Route
            path="/experiments/:experimentId"
            element={<output>Monitor target</output>}
          />
          <Route
            path="/experiments/:experimentId/report"
            element={<output>Report target</output>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Experiment History page", () => {
  it("reconstructs filters, preserves durable deleted identities, and paginates", async () => {
    const requests = installHistoryBackend();
    const rendered = renderHistory(
      "/experiments?limit=1&lifecycle=terminal"
      + "&catalogEntryId=deleted-catalog&agentId=deleted-agent"
      + "&acceptedFrom=10&acceptedBefore=30",
    );
    expect(await screen.findByText(firstId)).toBeTruthy();
    expect(screen.getAllByText(/deleted-catalog/).length).toBeGreaterThan(0);
    expect(screen.getByText(/deleted-agent @ revision-durable/)).toBeTruthy();
    expect(screen.getByText(/Replay 可用/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Replay/ })).toBeNull();
    expect(screen.getByRole("link", { name: "打开 Report" })).toBeTruthy();
    expect(
      requests.some((url) => {
        const query = new URL(url, "http://studio.test").searchParams;
        return (
          query.get("lifecycle") === "terminal"
          && query.get("catalogEntryId") === "deleted-catalog"
          && query.get("agentId") === "deleted-agent"
          && query.get("acceptedFrom") === "10"
          && query.get("acceptedBefore") === "30"
        );
      }),
    ).toBe(true);
    const options =
      rendered.container.querySelectorAll<HTMLOptionElement>(
        "datalist option",
      );
    expect(Array.from(options).some((option) => option.value === "current-catalog")).toBe(true);
    expect(Array.from(options).some((option) => option.value === "current-agent")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() =>
      expect(screen.getByLabelText("location").textContent).toContain(
        "cursor=opaque-next",
      ),
    );
    expect(await screen.findByText(secondId)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "打开 Report" })).toBeNull();
    expect(screen.getByText(/opaque cursor deep link/)).toBeTruthy();
  });

  it("navigates only through strict Monitor and available Report links", async () => {
    installHistoryBackend();
    renderHistory();
    expect(await screen.findByText(firstId)).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "打开 Monitor" }));
    expect(await screen.findByText("Monitor target")).toBeTruthy();
    cleanup();
    vi.unstubAllGlobals();

    installHistoryBackend();
    renderHistory();
    expect(await screen.findByText(firstId)).toBeTruthy();
    fireEvent.click(screen.getByRole("link", { name: "打开 Report" }));
    expect(await screen.findByText("Report target")).toBeTruthy();
  });

  it("shows invalid-query reset and rejects cross-scope response links", async () => {
    installHistoryBackend();
    renderHistory("/experiments?agentId=one&agentId=two");
    expect(
      screen.getByText("Experiment History 地址无效"),
    ).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "重置为安全的第一页" }),
    );
    expect(await screen.findByText(firstId)).toBeTruthy();
    cleanup();
    vi.unstubAllGlobals();

    installHistoryBackend(true);
    renderHistory();
    expect(
      await screen.findByText("Experiment History 加载失败"),
    ).toBeTruthy();
    expect(screen.queryByRole("link", { name: "打开 Monitor" })).toBeNull();
  });
});
