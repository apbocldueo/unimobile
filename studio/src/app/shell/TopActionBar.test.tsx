import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { TopActionBar } from "./TopActionBar";

afterEach(cleanup);

describe("Studio global navigation", () => {
  it.each([
    ["/workspace", "我的 Agents"],
    ["/agents/agent-1/design", "我的 Agents"],
    ["/benchmark-authoring", "评测"],
    ["/experiments/experiment-1/report", "评测"],
    ["/experiments?lifecycle=running", "运行记录"],
    ["/runs/run-1/replay", "运行记录"],
  ])("marks the product domain for deep route %s", (entry, label) => {
    render(
      <MemoryRouter initialEntries={[entry]} >
        <TopActionBar />
      </MemoryRouter>,
    );
    expect(screen.getByRole("navigation", { name: "全局导航" })).not.toBeNull();
    expect(screen.getByRole("link", { name: "我的 Agents" }).getAttribute("href")).toBe("/agents");
    expect(screen.getByRole("link", { name: "ZhiXing Studio 首页" }).getAttribute("href")).toBe("/");
    expect(screen.getByRole("link", { name: label }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: label }).className).toContain("focus-visible:ring-2");
    cleanup();
  });
});
