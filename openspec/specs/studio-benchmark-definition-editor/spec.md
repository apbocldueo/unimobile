## Purpose

Define the Studio definition-only, unvalidated Benchmark draft editor built on
the Stage 5.5A durable authoring resource, including strict resource parsing,
lossless structured editing, client-local task buffers, optimistic revision
saves, and truthful read-only managed-resource boundaries.
## Requirements
### Requirement: Studio exposes independent Benchmark definition authoring routes
Studio SHALL expose an independent Benchmark Authoring entry route at
`/benchmark-authoring` and a stable draft editor route at
`/benchmark-drafts/:draftId/edit`. These routes MUST remain part of the
Benchmark product area, MUST use draft identity as navigation state, and MUST
NOT reuse Agent Builder, XYFlow, or Experiment Composer as the Benchmark
definition model.

#### Scenario: Open the authoring entry
- **WHEN** a user follows the Benchmark Authoring navigation entry
- **THEN** Studio opens `/benchmark-authoring` and presents durable draft creation and reopening actions rather than an AgentGraph canvas

#### Scenario: Open a stable draft route
- **WHEN** a user opens `/benchmark-drafts/{draftId}/edit` with a valid draft identity
- **THEN** Studio reconstructs the editor from the authoritative current authoring revision for that exact draft

#### Scenario: Reject an invalid draft route
- **WHEN** the editor route contains a missing or malformed draft identity
- **THEN** Studio displays a bounded route error and does not issue a request using a guessed or normalized replacement identity

### Requirement: The frontend consumes the strict Stage 5.5A authoring resource
The frontend SHALL define strict versioned parsers and typed API operations for
the existing draft list, draft detail, exact revision, template/Catalog create,
and optimistic revision-save resources. Unknown envelope fields, malformed
identities, unsafe values, and malformed pagination or error data MUST fail
closed before becoming editor state. React components MUST consume entity query
and command APIs rather than issuing direct network requests.

#### Scenario: Parse a valid draft detail
- **WHEN** the Stage 5.5A service returns a valid draft with its current immutable revision
- **THEN** the entity layer returns a typed resource preserving the exact draft, revision, document, fingerprint, provenance, ordinal, and unvalidated status facts

#### Scenario: Reject malformed authoring data
- **WHEN** an authoring response contains an unknown envelope field, malformed identity, non-finite value, or resource metadata outside the strict schema
- **THEN** the parser rejects the response, the editor does not hydrate from it, and the page shows a bounded resource error

#### Scenario: Preserve safe server errors
- **WHEN** create, list, get, or save returns the existing bounded Studio error envelope
- **THEN** the command/query layer exposes the stable status, error code, and safe conflict identity without parsing behavior from human-readable text

### Requirement: Authors can create and reopen durable drafts
The authoring entry SHALL list durable drafts using the bounded server page and
SHALL allow creation from one of the supported private templates or an opaque
available Catalog entry. Creation MUST use a stable client request identity and
MUST navigate only from the committed response. The browser MUST NOT accept a
host path, destination, force flag, or arbitrary Package directory as a source.

#### Scenario: Create from a supported template
- **WHEN** an author submits a valid name, Package identity fields, and one of the supported template names
- **THEN** Studio sends one idempotent create intent and navigates to the returned draft editor route after the service commits the initial revision

#### Scenario: Create an editable Catalog copy
- **WHEN** an author selects an available opaque Catalog entry and confirms draft creation
- **THEN** Studio submits only that Catalog identity and navigates to the independently managed draft returned by the service

#### Scenario: Retry after an uncertain create response
- **WHEN** a create response is lost or transport fails before its outcome is known
- **THEN** retrying the unchanged user intent reuses its client request identity instead of creating a second draft

#### Scenario: Page through durable drafts
- **WHEN** the author requests more drafts from a page with a continuation cursor
- **THEN** Studio requests the next bounded page using the opaque cursor and does not infer ordering or identity from visible names

### Requirement: Structured edits preserve the parsed Package definition losslessly
The editor SHALL provide structured controls for known manifest identity and
metadata, platforms, split-to-task-file membership, default Protocol reference,
named Protocol documents, applications, plugins, and inline JSON ground-truth
definition data. Editing a known field MUST patch the parsed document in place,
MUST preserve every untouched safe extension field and inventory member, and
MUST maintain the deterministic inventory ordering required by the authoring
resource. The editor MUST NOT describe these structural edits as formal
Benchmark validation.

