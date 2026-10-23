import { describe, expect, it } from "vitest";
import { resolveAgentTitle } from "./WorkbenchChrome";

describe("workbench Agent title", () => {
  it("uses human-readable metadata without changing the execution identity fallback", () => {
    expect(resolveAgentTitle("  Research Agent  ", "agent-authoritative")).toBe(
      "Research Agent",
    );
    expect(resolveAgentTitle("", "agent-1")).toBe("Agent agent-1");
    expect(resolveAgentTitle(undefined, "")).toBe("Agent 名称不可用");
  });
});
