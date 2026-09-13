import { classifyEvidenceOrigin } from "../model/evidenceOrigin.presentation";
import type { ExecutionEvidenceOrigin } from "../model/evidenceOrigin.schema";

type EvidenceOriginFactsProps = {
  origin: ExecutionEvidenceOrigin;
  title?: string;
};

/** Render authoritative provenance axes without collapsing source semantics. */
export function EvidenceOriginFacts({
  origin,
  title = "Execution evidence origin",
}: EvidenceOriginFactsProps) {
  const presentation = classifyEvidenceOrigin(origin);
  return (
    <section
      aria-label={title}
      data-provenance={presentation.kind}
      className="rounded-lg border border-[var(--zx-border-light)] bg-[var(--zx-canvas)] p-3"
    >
      <p className="text-[9px] font-semibold uppercase tracking-[0.1em] text-[color:var(--zx-text-muted)]">
        {title}
      </p>
      <strong className="mt-1 block text-[10px] text-[color:var(--zx-text-title)]">
        {presentation.label}
      </strong>
      <p className="mt-1 text-[9px] leading-relaxed text-[color:var(--zx-text-muted)]">
        {presentation.description}
      </p>
      <dl className="mt-2 grid grid-cols-[7rem_minmax(0,1fr)] gap-x-2 gap-y-1 text-[9px]">
        <dt className="text-[color:var(--zx-text-muted)]">Acquisition</dt>
        <dd className="break-all text-[color:var(--zx-text-title)]">
          {origin.acquisition}
        </dd>
        <dt className="text-[color:var(--zx-text-muted)]">Environment</dt>
        <dd className="break-all text-[color:var(--zx-text-title)]">
          {origin.environment}
        </dd>
        <dt className="text-[color:var(--zx-text-muted)]">Fresh device evidence</dt>
        <dd className="text-[color:var(--zx-text-title)]">
          {String(origin.realDeviceEvidence)}
        </dd>
        <dt className="text-[color:var(--zx-text-muted)]">Device profile</dt>
        <dd className="break-all text-[color:var(--zx-text-title)]">
          {origin.deviceProfileId ?? "not declared"}
        </dd>
      </dl>
      {origin.deviceChecks.length ? (
        <ul className="mt-2 space-y-1 text-[9px] text-[color:var(--zx-text-muted)]">
          {origin.deviceChecks.map((check) => (
            <li key={check.name}>
              {check.name}: {check.passed ? "passed" : "failed"} · {check.observed}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