#### Scenario: Edit a known manifest field
- **WHEN** an author changes a supported manifest field in the structured form
- **THEN** the working document changes only that field and preserves unknown safe sibling fields byte-semantically after JSON parse and serialization

#### Scenario: Edit split membership
- **WHEN** an author adds, removes, or reorders a task-file reference in a split
- **THEN** the editor updates the parsed manifest membership while preserving unrelated task files and normalizing persisted inventory order deterministically

#### Scenario: Edit a Protocol document
- **WHEN** an author changes a supported seed, repeat, order, budget, device, application, isolation, or failure-policy field
- **THEN** the selected parsed Protocol mapping is patched without dropping unsupported extension fields or claiming that the Protocol is semantically valid

#### Scenario: Edit inline ground truth
- **WHEN** ground truth is represented as inline JSON definition data rather than a managed file resource
- **THEN** the author can edit that parsed value through the definition editor while file-backed ground truth remains read-only

### Requirement: Task source uses explicit client-local JSON buffers
The editor SHALL expose an explicit JSON text surface for each selected task
file. Raw buffer text MUST be owned by the local edit session, MUST contribute
to dirty and navigation-guard state, and MUST enter the parsed working document
only after an explicit successful parse/apply action. A syntactically invalid
or unsafe buffer MUST remain visible locally, MUST show a precise client-side
syntax or safety error, and MUST block revision save without being sent to the
service.

#### Scenario: Apply a valid task-file buffer
- **WHEN** an author edits a task-file buffer to a safe JSON array and explicitly applies it
- **THEN** the parsed task file in the working document is replaced by that array and the raw buffer remains synchronized with the applied value

#### Scenario: Keep invalid JSON local
- **WHEN** an author introduces invalid JSON and attempts to apply or save
- **THEN** the editor retains the raw text and error locally, leaves the last parsed working document unchanged, and sends no save command

#### Scenario: Navigate among task files with an invalid buffer
- **WHEN** one task file has an invalid or unapplied raw buffer and the author selects another file
- **THEN** the edit session retains the first file buffer and continues to report the overall draft as dirty and not saveable

#### Scenario: Reset an invalid buffer
- **WHEN** the author confirms reset to the saved baseline
- **THEN** all task buffers are reconstructed from the baseline and local syntax errors are cleared

### Requirement: Server resource state and the local edit session have separate owners
TanStack Query SHALL own authoring list/detail/revision server resources and
request lifecycle. A feature-local Zustand store SHALL own only the current
draft identity, immutable baseline clone, parsed working document, per-file raw
buffers, selection, dirty state, base revision identity, pending save intent,
and conflict identity. Background refetch MUST NOT overwrite a dirty local edit
session, and changing to a different draft identity MUST establish a separate
session.

#### Scenario: Hydrate a clean edit session
- **WHEN** a valid current revision first loads for a draft with no active local session
- **THEN** the editor clones it into distinct baseline and working documents and starts clean with its revision as the optimistic base

#### Scenario: Ignore background replacement while dirty
- **WHEN** a query refetch returns a newer server resource while the local edit session is dirty
- **THEN** Studio records that remote data may be newer but does not replace the working document or raw buffers automatically

#### Scenario: Move to another draft
- **WHEN** navigation changes from one valid draft identity to another after any required dirty confirmation
- **THEN** the feature clears the previous session and hydrates only from the second draft's strict current revision

### Requirement: Revision save is idempotent, optimistic, and non-destructive
Save SHALL submit the complete strict parsed working document with the
client-observed base revision and one stable client request identity for the
unchanged save intent. A retry after an uncertain transport outcome MUST reuse
that identity. A successful response MUST replace the baseline, working
document, raw buffers, and base identity with the returned immutable revision.
A stale-revision conflict MUST preserve every local edit, expose the safe
current revision identity, disable blind resubmission, and MUST NOT auto-merge
or auto-overwrite.

#### Scenario: Save a dirty parseable document
- **WHEN** the working document is dirty, all raw buffers are applied and safe, and no conflict is active
- **THEN** Studio submits one optimistic save command and adopts the exact returned revision as the new clean baseline

