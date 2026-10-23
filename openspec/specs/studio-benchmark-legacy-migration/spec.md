# studio-benchmark-legacy-migration Specification

## Purpose
Provide a safe, auditable bridge from the supported standalone BenchmarkTask V1 JSON format into Studio's durable Benchmark authoring workflow without silently changing task semantics or claiming validation, publication, or execution evidence.
## Requirements
### Requirement: Legacy migration accepts only bounded browser-supplied V1 source text
The system SHALL accept legacy migration input only as UTF-8 JSON source text inside a strict versioned request, never as a browser-supplied host path, destination, URL, Catalog identity, or server filesystem traversal. Source text MUST be at most 1 MiB, contain at most 100 task entries, use an array root, and satisfy the existing standalone BenchmarkTask V1 structural and semantic contract before it can be confirmed. Public source metadata MUST be limited to a bounded safe display name, submitted UTF-8 size, source fingerprint, task count, and unique-task count.

#### Scenario: Preview a bounded canonical V1 suite
- **WHEN** a caller submits a UTF-8 JSON array containing no more than 100 valid standalone BenchmarkTask V1 entries and valid explicit target metadata
- **THEN** the system accepts the source for analysis without reading a host path or modifying the submitted source

#### Scenario: Reject an unsupported source envelope
- **WHEN** a migration request supplies a host path, URL, destination, non-object request envelope, non-array source root, invalid UTF-8/JSON text, source text over 1 MiB, or more than 100 entries
- **THEN** the system returns a bounded safe error and produces no preview authority or durable authoring resource

#### Scenario: Reject pre-V1 fields rather than converting them
- **WHEN** a task uses rejected legacy fields such as `task`, `params_config`, `setup_config`, `eval_type`, or a plugin-level `type` field that the current V1 contract forbids
- **THEN** preview reports field-addressable V1 diagnostics, marks the result non-confirmable, and does not translate the rejected fields into accepted V1 fields

### Requirement: Preview is deterministic, bounded, and side-effect free
The system SHALL provide a migration preview that parses and safely analyzes the exact submitted source, validates duplicate task identities and the strict authoring safety envelope, constructs a deterministic candidate authoring document, and returns no more than 100 sanitized diagnostics and a bounded structured diff. Preview MUST NOT write a draft, revision, command record, content object, source copy, workspace file, Catalog snapshot, Package revision, export, Experiment, result, report, trajectory, or Replay resource, and MUST NOT resolve or execute plugins, devices, Agents, models, network operations, or secrets.

#### Scenario: Preview a valid source without persistence
- **WHEN** a confirmable migration preview completes
- **THEN** it returns deterministic source, target, diff, diagnostic, and evidence facts while all authoring repositories, content stores, source files, workspace trees, runtime boundaries, and publication authorities remain unchanged

#### Scenario: Duplicate task identity blocks confirmation
- **WHEN** two or more source entries use the same task ID, including byte-equivalent duplicate entries
- **THEN** preview identifies the later duplicate locations, reports the original entry count and unique-ID count, marks the result non-confirmable, and neither removes nor renames any task

#### Scenario: Unsafe authoring value blocks confirmation
- **WHEN** accepted JSON contains a resolved secret, host absolute path, non-finite value, unsupported value, or another value forbidden by the strict authoring safety envelope
- **THEN** preview returns a sanitized field-addressable diagnostic without echoing the unsafe value and marks the result non-confirmable

### Requirement: Target projection preserves accepted task semantics and exposes every addition
For a confirmable source, the system SHALL preserve the parsed JSON value of every accepted task in source order in exactly one deterministic Package-relative task file and SHALL NOT rename, delete, deduplicate, merge, reorder, or rewrite any task field. The candidate manifest MUST use only explicit target identity, title, platform, and split inputs plus mechanically derivable dependency declarations. Plugin declarations MAY be projected only from explicit initializer, environment, cleanup, and evaluator references. App declarations MAY be projected only when the task declarations determine the login requirement without inventing an unknown value; unresolved App declarations MUST remain explicit post-migration work. The candidate MUST contain no Protocol file or default Protocol, no ground-truth binding, and no managed resource bytes or fabricated resource declaration.

#### Scenario: Preserve a valid task array
- **WHEN** preview receives a confirmable array of distinct V1 tasks
- **THEN** the structured diff reports all task entries as retained, reports zero renamed, removed, deduplicated, or rewritten task entries, and identifies only the added Package wrapper and mechanically derived declarations

#### Scenario: Preserve representation truthfully
- **WHEN** source JSON whitespace or object-key order differs from the canonical authoring serialization
- **THEN** preview describes representation normalization separately and does not report semantic task-field changes or claim byte-for-byte Package preservation

#### Scenario: Do not invent missing Package semantics
- **WHEN** the standalone tasks provide no Protocol, ground-truth binding, resource metadata/bytes, or unambiguous App login declaration
- **THEN** the candidate omits the default Protocol and Protocol files, keeps ground truth and resources empty, and identifies unresolved author work rather than generating those facts

