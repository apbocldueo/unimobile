import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BenchmarkEvidencePreviewError,
  loadBenchmarkEvidencePreview,
  resolveBenchmarkEvidence,
  type BenchmarkArtifactInventoryItem,
  type BenchmarkArtifactInventoryPage,
  type BenchmarkEvidencePreview,
  type BenchmarkEvidenceResolution,
  type BenchmarkEvidenceScope,
  type BenchmarkEvidenceSelection,
} from "@/entities/benchmark-report";
import { StudioApiError } from "@/shared/api";

export type BenchmarkEvidenceViewerState =
  | { kind: "idle" }
  | { kind: "resolving" }
  | {
      kind: "no-reference" | "reference-unavailable";
      hiddenCount: number;
    }
  | {
      kind: "ambiguous-reference";
      hiddenCount: number;
      matchCount: number;
    }
  | {
      kind:
        | "pending"
        | "not-produced"
        | "excluded"
        | "missing"
        | "corrupt"
        | "failed";
      item: BenchmarkArtifactInventoryItem;
      hiddenCount: number;
    }
  | {
      kind: "loading";
      item: BenchmarkArtifactInventoryItem;
      hiddenCount: number;
    }
  | {
      kind: "ready-text";
      item: BenchmarkArtifactInventoryItem;
      hiddenCount: number;
      text: string;
      language: "json" | "ndjson" | "xml" | "text";
    }
  | {
      kind: "ready-image";
      item: BenchmarkArtifactInventoryItem;
      hiddenCount: number;
      objectUrl: string;
      width: number;
      height: number;
    }
  | {
      kind: "download-only";
      item: BenchmarkArtifactInventoryItem;
      hiddenCount: number;
      url: string;
      contentType: string;
    }
  | {
      kind:
        | "oversized"
        | "size-mismatch"
        | "mime-mismatch"
        | "invalid-content"
        | "request-failed";
      item: BenchmarkArtifactInventoryItem;
      hiddenCount: number;
      retryable: boolean;
    };

/** Own one explicitly selected evidence request and all disposable resources.
 *
 * Args:
 *   selection: React-local leaf selection, or null when the Viewer is closed.
 *   scope: Current Experiment and selected Studio TaskRun identities.
 *   inventory: Closed bounded metadata inventory already loaded by Report.
 *
 * Returns:
 *   A safe discriminated state and an explicit retry action. Artifact bodies
 *   never enter TanStack Query, Zustand, URL state, or localStorage.
 */
export function useBenchmarkEvidenceViewer(
  selection: BenchmarkEvidenceSelection | null,
  scope: BenchmarkEvidenceScope | null,
  inventory: BenchmarkArtifactInventoryPage | null,
): {
  state: BenchmarkEvidenceViewerState;
  retry: () => void;
} {
  const [retryRevision, setRetryRevision] = useState(0);
  const [state, setState] = useState<BenchmarkEvidenceViewerState>({
    kind: "idle",
  });
  const resolution = useMemo(
    () => resolveSelection(selection, scope, inventory),
    [inventory, scope, selection],
  );

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let ownedObjectUrl: string | null = null;

    if (resolution === null) {
      setState(selection === null ? { kind: "idle" } : { kind: "resolving" });
      return () => {
        active = false;
        controller.abort();
      };
    }
    const immediate = resolutionState(resolution);
    if (immediate !== null) {
      setState(immediate);
      return () => {
        active = false;
        controller.abort();
      };
    }
    if (resolution.kind !== "readable") {
      return () => {
        active = false;
        controller.abort();
      };
    }

    const readable = resolution;
    setState({
      kind: "loading",
      item: readable.item,
      hiddenCount: readable.hiddenCount,
    });
    void loadBenchmarkEvidencePreview(readable.item, controller.signal)
      .then((preview) => {
        if (preview.kind === "ready-image") {
          ownedObjectUrl = preview.objectUrl;
        }
        if (!active) {
          if (ownedObjectUrl !== null) URL.revokeObjectURL(ownedObjectUrl);
          ownedObjectUrl = null;
          return;
        }
        setState(previewState(readable, preview));
      })
      .catch((error: unknown) => {
        if (!active || controller.signal.aborted) return;
        setState(previewFailureState(readable, error));
      });

    return () => {
      active = false;
      controller.abort();
      if (ownedObjectUrl !== null) {
        URL.revokeObjectURL(ownedObjectUrl);
        ownedObjectUrl = null;
      }
    };
  }, [resolution, retryRevision, selection]);

  /** Start a fresh request for the same immutable local selection. */
  const retry = useCallback(() => {
    setRetryRevision((revision) => revision + 1);
  }, []);

  return { state, retry };
}

