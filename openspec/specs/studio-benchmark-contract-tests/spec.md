# studio-benchmark-contract-tests Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-contract-tests-5-5d. Update Purpose after archive.
## Requirements
### Requirement: Studio Contract Tests are bound to an exact current revision
The Studio Benchmark authoring service SHALL expose Contract Tests only for an owned draft, an explicit immutable authoring revision identity, an explicit split, a bounded integer seed, and a selected server-known fixture profile. The service MUST verify that the revision belongs to the draft and remains the draft current revision before work begins and again before returning authority. Every result SHALL be bound to the draft identity, revision identity, document fingerprint, split, seed, fixture profile identity/version, and established Package and BenchmarkPlan identities. The command MUST NOT append a revision, advance the current pointer, change `unvalidated` status, persist a result, or create publication eligibility.

#### Scenario: Test an exact current revision
- **WHEN** an author requests Contract Tests for an owned current revision, declared split, bounded seed, and available fixture profile
- **THEN** the service returns only facts produced from that exact immutable revision without mutating durable authoring state

#### Scenario: Reject a stale revision before testing
- **WHEN** the requested revision is no longer the draft current revision
- **THEN** the service returns a conflict containing only the safe current revision identity and invokes no fixture

#### Scenario: Current pointer advances during testing
- **WHEN** the current revision changes after Contract Tests start but before the result is returned
- **THEN** the service discards result authority, returns the stale-current conflict, and leaves both revisions unchanged

#### Scenario: Hide foreign revision ownership
- **WHEN** a valid revision identity is requested through another draft identity
- **THEN** the service returns not found without exposing the owning draft, revision content, profile internals, or Contract Test facts

### Requirement: Exact revision compilation reuses the private disposable Package boundary
The service SHALL reconstruct only the exact revision's closed manifest, task-file, Protocol, and managed-resource inventory through the existing verified private materializer and SHALL compile the requested split before fixture discovery. Definition serialization, managed-content integrity checks, safe path handling, deterministic identity computation, and cleanup MUST retain the Stage 5.5C-1 contracts. Invalid definitions SHALL produce bounded field-addressable precondition diagnostics and no fixture cases; missing, corrupt, unsafe, or over-capacity content MUST fail closed without exposing bytes, host paths, temporary paths, or private content identities.

#### Scenario: Compile a complete exact revision
- **WHEN** every declared definition and managed resource in the current revision passes integrity verification and the selected split compiles
- **THEN** fixture discovery receives the exact BenchmarkPlan and established identities from the disposable Package and the temporary root is removed afterward

#### Scenario: Definition is invalid
- **WHEN** the current revision cannot produce a valid BenchmarkPlan for the selected split
- **THEN** the result contains safe member-local precondition diagnostics, contains no fixture cases, and does not reinterpret validation failure as a failed plugin contract

#### Scenario: Managed content fails integrity
- **WHEN** a declared resource is missing or does not match its immutable size, digest, or regular-file contract
- **THEN** the request fails closed or returns the applicable safe content diagnostic before any fixture invocation and cleans all disposable state

#### Scenario: Disposable cleanup fails
- **WHEN** temporary Package cleanup cannot complete after success or failure
- **THEN** the command returns an analysis-unavailable failure without exposing the temporary location or publishing a partial Contract Test result

### Requirement: Fixture profiles are explicit server-owned capabilities
Studio SHALL obtain fixture profiles from an injected server-owned registry and SHALL expose only bounded metadata needed for an author to select an available profile. Every profile MUST have a stable identity, version, evidence level, supported contract kinds, and declared capability requirements. The default Studio profile MUST reject descriptors requiring device, model, network, secret, Agent execution, Experiment, publication, or real-runtime access. Benchmark authoring documents, Package manifests, task JSON, Protocol files, managed resources, and request payloads MUST NOT embed or upload executable fixture code, import paths, module names, callables, credentials, or host capabilities.

