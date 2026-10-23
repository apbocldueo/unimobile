import { describe, expect, it } from "vitest";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { describeRunStop, launchSummary } from "./launchSummary";
import { parseReplayListItem, type RunSnapshot } from "./run.schema";

/** Build a launch snapshot with a declared LLM and secret-bearing dependency. */
function snapshot(): RunSnapshot {
  const document = createEmptyStudioDocument("agent-1", "Test", "document-1");
  document.capabilities = [{ canvasId: "reason", logicalId: "reasoning", family: "reasoning", lifecycle: "per_step", implementation: { policy: "single", candidates: [{ namespace: "reasoning", name: "test", version: "1", params: {}, dependencies: { llm: { params: { model: "fixture-model", api_key: "secret-canary", base_url: "private-endpoint" } } } }] } }];
  return { agentId: "agent-1", revisionId: "revision-1", canonicalHash: null, contractVersion: "1.1", graphStatus: "available", agentGraph: null, graphNodes: [], graphEdges: [], presentation: null, sourceMap: [], capabilityDocument: document, providerIdentities: [] };
}

describe("user-facing run facts", () => {
  it("shows only model and budget fields and leaves unavailable legacy facts explicit", () => {
    const value = snapshot();
    const summary = launchSummary(value);
    expect(summary.models).toEqual(["reasoning · fixture-model"]);
    expect(JSON.stringify(summary)).not.toMatch(/secret-canary|private-endpoint/);
    expect(launchSummary({ ...value, capabilityDocument: null }).maxSteps).toBeNull();
  });
  it("translates only a known stopping condition without inventing a root cause", () => {
    expect(describeRunStop("Generalized feedback exhausted its iteration budget")).toContain("反馈循环次数已用尽");
    expect(describeRunStop("unknown fixture error")).toBe("unknown fixture error");
  });
  it("accepts legacy rows and rejects malformed or oversized presentation metadata", () => {
    const row = { runId: "run-fixture", agentId: "agent-1", agentStatus: "success", provenance: "fake_contract_fixture", integrityState: "complete", evidenceCompleteness: 100, importedAt: 1 };
    expect(parseReplayListItem(row).agentName).toBeNull();
    expect(parseReplayListItem({ ...row, agentName: "测试", taskSummary: "📱".repeat(500) }).taskSummary).toHaveLength(1000);
    expect(() => parseReplayListItem({ ...row, agentName: 12 })).toThrow();
    expect(() => parseReplayListItem({ ...row, taskSummary: "x".repeat(501) })).toThrow();
  });
});
