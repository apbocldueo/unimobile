import { describe, expect, it } from "vitest";
import { createReplayEnvelopeFixture } from "@/entities/replay";
import type { AgentRevision } from "@/entities/agent-revision";
import { createEmptyStudioDocument } from "@/entities/agent-graph";
import { decideReplayRerunEligibility } from "./replayRerunEligibility";

const hash = `sha256:${"c".repeat(64)}`;

/** Build one exact valid local revision for eligibility tests. */
function revision(): AgentRevision {
  const envelope = createReplayEnvelopeFixture();
  return {
    revisionId: "revision-1",
    agentId: "research-agent",
    ordinal: 1,
    parentRevisionId: null,
    document: createEmptyStudioDocument("research-agent", "Research Agent", "document-1"),
    compileSnapshot: {
      status: "valid",
      diagnostics: [],
      sourceMap: [],
      agentGraph: typeof envelope.snapshot.agentGraph === "object"
        && envelope.snapshot.agentGraph !== null
        && !Array.isArray(envelope.snapshot.agentGraph)
          ? envelope.snapshot.agentGraph
          : { nodes: [], edges: [] },
      canonicalHash: hash,
    },
    createdAt: 1,
  };
}

describe("Replay ordinary rerun eligibility", () => {
  it("accepts only an exact native ordinary revision", () => {
    const envelope = createReplayEnvelopeFixture({
      provenance: "native_studio_run",
      benchmark: null,
    });
    envelope.snapshot.agentId = "research-agent";
    envelope.snapshot.revisionId = "revision-1";
    envelope.snapshot.canonicalHash = hash;
    expect(decideReplayRerunEligibility(envelope, revision())).toEqual({
      kind: "eligible",
      target: {
        agentId: "research-agent",
        revisionId: "revision-1",
        canonicalHash: hash,
      },
    });
  });

  it("fails closed for Benchmark, imported, missing, and hash-mismatched sources", () => {
    const envelope = createReplayEnvelopeFixture();
    expect(decideReplayRerunEligibility(envelope, revision()).kind).toBe("read_only");
    envelope.provenance = "native_studio_run";
    expect(decideReplayRerunEligibility(envelope, revision()).kind).toBe("read_only");
    envelope.benchmark = null;
    envelope.snapshot.agentId = "research-agent";
    envelope.snapshot.revisionId = "revision-1";
    envelope.snapshot.canonicalHash = hash;
    expect(decideReplayRerunEligibility(envelope, null).kind).toBe("read_only");
    const mismatched = revision();
    mismatched.compileSnapshot.canonicalHash = `sha256:${"d".repeat(64)}`;
    expect(decideReplayRerunEligibility(envelope, mismatched)).toMatchObject({
      kind: "read_only",
      reason: expect.stringContaining("canonical identity"),
    });
  });
});
