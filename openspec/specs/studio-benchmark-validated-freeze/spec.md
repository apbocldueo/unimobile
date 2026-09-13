# studio-benchmark-validated-freeze Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-validated-freeze-5-5e1. Update Purpose after archive.
## Requirements
### Requirement: Freeze targets one exact current authoring revision
The system SHALL provide an explicit freeze command for a Benchmark draft and
MUST require the caller-observed current authoring revision identity. The
command MUST resolve the revision through the owning draft, verify that it is
still current before analysis and again in the commit transaction, and use
only its durable document and managed content. It MUST NOT serialize unsaved
browser state, accept a caller-supplied host path or content identity, or mutate
the draft, current pointer, source authoring revision, document fingerprint, or
the source revision's `unvalidated` status.

#### Scenario: Freeze an exact current revision
- **WHEN** the caller submits the owned current revision and it remains current through commit
- **THEN** the service analyzes that exact durable revision and may create an independently identified immutable Package revision without changing the authoring resource

#### Scenario: Current revision advances during freeze
- **WHEN** the draft current pointer no longer equals the submitted revision before analysis or at commit
- **THEN** the command returns a conflict with the safe current revision identity and commits no attestation or Package revision

#### Scenario: Revision belongs to another draft
- **WHEN** a valid authoring revision is addressed through a different draft
- **THEN** the command returns not found without disclosing the owning draft or reading its content

### Requirement: Freeze revalidates the complete declared Package
The freeze service SHALL privately materialize the exact authoring revision and
run the existing strict Package validation and dry-run compilation over every
declared split in deterministic manifest order. It MUST validate the manifest,
all split task files, every applicable default or selected Protocol, task and
ground-truth bindings, Package dependencies, output layout, budgets, schedule
capacity, and fairness facts. Eligibility MUST be computed by the server from
this complete pass; a transient Stage 5.5C browser result, a single selected
split, or a Stage 5.5D Contract Test result MUST NOT grant or substitute for
freeze eligibility.

#### Scenario: Every declared split is valid
- **WHEN** all declared splits and their Protocol bindings pass strict Package validation and bounded dry-run compilation
- **THEN** the freeze may proceed with stable Package, content, per-split Plan, and Protocol identities recorded from that pass

#### Scenario: An unselected split is invalid
- **WHEN** one declared split fails even though the split most recently inspected in Studio passes
- **THEN** freeze fails with a bounded diagnostic for the invalid split and creates no attestation or Package revision

#### Scenario: Contract Tests passed previously
- **WHEN** fake-fixture Contract Tests passed for the exact revision but complete Package validation now fails
- **THEN** freeze remains ineligible because Contract Test evidence is neither validation status nor publication eligibility

#### Scenario: Complete analysis exceeds a public bound
- **WHEN** split, member, task, schedule, diagnostic, or total analysis cardinality exceeds its configured limit
- **THEN** the service rejects before unbounded work and does not represent a partial analysis as complete

### Requirement: Freeze closes and verifies all definition and content members
Before committing a Package revision, the system SHALL derive a deterministic
closed member inventory from the parsed authoring document. The closure MUST
include the canonical manifest, every declared task split file, every declared
Protocol file, all assets, file-backed ground truth, and every other declared
Package resource, while inline JSON ground truth remains part of its canonical
definition member. Every managed binary member MUST be a bounded regular object
whose stored size and SHA-256 match its descriptor; missing, corrupt, hidden,
undeclared, absolute, traversing, symlink-derived, or caller-selected members
MUST NOT enter the frozen closure.

#### Scenario: Close a mixed definition and resource Package
- **WHEN** the current authoring revision contains multiple definition files, assets, file-backed ground truth, and inline ground truth
- **THEN** the frozen inventory contains each declared definition or binary member exactly once in stable logical-path order with media type, size, and SHA-256

#### Scenario: Managed content is missing or corrupt
- **WHEN** a declared descriptor cannot be read exactly or its bytes do not match its stored size or digest
- **THEN** freeze fails closed with a safe field-addressable diagnostic and exposes no Package revision

#### Scenario: Authoring storage contains unrelated bytes
- **WHEN** the server-owned content root contains unreferenced objects or the imported source once contained undeclared files
- **THEN** those bytes are excluded because closure is derived only from the exact revision's declared inventory

