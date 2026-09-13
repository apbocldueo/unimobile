import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { runtimeReadinessKeys } from "@/entities/runtime-readiness";
import { useStudioModuleShellStore } from "@/stores/studioModuleShellStore";
import { useStudioSettingsStore } from "@/stores/studioSettingsStore";
import { SettingsPage } from "./SettingsPage";

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
  useStudioSettingsStore.getState().setThemeMode("light");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Settings runtime environment", () => {
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
