import { useEffect, useMemo, useRef, useState } from "react";
import {
  useBenchmarkAuthoringResourceHead,
  useRemoveBenchmarkAuthoringResource,
  useReplaceBenchmarkAuthoringResource,
  useUploadBenchmarkAuthoringResource,
  type BenchmarkAuthoringContentMutationOutcome,
  type BenchmarkAuthoringResource,
  type BenchmarkAuthoringRevision,
} from "@/entities/benchmark-authoring";
import { StudioApiError } from "@/shared/api";
import {
  prepareBenchmarkResourceIntent,
  type BenchmarkResourceCommandIntent,
  type BenchmarkResourceCommandSemantic,
} from "../model/benchmarkResourceIntents";
import type { BenchmarkResourceMutationGate } from "../model/benchmarkResourceGate";
import { projectBenchmarkResourceAvailability } from "../model/benchmarkResourceAvailability";
import {
  createBenchmarkResourceSession,
  reconcileBenchmarkResourceSession,
} from "../model/benchmarkResourceSession";

export type BenchmarkResourceEditorProps = {
  revision: BenchmarkAuthoringRevision;
  gate: BenchmarkResourceMutationGate;
  onMutationPendingChange: (pending: boolean) => void;
  onCommandSuccess: (outcome: BenchmarkAuthoringContentMutationOutcome) => void;
  onConflict: (revisionId: string | null) => void;
  selectionRequest?: {
    requestId: number;
    revisionId: string;
    resourceId: string;
  } | null;
};

type UploadFields = {
  resourceId: string;
  kind: "asset" | "ground_truth";
  path: string;
  mediaType: string;
};

const emptyUpload: UploadFields = {
  resourceId: "",
  kind: "asset",
  path: "assets/",
  mediaType: "application/octet-stream",
};

const cardClass =
  "rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-4";
const inputClass = "zx-control px-3 py-2 text-[12px]";
const labelClass =
  "grid gap-1 text-[10px] font-semibold text-[color:var(--zx-text-muted)]";

/**
 * Render managed assets and file-backed ground truth for one saved revision.
 *
 * Args:
 *   props: Exact revision, mutation gate, workbench callbacks, and optional
 *   current-revision-scoped controlled selection request.
 *
 * Returns:
 *   The resource-owned inventory, availability, and mutation surface.
 */
