import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { listStudioAgents } from "@/entities/agent";
import { listBenchmarkCatalog } from "@/entities/benchmark-catalog";
import {
  benchmarkExperimentHistoryQueryOptions,
  type BenchmarkAvailability,
  type BenchmarkExperimentHistoryItem,
  type BenchmarkExperimentLifecycle,
} from "@/entities/benchmark-experiment";
import {
  parseExperimentHistoryRoute,
  serializeExperimentHistoryRoute,
  type ExperimentHistoryRoute,
} from "./model/experimentHistoryRoute";
import { RunsTypeTabs } from "@/widgets/runs-navigation";

type HistoryDraft = {
  lifecycle: "" | BenchmarkExperimentLifecycle;
  catalogEntryId: string;
  agentId: string;
  acceptedFrom: string;
  acceptedBefore: string;
};

const EMPTY_DRAFT: HistoryDraft = {
  lifecycle: "",
  catalogEntryId: "",
  agentId: "",
  acceptedFrom: "",
  acceptedBefore: "",
};

/** Rebuild editable controls from one valid URL-owned query state. */
function draftFromRoute(route: ExperimentHistoryRoute): HistoryDraft {
  if (route.mode !== "history") return EMPTY_DRAFT;
  return {
    lifecycle: route.filters.lifecycle ?? "",
    catalogEntryId: route.filters.catalogEntryId ?? "",
    agentId: route.filters.agentId ?? "",
    acceptedFrom:
      route.filters.acceptedFrom === undefined
        ? ""
        : String(route.filters.acceptedFrom),
    acceptedBefore:
      route.filters.acceptedBefore === undefined
        ? ""
        : String(route.filters.acceptedBefore),
  };
}

/** Convert an already-strict same-service resource link to its app route. */
function appRouteFromResourceLink(link: string): string {
  const prefix = "/studio/benchmark-experiments/";
  if (!link.startsWith(prefix)) {
    throw new Error("Benchmark Experiment resource link is outside scope");
  }
  return `/experiments/${link.slice(prefix.length)}`;
}

/** Format an epoch millisecond using the browser locale and timezone. */
function formatEpoch(value: number | null): string {
  if (value === null) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return `${value} ms`;
  return date.toLocaleString(undefined, { timeZoneName: "short" });
}

