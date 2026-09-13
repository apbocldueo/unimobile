import { useEffect, useMemo, useState } from "react";
import type { BenchmarkContext } from "@/entities/benchmark";
import {
  EvidenceOriginFacts,
  type ExecutionEvidenceOrigin,
} from "@/entities/evidence-origin";
import type {
  ActivationProjection,
  FailureTarget,
  ReplayProjection,
  RunSnapshot,
} from "@/entities/run";
import {
  selectRunStory,
  type StoryFact,
  type StoryStep,
} from "../model/runStoryPresenter";
import { ModelResponseEvidenceViewer } from "./ModelResponseEvidenceViewer";
import styles from "./runInspector.module.css";

export type RunInspectorOverview = {
  agentStatus: string;
  benchmarkOutcome: BenchmarkContext["outcome"] | null;
  failureTarget: FailureTarget | null;
  location: string | null;
  reason: string;
  reasonSource: string;
  counts: { steps: number; activations: number; interactions: number };
  milestones: Array<{
    cursor: number;
    kind: string;
    label: string;
    activationId: string | null;
  }>;
  evidence: {
    graphState: string;
    screenshotState: string;
    integrityState: string;
  };
};

export type RunInspectorViewModel = {
  runId: string;
  snapshot: RunSnapshot;
  projection: ReplayProjection;
  provenance: string;
  agentStatus: string;
  kernelStatus: string;
  benchmarkOutcome: BenchmarkContext["outcome"] | null;
  resultError: string;
  availability: Record<string, { state: string } | undefined>;
  artifactUrl: (artifactId: string) => string;
  loadArtifactText: ((artifactId: string) => Promise<string>) | null;
  readOnlyLabel: string;
  terminalVisible?: boolean;
  overview?: RunInspectorOverview;
  evidenceOrigin?: ExecutionEvidenceOrigin;
};

type RunInspectorProps = {
  viewModel: RunInspectorViewModel;
  selectedActivationId: string | null;
  onSelectActivation: (activationId: string | null) => void;
  onJumpToFailure?: () => void;
  onJumpToMoment?: (cursor: number, activationId: string | null) => void;
};

type InspectorTab = "process" | "component" | "technical";

const TAB_COPY: Array<{ id: InspectorTab; label: string }> = [
  { id: "process", label: "过程" },
  { id: "component", label: "组件详情" },
  { id: "technical", label: "技术详情" },
];

const STATUS_COPY: Record<string, string> = {
  accepted: "等待开始",
  starting: "正在准备",
  running: "运行中",
  success: "已完成",
  completed: "已完成",
  complete: "已完成",
  failure: "运行失败",
  failed: "运行失败",
  cancelled: "已取消",
  cancelling: "正在取消",
  skipped: "已跳过",
  pass: "通过",
  fail: "未通过",
  invalid: "结果无效",
};

/** Return a concise Chinese label without changing the formal stored status. */
function statusLabel(status: string): string {
  return STATUS_COPY[status.toLowerCase()] ?? status;
}

/** Return a short inert representation for one already-sanitized fact value. */
function summarizeValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    const serialized = JSON.stringify(value);
    if (serialized === undefined) return String(value);
    return serialized.length > 360 ? `${serialized.slice(0, 357)}…` : serialized;
  } catch {
    return "[不可序列化摘要]";
  }
}

/** Recursively hide Prompt-shaped values before rendering technical payload evidence. */
function redactPromptFields(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactPromptFields);
  if (typeof value !== "object" || value === null) return value;
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      key.toLowerCase().includes("prompt") ? "[在普通界面中隐藏]" : redactPromptFields(item),
    ]),
  );
}

