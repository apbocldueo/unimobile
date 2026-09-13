import { describe, expect, it } from "vitest";
import {
  parseCreateStudioRunResponse,
  parseDebugPayload,
  parseStudioRunEventPage,
  parseStudioRunResource,
} from "@/entities/run";

const runId = `run-${"a".repeat(32)}`;
const artifactId = `artifact-${"b".repeat(32)}`;
const fingerprint = `sha256:${"c".repeat(64)}`;

/** Build one strict nonterminal Run fixture. */
function runningResource() {
  return {
    schemaVersion: 1,
    runId,
    clientRequestId: "launch-request",
    agentId: "agent-1",
    revisionId: "revision-1",
    canonicalHash: fingerprint,
    task: { text: "Open Settings", metadata: {} },
    deviceProfileId: "local-android",
    lifecycle: "running",
    cancellationRequested: false,
    resultAvailability: "not_captured",
    result: null,
    replayAvailability: "not_captured",
    eventHighWaterMark: 2,
    acceptedAt: 1,
    startedAt: 2,
    updatedAt: 3,
    terminalAt: null,
    storageWarnings: [],
  };
}

/** Build one strict journal envelope fixture. */
function event(sequence: number) {
  return {
    schemaVersion: 1,
    eventId: `event-${sequence}`,
    timestamp: sequence,
    source: "runtime",
    kind: "complete",
    payload: {},
    runtimeSequence: sequence,
    nodePath: "planner",
    activationId: "activation-1",
    interactionStep: 0,
    runId,
    sequence,
    fingerprint,
  };
}

describe("live Run schemas", () => {
  it("parses valid nonterminal, terminal, and create resources", () => {
    expect(parseStudioRunResource(runningResource()).lifecycle).toBe("running");
    const terminal = {
      ...runningResource(),
      lifecycle: "terminal",
      resultAvailability: "available",
      result: {
        status: "success",
        kernelStatus: "success",
        errorCode: "",
        error: "",
        stepCount: 2,
        activationCount: 3,
        interactionCount: 1,
        usage: {},
        finalOutput: null,
        artifactNamespace: "",
      },
      terminalAt: 4,
    };
    expect(parseStudioRunResource(terminal).result?.status).toBe("success");
    expect(parseCreateStudioRunResponse({ ...runningResource(), created: true }).created).toBe(true);
  });

  it("rejects unknown fields and invalid lifecycle/result combinations", () => {
    expect(() =>
      parseStudioRunResource({ ...runningResource(), storagePath: "/tmp/run" }),
    ).toThrow(/not supported/);
    expect(() =>
      parseStudioRunResource({
        ...runningResource(),
        lifecycle: "terminal",
        terminalAt: 4,
      }),
    ).toThrow(/requires result/);
    expect(() =>
      parseStudioRunResource({
        ...runningResource(),
        result: {
          status: "success",
          kernelStatus: "",
          errorCode: "",
          error: "",
          stepCount: 0,
          activationCount: 0,
          interactionCount: 0,
          usage: {},
          finalOutput: null,
          artifactNamespace: "",
        },
      }),
    ).toThrow(/nonterminal/);
  });

  it("rejects unsafe JSON and invalid event page cursors", () => {
    expect(() =>
      parseStudioRunResource({
        ...runningResource(),
        task: { text: "x", metadata: { invalid: Number.NaN } },
      }),
    ).toThrow(/finite/);
    expect(() =>
      parseStudioRunEventPage({
        schemaVersion: 1,
        runId,
        items: [event(1), event(3)],
        nextCursor: 3,
        highWaterMark: 3,
        terminal: false,
      }),
    ).toThrow(/not continuous/);
    expect(() =>
      parseStudioRunEventPage({
        schemaVersion: 1,
        runId,
        items: [event(1)],
        nextCursor: 2,
        highWaterMark: 1,
        terminal: false,
      }),
    ).toThrow(/exceeds/);
  });

  it("parses typed Debug evidence and degrades legacy payloads explicitly", () => {
    const base = {
      schemaVersion: 1,
      debugId: "debug-1",
      runId,
      nodePath: "planner",
      activationId: "activation-1",
      componentIdentity: "fixture:planner@1.0.0",
      role: "zhixing.role.planner",
      stage: "complete",
      task: "Open Settings",
      inputSummary: {},
      outputSummary: {},
      durationMs: 10,
      error: "",
      usage: {},
      artifactIds: [artifactId],
      availability: { modelResponse: "available" },
      diagnostics: [],
    };
    const legacy = parseDebugPayload(base);
    expect(legacy.artifactIds).toEqual([artifactId]);
    expect(legacy.evidenceRefs).toEqual({});

    const typed = parseDebugPayload({
      ...base,
      evidenceRefs: {
        modelResponse: {
          schemaVersion: 1,
          kind: "model_response",
          artifactId,
          availability: "available",
          contentType: "text/plain",
          size: 12,
          originalSize: null,
          sha256: fingerprint,
          provenance: "component_invocation",
          causalIdentity: "debug-1",
          hidden: false,
        },
        prompt: {
          schemaVersion: 1,
          kind: "sensitive_prompt",
          availability: "hidden",
          contentType: "",
          size: 0,
          originalSize: null,
          sha256: null,
          provenance: "component_invocation",
          causalIdentity: "debug-1",
          hidden: true,
        },
      },
    });
    expect(typed.evidenceRefs.modelResponse.artifactId).toBe(artifactId);
    expect(typed.evidenceRefs.prompt.artifactId).toBeNull();
    expect(() =>
      parseDebugPayload({
        ...base,
        evidenceRefs: {
          prompt: {
            ...typed.evidenceRefs.prompt,
            artifactId,
          },
        },
      }),
    ).toThrow(/hidden evidence/);
  });
});