#### Scenario: Retry an unchanged save intent
- **WHEN** a save transport outcome is uncertain and the document and base revision have not changed
- **THEN** retry uses the same client request identity so the service can return the original committed revision

#### Scenario: Encounter a stale base
- **WHEN** the service returns a revision conflict with a safe current revision identity
- **THEN** Studio preserves the working document and raw buffers, displays the conflict identity, and prevents last-writer-wins save

#### Scenario: Edit after a failed save
- **WHEN** the author changes the working document after a non-committed save failure
- **THEN** the former save intent is retired and a later save uses a new client request identity and the still-authoritative base revision

### Requirement: Reset, reload, and navigation protect unsaved work explicitly
Reset SHALL restore the current local baseline after confirmation. Reload
remote SHALL require confirmation when local work is dirty, fetch the
authoritative draft detail, and replace the session only from a strict valid
response. In-app navigation and browser unload MUST warn while parsed edits,
unapplied buffers, or invalid buffers are dirty. The editor MUST NOT claim
durable recovery for browser-local invalid text.

#### Scenario: Reset dirty local work
- **WHEN** an author confirms reset while parsed or raw-buffer edits are dirty
- **THEN** Studio restores the saved baseline, rebuilds buffers, clears local errors and conflict state, and creates no revision

#### Scenario: Cancel remote reload
- **WHEN** an author declines confirmation to discard dirty local work
- **THEN** Studio keeps the complete edit session unchanged and issues no destructive hydration

#### Scenario: Confirm remote reload after conflict
- **WHEN** an author confirms reload after a conflict and the strict current resource loads successfully
- **THEN** Studio replaces the local session with that revision and clears the conflict without deleting any server revision

#### Scenario: Close a tab with invalid local text
- **WHEN** an author attempts to unload the page while an invalid JSON buffer is dirty
- **THEN** the browser unload guard is active and the UI has not represented that text as durably saved

### Requirement: Managed resources remain truthful read-only inventory
The definition editor SHALL render existing asset and file-backed ground-truth
inventory using only the safe metadata provided by the authoring revision:
logical identity, kind, Package-relative path, media type, size, digest, and
opaque content identity. It MUST NOT expose a host path or infer a public
content capability, and MUST NOT offer upload, binary preview, replacement,
logical removal, or content deletion in this change.

#### Scenario: Inspect an imported resource
- **WHEN** an imported authoring revision contains a managed asset
- **THEN** Studio shows its authoritative bounded metadata with a read-only label and no fabricated open or download action

#### Scenario: Inspect file-backed ground truth
- **WHEN** ground truth is represented by a managed resource entry
- **THEN** Studio distinguishes it from inline JSON ground truth and defers content editing to the later resource-editor change

#### Scenario: Content identity is not a capability
- **WHEN** resource metadata contains an opaque content identity
- **THEN** the frontend treats it as displayable identity data only and does not construct a URL from it

### Requirement: The editor remains definition-only and reports evidence truthfully
The definition editing mode MUST preserve `status: unvalidated` as the
authoritative source-revision fact and MUST NOT expose Validate, Dry-run,
Contract Test, Run, Publish, Migrate, Package Export, resource mutation, or
Benchmark drag-canvas actions inside the definition surface. A separate
URL-owned Release mode MAY expose Freeze, Publish, Package Export, and Download
over strict server resources, but it MUST NOT merge release state into the
parsed working document, raw task buffers, or optimistic save intent. Loading,
editing, resetting, creating, and saving MUST NOT connect a device, instantiate
a plugin, resolve a secret, call a model, execute an initializer/evaluator,
create an Experiment, or create report, trajectory, Replay, or publication
facts.

#### Scenario: Save does not imply validity
- **WHEN** a revision save succeeds
- **THEN** Studio labels it saved and unvalidated without calling it valid, runnable, tested, frozen, exported, or published

#### Scenario: Switch from definition to Release mode
- **WHEN** a user opens Release mode for the same draft
- **THEN** the definition baseline, working document, and raw buffers retain their existing owner while release server facts are loaded independently and do not rewrite the edit session

#### Scenario: Complete the no-device authoring journey
- **WHEN** a browser lists drafts, creates one from a template or Catalog entry, edits structured fields and task JSON, saves, resets, reloads, and observes a conflict
- **THEN** the journey completes against the authoring resource with no runtime boundary call or Experiment, report, trajectory, Replay, or publication output

