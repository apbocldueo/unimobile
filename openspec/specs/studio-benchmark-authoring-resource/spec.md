# studio-benchmark-authoring-resource Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-authoring-resource-5-5a. Update Purpose after archive.
## Requirements
### Requirement: Studio Benchmark authoring document is strict, safe, and versioned
The system SHALL define a versioned Studio Benchmark authoring document that
contains exactly one parsed manifest, a deterministic Package-relative split
and task-file inventory, a deterministic Protocol inventory, declared resource
metadata, and ground-truth bindings. The envelope MUST reject unknown fields,
duplicate logical paths or identities, absolute or upward-traversing paths,
non-JSON or non-finite values, resolved secrets, device handles, and live
objects. It MAY preserve a Package whose parsed content is not yet semantically
valid, but MUST label the authoring revision unvalidated and MUST NOT invent a
verified Package, Plan, Protocol, or runtime identity.

#### Scenario: Save a safe but semantically incomplete authoring document
- **WHEN** an author submits a structurally safe parsed document whose task or Protocol content does not yet satisfy formal Benchmark validation
- **THEN** the system may persist an unvalidated authoring revision without claiming that the Package is runnable or valid

#### Scenario: Reject unsafe authoring metadata
- **WHEN** a submitted document contains a host absolute path, upward traversal, resolved secret, non-finite value, device handle, or unsupported live value
- **THEN** the system rejects the command with a safe field-addressable error and does not persist or echo the unsafe value

#### Scenario: Reject unparsable source text
- **WHEN** a client attempts to persist task, manifest, or Protocol source that cannot be represented by the strict parsed authoring envelope
- **THEN** the system rejects the revision and leaves the current durable revision unchanged

### Requirement: Draft and authoring-revision identities remain distinct from Package publication
The system SHALL represent a Benchmark draft as stable mutable metadata pointing
to an immutable current authoring revision. Each authoring revision MUST have a
stable opaque identity, ordinal, parent revision identity, document fingerprint,
safe source provenance, and creation time, and MUST NOT be modified after
commit. Draft, Catalog entry, authoring revision, Core Package/content, and
future published Package revision identities MUST remain separate contracts.

#### Scenario: Append a second authoring revision
- **WHEN** an author saves a new document against the current revision of an existing draft
- **THEN** the system appends a new immutable child revision, atomically advances the draft current pointer, and preserves the earlier revision unchanged

#### Scenario: Unvalidated revision has no publication identity
- **WHEN** a draft revision has been stored but has not completed the later validation and publication workflows
- **THEN** its resource identifies only the draft and authoring revision and does not expose a published revision or verified runnable identity

### Requirement: Durable repository reconstructs drafts after restart
The system SHALL provide a database-neutral Benchmark authoring repository port
and a versioned SQLite adapter. The adapter MUST durably store drafts, immutable
revisions, command idempotency facts, current pointers, ordinals, provenance,
and bounded canonical document content using an additive monotonic migration.
List operations MUST be deterministic, newest-first, bounded, and cursor-based.
No delete or retention command SHALL be added by this change.

#### Scenario: Reopen after service restart
- **WHEN** Studio is restarted after a draft and multiple revisions have committed
- **THEN** list, draft detail, and exact revision reads reconstruct the same identities, current pointer, documents, provenance, and revision order from durable storage

#### Scenario: Existing Studio database migrates additively
- **WHEN** a schema-7 Studio database is opened by the implementation
- **THEN** the next migration adds Benchmark authoring storage without rewriting existing Agent, Run, Replay, Experiment, publication, artifact, or History facts

#### Scenario: Revision belongs to another draft
- **WHEN** a client requests a valid revision identity through a different draft identity
- **THEN** the repository returns not found without disclosing the owning draft

### Requirement: Template scaffold creates an isolated managed draft
The system SHALL create a Benchmark draft from the existing `minimal`,
`dynamic-task`, or `composite-evaluation` scaffold semantics. The service MUST
use a fresh server-owned staging location, MUST keep scaffold replacement mode
disabled, MUST ingest the result through the strict authoring document contract,
and MUST NOT accept a browser-supplied destination or overwrite existing
workspace files.

#### Scenario: Create a minimal template draft
- **WHEN** a client submits a valid idempotent create command for the minimal template and valid Package identity fields
- **THEN** the system creates one draft and initial immutable revision containing the expected manifest, test task file, default Protocol, and empty resource directories as logical inventory

#### Scenario: Reject unsupported template
- **WHEN** a client requests an unknown template name or invalid Package identity
- **THEN** the system rejects the command before creating a visible draft or modifying any workspace file

#### Scenario: Template creation has no runtime side effect
- **WHEN** any supported template is converted into an authoring draft
- **THEN** the system performs no plugin import or construction, initializer or evaluator invocation, device connection, model call, secret resolution, or runtime artifact creation