### Requirement: Successful validation produces an immutable attestation
Each successful freeze SHALL persist a strict versioned validation attestation
separate from the authoring revision and Package revision. The attestation MUST
identify the draft, exact authoring revision, document fingerprint, validation
contract version, Package identity, Package content identity, every declared
split and its Plan and Protocol identities, output-layout and budget facts,
fairness warnings, explicit unverified checks, safety facts, and creation time.
It MUST state that execution, real-device, model, Package-plugin, and publication
evidence are false. A failed or incomplete analysis MUST NOT create a successful
attestation.

#### Scenario: Record successful all-split evidence
- **WHEN** the complete declared Package passes the freeze validation boundary
- **THEN** one immutable attestation records complete split coverage, exact identities, bounded warnings and unverified facts, and `executionEvidence=false`

#### Scenario: A check remains intentionally unverified
- **WHEN** a runtime-dependent fact cannot be established without a device, model, secret, network, or Package plugin implementation
- **THEN** the attestation identifies that check as unverified without treating it as execution proof or silently upgrading it to passed

#### Scenario: Validation fails
- **WHEN** any eligibility check fails
- **THEN** the response contains only bounded safe diagnostics and no successful attestation is persisted

### Requirement: Package revisions are immutable closed semantic snapshots
Each successful freeze SHALL create a stable opaque `PackageRevision` identity
that references exactly one validation attestation and one exact authoring
revision. The Package revision MUST contain the Package identity, canonical
Package content identity, deterministic closed member inventory, per-member
immutable content identity, and creation metadata required to reconstruct the
same Package semantics after restart and from an installed wheel. Its definition
members MUST use deterministic canonical JSON bytes, and its binary members
MUST reference server-owned content-addressed bytes. Once committed, neither
the Package revision nor its attestation or member mapping may be modified.

#### Scenario: Reconstruct after restart
- **WHEN** Studio restarts after a successful freeze
- **THEN** an exact read reconstructs the same Package revision, attestation, identities, inventory ordering, member digests, and safety facts without consulting mutable draft state

#### Scenario: Source draft changes later
- **WHEN** the draft appends a new authoring revision after a Package revision was frozen
- **THEN** the earlier Package revision retains its original definition and content closure and does not follow the draft current pointer

#### Scenario: Reconstruct in a clean installed environment
- **WHEN** the installed service reads a frozen Package revision from a repository-independent working directory
- **THEN** reconstruction uses installed contracts and managed content only and exposes no source or managed absolute path

### Requirement: Freeze commits are durable, atomic, and idempotent
The Studio repository SHALL durably store successful attestations, immutable
Package revisions, frozen member mappings, and freeze-command results through
an additive SQLite migration and database-neutral ports. Every freeze request
MUST carry a stable client request identity and canonical fingerprint scoped to
the owning draft. Repeating the identity with the same fingerprint MUST return
the original result without reanalysis or duplicate records; reusing it with a
different fingerprint MUST conflict. Frozen content MUST be fully verified and
atomically promoted before one transaction records the attestation, Package
revision, members, idempotency result, and final current-revision check.

#### Scenario: Retry after response loss
- **WHEN** the same freeze request is retried after its first transaction committed
- **THEN** the service returns the original Package revision with `created=false` and creates no duplicate attestation or member mapping

#### Scenario: Reuse a request identity with another revision
- **WHEN** a caller reuses the scoped request identity with a different revision or payload fingerprint
- **THEN** the service returns an idempotency conflict and preserves the original result

#### Scenario: Content promotion fails
- **WHEN** canonical member encoding, streaming, hashing, or atomic content promotion fails
- **THEN** no database row exposes a partial attestation or Package revision and the draft remains unchanged

#### Scenario: Database commit fails after content promotion
- **WHEN** immutable content is promoted but the following database transaction fails
- **THEN** no queryable Package revision references a partial closure; unreachable content may remain for later retention work but conveys no authority

