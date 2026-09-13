import type { ReplayEnvelope } from "@/entities/replay";
import type { BenchmarkContext } from "@/entities/benchmark";
import {
  classifyEvidenceOrigin,
  type EvidenceOriginPresentationKind,
} from "@/entities/evidence-origin";
import type {
  EvidenceAvailabilityState,
  FailureTarget,
  ReplayIntegrityState,
  ReplayProjection,
} from "@/entities/run";
import { selectFailureTargets } from "./replayProjection";

export type ReplayOverviewEvidence = {
  kind: EvidenceOriginPresentationKind;
  label: string;
  description: string;
  integrityState: ReplayIntegrityState;
  acquisition: ReplayEnvelope["evidenceOrigin"]["acquisition"];
  environment: ReplayEnvelope["evidenceOrigin"]["environment"];
  realDeviceEvidence: boolean;
  graphState: EvidenceAvailabilityState;
  screenshotState: EvidenceAvailabilityState;
};

export type ReplayOverview = {
  agentStatus: string;
  benchmarkOutcome: BenchmarkContext["outcome"] | null;
  failureTarget: FailureTarget | null;
  location: string | null;
  reason: string;
  reasonSource: "agent_result" | "benchmark_phase" | "integrity" | "failure_target" | "status";
  counts: {
    steps: number;
    activations: number;
    interactions: number;
  };
  milestones: Array<{
    cursor: number;
    kind: string;
    label: string;
    activationId: string | null;
  }>;
  evidence: ReplayOverviewEvidence;
};

const EVIDENCE_LABELS: Record<EvidenceOriginPresentationKind, string> = {
  "fresh-real-source": "真实 Android 执行",
  "historical-real-source": "真实 Android 历史回放",
  "fake-fixture": "模拟设备测试证据",
  unverified: "证据来源未验证",
};

/** Select a bounded chronological set of user-meaningful Replay milestones. */
function keyMilestones(envelope: ReplayEnvelope): ReplayOverview["milestones"] {
  return envelope.moments
    .filter((moment) =>
      moment.kind === "start"
      || ["complete", "success", "failure", "fail", "error", "cancelled", "skipped"].includes(moment.kind)
      || ["feedback_latched", "router_selected", "loop_exhausted"].includes(moment.kind)
      || moment.sourceKind === "observation"
      || moment.sourceKind === "action"
      || moment.sourceKind === "benchmark_lifecycle",
    )
    .slice(-6)
    .map((moment) => ({
      cursor: moment.causalIndex,
      kind: moment.kind,
      label: `${moment.nodePath || moment.phase || moment.role || "运行"} · ${moment.kind}`,
      activationId: moment.activationId || null,
    }));
}

/** Return the first bounded formal Benchmark failure description, if recorded. */
function benchmarkFailureReason(envelope: ReplayEnvelope): string | null {
  const phase = envelope.benchmark?.phases.find((item) =>
    ["failure", "fail", "error", "invalid"].includes(item.status.toLowerCase()),
  );
  if (!phase) return null;
  return phase.message || phase.errorCode || `${phase.phase} · ${phase.status}`;
}

/** Resolve a safe recorded reason without claiming automated root-cause analysis. */
function formalReason(
  envelope: ReplayEnvelope,
  projection: ReplayProjection,
  target: FailureTarget | null,
): Pick<ReplayOverview, "reason" | "reasonSource"> {
  if (
    target?.kind !== "benchmark_evaluation"
    && target?.kind !== "benchmark_infrastructure"
    && envelope.result.error
  ) {
    return { reason: envelope.result.error, reasonSource: "agent_result" };
  }
  const benchmarkReason = benchmarkFailureReason(envelope);
  if (target && benchmarkReason) {
    return { reason: benchmarkReason, reasonSource: "benchmark_phase" };
  }
  const integrityError = projection.diagnostics.find((item) => item.severity === "error");
  if (integrityError) {
    return { reason: integrityError.message, reasonSource: "integrity" };
  }
  if (target) {
    return { reason: target.label, reasonSource: "failure_target" };
  }
  return {
    reason: `Agent ${envelope.result.status}`,
    reasonSource: "status",
  };
}

/** Derive a presentation-only run overview from immutable Replay facts. */
export function selectReplayOverview(
  envelope: ReplayEnvelope,
  projection: ReplayProjection,
): ReplayOverview {
  const failureTarget = selectFailureTargets(projection)[0] ?? null;
  const origin = classifyEvidenceOrigin(envelope.evidenceOrigin);
  const reason = formalReason(envelope, projection, failureTarget);
  return {
    agentStatus: envelope.result.status,
    benchmarkOutcome: envelope.benchmark?.outcome ?? null,
    failureTarget,
    location:
      failureTarget?.nodePath
      ?? (failureTarget?.kind === "benchmark_evaluation" ? "Benchmark evaluation" : null)
      ?? (failureTarget?.kind === "benchmark_infrastructure" ? "Benchmark lifecycle" : null),
    ...reason,
    counts: {
      steps: envelope.result.stepCount,
      activations: envelope.result.activationCount,
      interactions: envelope.result.interactionCount,
    },
    milestones: keyMilestones(envelope),
    evidence: {
      kind: origin.kind,
      label: EVIDENCE_LABELS[origin.kind],
      description: origin.description,
      integrityState: envelope.integrityState,
      acquisition: envelope.evidenceOrigin.acquisition,
      environment: envelope.evidenceOrigin.environment,
      realDeviceEvidence: envelope.evidenceOrigin.realDeviceEvidence,
      graphState: envelope.snapshot.graphStatus,
      screenshotState: envelope.availability.screenshots?.state ?? "not_captured",
    },
  };
}
