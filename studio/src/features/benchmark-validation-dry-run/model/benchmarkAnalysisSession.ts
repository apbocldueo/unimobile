import type { StudioAgent } from "@/entities/agent";
import type {
  BenchmarkDryRunResult,
  BenchmarkValidationResult,
} from "@/entities/benchmark-authoring";
import {
  BENCHMARK_ANALYSIS_MAX_AGENTS,
  BENCHMARK_ANALYSIS_MAX_TASKS,
} from "@/entities/benchmark-authoring";

export type FrozenAgentRevision = {
  agentId: string;
  revisionId: string;
  displayName: string;
};

export type BenchmarkValidationRequestOwner = {
  key: string;
  draftId: string;
  revisionId: string;
  documentFingerprint: string;
  split: string;
  generation: number;
};

export type BenchmarkDryRunRequestOwner = BenchmarkValidationRequestOwner & {
  taskIds: string[];
  agentRevisions: FrozenAgentRevision[];
};

export type BenchmarkAnalysisSession = {
  draftId: string;
  revisionId: string;
  documentFingerprint: string;
  split: string;
  taskIds: string[];
  agentRevisions: FrozenAgentRevision[];
  validationResult: BenchmarkValidationResult | null;
  dryRunResult: BenchmarkDryRunResult | null;
  validationGeneration: number;
  dryRunGeneration: number;
  schedulePage: number;
  focusedAgentId: string | null;
  fieldPathBreadcrumb: Array<string | number>;
};

/**
 * Create one bounded transient analysis session for an immutable revision.
 *
 * Args:
 *   owner: Exact draft/revision/fingerprint owner and optional initial split.
 *
 * Returns:
 *   An empty browser-local session with independent result generations.
 */
export function createBenchmarkAnalysisSession(owner: {
  draftId: string;
  revisionId: string;
  documentFingerprint: string;
  split?: string;
}): BenchmarkAnalysisSession {
  return {
    ...owner,
    split: owner.split ?? "",
    taskIds: [],
    agentRevisions: [],
    validationResult: null,
    dryRunResult: null,
    validationGeneration: 0,
    dryRunGeneration: 0,
    schedulePage: 0,
    focusedAgentId: null,
    fieldPathBreadcrumb: [],
  };
}

/**
 * Reconcile transient state with one authoritative immutable revision owner.
 *
 * Args:
 *   session: Existing browser-local analysis state.
 *   owner: Latest authoritative immutable revision facts.
 *
 * Returns:
 *   The unchanged session for the same owner or a cleared session for a new one.
 */
export function reconcileBenchmarkAnalysisSession(
  session: BenchmarkAnalysisSession,
  owner: {
    draftId: string;
    revisionId: string;
    documentFingerprint: string;
    suggestedSplit?: string;
  },
): BenchmarkAnalysisSession {
  if (
    session.draftId === owner.draftId
    && session.revisionId === owner.revisionId
    && session.documentFingerprint === owner.documentFingerprint
  ) {
    return session;
  }
  return createBenchmarkAnalysisSession({
    ...owner,
    split: owner.suggestedSplit ?? "",
  });
}

/**
 * Change explicit split and invalidate both revision-bound result kinds.
 *
 * Args:
 *   session: Current transient analysis state.
 *   split: New explicit split string; semantic validation remains server-owned.
 *
 * Returns:
 *   A session with split-dependent inputs and results cleared when changed.
 */
export function setBenchmarkAnalysisSplit(
  session: BenchmarkAnalysisSession,
  split: string,
): BenchmarkAnalysisSession {
  if (session.split === split) return session;
  return {
    ...session,
    split,
    taskIds: [],
    validationResult: null,
    dryRunResult: null,
    validationGeneration: session.validationGeneration + 1,
    dryRunGeneration: session.dryRunGeneration + 1,
    schedulePage: 0,
    fieldPathBreadcrumb: [],
  };
}

/**
 * Replace a bounded unique task subset and invalidate only dry-run facts.
 *
 * Args:
 *   session: Current transient analysis state.
 *   taskIds: Explicit unique selection, or an empty array for the whole split.
 *
 * Returns:
 *   Updated state, or the original state when the selection violates capacity.
 */
export function setBenchmarkAnalysisTasks(
  session: BenchmarkAnalysisSession,
  taskIds: string[],
): BenchmarkAnalysisSession {
  if (taskIds.length > BENCHMARK_ANALYSIS_MAX_TASKS || new Set(taskIds).size !== taskIds.length) {
    return session;
  }
  if (JSON.stringify(session.taskIds) === JSON.stringify(taskIds)) return session;
  return {
    ...session,
    taskIds: [...taskIds],
    dryRunResult: null,
    dryRunGeneration: session.dryRunGeneration + 1,
    schedulePage: 0,
  };
}

/**
 * Freeze one Agent's observed current revision without advancing old pairs.
 *
 * Args:
 *   session: Current transient analysis state.
 *   agent: Candidate metadata whose current revision is captured exactly once.
 *
 * Returns:
 *   Updated state, or the original state for missing, duplicate, or over-capacity input.
 */
