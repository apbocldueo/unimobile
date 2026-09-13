import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { StudioApiError } from "@/shared/api";
import {
  handoffBenchmarkPackageDownload,
  useBenchmarkPackageRevisions,
  useExportBenchmarkPackage,
  useFreezeBenchmarkDraft,
  usePrepareBenchmarkPackageDownload,
  usePublishBenchmarkPackage,
  type BenchmarkAuthoringRevision,
  type BenchmarkPackageRevisionSummary,
} from "@/entities/benchmark-authoring";
import {
  prepareBenchmarkReleaseIntent,
  type BenchmarkReleaseIntent,
} from "../model/benchmarkReleaseIntents";

const PACKAGE_REVISION_ID = /^benchmark-package-revision-[a-f0-9]{32}$/;

export type BenchmarkReleaseGateInput = {
  dirty: boolean;
  hasBufferError: boolean;
  hasUnappliedBuffer: boolean;
  baselineRevisionId: string | null;
  queryCurrentRevisionId: string;
  conflictRevisionId: string | null;
  remoteMayBeNewer: boolean;
  peerPending: boolean;
};

type BenchmarkReleaseViewProps = {
  revision: BenchmarkAuthoringRevision;
  gateInput: BenchmarkReleaseGateInput;
  onPendingChange?: (pending: boolean) => void;
};

/** Derive the exact clean-saved-current gate for creating a new freeze. */
export function benchmarkReleaseFreezeGate(input: BenchmarkReleaseGateInput) {
  if (input.peerPending) return { allowed: false, reason: "另一个 authoring 命令正在进行。" };
  if (input.conflictRevisionId || input.remoteMayBeNewer) {
    return { allowed: false, reason: "远端 current revision 未对齐，请先 Reload Remote。" };
  }
  if (input.hasBufferError || input.hasUnappliedBuffer) {
    return { allowed: false, reason: "Task JSON buffer 无效或尚未应用。" };
  }
  if (input.dirty) return { allowed: false, reason: "存在未保存的本地修改。" };
  if (
    input.baselineRevisionId === null
    || input.baselineRevisionId !== input.queryCurrentRevisionId
  ) {
    return { allowed: false, reason: "本地 baseline 不是服务器 current revision。" };
  }
  return { allowed: true, reason: "当前 baseline 干净、已保存且与服务器 current 对齐。" };
}

