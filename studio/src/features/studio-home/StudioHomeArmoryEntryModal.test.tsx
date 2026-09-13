import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StudioHomeArmoryEntryModal } from "./StudioHomeArmoryEntryModal";

vi.mock("@/app/shell/ModuleNavSwitchContext", () => ({
  useModuleNavSwitch: () => ({
    pendingPath: null,
    errorPath: null,
    switchModule: vi.fn(async () => undefined),
    retry: vi.fn(async () => undefined),
  }),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Studio Home Agent creation entry", () => {
  it("advertises only the authoritative remote explicit-loop template plus blank", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            schemaVersion: 1,
            templates: [{
              id: "modular_baseline",
              name: "Mobile Agent 显式闭环（推荐）",
              description: "显式设备观察与有界反馈",
            }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    render(<StudioHomeArmoryEntryModal onClose={vi.fn()} />);
    expect(await screen.findByText("Mobile Agent 显式闭环（推荐）")).not.toBeNull();
    expect(screen.getByText("空白流程")).not.toBeNull();
    expect(screen.queryByText(/线性主干|旧版|legacy/i)).toBeNull();
  });
});
