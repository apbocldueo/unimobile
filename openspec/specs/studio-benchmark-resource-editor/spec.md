# studio-benchmark-resource-editor Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-resource-editor-5-5b3. Update Purpose after archive.
## Requirements
### Requirement: Studio exposes a dedicated managed-resources authoring mode
Studio SHALL expose a managed-resources mode on the stable `/benchmark-drafts/:draftId/edit` route alongside the existing definition mode. The selected work mode MUST be reconstructable from a bounded URL value, MUST retain draft identity as the resource owner, and MUST NOT reuse Agent Builder, XYFlow, Experiment Composer, or a new competing Benchmark document model.

#### Scenario: Open managed resources directly
- **WHEN** an author opens a valid draft editor URL with managed-resources mode selected
- **THEN** Studio loads the authoritative draft and renders its managed asset and file-backed ground-truth inventory

#### Scenario: Return to definition editing
- **WHEN** the author switches from managed resources to definition mode
- **THEN** Studio keeps the same draft route and renders the existing definition session without copying it into resource-feature state

#### Scenario: Open an unsupported mode value
- **WHEN** the route contains an unsupported work-mode value
- **THEN** Studio falls back to the safe definition mode without constructing a different draft identity or issuing a guessed content command

### Requirement: The frontend consumes strict owner-scoped managed-content contracts
The frontend SHALL define strict versioned types, parsers, entity operations, and Query integration for the existing Stage 5.5B-2 upload, replace, logical-remove, and exact `HEAD` routes. React components MUST NOT issue direct requests, encode content as JSON/Base64, accept `contentIdentity` as authority, or construct a capability without exact draft, revision, and logical resource identities.

#### Scenario: Parse a valid upload result
- **WHEN** the service returns a valid upload result with a complete immutable revision and authoritative resource metadata
- **THEN** the entity layer preserves the exact operation, created fact, draft, revision, resource, media type, size, digest, and ownership facts

#### Scenario: Reject a malformed content result
- **WHEN** a response contains unknown envelope fields, malformed identities, contradictory operation fields, unsafe resource metadata, or mismatched draft/revision ownership
- **THEN** the parser rejects it before Query cache or editor state changes

#### Scenario: Send raw file bytes
- **WHEN** an author confirms upload or replacement
- **THEN** the entity operation sends the selected `File` or `Blob` as the raw request body, allows the browser to supply its exact content length, and does not allocate a Base64 or JSON copy

#### Scenario: Content identity is not a capability
- **WHEN** a resource row contains an opaque content identity
- **THEN** Studio may display the identity as metadata but constructs no read or write route from that identity alone

### Requirement: Resource mutations require an exact clean saved baseline
Studio SHALL enable upload, replacement, and logical removal only when the definition session is clean, all raw task buffers are valid and applied, save and content commands are idle, no conflict or remote-newer fact is active, and the local baseline revision equals the authoritative draft current revision. A blocked action MUST explain which save, reset, reload, or pending condition prevents the command.

#### Scenario: Mutate a clean current draft
- **WHEN** the saved baseline is clean and exactly matches the server current revision
- **THEN** managed-resource commands are available against that immutable base revision

#### Scenario: Block while definition data is dirty
- **WHEN** parsed definition fields or task buffers contain unsaved, invalid, or unapplied work
- **THEN** upload, replace, and remove are disabled and Studio instructs the author to save or reset before changing managed content

#### Scenario: Block a remote-newer baseline
- **WHEN** background query state indicates a newer remote revision or the authoritative current identity differs from the local baseline
- **THEN** Studio disables resource commands and requires an explicit remote reload rather than silently rebasing the content action

#### Scenario: Block concurrent commands
- **WHEN** a definition save or managed-content mutation is pending
- **THEN** Studio starts no second resource mutation from the same workbench

### Requirement: Authors can upload assets and file-backed ground truth
The resource editor SHALL allow an author to select a local file and submit a new stable logical resource ID, an `asset` or `ground_truth` kind, a matching Package-relative path, and an explicit media type against the clean base revision. Studio MUST rely on the returned immutable revision for authoritative size, SHA-256, media type, and content identity and MUST NOT invent task or ground-truth bindings.

#### Scenario: Upload a new asset
- **WHEN** an author submits a file with a new logical ID and an `assets/` path from a clean current revision
- **THEN** Studio sends one idempotent upload command and adopts the returned current immutable revision whose inventory contains the authoritative asset facts

#### Scenario: Upload file-backed ground truth
- **WHEN** an author submits a file with a new logical ID and a `ground_truth/` path
- **THEN** Studio adopts the returned file-backed ground-truth resource without changing inline ground truth or creating a semantic binding automatically

#### Scenario: Surface a rejected upload
- **WHEN** the service rejects duplicate identity/path, invalid metadata, capacity, framing, or storage
- **THEN** Studio retains the selected file and form state, displays the safe failure fact, and does not mutate visible inventory optimistically

### Requirement: Authors can explicitly replace or logically remove a resource
Replacement SHALL retain the selected resource's logical ID, kind, and Package-relative path while allowing new file bytes and media type. Logical removal SHALL require explicit confirmation, SHALL adopt only the returned immutable revision, and SHALL describe the operation as removing the current declaration rather than deleting historical bytes or repairing definition references.

#### Scenario: Replace current bytes
- **WHEN** an author selects a resource, chooses replacement bytes and media type, and confirms from a clean current baseline
- **THEN** Studio adopts the returned revision with the same logical ID, kind, and path and displays the server-derived new size and digest