export function BenchmarkResourceEditor({
  revision,
  gate,
  onMutationPendingChange,
  onCommandSuccess,
  onConflict,
  selectionRequest = null,
}: BenchmarkResourceEditorProps) {
  const resources = useMemo(
    () => [...revision.document.resources].sort((left, right) =>
      left.id.localeCompare(right.id)),
    [revision],
  );
  const [session, setSession] = useState(createBenchmarkResourceSession);
  const [upload, setUpload] = useState<UploadFields>(emptyUpload);
  const [replaceMediaType, setReplaceMediaType] = useState("");
  const retryIntent = useRef<BenchmarkResourceCommandIntent | null>(null);
  const uploadCommand = useUploadBenchmarkAuthoringResource();
  const replaceCommand = useReplaceBenchmarkAuthoringResource();
  const removeCommand = useRemoveBenchmarkAuthoringResource();
  const contentPending =
    uploadCommand.isPending
    || replaceCommand.isPending
    || removeCommand.isPending;

  useEffect(() => {
    setSession((current) =>
      reconcileBenchmarkResourceSession(current, {
        draftId: revision.draftId,
        revisionId: revision.revisionId,
        resourceIds: resources.map((resource) => resource.id),
      }));
    setUpload(emptyUpload);
    setReplaceMediaType("");
    retryIntent.current = null;
  }, [resources, revision.draftId, revision.revisionId]);

  useEffect(() => {
    if (
      selectionRequest === null
      || selectionRequest.revisionId !== revision.revisionId
      || !resources.some((resource) => resource.id === selectionRequest.resourceId)
    ) return;
    const resource = resources.find((item) => item.id === selectionRequest.resourceId)!;
    retryIntent.current = null;
    setReplaceMediaType(resource.mediaType);
    setSession((current) => ({
      ...current,
      selectedResourceId: resource.id,
      replacementFile: null,
      confirmationResourceId: null,
      error: null,
      message: null,
    }));
  }, [resources, revision.revisionId, selectionRequest]);

  useEffect(() => {
    onMutationPendingChange(contentPending);
    return () => onMutationPendingChange(false);
  }, [contentPending, onMutationPendingChange]);

  const selected = resources.find(
    (resource) => resource.id === session.selectedResourceId,
  ) ?? null;
  const headQuery = useBenchmarkAuthoringResourceHead(
    selected
      ? {
          draftId: revision.draftId,
          revisionId: revision.revisionId,
          resourceId: selected.id,
          mediaType: selected.mediaType,
          size: selected.size,
        }
      : null,
  );
  const availability = projectBenchmarkResourceAvailability({
    enabled: selected !== null,
    pending: selected !== null && (headQuery.isPending || headQuery.isFetching),
    data: headQuery.data,
    error: headQuery.error,
  });
  const effectiveGate = contentPending
    ? {
        allowed: false,
        code: "content-pending" as const,
        message: "已有资源命令正在提交，请等待结果。",
      }
    : gate;

  /** Retain or retire one retry identity and run the entity mutation. */
  const runCommand = async (
    semantic: BenchmarkResourceCommandSemantic,
  ) => {
    if (!effectiveGate.allowed) return;
    const intent = prepareBenchmarkResourceIntent(retryIntent.current, semantic);
    retryIntent.current = intent;
    setSession((current) => ({ ...current, error: null, message: null }));
    try {
      let outcome: BenchmarkAuthoringContentMutationOutcome;
      if (semantic.operation === "upload") {
        outcome = await uploadCommand.mutateAsync({
          draftId: semantic.draftId,
          baseRevisionId: semantic.baseRevisionId,
          clientRequestId: intent.clientRequestId,
          resourceId: semantic.resourceId,
          kind: semantic.kind,
          path: semantic.path,
          mediaType: semantic.mediaType,
          body: semantic.file,
        });
      } else if (semantic.operation === "replace") {
        outcome = await replaceCommand.mutateAsync({
          draftId: semantic.draftId,
          baseRevisionId: semantic.baseRevisionId,
          clientRequestId: intent.clientRequestId,
          resourceId: semantic.resourceId,
          mediaType: semantic.mediaType,
          body: semantic.file,
        });
      } else {
        outcome = await removeCommand.mutateAsync({
          draftId: semantic.draftId,
          baseRevisionId: semantic.baseRevisionId,
          clientRequestId: intent.clientRequestId,
          resourceId: semantic.resourceId,
        });
      }
      retryIntent.current = null;
      onCommandSuccess(outcome);
    } catch (error) {
      if (error instanceof StudioApiError && error.status === 409) {
        retryIntent.current = null;
        onConflict(error.currentRevisionId);
      }
      if (error instanceof StudioApiError && error.status < 500) {
        retryIntent.current = null;
      }
      setSession((current) => ({
        ...current,
        error: resourceCommandError(error),
        message: retryIntent.current
          ? "提交结果未确认；保持所有字段与同一文件可安全重试。"
          : null,
      }));
    }
  };

  /** Validate and submit a new resource without optimistic inventory edits. */
  const submitUpload = () => {
    const validation = validateUpload(upload, session.uploadFile);
    if (validation) {
      setSession((current) => ({ ...current, error: validation }));
      return;
    }
    void runCommand({
      operation: "upload",
      draftId: revision.draftId,
      baseRevisionId: revision.revisionId,
      resourceId: upload.resourceId,
      kind: upload.kind,
      path: upload.path,
      mediaType: upload.mediaType,
      file: session.uploadFile!,
    });
  };

  /** Submit replacement bytes while preserving logical resource metadata. */
  const submitReplacement = () => {
    const mediaType = replaceMediaType.trim() || selected?.mediaType || "";
    if (!selected || !session.replacementFile || !mediaType) {
      setSession((current) => ({
        ...current,
        error: "请选择替换文件并填写明确的 media type。",
      }));
      return;
    }
    void runCommand({
      operation: "replace",
      draftId: revision.draftId,
      baseRevisionId: revision.revisionId,
      resourceId: selected.id,
      mediaType,
      file: session.replacementFile,
    });
  };

  /** Submit a confirmed logical removal without rewriting definition data. */
  const confirmRemoval = () => {
    if (!selected || session.confirmationResourceId !== selected.id) return;
    void runCommand({
      operation: "remove",
      draftId: revision.draftId,
      baseRevisionId: revision.revisionId,
      resourceId: selected.id,
    });
  };

  return (
    <main className="min-h-0 flex-1 overflow-auto p-5">
      <div className="mx-auto max-w-6xl space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-[15px] font-semibold text-[color:var(--zx-text-title)]">
              Managed resources
            </h2>
            <p className="mt-1 max-w-3xl text-[11px] text-[color:var(--zx-text-muted)]">
              当前展示的是 immutable Revision {revision.ordinal} 的权威元数据。所有内容命令只创建新的 unvalidated revision，不代表语义校验、运行、发布或删除历史字节。
            </p>
          </div>
          <span className="rounded-full border border-amber-500/30 px-2 py-1 text-[9px] text-amber-400">
            unvalidated
          </span>
        </div>

        {!effectiveGate.allowed ? (
          <div role="status" className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
            资源命令已阻止：{effectiveGate.message}
          </div>
        ) : null}
        {session.error ? (
          <div role="alert" className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-300">
            {session.error}
          </div>
        ) : null}
        {session.message ? (
          <div aria-live="polite" className="text-[11px] text-amber-300">
            {session.message}
          </div>
        ) : null}

        <section className={cardClass}>
          <h3 className="text-[12px] font-semibold text-[color:var(--zx-text-title)]">
            Upload new resource
          </h3>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <label className={labelClass}>
              Logical ID
              <input
                aria-label="New resource logical ID"
                className={inputClass}
                value={upload.resourceId}
                onChange={(event) => {
                  retryIntent.current = null;
                  setUpload((current) => ({ ...current, resourceId: event.target.value }));
                }}
              />
            </label>
            <label className={labelClass}>
              Kind
              <select
                aria-label="New resource kind"
                className={inputClass}
                value={upload.kind}
                onChange={(event) => {
                  const kind = event.target.value as "asset" | "ground_truth";
                  retryIntent.current = null;
                  setUpload((current) => ({
                    ...current,
                    kind,
                    path: kind === "asset" ? "assets/" : "ground_truth/",
                  }));
                }}
              >
                <option value="asset">asset</option>
                <option value="ground_truth">ground_truth (file-backed)</option>
              </select>
            </label>
            <label className={labelClass}>
              Package-relative path
              <input
                aria-label="New resource path"
                className={inputClass}
                value={upload.path}
                onChange={(event) => {
                  retryIntent.current = null;
                  setUpload((current) => ({ ...current, path: event.target.value }));
                }}
              />
            </label>
            <label className={labelClass}>
              Media type
              <input
                aria-label="New resource media type"
                className={inputClass}
                value={upload.mediaType}
                onChange={(event) => {
                  retryIntent.current = null;
                  setUpload((current) => ({ ...current, mediaType: event.target.value }));
                }}
              />
            </label>
            <label className={labelClass}>
              Local file (reload clears it)
              <input
                key={revision.revisionId}
                aria-label="New resource file"
                type="file"
                className="text-[10px]"
                onChange={(event) => {
                  retryIntent.current = null;
                  setSession((current) => ({
                    ...current,
                    uploadFile: event.target.files?.[0] ?? null,
                  }));
                }}
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-[10px] text-[color:var(--zx-text-muted)]">
              {session.uploadFile
                ? `${session.uploadFile.name} · ${session.uploadFile.size} bytes (browser-local)`
                : "尚未选择文件；digest 和最终 size 只接受服务端返回值。"}
            </p>
            <button
              type="button"
              onClick={submitUpload}
              disabled={!effectiveGate.allowed}
              className="rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[11px] font-semibold text-white disabled:opacity-40"
            >
              {uploadCommand.isPending ? "Uploading…" : "Upload into new revision"}
            </button>
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <ResourceInventory
            resources={resources}
            selectedId={session.selectedResourceId}
            onSelect={(resourceId) => {
              retryIntent.current = null;
              const resource = resources.find((item) => item.id === resourceId);
              setReplaceMediaType(resource?.mediaType ?? "");
              setSession((current) => ({
                ...current,
                selectedResourceId: resourceId,
                replacementFile: null,
                confirmationResourceId: null,
                error: null,
                message: null,
              }));
            }}
          />

          <section className={cardClass}>
            {selected ? (
              <ResourceDetail
                resource={selected}
                revisionId={revision.revisionId}
                availability={availability}
                replaceMediaType={replaceMediaType || selected.mediaType}
                replacementFile={session.replacementFile}
                confirmationOpen={session.confirmationResourceId === selected.id}
                disabled={!effectiveGate.allowed}
                replacePending={replaceCommand.isPending}
                removePending={removeCommand.isPending}
                onRetryHead={() => void headQuery.refetch()}
                onReplaceMediaType={(mediaType) => {
                  retryIntent.current = null;
                  setReplaceMediaType(mediaType);
                }}
                onReplacementFile={(file) => {
                  retryIntent.current = null;
                  setSession((current) => ({ ...current, replacementFile: file }));
                }}
                onReplace={submitReplacement}
                onOpenRemove={() => setSession((current) => ({
                  ...current,
                  confirmationResourceId: selected.id,
                }))}
                onCancelRemove={() => setSession((current) => ({
                  ...current,
                  confirmationResourceId: null,
                }))}
                onConfirmRemove={confirmRemoval}
              />
            ) : (
              <p className="text-[11px] text-[color:var(--zx-text-muted)]">
                当前 immutable revision 没有 managed resource。可从上方上传新的 asset 或 file-backed ground truth。
              </p>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}

/** Render deterministic asset and file-backed ground-truth groups. */
function ResourceInventory({
  resources,
  selectedId,
  onSelect,
}: {
  resources: BenchmarkAuthoringResource[];
  selectedId: string | null;
  onSelect: (resourceId: string) => void;
}) {
  return (
    <nav aria-label="Managed resource inventory" className={cardClass}>
      {(["asset", "ground_truth"] as const).map((kind) => {
        const items = resources.filter((resource) => resource.kind === kind);
        return (
          <div key={kind} className="mb-4 last:mb-0">
            <h3 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-muted)]">
              {kind === "asset" ? "Assets" : "File-backed ground truth"} · {items.length}
            </h3>
            <div className="mt-2 space-y-1">
              {items.map((resource) => (
                <button
                  key={resource.id}
                  type="button"
                  onClick={() => onSelect(resource.id)}
                  className={[
                    "w-full rounded-lg px-3 py-2 text-left text-[11px]",
                    resource.id === selectedId
                      ? "bg-[var(--zx-primary-soft)] text-[color:var(--zx-text-title)]"
                      : "text-[color:var(--zx-text-muted)] hover:bg-black/10",
                  ].join(" ")}
                >
                  <span className="block font-semibold">{resource.id}</span>
                  <span className="mt-1 block truncate font-mono text-[9px]">{resource.path}</span>
                </button>
              ))}
              {items.length === 0 ? (
                <p className="px-3 py-2 text-[10px] text-[color:var(--zx-text-muted)]">None</p>
              ) : null}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

/** Render authoritative metadata, selected HEAD state, replace, and remove. */
function ResourceDetail({
  resource,
  revisionId,
  availability,
  replaceMediaType,
  replacementFile,
  confirmationOpen,
  disabled,
  replacePending,
  removePending,
  onRetryHead,
  onReplaceMediaType,
  onReplacementFile,
  onReplace,
  onOpenRemove,
  onCancelRemove,
  onConfirmRemove,
}: {
  resource: BenchmarkAuthoringResource;
  revisionId: string;
  availability: ReturnType<typeof projectBenchmarkResourceAvailability>;
  replaceMediaType: string;
  replacementFile: File | null;
  confirmationOpen: boolean;
  disabled: boolean;
  replacePending: boolean;
  removePending: boolean;
  onRetryHead: () => void;
  onReplaceMediaType: (value: string) => void;
  onReplacementFile: (file: File | null) => void;
  onReplace: () => void;
  onOpenRemove: () => void;
  onCancelRemove: () => void;
  onConfirmRemove: () => void;
}) {
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">{resource.id}</h3>
        <dl className="mt-3 grid gap-2 text-[10px] sm:grid-cols-2">
          <Fact label="kind" value={resource.kind} />
          <Fact label="path" value={resource.path} />
          <Fact label="media type" value={resource.mediaType} />
          <Fact label="size" value={`${resource.size} bytes`} />
          <Fact label="sha256" value={resource.sha256} wide />
          <Fact label="content identity (metadata only)" value={resource.contentIdentity} wide />
        </dl>
      </div>

      <div className="rounded-lg border border-[var(--zx-border-light)] p-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h4 className="text-[11px] font-semibold text-[color:var(--zx-text-title)]">Current-revision availability</h4>
            <AvailabilityText availability={availability} />
          </div>
          <button type="button" onClick={onRetryHead} className="rounded-md border border-[var(--zx-border-light)] px-2 py-1 text-[10px]">
            Retry HEAD
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--zx-border-light)] p-3">
        <h4 className="text-[11px] font-semibold text-[color:var(--zx-text-title)]">Replace bytes</h4>
        <p className="mt-1 text-[10px] text-[color:var(--zx-text-muted)]">
          Logical ID、kind 和 path 保持不变。缺失内容也可通过 replacement 修复。
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className={labelClass}>
            New media type
            <input aria-label="Replacement media type" className={inputClass} value={replaceMediaType} onChange={(event) => onReplaceMediaType(event.target.value)} />
          </label>
          <label className={labelClass}>
            Replacement file
            <input
              key={revisionId}
              aria-label="Replacement file"
              type="file"
              className="text-[10px]"
              onChange={(event) => onReplacementFile(event.target.files?.[0] ?? null)}
            />
          </label>
        </div>
        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="text-[10px] text-[color:var(--zx-text-muted)]">
            {replacementFile ? `${replacementFile.name} · ${replacementFile.size} bytes` : "No local file selected"}
          </span>
          <button type="button" disabled={disabled} onClick={onReplace} className="rounded-lg bg-[var(--zx-primary)] px-3 py-2 text-[11px] text-white disabled:opacity-40">
            {replacePending ? "Replacing…" : "Replace in new revision"}
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-rose-500/25 p-3">
        <h4 className="text-[11px] font-semibold text-rose-300">Logical removal</h4>
        <p className="mt-1 text-[10px] text-[color:var(--zx-text-muted)]">
          只从新的 current revision 移除声明；历史 immutable revisions 及其仍可达字节不会物理删除，也不会自动重写 manifest/task 引用。
        </p>
        {confirmationOpen ? (
          <div role="alertdialog" aria-label={`Confirm removal of ${resource.id}`} className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-rose-500/10 p-3">
            <span className="text-[10px] text-rose-200">确认移除当前声明 {resource.id}？revision 仍为 unvalidated。</span>
            <div className="flex gap-2">
              <button type="button" onClick={onCancelRemove} className="rounded-md border border-[var(--zx-border-light)] px-2 py-1 text-[10px]">Cancel</button>
              <button type="button" disabled={disabled} onClick={onConfirmRemove} className="rounded-md bg-rose-600 px-2 py-1 text-[10px] text-white disabled:opacity-40">
                {removePending ? "Removing…" : "Confirm logical remove"}
              </button>
            </div>
          </div>
        ) : (
          <button type="button" disabled={disabled} onClick={onOpenRemove} className="mt-3 rounded-md border border-rose-500/40 px-3 py-2 text-[10px] text-rose-300 disabled:opacity-40">Remove declaration…</button>
        )}
      </div>
    </div>
  );
}

/** Render one authoritative metadata fact without making it actionable. */
function Fact({ label, value, wide = false }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={wide ? "sm:col-span-2" : undefined}>
      <dt className="text-[color:var(--zx-text-muted)]">{label}</dt>
      <dd className="mt-0.5 break-all font-mono text-[color:var(--zx-text-body)]">{value}</dd>
    </div>
  );
}

/** Render distinct selected-resource availability states without inference. */
function AvailabilityText({ availability }: { availability: ReturnType<typeof projectBenchmarkResourceAvailability> }) {
  const copy = availability.state === "unchecked"
    ? "unchecked"
    : availability.state === "pending"
      ? "checking exact HEAD…"
      : availability.state === "readable"
        ? `readable · ${availability.head.contentLength} bytes · ${availability.head.filename}`
        : availability.state === "missing"
          ? "missing (404); declaration remains and replacement is available"
          : availability.message;
  const tone = availability.state === "readable"
    ? "text-emerald-400"
    : availability.state === "missing" || availability.state === "contract-failure"
      ? "text-rose-400"
      : "text-amber-400";
  return <p aria-live="polite" className={`mt-1 text-[10px] ${tone}`}>{copy}</p>;
}

/** Validate bounded browser metadata before issuing an upload command. */
function validateUpload(fields: UploadFields, file: File | null): string | null {
  if (!/^[a-z][a-z0-9_.-]{0,127}$/.test(fields.resourceId)) {
    return "Logical ID 必须是稳定的小写标识符。";
  }
  const prefix = fields.kind === "asset" ? "assets/" : "ground_truth/";
  if (
    !fields.path.startsWith(prefix)
    || fields.path === prefix
    || fields.path.includes("..")
    || fields.path.includes("\\")
    || fields.path.includes("//")
  ) {
    return `Path 必须是 ${prefix} 下的安全 Package-relative 文件路径。`;
  }
  if (!fields.mediaType.trim() || !fields.mediaType.includes("/")) {
    return "请填写明确的 media type。";
  }
  if (!file) return "请选择一个浏览器本地文件。";
  return null;
}

/** Convert safe backend/transport facts into truthful resource command copy. */
function resourceCommandError(error: unknown): string {
  if (error instanceof StudioApiError) {
    if (error.status === 409) return "Revision conflict：本地文件和表单已保留，请 Reload Remote 后重新确认。";
    if (error.status === 413) return "上传被容量或请求体上限拒绝；未修改当前 inventory。";
    if (error.status === 507) return "服务端存储当前不可用；未修改当前 inventory。";
    return `资源命令被服务端拒绝：${error.message}`;
  }
  return `资源命令结果未确认：${error instanceof Error ? error.message : "unknown error"}`;
}
