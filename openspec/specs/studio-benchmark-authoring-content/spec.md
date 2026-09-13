# studio-benchmark-authoring-content Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-authoring-content-5-5b2. Update Purpose after archive.
## Requirements
### Requirement: Managed content commands are scoped to one draft and base revision
The system SHALL expose strict versioned upload, replace, and logical-remove
commands only through an owning Benchmark draft, a client-observed base
revision, and a stable logical resource identity. A command MUST reject missing,
malformed, foreign, or stale ownership facts without accepting
`contentIdentity`, a host path, a source Package path, or an arbitrary server
destination as authority.

#### Scenario: Accept an owned current command
- **WHEN** a valid content command names an existing draft, its exact current base revision, and a valid logical resource identity
- **THEN** the service evaluates the operation against that base document and may append one immutable child revision

#### Scenario: Reject a foreign revision
- **WHEN** a valid revision identity belongs to another draft
- **THEN** the command returns not found without disclosing the owning draft and without reading or mutating managed bytes

#### Scenario: Content identity is not write authority
- **WHEN** a client submits an opaque content identity instead of an owned resource command
- **THEN** the service rejects the request and does not bind existing bytes into the draft

### Requirement: Upload creates one authoritative resource declaration
Upload SHALL accept a bounded raw byte stream plus strict resource kind,
Package-relative path, declared media type, client request identity, and base
revision metadata. The service MUST derive size, SHA-256, and immutable content
identity from the actual bytes; append a resource only when both its logical ID
and path are new; and return the complete newly committed `unvalidated`
revision.

#### Scenario: Upload a new asset
- **WHEN** an author uploads bounded bytes for a new `asset` ID and normalized `assets/` path against the current revision
- **THEN** the service atomically stores the bytes, appends matching authoritative resource metadata to a new revision, and advances the draft current pointer

#### Scenario: Upload file-backed ground truth
- **WHEN** an author uploads bounded bytes for a new `ground_truth` ID and normalized `ground_truth/` path
- **THEN** the new revision contains a file-backed ground-truth resource without inventing or changing any task-to-ground-truth binding

#### Scenario: Reject duplicate identity or path
- **WHEN** upload reuses an existing logical resource ID or Package path
- **THEN** the command fails before appending a revision and instructs the caller to use the explicit replace operation when appropriate

### Requirement: Replace preserves logical identity and immutable history
Replace SHALL target one resource present in the exact base revision. The
operation MUST preserve that resource's logical ID, kind, and Package-relative
path; MUST derive new content facts from the submitted bytes; MAY replace its
declared media type; and MUST append a new revision rather than changing any
existing revision or content object.

#### Scenario: Replace current resource bytes
- **WHEN** an author replaces an existing resource against the current base with a bounded new byte stream
- **THEN** the new revision references the new digest, size, media type, and content identity while the resource ID, kind, and path remain stable

#### Scenario: Read the resource before and after replacement
- **WHEN** the old and new exact revisions are read after replacement
- **THEN** the old revision resolves the original bytes and the new revision resolves the replacement bytes

#### Scenario: Replace an absent resource
- **WHEN** the named resource is absent from the base revision
- **THEN** the service returns not found and does not create an upload implicitly

### Requirement: Remove is logical and never destroys historical bytes
Remove SHALL append a new revision whose authoring and manifest resource
inventories no longer contain the named logical resource. It MUST NOT delete or
rewrite the immutable base revision, MUST NOT delete bytes still reachable from
any earlier revision, and MUST NOT silently rewrite task fields, inline ground
truth, or file-backed ground-truth bindings.

#### Scenario: Remove a current resource
- **WHEN** an author removes an existing resource against the current base revision
- **THEN** the service appends one child revision without that resource and leaves the earlier revision and its exact content capability intact

#### Scenario: Remove a referenced ground-truth resource
- **WHEN** a logical remove leaves an existing definition reference unresolved
- **THEN** the service preserves that definition data, labels the revision `unvalidated`, and defers the semantic diagnostic to the later validation workflow

#### Scenario: Remove an absent resource
- **WHEN** the named logical resource is absent from the base revision
- **THEN** the command returns not found without appending a no-op revision

### Requirement: Manifest and managed inventory remain structurally coherent
Every content command SHALL update the strict authoring `resources` inventory
and the parsed manifest `resources` declaration as one projected document. The
projection MUST preserve untouched safe manifest extension fields, preserve
untouched resource extension fields, derive authoritative known metadata from
managed bytes, reject ambiguous or inconsistent duplicate declarations, and
restore deterministic inventory ordering before persistence.

#### Scenario: Preserve an extended manifest resource
- **WHEN** replacement updates a resource declaration that contains an unknown safe extension field
- **THEN** the new revision changes only authoritative content metadata and retains the extension field unchanged

#### Scenario: Add resources in deterministic order
- **WHEN** upload adds a path that sorts before existing resource paths
- **THEN** both persisted inventories use the required deterministic path order without changing unrelated members

#### Scenario: Reject an incoherent base inventory
- **WHEN** the selected base revision contains ambiguous or contradictory managed and manifest resource declarations
- **THEN** the content command fails closed instead of guessing which declaration to mutate

### Requirement: Content commands are idempotent and optimistic
Every mutation SHALL require a stable client request identity and the
client-observed base revision. Its canonical fingerprint MUST bind operation,
draft, base revision, logical resource metadata, actual content digest, and
actual size where bytes are present. An exact retry MUST return the original
committed response; unequal reuse MUST return idempotency conflict; and a stale
new command MUST preserve the authoritative current revision.

