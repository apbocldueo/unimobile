# studio-benchmark-validation-dry-run-view Specification

## Purpose
定义 Studio Benchmark authoring 的 URL-owned Validation mode、strict revision-bound
validation/dry-run 消费、clean saved-baseline gate、immutable Agent revision 选择、
stale-result reconciliation、diagnostic navigation、bounded truthful presentation 与
zero-runtime-side-effect 合同。
## Requirements
### Requirement: Studio exposes a URL-owned validation and dry-run mode
Studio SHALL expose a `validation` mode on the stable `/benchmark-drafts/:draftId/edit` route alongside the existing definition and managed-resources modes. The selected work mode MUST be reconstructable from the bounded `mode` URL value, MUST retain the same draft identity and authoritative current-revision query, and MUST fall back to definition mode for unsupported values. Entering the mode MUST NOT automatically issue validation, dry-run, Agent revision, runtime, or device commands.

#### Scenario: Open validation mode directly
- **WHEN** an author opens a valid draft editor URL with `mode=validation`
- **THEN** Studio loads the authoritative draft and renders the validation/dry-run authoring surface without starting analysis automatically

#### Scenario: Move between authoring modes
- **WHEN** the author moves between definition, resources, and validation
- **THEN** Studio preserves the stable draft route, changes only the bounded URL mode, and does not copy the draft document into a competing feature-owned model

#### Scenario: Open an unsupported mode
- **WHEN** the route contains an unsupported mode value
- **THEN** Studio renders the safe definition mode and starts no guessed analysis command

### Requirement: The frontend strictly consumes revision-bound analysis resources
The frontend SHALL define strict schema-1 request and response contracts and entity operations for the existing Stage 5.5C-1 validation and dry-run commands. Parsers MUST reject unknown envelope fields, malformed or contradictory identities, unsafe member paths or field paths, out-of-bound diagnostics, Agent selections, task selections, or schedules, and any response that claims execution evidence. React components MUST invoke the resources through entity or Query integrations and MUST NOT calculate Package, content, Plan, Protocol, or AgentGraph canonical identities locally.

#### Scenario: Parse a valid partial validation result
- **WHEN** validation returns a valid schema-1 result with only the Package identity established and bounded diagnostics explaining unavailable downstream identities
- **THEN** the entity layer preserves the exact revision binding, partial identities, diagnostics, truncation, unverified facts, and `executionEvidence=false`

#### Scenario: Parse a complete dry-run result
- **WHEN** dry-run returns verified Agent revisions, a complete bounded schedule, budget, fairness warnings, output layout, identities, and no execution evidence
- **THEN** the entity layer preserves those server facts without recomputing or strengthening them

#### Scenario: Reject a misleading or malformed result
- **WHEN** a response contains an unknown field, malformed ownership, over-capacity collection, unsafe path, contradictory mode, or `executionEvidence` other than false
- **THEN** the parser rejects the result before it enters visible analysis state

#### Scenario: Surface bounded HTTP failures
- **WHEN** Stage 5.5C-1 returns malformed-request, hidden ownership, stale-current, capacity, or analysis-unavailable status
- **THEN** Studio presents the safe error fact and does not reinterpret it as a semantic validation result or execution failure

### Requirement: Analysis commands require an exact clean saved baseline
Studio SHALL enable validation and dry-run only when the definition session is clean, every raw task buffer is valid and applied, definition save and managed-content commands are idle, no conflict or remote-newer fact is active, and the local baseline revision equals the authoritative draft current revision. Each blocked state MUST identify the save, apply, reset, wait, or Reload Remote action needed to restore eligibility. Analysis MUST use the baseline revision identity and MUST NOT serialize unsaved browser-local definition or file state into the command.

#### Scenario: Analyze a clean current revision
- **WHEN** the local clean baseline exactly equals the authoritative draft current revision and no command is pending
- **THEN** validation and otherwise complete dry-run inputs are eligible against that immutable revision