#### Scenario: Select an available safe profile
- **WHEN** the author selects a profile whose metadata declares only supported fake-fixture capabilities
- **THEN** Studio resolves fixtures only through that exact injected profile identity and records its identity and version in the result

#### Scenario: Request an unavailable profile
- **WHEN** a request names an unknown, disabled, or changed fixture profile
- **THEN** the service rejects the request before Package materialization or fixture invocation and does not guess a replacement profile

#### Scenario: Unknown third-party logical reference
- **WHEN** a valid Package references a third-party initializer, environment, or evaluator for which the selected profile has no explicit descriptor
- **THEN** the corresponding case is skipped and Studio does not import, discover, instantiate, or execute the referenced plugin implementation

#### Scenario: Profile requests a forbidden capability
- **WHEN** profile metadata or fixture resolution requests device, model, network, secret, Agent execution, Experiment, publication, or real-runtime access
- **THEN** the default Contract Test command rejects the profile or case and exposes no such capability to fixture code

#### Scenario: Package attempts to supply executable fixture data
- **WHEN** an authoring document or HTTP payload includes fixture source code, module paths, callable identities, credentials, or unknown execution fields
- **THEN** existing strict definition or request parsing rejects it and no uploaded value becomes executable

### Requirement: Contract Test results are strict, bounded, and coverage-aware
The service SHALL return a strict schema-1 result containing immutable request ownership, established identities, profile provenance, safety facts, deterministic aggregate counts, and bounded stable-order cases. Each case SHALL identify its task and definition location, contract kind, logical reference, fixture identity when matched, case-local seed, executed checks, skip reasons, and safe diagnostics, and SHALL carry exactly one `passed`, `failed`, or `skipped` status. The public result MUST contain at most 1,000 cases and 100 diagnostics, MUST reject unsupported cardinality before case execution, and MUST never expose a partial case list as complete. Aggregate completeness and executed-check success MUST be separate facts, and `realDeviceEvidence` and `processSandbox` MUST remain false.

#### Scenario: All covered cases pass
- **WHEN** every bounded logical reference has a matching fixture and all required checks pass
- **THEN** the result reports zero failed and skipped cases, `complete=true`, and executed-check success without claiming real plugin, runtime, or device evidence

#### Scenario: Covered and uncovered cases are mixed
- **WHEN** all executed fixtures pass but at least one logical reference has no matching fixture
- **THEN** the result reports the exact passed and skipped counts, `complete=false`, and does not present the whole revision as fully Contract Tested

#### Scenario: One fixture contract fails
- **WHEN** one fixture violates determinism, isolation, lifecycle, type, serialization, or evidence-safety rules while other cases are valid
- **THEN** that case is failed, independent bounded cases continue in stable order, and aggregate executed-check success is false

#### Scenario: Unsafe diagnostic payload is produced
- **WHEN** fixture failure text or evidence contains a secret-shaped value, host path, device serial, private identity, binary content, or live object
- **THEN** the response retains only stable safe diagnostic fields and does not serialize or log the unsafe value

#### Scenario: Case capacity would be exceeded
- **WHEN** fixture discovery determines that the exact Plan requires more than 1,000 occurrence cases
- **THEN** the service returns a capacity failure before invoking any fixture and returns no partial case collection

### Requirement: Contract Test HTTP resources are strict and privately cache-controlled
The local Studio HTTP service SHALL provide a strict schema-1 JSON `POST` command at `/studio/benchmark-authoring/drafts/{draftId}/contract-tests` and a bounded same-origin metadata resource for available Contract Test profiles. The command MUST reject unknown or malformed fields and preserve existing Host, origin, content-type, body-size, and method protections. It SHALL return bad envelope or unavailable profile as 400, hidden ownership as 404, stale current revision as 409, unsupported input or result capacity as 413, and unavailable private materialization or fixture service as 503. Successful and error responses MUST use private no-store semantics; known routes with unsupported methods MUST return 405.

#### Scenario: Run Contract Tests over HTTP
- **WHEN** a same-origin caller posts a strict request for an owned exact current revision and available profile
- **THEN** the service returns one bounded no-store schema-1 result bound to the request and exact revision

