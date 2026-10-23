import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { useStudioRegistryStore } from "@/stores/studioRegistryStore";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("public home and workspace boundary", () => {
  it("renders and switches truthful product previews without querying a backend", async () => {
    const fetch = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", fetch);
    const bootstrap = vi.spyOn(useStudioRegistryStore.getState(), "bootstrap");
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Mobile Agent");
    expect(screen.queryByRole("navigation", { name: "全局导航" })).toBeNull();
    expect(screen.queryByText("运行准备")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "运行与回放" }));
    expect(screen.getByRole("button", { name: "运行与回放" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText(/此任务未完成/)).not.toBeNull();
    const replayImage = screen.getByRole("img");
    expect(replayImage.getAttribute("alt")).toContain("失败说明");
    expect(screen.getByRole("link", { name: "查看运行与回放完整截图（新标签页）" }).getAttribute("href")).toBe(replayImage.getAttribute("src"));

    fireEvent.click(screen.getByRole("button", { name: "独立评测" }));
    expect(screen.getByText(/不代表评测已通过/)).not.toBeNull();
    expect(screen.getByRole("link", { name: "浏览 Benchmark" }).getAttribute("href")).toBe("/benchmarks");
    await act(async () => {});
    expect(fetch).not.toHaveBeenCalled();
    expect(bootstrap).not.toHaveBeenCalled();
  });

  it("enters the existing workspace explicitly and returns home via the Studio logo", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    const bootstrap = vi.spyOn(useStudioRegistryStore.getState(), "bootstrap").mockResolvedValue(undefined);
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    fireEvent.click(screen.getAllByRole("link", { name: "进入知行" })[0]);
    // The full workspace module is deliberately lazy; parallel suite transforms can exceed 1 s.
    expect(await screen.findByRole("heading", { name: "我的 Agents" }, { timeout: 10_000 })).not.toBeNull();
    expect(bootstrap).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "我的 Agents" }).getAttribute("aria-current")).toBe("page");
    fireEvent.click(screen.getByRole("link", { name: "ZhiXing Studio 首页" }));
    expect(await screen.findByRole("heading", { level: 1 })).not.toBeNull();
    expect(screen.queryByRole("navigation", { name: "全局导航" })).toBeNull();
  }, 15_000);

  it("restores the workspace on direct entry", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    vi.spyOn(useStudioRegistryStore.getState(), "bootstrap").mockResolvedValue(undefined);
    render(<MemoryRouter initialEntries={["/workspace"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "我的 Agents" }, { timeout: 10_000 })).not.toBeNull();
  });
});