### Requirement: Catalog import copies only a verified declared closure
The system SHALL import only from an opaque entry resolved by the current
server-owned Studio Benchmark Catalog. Import MUST require a currently available
entry, MUST copy rather than reference or mutate the source, and MUST include
only the manifest, declared split task files, declared default Protocol, and
declared resources including resource-backed ground truth. It MUST NOT
recursively copy hidden, sibling, undeclared, or arbitrary host files. The
managed copy MUST be reparsed and checked against the selected Catalog identity
before the draft commits; source drift or a mixed snapshot MUST fail closed.

#### Scenario: Import an available Catalog Package
- **WHEN** a client creates a draft from an available opaque Catalog entry and the declared source closure remains coherent
- **THEN** the system commits one independent initial authoring revision with safe Catalog provenance and leaves every source Package file unchanged

#### Scenario: Reject browser host path import
- **WHEN** a create request includes a filesystem path, destination, force flag, or Catalog identity not present in the current server registry
- **THEN** the system rejects the request without scanning or reading the caller-selected location

#### Scenario: Reject Catalog drift during import
- **WHEN** the selected Catalog Package changes or produces an incoherent declared closure while the managed snapshot is being prepared
- **THEN** the system commits no draft and returns a safe conflict or validation error without exposing a host path

#### Scenario: Ignore undeclared Package files
- **WHEN** a valid Catalog Package directory also contains hidden, tooling, sibling, or other files absent from its declared authoring closure
- **THEN** those files do not enter the managed authoring revision

### Requirement: Managed authoring content cannot escape or be partially exposed
The system SHALL store resource bytes beneath a server-owned local authoring
root using immutable content identities. Every imported member MUST be a
bounded regular non-symlink file resolved beneath its trusted Package root and
MUST be streamed, size-checked, hashed, and atomically finalized before a
database revision references it. Public DTOs, errors, and logs MUST expose only
opaque content identity and declared safe metadata, never managed or source
absolute paths. Per-file, definition, member-count, and total-import limits MUST
be explicit and tested.

#### Scenario: Reject symlink or path escape
- **WHEN** a declared task, Protocol, resource, or ground-truth member is a symlink, absolute path, upward traversal, non-regular file, or resolves outside the trusted Package root
- **THEN** import fails without reading it into a visible draft or writing outside the authoring root

#### Scenario: Fail before exposing oversized content
- **WHEN** a definition, member count, individual resource, or total declared closure exceeds its configured bound
- **THEN** the system rejects the command and creates no queryable partial draft or revision

#### Scenario: Storage failure leaves no visible partial revision
- **WHEN** content streaming, atomic finalization, or the following SQLite transaction fails
- **THEN** no queryable revision references partial or missing bytes and the previous current revision remains authoritative

#### Scenario: HTTP reads resource metadata only
- **WHEN** a client reads a draft or revision containing managed resources
- **THEN** the response contains bounded declared metadata and opaque content identities but no binary content, local content path, or source path

### Requirement: Draft creation and revision save are durably idempotent
Every create and revision-save command SHALL require a stable client request
identity and SHALL persist a scoped canonical request fingerprint with its
result. Repeating a request identity with the same fingerprint MUST return the
original committed resource without creating another draft or revision and
without re-reading a mutable Catalog source. Reusing the same scoped request
identity with a different fingerprint MUST return a stable conflict.

#### Scenario: Retry template create after response loss
- **WHEN** the same template create request is submitted again after its first transaction committed
- **THEN** the system returns the original draft and initial revision with `created` false and does not append another record

#### Scenario: Retry Catalog import after source changes
- **WHEN** a committed Catalog-import request is retried with the same request identity and fingerprint after the current Catalog source has changed
- **THEN** the system returns the original durable imported revision without consulting or replacing it from the changed source

#### Scenario: Reuse request identity with different content
- **WHEN** a client reuses a create or per-draft save request identity for a different canonical payload
- **THEN** the system returns an idempotency conflict and preserves the original result

### Requirement: Revision save uses optimistic concurrency
Revision save SHALL require the client-observed base revision identity and MUST
append only when it exactly equals the draft current revision in the same
transaction. A stale, missing, or foreign base MUST NOT cause last-writer-wins
replacement. A stale conflict MUST return the safe current revision identity so
the future editor can reload or reconcile explicitly.

#### Scenario: Save against current base
- **WHEN** a valid idempotent revision command names the draft current revision as its base
- **THEN** the repository appends exactly one child revision and atomically advances the current pointer

#### Scenario: Two clients save from the same base
- **WHEN** one client commits a child revision and another client then submits a different save against the former shared base
- **THEN** the second save returns conflict with the new current revision identity and does not alter either committed revision

#### Scenario: Retry a successful save
- **WHEN** a client retries the exact successful revision command after the draft current pointer has advanced to its result
- **THEN** idempotency returns the original revision rather than treating the old base as a new stale command

