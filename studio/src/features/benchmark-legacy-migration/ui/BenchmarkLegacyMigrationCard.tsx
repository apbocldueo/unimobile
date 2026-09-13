import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import {
  BENCHMARK_LEGACY_MIGRATION_MAX_SOURCE_BYTES,
  useConfirmBenchmarkLegacyMigration,
  usePreviewBenchmarkLegacyMigration,
  type BenchmarkLegacyMigrationPreviewRequest,
} from "@/entities/benchmark-authoring";
import { StudioApiError } from "@/shared/api";
import { prepareBenchmarkLegacyMigrationConfirmIntent } from "../model/benchmarkLegacyMigration.intent";
import { useBenchmarkLegacyMigrationStore } from "../model/benchmarkLegacyMigration.store";

const inputClass = "zx-control w-full px-3 py-2 text-[11px]";
const cardClass = "rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-5";

type BenchmarkLegacyMigrationCardProps = {
  onConfirmed: (draftId: string) => void;
};

/** Render the disposable Preview/review/Confirm legacy migration workflow. */
export function BenchmarkLegacyMigrationCard({
  onConfirmed,
}: BenchmarkLegacyMigrationCardProps) {
  const session = useBenchmarkLegacyMigrationStore();
  const previewMutation = usePreviewBenchmarkLegacyMigration();
  const confirmMutation = useConfirmBenchmarkLegacyMigration();
  const [message, setMessage] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  useEffect(
    () => () => useBenchmarkLegacyMigrationStore.getState().reset(),
    [],
  );

  /** Read only the user-selected browser File while protecting late ownership. */
  const selectFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const generation = session.beginSourceFile(file);
    setMessage(null);
    if (file.size > BENCHMARK_LEGACY_MIGRATION_MAX_SOURCE_BYTES) {
      setFileError("文件超过 1 MiB；不会发送 Preview。");
      return;
    }
    setFileError(null);
    try {
      const sourceText = await file.text();
      session.completeSourceRead(generation, sourceText);
    } catch {
      setFileError("浏览器无法读取所选文件；请重新选择。");
    }
  };

  /** Build the exact current browser-read Preview request. */
  const currentRequest = (): BenchmarkLegacyMigrationPreviewRequest | null => {
    const state = useBenchmarkLegacyMigrationStore.getState();
    if (!state.sourceFile || state.sourceText === null) return null;
    return {
      schemaVersion: 1,
      sourceName: state.sourceFile.name,
      sourceText: state.sourceText,
      target: { ...state.target },
    };
  };

  /** Submit an explicit transient Preview and reject late generations. */
  const submitPreview = async (event: FormEvent) => {
    event.preventDefault();
    const request = currentRequest();
    if (!request) return;
    const owner = useBenchmarkLegacyMigrationStore.getState().generation;
    setMessage(null);
    try {
      const result = await previewMutation.mutateAsync(request);
      if (!useBenchmarkLegacyMigrationStore.getState().adoptPreview(owner, result)) {
        setMessage("旧 Preview 已被忽略；文件或目标已变化，请重新 Preview。");
      }
    } catch (error) {
      if (useBenchmarkLegacyMigrationStore.getState().generation === owner) {
        setMessage(`Preview 失败：${error instanceof Error ? error.message : "unknown"}`);
      }
    }
  };

  /** Confirm only the current reviewed Preview with retry-stable authority. */
  const confirm = async () => {
    const state = useBenchmarkLegacyMigrationStore.getState();
    const request = currentRequest();
    if (!request || !state.preview || state.previewGeneration !== state.generation) return;
    const intent = prepareBenchmarkLegacyMigrationConfirmIntent(
      state.confirmIntent,
      request,
      state.preview,
    );
    state.setConfirmIntent(intent);
    setMessage(null);
    try {
      const response = await confirmMutation.mutateAsync(intent.input);
      state.setConfirmIntent(null);
      setMessage(response.created ? "迁移草稿已创建。" : "已确认先前提交的迁移草稿。" );
      onConfirmed(response.draft.draftId);
    } catch (error) {
      if (error instanceof StudioApiError && error.status === 409) {
        useBenchmarkLegacyMigrationStore.getState().invalidatePreview();
        setMessage("Preview 已失效或命令冲突；必须重新 Preview 后再确认。");
        return;
      }
      setMessage(`Confirm 结果未确认：${error instanceof Error ? error.message : "unknown"}。保持输入后重试会复用同一命令。`);
    }
  };

  const preview = session.preview;
  const canPreview =
    session.sourceText !== null
    && !fileError
    && Object.values(session.target).every((value) => String(value).trim());
  const canConfirm =
    preview?.confirmable === true
    && preview.previewFingerprint !== null
    && session.previewGeneration === session.generation;

  return (
    <form onSubmit={submitPreview} className={`${cardClass} mt-4 space-y-4`}>
      <div>
        <h3 className="text-[12px] font-semibold text-[color:var(--zx-text-title)]">
          Legacy BenchmarkTask JSON
        </h3>
        <p className="mt-1 text-[10px] leading-relaxed text-[color:var(--zx-text-muted)]">
          浏览器读取 ≤1 MiB 的独立 V1 JSON 数组；只生成可审阅 Preview，不读取主机路径。
        </p>
      </div>
      <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-[10px] leading-relaxed text-amber-300">
        迁移只会创建 unvalidated draft；Validation、Contract Test、Freeze、Publication、Export、Execution 与 Device evidence 均为 false。
      </p>
      <label className="grid gap-1 text-[10px] text-[color:var(--zx-text-muted)]">
        Legacy JSON file
        <input aria-label="Legacy JSON file" type="file" accept="application/json,.json" onChange={(event) => void selectFile(event)} />
      </label>
      {fileError ? <p role="alert" className="text-[10px] text-rose-400">{fileError}</p> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <MigrationField label="Migration draft name" value={session.target.draftName} onChange={(value) => session.updateTarget("draftName", value)} />
        <MigrationField label="Migration title" value={session.target.title} onChange={(value) => session.updateTarget("title", value)} />
        <MigrationField label="Migration publisher" value={session.target.publisher} onChange={(value) => session.updateTarget("publisher", value)} />
        <MigrationField label="Migration package name" value={session.target.packageName} onChange={(value) => session.updateTarget("packageName", value)} />
        <MigrationField label="Migration version" value={session.target.version} onChange={(value) => session.updateTarget("version", value)} />
        <MigrationField label="Migration split" value={session.target.split} onChange={(value) => session.updateTarget("split", value)} />
      </div>
      <label className="grid gap-1 text-[10px] text-[color:var(--zx-text-muted)]">
        Migration platform
        <select aria-label="Migration platform" className={inputClass} value={session.target.platform} onChange={(event) => session.updateTarget("platform", event.target.value as "android" | "harmonyos")}>
          <option value="android">android</option>
          <option value="harmonyos">harmonyos</option>
        </select>
      </label>
      <MigrationField label="Migration task file" value={session.target.taskFilePath} onChange={(value) => session.updateTarget("taskFilePath", value)} />
      <button type="submit" disabled={!canPreview || previewMutation.isPending} className="rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-4 py-2 text-[11px] font-semibold disabled:opacity-40">
        {previewMutation.isPending ? "Previewing…" : "Preview migration"}
      </button>

      {preview ? (
        <section aria-label="Migration preview" className="space-y-3 rounded-lg border border-[var(--zx-border-light)] p-3">
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <Fact label="Source bytes" value={String(preview.source.utf8Size)} />
            <Fact label="Entries / unique" value={`${preview.source.entryCount} / ${preview.source.uniqueTaskCount}`} />
            <Fact label="Source fingerprint" value={preview.source.sourceFingerprint} />
            <Fact label="Preview fingerprint" value={preview.previewFingerprint ?? "not issued"} />
          </div>
          <p className="text-[10px] text-[color:var(--zx-text-muted)]">
            Retained {preview.diff.taskChanges.retained} · renamed {preview.diff.taskChanges.renamed} · removed {preview.diff.taskChanges.removed} · deduplicated {preview.diff.taskChanges.deduplicated} · rewritten {preview.diff.taskChanges.rewritten}
          </p>
          <ReviewList title="Wrapper / declaration / omission diff" items={preview.diff.entries.map((item) => `${item.category}: ${item.message}`)} />
          <ReviewList title="Derived plugins" items={preview.diff.pluginIds} />
          <ReviewList title="Derived Apps" items={preview.diff.appIds} />
          <ReviewList title="Post-migration work" items={preview.postMigrationWork.map((item) => item.message)} />
          <ReviewList title="Diagnostics" items={preview.diagnostics.map((item) =>
            `${item.severity} · ${item.code} · ${item.message}`
            + `${item.sourceIndex === null ? "" : ` · source[${item.sourceIndex}]`}`
            + `${item.taskId === null ? "" : ` · task ${item.taskId}`}`
            + `${item.fieldPath.length === 0 ? "" : ` · ${item.fieldPath.join(".")}`}`
          )} />
          <p className={preview.confirmable ? "text-[10px] text-emerald-400" : "text-[10px] text-rose-400"}>
            {preview.confirmable ? "Confirmable Preview；仍不代表验证或运行成功。" : "Non-confirmable Preview；不会创建草稿。"}
          </p>
          <button type="button" onClick={() => void confirm()} disabled={!canConfirm || confirmMutation.isPending} className="rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[11px] font-semibold text-white disabled:opacity-40">
            {confirmMutation.isPending ? "Confirming…" : "Confirm migration"}
          </button>
        </section>
      ) : null}
      {message ? <p role="alert" className="text-[10px] leading-relaxed text-rose-400">{message}</p> : null}
    </form>
  );
}

/** Render one explicit migration target input. */
function MigrationField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="grid gap-1 text-[10px] text-[color:var(--zx-text-muted)]">
      {label}
      <input aria-label={label} className={inputClass} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

/** Render one compact immutable Preview fact. */
function Fact({ label, value }: { label: string; value: string }) {
  return <p className="min-w-0"><span className="block text-[color:var(--zx-text-muted)]">{label}</span><span className="block truncate font-mono" title={value}>{value}</span></p>;
}

/** Render one bounded Preview review collection without raw source content. */
function ReviewList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <p className="text-[10px] font-semibold text-[color:var(--zx-text-title)]">{title}</p>
      {items.length === 0 ? <p className="text-[10px] text-[color:var(--zx-text-muted)]">None</p> : (
        <ul className="mt-1 list-disc space-y-1 pl-4 text-[10px] text-[color:var(--zx-text-muted)]">
          {items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
        </ul>
      )}
    </div>
  );
}