/** Resolve only when selection, scope, and closed inventory are all present. */
function resolveSelection(
  selection: BenchmarkEvidenceSelection | null,
  scope: BenchmarkEvidenceScope | null,
  inventory: BenchmarkArtifactInventoryPage | null,
): BenchmarkEvidenceResolution | null {
  if (selection === null || scope === null || inventory === null) return null;
  return resolveBenchmarkEvidence(scope, selection.evidence, inventory);
}

/** Convert a non-readable resolution into a stable Viewer state. */
function resolutionState(
  resolution: BenchmarkEvidenceResolution,
): BenchmarkEvidenceViewerState | null {
  if (resolution.kind === "readable") return null;
  if (resolution.kind === "no-reference") {
    return {
      kind: "no-reference",
      hiddenCount: resolution.hiddenCount,
    };
  }
  if (resolution.kind === "reference-unavailable") {
    return {
      kind: "reference-unavailable",
      hiddenCount: resolution.hiddenCount,
    };
  }
  if (resolution.kind === "ambiguous-reference") {
    return {
      kind: "ambiguous-reference",
      hiddenCount: resolution.hiddenCount,
      matchCount: resolution.matchCount,
    };
  }
  return {
    kind: persistedStateKind(resolution.availability),
    item: resolution.item,
    hiddenCount: resolution.hiddenCount,
  };
}

/** Preserve authoritative persisted availability without mutating metadata. */
function persistedStateKind(
  availability: string,
): "pending" | "not-produced" | "excluded" | "missing" | "corrupt" | "failed" {
  if (availability === "pending") return "pending";
  if (availability === "not_produced") return "not-produced";
  if (availability === "excluded") return "excluded";
  if (availability === "missing") return "missing";
  if (availability === "corrupt") return "corrupt";
  return "failed";
}

/** Attach authoritative descriptor facts to one successfully adapted preview. */
function previewState(
  resolution: Extract<BenchmarkEvidenceResolution, { kind: "readable" }>,
  preview: BenchmarkEvidencePreview,
): BenchmarkEvidenceViewerState {
  if (preview.kind === "ready-text") {
    return {
      ...preview,
      item: resolution.item,
      hiddenCount: resolution.hiddenCount,
    };
  }
  if (preview.kind === "ready-image") {
    return {
      ...preview,
      item: resolution.item,
      hiddenCount: resolution.hiddenCount,
    };
  }
  return {
    ...preview,
    item: resolution.item,
    hiddenCount: resolution.hiddenCount,
  };
}

/** Map arbitrary failures to safe local states without rendering raw messages. */
function previewFailureState(
  resolution: Extract<BenchmarkEvidenceResolution, { kind: "readable" }>,
  error: unknown,
): BenchmarkEvidenceViewerState {
  let kind:
    | "oversized"
    | "size-mismatch"
    | "mime-mismatch"
    | "invalid-content"
    | "missing"
    | "corrupt"
    | "request-failed" = "request-failed";
  if (error instanceof BenchmarkEvidencePreviewError) {
    kind = error.kind;
  } else if (error instanceof StudioApiError) {
    if (error.code.includes("missing") || error.status === 404) kind = "missing";
    else if (error.code.includes("corrupt") || error.status === 409) kind = "corrupt";
  }
  if (kind === "missing" || kind === "corrupt") {
    return {
      kind,
      item: resolution.item,
      hiddenCount: resolution.hiddenCount,
    };
  }
  return {
    kind,
    item: resolution.item,
    hiddenCount: resolution.hiddenCount,
    retryable: true,
  };
}