#### Scenario: Repair missing content by replacement
- **WHEN** exact availability reports a current resource as missing and the author submits replacement bytes
- **THEN** replacement remains available and Studio adopts the returned readable resource facts without claiming semantic validation

#### Scenario: Confirm logical removal
- **WHEN** an author confirms removal of a selected resource
- **THEN** Studio adopts the returned revision without that resource, clears obsolete selection, and explains that earlier immutable revisions remain retained

#### Scenario: Preserve dangling definition data
- **WHEN** logical removal leaves a manifest, task, or inline JSON reference unresolved
- **THEN** Studio leaves that definition data unchanged, keeps the revision unvalidated, and defers the diagnostic to the later validation workflow

### Requirement: Content commands are retryable without regressing current state
The resource editor SHALL retain one client request identity for an unchanged operation, draft, base revision, logical metadata, and selected file after an uncertain result. Editing the intent, choosing another file, changing base revision, receiving a conflict, or completing the command MUST retire that identity. Query and editor rehydration MUST distinguish a newly current result from an exact retry result whose returned revision is historical.

#### Scenario: Retry an unchanged uncertain upload
- **WHEN** an upload outcome is unknown and the author retries without changing its base, metadata, or selected file
- **THEN** Studio reuses the client request identity so the service can return the originally committed revision

#### Scenario: Change an uncertain intent
- **WHEN** the author changes any command field or selects another file after an uncertain outcome
- **THEN** Studio creates a new client request identity and does not reuse the previous byte-bound intent

#### Scenario: Adopt a newly current revision
- **WHEN** a content result's draft current pointer equals its returned immutable revision
- **THEN** Studio updates the exact revision and current draft Query caches and rehydrates the definition baseline and working document from that returned revision

#### Scenario: Confirm a historical exact retry
- **WHEN** an exact retry returns its original revision but the returned draft current pointer names a later revision
- **THEN** Studio caches the original revision only as exact history, reports that the command was confirmed, refetches the authoritative current draft, and never replaces current editor state with the historical result

### Requirement: The editor reports current-revision content availability truthfully
Studio SHALL render authoritative inventory metadata immediately and SHALL check bytes only through the selected resource's exact draft/revision/resource `HEAD` capability. A successful check MUST verify declared media type, exact size, and safe attachment headers. Missing, unavailable, header-contract failure, pending, and unchecked states MUST remain distinct, and Studio MUST NOT infer a more specific corruption cause than the response proves.

#### Scenario: Verify a readable selected resource
- **WHEN** exact `HEAD` returns headers matching the revision declaration
- **THEN** Studio marks that selected current-revision resource readable and continues to display the revision's media type, size, and SHA-256

#### Scenario: Show missing content
- **WHEN** exact `HEAD` returns not found for a resource declared by the selected revision
- **THEN** Studio displays a missing-content fact without removing the metadata declaration or treating the package as validated

#### Scenario: Show unavailable or inconsistent content
- **WHEN** exact `HEAD` returns unavailable or its headers disagree with declared media type, size, or attachment policy
- **THEN** Studio displays an unavailable or integrity-contract failure and does not fetch or preview the body

#### Scenario: Avoid unbounded inventory probing
- **WHEN** a draft contains many resources
- **THEN** Studio checks only the selected resource or an explicitly retried check rather than automatically issuing one request per inventory row

### Requirement: Resource-editor state remains bounded and correctly owned
TanStack Query SHALL own authoritative draft and revision resources. The existing definition feature SHALL remain the owner of baseline, working document, raw task buffers, dirty, remote-newer, and conflict facts. The resource feature SHALL own only transient resource selection, file/form input, availability state, confirmation state, pending mutation, and retry intent, and MUST clear obsolete state when draft or adopted revision identity changes.

#### Scenario: Switch to another draft
- **WHEN** navigation changes to a different valid draft identity
- **THEN** Studio clears the former resource selection, file, availability, and retry intent before accepting commands for the new owner

#### Scenario: Remove the selected resource
- **WHEN** a successful removal revision no longer contains the selected resource
- **THEN** the resource feature clears or deterministically moves selection without retaining a capability for the removed current declaration

#### Scenario: Reload with a selected file
- **WHEN** the browser reloads while a file is selected but not committed
- **THEN** the local file selection is lost and Studio makes no durable-recovery claim

### Requirement: Managed-resource editing remains definition-only and backward compatible
Every resource command and UI state in this change MUST preserve `status: unvalidated` and MUST NOT invoke Benchmark validation, dry-run, Contract Test, initializer, environment, evaluator, Agent, device, plugin construction, model, network, secret, Experiment, report, trajectory, Replay, publication, migration, or export boundaries. Existing definition editing, Catalog import, CLI authoring, BenchmarkTask JSON, AgentConfig, AgentGraph, and Studio Benchmark routes MUST retain their established behavior.

#### Scenario: Content success does not imply semantic validity
- **WHEN** upload, replacement, or logical removal succeeds
- **THEN** Studio reports a saved immutable unvalidated revision and does not label it valid, runnable, tested, published, migrated, or executed

#### Scenario: Complete the no-device resource journey
- **WHEN** a browser opens a draft, observes a blocked dirty action, uploads, verifies availability, replaces, handles a conflict or uncertain retry, and logically removes a resource
- **THEN** the journey completes through the authoring resource with zero runtime/device/validation/publication side effects

#### Scenario: Preserve existing authoring and runtime paths
- **WHEN** the resource editor is added
- **THEN** existing definition save/reset/reload, Agent Builder, Benchmark Catalog, Experiment, Report, History, Replay, Export, CLI authoring, BenchmarkTask JSON, AgentConfig, and AgentGraph behavior remains available

