import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { BenchmarkModuleSidebar } from "./BenchmarkModuleSidebar";

/** Render Benchmark navigation at one concrete app location. */
function renderSidebar(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <BenchmarkModuleSidebar />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("Benchmark module sidebar", () => {
  it("marks History active only on the exact `/experiments` route", () => {
    renderSidebar("/experiments");
    expect(
      screen
        .getByRole("link", { name: "Experiment History" })
        .getAttribute("aria-current"),
    ).toBe("page");
    cleanup();

    renderSidebar("/experiments/new");
    expect(
      screen
        .getByRole("link", { name: "Experiment Composer" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(
      screen
        .getByRole("link", { name: "Experiment History" })
        .getAttribute("aria-current"),
    ).toBeNull();
  });

  it("owns both Authoring entry and draft-editor routes", () => {
    renderSidebar("/benchmark-authoring");
    expect(
      screen
        .getByRole("link", { name: "Benchmark Authoring" })
        .getAttribute("aria-current"),
    ).toBe("page");
    cleanup();

    renderSidebar(`/benchmark-drafts/benchmark-draft-${"a".repeat(32)}/edit`);
    expect(
      screen
        .getByRole("link", { name: "Benchmark Authoring" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(screen.getByRole("link", { name: "Benchmark Catalog" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Experiment Composer" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Experiment History" })).toBeTruthy();
  });
});
