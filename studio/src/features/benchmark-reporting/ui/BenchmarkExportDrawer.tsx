import { useEffect, useMemo, useRef, useState } from "react";
import type {
  BenchmarkPublicationManifestSummary,
} from "@/entities/benchmark-report";
import {
  EvidenceOriginFacts,
  type ExecutionEvidenceOrigin,
} from "@/entities/evidence-origin";
import { studioApiUrl } from "@/shared/api";
import type {
  BenchmarkExportManifestState,
  BenchmarkExportPrepareState,
} from "../model/useBenchmarkExport";
import type {
  BenchmarkExportMaterial,
  BenchmarkExportMaterialProjection,
} from "../model/benchmarkExportMaterials";

const EVIDENCE_PAGE_SIZE = 10;

type BenchmarkExportDrawerProps = {
  projection: BenchmarkExportMaterialProjection | null;
  projectionError: string | null;
  prepareStates: ReadonlyMap<string, BenchmarkExportPrepareState>;
  manifestState: BenchmarkExportManifestState;
  evidenceOrigin?: ExecutionEvidenceOrigin | null;
  onPrepare: (material: BenchmarkExportMaterial) => void;
  onHandOff: (material: BenchmarkExportMaterial) => void;
  onReviewManifest: (material: BenchmarkExportMaterial) => void;
  onCloseManifest: () => void;
  onClose: () => void;
};

/** Render the short-lived Report-local Export surface.
 *
 * Args:
 *   projection: Closed authoritative inventory projection, if valid.
 *   projectionError: Safe local projection failure copy.
 *   prepareStates: Independent transport state keyed by immutable target facts.
 *   manifestState: Disposable bounded publication-manifest summary.
 *   evidenceOrigin: Selected authoritative TaskRun origin used as context only.
 *   onPrepare: Starts refresh plus no-body HEAD verification.
 *   onHandOff: Records only activation of the exact browser capability.
 *   onReviewManifest: Loads the bounded managed manifest without opening ZIP.
 *   onCloseManifest: Releases manifest bytes and summary state.
 *   onClose: Aborts and disposes all Export-local work.
 *
 * Returns:
 *   An accessible non-modal drawer that never owns artifact bytes.
 */
