import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppRoutes } from "@/app/routes";
import {
  benchmarkDraftDetailFixture,
  benchmarkDraftFixtureId,
  benchmarkDraftPageFixture,
} from "@/entities/benchmark-authoring";
import { BenchmarkDraftEditPage } from "./BenchmarkDraftEditPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Return one fresh JSON response for a route-level fake backend. */
function jsonResponse(value: object): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** Build one isolated Query client without automatic retries. */
function queryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

describe("Benchmark authoring routes", () => {
  it("registers the independent Authoring route in the application shell", async () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        /** Accept one observed element in the JSDOM shell fixture. */
        observe() {}

        /** Release the no-op observer in the JSDOM shell fixture. */
        disconnect() {}
      },
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((request: string) => {
        const url = String(request);
        if (url.includes("/studio/benchmark-authoring/drafts?")) {
          return Promise.resolve(jsonResponse(benchmarkDraftPageFixture(null)));
        }
        if (url.includes("/studio/benchmarks?")) {
          return Promise.resolve(
            jsonResponse({
              schemaVersion: 1,
              items: [],
              nextCursor: null,
            }),
          );
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    render(
      <QueryClientProvider client={queryClient()}>
        <MemoryRouter
          initialEntries={["/benchmark-authoring"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <AppRoutes />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      await screen.findByRole("heading", {
        name: "定义草稿与不可变 Revision",
      }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Experiments" }).getAttribute("aria-current")).toBe("page");
  });

  it("redirects malformed draft identities before issuing a query", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <QueryClientProvider client={queryClient()}>
        <MemoryRouter
          initialEntries={["/benchmark-drafts/not-a-draft/edit"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <Routes>
            <Route
              path="/benchmark-drafts/:draftId/edit"
              element={<BenchmarkDraftEditPage />}
            />
            <Route
              path="/benchmark-authoring"
              element={<div>safe authoring entry</div>}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("safe authoring entry")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("loads a valid draft route without exposing later-stage actions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(benchmarkDraftDetailFixture())),
    );
    render(
      <QueryClientProvider client={queryClient()}>
        <MemoryRouter
          initialEntries={[
            `/benchmark-drafts/${benchmarkDraftFixtureId}/edit`,
          ]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <Routes>
            <Route
              path="/benchmark-drafts/:draftId/edit"
              element={<BenchmarkDraftEditPage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByLabelText("Title")).toBeTruthy();
    for (const name of ["Validate", "Run", "Publish", "Export", "Upload"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
  });
});
