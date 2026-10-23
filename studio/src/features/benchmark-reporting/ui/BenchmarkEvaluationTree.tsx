import { useEffect, useState } from "react";
import type {
  BenchmarkEvaluationNode,
  BenchmarkEvaluationEvidence,
  BenchmarkEvidenceSelection,
} from "@/entities/benchmark-report";
import type { JsonValue } from "@/shared/lib";
import type { BenchmarkEvaluationProjection } from "../model/benchmarkReportProjection";
import type { BenchmarkReportComponentState } from "../model/benchmarkReportState";

type BenchmarkEvaluationTreeProps = {
  projection: BenchmarkEvaluationProjection | null;
  state: BenchmarkReportComponentState;
  onRetry: () => void;
  onOpenEvidence?: (selection: BenchmarkEvidenceSelection) => void;
};

/** Render a bounded auditable Evaluation Tree using stable node paths. */
export function BenchmarkEvaluationTree({
  projection,
  state,
  onRetry,
  onOpenEvidence,
}: BenchmarkEvaluationTreeProps) {
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(projection?.defaultExpandedPaths ?? []),
  );

  useEffect(() => {
    setExpanded(new Set(projection?.defaultExpandedPaths ?? []));
  }, [projection]);

  if (!projection) {
    return (
      <section className="grid h-full place-items-center p-6 text-center">
        <div>
          <span className="text-2xl text-[color:var(--zx-text-muted)]">◇</span>
          <h2 className="mt-2 text-[12px] font-semibold text-[color:var(--zx-text-title)]">
            Evaluation unavailable
          </h2>
          <p
            data-state={state.kind}
            className="mt-2 max-w-sm text-[10px] leading-relaxed text-[color:var(--zx-text-muted)]"
          >
            {state.message}
          </p>
          {state.retryable ? (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 text-[10px] text-[color:var(--zx-primary)] underline"
            >
              Retry Evaluation
            </button>
          ) : null}
        </div>
      </section>
    );
  }

  /** Toggle one verified path without mounting unrelated descendants. */
  const toggle = (path: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  return (
    <section className="h-full min-h-0 overflow-auto bg-[var(--zx-canvas)] p-4">
      <header className="mb-4">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-primary)]">
          Evaluation Tree
        </p>
        <p className="mt-1 text-[10px] text-[color:var(--zx-text-muted)]">
          Auditable evidence for manual failure localization; this is not
          automatic root-cause diagnosis.
        </p>
      </header>
      <div role="tree" aria-label="Benchmark Evaluation Tree">
        <EvaluationNode
          node={projection.root}
          depth={1}
          expanded={expanded}
          onToggle={toggle}
          onOpenEvidence={onOpenEvidence}
        />
      </div>
    </section>
  );
}

type EvaluationNodeProps = {
  node: BenchmarkEvaluationNode;
  depth: number;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  onOpenEvidence?: (selection: BenchmarkEvidenceSelection) => void;
};

