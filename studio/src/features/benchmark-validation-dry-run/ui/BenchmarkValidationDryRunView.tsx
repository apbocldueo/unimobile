import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  BenchmarkAnalysisDiagnostic,
  BenchmarkAnalysisIdentities,
  BenchmarkAuthoringRevision,
  BenchmarkDryRunResult,
  BenchmarkValidationResult,
} from "@/entities/benchmark-authoring";
import {
  useDryRunBenchmarkDraft,
  useValidateBenchmarkDraft,
} from "@/entities/benchmark-authoring";
import { StudioApiError } from "@/shared/api";
import { benchmarkAnalysisGate, type BenchmarkAnalysisGateInput } from "../model/benchmarkAnalysisGate";
import { discoverBenchmarkSplits, discoverBenchmarkTaskIds } from "../model/benchmarkAnalysisDiscovery";
import {
  acceptBenchmarkDryRunResult,
  acceptBenchmarkValidationResult,
  addFrozenAgentRevision,
  benchmarkDryRunRequestOwner,
  benchmarkValidationRequestOwner,
  createBenchmarkAnalysisSession,
  invalidateBenchmarkAnalysisResults,
  reconcileBenchmarkAnalysisSession,
  removeFrozenAgentRevision,
  setBenchmarkAnalysisSplit,
  setBenchmarkAnalysisTasks,
  type BenchmarkAnalysisSession,
} from "../model/benchmarkAnalysisSession";
import { useBenchmarkAnalysisAgents } from "../model/useBenchmarkAnalysisAgents";

export type BenchmarkDiagnosticNavigationIntent = {
  requestId: number;
  target: "definition" | "resource" | "agent";
  memberKind: BenchmarkAnalysisDiagnostic["memberKind"];
  memberPath: string | null;
  resourceId: string | null;
  agentId: string | null;
  revisionId: string | null;
  fieldPath: Array<string | number>;
};

export type BenchmarkValidationNavigationRequest = {
  requestId: number;
  agentId: string;
  fieldPath: Array<string | number>;
};

export type BenchmarkValidationDryRunViewProps = {
  revision: BenchmarkAuthoringRevision;
  gateInput: Omit<BenchmarkAnalysisGateInput, "analysisPending">;
  navigationRequest: BenchmarkValidationNavigationRequest | null;
  onDiagnosticNavigate: (intent: BenchmarkDiagnosticNavigationIntent) => void;
  onAnalysisPendingChange: (pending: boolean) => void;
  onStaleConflict: (currentRevisionId: string | null) => void;
};

const cardClass = "rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-4";
const inputClass = "zx-control px-3 py-2 text-[12px]";
const splitPattern = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;
const schedulePageSize = 50;

/**
 * Render explicit revision-bound validation and non-executing dry-run analysis.
 *
 * Args:
 *   props: Exact saved revision, public gate facts, controlled navigation intent,
 *   and workbench callbacks for pending, navigation, and stale-current state.
 *
 * Returns:
 *   A three-pane transient analysis view with bounded diagnostics and schedule DOM.
 */
