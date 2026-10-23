import type {
  BenchmarkArtifactAvailability,
} from "@/entities/benchmark-experiment";
import type {
  BenchmarkArtifactInventoryItem,
  BenchmarkArtifactInventoryPage,
  BenchmarkEvaluationEvidence,
} from "./benchmarkReport.schema";
import { parseBenchmarkArtifactInventoryItem } from "./benchmarkReport.schema";

export type BenchmarkEvidenceScope = {
  experimentId: string;
  taskRunId: string;
};

export type BenchmarkEvidenceSelection = {
  leafPath: string;
  evidenceIndex: number;
  evidence: BenchmarkEvaluationEvidence;
};

export type BenchmarkEvidenceResolution =
  | { kind: "no-reference"; hiddenCount: number }
  | {
      kind: "reference-unavailable";
      hiddenCount: number;
      reason: "incomplete-inventory" | "scope-conflict" | "no-visible-match";
    }
  | {
      kind: "ambiguous-reference";
      hiddenCount: number;
      matchCount: number;
    }
  | {
      kind: "persisted-unreadable";
      hiddenCount: number;
      item: BenchmarkArtifactInventoryItem;
      availability: Exclude<
        BenchmarkArtifactAvailability,
        "available" | "redacted" | "truncated"
      >;
    }
  | {
      kind: "readable";
      hiddenCount: number;
      item: BenchmarkArtifactInventoryItem;
      availability: "available" | "redacted" | "truncated";
    };

const READABLE_AVAILABILITIES = new Set([
  "available",
  "redacted",
  "truncated",
] as const);

/** Resolve one leaf causal reference against a closed same-scope inventory.
 *
 * Args:
 *   scope: Current Experiment and selected Studio TaskRun identities.
 *   evidence: The strict Core evaluator evidence descriptor.
 *   inventory: The bounded full inventory returned by the report feature.
 *
 * Returns:
 *   A fail-closed resolution; success requires exactly one visible same-scope
 *   causal match and, for readable content, one strict parsed capability.
 */
export function resolveBenchmarkEvidence(
  scope: BenchmarkEvidenceScope,
  evidence: BenchmarkEvaluationEvidence,
  inventory: BenchmarkArtifactInventoryPage,
): BenchmarkEvidenceResolution {
  if (evidence.artifactRef.length === 0) {
    return { kind: "no-reference", hiddenCount: inventory.hiddenCount };
  }
  if (inventory.nextCursor !== null) {
    return {
      kind: "reference-unavailable",
      hiddenCount: inventory.hiddenCount,
      reason: "incomplete-inventory",
    };
  }
  if (inventory.experimentId !== scope.experimentId) {
    return {
      kind: "reference-unavailable",
      hiddenCount: inventory.hiddenCount,
      reason: "scope-conflict",
    };
  }

  const matches = inventory.items.filter((item) =>
    item.descriptor.experimentId === scope.experimentId
    && item.descriptor.taskRunId === scope.taskRunId
    && item.descriptor.causalIdentity === evidence.artifactRef
  );
  if (matches.length === 0) {
    return {
      kind: "reference-unavailable",
      hiddenCount: inventory.hiddenCount,
      reason: "no-visible-match",
    };
  }
  if (matches.length > 1) {
    return {
      kind: "ambiguous-reference",
      hiddenCount: inventory.hiddenCount,
      matchCount: matches.length,
    };
  }

  const candidate = matches[0]!;
  try {
    parseBenchmarkArtifactInventoryItem(
      candidate,
      scope.experimentId,
      "evidenceArtifact",
    );
  } catch {
    return {
      kind: "reference-unavailable",
      hiddenCount: inventory.hiddenCount,
      reason: "scope-conflict",
    };
  }
  if (
    READABLE_AVAILABILITIES.has(
      candidate.descriptor.availability as
        | "available"
        | "redacted"
        | "truncated",
    )
    && candidate.links.content !== null
  ) {
    return {
      kind: "readable",
      hiddenCount: inventory.hiddenCount,
      item: candidate,
      availability: candidate.descriptor.availability as
        | "available"
        | "redacted"
        | "truncated",
    };
  }
  return {
    kind: "persisted-unreadable",
    hiddenCount: inventory.hiddenCount,
    item: candidate,
    availability: candidate.descriptor.availability as Exclude<
      BenchmarkArtifactAvailability,
      "available" | "redacted" | "truncated"
    >,
  };
}