export function addFrozenAgentRevision(
  session: BenchmarkAnalysisSession,
  agent: StudioAgent,
): BenchmarkAnalysisSession {
  if (
    agent.currentRevisionId === null
    || session.agentRevisions.length >= BENCHMARK_ANALYSIS_MAX_AGENTS
    || session.agentRevisions.some((item) => item.agentId === agent.agentId)
  ) {
    return session;
  }
  return {
    ...session,
    agentRevisions: [
      ...session.agentRevisions,
      {
        agentId: agent.agentId,
        revisionId: agent.currentRevisionId,
        displayName: agent.name,
      },
    ],
    dryRunResult: null,
    dryRunGeneration: session.dryRunGeneration + 1,
    schedulePage: 0,
  };
}

/**
 * Remove one frozen Agent dimension and invalidate only dry-run facts.
 *
 * Args:
 *   session: Current transient analysis state.
 *   agentId: Frozen Agent identity to remove.
 *
 * Returns:
 *   Updated state, or the original state when the Agent was not selected.
 */
export function removeFrozenAgentRevision(
  session: BenchmarkAnalysisSession,
  agentId: string,
): BenchmarkAnalysisSession {
  const remaining = session.agentRevisions.filter((item) => item.agentId !== agentId);
  if (remaining.length === session.agentRevisions.length) return session;
  return {
    ...session,
    agentRevisions: remaining,
    dryRunResult: null,
    dryRunGeneration: session.dryRunGeneration + 1,
    schedulePage: 0,
    focusedAgentId: session.focusedAgentId === agentId ? null : session.focusedAgentId,
  };
}

/**
 * Invalidate all visible analysis authority after local or remote movement.
 *
 * Args:
 *   session: Current transient analysis state.
 *
 * Returns:
 *   State with both result kinds cleared and generations advanced.
 */
export function invalidateBenchmarkAnalysisResults(
  session: BenchmarkAnalysisSession,
): BenchmarkAnalysisSession {
  return {
    ...session,
    validationResult: null,
    dryRunResult: null,
    validationGeneration: session.validationGeneration + 1,
    dryRunGeneration: session.dryRunGeneration + 1,
    schedulePage: 0,
  };
}

/**
 * Build the exact active owner for a validation command.
 *
 * Args:
 *   session: Current transient analysis state.
 *
 * Returns:
 *   A stable request key over revision, fingerprint, split, and generation.
 */
export function benchmarkValidationRequestOwner(
  session: BenchmarkAnalysisSession,
): BenchmarkValidationRequestOwner {
  const facts = {
    draftId: session.draftId,
    revisionId: session.revisionId,
    documentFingerprint: session.documentFingerprint,
    split: session.split,
    generation: session.validationGeneration,
  };
  return { ...facts, key: JSON.stringify(facts) };
}

/**
 * Build the exact active owner for a dry-run command.
 *
 * Args:
 *   session: Current transient analysis state.
 *
 * Returns:
 *   A stable request key that also captures task and frozen Agent dimensions.
 */
export function benchmarkDryRunRequestOwner(
  session: BenchmarkAnalysisSession,
): BenchmarkDryRunRequestOwner {
  const validation = benchmarkValidationRequestOwner(session);
  const facts = {
    draftId: validation.draftId,
    revisionId: validation.revisionId,
    documentFingerprint: validation.documentFingerprint,
    split: validation.split,
    generation: session.dryRunGeneration,
    taskIds: [...session.taskIds],
    agentRevisions: session.agentRevisions.map((item) => ({ ...item })),
  };
  return { ...facts, key: JSON.stringify(facts) };
}

/**
 * Accept validation only when both request and echoed response still match.
 *
 * Args:
 *   session: Current transient state at completion time.
 *   owner: Frozen owner captured before the request.
 *   result: Strict parsed server result.
 *
 * Returns:
 *   State with the result attached, or the unchanged state for a late response.
 */
export function acceptBenchmarkValidationResult(
  session: BenchmarkAnalysisSession,
  owner: BenchmarkValidationRequestOwner,
  result: BenchmarkValidationResult,
): BenchmarkAnalysisSession {
  const current = benchmarkValidationRequestOwner(session);
  if (
    current.key !== owner.key
    || result.draftId !== owner.draftId
    || result.revisionId !== owner.revisionId
    || result.documentFingerprint !== owner.documentFingerprint
    || result.split !== owner.split
  ) {
    return session;
  }
  return { ...session, validationResult: result, fieldPathBreadcrumb: [] };
}

/**
 * Accept dry-run only when request and every echoed owner fact still match.
 *
 * Args:
 *   session: Current transient state at completion time.
 *   owner: Frozen revision/task/Agent owner captured before the request.
 *   result: Strict parsed server projection.
 *
 * Returns:
 *   State with the result attached, or unchanged state for stale ownership.
 */
export function acceptBenchmarkDryRunResult(
  session: BenchmarkAnalysisSession,
  owner: BenchmarkDryRunRequestOwner,
  result: BenchmarkDryRunResult,
): BenchmarkAnalysisSession {
  const current = benchmarkDryRunRequestOwner(session);
  if (
    current.key !== owner.key
    || result.draftId !== owner.draftId
    || result.revisionId !== owner.revisionId
    || result.documentFingerprint !== owner.documentFingerprint
    || result.split !== owner.split
    || result.agentRevisions.length !== owner.agentRevisions.length
    || result.agentRevisions.some((item, index) => {
      const selected = owner.agentRevisions[index];
      return item.agentId !== selected?.agentId || item.revisionId !== selected.revisionId;
    })
  ) {
    return session;
  }
  return { ...session, dryRunResult: result, schedulePage: 0 };
}
