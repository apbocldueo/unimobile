import type { FinalConnectionState, ReactFlowProps } from "@xyflow/react";
import type { MouseEvent as ReactMouseEvent } from "react";
import { useToastStore } from "@/stores/toastStore";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { useCanvasInteractionStore } from "../model/canvasInteraction.store";
import { BuilderCanvas } from "./BuilderCanvas";
import type { BuilderFlowNode, BuilderFlowEdge } from "../model/flowAdapter";

const camera = vi.hoisted(() => ({
  props: {} as ReactFlowProps<BuilderFlowNode, BuilderFlowEdge>,
  viewport: { x: 0, y: 0, zoom: 1 },
  move: vi.fn(),
  cancel: vi.fn(),
  setFlowState: vi.fn(),
  nodes: [] as { id: string; measured?: { width: number; height: number } }[],
}));

vi.mock("@xyflow/react", async () => {
  const { applyNodeChanges } = await vi.importActual<typeof import("@xyflow/react")>("@xyflow/react");
  const flowApi = {
    screenToFlowPosition: (point: { x: number; y: number }) => point,
    getViewport: () => camera.viewport,
    setViewport: camera.move,
    getNodes: () => camera.nodes,
  };
  return ({
  applyNodeChanges,
  Background: () => null, Controls: () => null,
  BackgroundVariant: { Dots: "dots" }, MarkerType: { ArrowClosed: "arrow" },
  useNodesInitialized: () => true,
  useStore: () => 600,
  useStoreApi: () => ({ getState: () => ({ cancelConnection: camera.cancel }), setState: camera.setFlowState }),
  Handle: () => null, Position: { Left: "left", Right: "right" },
  useReactFlow: () => flowApi,
  ReactFlow: (props: typeof camera.props) => { camera.props = props; return null; },
});
});

describe("continuous drag geometry", () => {
  it("updates before release without touching document/history and commits one undoable move", () => {
    const before = setup();
    const previousPosition = before.document!.presentation.nodes.output;
    const initialInput = camera.props.nodes!.find((node) => node.id === "input");
    for (let step = 1; step <= 25; step += 1) {
      act(() => camera.props.onNodesChange?.([{ id: "output", type: "position", position: { x: 500 + step, y: 200 + step }, dragging: true }]));
      expect(camera.props.nodes!.find((node) => node.id === "output")!.position).toEqual({ x: 500 + step, y: 200 + step });
    }
    expect(camera.props.nodes!.find((node) => node.id === "input")).toBe(initialInput);
    expect(useAgentBuilderDocumentStore.getState().document).toBe(before.document);
    expect(useAgentBuilderDocumentStore.getState().past).toHaveLength(0);
    const moved = camera.props.nodes!.find((node) => node.id === "output")!;
    act(() => camera.props.onNodeDragStop?.({} as ReactMouseEvent, moved, [moved]));
    expect(useAgentBuilderDocumentStore.getState().past).toHaveLength(1);
    expect(useAgentBuilderDocumentStore.getState().document!.presentation.nodes.output).toMatchObject({ x: 525, y: 225 });
    act(() => useAgentBuilderDocumentStore.getState().undo());
    expect(camera.props.nodes!.find((node) => node.id === "output")!.position).toEqual({ x: previousPosition.x, y: previousPosition.y });
    act(() => useAgentBuilderDocumentStore.getState().redo());
    expect(camera.props.nodes!.find((node) => node.id === "output")!.position).toEqual({ x: 525, y: 225 });
  });

  it("commits a group once and rejects an old session's drag end", () => {
    setup();
    const end = camera.props.onNodeDragStop!;
    const moved = camera.props.nodes!.map((node) => ({ ...node, position: { x: node.position.x + 80, y: node.position.y + 40 } }));
    act(() => end({} as ReactMouseEvent, moved[0]!, moved));
    expect(useAgentBuilderDocumentStore.getState().past).toHaveLength(1);
    act(() => useAgentBuilderDocumentStore.getState().replaceDocument(createEmptyStudioDocument("new", "New", "new-doc"), "new-rev"));
    const replacement = useAgentBuilderDocumentStore.getState().document;
    act(() => end({} as ReactMouseEvent, moved[0]!, moved));
    expect(useAgentBuilderDocumentStore.getState().document).toBe(replacement);
    expect(useAgentBuilderDocumentStore.getState().past).toHaveLength(0);
  });
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); camera.move.mockReset(); useAgentBuilderDocumentStore.getState().clear(); });

/** Mount an inert XYFlow boundary with authoritative current DOM geometry.
 * Returns: Current document state; no real device or animation is involved.
 */
function setup() {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ x: 0, y: 0, left: 0, top: 0, right: 600, bottom: 400, width: 600, height: 400, toJSON: () => ({}) });
  const document = createEmptyStudioDocument("agent", "Test", "document");
  document.presentation.nodes.output = { x: 2000, y: 1000, label: "Output" };
  useAgentBuilderDocumentStore.getState().replaceDocument(document, "revision");
  render(<BuilderCanvas catalog={null} />);
  return useAgentBuilderDocumentStore.getState();
}