/** Render explicit Freeze, Publish, Export, and native Download boundaries. */
export function BenchmarkReleaseView({
  revision,
  gateInput,
  onPendingChange,
}: BenchmarkReleaseViewProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [cursor, setCursor] = useState<string | null>(null);
  const selectedParam = searchParams.get("packageRevisionId");
  const selectedId = selectedParam && PACKAGE_REVISION_ID.test(selectedParam)
    ? selectedParam
    : null;
  const pageQuery = useBenchmarkPackageRevisions({
    draftId: revision.draftId,
    limit: 30,
    cursor,
  });
  const freeze = useFreezeBenchmarkDraft();
  const publish = usePublishBenchmarkPackage();
  const packageExport = useExportBenchmarkPackage();
  const prepareDownload = usePrepareBenchmarkPackageDownload();
  const freezeIntent = useRef<BenchmarkReleaseIntent | null>(null);
  const publishIntent = useRef<BenchmarkReleaseIntent | null>(null);
  const exportIntent = useRef<BenchmarkReleaseIntent | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const pending = freeze.isPending
    || publish.isPending
    || packageExport.isPending
    || prepareDownload.isPending;
  const gate = benchmarkReleaseFreezeGate(gateInput);
  const selected = pageQuery.data?.items.find(
    (item) => item.packageRevisionId === selectedId,
  ) ?? null;

  useEffect(() => {
    onPendingChange?.(pending);
  }, [onPendingChange, pending]);

  /** Persist one exact immutable Package selection in the route query. */
  const selectPackage = (packageRevisionId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("mode", "release");
    next.set("packageRevisionId", packageRevisionId);
    setSearchParams(next, { replace: true });
  };

  /** Freeze only the clean exact current revision and select its result. */
  const freezeCurrent = async () => {
    if (!gate.allowed || pending) return;
    const intent = prepareBenchmarkReleaseIntent(freezeIntent.current, {
      operation: "freeze",
      draftId: revision.draftId,
      targetId: revision.revisionId,
    });
    freezeIntent.current = intent;
    setMessage(null);
    try {
      const result = await freeze.mutateAsync({
        draftId: revision.draftId,
        revisionId: revision.revisionId,
        command: intent.command,
      });
      freezeIntent.current = null;
      selectPackage(result.detail.packageRevision.packageRevisionId);
      await pageQuery.refetch();
      setMessage(
        result.created
          ? "已创建 validated immutable Package revision；尚未发布或导出。"
          : "已确认此前的 Freeze 结果；尚未发布或导出。",
      );
    } catch (error) {
      setMessage(releaseErrorMessage(error, "Freeze 结果未确认，可用相同命令重试。"));
    }
  };

  /** Publish one selected immutable closure after explicit identity confirmation. */
  const publishSelected = async () => {
    if (!selected || pending) return;
    if (!window.confirm(releaseConfirmation("Publish", selected))) return;
    const intent = prepareBenchmarkReleaseIntent(publishIntent.current, {
      operation: "publish",
      draftId: revision.draftId,
      targetId: selected.packageRevisionId,
    });
    publishIntent.current = intent;
    setMessage(null);
    try {
      const result = await publish.mutateAsync({
        draftId: revision.draftId,
        packageRevisionId: selected.packageRevisionId,
        command: intent.command,
      });
      publishIntent.current = null;
      await pageQuery.refetch();
      setMessage(
        result.created
          ? `已发布到 managed Catalog：${result.publication.catalogEntryId}`
          : `已确认等价 managed publication：${result.publication.catalogEntryId}`,
      );
    } catch (error) {
      setMessage(releaseErrorMessage(error, "Publish 结果未确认，可用相同命令重试。"));
    }
  };

  /** Export one selected immutable closure after separate confirmation. */
  const exportSelected = async () => {
    if (!selected || pending) return;
    if (!window.confirm(releaseConfirmation("Export", selected))) return;
    const intent = prepareBenchmarkReleaseIntent(exportIntent.current, {
      operation: "export",
      draftId: revision.draftId,
      targetId: selected.packageRevisionId,
    });
    exportIntent.current = intent;
    setMessage(null);
    try {
      const result = await packageExport.mutateAsync({
        draftId: revision.draftId,
        packageRevisionId: selected.packageRevisionId,
        command: intent.command,
      });
      exportIntent.current = null;
      await pageQuery.refetch();
      setMessage(
        result.created
          ? `确定性 ZIP 已生成：${result.packageExport.filename}`
          : `已确认此前生成的 ZIP：${result.packageExport.filename}`,
      );
    } catch (error) {
      setMessage(releaseErrorMessage(error, "Export 结果未确认，可用相同命令重试。"));
    }
  };

  /** Prepare exact headers then hand the capability to the browser download manager. */
  const download = async () => {
    if (!selected?.packageExport || pending) return;
    setMessage(null);
    try {
      await prepareDownload.mutateAsync({ packageExport: selected.packageExport });
      handoffBenchmarkPackageDownload(selected.packageExport);
      setMessage("下载已交给浏览器；归档字节不会进入 React state。");
    } catch (error) {
      setMessage(releaseErrorMessage(error, "下载准备失败；没有交付未知或损坏的归档。"));
    }
  };

  return (
    <section className="min-h-0 flex-1 overflow-auto p-5" aria-label="Benchmark Release">
      <div className="mx-auto grid max-w-6xl gap-4 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.4fr)]">
        <div className="rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-surface)] p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-[color:var(--zx-text-title)]">Immutable Package revisions</h2>
              <p className="mt-1 text-[10px] text-[color:var(--zx-text-muted)]">只显示服务器持久化的 validated freeze 结果。</p>
            </div>
            <button
              type="button"
              onClick={() => void freezeCurrent()}
              disabled={!gate.allowed || pending}
              className="rounded-lg bg-[var(--zx-primary)] px-3 py-2 text-[11px] font-semibold text-white disabled:opacity-40"
            >
              {freeze.isPending ? "Freezing…" : "Freeze current"}
            </button>
          </div>
          <p className={`mt-3 text-[10px] ${gate.allowed ? "text-emerald-400" : "text-amber-400"}`}>{gate.reason}</p>
          {pageQuery.isPending ? <ReleaseNotice text="正在加载 durable Package revisions…" /> : null}
          {pageQuery.isError ? <ReleaseNotice tone="error" text={`无法读取 release candidates：${pageQuery.error.message}`} /> : null}
          {pageQuery.data?.items.length === 0 ? <ReleaseNotice text="尚无 immutable Package revision。先保存并验证，再显式 Freeze。" /> : null}
          <div className="mt-3 space-y-2">
            {pageQuery.data?.items.map((item) => (
              <button
                key={item.packageRevisionId}
                type="button"
                aria-pressed={selectedId === item.packageRevisionId}
                onClick={() => selectPackage(item.packageRevisionId)}
                className={`w-full rounded-lg border p-3 text-left ${selectedId === item.packageRevisionId ? "border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)]" : "border-[var(--zx-border-light)]"}`}
              >
                <span className="block text-[11px] font-semibold text-[color:var(--zx-text-title)]">{item.packageIdentity}</span>
                <span className="mt-1 block truncate font-mono text-[9px] text-[color:var(--zx-text-muted)]">{item.packageRevisionId}</span>
                <span className="mt-2 flex gap-2 text-[9px]">
                  <ReleaseBadge active={item.publication !== null} label={item.publication ? "published" : "not published"} />
                  <ReleaseBadge active={item.packageExport !== null} label={item.packageExport ? "exported" : "not exported"} />
                </span>
              </button>
            ))}
          </div>
          {pageQuery.data?.nextCursor ? (
            <button type="button" className="mt-3 text-[10px] text-[color:var(--zx-primary)]" onClick={() => setCursor(pageQuery.data?.nextCursor ?? null)}>Next page</button>
          ) : null}
        </div>

        <div className="rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-surface)] p-4">
          {!selected ? (
            <ReleaseNotice tone={selectedId ? "error" : "default"} text={selectedId ? "URL 中选择的 Package revision 不在当前页面或已不可用。" : "选择一个 immutable Package revision 查看 release authority。"} />
          ) : (
            <>
              <h2 className="text-sm font-semibold text-[color:var(--zx-text-title)]">Release authority</h2>
              <IdentityFacts item={selected} />
              <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-[10px] text-amber-300">
                publication/export 仅证明 frozen closure 与归档完整性；executionEvidence=false，realDeviceEvidence=false。
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <ReleaseAction
                  title="Publish"
                  detail={selected.publication ? `Catalog ${selected.publication.catalogEntryId}` : "注册到 server-owned managed Catalog。"}
                  button={publish.isPending ? "Publishing…" : selected.publication ? "Published" : "Publish"}
                  disabled={pending || selected.publication !== null}
                  onClick={() => void publishSelected()}
                />
                <ReleaseAction
                  title="Export"
                  detail={selected.packageExport ? `${selected.packageExport.filename} · ${selected.packageExport.size} bytes` : "生成 byte-deterministic stored ZIP。"}
                  button={packageExport.isPending ? "Exporting…" : selected.packageExport ? "Exported" : "Export"}
                  disabled={pending || selected.packageExport !== null}
                  onClick={() => void exportSelected()}
                />
                <ReleaseAction
                  title="Download"
                  detail="先执行 exact HEAD，再交给浏览器原生下载。"
                  button={prepareDownload.isPending ? "Preparing…" : "Download"}
                  disabled={pending || selected.packageExport === null}
                  onClick={() => void download()}
                />
              </div>
            </>
          )}
          {message ? <p role="status" className="mt-4 text-[10px] text-[color:var(--zx-text-muted)]">{message}</p> : null}
        </div>
      </div>
    </section>
  );
}

