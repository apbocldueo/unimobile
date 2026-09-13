import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { AgentBuilderEntryPage } from "./AgentBuilderEntryPage";

/** Render the compatibility Builder entry with isolated query state. */
function renderEntry() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/" element={<AgentBuilderEntryPage />} />
          <Route path="/agents" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Expose the compatibility destination without relying on browser globals. */
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{`${location.pathname}${location.search}`}</output>;
}

afterEach(() => {
  cleanup();
});

describe("Agent Builder compatibility entry", () => {
  it("redirects deterministically to the authoritative Agent Library", () => {
    renderEntry();
    expect(screen.getByLabelText("location").textContent).toBe("/agents");
  });
});
