import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { HistoryModuleSidebar } from "./HistoryModuleSidebar";

describe("HistoryModuleSidebar", () => {
  afterEach(() => cleanup());

  it("uses a compact back rail inside Replay", () => {
    render(
      <MemoryRouter
        initialEntries={["/runs/run-1"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <HistoryModuleSidebar compact />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText("Replay 历史导航")).not.toBeNull();
    expect(screen.getByRole("link", { name: "返回运行历史" }).getAttribute("href")).toBe("/history");
    expect(screen.queryByText("筛选条件")).toBeNull();
    expect(screen.queryByText("导出记录")).toBeNull();
  });
});
