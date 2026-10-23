import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  adaptRunJournal,
  createReplayProjection,
  finalizeRunEvidenceProjection,
  reduceReplayMoment,
  studioRunKeys,
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

/**
 * Connect a Run to verified journal projection and authoritative resource refresh.
 * @param input Exact Run/snapshot and optional deterministic transport dependencies.
 * @returns Session, shared evidence projection, and normalized journal evidence.
 * Lifecycle events invalidate server state; they never fabricate a Run resource.
 */
export function useLiveRunSession({
  run,
  snapshot,
  dependencies,
}: UseLiveRunSessionInput) {
  const queryClient = useQueryClient();
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
  const lifecycleSequence = session.events.reduce((latest, event) => (
    event.source === "service"
    && ["run.starting", "run.running", "run.cancellation_requested"].includes(event.kind)
      ? event.sequence
      : latest
  ), 0);

  useEffect(() => {
    // A committed lifecycle event can outlive the accepted create-response cache.
    // Refresh only when that verified fact is newer; ordinary activations and
    // heartbeat traffic must not cause a resource request per event.
    if (
      session.runId === run.runId
      && session.connection !== "integrity-error"
      && lifecycleSequence > run.eventHighWaterMark
      && run.lifecycle !== "terminal"
    ) {
      void queryClient.invalidateQueries({ queryKey: studioRunKeys.detail(run.runId), exact: true });
    }
  }, [lifecycleSequence, queryClient, run.eventHighWaterMark, run.lifecycle, run.runId, session.connection, session.runId]);
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
