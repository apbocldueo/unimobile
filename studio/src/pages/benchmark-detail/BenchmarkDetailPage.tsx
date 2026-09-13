import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  useBenchmarkDetail,
  useBenchmarkTasks,
  useValidateBenchmark,
} from "@/entities/benchmark-catalog";

/** Inspect one concrete Package source, select a task, and validate it. */
export function BenchmarkDetailPage() {
  const catalogEntryId = useParams<{ benchmarkId: string }>().benchmarkId ?? "";
  const detail = useBenchmarkDetail(catalogEntryId);
  const [params, setParams] = useSearchParams();
  const split = params.get("split") ?? detail.data?.splits[0]?.name ?? "";
  const cursor = params.get("cursor");
  const tasks = useBenchmarkTasks(catalogEntryId, split, cursor);
  const validation = useValidateBenchmark();

  if (detail.isPending) {
    return <CenteredState title="正在加载 Benchmark 定义…" />;
  }
  if (detail.isError) {
    return <CenteredState title="Benchmark 无法读取" detail={detail.error.message} error />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header className="shrink-0 border-b border-[var(--zx-divider-ui)] px-6 py-5">
        <Link to="/benchmarks" className="text-[11px] text-[color:var(--zx-primary)] no-underline">
          ← 返回 Catalog
        </Link>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-[color:var(--zx-text-title)]">
              {detail.data.title}
            </h1>
            <p className="mt-1 font-mono text-[11px] text-[color:var(--zx-text-muted)]">
              {detail.data.packageIdentity}
            </p>
          </div>
          <button
            type="button"
            disabled={validation.isPending || !split}
            onClick={() => validation.mutate({ catalogEntryId, split })}
            className="rounded-lg border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-4 py-2 text-[12px] font-semibold text-[color:var(--zx-text-title)] disabled:opacity-50"
          >
            {validation.isPending ? "验证中…" : "验证此 split"}
          </button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.42fr)]">
        <section className="min-h-0 overflow-auto border-r border-[var(--zx-divider-ui)] p-6">
          <div className="mb-5 flex flex-wrap gap-2">
            {detail.data.splits.map((item) => (
              <button
                key={item.name}
                type="button"
                onClick={() => setParams({ split: item.name })}
                className={[
                  "rounded-lg border px-3 py-2 text-[11px] font-semibold",
                  split === item.name
                    ? "border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] text-[color:var(--zx-text-title)]"
                    : "border-[var(--zx-border-light)] text-[color:var(--zx-text-muted)]",
                ].join(" ")}
              >
                {item.name} · {item.taskCount ?? "?"}
              </button>
            ))}
          </div>
          {tasks.isPending ? (
            <CenteredState title="正在读取任务模板…" />
          ) : tasks.isError ? (
            <CenteredState title="任务定义不可用" detail={tasks.error.message} error />
          ) : (
            <div className="space-y-3">
              {tasks.data.items.map((task) => (
                <article
                  key={task.taskId}
                  className="rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h2 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">
                        {task.taskId}
                      </h2>
                      <p className="mt-2 max-w-3xl text-[12px] leading-relaxed text-[color:var(--zx-text-body)]">
                        {task.instruction}
                      </p>
                    </div>
                    <Link
                      to={`/experiments/new?benchmarkId=${encodeURIComponent(catalogEntryId)}&split=${encodeURIComponent(split)}&taskId=${encodeURIComponent(task.taskId)}`}
                      className="rounded-lg bg-[var(--zx-primary)] px-3 py-2 text-[11px] font-semibold text-white no-underline"
                    >
                      使用此任务
                    </Link>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-3 text-[10px] text-[color:var(--zx-text-muted)]">
                    <span>{task.taskType}</span>
                    <span>app: {task.app ?? "未指定"}</span>
                    <span>evaluator: {task.evaluatorKind}</span>
                    <span>initializers: {task.initializerCount}</span>
                  </div>
                </article>
              ))}
              {tasks.data.nextCursor ? (
                <button
                  type="button"
                  onClick={() => setParams({ split, cursor: tasks.data.nextCursor ?? "" })}
                  className="rounded-lg border border-[var(--zx-border-light)] px-4 py-2 text-[12px] text-[color:var(--zx-text-body)]"
                >
                  下一页任务
                </button>
              ) : null}
            </div>
          )}
        </section>

        <aside className="min-h-0 overflow-auto p-6">
          <InfoSection title="Package identities">
            <Identity label="content" value={detail.data.packageContentIdentity ?? "invalid"} />
            <Identity label="source" value={detail.data.sourceKind} />
            <Identity label="platform" value={detail.data.platforms.join(", ")} />
          </InfoSection>
          <InfoSection title="Requirements">
            {detail.data.requirements.length === 0 ? (
              <Muted>无额外 App 或 plugin 要求。</Muted>
            ) : detail.data.requirements.map((item) => (
              <Identity key={`${item.kind}:${item.id}`} label={item.kind} value={item.id} />
            ))}
          </InfoSection>
          <InfoSection title="Validation">
            {validation.isIdle ? (
              <Muted>验证由研究者显式触发，不在浏览时自动执行。</Muted>
            ) : validation.isError ? (
              <p className="text-[11px] text-rose-400">{validation.error.message}</p>
            ) : validation.data ? (
              <>
                <p className={`text-[12px] font-semibold ${validation.data.valid ? "text-emerald-400" : "text-rose-400"}`}>
                  {validation.data.valid ? "定义与资源验证通过" : "验证失败"}
                </p>
                {validation.data.diagnostics.map((diagnostic) => (
                  <p key={`${diagnostic.code}:${diagnostic.message}`} className="mt-2 text-[11px] text-[color:var(--zx-text-muted)]">
                    {diagnostic.code}: {diagnostic.message}
                  </p>
                ))}
              </>
            ) : (
              <Muted>正在执行完整定义验证…</Muted>
            )}
          </InfoSection>
          {detail.data.diagnostics.length > 0 ? (
            <InfoSection title="Catalog diagnostics">
              {detail.data.diagnostics.map((diagnostic) => (
                <p key={`${diagnostic.code}:${diagnostic.message}`} className="text-[11px] leading-relaxed text-amber-400">
                  {diagnostic.code}: {diagnostic.message}
                </p>
              ))}
            </InfoSection>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

/** Render one labeled metadata group. */
function InfoSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-6 rounded-xl border border-[var(--zx-border-light)] bg-black/10 p-4">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-title)]">
        {title}
      </h2>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

/** Render one potentially long identity without widening the pane. */
function Identity({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-[10px] text-[color:var(--zx-text-muted)]">{label}</span>
      <p className="break-all font-mono text-[10px] leading-relaxed text-[color:var(--zx-text-body)]">
        {value}
      </p>
    </div>
  );
}

/** Render subordinate explanatory copy. */
function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] leading-relaxed text-[color:var(--zx-text-muted)]">{children}</p>;
}

/** Render a full-pane loading or error state. */
function CenteredState({
  title,
  detail,
  error = false,
}: {
  title: string;
  detail?: string;
  error?: boolean;
}) {
  return (
    <div className="flex h-full min-h-64 flex-col items-center justify-center p-8 text-center">
      <h1 className={`text-[14px] font-semibold ${error ? "text-rose-400" : "text-[color:var(--zx-text-title)]"}`}>
        {title}
      </h1>
      {detail ? <p className="mt-2 text-[12px] text-[color:var(--zx-text-muted)]">{detail}</p> : null}
    </div>
  );
}
