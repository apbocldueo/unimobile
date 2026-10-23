import type { BenchmarkResourceCommandIntent } from "./benchmarkResourceIntents";

export type BenchmarkResourceSession = {
  draftId: string | null;
  revisionId: string | null;
  selectedResourceId: string | null;
  uploadFile: File | null;
  replacementFile: File | null;
  confirmationResourceId: string | null;
  error: string | null;
  message: string | null;
  retryIntent: BenchmarkResourceCommandIntent | null;
};

/** Create one empty, bounded resource-editor session. */
export function createBenchmarkResourceSession(): BenchmarkResourceSession {
  return {
    draftId: null,
    revisionId: null,
    selectedResourceId: null,
    uploadFile: null,
    replacementFile: null,
    confirmationResourceId: null,
    error: null,
    message: null,
    retryIntent: null,
  };
}

/**
 * Reconcile transient resource state with an authoritative immutable revision.
 *
 * Args:
 *   session: Current feature-local browser state.
 *   owner: Authoritative draft, revision, and sorted resource identities.
 *
 * Returns:
 *   A bounded session with stale files, confirmations, errors, and intents
 *   removed whenever ownership or revision changes.
 */
export function reconcileBenchmarkResourceSession(
  session: BenchmarkResourceSession,
  owner: { draftId: string; revisionId: string; resourceIds: string[] },
): BenchmarkResourceSession {
  const draftChanged = session.draftId !== owner.draftId;
  const revisionChanged = session.revisionId !== owner.revisionId;
  const selectedStillExists =
    session.selectedResourceId !== null
    && owner.resourceIds.includes(session.selectedResourceId);
  const selectedResourceId =
    !draftChanged && selectedStillExists
      ? session.selectedResourceId
      : (owner.resourceIds[0] ?? null);

  if (!draftChanged && !revisionChanged && selectedStillExists) {
    return session;
  }
  return {
    ...createBenchmarkResourceSession(),
    draftId: owner.draftId,
    revisionId: owner.revisionId,
    selectedResourceId,
  };
}
