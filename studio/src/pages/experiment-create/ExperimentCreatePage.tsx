import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { listStudioAgents } from "@/entities/agent";
import { useCreateBenchmarkExperiment } from "@/entities/benchmark-experiment";
import {
  useBenchmarkCatalog,
  useBenchmarkDetail,
  useBenchmarkTasks,
  useDeviceProfiles,
  useValidateBenchmark,
} from "@/entities/benchmark-catalog";
import {
  usePreviewExperiment,
  type ExperimentPreview,
  type ExperimentPreviewRequest,
} from "@/entities/experiment-preview";
import {
  isPreparedPreviewCurrent,
  prepareExperimentCreateIntent,
  useExperimentComposerStore,
  type ExperimentCreateIntent,
  type PreparedExperimentPreview,
} from "@/features/experiment-composer";
import { StudioApiError } from "@/shared/api";

type VersionedValidation = {
  semanticVersion: number;
  valid: boolean;
};

/** Compose, preview, and durably create one Benchmark Experiment. */
export function ExperimentCreatePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const initialBenchmark = params.get("benchmarkId") ?? "";
  const initialSplit = params.get("split") ?? "test";
  const initialTask = params.get("taskId") ?? "";
  const draft = useExperimentComposerStore((state) => state.draft);
  const semanticVersion = useExperimentComposerStore(
    (state) => state.semanticVersion,
  );
  const patchDraft = useExperimentComposerStore((state) => state.patchDraft);
  const patchProtocol = useExperimentComposerStore((state) => state.patchProtocol);
  const patchBudget = useExperimentComposerStore((state) => state.patchBudget);
  const reset = useExperimentComposerStore((state) => state.reset);
  const [validation, setValidation] = useState<VersionedValidation | null>(null);
  const [preview, setPreview] = useState<PreparedExperimentPreview | null>(null);
  const createIntent = useRef<ExperimentCreateIntent | null>(null);

  useEffect(() => {
    reset({
      catalogEntryId: initialBenchmark,
      split: initialSplit,
      taskId: initialTask,
    });
  }, [initialBenchmark, initialSplit, initialTask, reset]);

  const catalog = useBenchmarkCatalog({ limit: 100 });
  const detail = useBenchmarkDetail(draft.catalogEntryId);
  const tasks = useBenchmarkTasks(
    draft.catalogEntryId,
    draft.split,
    null,
  );
  const profiles = useDeviceProfiles();
  const agents = useQuery({
    queryKey: ["studio", "agents", "experiment-composer"],
    queryFn: () => listStudioAgents(100),
  });
  const validateCommand = useValidateBenchmark();
  const previewCommand = usePreviewExperiment();
  const createCommand = useCreateBenchmarkExperiment();
  const currentValidation =
    validation?.semanticVersion === semanticVersion ? validation : null;
  const previewCurrent = isPreparedPreviewCurrent(preview, semanticVersion);
  const previewStale = preview !== null && !previewCurrent;

  const selectedAgent = useMemo(
    () => agents.data?.items.find((item) => item.agentId === draft.agentId),
    [agents.data?.items, draft.agentId],
  );
  const canSubmit =
    Boolean(draft.catalogEntryId)
    && Boolean(draft.split)
    && Boolean(draft.taskId)
    && Boolean(draft.agentId)
    && Boolean(draft.revisionId)
    && Boolean(draft.deviceProfileId)
    && currentValidation?.valid === true;

  /** Change Agent while binding its current immutable revision explicitly. */
  const selectAgent = (agentId: string) => {
    const agent = agents.data?.items.find((item) => item.agentId === agentId);
    patchDraft({
      agentId,
      revisionId: agent?.currentRevisionId ?? "",
    });
  };

  /** Validate the selected Package split at the current semantic version. */
  const validate = () => {
    const submittedVersion = semanticVersion;
    validateCommand.mutate(
      {
        catalogEntryId: draft.catalogEntryId,
        split: draft.split,
      },
      {
        onSuccess: (result) => {
          setValidation({
            semanticVersion: submittedVersion,
            valid: result.valid,
          });
        },
      },
    );
  };

  /** Submit the strict one-Agent/one-task/one-repeat preview definition. */
  const submitPreview = () => {
    if (!canSubmit) return;
    const request: ExperimentPreviewRequest = {
      schemaVersion: 1,
      agentRevisions: [
        {
          agentId: draft.agentId,
          revisionId: draft.revisionId,
        },
      ],
      benchmark: {
        catalogEntryId: draft.catalogEntryId,
        split: draft.split,
        taskIds: [draft.taskId],
      },
      protocol: draft.protocol,
      deviceProfileId: draft.deviceProfileId,
    };
    const submittedVersion = semanticVersion;
    previewCommand.mutate(request, {
      onSuccess: (value) => {
        setPreview({
          semanticVersion: submittedVersion,
          request,
          value,
          invalidated: false,
        });
        createIntent.current = null;
      },
    });
  };

  /** Create exactly the current preview and preserve identity across safe retry. */
  const createExperiment = () => {
    if (
      !isPreparedPreviewCurrent(preview, semanticVersion)
      || createCommand.isPending
    ) {
      return;
    }
    const intent = prepareExperimentCreateIntent(
      createIntent.current,
      preview,
    );
    createIntent.current = intent;
    createCommand.mutate(intent.input, {
      onSuccess: ({ experiment }) => {
        createIntent.current = null;
        navigate(
          `/experiments/${encodeURIComponent(experiment.experimentId)}`,
        );
      },
      onError: (error) => {
        if (
          error instanceof StudioApiError
          && (error.status === 409 || error.code.includes("conflict"))
        ) {
          setPreview((current) =>
            current === null ? null : { ...current, invalidated: true },
          );
        }
      },
    });
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--zx-canvas)]">
      <header className="shrink-0 border-b border-[var(--zx-divider-ui)] px-6 py-5">
        <Link to="/benchmarks" className="text-[11px] text-[color:var(--zx-primary)] no-underline">
          ← Benchmark Catalog
        </Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-[color:var(--zx-text-title)]">
              Experiment Composer
            </h1>
            <p className="mt-1 text-[12px] text-[color:var(--zx-text-muted)]">
              先确定性预览，再以同一完整定义创建持久 Experiment。
            </p>
          </div>
          <span className="rounded-full border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-3 py-1 text-[10px] font-semibold text-[color:var(--zx-text-body)]">
            Stage 5.3 · durable create
          </span>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 xl:grid-cols-[minmax(26rem,0.9fr)_minmax(24rem,1.1fr)]">
        <form
          className="flex min-h-0 flex-col overflow-auto border-r border-[var(--zx-divider-ui)] p-6"
          onSubmit={(event) => {
            event.preventDefault();
            submitPreview();
          }}
        >
          <FormSection
            index="01"
            title="绑定 Agent revision"
            detail="Preview 复核保存 revision 内的 AgentGraph canonical identity。"
          >
            <Field label="Agent">
              <select
                aria-label="Agent revision"
                className="zx-control w-full px-3 py-2 text-[12px]"
                value={draft.agentId}
                onChange={(event) => selectAgent(event.target.value)}
              >
                <option value="">请选择已有 Agent</option>
                {agents.data?.items.map((item) => (
                  <option
                    key={item.agentId}
                    value={item.agentId}
                    disabled={!item.currentRevisionId}
                  >
                    {item.name}
                  </option>
                ))}
              </select>
            </Field>
            <details className="rounded-lg bg-black/10 p-3 text-[10px] text-[color:var(--zx-text-muted)]">
              <summary className="cursor-pointer font-semibold">Revision 技术详情</summary>
              <p className="mt-2 break-all font-mono">
                {draft.revisionId || selectedAgent?.currentRevisionId || "未选择"}
              </p>
            </details>
          </FormSection>

          <FormSection
            index="02"
            title="选择定义"
            detail="具体来源、split 与 exact task 都进入 preview fingerprint。"
          >
            <Field label="Benchmark Package">
              <select
                aria-label="Benchmark Package"
                className="zx-control w-full px-3 py-2 text-[12px]"
                value={draft.catalogEntryId}
                onChange={(event) =>
                  patchDraft({
                    catalogEntryId: event.target.value,
                    split: "",
                    taskId: "",
                  })
                }
              >
                <option value="">请选择 Benchmark</option>
                {catalog.data?.items.map((item) => (
                  <option
                    key={item.catalogEntryId}
                    value={item.catalogEntryId}
                    disabled={item.availability !== "available"}
                  >
                    {item.title} · {item.packageIdentity}
                  </option>
                ))}
              </select>
            </Field>
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="Split">
                <select
                  aria-label="Benchmark split"
                  className="zx-control w-full px-3 py-2 text-[12px]"
                  value={draft.split}
                  disabled={!detail.data}
                  onChange={(event) =>
                    patchDraft({ split: event.target.value, taskId: "" })
                  }
                >
                  <option value="">请选择 split</option>
                  {detail.data?.splits.map((item) => (
                    <option key={item.name} value={item.name}>{item.name}</option>
                  ))}
                </select>
              </Field>
              <Field label="Task">
                <select
                  aria-label="Benchmark task"
                  className="zx-control w-full px-3 py-2 text-[12px]"
                  value={draft.taskId}
                  disabled={!tasks.data}
                  onChange={(event) => patchDraft({ taskId: event.target.value })}
                >
                  <option value="">请选择 exact task</option>
                  {tasks.data?.items.map((item) => (
                    <option key={item.taskId} value={item.taskId}>{item.taskId}</option>
                  ))}
                </select>
              </Field>
            </div>
          </FormSection>

          <FormSection
            index="03"
            title="Protocol 与预算"
            detail="第一版固定 one Agent × one task × one repeat，但保留正式 Protocol。"
          >
            <div className="grid gap-3 md:grid-cols-2">
              <NumberField
                label="Seed"
                value={draft.protocol.seed}
                onChange={(seed) => patchProtocol({ seed })}
              />
              <Field label="Task order">
                <select
                  aria-label="Task order"
                  className="zx-control w-full px-3 py-2 text-[12px]"
                  value={draft.protocol.taskOrder.strategy}
                  onChange={(event) =>
                    patchProtocol({
                      taskOrder: {
                        strategy: event.target.value as "fixed" | "seeded",
                      },
                    })
                  }
                >
                  <option value="fixed">fixed</option>
                  <option value="seeded">seeded</option>
                </select>
              </Field>
              <NumberField
                label="Max interactions"
                min={1}
                value={draft.protocol.budget.maxInteractions}
                onChange={(maxInteractions) => patchBudget({ maxInteractions })}
              />
              <NumberField
                label="Max activations"
                min={1}
                value={draft.protocol.budget.maxActivations}
                onChange={(maxActivations) => patchBudget({ maxActivations })}
              />
              <NumberField
                label="Timeout seconds"
                min={1}
                value={draft.protocol.budget.timeoutSeconds}
                onChange={(timeoutSeconds) => patchBudget({ timeoutSeconds })}
              />
              <Field label="Device profile">
                <select
                  aria-label="Device profile"
                  className="zx-control w-full px-3 py-2 text-[12px]"
                  value={draft.deviceProfileId}
                  onChange={(event) =>
                    patchDraft({ deviceProfileId: event.target.value })
                  }
                >
                  <option value="">请选择安全 profile</option>
                  {profiles.data?.items.map((item) => (
                    <option key={item.deviceProfileId} value={item.deviceProfileId}>
                      {item.label} · {item.platform}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          </FormSection>

          <div className="flex flex-wrap items-center gap-3 border-t border-[var(--zx-divider-ui)] pt-5">
            <button
              type="button"
              disabled={!draft.catalogEntryId || !draft.split || validateCommand.isPending}
              onClick={validate}
              className="rounded-lg border border-[var(--zx-border-light)] px-4 py-2 text-[12px] font-semibold text-[color:var(--zx-text-body)] disabled:opacity-50"
            >
              {validateCommand.isPending ? "验证中…" : "1. 验证定义"}
            </button>
            <button
              type="submit"
              disabled={!canSubmit || previewCommand.isPending}
              className="rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[12px] font-semibold text-white disabled:cursor-not-allowed disabled:bg-[var(--zx-disabled-bg)]"
            >
              {previewCommand.isPending ? "预览中…" : "2. 生成确定性预览"}
            </button>
            <p className="text-[11px] text-[color:var(--zx-text-muted)]">
              {currentValidation?.valid
                ? "当前定义已验证"
                : "修改任何语义字段后需要重新验证"}
            </p>
          </div>
        </form>

        <aside className="min-h-0 overflow-auto p-6" aria-label="Experiment preview result">
          {previewCommand.isError ? (
            <ResultState
              title="Preview 被拒绝"
              detail={previewCommand.error.message}
              tone="error"
            />
          ) : preview === null ? (
            <ResultState
              title="等待 Preview"
              detail="完成左侧选择并显式验证后，服务会返回规范化 Protocol、canonical identities 与有序 schedule。"
            />
          ) : previewStale ? (
            <ResultState
              title="Preview 已过期"
              detail="表单语义已经变化；旧结果不能被视为可执行定义，请重新验证并预览。"
              tone="warning"
            />
          ) : (
            <div>
              <PreviewPanel preview={preview.value} />
              <section className="mt-4 rounded-xl border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] p-4">
                <h3 className="text-[12px] font-semibold text-[color:var(--zx-text-title)]">
                  创建持久 Experiment
                </h3>
                <p className="mt-1 text-[11px] text-[color:var(--zx-text-muted)]">
                  Create 会重新复核 preview fingerprint；网络结果未知时可安全重试。
                </p>
                {createCommand.isError ? (
                  <p role="alert" className="mt-3 text-[11px] text-rose-400">
                    {createCommand.error.message}
                  </p>
                ) : null}
                <button
                  type="button"
                  disabled={!previewCurrent || createCommand.isPending}
                  onClick={createExperiment}
                  className="mt-4 rounded-lg bg-[var(--zx-primary)] px-4 py-2 text-[12px] font-semibold text-white disabled:cursor-not-allowed disabled:bg-[var(--zx-disabled-bg)]"
                >
                  {createCommand.isPending
                    ? "创建中…"
                    : "3. 创建并打开 Experiment"}
                </button>
              </section>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

/** Group Composer controls into one research-facing step. */
function FormSection({
  index,
  title,
  detail,
  children,
}: {
  index: string;
  title: string;
  detail: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-6 rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-5">
      <div className="mb-4 flex items-start gap-3">
        <span className="rounded-md bg-[var(--zx-primary-soft)] px-2 py-1 font-mono text-[10px] font-semibold text-[color:var(--zx-primary)]">
          {index}
        </span>
        <div>
          <h2 className="text-[13px] font-semibold text-[color:var(--zx-text-title)]">{title}</h2>
          <p className="mt-1 text-[11px] leading-relaxed text-[color:var(--zx-text-muted)]">{detail}</p>
        </div>
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

/** Render one accessible labeled control. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.08em] text-[color:var(--zx-text-muted)]">
        {label}
      </span>
      {children}
    </label>
  );
}

/** Render one finite integer protocol control. */
function NumberField({
  label,
  value,
  min,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        aria-label={label}
        type="number"
        min={min}
        step={1}
        className="zx-control w-full px-3 py-2 text-[12px]"
        value={value}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next)) onChange(next);
        }}
      />
    </Field>
  );
}

/** Render the normalized, preview-only result without execution affordances. */
function PreviewPanel({ preview }: { preview: ExperimentPreview }) {
  return (
    <div>
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-emerald-400">
          Preview only · deterministic
        </p>
        <h2 className="mt-2 text-[15px] font-semibold text-[color:var(--zx-text-title)]">
          定义可以进入下一阶段复核
        </h2>
        <p className="mt-2 break-all font-mono text-[10px] text-[color:var(--zx-text-muted)]">
          {preview.previewFingerprint}
        </p>
      </div>
      <ResultSection title="Canonical identities">
        {Object.entries(preview.identities).map(([key, value]) => (
          <IdentityRow key={key} label={key} value={value} />
        ))}
        <IdentityRow label="agentGraph" value={preview.agentRevisions[0]?.agentGraph ?? ""} />
      </ResultSection>
      <ResultSection title="Normalized Protocol">
        <div className="grid grid-cols-2 gap-3 text-[11px]">
          <Metric label="seed" value={String(preview.normalizedProtocol.seed)} />
          <Metric label="repeats" value={String(preview.normalizedProtocol.repeats)} />
          <Metric label="max interactions" value={String(preview.normalizedProtocol.budget.maxInteractions)} />
          <Metric label="timeout" value={`${preview.normalizedProtocol.budget.timeoutSeconds}s`} />
        </div>
      </ResultSection>
      <ResultSection title="Ordered schedule">
        {preview.schedule.map((item) => (
          <div key={item.plannedEntryId} className="rounded-lg border border-[var(--zx-border-light)] bg-black/10 p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-semibold text-[color:var(--zx-text-title)]">
                #{item.order + 1} · {item.taskId}
              </span>
              <span className="text-[10px] text-[color:var(--zx-primary)]">
                seed {item.derivedSeed}
              </span>
            </div>
            <p className="mt-2 text-[10px] text-[color:var(--zx-text-muted)]">
              {item.taskInstance.availability === "pending_materialization"
                ? "动态任务将在真正创建 Experiment 时 materialize"
                : "静态 task template，尚未执行"}
            </p>
          </div>
        ))}
      </ResultSection>
      {preview.diagnostics.length > 0 ? (
        <ResultSection title="Warnings">
          {preview.diagnostics.map((item) => (
            <p key={`${item.code}:${item.message}`} className="text-[11px] text-amber-400">
              {item.code}: {item.message}
            </p>
          ))}
        </ResultSection>
      ) : null}
    </div>
  );
}

/** Render one preview result section. */
function ResultSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4 rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-4">
      <h3 className="mb-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-text-muted)]">
        {title}
      </h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

/** Render one canonical identity safely inside the panel. */
function IdentityRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-[9px] uppercase text-[color:var(--zx-text-muted)]">{label}</span>
      <p className="break-all font-mono text-[10px] text-[color:var(--zx-text-body)]">{value}</p>
    </div>
  );
}

/** Render one normalized Protocol metric. */
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-black/10 p-3">
      <span className="text-[9px] uppercase text-[color:var(--zx-text-muted)]">{label}</span>
      <p className="mt-1 font-semibold text-[color:var(--zx-text-title)]">{value}</p>
    </div>
  );
}

/** Render empty, stale, or failed preview state. */
function ResultState({
  title,
  detail,
  tone = "neutral",
}: {
  title: string;
  detail: string;
  tone?: "neutral" | "warning" | "error";
}) {
  const color =
    tone === "error"
      ? "text-rose-400"
      : tone === "warning"
        ? "text-amber-400"
        : "text-[color:var(--zx-text-title)]";
  return (
    <div className="flex min-h-64 flex-col items-center justify-center rounded-xl border border-dashed border-[var(--zx-border-light)] p-8 text-center">
      <h2 className={`text-[14px] font-semibold ${color}`}>{title}</h2>
      <p className="mt-2 max-w-md text-[12px] leading-relaxed text-[color:var(--zx-text-muted)]">{detail}</p>
    </div>
  );
}