#### Scenario: Block dirty or unapplied definition data
- **WHEN** structured fields are dirty or a task JSON buffer is invalid or unapplied
- **THEN** Studio disables analysis and instructs the author to apply and save or reset the local work

#### Scenario: Block a pending authoring command
- **WHEN** a definition save or managed-content command is pending
- **THEN** Studio starts no validation or dry-run command until the authoring command reaches a known result and authoritative state is reconciled

#### Scenario: Block conflict or remote-newer state
- **WHEN** the editor has a conflict, a remote-newer fact, or a baseline/current revision mismatch
- **THEN** Studio disables analysis and requires explicit Reload Remote rather than rebasing or analyzing a guessed revision

### Requirement: Validation inputs remain explicit without duplicating Core semantics
The validation view SHALL require an explicit non-empty split input and SHALL offer safely discoverable declared split names only as suggestions. It MUST remain possible to submit an explicit bounded split value when the manifest is semantically invalid or no declared split can be discovered client-side. The frontend MUST NOT treat its manifest inspection as validation and MUST rely on the backend result for split, task, Protocol, resource, and Package semantics.

#### Scenario: Validate a suggested declared split
- **WHEN** the current revision exposes a safely discoverable declared split and the author selects it
- **THEN** Studio submits that exact split with the exact baseline revision and displays only the returned validation facts

#### Scenario: Validate an invalid manifest
- **WHEN** client-side inspection cannot discover a split because the manifest is malformed but the author enters a bounded explicit split
- **THEN** Studio can submit validation so the backend can return field-addressable manifest or split diagnostics

#### Scenario: Avoid automatic semantic validation
- **WHEN** the author edits, saves, reloads, or enters validation mode
- **THEN** Studio does not infer semantic validity from document shape and waits for an explicit validation command

### Requirement: Dry-run freezes bounded immutable Agent revision selections
The dry-run view SHALL allow an author to select one to 16 distinct Agents with saved current revisions and SHALL freeze each selection as the exact `{agentId, revisionId}` pair observed at selection time. Agent candidates MUST be loaded through the existing bounded cursor resource, Agents without a current revision MUST remain unavailable, and refreshing candidate metadata MUST NOT silently advance or replace a frozen pair. The view MUST NOT claim or emulate arbitrary historical revision browsing when no history-list resource exists, and the backend SHALL remain authoritative for exact revision ownership, compile validity, and AgentGraph identity verification.

#### Scenario: Freeze a current Agent revision
- **WHEN** an author selects an Agent whose metadata names a current immutable revision
- **THEN** the dry-run session stores that exact Agent/revision pair and later submits it unchanged unless the author explicitly removes and reselects it

#### Scenario: Agent current pointer advances after selection
- **WHEN** refreshed Agent metadata names a newer current revision after an older pair was selected
- **THEN** Studio keeps the frozen older pair visible and does not substitute the newer revision silently

#### Scenario: Select multiple Agent dimensions
- **WHEN** the author selects distinct Agents up to the bound of 16
- **THEN** Studio submits each exact pair once and prevents duplicate Agent identities and a seventeenth selection

#### Scenario: Agent has no current revision
- **WHEN** candidate metadata contains an Agent without a saved current revision
- **THEN** Studio identifies it as unavailable for dry-run and constructs no guessed revision identity

### Requirement: Dry-run task selection is explicit and bounded
The dry-run view SHALL default an empty task selection to all tasks in the explicit split and SHALL allow an optional subset of at most 100 unique task identities only from safely discoverable current-revision data. Client-side discovery MUST remain a convenience rather than validation authority. Studio MUST display unsupported request or schedule cardinality as a capacity fact and MUST NOT silently truncate task selections or a backend schedule.

#### Scenario: Plan the whole split
- **WHEN** the author keeps the task selection in its default whole-split state
- **THEN** Studio submits an empty `taskIds` collection with the explicit split