/** Render safe Package/content/closure identities for confirmation. */
function IdentityFacts({ item }: { item: BenchmarkPackageRevisionSummary }) {
  return (
    <dl className="mt-3 grid gap-2 text-[10px]">
      {[
        ["Package", item.packageIdentity],
        ["Package content", item.packageContentIdentity],
        ["Frozen closure", item.closureIdentity],
        ["Members", String(item.memberCount)],
      ].map(([label, value]) => (
        <div key={label} className="grid gap-1 sm:grid-cols-[8rem_minmax(0,1fr)]">
          <dt className="text-[color:var(--zx-text-muted)]">{label}</dt>
          <dd className="break-all font-mono text-[color:var(--zx-text-body)]">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Render one explicit release action card. */
function ReleaseAction({ title, detail, button, disabled, onClick }: { title: string; detail: string; button: string; disabled: boolean; onClick: () => void }) {
  return (
    <div className="rounded-lg border border-[var(--zx-border-light)] p-3">
      <h3 className="text-[11px] font-semibold text-[color:var(--zx-text-title)]">{title}</h3>
      <p className="mt-1 min-h-10 text-[9px] text-[color:var(--zx-text-muted)]">{detail}</p>
      <button type="button" onClick={onClick} disabled={disabled} className="mt-3 w-full rounded-md border border-[var(--zx-primary-border)] px-2 py-1.5 text-[10px] disabled:opacity-40">{button}</button>
    </div>
  );
}

/** Render a compact authoritative availability badge. */
function ReleaseBadge({ active, label }: { active: boolean; label: string }) {
  return <span className={active ? "text-emerald-400" : "text-[color:var(--zx-text-muted)]"}>{label}</span>;
}

/** Render one bounded empty/loading/error state. */
function ReleaseNotice({ text, tone = "default" }: { text: string; tone?: "default" | "error" }) {
  return <p role={tone === "error" ? "alert" : undefined} className={`mt-3 rounded-lg border p-3 text-[10px] ${tone === "error" ? "border-rose-500/30 text-rose-400" : "border-[var(--zx-border-light)] text-[color:var(--zx-text-muted)]"}`}>{text}</p>;
}

/** Build the explicit confirmation text from immutable server facts only. */
function releaseConfirmation(operation: "Publish" | "Export", item: BenchmarkPackageRevisionSummary) {
  return `${operation} immutable Package?\n${item.packageIdentity}\ncontent=${item.packageContentIdentity}\nclosure=${item.closureIdentity}\nexecutionEvidence=false\nrealDeviceEvidence=false`;
}

/** Project one bounded API failure without inventing release state. */
function releaseErrorMessage(error: unknown, fallback: string) {
  if (error instanceof StudioApiError) {
    if (error.status === 409) return `Release conflict：${error.message}`;
    if (error.status === 404) return "Release resource 不存在或不属于当前 draft。";
    if (error.status === 503) return "Managed release storage 缺失、损坏或暂不可用。";
    return error.message;
  }
  return error instanceof Error ? error.message : fallback;
}