/** Render one Evaluation node and only its currently expanded descendants. */
function EvaluationNode({
  node,
  depth,
  expanded,
  onToggle,
  onOpenEvidence,
}: EvaluationNodeProps) {
  const hasChildren = node.children.length > 0;
  const isExpanded = hasChildren && expanded.has(node.path);
  return (
    <div
      role="treeitem"
      aria-level={depth}
      aria-expanded={hasChildren ? isExpanded : undefined}
      data-node-path={node.path}
      className="mb-2"
    >
      <div className="rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-card)] p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {hasChildren ? (
                <button
                  type="button"
                  aria-label={`${isExpanded ? "Collapse" : "Expand"} ${node.name}`}
                  onClick={() => onToggle(node.path)}
                  className="grid h-5 w-5 shrink-0 place-items-center rounded border border-[var(--zx-border-light)] text-[10px] text-[color:var(--zx-text-muted)]"
                >
                  {isExpanded ? "−" : "+"}
                </button>
              ) : (
                <span
                  aria-hidden
                  className="block h-2 w-2 shrink-0 rounded-full bg-[var(--zx-primary)]"
                />
              )}
              <strong className="truncate text-[11px] text-[color:var(--zx-text-title)]">
                {node.name}
              </strong>
              <code className="truncate text-[9px] text-[color:var(--zx-text-muted)]">
                {node.path}
              </code>
            </div>
            <p className="mt-2 text-[9px] text-[color:var(--zx-text-muted)]">
              status {node.status} · pass {passLabel(node.isPass)} · score{" "}
              {node.score ?? "unavailable"} · {node.durationMs} ms
            </p>
          </div>
          {node.shortCircuited ? (
            <span className="shrink-0 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[9px] text-amber-200">
              short-circuited
            </span>
          ) : null}
        </div>
        {node.reason ? (
          <p className="mt-2 text-[10px] leading-relaxed text-[color:var(--zx-text-muted)]">
            {node.reason}
          </p>
        ) : null}
        <div className="mt-2 grid gap-1 text-[9px] text-[color:var(--zx-text-muted)]">
          <span>aggregation {safeValueSummary(node.aggregation)}</span>
          <span>
            token{" "}
            {node.token === "<redacted>"
              ? "unavailable (safely redacted)"
              : node.token ?? "unavailable"}
          </span>
        </div>
        {node.children.length === 0 && node.evaluatorResult ? (
          <EvaluatorFacts node={node} onOpenEvidence={onOpenEvidence} />
        ) : null}
      </div>
      {isExpanded ? (
        <div
          role="group"
          className="ml-4 mt-2 border-l border-[var(--zx-divider-ui)] pl-3"
        >
          {node.children.map((child) => (
            <EvaluationNode
              key={child.path}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              onOpenEvidence={onOpenEvidence}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Render one bounded evaluator result and descriptor-only evidence list. */
function EvaluatorFacts({
  node,
  onOpenEvidence,
}: {
  node: BenchmarkEvaluationNode;
  onOpenEvidence?: (selection: BenchmarkEvidenceSelection) => void;
}) {
  const evaluator = node.evaluatorResult!;
  return (
    <section className="mt-3 border-t border-[var(--zx-divider-ui)] pt-3">
      <p className="text-[9px] text-[color:var(--zx-text-muted)]">
        evaluator {evaluator.evaluatorId} · {evaluator.status} · pass{" "}
        {passLabel(evaluator.passed)} · score {evaluator.score ?? "unavailable"}
      </p>
      {evaluator.evidence.length > 0 ? (
        <ul aria-label={`${node.name} evidence`} className="mt-2 space-y-1">
          {evaluator.evidence.map((evidence, index) => (
            <EvidenceDescriptor
              key={`${evidence.kind}-${evidence.artifactRef}-${index}`}
              evidence={evidence}
              onOpen={
                evidence.artifactRef.length > 0 && onOpenEvidence
                  ? () => onOpenEvidence({
                      leafPath: node.path,
                      evidenceIndex: index,
                      evidence,
                    })
                  : undefined
              }
            />
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-[9px] text-[color:var(--zx-text-muted)]">
          No evaluator evidence descriptors.
        </p>
      )}
    </section>
  );
}

/** Render safe metadata and an optional typed 5.4D-2 open intent. */
function EvidenceDescriptor({
  evidence,
  onOpen,
}: {
  evidence: BenchmarkEvaluationEvidence;
  onOpen?: () => void;
}) {
  return (
    <li className="rounded border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] p-2 text-[9px] text-[color:var(--zx-text-muted)]">
      <strong className="text-[color:var(--zx-text-title)]">
        {evidence.kind}
      </strong>
      <span className="ml-2">
        {evidence.artifactRef ? "descriptor available" : "inline descriptor"}
      </span>
      <span className="mt-1 block">
        value {safeValueSummary(evidence.value)}
      </span>
      {evidence.artifactRef ? (
        <code className="mt-1 block break-all">{evidence.artifactRef}</code>
      ) : null}
      {onOpen ? (
        <button
          type="button"
          onClick={onOpen}
          className="mt-2 text-[9px] text-[color:var(--zx-primary)] underline"
        >
          Open evidence
        </button>
      ) : null}
    </li>
  );
}

/** Preserve the three-state pass contract without treating null as failure. */
function passLabel(value: boolean | null): string {
  return value === true ? "passed" : value === false ? "not passed" : "undetermined";
}

/** Summarize bounded JSON structurally without exposing nested secret values. */
function safeValueSummary(value: JsonValue): string {
  if (value === null) return "null";
  if (typeof value === "boolean" || typeof value === "number") {
    return String(value);
  }
  if (typeof value === "string") {
    if (
      value.startsWith("/")
      || /^[A-Za-z]:[\\/]/.test(value)
      || value.includes("\n")
    ) {
      return "[string value omitted]";
    }
    return value.length > 80 ? `${value.slice(0, 77)}…` : value;
  }
  if (Array.isArray(value)) return `array(${value.length})`;
  return `object(${Object.keys(value).length} fields)`;
}
