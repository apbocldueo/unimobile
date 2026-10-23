import { describe, expect, it } from "vitest";
import {
  parseStudioRunEvent,
  type StudioRunResource,
} from "@/entities/run";
import { decideTerminalHandoff } from "./terminalHandoff";

const runId = `run-${"a".repeat(32)}`;
const hash = `sha256:${"b".repeat(64)}`;

/** Build one authoritative terminal resource for an outcome variant. */
function terminalRun(
  status: string,
  replayAvailability: StudioRunResource["replayAvailability"] = "available",
): StudioRunResource {
  return {
    schemaVersion: 1,
    runId,
    clientRequestId: "request-1",
    agentId: "agent-1",
    revisionId: "revision-1",
    canonicalHash: hash,
    task: { text: "Open Settings", metadata: {} },
    deviceProfileId: "local-android",
    lifecycle: "terminal",
    cancellationRequested: status === "cancelled",
    resultAvailability: "available",
    result: {
      status,
      kernelStatus: status,
      errorCode: status === "success" ? "" : `runtime.${status}`,
      error: status === "success" ? "" : status,
      stepCount: 1,
      activationCount: 1,
      interactionCount: 0,
      usage: {},
      finalOutput: null,
      artifactNamespace: "",
    },
    replayAvailability,
    eventHighWaterMark: 4,
    acceptedAt: 1,
    startedAt: 2,
    updatedAt: 4,
    terminalAt: 4,
    storageWarnings: [],
  };
}

/** Build the unique terminal journal fact. */
function terminalEvent(status: string) {
  return parseStudioRunEvent({
    schemaVersion: 1,
    eventId: "service-run-terminal",
    timestamp: 4,
    source: "result",
    kind: "run.terminal",
    payload: { result: { status }, replayAvailability: "available" },
    nodePath: "",
    activationId: "",
    runId,
    sequence: 4,
    fingerprint: hash,
  });
}

describe("terminal Replay handoff", () => {
  it.each([
    "success",
    "failure",
    "cancelled",
    "step_limit",
    "device_failure",
  ])("navigates all verified outcome variants when Replay is available", (status) => {
    expect(
      decideTerminalHandoff(terminalRun(status), terminalEvent(status)),
    ).toEqual({ kind: "replay", runId });
  });

  it.each(["not_captured", "missing", "corrupt"] as const)(
    "keeps an inspectable terminal page when Replay is %s",
    (availability) => {
      expect(
        decideTerminalHandoff(
          terminalRun("failure", availability),
          terminalEvent("failure"),
        ),
      ).toEqual({ kind: "stay", reason: `Replay is ${availability}` });
    },
  );

  it("waits for authoritative terminal persistence and rejects disagreement", () => {
    const running = {
      ...terminalRun("success"),
      lifecycle: "running",
      result: null,
      terminalAt: null,
      resultAvailability: "not_captured",
    } as StudioRunResource;
    expect(decideTerminalHandoff(running, terminalEvent("success")).kind).toBe(
      "pending",
    );
    expect(
      decideTerminalHandoff(
        terminalRun("failure"),
        terminalEvent("success"),
      ),
    ).toEqual({
      kind: "stay",
      reason: "terminal event and RunResult disagree",
    });
  });
});
