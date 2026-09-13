import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { StudioApiError } from "@/shared/api";
import {
  useBenchmarkDraft,
  useSaveBenchmarkDraftRevision,
  type BenchmarkAuthoringContentMutationOutcome,
  type BenchmarkDraftDetail,
} from "@/entities/benchmark-authoring";
import {
  BenchmarkDefinitionEditor,
  benchmarkDefinitionEditorStatus,
  normalizeAuthoringInventory,
  prepareBenchmarkSaveIntent,
  useBenchmarkDefinitionEditorStore,
  type BenchmarkSaveIntent,
} from "@/features/benchmark-definition-editor";
import {
  BenchmarkResourceEditor,
  benchmarkResourceMutationGate,
} from "@/features/benchmark-resource-editor";
import {
  BenchmarkValidationDryRunView,
  type BenchmarkDiagnosticNavigationIntent,
  type BenchmarkValidationNavigationRequest,
} from "@/features/benchmark-validation-dry-run";
import {
  BenchmarkContractTestsView,
  type BenchmarkContractDiagnosticNavigationIntent,
} from "@/features/benchmark-contract-tests";
import { BenchmarkReleaseView } from "@/features/benchmark-release";

type BenchmarkWorkbenchMode =
  | "definition"
  | "resources"
  | "validation"
  | "contract-tests"
  | "release";

type WorkbenchDiagnosticNavigationIntent =
  | BenchmarkDiagnosticNavigationIntent
  | BenchmarkContractDiagnosticNavigationIntent;

type BenchmarkDefinitionWorkbenchProps = {
  draftId: string;
};

/**
 * Compose authoritative draft queries with browser-local authoring features.
 *
 * Args:
 *   props: Stable draft identity owned by the route.
 *
 * Returns:
 *   The URL-owned Definition, Resources, or Validation workbench.
 */
