import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { AgentBuilderFlowProvider } from "./AgentBuilderFlowProvider";
import { BuilderCanvas } from "./BuilderCanvas";
import { AgentBuilderNode } from "./AgentBuilderNode";
import type { BuilderNodeData } from "../model/flowAdapter";

const OriginalResizeObserver = globalThis.ResizeObserver;

beforeAll(() => {
  globalThis.ResizeObserver = class ResizeObserver {
    /** Register one observed element for the inert XYFlow test shell. */
    observe(): void {}

    /** Stop observing one element for the inert XYFlow test shell. */
    unobserve(): void {}

    /** Release the inert XYFlow test observer. */
    disconnect(): void {}
  };
});

afterAll(() => {
  globalThis.ResizeObserver = OriginalResizeObserver;
});

/** Load one capability document with immutable system boundaries. */
function setupSingleCanvasDocument(): void {
  const document = createEmptyStudioDocument("agent-hierarchy", "Hierarchy", "document-hierarchy");
  useAgentBuilderDocumentStore.getState().replaceDocument(document, "revision-test");
}

beforeEach(setupSingleCanvasDocument);
afterEach(() => {
  cleanup();
  useAgentBuilderDocumentStore.getState().clear();
});

/** Render the Builder within its required XYFlow provider and a measurable viewport. */
function renderCanvas(): void {
  render(
    <AgentBuilderFlowProvider>
      <div style={{ width: 960, height: 640, display: "grid" }}>
        <BuilderCanvas catalog={null} />
      </div>
    </AgentBuilderFlowProvider>,
  );
}

describe("Builder single capability canvas", () => {
  it("keeps connected inputs visible and expands unused ports only when selected or connecting", () => {
    const data: BuilderNodeData = { label: "Reason", description: "Choose", kind: "capability", unavailable: false,
      diagnosticCount: 0, renderMode: "card", capabilityKind: "core", connectedPortIds: ["memory"], ports: [
        { id: "task", direction: "input", required: true, cardinality: "single", dataTypes: ["task_input"] },
        { id: "memory", direction: "input", required: false, cardinality: "single", dataTypes: ["memory_context"] },
        { id: "plan", direction: "input", required: false, cardinality: "single", dataTypes: ["plan_result"] },
      ] };
    const props = { id: "reason", data, type: "agentBuilder" as const, selected: false, dragging: false,
      zIndex: 0, isConnectable: true, selectable: true, deletable: true, draggable: true, positionAbsoluteX: 0, positionAbsoluteY: 0 };
    const view = render(<AgentBuilderFlowProvider><AgentBuilderNode {...props} /></AgentBuilderFlowProvider>);
    expect(screen.getByLabelText("输入连接 任务")).toBeTruthy();
    expect(screen.getByLabelText("输入连接 记忆上下文")).toBeTruthy();
    expect(screen.queryByLabelText("输入连接 计划")).toBeNull();
    view.rerender(<AgentBuilderFlowProvider><AgentBuilderNode {...props} selected /></AgentBuilderFlowProvider>);
    expect(screen.getByLabelText("输入连接 计划")).toBeTruthy();
    view.rerender(<AgentBuilderFlowProvider><AgentBuilderNode {...props} data={{ ...data, connectionFocus: true }} /></AgentBuilderFlowProvider>);
    expect(screen.getByLabelText("输入连接 计划")).toBeTruthy();
  });
  it("expands and restores the canvas without modifying the document", () => {
    renderCanvas();
    const before = useAgentBuilderDocumentStore.getState();
    fireEvent.click(screen.getByText("画布工具"));
    fireEvent.click(screen.getByRole("button", { name: "专注画布" }));
    expect(screen.getByRole("button", { name: "退出专注" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "退出专注" }));
    expect(useAgentBuilderDocumentStore.getState().document).toBe(before.document);
    expect(useAgentBuilderDocumentStore.getState().generation).toBe(before.generation);
    expect(useAgentBuilderDocumentStore.getState().dirty).toBe(before.dirty);
  });
  it("renders one graph with Input/Output and no raw-control view switch", () => {
    renderCanvas();

    expect(document.querySelectorAll(".react-flow")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /Agent 视图|完整视图|精确视图/i })).toBeNull();
    expect(screen.getByTestId("builder-node-input").dataset.renderMode).toBe("boundary");
    expect(screen.getByTestId("builder-node-output").dataset.renderMode).toBe("boundary");
    expect(screen.getByLabelText("输入连接 结束")).toBeTruthy();
    expect(screen.queryByText(/Router|Condition|DONE|FAIL/i)).toBeNull();
  });

  it("selects Output by its real canvas identity without making it deletable", () => {
    renderCanvas();

    fireEvent.click(screen.getByTestId("builder-node-output"));
    expect(useAgentBuilderDocumentStore.getState().selectedCanvasId).toBe("output");
    expect(useAgentBuilderDocumentStore.getState().selectedEdgeId).toBeNull();
  });

  it("keeps connection guidance contextual instead of occupying the idle canvas", () => {
    renderCanvas();
    expect(screen.queryByText(/点击输出圆点，可选择普通连接/)).toBeNull();
    expect(screen.queryByRole("button", { name: "↻ 下一轮反馈" })).toBeNull();
    expect(useAgentBuilderDocumentStore.getState().dirty).toBe(false);
  });
});