#### Scenario: Plan a discoverable task subset
- **WHEN** the author selects unique discoverable task identities within the bound
- **THEN** Studio submits exactly that subset without changing its order or inventing missing tasks

#### Scenario: Capacity is exceeded
- **WHEN** task selection exceeds 100 or the backend reports schedule cardinality above 10,000
- **THEN** Studio prevents the oversized selection or presents the backend capacity failure and displays no partial schedule

### Requirement: Analysis results are bound to revision and request ownership
Every visible validation or dry-run result SHALL be owned by the exact draft identity, baseline revision identity, document fingerprint returned by the backend, split, and command-specific task and Agent selections that produced it. A draft or revision change, dirty local definition, relevant input change, Reload Remote, content success, or stale-current response MUST invalidate the affected result. An in-flight command SHOULD be aborted when practical, but Studio MUST also compare immutable request ownership before accepting completion and MUST discard a late response that no longer matches the active session.

#### Scenario: Accept the active request result
- **WHEN** a command completes and its draft, revision, fingerprint, split, task selection, and Agent selection still match the active request owner
- **THEN** Studio presents the result as analysis of that exact saved revision

#### Scenario: Discard a late response after input change
- **WHEN** the author changes a relevant split, task, or Agent selection before an earlier command completes
- **THEN** Studio discards the late response even if request cancellation did not complete in time

#### Scenario: Invalidate after local or durable authoring change
- **WHEN** definition data becomes dirty or save, upload, replacement, removal, or Reload Remote adopts another revision
- **THEN** Studio removes current-result authority and requires an explicit analysis of the reconciled clean revision

#### Scenario: Handle exact-current conflict
- **WHEN** validation or dry-run returns stale-current conflict with a safe current revision identity
- **THEN** Studio invalidates the result, exposes Reload Remote, and does not automatically overwrite, merge, or retry against the newer revision

### Requirement: The view presents partial planning facts truthfully and boundedly
The validation view SHALL distinguish valid, invalid, transport-failed, pending, stale, and not-yet-run states. It SHALL present each Package, content, Plan, and Protocol identity independently and MUST label an absent identity as not established rather than inventing a placeholder. Dry-run SHALL present verified Agent/revision/AgentGraph identities, complete deterministic schedule, budget, fairness warnings, relative output layout, diagnostics, and unverified checks only when returned. Schedule rendering MUST remain bounded through local pagination or virtualization and MUST never render or copy an unbounded collection. Unverified facts and `executionEvidence=false` MUST remain visible whenever dry-run facts are shown.

#### Scenario: Show partial identities for invalid definition
- **WHEN** validation establishes an upstream Package identity but cannot establish content, Plan, or Protocol identity
- **THEN** Studio shows the Package identity, marks each unavailable identity not established, and keeps the diagnostic explanation visible

#### Scenario: Show a complete bounded schedule
- **WHEN** dry-run returns up to 10,000 deterministic schedule entries
- **THEN** Studio provides bounded local navigation over the complete collection without claiming that the current worker can execute it

#### Scenario: Show fairness and runtime boundaries
- **WHEN** dry-run returns fairness warnings, output layout, dynamic-materialization uncertainty, or current-worker-cardinality uncertainty
- **THEN** Studio presents those facts prominently and does not reword them as fairness proof, created output, execution support, or runtime success

#### Scenario: Keep authoring status truthful
- **WHEN** validation or dry-run succeeds
- **THEN** the draft revision remains displayed as `unvalidated` and Studio exposes no valid-package, runnable, tested, published, migrated, or executed status

### Requirement: Diagnostics navigate through public workbench intents
Each diagnostic SHALL display its stable code, severity, bounded message, semantic member, safe member-local field path, and applicable task, resource, Agent, or revision identity. When the target is known, the validation feature SHALL emit a public navigation intent that the workbench coordinates to the corresponding definition member, managed resource, or Agent selection without importing peer-feature internals. Definition-member navigation MUST select the exact manifest, task file, Protocol file, or resource declaration when present. Exact field control focus SHALL occur only for supported mapped controls; every other path MUST degrade to the correct member plus a visible field-path breadcrumb rather than claiming an exact raw-text cursor.

