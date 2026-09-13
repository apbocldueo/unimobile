import { useEffect, useMemo, useRef, useState } from "react";
import { StudioApiError } from "@/shared/api";
import {
  useBenchmarkContractTestProfiles,
  useRunBenchmarkContractTests,
  type BenchmarkAuthoringRevision,
  type BenchmarkContractKind,
  type BenchmarkContractStatus,
  type BenchmarkContractTestDiagnostic,
  type BenchmarkContractTestResult,
} from "@/entities/benchmark-authoring";
import {
  benchmarkContractTestGate,
  type BenchmarkContractTestGateInput,
} from "../model/benchmarkContractTestGate";
import {
  acceptBenchmarkContractTestResult,
  benchmarkContractTestRequestOwner,
  createBenchmarkContractTestSession,
  invalidateBenchmarkContractTestSession,
  setBenchmarkContractTestInputs,
} from "../model/benchmarkContractTestSession";

const SPLIT = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;
const PAGE_SIZE = 25;

export type BenchmarkContractDiagnosticNavigationIntent = {
  requestId: number;
  target: "definition";
  memberKind: "manifest" | "task" | "protocol";
  memberPath: string | null;
  resourceId: null;
  agentId: null;
  revisionId: null;
  fieldPath: Array<string | number>;
};

export type BenchmarkContractTestsViewProps = {
  revision: BenchmarkAuthoringRevision;
  gateInput: Omit<BenchmarkContractTestGateInput, "contractTestPending">;
  onPendingChange: (pending: boolean) => void;
  onDiagnosticNavigate: (intent: BenchmarkContractDiagnosticNavigationIntent) => void;
  onStaleConflict: (revisionId: string | null) => void;
};

