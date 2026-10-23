import type {
  StudioRunEvent,
  StudioRunResource,
} from "@/entities/run";
import { isRecord } from "@/shared/lib";

export type TerminalHandoffDecision =
  | { kind: "replay"; runId: string }
  | { kind: "stay"; reason: string }
  | { kind: "pending"; reason: string };

/** Verify terminal event/resource consistency before Replay navigation. */
export function decideTerminalHandoff(
  run: StudioRunResource,
  terminalEvent: StudioRunEvent,
): TerminalHandoffDecision {
  if (
    terminalEvent.runId !== run.runId
    || terminalEvent.kind !== "run.terminal"
  ) {
    return { kind: "stay", reason: "terminal event identity mismatch" };
  }
  if (run.lifecycle !== "terminal" || !run.result) {
    return { kind: "pending", reason: "authoritative Run is not terminal yet" };
  }
  const payloadResult = isRecord(terminalEvent.payload)
    && isRecord(terminalEvent.payload.result)
    ? terminalEvent.payload.result
    : null;
  const eventStatus =
    payloadResult && typeof payloadResult.status === "string"
      ? payloadResult.status
      : null;
  if (eventStatus !== null && eventStatus !== run.result.status) {
    return { kind: "stay", reason: "terminal event and RunResult disagree" };
  }
  if (run.replayAvailability === "available") {
    return { kind: "replay", runId: run.runId };
  }
  return {
    kind: "stay",
    reason: `Replay is ${run.replayAvailability}`,
  };
}