#### Scenario: List fixture profile metadata
- **WHEN** a same-origin caller requests available Contract Test profiles
- **THEN** the service returns only bounded stable profile metadata and exposes no fixture callable, module path, secret, or private registry object

#### Scenario: Reject unknown request fields
- **WHEN** the request includes source code, import/module paths, destination paths, content identities, device profiles, credentials, runtime options, or another unknown field
- **THEN** the service returns a bounded 400 response before materialization or fixture invocation

#### Scenario: Reject unsupported method
- **WHEN** a caller uses an unsupported HTTP method on a known Contract Test or profile route
- **THEN** the service returns 405 and performs no fixture or authoring command

### Requirement: Studio exposes a URL-owned Contract Tests mode
Studio SHALL add `contract-tests` as a bounded mode on `/benchmark-drafts/:draftId/edit` alongside definition, resources, and validation. The mode SHALL retain the same draft route and authoritative current-revision query; unsupported mode values MUST still fall back safely to definition. Entering or reloading the mode MUST NOT automatically list execution internals, run Contract Tests, save content, execute a Benchmark, or contact a device. The surface SHALL load bounded profile metadata, accept an explicit split and seed, and run only after an explicit author action.

#### Scenario: Open Contract Tests mode directly
- **WHEN** an author opens a valid draft URL with `mode=contract-tests`
- **THEN** Studio renders the Contract Test surface for that authoritative draft without starting a Contract Test command

#### Scenario: Move among authoring modes
- **WHEN** the author moves between definition, resources, validation, and contract-tests
- **THEN** Studio changes only the bounded URL mode, keeps the same draft identity, and does not duplicate durable authoring state

#### Scenario: Open an unsupported mode
- **WHEN** the URL contains an unknown mode value
- **THEN** the workbench falls back to definition and starts no guessed profile or Contract Test request

### Requirement: Contract Tests require a clean saved baseline
The Contract Test action SHALL be eligible only when the definition session is clean, every raw task buffer is valid and applied, the feature baseline equals the authoritative current revision, no conflict or remote-newer fact is active, and definition save, content mutation, validation/dry-run, and Contract Test commands are idle. The command MUST use only the exact saved baseline revision and MUST NOT serialize unsaved browser-local definition, file, fixture, or credential state. Every blocked state SHALL identify the explicit apply, save, reset, wait, or Reload Remote action required.

#### Scenario: Run against a clean baseline
- **WHEN** the saved baseline equals the authoritative current revision and all authoring commands are idle
- **THEN** Studio can submit the exact revision, explicit split, bounded seed, and selected profile

#### Scenario: Block dirty or unapplied definition data
- **WHEN** structured definition state is dirty or task JSON is invalid or unapplied
- **THEN** Studio disables Contract Tests and requires apply-and-save or reset rather than testing browser-local content

#### Scenario: Block pending or conflicting authoring state
- **WHEN** save, content, validation/dry-run, or Contract Test work is pending, or a conflict, remote-newer, or baseline mismatch exists
- **THEN** Studio starts no new Contract Test and exposes the corrective wait or Reload Remote action

### Requirement: Visible results remain request-owned and disposable
The Contract Test feature SHALL own only bounded profile selection, split, seed, command lifecycle, result ownership, diagnostic focus, and presentation state. TanStack Query SHALL continue to own authoritative draft and profile resources; the definition feature SHALL retain its editable baseline, raw buffers, dirty, conflict, and remote-newer state. A visible result SHALL be accepted only when its draft, revision, fingerprint, split, seed, profile identity/version, feature generation, and active request owner still match. Relevant input changes, dirty state, save/content success, Reset, Reload Remote, 409, draft switch, or revision advance MUST invalidate the result; an aborted or late response MUST NOT regain authority.

#### Scenario: Accept the active result
- **WHEN** a response owner exactly matches the active clean revision, inputs, profile version, and feature generation
- **THEN** Studio presents it as disposable Contract Test evidence for that exact request

