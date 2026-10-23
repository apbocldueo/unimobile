import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { useAgentBuilderDocumentStore as store } from "../model/builder.store";
import { BuilderHistoryControls } from "./BuilderHistoryControls";

afterEach(() => { cleanup(); store.getState().clear(); });

/** Mount scoped controls after an undoable edit and return the workspace target. */
function setup() {
  store.getState().replaceDocument(createEmptyStudioDocument("a", "A", "d"), "r1");
  store.getState().updateCurrentDocument((doc) => ({ ...doc, name: "Edited" }));
  render(<><div aria-label="Builder workspace" tabIndex={0}>
    <BuilderHistoryControls /><textarea aria-label="Config" /><input aria-label="Name" />
    <div contentEditable aria-label="Rich editor" /><div role="dialog"><button>Modal action</button></div>
  </div><button>Outside</button></>);
  return screen.getByLabelText("Builder workspace");
}

describe("Builder history controls", () => {
  it("keeps undo available after deleting focus but relinquishes body clicks outside", () => {
    const root = setup();
    fireEvent.pointerDown(root);
    fireEvent.keyDown(document.body, { key: "z", metaKey: true });
    expect(store.getState().document?.name).toBe("A");
    fireEvent.keyDown(document.body, { key: "z", metaKey: true, shiftKey: true });
    expect(store.getState().document?.name).toBe("Edited");
    fireEvent.pointerDown(document.body);
    expect(fireEvent.keyDown(document.body, { key: "z", metaKey: true })).toBe(true);
    expect(store.getState().document?.name).toBe("Edited");
  });
  it("supports toolbar, Mac and Windows commands and disabled redo branches", () => {
    const root = setup();
    fireEvent.click(screen.getByRole("button", { name: "撤销" }));
    expect(store.getState().document?.name).toBe("A");
    fireEvent.keyDown(root, { key: "z", metaKey: true, shiftKey: true });
    expect(store.getState().document?.name).toBe("Edited");
    fireEvent.keyDown(root, { key: "z", ctrlKey: true });
    fireEvent.keyDown(root, { key: "y", ctrlKey: true });
    expect(store.getState().document?.name).toBe("Edited");
    expect((screen.getByRole("button", { name: "重做" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("does not steal native text, modal, outside or composing shortcuts", () => {
    const root = setup();
    const generation = store.getState().generation;
    for (const target of [screen.getByLabelText("Config"), screen.getByLabelText("Name"), screen.getByLabelText("Rich editor"), screen.getByRole("button", { name: "Modal action" }), screen.getByRole("button", { name: "Outside" })]) {
      expect(fireEvent.keyDown(target, { key: "z", metaKey: true })).toBe(true);
    }
    fireEvent.keyDown(root, { key: "z", ctrlKey: true, isComposing: true });
    expect(store.getState().generation).toBe(generation);
  });
});
