import { uiText, useUiLocale } from "@/shared/i18n";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useBenchmarkCatalog } from "@/entities/benchmark-catalog";

/** Browse the immutable process Benchmark Catalog with shareable filters. */
export function BenchmarksPage() {
  useUiLocale();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("query") ?? "");
  const filters = {
    query: params.get("query") ?? "",
    platform: params.get("platform") ?? "",
    sourceKind: params.get("sourceKind") ?? "",
    cursor: params.get("cursor") ?? undefined,
    limit: 30,
  };
  const catalog = useBenchmarkCatalog(filters);

  /** Commit the text filter while resetting an incompatible cursor. */
  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    const next = new URLSearchParams(params);
    if (search.trim()) next.set("query", search.trim());
    else next.delete("query");
    next.delete("cursor");
    setParams(next);
  };

  /** Change one exact filter and reset pagination. */
  const setFilter = (key: "platform" | "sourceKind", value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("cursor");
    setParams(next);
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header className="shrink-0 border-b border-[var(--zx-divider-ui)] px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[color:var(--zx-primary)]">
              Experiments
            </p>
            <h1 className="mt-1 text-xl font-semibold text-[color:var(--zx-text-title)]">
              {uiText("设计一次可复现的 Mobile Agent 实验")}</h1>
            <p className="mt-2 text-[12px] text-[color:var(--zx-text-muted)]">
              {uiText("从 Agent 与 Benchmark 定义开始，预览运行计划，再创建持久 Experiment。")}</p>
          </div>
          <div className="flex flex-wrap gap-2"><Link to="/experiments" className="rounded-lg border border-[var(--zx-border-light)] px-4 py-2 text-[12px] font-semibold text-[color:var(--zx-text-body)] no-underline">{uiText("查看实验记录")}</Link><Link to="/experiments/new" className="rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[12px] font-semibold text-white no-underline">{uiText("新建 Experiment")}</Link></div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <Link to="/agents" className="rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-4 no-underline"><span className="text-[10px] font-semibold text-[color:var(--zx-primary)]">01 · AGENT</span><strong className="mt-2 block text-[12px] text-[color:var(--zx-text-title)]">{uiText("选择已验证的 Agent revision")}</strong></Link>
          <Link to="/experiments/new" className="rounded-xl border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] p-4 no-underline"><span className="text-[10px] font-semibold text-[color:var(--zx-primary)]">02 · COMPOSE</span><strong className="mt-2 block text-[12px] text-[color:var(--zx-text-title)]">{uiText("选择 Benchmark、Task 与 Protocol")}</strong></Link>
          <Link to="/experiments" className="rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-4 no-underline"><span className="text-[10px] font-semibold text-[color:var(--zx-primary)]">03 · INSPECT</span><strong className="mt-2 block text-[12px] text-[color:var(--zx-text-title)]">{uiText("监控、报告、证据与 Replay")}</strong></Link>
        </div>
        <details className="mt-4 rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-panel)] px-4 py-3 text-[11px] text-[color:var(--zx-text-muted)]"><summary className="cursor-pointer font-semibold text-[color:var(--zx-text-body)]">{uiText("Benchmark 高级能力")}</summary><div className="mt-3 flex flex-wrap gap-3"><Link to="/benchmark-authoring" className="text-[color:var(--zx-primary)] no-underline">Authoring</Link><span>Validation</span><span>Contract Tests</span><span>Freeze / Release</span><span>Legacy Migration</span></div></details>
        <div className="mt-6 border-t border-[var(--zx-divider-ui)] pt-5"><h2 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">Benchmark Catalog</h2><p className="mt-1 text-[11px] text-[color:var(--zx-text-muted)]">{uiText("选择定义快照不会连接设备、执行任务或创建 Experiment。")}</p></div>
        <form onSubmit={submitSearch} className="mt-5 grid gap-3 md:grid-cols-[1fr_160px_160px_auto]">
          <input
            aria-label={uiText("搜索 Benchmark")}
            className="zx-control px-3 py-2 text-[12px]"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={uiText("按名称或 Package identity 搜索")}
          />
          <select
            aria-label={uiText("平台筛选")}
            className="zx-control px-3 py-2 text-[12px]"
            value={filters.platform}
            onChange={(event) => setFilter("platform", event.target.value)}
          >
            <option value="">{uiText("全部平台")}</option>
            <option value="android">Android</option>
            <option value="harmonyos">HarmonyOS</option>
          </select>
          <select
            aria-label={uiText("来源筛选")}
            className="zx-control px-3 py-2 text-[12px]"
            value={filters.sourceKind}
            onChange={(event) => setFilter("sourceKind", event.target.value)}
          >
            <option value="">{uiText("全部来源")}</option>
            <option value="catalog">Catalog root</option>
            <option value="package">Package</option>
            <option value="installed">Installed</option>
          </select>
          <button
            type="submit"
            className="rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-4 py-2 text-[12px] font-semibold text-[color:var(--zx-text-title)]"
          >
            {uiText("搜索")}</button>
        </form>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-6">
        {catalog.isPending ? (
          <StateCard title={uiText("正在读取 Catalog…")} detail={uiText("服务正在返回固定快照。")} />
        ) : catalog.isError ? (
          <div><StateCard title={uiText("Catalog 暂不可用")} detail={catalog.error.message} tone="error" /><button type="button" className="zx-control p-3" onClick={() => void catalog.refetch()}>{uiText("重试 Catalog")}</button></div>
        ) : catalog.data.items.length === 0 ? (
          <div className="space-y-4">
            <StateCard title={filters.query || filters.platform || filters.sourceKind || filters.cursor ? uiText("没有匹配的 Benchmark") : uiText("Catalog 中尚无 Benchmark")}
              detail={uiText("Authoring 草稿不等于已发布的 Catalog 资源；需要完成校验、冻结并显式发布。普通 Run 不需要 Benchmark。")} />
            {filters.query || filters.platform || filters.sourceKind || filters.cursor ? <button type="button" className="zx-control p-3" onClick={() => { setSearch(""); setParams({}); }}>{uiText("清除筛选与分页")}</button> : <Link to="/benchmark-authoring">{uiText("创建或导入 Benchmark 草稿")}</Link>}
            <Link to="/help?topic=benchmark" className="ml-4">{uiText("Benchmark 准备说明")}</Link>
          </div>
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {catalog.data.items.map((item) => (
              <Link
                key={item.catalogEntryId}
                to={`/benchmarks/${encodeURIComponent(item.catalogEntryId)}`}
                className="rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-5 text-left no-underline transition hover:-translate-y-0.5 hover:border-[var(--zx-primary-border)]"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h2 className="truncate text-[15px] font-semibold text-[color:var(--zx-text-title)]">
                      {item.title}
                    </h2>
                    <p className="mt-1 truncate font-mono text-[11px] text-[color:var(--zx-text-muted)]">
                      {item.packageIdentity}
                    </p>
                  </div>
                  <span
                    className={[
                      "rounded-full px-2 py-1 text-[10px] font-semibold",
                      item.availability === "available"
                        ? "bg-emerald-500/15 text-emerald-400"
                        : "bg-rose-500/15 text-rose-400",
                    ].join(" ")}
                  >
                    {item.availability}
                  </span>
                </div>
                <div className="mt-4 flex flex-wrap gap-2 text-[10px] text-[color:var(--zx-text-body)]">
                  <Badge>{item.sourceKind}</Badge>
                  {item.platforms.map((value) => <Badge key={value}>{value}</Badge>)}
                  {item.splits.map((split) => (
                    <Badge key={split.name}>
                      {split.name} · {split.taskCount ?? "?"} tasks
                    </Badge>
                  ))}
                </div>
                {item.warnings.length > 0 ? (
                  <p className="mt-4 text-[11px] text-amber-400">
                    {item.warnings[0].message}
                  </p>
                ) : null}
              </Link>
            ))}
          </div>
        )}
        {catalog.data?.nextCursor ? (
          <button
            type="button"
            className="mt-5 rounded-lg border border-[var(--zx-border-light)] px-4 py-2 text-[12px] text-[color:var(--zx-text-body)]"
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set("cursor", catalog.data.nextCursor ?? "");
              setParams(next);
            }}
          >
            {uiText("下一页")}</button>
        ) : null}
      </div>
    </div>
  );
}

/** Render one compact metadata badge. */
function Badge({ children }: { children: React.ReactNode }) {
  useUiLocale();
  return (
    <span className="rounded-md border border-[var(--zx-border-light)] bg-black/10 px-2 py-1">
      {children}
    </span>
  );
}

/** Render loading, empty, and error states consistently. */
function StateCard({
  title,
  detail,
  tone = "neutral",
}: {
  title: string;
  detail: string;
  tone?: "neutral" | "error";
}) {
  useUiLocale();
  return (
    <div className="mx-auto mt-12 max-w-xl rounded-xl border border-dashed border-[var(--zx-border-light)] p-8 text-center">
      <h2 className={`text-[14px] font-semibold ${tone === "error" ? "text-rose-400" : "text-[color:var(--zx-text-title)]"}`}>
        {title}
      </h2>
      <p className="mt-2 text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">
        {detail}
      </p>
    </div>
  );
}
