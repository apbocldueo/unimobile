import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import {
  benchmarkCatalogFixtureId,
  benchmarkDraftCommandFixture,
  benchmarkDraftPageFixture,
} from "@/entities/benchmark-authoring";
import { BenchmarkAuthoringPage } from "./BenchmarkAuthoringPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Return a fresh JSON response for the fake Studio backend. */
function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Build one available Catalog page for opaque copy creation. */
function catalogPage() {
  return {
    schemaVersion: 1,
    items: [
      {
        catalogEntryId: benchmarkCatalogFixtureId,
        packageIdentity: "fixture/authoring@0.1.0",
        title: "Authoring Catalog Fixture",
        version: "0.1.0",
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

/** Render the entry page plus a destination route using an isolated Query cache. */
function renderEntry() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/benchmark-authoring"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/benchmark-authoring" element={<BenchmarkAuthoringPage />} />
          <Route
            path="/benchmark-drafts/:draftId/edit"
            element={<div>draft editor destination</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Install a route-aware backend with optional first-create transport failure. */
function installBackend(firstCreateFails = false) {
  const requests: string[] = [];
  let shouldFail = firstCreateFails;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((request: string, init?: RequestInit) => {
      const url = String(request);
      if (url.includes("/studio/benchmarks?")) {
        return Promise.resolve(jsonResponse(catalogPage()));
      }
      if (url.includes("/studio/benchmark-authoring/drafts?")) {
        return Promise.resolve(jsonResponse(benchmarkDraftPageFixture()));
      }
      if (
        url.endsWith("/studio/benchmark-authoring/drafts")
        && init?.method === "POST"
      ) {
        requests.push(String(init.body));
        if (shouldFail) {
          shouldFail = false;
          return Promise.reject(new Error("connection lost"));
        }
        return Promise.resolve(jsonResponse(benchmarkDraftCommandFixture(), 201));
      }
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
  return requests;
}

describe("Benchmark authoring entry", () => {
  it("shows durable draft facts and bounded cursor pagination", async () => {
    installBackend();
    renderEntry();
    expect(await screen.findByText("Authoring Fixture")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Next page" })).toBeTruthy();
  });

  it("creates from each supported template and navigates only after commit", async () => {
    const requests = installBackend();
    renderEntry();
    await screen.findByText("Authoring Fixture");
    fireEvent.change(screen.getByLabelText("Template"), {
      target: { value: "composite-evaluation" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create from template" }));
    expect(await screen.findByText("draft editor destination")).toBeTruthy();
    expect(JSON.parse(requests[0] ?? "{}")).toMatchObject({
      source: { kind: "template", template: "composite-evaluation" },
    });
  });

  it("creates only from an available opaque Catalog entry", async () => {
    const requests = installBackend();
    renderEntry();
    const select = await screen.findByLabelText("Catalog entry");
    fireEvent.change(select, { target: { value: benchmarkCatalogFixtureId } });
    fireEvent.click(screen.getByRole("button", { name: "Create from Catalog" }));
    expect(await screen.findByText("draft editor destination")).toBeTruthy();
    expect(JSON.parse(requests[0] ?? "{}")).toMatchObject({
      source: { kind: "catalog", catalogEntryId: benchmarkCatalogFixtureId },
    });
  });

  it("reuses an unchanged identity after uncertain failure without navigating", async () => {
    const requests = installBackend(true);
    renderEntry();
    await screen.findByText("Authoring Fixture");
    const button = screen.getByRole("button", { name: "Create from template" });
    fireEvent.click(button);
    expect((await screen.findByRole("alert")).textContent).toContain("结果未确认");
    expect(screen.queryByText("draft editor destination")).toBeNull();
    fireEvent.click(button);
    await screen.findByText("draft editor destination");
    expect(JSON.parse(requests[0] ?? "{}").clientRequestId).toBe(
      JSON.parse(requests[1] ?? "{}").clientRequestId,
    );
  });
});