#### Scenario: Navigate to a definition member
- **WHEN** an author activates a diagnostic for a known manifest, task file, Protocol file, or resource declaration
- **THEN** the workbench switches to definition mode and selects that exact member through the definition feature's public API

#### Scenario: Navigate to a managed resource
- **WHEN** an author activates a content diagnostic with a known logical resource identity
- **THEN** the workbench switches to resources mode and requests selection of that current-revision resource through the resource feature's public API

#### Scenario: Navigate to an Agent diagnostic
- **WHEN** an author activates a diagnostic containing a selected Agent and revision identity
- **THEN** the validation mode focuses or reveals the exact frozen Agent selection without changing it

#### Scenario: Field path has no exact editor control
- **WHEN** a diagnostic addresses an extension field, raw task JSON element, or other unsupported exact control
- **THEN** Studio selects the closest exact member and shows the full safe field path without promising caret-level navigation

### Requirement: Validation-view state remains bounded and correctly owned
TanStack Query SHALL remain the owner of authoritative draft and Agent resources. The existing definition feature SHALL retain ownership of baseline, working document, raw task buffers, dirty, remote-newer, and conflict facts. The validation feature SHALL own only bounded split, task, frozen Agent revision, command lifecycle, result binding, diagnostic focus, and presentation state. URL state SHALL own only the stable workbench mode unless another separately specified route contract exists. Obsolete input, pending ownership, results, pagination, and focus MUST be cleared when draft or authoritative revision identity changes.

#### Scenario: Switch to another draft
- **WHEN** route ownership changes to another valid draft identity
- **THEN** Studio clears the former split, task, Agent, result, diagnostic-focus, and schedule-page state before accepting analysis for the new owner

#### Scenario: Adopt another revision
- **WHEN** the workbench adopts a saved, content-command, or remote current revision
- **THEN** validation session state is reconciled to that exact revision and no earlier result remains authoritative

#### Scenario: Reload the browser
- **WHEN** the browser reloads a validation-mode route
- **THEN** Studio reconstructs the mode and authoritative resources but makes no durable recovery claim for transient selections or analysis results

### Requirement: Validation and dry-run view remains non-executing and backward compatible
The view MUST preserve the Stage 5.5C-1 zero-runtime-side-effect boundary and MUST NOT invoke initializer, environment, evaluator, device, Agent execution, plugin construction, model, network, secret, Experiment, TaskRun, result, report, trajectory, bundle, Replay, Contract Test, publication, migration, export, or Android boundaries. It MUST expose no Run, Contract Test, Publish, or Migrate action. Existing definition/resource authoring, Catalog, Experiment, Report, History, Replay, Export, CLI authoring, BenchmarkTask JSON, AgentConfig, AgentGraph, and current worker behavior MUST remain available, and no backend API, database migration, or Agent revision-history resource SHALL be introduced by this capability.

#### Scenario: Complete a no-device validation journey
- **WHEN** an author opens validation mode, observes a dirty gate, saves, validates, follows a diagnostic, selects frozen Agent revisions, and performs dry-run
- **THEN** the journey returns only revision-bound definition and planning facts while all runtime and external-boundary canary counts remain zero

#### Scenario: Avoid future-work controls
- **WHEN** the validation view renders any pending, successful, invalid, stale, or failed result
- **THEN** it exposes no execution, Contract Test, publication, or migration control and makes no corresponding completion claim

#### Scenario: Preserve existing Studio behavior
- **WHEN** the validation mode is added
- **THEN** existing authoring modes, Agent Builder, Benchmark Catalog, Experiment creation and monitoring, reporting, Replay, Export, CLI, BenchmarkTask JSON, AgentConfig, and AgentGraph paths retain their established behavior
