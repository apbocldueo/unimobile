import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { TopActionBar } from "./TopActionBar";

afterEach(cleanup);

describe("Studio global navigation", () => {
  it.each([
    ["/agents/agent-1/design", "Agents"],
    ["/benchmark-authoring", "Experiments"],
    ["/experiments/experiment-1/report", "Experiments"],
    ["/experiments?lifecycle=running", "Runs"],
    ["/runs/run-1/replay", "Runs"],
  ])("marks the product domain for deep route %s", (entry, label) => {
    render(
      <MemoryRouter initialEntries={[entry]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <TopActionBar />
      </MemoryRouter>,
    );
    expect(screen.getByRole("navigation", { name: "全局导航" })).not.toBeNull();
    expect(screen.getByRole("link", { name: label }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: label }).className).toContain("focus-visible:ring-2");
    cleanup();
  });
});
