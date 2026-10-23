# studio-benchmark-package-publication-export Specification

## Purpose
Define the explicit release boundary that publishes an immutable validated
Benchmark Package revision to Studio Catalog and exports the same verified
closed member set as a deterministic downloadable package.
## Requirements
### Requirement: Release consumes only an owned immutable Package revision
The system SHALL expose release operations only through an E-1 Package revision
addressed by its owning Benchmark draft. It MUST load the immutable validation
attestation and complete frozen member inventory, require that all records are
internally consistent, and reject mutable authoring documents, unsaved browser
state, transient Validation/Dry-run results, Contract Test results, Catalog
source paths, caller-supplied content identities, and caller-supplied member
lists as release authority. Publication and export MUST be independent explicit
commands over the same Package revision and MUST NOT implicitly freeze a draft
or invoke each other.

#### Scenario: Select an owned frozen revision
- **WHEN** a caller addresses a complete Package revision through its owning draft
- **THEN** release queries return its immutable Package identity, closure identity, attestation facts, inventory summary, and available publication or export facts without consulting the mutable draft document

#### Scenario: Address a revision through another draft
- **WHEN** a valid Package revision is addressed through a different draft
- **THEN** the service returns not found without disclosing its owner or reading its members

#### Scenario: Submit mutable or caller-invented authority
- **WHEN** a release command contains an authoring document, browser validation result, Contract Test result, source path, destination path, content identity, or member override
- **THEN** strict request parsing rejects it before storage, Catalog, or archive work begins

#### Scenario: Publish without exporting
- **WHEN** an eligible Package revision is explicitly published and no export command is submitted
- **THEN** Catalog publication may complete while no downloadable export is created

### Requirement: Frozen members are reverified before release materialization
Before publication or export becomes authoritative, the release boundary MUST
stream every frozen member from server-owned immutable content using the exact
logical path, kind, media type, size, SHA-256, content identity, and stable
ordering recorded by the Package revision. Missing, corrupt, duplicate,
traversing, absolute, symlink-derived, undeclared, or extra content MUST fail
closed. A successful release MUST contain exactly the frozen closed inventory;
it MUST NOT rescan a workspace Package, follow the current draft pointer, or
silently repair content from another source.

#### Scenario: Reverify a complete mixed Package
- **WHEN** every canonical definition and managed binary object matches the frozen inventory
- **THEN** materialization produces exactly one regular file for each safe logical member and preserves every recorded digest

#### Scenario: Frozen content is missing or corrupt
- **WHEN** a member cannot be opened exactly or its observed size or digest differs from the Package revision
- **THEN** publication or export fails with a bounded integrity error and exposes no successful release resource

#### Scenario: Workspace source changed after freeze
- **WHEN** the original authoring source or a configured Catalog directory changes after the Package revision was created
- **THEN** release still uses only the frozen server-owned members and neither reads nor copies the changed source

### Requirement: Catalog publication has explicit identity and conflict semantics
Publishing SHALL register one managed immutable Catalog Package for the frozen
`publisher/name@version` identity and its exact content and closure identities.
If that readable identity is already managed with the same semantic content,
publishing MUST return the existing equivalent publication without creating a
second managed entry. If any current managed or configured Catalog source uses
the same readable identity with different content, publishing MUST return a
version conflict and MUST NOT overwrite, shadow, relabel, or reorder the
existing Package. An equivalent configured non-managed source MAY remain as a
separately identified source while the managed publication is created; Catalog
MUST keep the two safe source identities explicit. Older published versions and
historical managed entries MUST remain addressable.

#### Scenario: Publish a new Package version
- **WHEN** no current Catalog entry has the frozen readable Package identity
- **THEN** the command creates one managed publication with an opaque stable publication identity and a stable managed Catalog entry identity

#### Scenario: Publish equivalent content again
- **WHEN** the same readable identity and equivalent frozen content were already published to the managed source
- **THEN** the command returns the existing publication as not newly created and the Catalog contains one equivalent managed entry

#### Scenario: Equivalent configured source already exists
- **WHEN** a configured non-managed source exposes the same readable identity and semantic content
- **THEN** the managed publication may be created while Catalog continues to identify both concrete sources explicitly rather than silently replacing either one

#### Scenario: Publish a conflicting version
- **WHEN** the same readable Package identity is already visible with different canonical content or frozen closure
- **THEN** the command returns a safe conflict that identifies the readable version but discloses no source path and leaves the current Catalog unchanged

#### Scenario: Publish a later semantic version
- **WHEN** a different valid semantic version of the same publisher and name is published
- **THEN** both immutable versions remain independently selectable by their opaque Catalog entry identities

