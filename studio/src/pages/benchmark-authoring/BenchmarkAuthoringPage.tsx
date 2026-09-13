import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  useBenchmarkCatalog,
} from "@/entities/benchmark-catalog";
import {
  useBenchmarkDrafts,
  useCreateBenchmarkDraft,
  type BenchmarkAuthoringTemplate,
} from "@/entities/benchmark-authoring";
import {
  prepareBenchmarkCreateIntent,
  type BenchmarkCreateIntent,
} from "@/features/benchmark-definition-editor";
import { BenchmarkLegacyMigrationCard } from "@/features/benchmark-legacy-migration";

const inputClass = "zx-control px-3 py-2 text-[12px]";
const cardClass =
  "rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-5";

/** List and create durable definition-only Benchmark authoring drafts. */
export function BenchmarkAuthoringPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const cursor = params.get("cursor");
  const drafts = useBenchmarkDrafts({ limit: 30, cursor });
  const catalog = useBenchmarkCatalog({ limit: 30 });
  const create = useCreateBenchmarkDraft();
  const createIntent = useRef<BenchmarkCreateIntent | null>(null);
  const [name, setName] = useState("New Benchmark Draft");
  const [template, setTemplate] =
    useState<BenchmarkAuthoringTemplate>("minimal");
  const [publisher, setPublisher] = useState("local");
  const [packageName, setPackageName] = useState("new-benchmark");
  const [version, setVersion] = useState("0.1.0");
  const [catalogEntryId, setCatalogEntryId] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const availableCatalog =
    catalog.data?.items.filter((item) => item.availability === "available") ?? [];

  /** Submit one semantic command while retaining its identity across uncertainty. */
  const submitIntent = async (intent: BenchmarkCreateIntent) => {
    createIntent.current = intent;
    setMessage(null);
    try {
      const response = await create.mutateAsync(intent.input);
      createIntent.current = null;
      navigate(
        `/benchmark-drafts/${encodeURIComponent(response.draft.draftId)}/edit`,
      );
    } catch (error) {
      setMessage(
        `创建结果未确认：${error instanceof Error ? error.message : "unknown"}。保持输入后重试会复用相同命令。`,
      );
    }
  };

  /** Create one draft from a server-owned built-in template. */
  const submitTemplate = (event: FormEvent) => {
    event.preventDefault();
    const intent = prepareBenchmarkCreateIntent(createIntent.current, {
      name: name.trim(),
      source: {
        kind: "template",
        template,
        publisher: publisher.trim(),
        packageName: packageName.trim(),
        version: version.trim(),
      },
    });
    void submitIntent(intent);
  };

  /** Copy one currently available opaque Catalog entry into a new draft. */
  const submitCatalog = (event: FormEvent) => {
    event.preventDefault();
    if (!catalogEntryId) return;
    const intent = prepareBenchmarkCreateIntent(createIntent.current, {
      name: name.trim(),
      source: { kind: "catalog", catalogEntryId },
    });
    void submitIntent(intent);
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header className="shrink-0 border-b border-[var(--zx-divider-ui)] px-6 py-5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[color:var(--zx-primary)]">
          Benchmark Authoring
        </p>
        <h1 className="mt-1 text-xl font-semibold text-[color:var(--zx-text-title)]">
          定义草稿与不可变 Revision
        </h1>
        <p className="mt-2 text-[11px] text-[color:var(--zx-text-muted)]">
          Definition only · unvalidated。此处不会 Validate、Run、Publish、Export 或访问设备。
        </p>
      </header>
      <div className="grid min-h-0 flex-1 overflow-auto xl:grid-cols-[minmax(24rem,0.8fr)_minmax(28rem,1.2fr)]">
        <section className="border-r border-[var(--zx-divider-ui)] p-6">
          <h2 className="text-[14px] font-semibold text-[color:var(--zx-text-title)]">
            Create draft
          </h2>
          <label className="mt-4 grid gap-1 text-[11px] text-[color:var(--zx-text-muted)]">
            Draft name
            <input
              aria-label="Draft name"
              className={inputClass}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <form onSubmit={submitTemplate} className={`${cardClass} mt-4 space-y-3`}>
            <h3 className="text-[12px] font-semibold text-[color:var(--zx-text-title)]">
              Built-in template
            </h3>
            <select
              aria-label="Template"
              className={inputClass}
              value={template}
              onChange={(event) =>
                setTemplate(event.target.value as BenchmarkAuthoringTemplate)}
            >
              <option value="minimal">minimal</option>
              <option value="dynamic-task">dynamic-task</option>
              <option value="composite-evaluation">composite-evaluation</option>
            </select>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-[10px] text-[color:var(--zx-text-muted)]">
                Publisher
                <input
                  className={inputClass}
                  value={publisher}
                  onChange={(event) => setPublisher(event.target.value)}
                />
              </label>
              <label className="grid gap-1 text-[10px] text-[color:var(--zx-text-muted)]">
                Package name
                <input
                  className={inputClass}
                  value={packageName}
                  onChange={(event) => setPackageName(event.target.value)}
                />
              </label>
            </div>
            <label className="grid gap-1 text-[10px] text-[color:var(--zx-text-muted)]">
              Version
              <input
                className={inputClass}
                value={version}
                onChange={(event) => setVersion(event.target.value)}
              />
            </label>
            <button
              type="submit"
              disabled={
                create.isPending
                || !name.trim()
                || !publisher.trim()
                || !packageName.trim()
                || !version.trim()
              }
              className="rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[11px] font-semibold text-white disabled:opacity-40"
            >
              {create.isPending ? "Creating…" : "Create from template"}
            </button>
          </form>

          <form onSubmit={submitCatalog} className={`${cardClass} mt-4 space-y-3`}>
            <h3 className="text-[12px] font-semibold text-[color:var(--zx-text-title)]">
              Copy current Catalog snapshot
            </h3>
            {catalog.isPending ? (
              <p className="text-[11px] text-[color:var(--zx-text-muted)]">
                Loading Catalog…
              </p>
            ) : catalog.isError ? (
              <p role="alert" className="text-[11px] text-rose-400">
                Catalog unavailable: {catalog.error.message}
              </p>
            ) : availableCatalog.length === 0 ? (
              <p className="text-[11px] text-amber-400">
                没有当前可用的 Catalog entry；invalid entry 不可复制。
              </p>
            ) : (
              <select
                aria-label="Catalog entry"
                className={`${inputClass} w-full`}
                value={catalogEntryId}
                onChange={(event) => setCatalogEntryId(event.target.value)}
              >
                <option value="">Select available entry…</option>
                {availableCatalog.map((item) => (
                  <option key={item.catalogEntryId} value={item.catalogEntryId}>
                    {item.title} · {item.packageIdentity}
                  </option>
                ))}
              </select>
            )}
            <button
              type="submit"
              disabled={create.isPending || !name.trim() || !catalogEntryId}
              className="rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-4 py-2 text-[11px] font-semibold text-[color:var(--zx-text-title)] disabled:opacity-40"
            >
              Create from Catalog
            </button>
          </form>
          <BenchmarkLegacyMigrationCard
            onConfirmed={(draftId) =>
              navigate(`/benchmark-drafts/${encodeURIComponent(draftId)}/edit`)
            }
          />
          {message ? (
            <p role="alert" className="mt-4 text-[11px] leading-relaxed text-rose-400">
              {message}
            </p>
          ) : null}
        </section>

        <section className="min-h-0 overflow-auto p-6">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-[14px] font-semibold text-[color:var(--zx-text-title)]">
              Drafts
            </h2>
            <button
              type="button"
              onClick={() => void drafts.refetch()}
              className="rounded-lg border border-[var(--zx-border-light)] px-3 py-2 text-[10px]"
            >
              Retry / refresh
            </button>
          </div>
          {drafts.isPending ? (
            <DraftState title="Loading durable drafts…" />
          ) : drafts.isError ? (
            <DraftState title="Draft list unavailable" detail={drafts.error.message} />
          ) : drafts.data.items.length === 0 ? (
            <DraftState
              title="No drafts yet"
              detail="Create one from a built-in template or available Catalog entry."
            />
          ) : (
            <div className="mt-4 space-y-3">
              {drafts.data.items.map((draft) => (
                <Link
                  key={draft.draftId}
                  to={`/benchmark-drafts/${encodeURIComponent(draft.draftId)}/edit`}
                  className={`${cardClass} block no-underline transition hover:border-[var(--zx-primary-border)]`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="truncate text-[13px] font-semibold text-[color:var(--zx-text-title)]">
                        {draft.name}
                      </h3>
                      <p className="mt-1 truncate font-mono text-[9px] text-[color:var(--zx-text-muted)]">
                        {draft.draftId}
                      </p>
                    </div>
                    <span className="rounded-full bg-amber-500/15 px-2 py-1 text-[9px] text-amber-400">
                      unvalidated
                    </span>
                  </div>
                  <p className="mt-3 truncate font-mono text-[9px] text-[color:var(--zx-text-muted)]">
                    current: {draft.currentRevisionId}
                  </p>
                </Link>
              ))}
            </div>
          )}
          {drafts.data?.nextCursor ? (
            <button
              type="button"
              onClick={() =>
                setParams({ cursor: drafts.data?.nextCursor ?? "" })}
              className="mt-4 rounded-lg border border-[var(--zx-border-light)] px-4 py-2 text-[11px]"
            >
              Next page
            </button>
          ) : null}
        </section>
      </div>
    </div>
  );
}

/** Render loading, empty, and safe list-error states consistently. */
function DraftState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="mt-6 rounded-xl border border-dashed border-[var(--zx-border-light)] p-8 text-center">
      <h3 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">
        {title}
      </h3>
      {detail ? (
        <p className="mt-2 text-[11px] text-[color:var(--zx-text-muted)]">
          {detail}
        </p>
      ) : null}
    </div>
  );
}
