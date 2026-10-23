import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  loadBenchmarkPublicationManifest,
  prepareBenchmarkExportTarget,
  summarizeBenchmarkPublicationManifest,
  type BenchmarkPublicationManifestSummary,
} from "@/entities/benchmark-report";
import {
  StudioHeadContractError,
  type StudioHeadResponse,
} from "@/shared/api";
import {
  projectBenchmarkExportMaterials,
  type BenchmarkExportMaterial,
  type BenchmarkExportMaterialProjection,
} from "./benchmarkExportMaterials";
import type {
  BenchmarkExportMetadataSnapshot,
} from "./useBenchmarkExperimentReport";
import type {
  BenchmarkArtifactInventoryPage,
} from "@/entities/benchmark-report";

export type BenchmarkExportPrepareFailure =
  | "stale-target"
  | "scope-conflict"
  | "unavailable"
  | "header-conflict"
  | "request-failed";

export type BenchmarkExportPrepareState =
  | { kind: "idle" }
  | { kind: "refreshing-metadata" }
  | { kind: "verifying-head" }
  | {
      kind: "ready-for-handoff";
      item: BenchmarkExportMaterial["item"];
      head: StudioHeadResponse;
    }
  | {
      kind: "handed-off";
      item: BenchmarkExportMaterial["item"];
    }
  | {
      kind: "failed";
      failure: BenchmarkExportPrepareFailure;
      availability: string | null;
      retryable: boolean;
    };

export type BenchmarkExportManifestState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; summary: BenchmarkPublicationManifestSummary }
  | { kind: "failed"; retryable: boolean };

export type BenchmarkExportRefresh = () => Promise<
  BenchmarkExportMetadataSnapshot
>;

type InFlightPrepare = {
  controller: AbortController;
  promise: Promise<void>;
  generation: number;
};

/** Collect every material, including unavailable facts, for exact refresh lookup. */
function allMaterials(
  projection: BenchmarkExportMaterialProjection,
): BenchmarkExportMaterial[] {
  return [
    projection.experimentReport,
    projection.experimentBundle,
    projection.publicationManifest,
    ...Array.from(projection.taskMaterials.values()).flat(),
    ...projection.otherEvidence,
    ...projection.unavailable,
  ].filter((item): item is BenchmarkExportMaterial => item !== null);
}

/** Classify one refreshed persisted target without exposing transport details. */
function refreshedFailure(
  original: BenchmarkExportMaterial,
  snapshot: BenchmarkExportMetadataSnapshot,
): BenchmarkExportPrepareState {
  let projection: BenchmarkExportMaterialProjection;
  try {
    projection = projectBenchmarkExportMaterials(
      snapshot.experiment.experimentId,
      snapshot.inventory,
    );
  } catch {
    return {
      kind: "failed",
      failure: "scope-conflict",
      availability: null,
      retryable: true,
    };
  }
  const refreshed = allMaterials(projection).find(
    (material) =>
      material.item.descriptor.artifactId
      === original.item.descriptor.artifactId,
  );
  if (!refreshed) {
    return {
      kind: "failed",
      failure: "unavailable",
      availability: "missing",
      retryable: true,
    };
  }
  if (refreshed.key !== original.key) {
    return {
      kind: "failed",
      failure: refreshed.item.links.content === null
        ? "unavailable"
        : "stale-target",
      availability: refreshed.item.descriptor.availability,
      retryable: true,
    };
  }
  return {
    kind: "failed",
    failure: "request-failed",
    availability: refreshed.item.descriptor.availability,
    retryable: true,
  };
}

/** Own disposable Report-local Export projection, preparation, and manifest state.
 *
 * Args:
 *   experimentId: Current durable Experiment identity.
 *   inventory: Current closed inventory metadata, never artifact bytes.
 *   taskRunIds: Current durable TaskRun identities for manifest scope checks.
 *   refreshMetadata: Callback that refetches Experiment, TaskRuns, and inventory.
 *
 * Returns:
 *   Fail-closed projection and short-lived user-driven Export actions.
 */
