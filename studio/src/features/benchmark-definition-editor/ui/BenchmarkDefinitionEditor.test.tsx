import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { benchmarkAuthoringRevisionFixture } from "@/entities/benchmark-authoring";
import {
  BenchmarkDefinitionEditor,
  benchmarkDefinitionEditorStatus,
  useBenchmarkDefinitionEditorStore,
} from "@/features/benchmark-definition-editor";

beforeEach(() => {
  useBenchmarkDefinitionEditorStore.getState().clear();
  useBenchmarkDefinitionEditorStore
    .getState()
    .hydrate(benchmarkAuthoringRevisionFixture());
});

afterEach(cleanup);

describe("Benchmark definition editor", () => {
  it("focuses an exact public member and preserves a safe open-path breadcrumb", () => {
    useBenchmarkDefinitionEditorStore.getState().focusMember(
      "task:tasks/test.json",
      [0, "x_extension", "nested"],
    );
    render(
      <BenchmarkDefinitionEditor revision={benchmarkAuthoringRevisionFixture()} />,
    );
    expect(screen.getByLabelText("Task JSON tasks/test.json")).toBeTruthy();
    expect(screen.getByText("[0].x_extension.nested")).toBeTruthy();
    expect(useBenchmarkDefinitionEditorStore.getState().selectedMember).toBe(
      "task:tasks/test.json",
    );
  });

  it("edits known manifest and split fields while preserving extensions", () => {
    render(
      <BenchmarkDefinitionEditor revision={benchmarkAuthoringRevisionFixture()} />,
    );
    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Edited title" },
    });
    fireEvent.change(screen.getByLabelText("test task files"), {
      target: { value: "tasks/test.json, tasks/extra.json" },
    });
    const manifest =
      useBenchmarkDefinitionEditorStore.getState().workingDocument?.manifest
        .document;
    expect(manifest?.title).toBe("Edited title");
    expect(manifest?.x_extension).toEqual({ nested: ["must", "survive"] });
    expect(
      (
        manifest?.splits as Record<
          string,
          { files: string[]; extension_split: { keep: boolean } }
        >
      ).test,
    ).toMatchObject({
      files: ["tasks/test.json", "tasks/extra.json"],
      extension_split: { keep: true },
    });
  });

  it("keeps invalid and unapplied task JSON local until explicit apply", () => {
    render(
      <BenchmarkDefinitionEditor revision={benchmarkAuthoringRevisionFixture()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /tasks\/test\.json/ }));
    const editor = screen.getByLabelText("Task JSON tasks/test.json");
    fireEvent.change(editor, { target: { value: "[" } });
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(
      benchmarkDefinitionEditorStatus(
        useBenchmarkDefinitionEditorStore.getState(),
      ).saveable,
    ).toBe(false);
    fireEvent.change(editor, { target: { value: "[]" } });
    expect(screen.getByText(/尚未 Apply/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Apply JSON" }));
    expect(
      useBenchmarkDefinitionEditorStore.getState().workingDocument?.taskFiles[0]
        ?.tasks,
    ).toEqual([]);
  });

  it("edits Protocol/inline ground truth and exposes resources as metadata only", () => {
    render(
      <BenchmarkDefinitionEditor revision={benchmarkAuthoringRevisionFixture()} />,
    );
    const groundTruth = screen
      .getByText("Inline ground truth definition")
      .closest("section");
    if (!groundTruth) throw new Error("inline ground truth section missing");
    fireEvent.change(
      within(groundTruth).getByRole("textbox"),
      { target: { value: '{"inline":{"kind":"json","value":{"score":7}}}' } },
    );
    fireEvent.click(within(groundTruth).getByRole("button", { name: "Apply field" }));
    expect(
      useBenchmarkDefinitionEditorStore.getState().workingDocument?.manifest
        .document.ground_truth,
    ).toEqual({ inline: { kind: "json", value: { score: 7 } } });

    fireEvent.click(
      screen.getByRole("button", { name: /protocols\/default\.yaml/ }),
    );
    fireEvent.change(screen.getByLabelText("seed"), {
      target: { value: "42" },
    });
    expect(
      useBenchmarkDefinitionEditorStore.getState().workingDocument
        ?.protocolFiles[0]?.document.seed,
    ).toBe(42);

    fireEvent.click(screen.getByRole("button", { name: /assets\/screen\.png/ }));
    expect(screen.getByText(/Metadata only/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: /download|preview/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /upload|replace|remove/i })).toBeNull();
  });
});