describe("temporary camera command boundary", () => {
  it("reveals an off-screen object with zero duration without changing a saved document", () => {
    const before = setup();
    const port = useCanvasInteractionStore.getState().port!;
    act(() => port.reveal("output"));
    expect(camera.move).toHaveBeenCalledWith(expect.objectContaining({ x: expect.any(Number), y: expect.any(Number) }), { duration: 0 });
    act(() => camera.props.onMoveEnd?.(null, { x: -1700, y: -800, zoom: 1 }));
    const after = useAgentBuilderDocumentStore.getState();
    expect(after.document).toBe(before.document);
    expect(after.generation).toBe(before.generation);
    expect(after.dirty).toBe(false);
    expect(after.compileResult).toBe(before.compileResult);
  });
  it("keeps actual user camera gestures temporary and preserves validation", () => {
    const before = setup();
    act(() => camera.props.onMoveEnd?.(new MouseEvent("pointerup"), { x: 30, y: 40, zoom: 0.8 }));
    const after = useAgentBuilderDocumentStore.getState();
    expect(after.cameraViewport).toEqual({ x: 30, y: 40, zoom: 0.8 });
    expect(after.document).toBe(before.document);
    expect(after.generation).toBe(before.generation);
    expect(after.dirty).toBe(false);
    expect(after.compileResult).toBe(before.compileResult);
  });
  it("ignores absent targets and captured commands from a replaced session", () => {
    setup();
    const stale = useCanvasInteractionStore.getState().port!;
    act(() => stale.reveal("deleted-node"));
    expect(camera.move).not.toHaveBeenCalled();
    act(() => useAgentBuilderDocumentStore.getState().replaceDocument(createEmptyStudioDocument("other", "Other", "other-doc"), "other-rev"));
    act(() => stale.reveal("output"));
    expect(camera.move).not.toHaveBeenCalled();
    expect(stale.placement()).toBeNull();
  });
});


describe("connection-end rejection feedback", () => {
  it("explains invalid drag and reconnect once while retaining the original graph", () => {
    const push = vi.spyOn(useToastStore.getState(), "pushToast");
    const before = setup();
    const state = { isValid: false,
      fromHandle: { nodeId: "input", id: "input:output:task", type: "source" },
      toHandle: { nodeId: "output", id: "output:input:connection", type: "target" } } as FinalConnectionState;
    act(() => camera.props.onConnectEnd?.(new MouseEvent("mouseup"), state));
    expect(push).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining("无法连接") }));
    const edge = { id: "edge", source: "input", target: "output" };
    act(() => {
      camera.props.onReconnectStart?.({} as ReactMouseEvent, edge, "target");
      camera.props.onConnectEnd?.(new MouseEvent("mouseup"), state);
      camera.props.onReconnectEnd?.(new MouseEvent("mouseup"), edge, "target", state);
    });
    expect(push).toHaveBeenCalledTimes(2);
    expect(useAgentBuilderDocumentStore.getState().document).toBe(before.document);
    expect(useAgentBuilderDocumentStore.getState().past).toHaveLength(0);
  });
  it("explains click-only rejection when XYFlow supplies no drag state", () => {
    const push = vi.spyOn(useToastStore.getState(), "pushToast");
    setup();
    const handle = document.createElement("div");
    handle.dataset.nodeid = "output";
    handle.dataset.handleid = "output:input:connection";
    handle.className = "target";
    const event = new MouseEvent("click", { bubbles: true });
    handle.dispatchEvent(event);
    act(() => {
      camera.props.onClickConnectStart?.(new MouseEvent("click"), { nodeId: "input", handleId: "input:output:task", handleType: "source" });
      camera.props.onClickConnectEnd?.(event, { fromHandle: null, toHandle: null, isValid: null } as FinalConnectionState);
    });
    expect(push).toHaveBeenCalledOnce();
    expect(push).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining("Catalog 未加载") }));
  });
});


describe("connection cancellation", () => {
  it("cancels XYFlow click and drag state as well as guidance without editing", () => {
    const before = setup();
    act(() => camera.props.onClickConnectStart?.(new MouseEvent("click"), { nodeId: "input", handleId: "input:output:task", handleType: "source" }));
    expect(screen.getByText(/当前没有可连接端口/)).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("main", { name: "AgentGraph 画布" }), { key: "Escape" });
    expect(camera.cancel).toHaveBeenCalled();
    expect(camera.setFlowState).toHaveBeenCalledWith({ connectionClickStartHandle: null });
    expect(screen.queryByText(/当前没有可连接端口/)).toBeNull();
    expect(useAgentBuilderDocumentStore.getState().document).toBe(before.document);
    expect(useAgentBuilderDocumentStore.getState().past).toHaveLength(0);
  });
});


describe("per-connection feedback intent", () => {
  it("keeps feedback during target pointer events and resets after cancellation", () => {
    const before = setup();
    const start = { nodeId: "input", handleId: "input:output:task", handleType: "source" as const };
    act(() => camera.props.onClickConnectStart?.(new MouseEvent("click"), start));
    fireEvent.click(screen.getByRole("button", { name: "↻ 下一轮反馈" }));
    expect(screen.getByText(/没有可反馈的目标/)).toBeTruthy();
    act(() => {
      camera.props.onConnectStart?.(new MouseEvent("mousedown"), { nodeId: "output", handleId: "output:input:connection", handleType: "target" });
      camera.props.onConnectEnd?.(new MouseEvent("mouseup"), { isValid: false } as FinalConnectionState);
    });
    expect(screen.getByRole("button", { name: "↻ 下一轮反馈" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "取消连线（Esc）" }));
    expect(screen.queryByRole("button", { name: "↻ 下一轮反馈" })).toBeNull();
    act(() => camera.props.onClickConnectStart?.(new MouseEvent("click"), start));
    expect(screen.getByRole("button", { name: "普通连接" }).getAttribute("aria-pressed")).toBe("true");
    expect(useAgentBuilderDocumentStore.getState().document).toBe(before.document);
    expect(useAgentBuilderDocumentStore.getState().past).toHaveLength(0);
  });
});
