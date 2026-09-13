import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { benchmarkExperimentKeys } from "@/entities/benchmark-experiment";
import {
  BenchmarkEventSession,
  type BenchmarkEventSessionDependencies,
  type BenchmarkEventSessionSnapshot,
} from "./benchmarkEventSession";
import { ResourceRefreshCoalescer } from "./resourceRefreshCoalescer";

type UseBenchmarkEventSessionInput = {
  experimentId: string;
  enabled: boolean;
  dependencies?: Partial<
    Omit<BenchmarkEventSessionDependencies, "onChange" | "onProgress">
  >;
};

/** Build the detached initial transport state for one Experiment route. */
function initialSession(experimentId: string): BenchmarkEventSessionSnapshot {
  return {
    experimentId,
    connection: "idle",
    cursor: 0,
    highWaterMark: 0,
    events: [],
    lastFreshAt: null,
    integrityError: null,
    deliveryMode: "backfill",
    deliveryVersion: 0,
  };
}

/** Connect durable journal progress to coalesced authoritative query refresh. */
export function useBenchmarkEventSession({
  experimentId,
  enabled,
  dependencies,
}: UseBenchmarkEventSessionInput) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<BenchmarkEventSessionSnapshot>(() =>
    initialSession(experimentId),
  );
  const controller = useRef<BenchmarkEventSession | null>(null);
  const dependencyRef = useRef(dependencies);
  dependencyRef.current = dependencies;

  useEffect(() => {
    setSession(initialSession(experimentId));
    if (!enabled || experimentId.length === 0) return undefined;
    const refresh = new ResourceRefreshCoalescer({
      refresh: async () => {
        await Promise.all([
          queryClient.invalidateQueries({
            queryKey: benchmarkExperimentKeys.detail(experimentId),
          }),
          queryClient.invalidateQueries({
            queryKey: benchmarkExperimentKeys.taskRuns(experimentId),
          }),
        ]);
      },
    });
    const next = new BenchmarkEventSession(experimentId, {
      ...dependencyRef.current,
      onChange: setSession,
      onProgress: () => refresh.request(),
    });
    controller.current = next;
    void next.start();
    return () => {
      controller.current = null;
      next.stop();
      refresh.dispose();
    };
  }, [enabled, experimentId, queryClient]);

  /** Retry from the verified cursor without changing resource or UI facts. */
  const retry = useCallback(() => {
    void controller.current?.retry();
  }, []);

  return { session, retry };
}