#### Scenario: Discard a late response
- **WHEN** the author changes split, seed, profile, draft, revision, or session generation before an earlier response completes
- **THEN** Studio discards the response even when network cancellation did not finish

#### Scenario: Invalidate after authoring change
- **WHEN** definition becomes dirty or save, upload, replacement, removal, Reset, Reload Remote, or conflict reconciliation changes authority
- **THEN** the previous result and diagnostic focus become stale or are cleared and an explicit rerun is required

#### Scenario: Reload the browser
- **WHEN** the browser reloads a `contract-tests` route
- **THEN** it reconstructs URL mode and authoritative resources but does not claim durable recovery of transient inputs or results

### Requirement: The view presents Contract Test facts and limits truthfully
The view SHALL distinguish not-run, pending, passed coverage, failed checks, skipped coverage, mixed incomplete coverage, transport failure, stale, and capacity states without conflating them. It SHALL show aggregate counts, completeness, executed-check success, profile provenance, exact revision and Plan ownership, and bounded cases grouped or filterable by initializer, environment, and evaluator kind. Diagnostics SHALL navigate through public workbench intents to the exact known manifest, task file, Protocol file, or safe field breadcrumb. `realDeviceEvidence=false`, `processSandbox=false`, package-code-not-executed, and the absence of Benchmark execution, Agent execution, publication eligibility, and persisted validation status MUST remain visible for every result.

#### Scenario: Present incomplete successful coverage
- **WHEN** all executed cases pass but one or more cases are skipped
- **THEN** Studio shows successful executed checks and incomplete coverage as separate facts and does not display an unqualified all-passed state

#### Scenario: Filter case kinds without changing facts
- **WHEN** the author filters initializer, environment, evaluator, passed, failed, or skipped cases
- **THEN** the view changes only bounded presentation and does not recompute counts, status, or evidence

#### Scenario: Navigate to a definition diagnostic
- **WHEN** the author activates a case diagnostic with a known member and field path
- **THEN** the workbench selects the exact definition member and displays a safe field breadcrumb without claiming unsupported caret precision

#### Scenario: Keep safety limitations visible
- **WHEN** any Contract Test result is displayed
- **THEN** the view states that only trusted fake fixtures ran in-process, no Package plugin implementation or real runtime was proven, and the revision remains `unvalidated`

### Requirement: Contract Tests preserve existing product and execution boundaries
The capability MUST preserve existing Benchmark Package scaffold/validate/dry-run/contract-test CLI behavior, legacy BenchmarkTask JSON, Package/Plan/Protocol canonical identities, Stage 5.5A/B/C authoring APIs and views, Catalog, Experiment resource and worker, Report, History, Replay, Export, AgentConfig, and AgentGraph behavior. It MUST work from a clean installed wheel without repository-relative imports. No SQLite migration, arbitrary uploaded Python, Package fixture schema, process sandbox, real-device profile, Agent execution, Benchmark execution, durable Contract Test result, publication/migration, worker expansion, PostgreSQL, object storage, retention/delete, or Android acceptance claim SHALL be added by this change.

#### Scenario: Complete a no-device browser journey
- **WHEN** an author opens Contract Tests mode, observes a dirty gate, saves, runs passing/failed/skipped fixtures, follows a diagnostic, changes inputs, and reconciles a stale revision
- **THEN** only bounded revision-owned fake-fixture facts are produced and all runtime/external-boundary canaries remain zero

#### Scenario: Preserve adjacent authoring behavior
- **WHEN** Contract Tests mode is installed beside Definition, Resources, and Validation
- **THEN** existing save, content, validation, dry-run, Catalog, Experiment, reporting, Replay, and export journeys retain their established contracts

#### Scenario: Run from a clean wheel
- **WHEN** the service is installed in a clean environment and tests a managed draft from a repository-independent working directory
- **THEN** profile discovery, disposable reconstruction, bounded fake fixtures, HTTP DTOs, and cleanup work through installed-package resources without leaking a source path

