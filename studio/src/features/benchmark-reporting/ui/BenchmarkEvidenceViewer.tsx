import type {
  BenchmarkArtifactInventoryItem,
  BenchmarkEvidenceSelection,
} from "@/entities/benchmark-report";
import {
  EvidenceOriginFacts,
  type ExecutionEvidenceOrigin,
} from "@/entities/evidence-origin";
import type { BenchmarkEvidenceViewerState } from "../model/useBenchmarkEvidenceViewer";

type BenchmarkEvidenceViewerProps = {
  selection: BenchmarkEvidenceSelection;
  state: BenchmarkEvidenceViewerState;
  evidenceOrigin?: ExecutionEvidenceOrigin | null;
  onClose: () => void;
  onRetry: () => void;
};

/** Render one isolated evidence inspection surface with escaped content only. */
export function BenchmarkEvidenceViewer({
  selection,
  state,
  evidenceOrigin = null,
  onClose,
  onRetry,
}: BenchmarkEvidenceViewerProps) {
  const item = stateItem(state);
  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-label="Benchmark evidence viewer"
      className="absolute inset-y-3 right-3 z-20 flex w-[min(38rem,calc(100%-1.5rem))] flex-col overflow-hidden rounded-xl border border-[var(--zx-border-light)] bg-[var(--zx-card)] shadow-2xl"
    >
      <header className="flex items-start justify-between gap-4 border-b border-[var(--zx-divider-ui)] px-4 py-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[color:var(--zx-primary)]">
            Evidence Viewer
          </p>
          <h2 className="mt-1 truncate text-[12px] font-semibold text-[color:var(--zx-text-title)]">
            {selection.evidence.kind}
          </h2>
          <code className="mt-1 block truncate text-[9px] text-[color:var(--zx-text-muted)]">
            {selection.leafPath} · evidence {selection.evidenceIndex + 1}
          </code>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-[var(--zx-border-light)] px-2 py-1 text-[10px] text-[color:var(--zx-text-title)]"
        >
          Close
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {evidenceOrigin ? (
          <div className="mb-4">
            <EvidenceOriginFacts
              origin={evidenceOrigin}
              title="Selected TaskRun context"
            />
          </div>
        ) : (
          <p className="mb-4 text-[9px] text-[color:var(--zx-text-muted)]">
            Execution provenance is unavailable; artifact descriptor provenance
            cannot replace it.
          </p>
        )}
        <EvidenceDescriptorFacts selection={selection} item={item} />
        <EvidenceBody state={state} onRetry={onRetry} />
      </div>
    </aside>
  );
}

/** Render causal and authoritative descriptor facts without storage details. */
function EvidenceDescriptorFacts({
  selection,
  item,
}: {
  selection: BenchmarkEvidenceSelection;
  item: BenchmarkArtifactInventoryItem | null;
}) {
  return (
    <dl className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-2 rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] p-3 text-[9px]">
      <dt className="text-[color:var(--zx-text-muted)]">Causal reference</dt>
      <dd className="break-all text-[color:var(--zx-text-title)]">
        {selection.evidence.artifactRef || "No artifact reference"}
      </dd>
      {item ? (
        <>
          <dt className="text-[color:var(--zx-text-muted)]">Artifact</dt>
          <dd className="break-all text-[color:var(--zx-text-title)]">
            {item.descriptor.artifactId} · {item.descriptor.kind}
          </dd>
          <dt className="text-[color:var(--zx-text-muted)]">Availability</dt>
          <dd>
            <AvailabilityBadge availability={item.descriptor.availability} />
          </dd>
          <dt className="text-[color:var(--zx-text-muted)]">Media / size</dt>
          <dd className="text-[color:var(--zx-text-title)]">
            {item.descriptor.contentType || "unavailable"} ·{" "}
            {item.descriptor.size} bytes
          </dd>
          <dt className="text-[color:var(--zx-text-muted)]">Integrity</dt>
          <dd className="break-all text-[color:var(--zx-text-title)]">
            {item.descriptor.sha256 ?? "unavailable"}
          </dd>
          <dt className="text-[color:var(--zx-text-muted)]">Provenance</dt>
          <dd className="text-[color:var(--zx-text-title)]">
            {item.descriptor.provenance || "unavailable"}
          </dd>
        </>
      ) : null}
    </dl>
  );
}