export function BenchmarkDefinitionWorkbench({
  draftId,
}: BenchmarkDefinitionWorkbenchProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const mode = parseWorkbenchMode(searchParams.get("mode"));
  const draftQuery = useBenchmarkDraft(draftId);
  const saveCommand = useSaveBenchmarkDraftRevision();
  const hydrate = useBenchmarkDefinitionEditorStore((state) => state.hydrate);
  const reloadSession = useBenchmarkDefinitionEditorStore((state) => state.reload);
  const adoptSavedRevision = useBenchmarkDefinitionEditorStore(
    (state) => state.adoptSavedRevision,
  );
  const reset = useBenchmarkDefinitionEditorStore((state) => state.reset);
  const clear = useBenchmarkDefinitionEditorStore((state) => state.clear);
  const setConflict = useBenchmarkDefinitionEditorStore(
    (state) => state.setConflict,
  );
  const setSavePending = useBenchmarkDefinitionEditorStore(
    (state) => state.setSavePending,
  );
  const focusMember = useBenchmarkDefinitionEditorStore(
    (state) => state.focusMember,
  );
  const state = useBenchmarkDefinitionEditorStore();
  const status = benchmarkDefinitionEditorStatus(state);
  const saveIntent = useRef<BenchmarkSaveIntent | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [contentPending, setContentPending] = useState(false);
  const [analysisPending, setAnalysisPending] = useState(false);
  const [contractTestPending, setContractTestPending] = useState(false);
  const [releasePending, setReleasePending] = useState(false);
  const [analysisEpoch, setAnalysisEpoch] = useState(0);
  const [resourceSelection, setResourceSelection] = useState<{
    requestId: number;
    revisionId: string;
    resourceId: string;
  } | null>(null);
  const [validationNavigation, setValidationNavigation] =
    useState<BenchmarkValidationNavigationRequest | null>(null);

  useEffect(() => {
    if (draftQuery.data?.currentRevision) {
      hydrate(draftQuery.data.currentRevision);
    }
  }, [draftQuery.data, hydrate]);

  useEffect(() => {
    /** Protect browser close/refresh while parsed or raw work is dirty. */
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      const current = useBenchmarkDefinitionEditorStore.getState();
      if (!benchmarkDefinitionEditorStatus(current).dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    /** Guard in-app anchor navigation in the BrowserRouter integration. */
    const onDocumentClick = (event: MouseEvent) => {
      if (!benchmarkDefinitionEditorStatus(
        useBenchmarkDefinitionEditorStore.getState(),
      ).dirty) return;
      const target = event.target;
      const anchor =
        target instanceof Element ? target.closest<HTMLAnchorElement>("a[href]") : null;
      if (!anchor || anchor.target === "_blank" || event.defaultPrevented) return;
      if (!window.confirm("离开会丢失未保存或未应用的本地修改，是否继续？")) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("click", onDocumentClick, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("click", onDocumentClick, true);
    };
  }, []);

  useEffect(
    () => () => {
      clear();
    },
    [clear],
  );

  /** Discard local work and adopt the latest authoritative query response. */
  const reloadRemote = async () => {
    if (
      status.dirty
      && !window.confirm("Reload Remote 会丢弃所有本地修改，是否继续？")
    ) {
      return;
    }
    const result = await draftQuery.refetch();
    if (result.data?.currentRevision) {
      reloadSession(result.data.currentRevision);
      saveIntent.current = null;
      setAnalysisEpoch((current) => current + 1);
      setMessage("已加载远端 current revision。");
    }
  };

  /** Restore the current local immutable baseline without a server command. */
  const resetLocal = () => {
    if (status.dirty && !window.confirm("Reset 会放弃当前本地修改，是否继续？")) {
      return;
    }
    reset();
    saveIntent.current = null;
    setAnalysisEpoch((current) => current + 1);
    setMessage("已重置到本地 baseline；没有创建 revision。");
  };

  /** Append one immutable revision, preserving uncertain retry identity. */
  const save = async () => {
    const current = useBenchmarkDefinitionEditorStore.getState();
    const currentStatus = benchmarkDefinitionEditorStatus(current);
    if (
      !currentStatus.saveable
      || contentPending
      || analysisPending
      || contractTestPending
      || releasePending
      || !current.workingDocument
      || !current.baselineRevision
    ) {
      return;
    }
    const prepared = prepareBenchmarkSaveIntent(saveIntent.current, {
      draftId,
      baseRevisionId: current.baselineRevision.revisionId,
      document: normalizeAuthoringInventory(current.workingDocument),
    });
    saveIntent.current = prepared;
    setSavePending(true);
    setMessage(null);
    try {
      const response = await saveCommand.mutateAsync(prepared);
      adoptSavedRevision(response.revision);
      saveIntent.current = null;
      setMessage(
        response.created
          ? `Revision ${response.revision.ordinal} 已保存；状态仍为 unvalidated。`
          : `已确认此前提交的 Revision ${response.revision.ordinal}。`,
      );
    } catch (error) {
      if (error instanceof StudioApiError && error.status === 409) {
        setConflict(error.currentRevisionId);
        saveIntent.current = null;
        setMessage("保存冲突：本地内容已保留，不会自动合并或覆盖远端。");
      } else {
        setMessage(
          `保存结果未确认：${error instanceof Error ? error.message : "unknown"}。可用相同内容重试。`,
        );
      }
    } finally {
      setSavePending(false);
    }
  };

  /** Select one bounded reloadable workbench mode without changing ownership. */
  const selectMode = (nextMode: BenchmarkWorkbenchMode) => {
    const next = new URLSearchParams(searchParams);
    next.set("mode", nextMode);
    setSearchParams(next, { replace: true });
  };

  /** Adopt only the authoritative current revision returned by cache reconciliation. */
  const handleContentSuccess = useCallback(
    (outcome: BenchmarkAuthoringContentMutationOutcome) => {
      adoptSavedRevision(outcome.currentRevision);
      setMessage(
        outcome.historicalRetry
          ? `已确认较早的 ${outcome.result.operation} 命令；已重新加载当前 Revision ${outcome.currentRevision.ordinal}。`
          : `${outcome.result.operation} 已创建 immutable Revision ${outcome.currentRevision.ordinal}；状态仍为 unvalidated。`,
      );
    },
    [adoptSavedRevision],
  );

  /** Preserve the definition session and expose a content revision conflict. */
  const handleContentConflict = useCallback(
    (revisionId: string | null) => {
      setConflict(revisionId);
      setMessage("资源命令冲突：本地文件和表单已保留，请显式 Reload Remote。");
    },
    [setConflict],
  );

  /** Mirror resource pending state only for cross-feature command exclusion. */
  const handleContentPending = useCallback((pending: boolean) => {
    setContentPending(pending);
  }, []);

  /** Mirror analysis pending state for cross-feature command exclusion. */
  const handleAnalysisPending = useCallback((pending: boolean) => {
    setAnalysisPending(pending);
  }, []);

  /** Mirror Contract Test pending state for mutual command exclusion. */
  const handleContractTestPending = useCallback((pending: boolean) => {
    setContractTestPending(pending);
  }, []);

  /** Mirror Package release pending state for mutual command exclusion. */
  const handleReleasePending = useCallback((pending: boolean) => {
    setReleasePending(pending);
  }, []);

  if (draftQuery.isPending) {
    return <WorkbenchState title="正在加载 Benchmark draft…" />;
  }
  if (draftQuery.isError) {
    const notFound =
      draftQuery.error instanceof StudioApiError
      && draftQuery.error.status === 404;
    return (
      <WorkbenchState
        title={notFound ? "Benchmark draft 不存在" : "无法读取 Benchmark draft"}
        detail={draftQuery.error.message}
        action={() => void draftQuery.refetch()}
      />
    );
  }
  const resourceGate = benchmarkResourceMutationGate({
    definitionStatus: status,
    baselineRevisionId: state.baselineRevision?.revisionId ?? null,
    queryCurrentRevisionId: draftQuery.data.draft.currentRevisionId,
    conflictRevisionId: state.conflictRevisionId,
    remoteMayBeNewer: state.remoteMayBeNewer,
    contentPending:
      contentPending || analysisPending || contractTestPending || releasePending,
  });
  const currentRevision =
    state.baselineRevision ?? draftQuery.data.currentRevision;
  /**
   * Coordinate one diagnostic without exposing peer-feature internals.
   *
   * Args:
   *   intent: Typed safe member/field/scoped-identity navigation request.
   */
  const handleDiagnosticNavigate = (intent: WorkbenchDiagnosticNavigationIntent) => {
    if (intent.target === "agent" && intent.agentId) {
      setValidationNavigation({
        requestId: intent.requestId,
        agentId: intent.agentId,
        fieldPath: [...intent.fieldPath],
      });
      selectMode("validation");
      return;
    }
    if (intent.target === "resource" && intent.resourceId) {
      setResourceSelection({
        requestId: intent.requestId,
        revisionId: currentRevision.revisionId,
        resourceId: intent.resourceId,
      });
      selectMode("resources");
      return;
    }
    const memberKey = diagnosticMemberKey(intent);
    focusMember(memberKey, intent.fieldPath);
    selectMode("definition");
  };

  /**
   * Preserve conflict ownership surfaced by exact-current analysis.
   *
   * Args:
   *   revisionId: Safe current revision identity, or null when unavailable.
   */
  const handleAnalysisConflict = (revisionId: string | null) => {
    setConflict(revisionId);
    setMessage("分析期间 current revision 已推进；结果已丢弃，请显式 Reload Remote。");
  };
  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <WorkbenchHeader
        detail={draftQuery.data}
        status={status}
        conflictRevisionId={state.conflictRevisionId}
        remoteMayBeNewer={state.remoteMayBeNewer}
        mode={mode}
        contentPending={
          contentPending || analysisPending || contractTestPending || releasePending
        }
        message={message}
        onSave={() => void save()}
        onReset={resetLocal}
        onReload={() => void reloadRemote()}
        onModeChange={selectMode}
      />
      {mode === "definition" ? (
        <BenchmarkDefinitionEditor revision={currentRevision} />
      ) : mode === "resources" ? (
        <BenchmarkResourceEditor
          revision={currentRevision}
          gate={resourceGate}
          onMutationPendingChange={handleContentPending}
          onCommandSuccess={handleContentSuccess}
          onConflict={handleContentConflict}
          selectionRequest={resourceSelection}
        />
      ) : mode === "validation" ? (
        <BenchmarkValidationDryRunView
          key={`${currentRevision.revisionId}:${analysisEpoch}`}
          revision={currentRevision}
          gateInput={{
            definitionStatus: status,
            baselineRevisionId: state.baselineRevision?.revisionId ?? null,
            queryCurrentRevisionId: draftQuery.data.draft.currentRevisionId,
            conflictRevisionId: state.conflictRevisionId,
            remoteMayBeNewer: state.remoteMayBeNewer,
            contentPending: contentPending || contractTestPending || releasePending,
          }}
          navigationRequest={validationNavigation}
          onAnalysisPendingChange={handleAnalysisPending}
          onDiagnosticNavigate={handleDiagnosticNavigate}
          onStaleConflict={handleAnalysisConflict}
        />
      ) : mode === "contract-tests" ? (
        <BenchmarkContractTestsView
          key={`${currentRevision.revisionId}:${analysisEpoch}`}
          revision={currentRevision}
          gateInput={{
            definitionStatus: status,
            baselineRevisionId: state.baselineRevision?.revisionId ?? null,
            queryCurrentRevisionId: draftQuery.data.draft.currentRevisionId,
            conflictRevisionId: state.conflictRevisionId,
            remoteMayBeNewer: state.remoteMayBeNewer,
            contentPending: contentPending || releasePending,
            peerAnalysisPending: analysisPending,
          }}
          onPendingChange={handleContractTestPending}
          onDiagnosticNavigate={handleDiagnosticNavigate}
          onStaleConflict={handleAnalysisConflict}
        />
      ) : (
        <BenchmarkReleaseView
          revision={currentRevision}
          gateInput={{
            dirty: status.dirty,
            hasBufferError: status.hasBufferError,
            hasUnappliedBuffer: status.hasUnappliedBuffer,
            baselineRevisionId: state.baselineRevision?.revisionId ?? null,
            queryCurrentRevisionId: draftQuery.data.draft.currentRevisionId,
            conflictRevisionId: state.conflictRevisionId,
            remoteMayBeNewer: state.remoteMayBeNewer,
            peerPending: contentPending || analysisPending || contractTestPending,
          }}
          onPendingChange={handleReleasePending}
        />
      )}
    </div>
  );
}

/** Render all save/reset/reload facts at the workbench action boundary. */
function WorkbenchHeader({
  detail,
  status,
  conflictRevisionId,
  remoteMayBeNewer,
  mode,
  contentPending,
  message,
  onSave,
  onReset,
  onReload,
  onModeChange,
}: {
  detail: BenchmarkDraftDetail;
  status: ReturnType<typeof benchmarkDefinitionEditorStatus>;
  conflictRevisionId: string | null;
  remoteMayBeNewer: boolean;
  mode: BenchmarkWorkbenchMode;
  contentPending: boolean;
  message: string | null;
  onSave: () => void;
  onReset: () => void;
  onReload: () => void;
  onModeChange: (mode: BenchmarkWorkbenchMode) => void;
}) {
  return (
    <header className="shrink-0 border-b border-[var(--zx-divider-ui)] px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[15px] font-semibold text-[color:var(--zx-text-title)]">
              {detail.draft.name}
            </h1>
            <span className="rounded-full bg-amber-500/15 px-2 py-1 text-[9px] font-semibold text-amber-400">
              unvalidated
            </span>
            {status.dirty ? (
              <span className="text-[10px] font-semibold text-amber-400">dirty</span>
            ) : (
              <span className="text-[10px] text-emerald-400">clean</span>
            )}
          </div>
          <p className="mt-1 font-mono text-[9px] text-[color:var(--zx-text-muted)]">
            {detail.draft.draftId}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="flex rounded-lg border border-[var(--zx-border-light)] p-0.5">
            {(["definition", "resources", "validation", "contract-tests", "release"] as const).map((item) => (
              <button
                key={item}
                type="button"
                aria-pressed={mode === item}
                onClick={() => onModeChange(item)}
                className={[
                  "rounded-md px-3 py-1.5 text-[10px]",
                  mode === item
                    ? "bg-[var(--zx-primary-soft)] font-semibold text-[color:var(--zx-text-title)]"
                    : "text-[color:var(--zx-text-muted)]",
                ].join(" ")}
              >
                {item === "definition"
                  ? "Definition"
                  : item === "resources"
                    ? "Resources"
                    : item === "validation"
                      ? "Validation"
                      : item === "contract-tests"
                        ? "Contract Tests"
                        : "Release"}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onReset}
            disabled={!status.dirty || contentPending}
            className="rounded-lg border border-[var(--zx-border-light)] px-3 py-2 text-[11px] text-[color:var(--zx-text-body)] disabled:opacity-40"
          >
            Reset
          </button>
          <button
            type="button"
            onClick={onReload}
            className="rounded-lg border border-[var(--zx-border-light)] px-3 py-2 text-[11px] text-[color:var(--zx-text-body)]"
          >
            Reload Remote
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!status.saveable || contentPending}
            className="rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[11px] font-semibold text-white disabled:opacity-40"
          >
            {status.saveable && !contentPending ? "Save revision" : "Save blocked"}
          </button>
        </div>
      </div>
      {status.hasBufferError || status.hasUnappliedBuffer ? (
        <p className="mt-2 text-[10px] text-amber-400">
          Task JSON 存在无效或未应用的浏览器本地 buffer，保存已阻止。
        </p>
      ) : null}
      {remoteMayBeNewer ? (
        <p className="mt-2 text-[10px] text-amber-400">
          后台查询发现远端可能更新；本地内容未被覆盖，请显式 Reload Remote。
        </p>
      ) : null}
      {conflictRevisionId ? (
        <p role="alert" className="mt-2 text-[10px] text-rose-400">
          Revision conflict · current remote: {conflictRevisionId}
        </p>
      ) : null}
      {message ? (
        <p aria-live="polite" className="mt-2 text-[10px] text-[color:var(--zx-text-muted)]">
          {message}
        </p>
      ) : null}
    </header>
  );
}

/** Parse one bounded workbench mode with a safe definition fallback. */
function parseWorkbenchMode(value: string | null): BenchmarkWorkbenchMode {
  return value === "resources"
    || value === "validation"
    || value === "contract-tests"
    || value === "release"
    ? value
    : "definition";
}

/** Resolve one diagnostic to a stable definition-member selection key. */
function diagnosticMemberKey(intent: WorkbenchDiagnosticNavigationIntent): string {
  if (intent.memberKind === "task" && intent.memberPath) {
    return `task:${intent.memberPath}`;
  }
  if (intent.memberKind === "protocol" && intent.memberPath) {
    return `protocol:${intent.memberPath}`;
  }
  if (intent.memberKind === "resource" && intent.resourceId) {
    return `resource:${intent.resourceId}`;
  }
  return "manifest";
}

/** Render bounded loading/error/not-found workbench states. */
function WorkbenchState({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: () => void;
}) {
  return (
    <div className="flex h-full items-center justify-center p-8 text-center">
      <div>
        <h1 className="text-[15px] font-semibold text-[color:var(--zx-text-title)]">
          {title}
        </h1>
        {detail ? (
          <p className="mt-2 text-[11px] text-[color:var(--zx-text-muted)]">
            {detail}
          </p>
        ) : null}
        {action ? (
          <button
            type="button"
            onClick={action}
            className="mt-4 rounded-lg border border-[var(--zx-primary-border)] px-3 py-2 text-[11px]"
          >
            Retry
          </button>
        ) : null}
      </div>
    </div>
  );
}