#### Scenario: Existing Studio and Benchmark paths remain available
- **WHEN** the separate Release workflow is added
- **THEN** existing Agent Builder, definition/resources/validation/Contract Test modes, Benchmark Catalog, Experiment Composer, Monitor, Report, History, Replay, experiment-result Export, CLI authoring, BenchmarkTask JSON, AgentConfig, and AgentGraph paths retain their established behavior

### Requirement: Authoring landing page provides an explicit legacy migration workflow
The `/benchmark-authoring` page SHALL present Legacy BenchmarkTask JSON migration as a third draft source beside Template and Catalog creation. The selected file text, editable target metadata, preview response, structured diff, diagnostics, stale state, and uncertain confirm intent MUST remain feature-local browser state until a successful confirm creates a durable draft. The browser MUST send source text rather than a local path and MUST NOT auto-preview, auto-confirm, mutate a source file, or place migration controls inside an existing draft workbench mode.

#### Scenario: Select source and preview explicitly
- **WHEN** an author selects a bounded JSON file, supplies target metadata, and presses Preview
- **THEN** the page submits the source text to the preview resource, displays the safe source facts and structured result, and creates no draft

#### Scenario: Refresh before confirmation
- **WHEN** the author refreshes or leaves the page before confirming
- **THEN** browser-local source and preview state may be discarded and no durable migration draft or server-side preview resource exists

#### Scenario: Existing draft modes remain unchanged
- **WHEN** an author opens an existing draft in definition, resources, validation, contract-tests, or release mode
- **THEN** the workbench retains its existing ownership and gates and does not expose a Migrate command for replacing that draft

### Requirement: Migration review is bounded, truthful, and stale-aware
The migration surface SHALL show confirmability, source and preview fingerprints, retained/renamed/removed/rewritten counts, Package wrapper additions, mechanically derived declarations, omitted Protocol/ground-truth/resource facts, post-migration work, diagnostics, and explicit false validation/publication/execution evidence. Changing the selected source or any target metadata after preview MUST immediately mark the preview stale and disable Confirm until a new preview succeeds. Non-confirmable results MUST keep Confirm disabled while preserving safe diagnostics for correction.

#### Scenario: Duplicate fixture is non-confirmable
- **WHEN** preview reports duplicate task IDs
- **THEN** the page displays the duplicate task locations and entry/unique counts, states that no task will be renamed or removed, and disables Confirm

#### Scenario: Target metadata changes after preview
- **WHEN** the author edits publisher, package name, version, title, platform, split, task-file target, draft name, or replaces the selected file after preview
- **THEN** the page labels the preview stale, clears its confirm authority, and requires another explicit Preview

#### Scenario: Valid source has unresolved author work
- **WHEN** a confirmable source still contains relative resource references or incomplete App declarations and no Protocol or ground truth
- **THEN** the page distinguishes those post-migration authoring tasks from migration errors and does not describe the candidate as validated or runnable

### Requirement: Confirm uses exact intent and hands off only authoritative state
The page SHALL require an explicit Confirm action for a current confirmable preview. It MUST retain one semantic confirm intent, including its client request identity and source/preview ownership, across an uncertain response and reuse it only for an exact retry. On a successful created or replayed response, the page MUST invalidate relevant draft queries and navigate to the authoritative new draft Definition Editor; it MUST NOT optimistically synthesize a draft, revision, validation result, frozen Package, Catalog entry, publication, or execution fact.

#### Scenario: Confirm and open new draft
- **WHEN** exact confirmation returns a durable draft and initial revision
- **THEN** the page navigates to `/benchmark-drafts/:draftId/edit`, where authoritative query state shows the migrated `unvalidated` revision

#### Scenario: Confirm response is uncertain
- **WHEN** the network fails after Confirm may have committed
- **THEN** the page preserves the exact selected source, target intent, preview fingerprint, and client request identity and offers an exact retry without generating a new command identity

#### Scenario: Confirm returns stale preview conflict
- **WHEN** the server rejects confirmation because recomputation no longer matches the preview
- **THEN** the page clears confirm authority, preserves editable source/target inputs, and requires another Preview rather than forcing creation or silently adopting a different candidate