### Requirement: Freeze HTTP resources are strict, scoped, and bounded
The local Studio HTTP service SHALL expose a strict schema-1 JSON `POST` command
at `/studio/benchmark-authoring/drafts/{draftId}/package-revisions` and an exact
scoped `GET` resource at
`/studio/benchmark-authoring/drafts/{draftId}/package-revisions/{packageRevisionId}`.
The command request SHALL contain only its schema version, client request
identity, and exact authoring revision identity. Responses MUST be bounded,
strictly parsed, privately no-store, and limited to safe logical identities,
inventory metadata, diagnostics, warnings, unverified facts, and safety facts.
They MUST NOT expose binary bytes, absolute paths, storage keys, secrets, live
objects, or private capabilities. Existing Host, origin, content-type, body-size,
method, and error-envelope protections MUST remain in force.

#### Scenario: Freeze through HTTP
- **WHEN** a same-origin caller posts a valid command for the owned exact current revision
- **THEN** the service returns a strict no-store schema-1 result containing the immutable attestation and Package revision or bounded eligibility diagnostics

#### Scenario: Read an exact Package revision
- **WHEN** a caller requests an owned Package revision through its owning draft
- **THEN** the service returns the same bounded immutable metadata after restart without returning member bytes or storage locations

#### Scenario: Reject unknown command fields
- **WHEN** the request contains a split selector, browser validation result, Contract Test result, destination path, content identity, publication option, credential, device profile, or another unknown field
- **THEN** the service returns 400 before materialization and performs no freeze work

#### Scenario: Preserve HTTP error semantics
- **WHEN** the command encounters hidden ownership, stale current state, capacity excess, invalid Package content, or unavailable private storage
- **THEN** it returns the established bounded 404, 409, 413, validation error, or 503 class respectively and known unsupported methods return 405

### Requirement: Freeze remains side-effect free and truthfully bounded
Freeze validation and reconstruction MUST NOT import or instantiate Package
plugins, invoke task initializers or evaluators, connect to a device, call a
model, resolve secrets, access the network, execute an Agent or Benchmark,
create an Experiment, publish to Catalog, generate a distributable download,
or create runtime report, trajectory, Replay, or execution claims. Temporary
Package materialization MUST use a fresh private disposable directory, expose
no path publicly, and clean up on success, validation failure, cancellation,
and unexpected exceptions.

#### Scenario: Zero-runtime-side-effect freeze
- **WHEN** a valid revision is frozen with fail-fast canaries installed at device, model, network, secret, plugin-construction, initializer, evaluator, Agent, Benchmark, Experiment, publication, and runtime-output boundaries
- **THEN** all canaries remain untouched while only validation metadata and immutable frozen content are produced

#### Scenario: Materialization cleanup after failure
- **WHEN** validation or frozen-content preparation raises after private materialization begins
- **THEN** the disposable directory is removed and no host path appears in the response or logs

### Requirement: Validated freeze preserves adjacent contracts and defers publication
The capability MUST preserve existing BenchmarkTask JSON, Benchmark Package,
Plan and Protocol canonical identities, AgentConfig and AgentGraph independence,
authoring create/save/content commands, transient Validation/Dry-run and Contract
Test behavior, Catalog snapshots, Experiment execution, reporting, Replay,
History, and Export behavior. It MUST work from a clean installed wheel. This
change MUST NOT add Catalog mutation or visibility, downloadable Package export,
React publish controls, legacy JSON migration, worker expansion, multi-Task or
multi-Agent execution, PostgreSQL, external object storage, retention/delete,
arbitrary third-party sandbox claims, or real Android acceptance.

#### Scenario: Freeze does not publish
- **WHEN** a Package revision is successfully frozen
- **THEN** the current Catalog and every existing Catalog entry remain unchanged and the frozen Package is not discoverable as a published Benchmark

#### Scenario: Preserve legacy Benchmark and Agent paths
- **WHEN** existing BenchmarkTask JSON, AgentConfig YAML, AgentGraph, authoring, Catalog, Experiment, report, Replay, or export flows run after the migration
- **THEN** their public contracts and canonical identities remain unchanged by the freeze layer

#### Scenario: Hand off to later Stage 5.5E changes
- **WHEN** a caller needs Catalog publication, a distributable archive, or legacy Benchmark JSON conversion
- **THEN** those actions remain unavailable in E-1 and require the explicit E-2 or E-3 workflow rather than an implicit freeze side effect