### Requirement: Publication and export commands are durable and idempotent
Every publication and export command SHALL require a stable client request
identity and a canonical request fingerprint scoped to the owning draft and
Package revision. Retrying the same identity and fingerprint MUST return the
original result without duplicating records, Catalog entries, or archives;
reusing the identity with another fingerprint MUST conflict. Successful
publication and export metadata MUST survive restart through storage-neutral
repository contracts. Content preparation MUST complete before authoritative
metadata is committed, and a failed command MUST NOT expose a partial release
resource.

#### Scenario: Retry after a lost publication response
- **WHEN** a publication transaction committed but its response was lost
- **THEN** retrying the same command returns the original publication and does not add another Catalog entry

#### Scenario: Retry after a lost export response
- **WHEN** an export completed but its response was lost
- **THEN** retrying the same command returns the original archive identity and content link without generating another authoritative export

#### Scenario: Reuse a command identity with different content
- **WHEN** a client request identity is reused with another Package revision or command fingerprint
- **THEN** the service returns an idempotency conflict and preserves the first command result

#### Scenario: Metadata commit fails after content preparation
- **WHEN** managed Package files or archive bytes are prepared but the authoritative transaction fails
- **THEN** no queryable publication or export references partial state; unreachable immutable bytes may remain without conveying release authority

### Requirement: Published Packages become visible through atomic Catalog snapshots
A successful publication SHALL make its managed Package visible through one
atomically replaced immutable Catalog snapshot. Each list, detail, task, or
Composer operation MUST capture one snapshot for its complete request, so it
observes either the snapshot before publication or the complete snapshot after
publication, never a partially rebuilt Catalog. Managed publications MUST be
reconstructed after restart before the current snapshot is served. Publication
MUST NOT trigger an arbitrary workspace rescan, discard prior entries, or
invalidate already committed Experiment snapshots.

#### Scenario: Read during publication
- **WHEN** a Catalog request overlaps a successful snapshot replacement
- **THEN** that request returns a self-consistent old or new snapshot and never mixes entry, split, task, or cursor facts from both

#### Scenario: List after successful publication
- **WHEN** publication returns success and a new Catalog list begins
- **THEN** the managed Package is discoverable with its complete immutable metadata and safe managed provenance

#### Scenario: Restart after publication
- **WHEN** Studio restarts with durable managed publication metadata and verified managed Package content
- **THEN** the reconstructed Catalog exposes the same publication and managed Catalog entry identity without consulting the source draft

#### Scenario: Existing Experiment references an older entry
- **WHEN** a publication changes the current Catalog snapshot after an Experiment snapshot was committed
- **THEN** the Experiment retains its original immutable definition facts and is not rewritten to the new Catalog snapshot

### Requirement: Package exports are byte-deterministic and integrity closed
Export SHALL generate a versioned ZIP archive containing exactly the frozen
logical members in stable path order. Entry names MUST be safe normalized
Package-relative paths; timestamps, creator metadata, permissions, compression
method, comments, and extra fields MUST be fixed by the export contract rather
than inherited from the host. The service SHALL record a strict export schema,
Package revision identity, Package/content/closure identities, member count,
archive media type, safe filename, byte size, and SHA-256. Repeating export for
the same Package revision and export contract MUST produce byte-identical
content regardless of working directory, source formatting, file mtime,
locale, operating system path separator, or process restart.

#### Scenario: Export the same Package twice
- **WHEN** the same Package revision is exported under the same export contract in separate clean processes
- **THEN** both archives have identical bytes, size, SHA-256, member names, order, and per-member contents

#### Scenario: Inspect archive membership
- **WHEN** a verifier enumerates a successful export
- **THEN** the archive contains every frozen member exactly once and contains no host path, storage key, draft-only file, undeclared object, or generated runtime output

#### Scenario: Host metadata differs
- **WHEN** source mtimes, current working directory, locale, and platform path separator differ
- **THEN** the export identity and bytes remain unchanged because archive metadata is fixed by the versioned contract

#### Scenario: Archive verification fails
- **WHEN** generated or stored archive bytes do not match the recorded archive digest, size, or member closure
- **THEN** the export is unavailable for download and is never described as a verified package

### Requirement: Release HTTP resources are strict, scoped, and download safe
The local Studio HTTP service SHALL provide a bounded Package-revision page,
exact release resources, and explicit publication and export commands beneath
`/studio/benchmark-authoring/drafts/{draftId}/package-revisions`. Export content
MUST be served only through an exact owning-draft, Package-revision, and export
identity using GET and HEAD with identical availability, size, digest, media
type, and attachment filename facts. Responses MUST preserve existing origin,
method, content-type, body-size, error-envelope, and private no-store controls;
they MUST NOT reveal absolute paths, source locators, storage keys, secrets,
live objects, or raw private capabilities.

