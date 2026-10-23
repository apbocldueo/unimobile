import { describe, expect, it } from "vitest";
import { prepareTaskRun, stableTaskJson } from "./taskRunDraft";

const target = {
  agentId: "agent-1",
  revisionId: "revision-1",
  canonicalHash: `sha256:${"a".repeat(64)}`,
};

describe("ordinary task draft", () => {
  it("normalizes object order into one retry identity", () => {
    expect(stableTaskJson({ z: 1, a: { y: 2, x: 3 } })).toBe(
      '{"a":{"x":3,"y":2},"z":1}',
    );
    expect(prepareTaskRun(target, "safe-android", "  Open Settings  ", '{"b":2,"a":1}')).toEqual({
      task: { text: "Open Settings", metadata: { b: 2, a: 1 } },
      semanticIdentity: `${target.agentId}\u0000${target.revisionId}\u0000${target.canonicalHash}\u0000safe-android\u0000Open Settings\u0000{"a":1,"b":2}`,
    });
  });

  it("rejects empty tasks and non-object metadata", () => {
    expect(() => prepareTaskRun(target, "safe-android", " ", "{}")).toThrow(/请输入普通 Agent task/);
    expect(() => prepareTaskRun(target, "safe-android", "Open Settings", "[]")).toThrow(/根必须是对象/);
    expect(() => prepareTaskRun(target, "safe-android", "Open Settings", "{" )).toThrow(/有效 JSON/);
  });
});