/** Render the process-first Run Inspector over immutable Live/Replay facts. */
export function RunInspector({
  viewModel,
  selectedActivationId,
  onSelectActivation,
  onJumpToFailure,
  onJumpToMoment,
}: RunInspectorProps) {
  const [tab, setTab] = useState<InspectorTab>("process");
  const overview = viewModel.overview ?? fallbackOverview(viewModel);
  const story = useMemo(
    () => selectRunStory(viewModel.snapshot, viewModel.projection, {
      terminalVisible: viewModel.terminalVisible,
      agentStatus: viewModel.agentStatus,
      resultError: viewModel.resultError,
    }),
    [viewModel],
  );
  const interactionDisplayOffset = story.steps.some((step) => step.interactionStep === 0) ? 1 : 0;
  const selectedStep = selectedActivationId
    ? story.steps.find((step) => step.activationIds.includes(selectedActivationId)) ?? null
    : story.steps.find((step) => step.stepId === story.currentStepId) ?? null;
  const selectedActivation = selectedActivationId
    ? viewModel.projection.activationsById[selectedActivationId] ?? null
    : selectedStep?.primaryActivationId
      ? viewModel.projection.activationsById[selectedStep.primaryActivationId] ?? null
      : null;

  useEffect(() => {
    if (!selectedActivationId) return;
    setTab(selectedStep ? "component" : "technical");
  }, [selectedActivationId, selectedStep]);

  /** Select one story step without mutating factual playback state. */
  const selectStep = (step: StoryStep) => {
    if (!step.primaryActivationId) return;
    onSelectActivation(step.primaryActivationId);
    onJumpToMoment?.(step.endCursor ?? step.startCursor, step.primaryActivationId);
    setTab("component");
  };

  return (
    <aside className={styles.inspector} aria-label="Run Inspector">
      <header className={styles.header}>
        <div>
          <p>AGENT RUN STORY</p>
          <h2>这次 Agent 做了什么</h2>
        </div>
        <span className={styles.readOnly}>{viewModel.readOnlyLabel}</span>
      </header>

      <RunConclusion overview={overview} onJumpToFailure={onJumpToFailure} />

      <div className={styles.tabs} role="tablist" aria-label="Inspector 视图">
        {TAB_COPY.map((item) => (
          <button
            aria-controls={`run-inspector-${item.id}`}
            aria-selected={tab === item.id}
            className={tab === item.id ? styles.activeTab : ""}
            id={`run-inspector-tab-${item.id}`}
            key={item.id}
            onClick={() => setTab(item.id)}
            role="tab"
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>

      <div
        aria-labelledby={`run-inspector-tab-${tab}`}
        className={styles.tabPanel}
        id={`run-inspector-${tab}`}
        role="tabpanel"
      >
        {tab === "process" ? (
          <ProcessView
            story={story}
            selectedActivationId={selectedActivationId}
            onSelectStep={selectStep}
            onReturnToCurrent={() => onSelectActivation(null)}
          />
        ) : tab === "component" ? (
          <ComponentView
            step={selectedStep}
            displayInteractionStep={selectedStep ? selectedStep.interactionStep + interactionDisplayOffset : null}
            artifactUrl={viewModel.artifactUrl}
            locked={selectedActivationId !== null}
            onReturnToCurrent={() => onSelectActivation(null)}
          />
        ) : (
          <TechnicalView
            viewModel={viewModel}
            overview={overview}
            story={story}
            selectedStep={selectedStep}
            selectedActivation={selectedActivation}
            selectedActivationId={selectedActivationId}
            onSelectActivation={onSelectActivation}
            onJumpToMoment={onJumpToMoment}
          />
        )}
      </div>
    </aside>
  );
}

/** Build a truthful bounded overview for Live callers without a Replay selector. */
function fallbackOverview(viewModel: RunInspectorViewModel): RunInspectorOverview {
  const target = viewModel.projection.failureTargets[0] ?? null;
  return {
    agentStatus: viewModel.agentStatus,
    benchmarkOutcome: viewModel.benchmarkOutcome,
    failureTarget: target,
    location: target?.nodePath ?? null,
    reason: target?.label ?? `Agent ${viewModel.agentStatus}`,
    reasonSource: target ? "failure_target" : "status",
    counts: {
      steps: Math.max(viewModel.projection.currentInteractionStep, 0),
      activations: viewModel.projection.activationOrder.length,
      interactions: Math.max(viewModel.projection.currentInteractionStep, 0),
    },
    milestones: [],
    evidence: {
      graphState: viewModel.snapshot.graphStatus,
      screenshotState: viewModel.availability.screenshots?.state ?? "not_captured",
      integrityState: viewModel.projection.integrityState,
    },
  };
}

/** Render a compact outcome strip that does not compete with the process story. */
function RunConclusion({
  overview,
  onJumpToFailure,
}: {
  overview: RunInspectorOverview;
  onJumpToFailure?: () => void;
}) {
  return (
    <section className={styles.conclusionStrip} aria-label="运行结论">
      <div>
        <span>Agent</span>
        <strong data-status={overview.agentStatus}>{statusLabel(overview.agentStatus)}</strong>
      </div>
      {overview.benchmarkOutcome ? (
        <div>
          <span>Benchmark</span>
          <strong data-status={overview.benchmarkOutcome}>{statusLabel(overview.benchmarkOutcome)}</strong>
        </div>
      ) : null}
      {overview.failureTarget && onJumpToFailure ? (
        <button onClick={onJumpToFailure} type="button">定位失败事实</button>
      ) : null}
    </section>
  );
}

/** Render the cumulative causal ribbon grouped by real interaction boundaries. */
function ProcessView({
  story,
  selectedActivationId,
  onSelectStep,
  onReturnToCurrent,
}: {
  story: ReturnType<typeof selectRunStory>;
  selectedActivationId: string | null;
  onSelectStep: (step: StoryStep) => void;
  onReturnToCurrent: () => void;
}) {
  const interactions = new Map<number, StoryStep[]>();
  for (const step of story.steps) {
    const items = interactions.get(step.interactionStep) ?? [];
    items.push(step);
    interactions.set(step.interactionStep, items);
  }
  const interactionDisplayOffset = interactions.has(0) ? 1 : 0;
  if (story.steps.length === 0) {
    return (
      <div className={styles.guidedEmpty}>
        <strong>等待第一个组件步骤</strong>
        <p>运行事实到达后，这里会持续保留观察、判断和行动，不会被下一条内部事件覆盖。</p>
      </div>
    );
  }
  return (
    <>
      {selectedActivationId ? (
        <div className={styles.lockNotice}>
          <span>组件详情已锁定；过程仍在继续更新。</span>
          <button onClick={onReturnToCurrent} type="button">回到当前</button>
        </div>
      ) : null}
      {story.truncatedStepCount > 0 ? (
        <p className={styles.notice}>较早的 {story.truncatedStepCount} 个步骤已从此紧凑视图收起，完整顺序仍在时间轴中。</p>
      ) : null}
      <div className={styles.storyGroups}>
        {[...interactions.entries()].map(([interactionStep, steps]) => (
          <section className={styles.storyGroup} key={interactionStep}>
            <header>
              <span>交互 {interactionStep + interactionDisplayOffset}</span>
              <small>{steps.length} 个关键步骤</small>
            </header>
            <ol className={styles.causalRibbon}>
              {steps.map((step) => {
                const current = step.stepId === story.currentStepId;
                const selectable = Boolean(step.primaryActivationId);
                return (
                  <li data-status={step.status} key={step.stepId}>
                    <span className={styles.railMarker} aria-hidden="true" />
                    <button
                      aria-current={current ? "step" : undefined}
                      className={current ? styles.currentStoryStep : ""}
                      disabled={!selectable}
                      onClick={() => onSelectStep(step)}
                      type="button"
                    >
                      <span className={styles.storyMeta}>
                        <strong>{step.verb}</strong>
                        <small>{step.roleLabel} · {statusLabel(step.status)}</small>
                      </span>
                      <span className={styles.storyCopy}>
                        <strong>{step.title}</strong>
                        <small>{step.summary}</small>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </section>
        ))}
      </div>
    </>
  );
}

/** Render reader-facing inputs and outputs for one selected story step. */
function ComponentView({
  step,
  displayInteractionStep,
  artifactUrl,
  locked,
  onReturnToCurrent,
}: {
  step: StoryStep | null;
  displayInteractionStep: number | null;
  artifactUrl: (artifactId: string) => string;
  locked: boolean;
  onReturnToCurrent: () => void;
}) {
  if (!step) {
    return (
      <div className={styles.guidedEmpty}>
        <strong>选择一个过程步骤</strong>
        <p>这里会把该组件本次执行的输入和输出分开说明；未映射的内部事实请到技术详情查看。</p>
      </div>
    );
  }
  return (
    <>
      <section className={styles.componentHero} data-status={step.status}>
        <div>
          <span>{step.roleLabel}</span>
          <h3>{step.title}</h3>
          <p>{step.summary}</p>
        </div>
        <strong>{statusLabel(step.status)}</strong>
      </section>
      {locked ? (
        <div className={styles.lockNotice}>
          <span>正在查看历史步骤，运行事实不会覆盖这里。</span>
          <button onClick={onReturnToCurrent} type="button">回到当前</button>
        </div>
      ) : null}
      <div className={styles.ioGrid}>
        <FactPanel
          facts={step.inputs}
          kind="input"
          title="输入"
          empty="本次运行没有采集到可展示的安全输入摘要。"
          artifactUrl={artifactUrl}
        />
        <FactPanel
          facts={step.outputs}
          kind="output"
          title="输出"
          empty="本次运行没有采集到可展示的安全输出摘要。"
          artifactUrl={artifactUrl}
        />
      </div>
      <section className={styles.componentFacts}>
        <div><span>交互</span><strong>{displayInteractionStep}</strong></div>
        <div><span>耗时</span><strong>{step.durationMs === null ? "未记录" : `${step.durationMs.toFixed(1)} ms`}</strong></div>
        <div><span>执行次数</span><strong>{step.activationIds.length}</strong></div>
      </section>
      {step.error ? <p className={styles.errorBox}>{step.error}</p> : null}
    </>
  );
}

/** Render one explicitly labelled input or output fact panel. */
function FactPanel({
  facts,
  kind,
  title,
  empty,
  artifactUrl,
}: {
  facts: StoryFact[];
  kind: "input" | "output";
  title: string;
  empty: string;
  artifactUrl: (artifactId: string) => string;
}) {
  return (
    <section className={styles.factPanel} data-kind={kind}>
      <header><span aria-hidden="true">{kind === "input" ? "↘" : "↗"}</span><h3>{title}</h3></header>
      {facts.length ? (
        <dl>
          {facts.map((fact, index) => (
            <div key={`${fact.key}-${index}`}>
              <dt>{fact.label}</dt>
              <dd>
                {fact.artifactId ? (
                  <a href={artifactUrl(fact.artifactId)} rel="noreferrer" target="_blank">
                    {summarizeValue(fact.value)} · 查看证据
                  </a>
                ) : summarizeValue(fact.value)}
              </dd>
            </div>
          ))}
        </dl>
      ) : <p>{empty}</p>}
    </section>
  );
}

/** Render exact identities and evidence only after the user opens technical detail. */
function TechnicalView({
  viewModel,
  overview,
  story,
  selectedStep,
  selectedActivation,
  selectedActivationId,
  onSelectActivation,
  onJumpToMoment,
}: {
  viewModel: RunInspectorViewModel;
  overview: RunInspectorOverview;
  story: ReturnType<typeof selectRunStory>;
  selectedStep: StoryStep | null;
  selectedActivation: ActivationProjection | null;
  selectedActivationId: string | null;
  onSelectActivation: (activationId: string | null) => void;
  onJumpToMoment?: (cursor: number, activationId: string | null) => void;
}) {
  const selectedDebug = selectedActivation
    ? viewModel.projection.debugByActivationId[selectedActivation.activationId]?.at(-1) ?? null
    : null;
  const currentObservation = selectedStep
    ? [...viewModel.projection.visibleObservationIds]
      .reverse()
      .map((id) => viewModel.projection.observationsById[id])
      .find((item) => item?.interactionStep === selectedStep.interactionStep) ?? null
    : null;
  return (
    <>
      <Disclosure title="运行身份与完整性">
        <Fact label="Run" value={viewModel.runId} />
        <Fact label="Agent" value={viewModel.snapshot.agentId || "unknown"} />
        <Fact label="Revision" value={viewModel.snapshot.revisionId ?? "not captured"} />
        <Fact label="Canonical hash" value={viewModel.snapshot.canonicalHash ?? "not captured"} />
        <Fact label="Provenance" value={viewModel.provenance} />
        <Fact label="Kernel" value={viewModel.kernelStatus || "—"} />
        <Fact label="Projection integrity" value={viewModel.projection.integrityState} />
        {viewModel.evidenceOrigin ? (
          <EvidenceOriginFacts origin={viewModel.evidenceOrigin} title="Replay 证据来源" />
        ) : null}
      </Disclosure>

      <Disclosure title="组件定义与 exact activation">
        {selectedActivation ? (
          <>
            <Fact label="Activation" value={selectedActivation.activationId} />
            <Fact label="Node path" value={selectedActivation.nodePath || selectedActivation.nodeId} />
            <Fact label="Role" value={selectedActivation.role || "—"} />
            <Fact label="Component" value={selectedActivation.component || "built-in / unknown"} />
            <Fact label="Interaction" value={String(selectedActivation.interactionStep)} />
            <Fact label="Status" value={selectedActivation.status} />
          </>
        ) : <Empty>当前没有选中的 exact activation。</Empty>}
        <Fact label="Contract" value={viewModel.snapshot.contractVersion} />
      </Disclosure>

      <Disclosure title="证据与安全原始数据">
        <ModelResponseEvidenceViewer
          reference={selectedStep?.modelResponse ?? null}
          availability={selectedStep?.modelResponseAvailability ?? "not_captured"}
          loadText={viewModel.loadArtifactText}
        />
        <Availability label="Debug Payload" state={selectedDebug?.availability.debugPayload ?? viewModel.availability.debugPayload?.state ?? "not_captured"} />
        <Availability label="Prompt" state={viewModel.availability.prompt?.state ?? selectedStep?.promptAvailability ?? selectedDebug?.availability.prompt ?? "not_captured"} />
        {selectedActivation ? (
          <details className={styles.rawPayload}>
            <summary>查看安全原始 Payload</summary>
            <pre>{JSON.stringify(redactPromptFields(selectedActivation.payloadHistory), null, 2)}</pre>
          </details>
        ) : null}
        {currentObservation?.uiArtifactId ? (
          <a className={styles.link} href={viewModel.artifactUrl(currentObservation.uiArtifactId)} rel="noreferrer" target="_blank">
            打开本次交互的 UI XML
          </a>
        ) : null}
      </Disclosure>

      <Disclosure title={`Exact activation 历史 · ${viewModel.projection.activationOrder.length}`}>
        <div className={styles.history}>
          {viewModel.projection.activationOrder.map((activationId) => {
            const activation = viewModel.projection.activationsById[activationId]!;
            return (
              <button
                className={activationId === selectedActivation?.activationId ? styles.selected : ""}
                key={activationId}
                onClick={() => {
                  onSelectActivation(activationId);
                  onJumpToMoment?.(activation.endCursor ?? activation.startCursor, activationId);
                }}
                type="button"
              >
                <StatusDot status={activation.status} />
                <span><strong>{activation.nodePath || activation.nodeId}</strong><small>{activation.activationId} · interaction {activation.interactionStep}</small></span>
              </button>
            );
          })}
        </div>
        {selectedActivationId ? <button className={styles.linkButton} onClick={() => onSelectActivation(null)} type="button">回到当前</button> : null}
      </Disclosure>

      {story.unmappedActivationIds.length ? (
        <Disclosure title={`未映射运行事实 · ${story.unmappedActivationIds.length}`}>
          <p className={styles.notice}>这些 exact activation 没有可信 capability owner，因此没有进入默认过程。</p>
          {story.unmappedActivationIds.map((activationId) => <Fact key={activationId} label="Activation" value={activationId} />)}
        </Disclosure>
      ) : null}

      <Disclosure title="运行计数与证据状态">
        <Fact label="Steps" value={String(overview.counts.steps)} />
        <Fact label="Activations" value={String(overview.counts.activations)} />
        <Fact label="Interactions" value={String(overview.counts.interactions)} />
        <Availability label="AgentGraph" state={overview.evidence.graphState} />
        <Availability label="Screenshot" state={overview.evidence.screenshotState} />
        <Availability label="Integrity" state={overview.evidence.integrityState} />
        {viewModel.resultError ? <p className={styles.errorBox}>{viewModel.resultError}</p> : null}
      </Disclosure>
    </>
  );
}

/** Render one collapsed secondary audit section. */
function Disclosure({ title, children }: { title: string; children: React.ReactNode }) {
  return <details className={styles.disclosure}><summary>{title}</summary><div>{children}</div></details>;
}

/** Render one exact identity fact without promoting it to the default story. */
function Fact({ label, value }: { label: string; value: string }) {
  return <div className={styles.fact}><span>{label}</span><code title={value}>{value}</code></div>;
}

/** Render one evidence availability fact with text and color. */
function Availability({ label, state }: { label: string; state: string }) {
  return <div className={styles.availability}><span>{label}</span><strong data-state={state}>{state}</strong></div>;
}

/** Render an activation status marker with a non-color accessible label. */
function StatusDot({ status }: { status: string }) {
  return <span aria-label={statusLabel(status)} className={`${styles.dot} ${styles[status] ?? ""}`} role="img" />;
}

/** Render truthful empty-state guidance. */
function Empty({ children }: { children: React.ReactNode }) {
  return <p className={styles.notice}>{children}</p>;
}
