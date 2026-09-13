import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { RunsTypeTabs } from "./RunsTypeTabs";

/** Expose history movement and the currently reconstructed typed URL. */
function RouteProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return <><output aria-label="location">{`${location.pathname}${location.search}`}</output><button type="button" onClick={() => navigate(-1)}>Back</button></>;
}

afterEach(cleanup);

describe("Runs type navigation", () => {
  it("keeps ordinary and Experiment history in separate URLs and restores filters on Back", () => {
    render(
      <MemoryRouter initialEntries={["/history?q=agent&status=failure"]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <RunsTypeTabs active="ordinary" />
        <RouteProbe />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("link", { name: "Benchmark Experiments" }));
    expect(screen.getByLabelText("location").textContent).toBe("/experiments");
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByLabelText("location").textContent).toBe("/history?q=agent&status=failure");
  });
});