#### Scenario: Preserve unresolved relative resource references for author repair
- **WHEN** an otherwise safe V1 task contains a host-relative resource field that later Package validation will reject
- **THEN** migration preserves the task field unchanged, reports it as post-migration work, and does not copy bytes or rewrite it to an `asset://` or `groundtruth://` reference

### Requirement: Preview identities bind source, transformation contract, and target intent
Every preview SHALL expose a SHA-256 source fingerprint derived from the exact submitted UTF-8 source text, a stable migration-contract identity, the deterministic candidate document fingerprint when available, and a preview fingerprint binding the source fingerprint, complete explicit target intent, migration-contract identity, and candidate document fingerprint. Results MUST expose `confirmable` independently from validation, publication, and execution evidence and MUST state that those evidence facts are false.

#### Scenario: Equivalent repeated preview is stable
- **WHEN** the same source text, target intent, and migration contract are previewed repeatedly
- **THEN** source, candidate-document, and preview fingerprints plus the ordered structured diff are identical

#### Scenario: Source or target intent changes
- **WHEN** any submitted source character, Package identity field, title, platform, split, task-file target, or migration-contract identity changes
- **THEN** the resulting preview fingerprint changes and an earlier preview cannot authorize confirmation

### Requirement: Confirm replays the complete analysis and creates one unvalidated draft
The system SHALL require explicit confirmation with the complete source text, complete target intent, a stable client request identity, and the caller-observed preview fingerprint. Confirm MUST rerun the same bounds, safety, V1, duplicate, projection, diff, and fingerprint computation before any durable write. It MUST reject a non-confirmable result or fingerprint mismatch, and on success atomically create exactly one new draft and initial immutable revision whose document equals the recomputed candidate and whose status remains `unvalidated`.

#### Scenario: Confirm an unchanged preview
- **WHEN** a caller confirms the same confirmable source and target intent with the matching preview fingerprint and a fresh request identity
- **THEN** the system creates one new draft and ordinal-one immutable revision, returns created true, and preserves false validation, Contract Test, freeze, publication, export, execution, and device evidence

#### Scenario: Reject stale preview confirmation
- **WHEN** confirm recomputation produces a different source fingerprint, target intent, candidate document fingerprint, migration-contract identity, confirmability result, or preview fingerprint
- **THEN** the system rejects the command as stale and creates no draft, revision, command result, or content object

#### Scenario: Retry a committed confirmation
- **WHEN** the exact confirmed command is retried with the same client request identity after the original transaction committed
- **THEN** the system returns the original draft and initial revision with created false and does not re-create, re-number, or replace them

#### Scenario: Reuse request identity with different migration input
- **WHEN** a client request identity previously committed or reserved for one migration is reused with different source, target intent, preview fingerprint, or migration-contract identity
- **THEN** the system returns an idempotency conflict and preserves the original authority

### Requirement: Migration exposes strict local HTTP preview and confirm resources
Studio SHALL expose strict versioned local HTTP resources at `/studio/benchmark-authoring/legacy-migrations/preview` and `/studio/benchmark-authoring/legacy-migrations/confirm`. Both MUST use the existing Host, Origin, CORS, no-store, request-body, safe-error, and JSON serialization controls; reject unknown request and response fields through their strict contracts; and never return raw source text, host paths, resolved secrets, private content capabilities, or live objects.

#### Scenario: Preview and confirm through HTTP
- **WHEN** an allowed local Studio client submits a valid preview and then confirms the exact returned authority
- **THEN** the endpoints return strict schema-versioned resources whose fingerprints and created draft/revision identities agree with durable authoring state

#### Scenario: Unsupported method or malformed contract
- **WHEN** a caller uses an unsupported method, unknown field, malformed identity, invalid target segment, oversized body, or unsupported schema version
- **THEN** the endpoint fails predictably with a bounded safe error and performs no migration write

### Requirement: Existing compatibility and evidence boundaries remain unchanged
Migration SHALL preserve existing standalone BenchmarkTask JSON loading and compilation, Benchmark Package/Catalog/Protocol identities, Template and Catalog draft creation, definition/resource editing, validation/dry-run, Contract Tests, freeze, publication/export, Experiment execution/reporting, Replay, AgentConfig, and AgentGraph behavior. It MUST NOT mutate original JSON sources, workspace `data/`, `benchmarks/`, examples, source Catalog trees, managed published Packages, or existing drafts. A migration success MUST NOT be described as Package validation, Contract Test success, freeze/publication eligibility, export, Agent/Benchmark execution, Android acceptance, or automatic diagnosis.

#### Scenario: Definition-only migration under fail-fast canaries
- **WHEN** preview and confirm run with device, plugin, Agent, model, network, secret, Experiment, publication, export, report, trajectory, and Replay boundaries instrumented to fail on access
- **THEN** the migration completes with every canary untouched and returns explicit false evidence facts

#### Scenario: Original source remains byte-identical
- **WHEN** preview or confirm operates on source text obtained from an existing file
- **THEN** the service neither receives a host path nor writes the file, and an independent digest of the original file remains unchanged

#### Scenario: Existing regression paths remain stable
- **WHEN** legacy JSON compilation and all existing Studio Benchmark authoring and release regression suites run after the change
- **THEN** their public contracts, identities, side-effect boundaries, and previously verified behavior remain unchanged