export function BenchmarkExportDrawer({
  projection,
  projectionError,
  prepareStates,
  manifestState,
  evidenceOrigin = null,
  onPrepare,
  onHandOff,
  onReviewManifest,
  onCloseManifest,
  onClose,
}: BenchmarkExportDrawerProps) {
  const drawerRef = useRef<HTMLElement>(null);
  const [evidencePage, setEvidencePage] = useState(0);

  useEffect(() => {
    drawerRef.current?.focus();
  }, []);

  const evidencePages = projection
    ? Math.max(1, Math.ceil(
      projection.otherEvidence.length / EVIDENCE_PAGE_SIZE,
    ))
    : 1;
  const boundedPage = Math.min(evidencePage, evidencePages - 1);
  const visibleEvidence = useMemo(
    () => projection?.otherEvidence.slice(
      boundedPage * EVIDENCE_PAGE_SIZE,
      (boundedPage + 1) * EVIDENCE_PAGE_SIZE,
    ) ?? [],
    [boundedPage, projection],
  );

  return (
    <aside
      ref={drawerRef}
      role="dialog"
      aria-modal="false"
      aria-label="Benchmark export"
      tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
      className="absolute inset-y-3 right-3 z-30 flex w-[min(46rem,calc(100%-1.5rem))] flex-col overflow-hidden rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] shadow-2xl outline-none"
    >
      <header className="flex items-start justify-between gap-4 border-b border-[var(--zx-divider-ui)] px-4 py-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-primary)]">
            Benchmark Export
          </p>
          <h2 className="mt-1 text-[12px] font-semibold text-[color:var(--zx-text-title)]">
            Published materials
          </h2>
          <p className="mt-1 max-w-xl text-[9px] text-[color:var(--zx-text-muted)]">
            Prepare refreshes durable metadata and verifies response headers.
            Handoff delegates the exact capability to the browser; this UI
            cannot observe download, save, client digest, or bundle-verifier
            completion.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-[var(--zx-border-light)] px-2 py-1 text-[10px] text-[color:var(--zx-text-title)]"
        >
          Close export
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-auto p-4">
        {evidenceOrigin ? (
          <EvidenceOriginFacts
            origin={evidenceOrigin}
            title="Selected TaskRun context"
          />
        ) : (
          <ExportNotice
            state="provenance-unavailable"
            copy="Selected TaskRun provenance is unavailable; Export metadata cannot establish execution origin."
          />
        )}
        {projectionError ? (
          <ExportNotice state="projection-failed" copy={projectionError} />
        ) : null}
        {!projection && !projectionError ? (
          <ExportNotice
            state="inventory-unavailable"
            copy="A complete artifact inventory is not available for Export."
          />
        ) : null}
        {projection ? (
          <>
            <ExportSection title="Experiment components">
              <MaterialRow
                label="Experiment report"
                material={projection.experimentReport}
                state={stateFor(
                  projection.experimentReport,
                  prepareStates,
                )}
                onPrepare={onPrepare}
                onHandOff={onHandOff}
              />
              <MaterialRow
                label="Experiment bundle"
                material={projection.experimentBundle}
                state={stateFor(
                  projection.experimentBundle,
                  prepareStates,
                )}
                onPrepare={onPrepare}
                onHandOff={onHandOff}
              />
              <MaterialRow
                label="Publication manifest"
                material={projection.publicationManifest}
                state={stateFor(
                  projection.publicationManifest,
                  prepareStates,
                )}
                onPrepare={onPrepare}
                onHandOff={onHandOff}
                onReview={onReviewManifest}
              />
            </ExportSection>

            {manifestState.kind !== "idle" ? (
              <ManifestReview
                bundle={projection.experimentBundle}
                state={manifestState}
                onClose={onCloseManifest}
              />
            ) : null}

            <ExportSection title="TaskRun materials">
              {projection.taskMaterials.size > 0 ? (
                Array.from(projection.taskMaterials.entries()).map(
                  ([taskRunId, materials]) => (
                    <section
                      key={taskRunId}
                      className="rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] p-3"
                    >
                      <code className="block break-all text-[9px] text-[color:var(--zx-text-muted)]">
                        {taskRunId}
                      </code>
                      <div className="mt-2 space-y-2">
                        {materials.map((material) => (
                          <MaterialRow
                            key={material.key}
                            label={materialLabel(material)}
                            material={material}
                            state={prepareStates.get(material.key) ?? {
                              kind: "idle",
                            }}
                            onPrepare={onPrepare}
                            onHandOff={onHandOff}
                          />
                        ))}
                      </div>
                    </section>
                  ),
                )
              ) : (
                <EmptyFact copy="No readable TaskRun report or trajectory is published." />
              )}
            </ExportSection>

            <ExportSection title="Other readable evidence">
              {visibleEvidence.length > 0 ? (
                visibleEvidence.map((material) => (
                  <MaterialRow
                    key={material.key}
                    label={material.item.descriptor.kind}
                    material={material}
                    state={prepareStates.get(material.key) ?? { kind: "idle" }}
                    onPrepare={onPrepare}
                    onHandOff={onHandOff}
                  />
                ))
              ) : (
                <EmptyFact copy="No additional readable evidence is published." />
              )}
              {evidencePages > 1 ? (
                <nav
                  aria-label="Other evidence pages"
                  className="flex items-center justify-end gap-2 text-[9px]"
                >
                  <button
                    type="button"
                    disabled={boundedPage === 0}
                    onClick={() => setEvidencePage((page) => Math.max(0, page - 1))}
                    className="rounded border border-[var(--zx-border-light)] px-2 py-1 disabled:opacity-40"
                  >
                    Previous evidence
                  </button>
                  <span>{boundedPage + 1} / {evidencePages}</span>
                  <button
                    type="button"
                    disabled={boundedPage + 1 >= evidencePages}
                    onClick={() => setEvidencePage((page) => (
                      Math.min(evidencePages - 1, page + 1)
                    ))}
                    className="rounded border border-[var(--zx-border-light)] px-2 py-1 disabled:opacity-40"
                  >
                    Next evidence
                  </button>
                </nav>
              ) : null}
            </ExportSection>

            <ExportSection title="Unavailable publication facts">
              {projection.unavailable.length > 0 ? (
                <ul className="space-y-2">
                  {projection.unavailable.map((material) => (
                    <li
                      key={material.key}
                      className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-[9px]"
                    >
                      <strong className="text-amber-100">
                        {material.item.descriptor.kind}
                      </strong>
                      <span className="ml-2 text-amber-200">
                        {material.item.descriptor.availability}
                      </span>
                      <code className="mt-1 block break-all text-amber-200/80">
                        {material.item.descriptor.taskRunId
                          ?? projection.experimentId}
                      </code>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyFact copy="No visible unavailable artifact descriptors." />
              )}
              <p className="mt-2 text-[9px] text-[color:var(--zx-text-muted)]">
                Hidden artifact descriptors: {projection.hiddenCount}. Hidden
                identities, Prompt content, storage references, and host paths
                are not exposed.
              </p>
            </ExportSection>
          </>
        ) : null}
      </div>
    </aside>
  );
}

/** Render one semantic drawer section. */
function ExportSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title}>
      <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[color:var(--zx-text-muted)]">
        {title}
      </h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

/** Resolve a nullable material to its isolated transport state. */
function stateFor(
  material: BenchmarkExportMaterial | null,
  states: ReadonlyMap<string, BenchmarkExportPrepareState>,
): BenchmarkExportPrepareState {
  return material
    ? states.get(material.key) ?? { kind: "idle" }
    : { kind: "idle" };
}

/** Render one exact immutable material and its prepare/handoff controls. */
function MaterialRow({
  label,
  material,
  state,
  onPrepare,
  onHandOff,
  onReview,
}: {
  label: string;
  material: BenchmarkExportMaterial | null;
  state: BenchmarkExportPrepareState;
  onPrepare: (material: BenchmarkExportMaterial) => void;
  onHandOff: (material: BenchmarkExportMaterial) => void;
  onReview?: (material: BenchmarkExportMaterial) => void;
}) {
  if (!material) {
    return <EmptyFact copy={`${label}: not published.`} />;
  }
  const descriptor = material.item.descriptor;
  const preparing = state.kind === "refreshing-metadata"
    || state.kind === "verifying-head";
  return (
    <article
      data-material-kind={descriptor.kind}
      className="rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] p-3"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <strong className="text-[10px] text-[color:var(--zx-text-title)]">
            {label}
          </strong>
          <p className="mt-1 break-all text-[9px] text-[color:var(--zx-text-muted)]">
            {descriptor.contentType} · {formatBytes(descriptor.size)} ·{" "}
            {descriptor.availability}
          </p>
          <code className="mt-1 block break-all text-[8px] text-[color:var(--zx-text-muted)]">
            {descriptor.artifactId} · {shortDigest(descriptor.sha256)}
          </code>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          {onReview ? (
            <button
              type="button"
              onClick={() => onReview(material)}
              className="rounded border border-[var(--zx-border-light)] px-2 py-1 text-[9px] text-[color:var(--zx-text-title)]"
            >
              Review manifest
            </button>
          ) : null}
          {state.kind === "ready-for-handoff" ? (
            <a
              href={studioApiUrl(state.item.links.content!)}
              target="_blank"
              rel="noreferrer"
              onClick={() => onHandOff(material)}
              className="rounded border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-2 py-1 text-[9px] font-semibold text-[color:var(--zx-primary)]"
            >
              Hand off to browser
            </a>
          ) : (
            <button
              type="button"
              disabled={preparing || state.kind === "handed-off"}
              onClick={() => onPrepare(material)}
              className="rounded border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] px-2 py-1 text-[9px] font-semibold text-[color:var(--zx-primary)] disabled:opacity-50"
            >
              {preparing ? "Preparing…" : state.kind === "failed"
                ? "Retry prepare"
                : "Prepare export"}
            </button>
          )}
        </div>
      </div>
      <MaterialState state={state} />
    </article>
  );
}

/** Render safe transport copy without raw backend or browser claims. */
function MaterialState({ state }: { state: BenchmarkExportPrepareState }) {
  const copy: Record<BenchmarkExportPrepareState["kind"], string> = {
    idle: "Not prepared.",
    "refreshing-metadata": "Refreshing Experiment, TaskRuns, and closed inventory…",
    "verifying-head": "Verifying the exact managed response without reading its body…",
    "ready-for-handoff":
      "Headers match refreshed metadata. The exact browser capability is ready.",
    "handed-off":
      "Link handed to the browser. Browser/OS transfer completion is not observed.",
    failed: "",
  };
  const detail = state.kind === "failed"
    ? failureCopy(state.failure, state.availability)
    : copy[state.kind];
  return (
    <p
      role="status"
      data-state={state.kind}
      className="mt-2 text-[9px] text-[color:var(--zx-text-muted)]"
    >
      {detail}
    </p>
  );
}

/** Return fixed retryable failure copy for one prepared material. */
function failureCopy(failure: string, availability: string | null): string {
  const copy: Record<string, string> = {
    "stale-target":
      "Metadata changed during preparation. Refresh and prepare this exact target again.",
    "scope-conflict":
      "The refreshed inventory conflicts with the current Experiment scope.",
    unavailable:
      `The refreshed artifact is not readable (${availability ?? "unavailable"}).`,
    "header-conflict":
      "Response headers conflict with the refreshed descriptor; handoff is blocked.",
    "request-failed":
      "Preparation could not be completed safely. No artifact bytes were loaded.",
  };
  return copy[failure] ?? copy["request-failed"]!;
}

/** Render bounded declared bundle facts without creating member links. */
function ManifestReview({
  bundle,
  state,
  onClose,
}: {
  bundle: BenchmarkExportMaterial | null;
  state: BenchmarkExportManifestState;
  onClose: () => void;
}) {
  return (
    <section
      aria-label="Publication manifest review"
      className="rounded-xl border border-[var(--zx-primary-border)] bg-[var(--zx-primary-soft)] p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[10px] font-semibold text-[color:var(--zx-text-title)]">
            Publication manifest review
          </h3>
          <p className="mt-1 text-[9px] text-[color:var(--zx-text-muted)]">
            Bundle identity:{" "}
            {bundle?.item.descriptor.artifactId ?? "bundle not published"}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-[var(--zx-border-light)] px-2 py-1 text-[9px]"
        >
          Close manifest
        </button>
      </div>
      {state.kind === "loading" ? (
        <ExportNotice state="loading" copy="Loading bounded manifest facts…" />
      ) : null}
      {state.kind === "failed" ? (
        <ExportNotice
          state="manifest-invalid"
          copy="The publication manifest could not be validated safely."
        />
      ) : null}
      {state.kind === "ready" ? (
        <ManifestSummary summary={state.summary} />
      ) : null}
    </section>
  );
}

/** Render bounded member and excluded-evidence summaries with no capabilities. */
function ManifestSummary({
  summary,
}: {
  summary: BenchmarkPublicationManifestSummary;
}) {
  return (
    <div className="mt-3 space-y-3 text-[9px]">
      <dl className="grid grid-cols-[8rem_minmax(0,1fr)] gap-2">
        <dt className="text-[color:var(--zx-text-muted)]">Manifest TaskRun</dt>
        <dd className="break-all">{summary.taskRunId}</dd>
        <dt className="text-[color:var(--zx-text-muted)]">Declared members</dt>
        <dd>{summary.memberCount}</dd>
        <dt className="text-[color:var(--zx-text-muted)]">Declared bytes</dt>
        <dd>{formatBytes(summary.declaredBytes)}</dd>
      </dl>
      <div className="max-h-52 overflow-auto rounded border border-[var(--zx-border-light)] bg-[var(--zx-card)]">
        <table aria-label="Publication manifest members" className="w-full text-left">
          <thead>
            <tr className="border-b border-[var(--zx-divider-ui)]">
              <th className="p-2">Reference</th>
              <th className="p-2">Kind / scope</th>
              <th className="p-2">Size / digest</th>
            </tr>
          </thead>
          <tbody>
            {summary.members.map((member) => (
              <tr
                key={member.reference}
                className="border-b border-[var(--zx-divider-ui)] last:border-0"
              >
                <td className="max-w-48 break-all p-2">{member.reference}</td>
                <td className="p-2">
                  {member.kind}
                  <code className="block break-all text-[8px] text-[color:var(--zx-text-muted)]">
                    {member.scope.taskRunId ?? member.scope.experimentId}
                  </code>
                </td>
                <td className="p-2">
                  {formatBytes(member.size)}
                  <code className="block">{shortDigest(member.sha256)}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[color:var(--zx-text-muted)]">
        These are bundle-member declarations, not standalone inventory
        capabilities. The browser does not open or scan the ZIP.
      </p>
      {summary.excludedEvidence.length > 0 ? (
        <ul aria-label="Excluded evidence policy" className="space-y-1">
          {summary.excludedEvidence.map((excluded, index) => (
            <li key={`${excluded.kind}-${index}`}>
              {excluded.kind}: {excluded.availability} — {excluded.reason}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Render one safe empty-state fact. */
function EmptyFact({ copy }: { copy: string }) {
  return (
    <p className="rounded-lg border border-dashed border-[var(--zx-border-light)] p-3 text-[9px] text-[color:var(--zx-text-muted)]">
      {copy}
    </p>
  );
}

/** Render a visible safe local status. */
function ExportNotice({ state, copy }: { state: string; copy: string }) {
  return (
    <p
      role="status"
      data-state={state}
      className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-[9px] text-amber-100"
    >
      {copy}
    </p>
  );
}

/** Format exact bytes for compact presentation only. */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

/** Abbreviate a canonical digest without using it for comparison. */
function shortDigest(digest: string | null): string {
  if (!digest) return "digest unavailable";
  return `${digest.slice(0, 15)}…${digest.slice(-8)}`;
}

/** Return one stable human label for a typed material. */
function materialLabel(material: BenchmarkExportMaterial): string {
  const labels: Record<BenchmarkExportMaterial["category"], string> = {
    "experiment-report": "Experiment report",
    "experiment-bundle": "Experiment bundle",
    "publication-manifest": "Publication manifest",
    "task-report": "TaskRun report",
    "task-trajectory": "TaskRun trajectory",
    "other-evidence": material.item.descriptor.kind,
  };
  return labels[material.category];
}
