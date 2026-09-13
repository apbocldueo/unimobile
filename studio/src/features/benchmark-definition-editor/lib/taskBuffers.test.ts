import { describe, expect, it } from "vitest";
import { benchmarkAuthoringDocumentFixture } from "@/entities/benchmark-authoring";
import {
  createTaskBuffers,
  inspectTaskBuffer,
  isTaskBufferUnapplied,
  parseTaskBuffer,
  taskBuffersBlockSave,
} from "@/features/benchmark-definition-editor";

describe("task buffers", () => {
  it("reconstructs one deterministic applied buffer per task file", () => {
    const buffers = createTaskBuffers(benchmarkAuthoringDocumentFixture());
    const buffer = buffers["tasks/test.json"];
    expect(buffer?.text).toContain('"fixture-task"');
    expect(buffer?.text).toBe(buffer?.appliedText);
    expect(taskBuffersBlockSave(buffers)).toBe(false);
  });

  it("detects unapplied valid text and reports invalid syntax locally", () => {
    const buffer = createTaskBuffers(
      benchmarkAuthoringDocumentFixture(),
    )["tasks/test.json"]!;
    const valid = { ...buffer, text: "[]\n" };
    expect(inspectTaskBuffer(valid).tasks).toEqual([]);
    expect(isTaskBufferUnapplied(valid)).toBe(true);
    const invalid = { ...buffer, text: "[\n  {" };
    const result = inspectTaskBuffer(invalid);
    expect(result.tasks).toBeNull();
    expect(result.error?.message).toBeTruthy();
  });

  it("requires an array and rejects unsafe non-finite clone values", () => {
    expect(() => parseTaskBuffer('{"id":"not-array"}')).toThrow(/array/);
    expect(parseTaskBuffer('[{"score": 1}]')).toEqual([{ score: 1 }]);
  });
});