### Requirement: Local HTTP API exposes the bounded authoring resource
Studio SHALL expose strict versioned endpoints to create and list Benchmark
drafts, read a draft with its current revision, read an exact owned authoring
revision, and append a revision. Create MUST use a discriminated template or
Catalog source and no path fallback. List and get MUST be bounded and use
existing Studio no-store, origin, host, request-size, safe-error, and JSON
serialization controls. Unknown fields, malformed opaque identities, invalid
cursors, and unsupported methods MUST fail predictably.

#### Scenario: Create, reopen, and save through HTTP
- **WHEN** a local allowed Studio client creates a template draft, reads it, and saves a new revision against the returned base
- **THEN** the endpoints return strict versioned resources whose identities and current pointer match durable repository state

#### Scenario: List drafts with bounded cursor
- **WHEN** more drafts exist than the requested valid page limit
- **THEN** the endpoint returns deterministic newest-first items and an opaque continuation cursor without embedding absolute paths or document bodies in list items

#### Scenario: Reject unknown create fields
- **WHEN** a create or save request contains an unknown field, malformed source union, malformed opaque identity, or oversized request body
- **THEN** the endpoint returns a bounded safe error and performs no repository or content mutation

### Requirement: Authoring resource remains definition-only and backward compatible
All scaffold, import, list, get, and save paths introduced by this change MUST
remain definition-only. They MUST NOT load or construct Benchmark plugins,
execute initializers, environments, evaluators, Agents, devices, models, or
network actions; resolve secrets; create Experiment/runtime/report facts; or
claim validation, Contract Test, publication, migration, export, or real-device
evidence. Existing CLI scaffold/validate/dry-run/contract-test commands,
BenchmarkTask JSON, Package/Protocol/Catalog APIs, Agent revision storage, and
AgentConfig/AgentGraph behavior MUST remain available and unchanged.

#### Scenario: Exercise the complete authoring resource without a device
- **WHEN** template create, Catalog import, list/get, conflict, retry, save, and restart journeys run in a clean installed environment with device and plugin execution boundaries instrumented
- **THEN** all resource operations complete with zero runtime boundary calls and no Experiment, report, trajectory, or Replay output

#### Scenario: Existing authoring and Catalog regressions remain stable
- **WHEN** the implementation is validated against existing Benchmark CLI authoring and Studio Catalog test suites
- **THEN** their public behavior, identities, non-destructive semantics, and no-side-effect guarantees remain unchanged

### Requirement: Confirmed legacy migration is a safe initial-revision source
The durable Benchmark authoring resource SHALL accept a legacy migration only through the confirmed migration authority defined by `studio-benchmark-legacy-migration`. A successful command MUST atomically create one new draft and ordinal-one immutable `unvalidated` revision using the recomputed candidate document. The revision provenance MUST identify the legacy-migration source kind and record only bounded safe source display metadata, source fingerprint, preview fingerprint, migration-contract identity, candidate document fingerprint, and task-count facts; it MUST NOT contain raw source text, a host path, resolved secret, private content capability, validation identity, frozen Package identity, publication identity, or runtime evidence.

#### Scenario: Persist a confirmed migration revision
- **WHEN** the migration service supplies a recomputed confirmable candidate and fresh exact command authority
- **THEN** the authoring repository commits one draft/current pointer/initial revision transaction whose document and safe provenance match the confirmed preview and whose status is `unvalidated`

#### Scenario: Reject direct migration-shaped create source
- **WHEN** a caller tries to bypass confirmation by submitting a migration source, raw source text, source path, preview fingerprint, or destination through the ordinary Template/Catalog draft-create endpoint
- **THEN** the ordinary create contract rejects the request and creates no draft

#### Scenario: Reconstruct migration provenance after restart
- **WHEN** Studio restarts after a confirmed migration commits
- **THEN** draft detail and exact revision reads reconstruct the same immutable document, current pointer, ordinal, and bounded migration provenance without rereading the original source

### Requirement: Migration confirm reuses durable create idempotency without partial authority
The authoring resource SHALL apply the existing durable create-command idempotency and atomic visibility rules to migration confirmation. The command fingerprint MUST bind the complete confirmed migration authority. Preview alone MUST create no durable command record. A repository transaction failure MUST expose neither a partial draft nor a partial revision, and retries MUST obey exact same-request or conflict semantics.

#### Scenario: Response is lost after migration commit
- **WHEN** a migration confirmation commits but its response is lost and the caller repeats the exact command
- **THEN** the repository returns the original draft and revision without allocating another identity or ordinal

#### Scenario: Repository transaction fails
- **WHEN** durable command, draft, revision, provenance, or current-pointer persistence fails during migration confirmation
- **THEN** no queryable partial migration resource becomes visible and the source plus all pre-existing authoring resources remain unchanged

#### Scenario: Existing schema opens without rewriting authority
- **WHEN** an existing schema-10 Studio database is opened by the migration-capable service
- **THEN** existing authoring, validation, freeze, release, Catalog, Experiment, artifact, report, Replay, and export facts remain byte-for-byte authoritative and migration preview remains transient

