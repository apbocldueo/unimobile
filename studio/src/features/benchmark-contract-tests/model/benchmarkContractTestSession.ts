import type {
  BenchmarkContractTestProfile,
  BenchmarkContractTestResult,
} from "@/entities/benchmark-authoring";

export type BenchmarkContractTestSession = {
  draftId: string;
  revisionId: string;
  documentFingerprint: string;
  split: string;
  seed: number;
  profile: BenchmarkContractTestProfile | null;
  generation: number;
  result: BenchmarkContractTestResult | null;
};

export type BenchmarkContractTestRequestOwner = {
  draftId: string;
  revisionId: string;
  documentFingerprint: string;
  split: string;
  seed: number;
  profileId: string;
  profileVersion: string;
  generation: number;
};

/** Create one disposable Contract Test feature session. */
export function createBenchmarkContractTestSession(input: {
  draftId: string;
  revisionId: string;
  documentFingerprint: string;
  split: string;
}): BenchmarkContractTestSession {
  return { ...input, seed: 0, profile: null, generation: 0, result: null };
}

/** Change request inputs and invalidate all previous result authority. */
export function setBenchmarkContractTestInputs(
  session: BenchmarkContractTestSession,
  input: Partial<Pick<BenchmarkContractTestSession, "split" | "seed" | "profile">>,
): BenchmarkContractTestSession {
  return {
    ...session,
    ...input,
    generation: session.generation + 1,
    result: null,
  };
}

/** Invalidate the current response generation without changing inputs. */
export function invalidateBenchmarkContractTestSession(
  session: BenchmarkContractTestSession,
): BenchmarkContractTestSession {
  return { ...session, generation: session.generation + 1, result: null };
}

/** Freeze one exact request owner before starting the mutation. */
export function benchmarkContractTestRequestOwner(
  session: BenchmarkContractTestSession,
): BenchmarkContractTestRequestOwner | null {
  if (!session.profile) return null;
  return {
    draftId: session.draftId,
    revisionId: session.revisionId,
    documentFingerprint: session.documentFingerprint,
    split: session.split,
    seed: session.seed,
    profileId: session.profile.profileId,
    profileVersion: session.profile.version,
    generation: session.generation,
  };
}

/** Accept a result only when every active request-owner dimension matches. */
export function acceptBenchmarkContractTestResult(
  session: BenchmarkContractTestSession,
  owner: BenchmarkContractTestRequestOwner,
  result: BenchmarkContractTestResult,
): BenchmarkContractTestSession {
  const active = benchmarkContractTestRequestOwner(session);
  if (!active || JSON.stringify(active) !== JSON.stringify(owner)) return session;
  if (
    result.draftId !== owner.draftId
    || result.revisionId !== owner.revisionId
    || result.documentFingerprint !== owner.documentFingerprint
    || result.split !== owner.split
    || result.seed !== owner.seed
    || result.profile.profileId !== owner.profileId
    || result.profile.version !== owner.profileVersion
  ) return session;
  return { ...session, result };
}