export function BenchmarkValidationDryRunView({
  revision,
  gateInput,
  navigationRequest,
  onDiagnosticNavigate,
  onAnalysisPendingChange,
  onStaleConflict,
}: BenchmarkValidationDryRunViewProps) {
  const splitSuggestions = useMemo(
    () => discoverBenchmarkSplits(revision.document),
    [revision.document],
  );
  const [session, setSessionState] = useState<BenchmarkAnalysisSession>(() =>
    createBenchmarkAnalysisSession({
      draftId: revision.draftId,
      revisionId: revision.revisionId,
      documentFingerprint: revision.documentFingerprint,
      split: splitSuggestions[0] ?? "test",
    }));
  const sessionRef = useRef(session);
  const validationAbort = useRef<AbortController | null>(null);
  const dryRunAbort = useRef<AbortController | null>(null);
  const eligibilityRef = useRef<boolean | null>(null);
  const navigationSequence = useRef(0);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [dryRunError, setDryRunError] = useState<string | null>(null);
  const [staleMessage, setStaleMessage] = useState<string | null>(null);
  const validateCommand = useValidateBenchmarkDraft();
  const dryRunCommand = useDryRunBenchmarkDraft();
  const agents = useBenchmarkAnalysisAgents();
  const analysisPending = validateCommand.isPending || dryRunCommand.isPending;
  const baseGate = benchmarkAnalysisGate({ ...gateInput, analysisPending: false });
  const gate = benchmarkAnalysisGate({ ...gateInput, analysisPending });
  const taskCandidates = useMemo(
    () => discoverBenchmarkTaskIds(revision.document, session.split),
    [revision.document, session.split],
  );

  useEffect(() => {
    onAnalysisPendingChange(analysisPending);
    return () => onAnalysisPendingChange(false);
  }, [analysisPending, onAnalysisPendingChange]);

  /**
   * Commit one session transition while keeping async owner checks current.
   *
   * Args:
   *   transition: Pure transformation over the latest browser-local session.
   */
  const updateSession = useCallback((
    transition: (current: BenchmarkAnalysisSession) => BenchmarkAnalysisSession,
  ) => {
    setSessionState((current) => {
      const next = transition(current);
      sessionRef.current = next;
      return next;
    });
  }, []);

  useEffect(() => {
    updateSession((current) => reconcileBenchmarkAnalysisSession(current, {
      draftId: revision.draftId,
      revisionId: revision.revisionId,
      documentFingerprint: revision.documentFingerprint,
      suggestedSplit: splitSuggestions[0] ?? "test",
    }));
    validationAbort.current?.abort();
    dryRunAbort.current?.abort();
    setValidationError(null);
    setDryRunError(null);
    setStaleMessage(null);
  }, [revision.draftId, revision.documentFingerprint, revision.revisionId, splitSuggestions, updateSession]);

  useEffect(() => {
    if (eligibilityRef.current === true && !baseGate.allowed) {
      validationAbort.current?.abort();
      dryRunAbort.current?.abort();
      updateSession(invalidateBenchmarkAnalysisResults);
      setStaleMessage("本地或远端 authoring 状态已变化；此前分析结果不再属于当前视图。");
    }
    eligibilityRef.current = baseGate.allowed;
  }, [baseGate.allowed, updateSession]);

  useEffect(() => () => {
    validationAbort.current?.abort();
    dryRunAbort.current?.abort();
  }, []);

  useEffect(() => {
    if (!navigationRequest) return;
    updateSession((current) => ({
      ...current,
      focusedAgentId: navigationRequest.agentId,
      fieldPathBreadcrumb: [...navigationRequest.fieldPath],
    }));
  }, [navigationRequest, updateSession]);

  /**
   * Invalidate selected result ownership before changing explicit split.
   *
   * Args:
   *   split: New explicit split string, still subject to backend validation.
   */
  const changeSplit = (split: string) => {
    validationAbort.current?.abort();
    dryRunAbort.current?.abort();
    updateSession((current) => setBenchmarkAnalysisSplit(current, split));
    setValidationError(null);
    setDryRunError(null);
    setStaleMessage("Split 已变化；请对新输入显式重新分析。");
  };

  /**
   * Toggle one safely discovered task identity for dry-run only.
   *
   * Args:
   *   taskId: Best-effort discovered task identity to add or remove.
   */
  const toggleTask = (taskId: string) => {
    dryRunAbort.current?.abort();
    updateSession((current) => setBenchmarkAnalysisTasks(
      current,
      current.taskIds.includes(taskId)
        ? current.taskIds.filter((item) => item !== taskId)
        : [...current.taskIds, taskId],
    ));
    setDryRunError(null);
    setStaleMessage("Task scope 已变化；此前 dry-run 已失效。");
  };

  /**
   * Submit validation against the exact active clean baseline owner.
   *
   * Returns:
   *   A promise that settles after the strict result is accepted or discarded.
   */
  const validate = async () => {
    const current = sessionRef.current;
    if (!baseGate.allowed || !splitPattern.test(current.split)) return;
    validationAbort.current?.abort();
    const controller = new AbortController();
    validationAbort.current = controller;
    const owner = benchmarkValidationRequestOwner(current);
    setValidationError(null);
    setStaleMessage(null);
    try {
      const result = await validateCommand.mutateAsync({
        draftId: owner.draftId,
        request: {
          schemaVersion: 1,
          revisionId: owner.revisionId,
          split: owner.split,
        },
        signal: controller.signal,
      });
      updateSession((active) => acceptBenchmarkValidationResult(active, owner, result));
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof StudioApiError && error.status === 409) {
        updateSession(invalidateBenchmarkAnalysisResults);
        setStaleMessage("服务端 current revision 已推进；分析结果已丢弃，请 Reload Remote。");
        onStaleConflict(error.currentRevisionId);
        return;
      }
      setValidationError(error instanceof Error ? error.message : "Validation failed");
    }
  };

  /**
   * Submit deterministic dry-run for exact task and frozen Agent inputs.
   *
   * Returns:
   *   A promise that settles after the strict plan is accepted or discarded.
   */
  const dryRun = async () => {
    const current = sessionRef.current;
    if (
      !baseGate.allowed
      || !splitPattern.test(current.split)
      || current.agentRevisions.length === 0
    ) return;
    dryRunAbort.current?.abort();
    const controller = new AbortController();
    dryRunAbort.current = controller;
    const owner = benchmarkDryRunRequestOwner(current);
    setDryRunError(null);
    setStaleMessage(null);
    try {
      const result = await dryRunCommand.mutateAsync({
        draftId: owner.draftId,
        request: {
          schemaVersion: 1,
          revisionId: owner.revisionId,
          split: owner.split,
          taskIds: owner.taskIds,
          agentRevisions: owner.agentRevisions.map((item) => ({
            agentId: item.agentId,
            revisionId: item.revisionId,
          })),
        },
        signal: controller.signal,
      });
      updateSession((active) => acceptBenchmarkDryRunResult(active, owner, result));
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof StudioApiError && error.status === 409) {
        updateSession(invalidateBenchmarkAnalysisResults);
        setStaleMessage("服务端 current revision 已推进；dry-run 已丢弃，请 Reload Remote。");
        onStaleConflict(error.currentRevisionId);
        return;
      }
      setDryRunError(error instanceof Error ? error.message : "Dry-run failed");
    }
  };

  /**
   * Convert one diagnostic into a workbench-owned navigation request.
   *
   * Args:
   *   diagnostic: Strict server-provided member, field, and scoped identity facts.
   */
  const navigateDiagnostic = (diagnostic: BenchmarkAnalysisDiagnostic) => {
    const contentDiagnostic =
      diagnostic.memberKind === "resource"
      && diagnostic.resourceId !== null
      && diagnostic.code.includes("content");
    const target = diagnostic.memberKind === "agent"
      ? "agent"
      : contentDiagnostic
        ? "resource"
        : "definition";
    navigationSequence.current += 1;
    onDiagnosticNavigate({
      requestId: navigationSequence.current,
      target,
      memberKind: diagnostic.memberKind,
      memberPath: diagnostic.memberPath,
      resourceId: diagnostic.resourceId,
      agentId: diagnostic.agentId,
      revisionId: diagnostic.revisionId,
      fieldPath: [...diagnostic.fieldPath],
    });
  };

  const validationEnabled = gate.allowed && splitPattern.test(session.split);
  const dryRunEnabled = validationEnabled && session.agentRevisions.length > 0;
  return (
    <div className="grid min-h-0 flex-1 gap-0 lg:grid-cols-[20rem_minmax(30rem,1fr)_19rem]">
      <aside className="min-h-0 overflow-auto border-r border-[var(--zx-divider-ui)] p-4">
        <h2 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">
          Analysis inputs
        </h2>
        <p className="mt-1 font-mono text-[9px] text-[color:var(--zx-text-muted)]">
          revision {revision.ordinal} · {revision.revisionId}
        </p>
        <label className="mt-4 grid gap-1 text-[10px] font-semibold text-[color:var(--zx-text-muted)]">
          Explicit split
          <input
            aria-label="Explicit split"
            className={inputClass}
            list="benchmark-analysis-splits"
            value={session.split}
            onChange={(event) => changeSplit(event.target.value)}
          />
          <datalist id="benchmark-analysis-splits">
            {splitSuggestions.map((split) => <option key={split} value={split} />)}
          </datalist>
        </label>
        {!splitPattern.test(session.split) ? (
          <p className="mt-2 text-[10px] text-rose-400">Split 必须是非空的 bounded stable name。</p>
        ) : null}

        <section className="mt-5">
          <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-muted)]">
            Task scope
          </h3>
          <button
            type="button"
            onClick={() => {
              dryRunAbort.current?.abort();
              updateSession((current) => setBenchmarkAnalysisTasks(current, []));
              setDryRunError(null);
            }}
            className="mt-2 text-[10px] text-[color:var(--zx-primary)]"
          >
            Use entire split ({session.taskIds.length === 0 ? "active" : "reset"})
          </button>
          <div className="mt-2 max-h-40 space-y-1 overflow-auto">
            {taskCandidates.map((taskId) => (
              <label key={taskId} className="flex items-center gap-2 text-[10px]">
                <input
                  type="checkbox"
                  checked={session.taskIds.includes(taskId)}
                  onChange={() => toggleTask(taskId)}
                />
                <span className="truncate font-mono">{taskId}</span>
              </label>
            ))}
            {taskCandidates.length === 0 ? (
              <p className="text-[10px] text-[color:var(--zx-text-muted)]">
                未发现可安全枚举的 Task；dry-run 默认使用整个 split，后端仍是权威。
              </p>
            ) : null}
          </div>
        </section>

        <section className="mt-5">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-muted)]">
              Frozen Agent revisions ({session.agentRevisions.length}/16)
            </h3>
            <button type="button" className="text-[9px] text-[color:var(--zx-primary)]" onClick={() => void agents.refetch()}>
              Refresh
            </button>
          </div>
          <div className="mt-2 max-h-52 space-y-2 overflow-auto">
            {agents.items.map((agent) => {
              const frozen = session.agentRevisions.find((item) => item.agentId === agent.agentId);
              const drifted = frozen && frozen.revisionId !== agent.currentRevisionId;
              return (
                <div key={agent.agentId} className="rounded-lg border border-[var(--zx-border-light)] p-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-[10px] font-semibold">{agent.name}</p>
                      <p className="truncate font-mono text-[8px] text-[color:var(--zx-text-muted)]">
                        {frozen?.revisionId ?? agent.currentRevisionId ?? "no saved revision"}
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={agent.currentRevisionId === null}
                      onClick={() => {
                        dryRunAbort.current?.abort();
                        updateSession((current) => frozen
                          ? removeFrozenAgentRevision(current, agent.agentId)
                          : addFrozenAgentRevision(current, agent));
                        setDryRunError(null);
                      }}
                      className="text-[9px] font-semibold text-[color:var(--zx-primary)] disabled:opacity-40"
                    >
                      {frozen ? "Remove" : "Freeze"}
                    </button>
                  </div>
                  {drifted ? (
                    <p className="mt-1 text-[9px] text-amber-400">Current 已推进；旧 pair 保持冻结，需显式重选。</p>
                  ) : null}
                </div>
              );
            })}
          </div>
          {agents.hasNextPage ? (
            <button type="button" className="mt-2 text-[10px] text-[color:var(--zx-primary)]" onClick={() => void agents.fetchNextPage()}>
              Load more Agents
            </button>
          ) : null}
          {agents.isError ? <p className="mt-2 text-[10px] text-rose-400">Agent 列表读取失败。</p> : null}
        </section>

        <div className="mt-5 grid grid-cols-2 gap-2">
          <button type="button" onClick={() => void validate()} disabled={!validationEnabled} className="rounded-lg border border-[var(--zx-border-light)] px-3 py-2 text-[10px] font-semibold disabled:opacity-40">
            {validateCommand.isPending ? "Validating…" : "Validate"}
          </button>
          <button type="button" onClick={() => void dryRun()} disabled={!dryRunEnabled} className="rounded-lg bg-[var(--zx-primary)] px-3 py-2 text-[10px] font-semibold text-white disabled:opacity-40">
            {dryRunCommand.isPending ? "Planning…" : "Dry-run"}
          </button>
        </div>
        {!gate.allowed ? <p className="mt-3 text-[10px] text-amber-400">{gate.message}</p> : null}
      </aside>

      <main className="min-h-0 overflow-auto p-5">
        {staleMessage ? <div role="status" className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-[10px] text-amber-300">{staleMessage}</div> : null}
        <ValidationPanel
          pending={validateCommand.isPending}
          error={validationError}
          result={session.validationResult}
          onNavigate={navigateDiagnostic}
        />
        <div className="mt-5">
          <DryRunPanel
            pending={dryRunCommand.isPending}
            error={dryRunError}
            result={session.dryRunResult}
            page={session.schedulePage}
            onPage={(schedulePage) => updateSession((current) => ({ ...current, schedulePage }))}
            onNavigate={navigateDiagnostic}
          />
        </div>
      </main>

      <aside className="min-h-0 overflow-auto border-l border-[var(--zx-divider-ui)] p-4">
        <h2 className="text-[12px] font-semibold text-[color:var(--zx-text-title)]">Evidence boundary</h2>
        <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-[10px] leading-5 text-amber-200">
          <strong className="block">executionEvidence = false</strong>
          本页面只展示 saved revision 的 definition-level validation 与 deterministic planning。
          没有调用 initializer、evaluator、Agent、设备、模型或 Worker，也没有创建输出文件。
        </div>
        <dl className="mt-4 space-y-3 text-[10px]">
          <Fact label="Authoring status" value="unvalidated" />
          <Fact label="Durable analysis" value="none" />
          <Fact label="Contract Test" value="not run" />
          <Fact label="Publication" value="not performed" />
          <Fact label="Runtime / Android" value="not evidenced" />
        </dl>
        {session.focusedAgentId ? (
          <div className="mt-5 rounded-lg border border-[var(--zx-border-light)] p-3">
            <p className="text-[9px] uppercase text-[color:var(--zx-text-muted)]">Diagnostic target</p>
            <p className="mt-1 break-all font-mono text-[9px]">{session.focusedAgentId}</p>
            {session.fieldPathBreadcrumb.length > 0 ? (
              <p className="mt-2 break-all font-mono text-[9px] text-amber-300">
                {formatFieldPath(session.fieldPathBreadcrumb)}
              </p>
            ) : null}
          </div>
        ) : null}
      </aside>
    </div>
  );
}