/** Render explicit disposable fake-fixture Contract Tests for one revision. */
export function BenchmarkContractTestsView({
  revision,
  gateInput,
  onPendingChange,
  onDiagnosticNavigate,
  onStaleConflict,
}: BenchmarkContractTestsViewProps) {
  const profilesQuery = useBenchmarkContractTestProfiles();
  const command = useRunBenchmarkContractTests();
  const initialSplit = discoverSplits(revision)[0] ?? "test";
  const [session, setSession] = useState(() => createBenchmarkContractTestSession({
    draftId: revision.draftId,
    revisionId: revision.revisionId,
    documentFingerprint: revision.documentFingerprint,
    split: initialSplit,
  }));
  const sessionRef = useRef(session);
  const abortRef = useRef<AbortController | null>(null);
  const navigationSequence = useRef(0);
  const [error, setError] = useState<{ title: string; detail: string } | null>(null);
  const [stale, setStale] = useState<string | null>(null);
  const [kind, setKind] = useState<"all" | BenchmarkContractKind>("all");
  const [status, setStatus] = useState<"all" | BenchmarkContractStatus>("all");
  const [page, setPage] = useState(0);

  sessionRef.current = session;
  useEffect(() => onPendingChange(command.isPending), [command.isPending, onPendingChange]);
  useEffect(() => () => {
    abortRef.current?.abort();
    onPendingChange(false);
  }, [onPendingChange]);

  useEffect(() => {
    if (session.profile || !profilesQuery.data?.profiles[0]) return;
    setSession((current) => setBenchmarkContractTestInputs(current, {
      profile: profilesQuery.data?.profiles[0] ?? null,
    }));
  }, [profilesQuery.data, session.profile]);

  const externalGate = benchmarkContractTestGate({
    ...gateInput,
    contractTestPending: false,
  });
  const gate = benchmarkContractTestGate({
    ...gateInput,
    contractTestPending: command.isPending,
  });
  useEffect(() => {
    if (externalGate.allowed || session.result === null) return;
    abortRef.current?.abort();
    setSession(invalidateBenchmarkContractTestSession);
    setStale("Authoring authority 已变化；此前 Contract Test 结果已失效。");
  }, [externalGate.allowed, session.result]);

  const changeInputs = (
    input: Parameters<typeof setBenchmarkContractTestInputs>[1],
  ) => {
    abortRef.current?.abort();
    setSession((current) => setBenchmarkContractTestInputs(current, input));
    setError(null);
    setStale("输入已变化；请显式重新运行。");
    setPage(0);
  };

  /** Submit one exact owner and accept only an owner-matching response. */
  const run = async () => {
    const active = sessionRef.current;
    const owner = benchmarkContractTestRequestOwner(active);
    if (!owner || !externalGate.allowed || !SPLIT.test(owner.split)) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setStale(null);
    try {
      const result = await command.mutateAsync({
        draftId: owner.draftId,
        request: {
          schemaVersion: 1,
          revisionId: owner.revisionId,
          split: owner.split,
          seed: owner.seed,
          fixtureProfileId: owner.profileId,
        },
        signal: controller.signal,
      });
      setSession((current) => acceptBenchmarkContractTestResult(current, owner, result));
    } catch (caught) {
      if (controller.signal.aborted) return;
      if (caught instanceof StudioApiError && caught.status === 409) {
        setSession(invalidateBenchmarkContractTestSession);
        setStale("服务端 current revision 已推进；结果已丢弃，请 Reload Remote。");
        onStaleConflict(caught.currentRevisionId);
        return;
      }
      const detail = caught instanceof Error ? caught.message : "Contract Tests failed";
      setError({
        title: caught instanceof StudioApiError && caught.status === 413
          ? "Contract Test capacity exceeded"
          : caught instanceof StudioApiError && caught.status === 503
            ? "Contract Test service unavailable"
            : "Transport / service failure",
        detail,
      });
    }
  };

  const filtered = useMemo(() => (session.result?.cases ?? []).filter((item) =>
    (kind === "all" || item.kind === kind)
    && (status === "all" || item.status === status)), [kind, session.result, status]);
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const splitSuggestions = discoverSplits(revision);

  const navigate = (diagnostic: BenchmarkContractTestDiagnostic) => {
    navigationSequence.current += 1;
    onDiagnosticNavigate({
      requestId: navigationSequence.current,
      target: "definition",
      memberKind: diagnostic.memberKind,
      memberPath: diagnostic.memberPath,
      resourceId: null,
      agentId: null,
      revisionId: null,
      fieldPath: [...diagnostic.fieldPath],
    });
  };

  return (
    <div className="grid min-h-0 flex-1 gap-0 lg:grid-cols-[20rem_minmax(30rem,1fr)_20rem]">
      <aside className="overflow-auto border-r border-[var(--zx-divider-ui)] p-4">
        <h2 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">Contract Test inputs</h2>
        <p className="mt-1 font-mono text-[9px] text-[color:var(--zx-text-muted)]">
          revision {revision.ordinal} · {revision.revisionId}
        </p>
        <label className="mt-4 grid gap-1 text-[10px] text-[color:var(--zx-text-muted)]">
          Split
          <input aria-label="Contract Test split" list="contract-test-splits" value={session.split}
            onChange={(event) => changeInputs({ split: event.target.value })}
            className="rounded border border-[var(--zx-border-light)] bg-transparent px-2 py-2" />
          <datalist id="contract-test-splits">
            {splitSuggestions.map((item) => <option key={item} value={item} />)}
          </datalist>
        </label>
        <label className="mt-3 grid gap-1 text-[10px] text-[color:var(--zx-text-muted)]">
          Seed
          <input aria-label="Contract Test seed" type="number" step="1" value={session.seed}
            onChange={(event) => {
              const seed = Number(event.target.value);
              if (Number.isSafeInteger(seed)) changeInputs({ seed });
            }}
            className="rounded border border-[var(--zx-border-light)] bg-transparent px-2 py-2" />
        </label>
        <label className="mt-3 grid gap-1 text-[10px] text-[color:var(--zx-text-muted)]">
          Fixture profile
          <select aria-label="Fixture profile" value={session.profile?.profileId ?? ""}
            onChange={(event) => changeInputs({
              profile: profilesQuery.data?.profiles.find((item) => item.profileId === event.target.value) ?? null,
            })}
            className="rounded border border-[var(--zx-border-light)] bg-transparent px-2 py-2">
            {profilesQuery.data?.profiles.map((item) => (
              <option key={`${item.profileId}:${item.version}`} value={item.profileId}>{item.title} · {item.version}</option>
            ))}
          </select>
        </label>
        <p className={`mt-4 text-[10px] ${gate.allowed ? "text-emerald-400" : "text-amber-400"}`}>{gate.message}</p>
        {profilesQuery.isError ? <p role="alert" className="mt-2 text-[10px] text-rose-400">Profile metadata unavailable.</p> : null}
        <button type="button" onClick={() => void run()}
          disabled={!externalGate.allowed || command.isPending || !session.profile || !SPLIT.test(session.split)}
          className="mt-4 w-full rounded bg-[var(--zx-primary)] px-3 py-2 text-[11px] font-semibold text-white disabled:opacity-40">
          {command.isPending ? "Running trusted fakes…" : "Run Contract Tests"}
        </button>
        <p className="mt-3 text-[9px] text-[color:var(--zx-text-muted)]">No automatic run. Inputs and results are browser-local and disposable.</p>
      </aside>

      <main className="min-h-0 overflow-auto p-5">
        {error ? <State title={error.title} detail={error.detail} tone="error" /> : null}
        {stale ? <State title="Result stale" detail={stale} tone="warning" /> : null}
        {!session.result && !error && !stale && !command.isPending ? (
          <State title="Not run" detail="Select bounded inputs, satisfy the clean saved-baseline gate, then run explicitly." />
        ) : null}
        {command.isPending ? <State title="Contract Tests pending" detail="Only the selected server-owned fake profile is running in-process." /> : null}
        {session.result ? (
          <>
            <ResultSummary result={session.result} />
            <div className="mt-5 flex flex-wrap gap-2">
              <select aria-label="Contract kind filter" value={kind} onChange={(event) => { setKind(event.target.value as typeof kind); setPage(0); }}
                className="rounded border border-[var(--zx-border-light)] bg-transparent px-2 py-1 text-[10px]">
                <option value="all">All kinds</option><option value="initializer">Initializer</option>
                <option value="environment">Environment</option><option value="evaluator">Evaluator</option>
              </select>
              <select aria-label="Contract status filter" value={status} onChange={(event) => { setStatus(event.target.value as typeof status); setPage(0); }}
                className="rounded border border-[var(--zx-border-light)] bg-transparent px-2 py-1 text-[10px]">
                <option value="all">All statuses</option><option value="passed">Passed</option>
                <option value="failed">Failed</option><option value="skipped">Skipped</option>
              </select>
              <span className="text-[10px] text-[color:var(--zx-text-muted)]">{filtered.length} matching cases</span>
            </div>
            <div className="mt-3 space-y-2">
              {visible.map((item) => (
                <article key={item.caseId} className="rounded-lg border border-[var(--zx-border-light)] p-3">
                  <div className="flex flex-wrap items-center gap-2 text-[10px]">
                    <strong className="text-[color:var(--zx-text-title)]">{item.kind} · {item.logicalName}</strong>
                    <span>{item.status}</span><span className="font-mono text-[9px]">seed {item.seed}</span>
                  </div>
                  <p className="mt-1 font-mono text-[9px] text-[color:var(--zx-text-muted)]">{item.taskId} · {item.memberPath ?? "unknown member"}</p>
                  {item.checks.length ? <p className="mt-2 text-[9px]">checks: {item.checks.join(", ")}</p> : null}
                  {item.skipped.length ? <p className="mt-2 text-[9px] text-amber-400">skipped: {item.skipped.join(", ")}</p> : null}
                  {item.diagnostics.map((diagnostic) => (
                    <button key={`${item.caseId}:${diagnostic.code}`} type="button" onClick={() => navigate(diagnostic)}
                      className="mt-2 block text-left text-[9px] text-rose-400 underline">
                      {diagnostic.code} · {diagnostic.message} · {diagnostic.fieldPath.join(".")}
                    </button>
                  ))}
                </article>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2 text-[10px]">
              <button type="button" disabled={page === 0} onClick={() => setPage((current) => Math.max(0, current - 1))}>Previous</button>
              <span>Page {page + 1} / {pages}</span>
              <button type="button" disabled={page + 1 >= pages} onClick={() => setPage((current) => Math.min(pages - 1, current + 1))}>Next</button>
            </div>
          </>
        ) : null}
      </main>

      <aside className="overflow-auto border-l border-[var(--zx-divider-ui)] p-4 text-[10px] text-[color:var(--zx-text-muted)]">
        <h2 className="font-semibold text-[color:var(--zx-text-title)]">Evidence boundary</h2>
        <ul className="mt-3 list-disc space-y-2 pl-4">
          <li>Only reviewed server-owned fake fixtures execute in-process.</li>
          <li>Package plugin code and the real Benchmark runtime do not execute.</li>
          <li>No device, model, network, secret, Agent, Experiment, or publication capability is supplied.</li>
          <li>This is not a process sandbox and is not real-device evidence.</li>
          <li>The revision remains unvalidated; results are not persisted and grant no publication eligibility.</li>
        </ul>
        {session.result ? (
          <div className="mt-5 space-y-1 font-mono text-[9px]">
            <p>profile {session.result.profile.profileId}@{session.result.profile.version}</p>
            <p>plan {session.result.identities.benchmarkPlan ?? "not established"}</p>
            <p>document {session.result.documentFingerprint}</p>
          </div>
        ) : null}
      </aside>
    </div>
  );
}

/** Discover stable split suggestions without treating them as authority. */
function discoverSplits(revision: BenchmarkAuthoringRevision): string[] {
  const splits = revision.document.manifest.document.splits;
  if (!splits || typeof splits !== "object" || Array.isArray(splits)) return [];
  return Object.keys(splits).filter((item) => SPLIT.test(item)).sort();
}

/** Render a bounded empty/pending/error state. */
function State({ title, detail, tone = "neutral" }: { title: string; detail: string; tone?: "neutral" | "warning" | "error" }) {
  return <section className="rounded-lg border border-[var(--zx-border-light)] p-5">
    <h2 className={tone === "error" ? "text-rose-400" : tone === "warning" ? "text-amber-400" : "text-[color:var(--zx-text-title)]"}>{title}</h2>
    <p className="mt-2 text-[10px] text-[color:var(--zx-text-muted)]">{detail}</p>
  </section>;
}

/** Present completeness and executed-check success as independent facts. */
function ResultSummary({ result }: { result: BenchmarkContractTestResult }) {
  const { coverage } = result;
  const title = !result.validDefinition
    ? "Definition precondition failed"
    : coverage.failed > 0
      ? "Executed contract checks failed"
      : coverage.skipped > 0
        ? "Executed checks passed; coverage incomplete"
        : "All covered fake-fixture checks passed";
  return <section className="rounded-lg border border-[var(--zx-border-light)] p-4">
    <h2 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">{title}</h2>
    <p className="mt-2 text-[10px]">passed {coverage.passed} · failed {coverage.failed} · skipped {coverage.skipped} · total {coverage.total}</p>
    <p className="mt-1 text-[10px]">complete: {String(coverage.complete)} · executedChecksPassed: {String(coverage.executedChecksPassed)}</p>
    {result.preconditionDiagnostics.map((diagnostic) => <p key={diagnostic.code} className="mt-2 text-[9px] text-rose-400">{diagnostic.code} · {diagnostic.message}</p>)}
  </section>;
}