/** Render durable Benchmark Experiment History with URL-owned server filters. */
export function ExperimentHistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const route = useMemo(
    () => parseExperimentHistoryRoute(searchParams),
    [searchParams],
  );
  const [draft, setDraft] = useState<HistoryDraft>(() => draftFromRoute(route));
  const [formError, setFormError] = useState<string | null>(null);
  useEffect(() => {
    setDraft(draftFromRoute(route));
    setFormError(null);
  }, [route]);

  const active =
    route.mode === "history"
      ? route
      : { mode: "history" as const, limit: 50, cursor: null, filters: {} };
  const history = useQuery({
    ...benchmarkExperimentHistoryQueryOptions(
      active.limit,
      active.cursor,
      active.filters,
    ),
    enabled: route.mode === "history",
  });
  const catalogSuggestions = useQuery({
    queryKey: ["studio", "benchmark-experiment-history", "catalog-suggestions"],
    queryFn: ({ signal }) => listBenchmarkCatalog({ limit: 100 }, signal),
    staleTime: 60_000,
  });
  const agentSuggestions = useQuery({
    queryKey: ["studio", "benchmark-experiment-history", "agent-suggestions"],
    queryFn: () => listStudioAgents(100),
    staleTime: 60_000,
  });

  /** Apply draft filters through the same strict route parser and reset cursor. */
  const applyFilters = (event: FormEvent) => {
    event.preventDefault();
    const candidate = new URLSearchParams({ limit: String(active.limit) });
    if (draft.lifecycle) candidate.set("lifecycle", draft.lifecycle);
    if (draft.catalogEntryId.trim()) {
      candidate.set("catalogEntryId", draft.catalogEntryId.trim());
    }
    if (draft.agentId.trim()) {
      candidate.set("agentId", draft.agentId.trim());
    }
    if (draft.acceptedFrom.trim()) {
      candidate.set("acceptedFrom", draft.acceptedFrom.trim());
    }
    if (draft.acceptedBefore.trim()) {
      candidate.set("acceptedBefore", draft.acceptedBefore.trim());
    }
    const parsed = parseExperimentHistoryRoute(candidate);
    if (parsed.mode === "invalid") {
      setFormError(parsed.reason);
      return;
    }
    setFormError(null);
    setSearchParams(serializeExperimentHistoryRoute(parsed));
  };

  /** Clear every filter and restart at the first keyset page. */
  const clearFilters = () => {
    setSearchParams(
      serializeExperimentHistoryRoute({
        mode: "history",
        limit: active.limit,
        cursor: null,
        filters: {},
      }),
    );
  };

  if (route.mode === "invalid") {
    return (
      <HistoryState
        title="Experiment History 地址无效"
        detail={route.reason}
        action={
          <button type="button" onClick={clearFilters} className="underline">
            重置为安全的第一页
          </button>
        }
      />
    );
  }

  const hasFilters = Object.keys(route.filters).length > 0;
  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header className="shrink-0 border-b border-[var(--zx-divider-ui)] px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[color:var(--zx-primary)]">
              Benchmark Experiment History
            </p>
            <h1 className="mt-1 text-xl font-semibold text-[color:var(--zx-text-title)]">
              Durable experiments
            </h1>
            <p className="mt-2 text-[12px] text-[color:var(--zx-text-muted)]">
              读取持久 metadata；不会启动 worker、连接设备或读取 artifact bytes。
            </p>
          </div>
          <Link
            to="/experiments/new"
            className="rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[12px] font-semibold text-white no-underline"
          >
            新建 Experiment
          </Link>
        </div>
        <form
          onSubmit={applyFilters}
          className="mt-5 grid gap-3 xl:grid-cols-[150px_1fr_1fr_170px_170px_auto_auto]"
        >
          <select
            aria-label="Lifecycle"
            className="zx-control px-3 py-2 text-[12px]"
            value={draft.lifecycle}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                lifecycle: event.target.value as HistoryDraft["lifecycle"],
              }))
            }
          >
            <option value="">全部 lifecycle</option>
            {[
              "accepted",
              "starting",
              "running",
              "cancelling",
              "finalizing",
              "terminal",
            ].map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <input
            aria-label="Catalog entry identity"
            className="zx-control px-3 py-2 font-mono text-[12px]"
            list="benchmark-history-catalog-options"
            value={draft.catalogEntryId}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                catalogEntryId: event.target.value,
              }))
            }
            placeholder="exact catalogEntryId"
          />
          <datalist id="benchmark-history-catalog-options">
            {catalogSuggestions.data?.items.map((item) => (
              <option
                key={item.catalogEntryId}
                value={item.catalogEntryId}
                label={item.title}
              />
            ))}
          </datalist>
          <input
            aria-label="Agent identity"
            className="zx-control px-3 py-2 font-mono text-[12px]"
            list="benchmark-history-agent-options"
            value={draft.agentId}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                agentId: event.target.value,
              }))
            }
            placeholder="exact agentId"
          />
          <datalist id="benchmark-history-agent-options">
            {agentSuggestions.data?.items.map((item) => (
              <option key={item.agentId} value={item.agentId} label={item.name} />
            ))}
          </datalist>
          <input
            aria-label="Accepted from"
            className="zx-control px-3 py-2 font-mono text-[12px]"
            value={draft.acceptedFrom}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                acceptedFrom: event.target.value,
              }))
            }
            placeholder="acceptedFrom ms"
          />
          <input
            aria-label="Accepted before"
            className="zx-control px-3 py-2 font-mono text-[12px]"
            value={draft.acceptedBefore}
            onChange={(event) =>
              setDraft((current) => ({
                ...current,
                acceptedBefore: event.target.value,
              }))
            }
            placeholder="acceptedBefore ms"
          />
          <button
            type="submit"
            className="rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-4 py-2 text-[12px] font-semibold text-[color:var(--zx-text-title)]"
          >
            应用筛选
          </button>
          <button
            type="button"
            onClick={clearFilters}
            className="rounded-lg border border-[var(--zx-border-light)] px-4 py-2 text-[12px] text-[color:var(--zx-text-body)]"
          >
            清除
          </button>
        </form>
        {formError ? (
          <p role="alert" className="mt-3 text-[11px] text-rose-400">
            {formError}
          </p>
        ) : null}
        {catalogSuggestions.isError || agentSuggestions.isError ? (
          <p className="mt-3 text-[11px] text-amber-400">
            当前 Catalog/Agent suggestions 不可用；仍可输入 durable exact identity。
          </p>
        ) : null}
      </header>
      <RunsTypeTabs active="experiment" />

      <div className="min-h-0 flex-1 overflow-auto p-6">
        {history.isPending ? (
          <HistoryState
            title="正在读取 Experiment History…"
            detail="按 durable acceptedAt / experimentId keyset 排序。"
            busy
          />
        ) : history.isError ? (
          <HistoryState
            title="Experiment History 加载失败"
            detail={history.error.message}
            action={
              <div className="flex justify-center gap-3">
                <button
                  type="button"
                  onClick={() => void history.refetch()}
                  className="underline"
                >
                  重试当前 URL
                </button>
                <button type="button" onClick={clearFilters} className="underline">
                  重置
                </button>
              </div>
            }
          />
        ) : history.data.items.length === 0 ? (
          <HistoryState
            title={hasFilters ? "当前筛选无结果" : "尚无 durable Benchmark Experiment"}
            detail={
              hasFilters
                ? "筛选针对完整 backend history；可清除筛选返回第一页。"
                : "先从 Catalog/Composer 创建 Experiment，History 不生成 mock row。"
            }
            action={
              hasFilters ? (
                <button type="button" onClick={clearFilters} className="underline">
                  清除筛选
                </button>
              ) : (
                <div className="flex justify-center gap-3">
                  <Link to="/benchmarks" className="underline">打开 Catalog</Link>
                  <Link to="/experiments/new" className="underline">打开 Composer</Link>
                </div>
              )
            }
          />
        ) : (
          <>
            {history.isPlaceholderData || history.isFetching ? (
              <p
                role="status"
                className="mb-4 rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-4 py-2 text-[11px] text-[color:var(--zx-text-body)]"
              >
                正在读取当前 cursor page；保留的旧布局不代表新页完成。
              </p>
            ) : null}
            <div className="grid gap-4 2xl:grid-cols-2">
              {history.data.items.map((item) => (
                <HistoryItemCard key={item.experimentId} item={item} />
              ))}
            </div>
            {history.data.nextCursor ? (
              <button
                type="button"
                disabled={history.isPlaceholderData || history.isFetching}
                className="mt-5 rounded-lg border border-[var(--zx-border-light)] px-4 py-2 text-[12px] text-[color:var(--zx-text-body)] disabled:opacity-50"
                onClick={() =>
                  setSearchParams(
                    serializeExperimentHistoryRoute({
                      ...route,
                      cursor: history.data.nextCursor,
                    }),
                  )
                }
              >
                下一页
              </button>
            ) : null}
            {route.cursor ? (
              <p className="mt-3 text-[10px] text-[color:var(--zx-text-muted)]">
                当前为 opaque cursor deep link；返回上一页请使用浏览器 Back。
              </p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

/** Render one durable Experiment summary without mutable registry rewriting. */
function HistoryItemCard({ item }: { item: BenchmarkExperimentHistoryItem }) {
  const monitorRoute = appRouteFromResourceLink(item.links.self);
  const reportRoute =
    item.reportAvailability === "available" && item.links.report
      ? appRouteFromResourceLink(item.links.report)
      : null;
  return (
    <article className="rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[11px] text-[color:var(--zx-text-title)]">
            {item.experimentId}
          </p>
          <p className="mt-1 font-mono text-[10px] text-[color:var(--zx-text-muted)]">
            {item.source.catalogEntryId} · {item.source.packageIdentity} · {item.source.split}
          </p>
        </div>
        <span className="rounded-full bg-blue-500/15 px-2 py-1 text-[10px] font-semibold text-blue-300">
          {item.lifecycle}
          {item.terminalReason ? ` · ${item.terminalReason}` : ""}
        </span>
      </div>
      <dl className="mt-4 grid gap-3 text-[11px] md:grid-cols-2">
        <Fact label="Accepted" value={formatEpoch(item.acceptedAt)} raw={item.acceptedAt} />
        <Fact label="Updated" value={formatEpoch(item.updatedAt)} raw={item.updatedAt} />
        <Fact label="Terminal" value={formatEpoch(item.terminalAt)} raw={item.terminalAt} />
        <Fact label="Planned TaskRuns" value={String(item.plannedTaskRunCount)} />
      </dl>
      <div className="mt-4 space-y-1">
        {item.agents.map((agent) => (
          <p
            key={`${agent.agentId}:${agent.revisionId}`}
            className="font-mono text-[10px] text-[color:var(--zx-text-body)]"
          >
            {agent.agentId} @ {agent.revisionId}
          </p>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Availability label="Outcome" value={item.outcomeAvailability} />
        <Availability label="Report" value={item.reportAvailability} />
        <Availability label="Replay" value={item.replayAvailability} />
        <Availability label="Trajectory" value={item.trajectoryAvailability} />
        <Availability label="Bundle" value={item.bundleAvailability} />
      </div>
      <div className="mt-5 flex flex-wrap gap-3">
        <Link
          to={monitorRoute}
          className="rounded-lg bg-[var(--zx-primary)] px-3 py-2 text-[11px] font-semibold text-white no-underline"
        >
          打开 Monitor
        </Link>
        {reportRoute ? (
          <Link
            to={reportRoute}
            className="rounded-lg border border-[var(--zx-primary-border)] px-3 py-2 text-[11px] font-semibold text-[color:var(--zx-text-title)] no-underline"
          >
            打开 Report
          </Link>
        ) : null}
        {item.replayAvailability === "available" ? (
          <span className="self-center text-[10px] text-[color:var(--zx-text-muted)]">
            Replay 可用；请在 Monitor/Report 选择具体 TaskRun。
          </span>
        ) : null}
      </div>
    </article>
  );
}

/** Render one timestamp or compact durable fact. */
function Fact({
  label,
  value,
  raw,
}: {
  label: string;
  value: string;
  raw?: number | null;
}) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-[color:var(--zx-text-muted)]">
        {label}
      </dt>
      <dd
        className="mt-1 text-[color:var(--zx-text-body)]"
        title={raw === undefined || raw === null ? undefined : `${raw} ms`}
      >
        {value}
      </dd>
    </div>
  );
}

/** Render one availability axis without inferring another outcome. */
function Availability({
  label,
  value,
}: {
  label: string;
  value: BenchmarkAvailability;
}) {
  return (
    <div className="rounded-lg border border-[var(--zx-border-light)] bg-black/10 px-2 py-2 text-center">
      <p className="text-[9px] uppercase text-[color:var(--zx-text-muted)]">{label}</p>
      <p className="mt-1 text-[10px] font-semibold text-[color:var(--zx-text-body)]">
        {value}
      </p>
    </div>
  );
}

/** Render one stable loading, invalid, empty, or retryable page state. */
function HistoryState({
  title,
  detail,
  busy = false,
  action,
}: {
  title: string;
  detail: string;
  busy?: boolean;
  action?: ReactNode;
}) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <section className="max-w-xl rounded-xl border border-dashed border-[var(--zx-border-light)] p-8 text-center">
        {busy ? (
          <span className="mx-auto mb-4 block h-8 w-8 animate-spin rounded-full border-2 border-[var(--zx-primary)] border-t-transparent" />
        ) : null}
        <h2 className="text-[14px] font-semibold text-[color:var(--zx-text-title)]">
          {title}
        </h2>
        <p className="mt-2 text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">
          {detail}
        </p>
        {action ? (
          <div className="mt-4 text-[11px] text-[color:var(--zx-primary)]">
            {action}
          </div>
        ) : null}
      </section>
    </div>
  );
}