#### Scenario: Page durable Package revisions
- **WHEN** a draft has more frozen Package revisions than one response permits
- **THEN** the service returns a stable bounded page and opaque continuation cursor without exposing member bytes or mutable draft state

#### Scenario: Create and read release resources
- **WHEN** a same-origin client submits valid publication or export commands and later reads their exact resources
- **THEN** strict versioned responses return immutable identities, status, safe links, integrity metadata, and truthful safety facts after restart

#### Scenario: Prepare a valid download with HEAD
- **WHEN** the client sends HEAD for an available verified export
- **THEN** the response returns the same safe content metadata and attachment headers as GET with no body and without loading the archive into browser application state

#### Scenario: Reject hidden ownership or unsupported methods
- **WHEN** a release resource is addressed through another draft or Package revision, or a known route receives an unsupported method
- **THEN** the service returns bounded 404 or 405 semantics without disclosing the owner, storage location, or candidate identities

### Requirement: Studio provides a truthful URL-owned Release workflow
The Benchmark draft workspace SHALL provide a `release` mode owned by the URL
alongside the existing definition, resources, validation, and Contract Tests
modes. TanStack Query SHALL own Package-revision, publication, export, and
Catalog server facts; the existing feature-local edit store SHALL remain the
owner of baseline and working-document state; component-local state SHALL own
only confirmation and pending user intent. Release actions MUST require a clean
saved current baseline, present Freeze, Publish, Export, and Download as
separate explicit steps, and reconcile every successful command from its strict
server response. The UI MUST NOT infer publication from validation, infer an
export URL from an opaque identity, or store semantic release data in
`localStorage`.

#### Scenario: Open Release mode after refresh
- **WHEN** a user opens `/benchmark-drafts/{draftId}/edit?mode=release`
- **THEN** Studio reconstructs durable Package revisions and their publication/export facts from strict server resources without relying on a prior browser session

#### Scenario: Local edit session is dirty
- **WHEN** the current draft has parsed edits, unapplied text, invalid text, or a server conflict
- **THEN** Freeze is disabled with a truthful clean-baseline explanation while existing immutable Package revisions remain inspectable

#### Scenario: Freeze then choose a release action
- **WHEN** an author explicitly freezes a clean current revision successfully
- **THEN** the new Package revision becomes selectable, but Publish and Export remain separate user commands and neither runs automatically

#### Scenario: Download a verified export
- **WHEN** an export is available and its exact HEAD preparation succeeds
- **THEN** the browser is handed the authoritative content link for native download without buffering archive bytes in React, query cache, or the edit store

#### Scenario: Publication conflict or corrupt export
- **WHEN** publication conflicts with different content or export integrity preparation fails
- **THEN** the UI preserves the selected immutable revision, displays the authoritative bounded failure, and does not fabricate Catalog visibility or a download

### Requirement: Release preserves source, runtime, and adjacent product boundaries
Publication and export MUST write only database metadata and database-sibling
server-owned managed release storage. They MUST NOT modify original Catalog
sources, authoring drafts or revisions, workspace `benchmarks/`, workspace
`data/`, imported legacy JSON, installed distributions, or runtime output.
They MUST NOT import or instantiate Package plugins, invoke initializer or
evaluator code, connect to a device, call a model, resolve secrets, access the
network, execute an Agent or Benchmark, create an Experiment, or claim Contract
Test, execution, real-device, model, or statistical evidence. The capability
MUST preserve BenchmarkTask V1, Benchmark Package canonical semantics,
AgentConfig/AgentGraph independence, existing Catalog and Composer behavior,
Experiment/report/Replay/history, and experiment-result Export contracts.

#### Scenario: Release with fail-fast runtime canaries
- **WHEN** a valid Package revision is published and exported with fail-fast canaries at plugin, initializer, evaluator, device, model, network, secret, Agent, Benchmark, and Experiment boundaries
- **THEN** every canary remains untouched while only managed release facts and bytes are produced

#### Scenario: Inspect publication evidence
- **WHEN** a Package is visible in managed Catalog
- **THEN** the release record proves only publication of the exact frozen closure and retains `executionEvidence=false` and `realDeviceEvidence=false`

#### Scenario: Preserve original sources
- **WHEN** publication and export complete successfully
- **THEN** source Package trees, draft revisions, current pointers, imported JSON, installed distributions, and existing runtime artifacts remain byte-for-byte and identity-semantically unchanged

#### Scenario: Request legacy migration or release deletion
- **WHEN** a caller requests legacy JSON conversion, unpublish, delete, retention cleanup, external object storage, or real Android acceptance
- **THEN** the E-2 capability does not perform it and leaves those concerns to later explicit contracts

