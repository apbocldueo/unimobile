import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { runtimeReadinessKeys } from "@/entities/runtime-readiness";
import { useStudioModuleShellStore } from "@/stores/studioModuleShellStore";
import { useStudioSettingsStore } from "@/stores/studioSettingsStore";
import { SettingsPage } from "./SettingsPage";
import { useUiLocaleStore } from "@/shared/i18n";

const safeResponse = {
  schemaVersion: 1 as const,
  ready: false,
  providers: [{
    identifier: "llm:openai_llm@1.0.0",
    category: "runtime_service",
    available: true,
    errorType: "",
  }],
  secrets: [{ secretRef: "openai_api_key", configured: false }],
  deviceProfiles: [{
    deviceProfileId: "research-android",
    label: "Research Android",
    platform: "android" as const,
    availability: "configured" as const,
  }],
  diagnostics: [],
};

beforeEach(() => {
  useStudioModuleShellStore.getState().setSettingsSidebarKey("runtime");
  window.localStorage.clear();
  useUiLocaleStore.getState().setLocale("zh-CN");
  useStudioSettingsStore.getState().setThemeMode("light");
});

afterEach(() => {
  cleanup();
  useUiLocaleStore.getState().setLocale("zh-CN");
  vi.unstubAllGlobals();
});

describe("Settings runtime environment", () => {
  it("switches language immediately with local-only persistence and keeps the active section", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
    client.setQueryData(runtimeReadinessKeys.process, safeResponse);
    render(<QueryClientProvider client={client}><SettingsPage /></QueryClientProvider>);
    fireEvent.click(screen.getByRole("button", { name: "主题与字号" }));
    fireEvent.click(screen.getByRole("button", { name: "English", pressed: false }));
    expect(screen.getByRole("heading", { name: "Theme settings" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "English", pressed: true })).toBeTruthy();
    expect(screen.getByText("Interface theme")).toBeTruthy();
    expect(window.localStorage.getItem("zx-studio-language-v1")).toBe("en");
    expect(useStudioModuleShellStore.getState().settingsSidebarKey).toBe("theme");
    fireEvent.click(screen.getByRole("button", { name: "中文", pressed: false }));
    expect(screen.getByRole("heading", { name: "主题设置" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("zh-CN");
    expect(fetch).not.toHaveBeenCalled();
  });
  it("replaces cached readiness with a failure state and retries only the read-only query", async () => {
    let calls = 0;
    const fetch = vi.fn(async () => {
      calls += 1;
      return calls === 1 ? new Response("unavailable", { status: 503 }) : new Response(JSON.stringify(safeResponse), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetch);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(runtimeReadinessKeys.process, { ...safeResponse, ready: true });
    render(<QueryClientProvider client={client}><SettingsPage /></QueryClientProvider>);
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    expect(await screen.findByText("静态配置状态未知")).not.toBeNull();
    expect(screen.queryByRole("heading", { name: "Preparation checklist" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    expect(await screen.findByText("静态运行配置需要处理")).not.toBeNull();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("textbox")).toBeNull();
  });
  it("renders presence-only identities and never persists configuration", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(runtimeReadinessKeys.process, safeResponse);
    render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    expect(screen.getByText("openai_api_key")).not.toBeNull();
    expect(screen.getByText("Research Android")).not.toBeNull();
    expect(screen.getByText("设备在线状态：尚未检查")).not.toBeNull();
    expect(screen.getByText("模型接口连接：尚未测试")).not.toBeNull();
    expect(screen.getByText("python run_studio.py")).not.toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(JSON.stringify(window.localStorage)).not.toContain("openai_api_key");
  });

  it("refreshes the process projection after a service restart", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(
      JSON.stringify({ ...safeResponse, ready: true, secrets: [{ secretRef: "openai_api_key", configured: true }] }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(runtimeReadinessKeys.process, safeResponse);
    render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await waitFor(() => expect(screen.getByText("configured")).not.toBeNull());
    expect(screen.getByText("静态运行配置已就绪")).not.toBeNull();
  });

  it("keeps settings modes discoverable after the global sidebar is removed", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(runtimeReadinessKeys.process, safeResponse);
    render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "主题与字号" }));
    fireEvent.click(screen.getByRole("radio", { name: "深色" }));

    expect(document.documentElement.dataset.zxTheme).toBe("dark");
    expect(window.localStorage.getItem("zx-studio-settings-v1")).toContain('"themeMode":"dark"');
    expect(window.localStorage.getItem("zx-studio-settings-v1")).not.toContain("openai_api_key");
  });
});
