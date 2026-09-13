import { useEffect, useMemo, useRef, useState } from "react";
import {
  adaptRunJournal,
  createReplayProjection,
  finalizeRunEvidenceProjection,
  reduceReplayMoment,
  type RunSnapshot,
  type StudioRunResource,
} from "@/entities/run";
import type { EvidenceAvailability } from "@/entities/run";
import { HighlightQueue } from "./highlightQueue";
import {
  LiveRunSession,
  type LiveRunSessionDependencies,
  type LiveRunSessionSnapshot,
} from "./liveRunSession";
import { useLiveRunUiStore } from "./liveRunUi.store";

type UseLiveRunSessionInput = {
  run: StudioRunResource;
  snapshot: RunSnapshot;
  dependencies?: Partial<Omit<LiveRunSessionDependencies, "onChange">>;
};

const SCREENSHOT_PENDING: Record<string, EvidenceAvailability> = {
  screenshots: { state: "available", reasonCode: "", detail: "" },
};

/** Connect one Run to the shared reducer while keeping UI selection separate. */
export function useLiveRunSession({
  run,
  snapshot,
  dependencies,
}: UseLiveRunSessionInput) {
  const [session, setSession] = useState<LiveRunSessionSnapshot>({
    runId: run.runId,
    connection: "idle",
    cursor: 0,
    highWaterMark: 0,
    events: [],
    lastFreshAt: null,
    integrityError: null,
    deliveryMode: "backfill",
    deliveryVersion: 0,
  });
  const queue = useRef<HighlightQueue | null>(null);
  const initialize = useLiveRunUiStore((state) => state.initialize);
  const setVisualActivation = useLiveRunUiStore(
    (state) => state.setVisualActivation,
  );
  const notifyFailure = useLiveRunUiStore((state) => state.notifyFailure);

  const evidence = useMemo(
    () => adaptRunJournal(session.events),
    [session.events],
  );
  const projection = useMemo(() => {
    const replayResult = {
      status: run.result?.status ?? run.lifecycle,
      kernelStatus: run.result?.kernelStatus ?? "",
      error: run.result?.error ?? "",
      stepCount: run.result?.stepCount ?? 0,
      activationCount: run.result?.activationCount ?? 0,
      interactionCount: run.result?.interactionCount ?? 0,
      usage: run.result?.usage ?? {},
    };
    let current = createReplayProjection(
      snapshot,
      replayResult,
      null,
      evidence.observations,
      evidence.actions,
      SCREENSHOT_PENDING,
      session.connection === "integrity-error" ? "partial" : "complete",
    );
    for (const moment of evidence.moments) {
      current = reduceReplayMoment(current, moment);
    }
    return run.result
      ? finalizeRunEvidenceProjection(current, replayResult, null)
      : current;
  }, [
    evidence.actions,
    evidence.moments,
    evidence.observations,
    run.lifecycle,
    run.result,
    session.connection,
    snapshot,
  ]);

  useEffect(() => {
    initialize(run.runId);
    queue.current = new HighlightQueue({ onChange: setVisualActivation });
    const controller = new LiveRunSession(run.runId, {
      ...dependencies,
      onChange: setSession,
    });
    void controller.start();
    return () => {
      controller.stop();
      queue.current?.dispose();
      queue.current = null;
    };
  }, [dependencies, initialize, run.runId, setVisualActivation]);

  useEffect(() => {
    const visualQueue = queue.current;
    if (!visualQueue) return;
    const failure = projection.failureTargets.at(-1);
    if (failure?.activationId) {
      notifyFailure(failure.activationId);
      visualQueue.preempt(failure.activationId);
      return;
    }
    if (session.connection === "terminal") {
      visualQueue.preempt(projection.currentActivationId);
      return;
    }
    if (session.deliveryMode === "backfill") {
      visualQueue.restore(projection.currentActivationId);
    } else if (projection.currentActivationId) {
      visualQueue.enqueue(projection.currentActivationId);
    }
  }, [
    notifyFailure,
    projection.currentActivationId,
    projection.failureTargets,
    session.connection,
    session.deliveryMode,
    session.deliveryVersion,
  ]);

  return { session, projection, evidence };
}