export function useBenchmarkExport(
  experimentId: string,
  inventory: BenchmarkArtifactInventoryPage | null,
  taskRunIds: readonly string[],
  refreshMetadata: BenchmarkExportRefresh,
) {
  const [prepareStates, setPrepareStates] = useState<
    Map<string, BenchmarkExportPrepareState>
  >(new Map());
  const [manifestState, setManifestState] =
    useState<BenchmarkExportManifestState>({ kind: "idle" });
  const inFlight = useRef(new Map<string, InFlightPrepare>());
  const generation = useRef(0);
  const manifestRequest = useRef<AbortController | null>(null);

  const projectionResult = useMemo(() => {
    if (!inventory) return { projection: null, error: null };
    try {
      return {
        projection: projectBenchmarkExportMaterials(experimentId, inventory),
        error: null,
      };
    } catch {
      return {
        projection: null,
        error: "Artifact inventory cannot be closed safely for Export.",
      };
    }
  }, [experimentId, inventory]);

  /** Commit one target state without mutating sibling materials. */
  const commitState = useCallback(
    (key: string, state: BenchmarkExportPrepareState) => {
      setPrepareStates((current) => {
        const next = new Map(current);
        next.set(key, state);
        return next;
      });
    },
    [],
  );

  /** Abort and release all transient Export work. */
  const reset = useCallback(() => {
    generation.current += 1;
    for (const entry of inFlight.current.values()) {
      entry.controller.abort();
    }
    inFlight.current.clear();
    manifestRequest.current?.abort();
    manifestRequest.current = null;
    setPrepareStates(new Map());
    setManifestState({ kind: "idle" });
  }, []);

  useEffect(() => {
    reset();
    return () => {
      generation.current += 1;
      for (const entry of inFlight.current.values()) {
        entry.controller.abort();
      }
      inFlight.current.clear();
      manifestRequest.current?.abort();
      manifestRequest.current = null;
    };
  }, [experimentId, reset]);

  /** Prepare one exact material with refresh, single-flight, and HEAD. */
  const prepare = useCallback(
    (material: BenchmarkExportMaterial): Promise<void> => {
      const existing = inFlight.current.get(material.key);
      if (existing) return existing.promise;
      const controller = new AbortController();
      const requestGeneration = generation.current;
      const run = async () => {
        commitState(material.key, { kind: "refreshing-metadata" });
        try {
          const snapshot = await refreshMetadata();
          if (
            controller.signal.aborted
            || requestGeneration !== generation.current
          ) {
            return;
          }
          const refreshedProjection = projectBenchmarkExportMaterials(
            experimentId,
            snapshot.inventory,
          );
          const refreshed = allMaterials(refreshedProjection).find(
            (candidate) =>
              candidate.item.descriptor.artifactId
              === material.item.descriptor.artifactId,
          );
          if (!refreshed || refreshed.key !== material.key) {
            commitState(
              material.key,
              refreshedFailure(material, snapshot),
            );
            return;
          }
          commitState(material.key, { kind: "verifying-head" });
          const head = await prepareBenchmarkExportTarget(
            refreshed.item,
            controller.signal,
          );
          if (
            controller.signal.aborted
            || requestGeneration !== generation.current
          ) {
            return;
          }
          commitState(material.key, {
            kind: "ready-for-handoff",
            item: refreshed.item,
            head,
          });
        } catch (error) {
          if (
            controller.signal.aborted
            || requestGeneration !== generation.current
          ) {
            return;
          }
          if (error instanceof StudioHeadContractError) {
            commitState(material.key, {
              kind: "failed",
              failure: "header-conflict",
              availability: material.item.descriptor.availability,
              retryable: true,
            });
            return;
          }
          try {
            const snapshot = await refreshMetadata();
            if (
              controller.signal.aborted
              || requestGeneration !== generation.current
            ) {
              return;
            }
            commitState(
              material.key,
              refreshedFailure(material, snapshot),
            );
          } catch {
            commitState(material.key, {
              kind: "failed",
              failure: "request-failed",
              availability: null,
              retryable: true,
            });
          }
        } finally {
          const current = inFlight.current.get(material.key);
          if (current?.generation === requestGeneration) {
            inFlight.current.delete(material.key);
          }
        }
      };
      const promise = run();
      inFlight.current.set(material.key, {
        controller,
        promise,
        generation: requestGeneration,
      });
      return promise;
    },
    [commitState, experimentId, refreshMetadata],
  );

  /** Record only that an exact ready capability was handed to the browser. */
  const markHandedOff = useCallback(
    (material: BenchmarkExportMaterial) => {
      const state = prepareStates.get(material.key);
      if (state?.kind !== "ready-for-handoff") return;
      commitState(material.key, {
        kind: "handed-off",
        item: state.item,
      });
    },
    [commitState, prepareStates],
  );

  /** Load one manifest into disposable local state without scanning bundle ZIP. */
  const loadManifest = useCallback(
    async (material: BenchmarkExportMaterial) => {
      manifestRequest.current?.abort();
      const controller = new AbortController();
      manifestRequest.current = controller;
      setManifestState({ kind: "loading" });
      try {
        const manifest = await loadBenchmarkPublicationManifest(
          material.item,
          new Set(taskRunIds),
          controller.signal,
        );
        if (manifestRequest.current !== controller) return;
        setManifestState({
          kind: "ready",
          summary: summarizeBenchmarkPublicationManifest(manifest),
        });
      } catch {
        if (controller.signal.aborted) return;
        setManifestState({ kind: "failed", retryable: true });
      } finally {
        if (manifestRequest.current === controller) {
          manifestRequest.current = null;
        }
      }
    },
    [taskRunIds],
  );

  /** Abort and discard publication manifest bytes and projection. */
  const closeManifest = useCallback(() => {
    manifestRequest.current?.abort();
    manifestRequest.current = null;
    setManifestState({ kind: "idle" });
  }, []);

  return {
    projection: projectionResult.projection,
    projectionError: projectionResult.error,
    prepareStates,
    manifestState,
    prepare,
    markHandedOff,
    loadManifest,
    closeManifest,
    reset,
  };
}