/**
 * Render revision-bound validation lifecycle and partial identities.
 *
 * Args:
 *   props: Independent pending/error/result facts and diagnostic callback.
 *
 * Returns:
 *   The bounded semantic-versus-transport validation panel.
 */
function ValidationPanel({
  pending,
  error,
  result,
  onNavigate,
}: {
  pending: boolean;
  error: string | null;
  result: BenchmarkValidationResult | null;
  onNavigate: (diagnostic: BenchmarkAnalysisDiagnostic) => void;
}) {
  return (
    <section className={cardClass}>
      <h2 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">Validation</h2>
      {pending ? <p className="mt-3 text-[11px]">Analyzing the exact saved revision…</p> : null}
      {error ? <p className="mt-3 text-[11px] text-rose-400">Transport failure: {error}</p> : null}
      {!pending && !error && !result ? <p className="mt-3 text-[11px] text-[color:var(--zx-text-muted)]">Not run. Validation only starts after the explicit command.</p> : null}
      {result ? (
        <>
          <p className={`mt-3 text-[12px] font-semibold ${result.valid ? "text-emerald-400" : "text-rose-400"}`}>
            {result.valid ? "Definition valid for selected split" : "Definition invalid"}
          </p>
          <IdentityGrid identities={result.identities} />
          <Diagnostics diagnostics={result.diagnostics} truncated={result.diagnosticsTruncated} onNavigate={onNavigate} />
          <Unverified items={result.unverifiedChecks} />
        </>
      ) : null}
    </section>
  );
}