#### Scenario: Retry after upload response loss
- **WHEN** an upload commits but its HTTP response is lost and the client retries the same identity, metadata, and bytes
- **THEN** the service returns the original revision with `created` false and does not append another revision

#### Scenario: Reuse identity with different bytes
- **WHEN** a client retries an upload or replacement request identity with bytes that produce a different digest
- **THEN** the service returns idempotency conflict and preserves the original command result

#### Scenario: Race two resource commands
- **WHEN** two different content commands begin from the same current base and one commits first
- **THEN** the second returns revision conflict with the safe current revision identity and does not advance the pointer

### Requirement: Uploaded bytes are bounded, checksummed, and failure-safe
The system SHALL stream content through the private managed authoring store
without buffering the complete resource in JSON or memory. It MUST enforce the
configured per-resource request limit, reject incomplete or overlong bodies,
hash the received bytes, flush and atomically promote a regular immutable
object before any revision references it, deduplicate identical content, and
clean temporary staging files on all normal failure paths. A storage or
following repository failure MUST leave the previous current revision
authoritative and MUST NOT expose a revision that references partial or missing
bytes.

#### Scenario: Reject an oversized upload
- **WHEN** declared or streamed content exceeds the configured authoring resource limit
- **THEN** the service returns a bounded capacity error, removes temporary bytes, and appends no revision

#### Scenario: Fail atomic promotion
- **WHEN** flushing, hashing, or atomic content promotion fails
- **THEN** the command returns a safe storage error with no queryable revision and no visible partial object

#### Scenario: Fail revision commit after content promotion
- **WHEN** immutable bytes are promoted but the optimistic SQLite revision transaction does not commit
- **THEN** no scoped content route can reach those bytes, the former current revision remains authoritative, and later retention or garbage collection remains a separate concern

### Requirement: Exact content reads require draft, revision, and resource ownership
The system SHALL provide `GET` and `HEAD` content capabilities addressed by
owning draft identity, exact immutable revision identity, and logical resource
identity. Resolution MUST first load the owned revision and resource metadata,
then resolve the private content identity internally and verify regular-file,
size, and digest integrity before returning headers or bytes. No route SHALL
resolve authoring content from `contentIdentity` alone.

#### Scenario: Read exact owned content
- **WHEN** a client requests a resource through its owning draft and exact revision
- **THEN** `GET` returns the integrity-verified bytes and `HEAD` returns the same safe metadata without a body

#### Scenario: Probe another draft or revision
- **WHEN** a client combines a resource ID with a foreign draft or revision
- **THEN** the service returns not found without revealing whether the resource or content object exists elsewhere

#### Scenario: Detect missing or corrupt managed bytes
- **WHEN** the owned revision exists but the immutable object is absent, non-regular, has the wrong size, or fails its digest
- **THEN** the service returns a bounded unavailable or integrity error and streams no body

### Requirement: Authoring content HTTP remains local, strict, and non-executable
The HTTP layer SHALL expose explicit upload, replace, remove, and exact
`GET`/`HEAD` routes under the existing local Studio origin and host policy.
Binary writes MUST use a strict bounded raw-body transport rather than JSON
Base64; command metadata and query fields MUST be exact and versioned; binary
responses MUST use declared length and media type, private no-store caching,
`nosniff`, and safe attachment disposition. Unsupported methods, chunked or
missing length, unknown metadata, unsafe media type, malformed paths, and
cross-origin requests MUST fail predictably.

#### Scenario: Upload a body larger than the JSON limit
- **WHEN** an allowed local client uploads a resource within the resource limit but larger than the general JSON request limit
- **THEN** the HTTP layer streams it through the binary command path without decoding it as JSON or loading the complete body into memory

#### Scenario: Download active content safely
- **WHEN** exact owned content declares HTML, SVG, XML, or another potentially active media type
- **THEN** the response is attachment-oriented, private, and `nosniff` rather than being served as trusted Studio application content

#### Scenario: Direct content-identity route remains absent
- **WHEN** a client requests `/studio/benchmark-authoring/content/{contentIdentity}`
- **THEN** Studio returns not found even if the underlying immutable object exists

### Requirement: Managed content stays definition-only and backward compatible
Upload, replace, remove, and exact read MUST preserve `status: unvalidated` and
MUST NOT invoke Benchmark validation, dry-run, initializer, environment,
evaluator, Agent, device, plugin construction, model, network, secret,
Experiment, report, trajectory, Replay, publication, migration, or export
boundaries. Existing definition save, Catalog import, CLI authoring,
BenchmarkTask JSON, AgentConfig, AgentGraph, and Studio Benchmark routes MUST
retain their established behavior.

#### Scenario: Complete a no-device content journey
- **WHEN** tests upload, read, replace, read an older revision, logically remove, retry, conflict, and restart the service
- **THEN** all operations preserve exact revision history with zero runtime boundary calls and no validation, execution, or publication facts

#### Scenario: Existing authoring regressions remain stable
- **WHEN** Stage 5.5A and 5.5B-1 resource, HTTP, and frontend regression suites run after the backend content capability is added
- **THEN** their strict identities, optimistic save behavior, metadata parsing, definition editor behavior, and negative capability boundaries remain compatible

