import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { english } from "./messages";
import { applyUiLocale, uiMessage, uiText, useUiLocale, useUiLocaleStore } from "./locale";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  useUiLocaleStore.getState().setLocale("zh-CN");
  window.localStorage.clear();
});

/** Exercise live copy alongside an uncontrolled draft owned by a React editor. */
function DraftExample() {
  useUiLocale();
  const [value, setValue] = useState("保留我的任务 {0}");
  return <><label>{uiText("任务")}<input aria-label="draft" value={value} onChange={(event) => setValue(event.target.value)} /></label><p>{uiMessage`Agent 状态：${value}`}</p></>;
}

describe("interface language", () => {
  it("switches mounted copy without remounting or translating task input", () => {
    const request = vi.spyOn(window, "fetch");
    render(<DraftExample />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "我的未保存任务 <script>{1}</script>" } });
    act(() => useUiLocaleStore.getState().setLocale("en"));
    expect(screen.getByText("Task")).toBeTruthy();
    expect(screen.getByRole("textbox").getAttribute("value")).toBe("我的未保存任务 <script>{1}</script>");
    expect(screen.getByText("Agent status: 我的未保存任务 <script>{1}</script>")).toBeTruthy();
    expect(document.querySelector("script")).toBeNull();
    expect(document.documentElement.lang).toBe("en");
    expect(document.title).toBe("ZhiXing · Mobile Agent");
    expect(window.localStorage.getItem("zx-studio-language-v1")).toBe("en");
    act(() => useUiLocaleStore.getState().setLocale("zh-CN"));
    expect(screen.getByText("任务")).toBeTruthy();
    expect(screen.getByRole("textbox").getAttribute("value")).toBe("我的未保存任务 <script>{1}</script>");
    expect(request).not.toHaveBeenCalled();
  });

  it("allows in-memory switching when browser persistence is unavailable", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    useUiLocaleStore.getState().setLocale("en");
    expect(uiText("设置")).toBe("Settings");
    applyUiLocale("en");
    expect(document.documentElement.lang).toBe("en");
  });

  it("persists and restores only an allowlisted display preference", async () => {
    window.localStorage.setItem("zx-studio-language-v1", "en");
    vi.resetModules();
    const restored = await import("./locale");
    expect(restored.useUiLocaleStore.getState().locale).toBe("en");
    restored.useUiLocaleStore.getState().setLocale("fr" as "en");
    expect(restored.useUiLocaleStore.getState().locale).toBe("en");
    window.localStorage.setItem("zx-studio-language-v1", "<unsupported>");
    vi.resetModules();
    const invalid = await import("./locale");
    expect(invalid.useUiLocaleStore.getState().locale).toBe("zh-CN");
  });

  it("keeps placeholders intact across the complete reviewed catalog", () => {
    for (const [source, translated] of Object.entries(english)) {
      expect(translated.trim(), source).not.toBe("");
      expect([...new Set(translated.match(/\{\d+\}/g) ?? [])].sort(), source)
        .toEqual([...new Set(source.match(/\{\d+\}/g) ?? [])].sort());
    }
    useUiLocaleStore.getState().setLocale("en");
    expect(uiText("用户原文，不是界面文案")).toBe("用户原文，不是界面文案");
  });
});