/**
 * Render deterministic planning facts with a bounded schedule page.
 *
 * Args:
 *   props: Dry-run lifecycle, complete result, current page, and callbacks.
 *
 * Returns:
 *   One result panel that renders at most 50 schedule rows at a time.
 */
function DryRunPanel({
  pending,
  error,
  result,
  page,
  onPage,
  onNavigate,
}: {
  pending: boolean;
  error: string | null;
  result: BenchmarkDryRunResult | null;
  page: number;
  onPage: (page: number) => void;
  onNavigate: (diagnostic: BenchmarkAnalysisDiagnostic) => void;
}) {
  const pageCount = result ? Math.max(1, Math.ceil(result.schedule.length / schedulePageSize)) : 1;
  const safePage = Math.min(page, pageCount - 1);
  const rows = result?.schedule.slice(
    safePage * schedulePageSize,
    (safePage + 1) * schedulePageSize,
  ) ?? [];
  return (
    <section className={cardClass}>
      <h2 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">Side-effect-free dry-run</h2>
      {pending ? <p className="mt-3 text-[11px]">Building a deterministic definition-level plan…</p> : null}
      {error ? <p className="mt-3 text-[11px] text-rose-400">Transport/capacity failure: {error}</p> : null}
      {!pending && !error && !result ? <p className="mt-3 text-[11px] text-[color:var(--zx-text-muted)]">Not run. Select at least one frozen Agent revision.</p> : null}
      {result ? (
        <div className="mt-4 space-y-4">
          <p className={`text-[12px] font-semibold ${result.ok ? "text-emerald-400" : "text-rose-400"}`}>
            {result.ok ? "Complete bounded plan projected" : "No schedule constructed"}
          </p>
          <IdentityGrid identities={result.identities} />
          {result.agentRevisions.length > 0 ? (
            <section>
              <h3 className="text-[10px] font-semibold uppercase text-[color:var(--zx-text-muted)]">Verified Agent revisions</h3>
              <div className="mt-2 space-y-1">
                {result.agentRevisions.map((item) => (
                  <p key={item.agentId} className="break-all font-mono text-[9px]">
                    {item.agentId} · {item.revisionId} · {item.agentGraphIdentity}
                  </p>
                ))}
              </div>
            </section>
          ) : null}
          {result.budget ? (
            <section>
              <h3 className="text-[10px] font-semibold uppercase text-[color:var(--zx-text-muted)]">Declared budget projection</h3>
              <p className="mt-2 text-[10px]">
                interactions {result.budget.maxInteractions} · activations {result.budget.maxActivations} · timeout {result.budget.timeoutSeconds}s · tokens {result.budget.tokenLimit ?? "not declared"}
              </p>
            </section>
          ) : null}
          {result.fairnessWarnings.length > 0 ? (
            <section className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
              <h3 className="text-[10px] font-semibold text-amber-300">Fairness warnings — not fairness proof</h3>
              {result.fairnessWarnings.map((item) => <p key={item} className="mt-1 text-[10px]">{item}</p>)}
            </section>
          ) : null}
          {result.schedule.length > 0 ? (
            <section>
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-[10px] font-semibold uppercase text-[color:var(--zx-text-muted)]">Complete schedule · {result.schedule.length} entries</h3>
                <div className="flex items-center gap-2 text-[9px]">
                  <button type="button" disabled={safePage === 0} onClick={() => onPage(safePage - 1)}>Previous</button>
                  <span>{safePage + 1}/{pageCount}</span>
                  <button type="button" disabled={safePage + 1 >= pageCount} onClick={() => onPage(safePage + 1)}>Next</button>
                </div>
              </div>
              <div className="mt-2 overflow-auto">
                <table className="w-full text-left text-[9px]">
                  <thead><tr className="text-[color:var(--zx-text-muted)]"><th>repeat</th><th>task</th><th>Agent</th><th>seed</th></tr></thead>
                  <tbody>{rows.map((row, index) => (
                    <tr key={`${row.sharedInstanceKey}:${row.agentId}:${index}`} className="border-t border-[var(--zx-divider-ui)]">
                      <td className="py-1">{row.repeat}</td><td className="py-1 font-mono">{row.taskId}</td><td className="py-1 font-mono">{row.agentId}</td><td className="py-1">{row.seed}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </section>
          ) : null}
          {result.outputLayout ? (
            <section>
              <h3 className="text-[10px] font-semibold uppercase text-[color:var(--zx-text-muted)]">Relative output layout — no files created</h3>
              {Object.entries(result.outputLayout).map(([key, value]) => <p key={key} className="mt-1 break-all font-mono text-[9px]">{key}: {value}</p>)}
            </section>
          ) : null}
          <Diagnostics diagnostics={result.diagnostics} truncated={result.diagnosticsTruncated} onNavigate={onNavigate} />
          <Unverified items={result.unverifiedChecks} />
          <div className="rounded-lg border border-amber-500/30 p-3 text-[10px] text-amber-300">
            executionEvidence=false · schedule preview does not prove current Worker cardinality or runtime success.
          </div>
        </div>
      ) : null}
    </section>
  );
}

/**
 * Render independently gated identity rows without synthetic placeholders.
 *
 * Args:
 *   identities: Partial identities established by the backend phases.
 *
 * Returns:
 *   A factual identity grid that marks unavailable values as not established.
 */
function IdentityGrid({ identities }: { identities: BenchmarkAnalysisIdentities }) {
  return (
    <dl className="mt-4 grid gap-2 sm:grid-cols-2">
      <Fact label="Package" value={identities.package ?? "not established"} />
      <Fact label="Package content" value={identities.packageContent ?? "not established"} />
      <Fact label="BenchmarkPlan" value={identities.benchmarkPlan ?? "not established"} />
      <Fact label="ExperimentProtocol" value={identities.experimentProtocol ?? "not established"} />
    </dl>
  );
}

/**
 * Render bounded diagnostics and their public navigation intents.
 *
 * Args:
 *   props: Strict diagnostics, truncation fact, and typed navigation callback.
 *
 * Returns:
 *   A diagnostic list or no element when no diagnostic fact exists.
 */
function Diagnostics({
  diagnostics,
  truncated,
  onNavigate,
}: {
  diagnostics: BenchmarkAnalysisDiagnostic[];
  truncated: boolean;
  onNavigate: (diagnostic: BenchmarkAnalysisDiagnostic) => void;
}) {
  if (diagnostics.length === 0 && !truncated) return null;
  return (
    <section className="mt-4">
      <h3 className="text-[10px] font-semibold uppercase text-[color:var(--zx-text-muted)]">
        Diagnostics {truncated ? "· truncated at 100" : ""}
      </h3>
      <div className="mt-2 space-y-2">
        {diagnostics.map((diagnostic, index) => (
          <div key={`${diagnostic.code}:${index}`} className="rounded-lg border border-[var(--zx-border-light)] p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-mono text-[9px]">{diagnostic.severity} · {diagnostic.code}</p>
                <p className="mt-1 text-[10px]">{diagnostic.message}</p>
                <p className="mt-1 break-all font-mono text-[9px] text-[color:var(--zx-text-muted)]">
                  {diagnostic.memberPath ?? diagnostic.memberKind} {formatFieldPath(diagnostic.fieldPath)}
                </p>
              </div>
              <button type="button" onClick={() => onNavigate(diagnostic)} className="shrink-0 text-[9px] font-semibold text-[color:var(--zx-primary)]">
                Navigate
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * Render facts that analysis deliberately did not verify.
 *
 * Args:
 *   items: Bounded backend-provided unverified fact codes.
 *
 * Returns:
 *   A warning block or no element for an empty collection.
 */
function Unverified({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
      <h3 className="text-[10px] font-semibold text-amber-300">Explicitly unverified</h3>
      {items.map((item) => <p key={item} className="mt-1 font-mono text-[9px]">{item}</p>)}
    </section>
  );
}

/**
 * Render one factual label/value pair with bounded wrapping.
 *
 * Args:
 *   props: Display label and already-bounded factual value.
 *
 * Returns:
 *   One description-list row.
 */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[9px] uppercase tracking-[0.1em] text-[color:var(--zx-text-muted)]">{label}</dt>
      <dd className="mt-1 break-all font-mono text-[9px]">{value}</dd>
    </div>
  );
}

/**
 * Format a safe mixed field path as a truthful breadcrumb.
 *
 * Args:
 *   path: Strict parsed string/index field segments.
 *
 * Returns:
 *   A display-only breadcrumb without DOM selector semantics.
 */
function formatFieldPath(path: Array<string | number>): string {
  if (path.length === 0) return "";
  return path.map((item) => typeof item === "number" ? `[${item}]` : `.${item}`).join("");
}
