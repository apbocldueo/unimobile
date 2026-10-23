import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BuilderLayout } from "./BuilderLayout";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { PANE_STORAGE_KEY } from "../model/panePreferences";

afterEach(() => { cleanup(); localStorage.clear(); vi.restoreAllMocks(); });
describe("Builder pane layout", () => {
  it("resizes by keyboard and resets without touching editing state", () => {
    const before = useAgentBuilderDocumentStore.getState();
    render(<BuilderLayout><span>content</span></BuilderLayout>);
    fireEvent.click(screen.getByRole("button", { name: "＋ 添加能力" }));
    const separator = screen.getByRole("separator", { name: "Resize palette" });
    const width = separator.getAttribute("aria-valuenow");
    fireEvent.keyDown(separator, { key: "ArrowLeft" });
    expect(Number(separator.getAttribute("aria-valuenow"))).toBe(Number(width) - 20);
    fireEvent.keyDown(separator, { key: "Home" });
    expect(separator.getAttribute("aria-valuenow")).toBe(width);
    expect(useAgentBuilderDocumentStore.getState()).toBe(before);
    expect(Object.keys(JSON.parse(localStorage.getItem(PANE_STORAGE_KEY)!)).sort()).toEqual(["inspector", "palette", "version"]);
  });
  it("works with unavailable preference storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("denied"); });
    render(<BuilderLayout><span>content</span></BuilderLayout>);
    fireEvent.click(screen.getByRole("button", { name: "配置与检查" }));
    fireEvent.keyDown(screen.getByRole("separator", { name: "Resize inspector" }), { key: "Home" });
    expect(screen.getByText("content")).not.toBeNull();
  });
});

/** Verify that panel visibility is local UI state and selections reveal their editor. */
it("opens configuration for a selection and lets users hide it without clearing selection", () => {
  useAgentBuilderDocumentStore.setState({ selectedCanvasId: null, selectedEdgeId: null, compileResult: null });
  render(<BuilderLayout><span>content</span></BuilderLayout>);
  expect(screen.queryByRole("separator")).toBeNull();
  act(() => useAgentBuilderDocumentStore.getState().selectNode("memory"));
  expect(screen.getByRole("button", { name: "收起配置" }).getAttribute("aria-expanded")).toBe("true");
  fireEvent.click(screen.getByRole("button", { name: "收起配置" }));
  expect(useAgentBuilderDocumentStore.getState().selectedCanvasId).toBe("memory");
  expect(screen.queryByRole("separator")).toBeNull();
  act(() => useAgentBuilderDocumentStore.getState().selectNode(null));
});
