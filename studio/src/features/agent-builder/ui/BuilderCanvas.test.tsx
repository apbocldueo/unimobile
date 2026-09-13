import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { useAgentBuilderDocumentStore } from "../model/builder.store";
import { AgentBuilderFlowProvider } from "./AgentBuilderFlowProvider";
import { BuilderCanvas } from "./BuilderCanvas";

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
  it("renders one graph with Input/Output and no raw-control view switch", () => {
    renderCanvas();

    expect(document.querySelectorAll(".react-flow")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /Agent 视图|完整视图|精确视图/i })).toBeNull();
    expect(screen.getByTestId("builder-node-input").dataset.renderMode).toBe("boundary");
    expect(screen.getByTestId("builder-node-output").dataset.renderMode).toBe("boundary");
    expect(screen.queryByText(/Router|Condition|DONE|FAIL/i)).toBeNull();
  });

  it("selects Output by its real canvas identity without making it deletable", () => {
    renderCanvas();

    fireEvent.click(screen.getByTestId("builder-node-output"));
    expect(useAgentBuilderDocumentStore.getState().selectedCanvasId).toBe("output");
    expect(useAgentBuilderDocumentStore.getState().selectedEdgeId).toBeNull();
  });
});