/** Preserve redacted/truncated publication semantics as visible badges. */
function AvailabilityBadge({ availability }: { availability: string }) {
  return (
    <span
      data-availability={availability}
      className="rounded-full border border-[var(--zx-border-light)] px-2 py-0.5 text-[color:var(--zx-text-title)]"
    >
      {availability}
    </span>
  );
}

/** Render one preview or safe state-specific explanation. */
function EvidenceBody({
  state,
  onRetry,
}: {
  state: BenchmarkEvidenceViewerState;
  onRetry: () => void;
}) {
  if (state.kind === "ready-text") {
    return (
      <pre
        data-language={state.language}
        className="mt-4 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-[var(--zx-border-light)] bg-slate-950 p-4 text-[10px] leading-relaxed text-slate-100"
      >
        {state.text}
      </pre>
    );
  }
  if (state.kind === "ready-image") {
    return (
      <figure className="mt-4">
        <img
          src={state.objectUrl}
          alt={`Bounded Benchmark evidence preview, ${state.width} by ${state.height} pixels`}
          className="max-h-[60vh] max-w-full rounded border border-[var(--zx-border-light)] object-contain"
        />
        <figcaption className="mt-2 text-[9px] text-[color:var(--zx-text-muted)]">
          PNG dimensions {state.width} × {state.height}; integrity was verified
          by the managed backend resolver before streaming.
        </figcaption>
      </figure>
    );
  }
  if (state.kind === "download-only") {
    return (
      <section className="mt-4 rounded-lg border border-[var(--zx-border-light)] p-4 text-[10px]">
        <p className="text-[color:var(--zx-text-muted)]">
          This allowlisted media type is not previewed or decompressed. The
          action below only hands the authoritative request to the browser; it
          does not claim download or verification completion.
        </p>
        <a
          href={state.url}
          download
          className="mt-3 inline-block text-[color:var(--zx-primary)] underline"
        >
          Hand off evidence download
        </a>
      </section>
    );
  }

  const copy = evidenceStateCopy(state);
  return (
    <section
      role="status"
      data-state={state.kind}
      className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-[10px] text-amber-100"
    >
      <p>{copy}</p>
      {"retryable" in state && state.retryable ? (
        <button type="button" onClick={onRetry} className="mt-3 underline">
          Retry evidence
        </button>
      ) : null}
      {"hiddenCount" in state && state.hiddenCount > 0 ? (
        <p className="mt-2 text-[9px] text-amber-200">
          The inventory also contains {state.hiddenCount} hidden artifact
          descriptor{state.hiddenCount === 1 ? "" : "s"}; none is attributed
          to this leaf.
        </p>
      ) : null}
    </section>
  );
}

/** Return fixed copy for every non-ready state without raw exception text. */
function evidenceStateCopy(state: BenchmarkEvidenceViewerState): string {
  const copy: Record<BenchmarkEvidenceViewerState["kind"], string> = {
    idle: "No evidence is selected.",
    resolving: "Resolving the selected causal reference…",
    loading: "Loading bounded evidence bytes…",
    "no-reference": "This evidence descriptor has no artifact reference.",
    "reference-unavailable":
      "No unique visible artifact is authorized for this causal reference.",
    "ambiguous-reference":
      "Multiple visible artifacts match this causal reference; preview is blocked.",
    pending: "The authoritative artifact is still pending.",
    "not-produced": "The authoritative artifact was not produced.",
    excluded: "The artifact was excluded by publication policy.",
    missing: "The authoritative artifact is missing.",
    corrupt: "The authoritative artifact failed its integrity check.",
    failed: "Artifact publication failed.",
    oversized: "The artifact exceeds the browser preview byte policy.",
    "size-mismatch":
      "The declared or streamed byte count conflicts with the descriptor.",
    "mime-mismatch":
      "The response media type conflicts with the descriptor.",
    "invalid-content":
      "The content does not satisfy its strict preview format.",
    "request-failed": "The artifact request could not be completed safely.",
    "ready-text": "",
    "ready-image": "",
    "download-only": "",
  };
  return copy[state.kind];
}

/** Extract descriptor facts only from states that own an inventory item. */
function stateItem(
  state: BenchmarkEvidenceViewerState,
): BenchmarkArtifactInventoryItem | null {
  return "item" in state ? state.item : null;
}
