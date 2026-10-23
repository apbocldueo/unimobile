# studio-benchmark-validation-dry-run-resource Specification

## Purpose
定义 Studio Benchmark authoring exact-current revision 的无副作用 validation/dry-run、私有一次性 Package 重建、字段级诊断、可信 identity、immutable Agent revision 验证与有界确定性规划合同。

## Requirements

### Requirement: Analysis is bound to the exact current authoring revision
The system SHALL expose validation and dry-run commands only through an owned Benchmark draft and an explicit immutable authoring revision identity. Each command MUST verify that the revision belongs to the draft and is still the draft's current revision before analysis starts, MUST require an explicit declared split, and MUST bind every returned fact to the draft identity, revision identity, document fingerprint, and selected split. Analysis MUST NOT mutate the draft, append a revision, advance the current pointer, or persist a validation cache.

#### Scenario: Validate the exact current revision
- **WHEN** a caller requests validation for a revision that belongs to the draft, remains current, and names a declared split
- **THEN** the system analyzes exactly that immutable revision and returns revision-bound facts without changing durable authoring state

#### Scenario: Reject a stale revision
- **WHEN** the draft current pointer has advanced beyond the revision named by the request
- **THEN** the system returns a conflict containing only the safe current revision identity and performs no analysis against either revision

#### Scenario: Hide foreign revision ownership
- **WHEN** a valid revision identity is requested through a different draft identity
- **THEN** the system returns not found without revealing the owning draft or revision content

#### Scenario: Require explicit split selection
- **WHEN** a request omits the split or names a split not declared by the exact revision
- **THEN** the system does not silently select another split and returns a safe request or field-addressable validation fact as appropriate

### Requirement: Exact revision content is reconstructed privately and verified
The system SHALL reconstruct the exact authoring revision as a private disposable Benchmark Package containing only the revision's closed manifest, task-file, Protocol, and declared resource inventory. Definition members MUST be serialized deterministically, managed bytes MUST be opened through the verified content boundary, and every materialized member MUST remain beneath a fresh server-owned temporary root. Missing, unsafe, size-inconsistent, digest-inconsistent, or identity-inconsistent managed content MUST fail closed or become an explicit resource diagnostic, and temporary materialization MUST be removed after every success or failure. Public DTOs, errors, diagnostics, and logs MUST NOT disclose a host path, temporary path, private content identity, secret, or raw managed byte content.

#### Scenario: Reconstruct a complete revision
- **WHEN** an exact current revision has coherent definition members and every declared managed resource passes exact size and digest verification
- **THEN** the system analyzes a disposable Package containing exactly that revision's declared closure and removes it after the command completes

#### Scenario: Current revision references missing managed content
- **WHEN** a declared current resource cannot be opened through the verified content boundary
- **THEN** validation reports a safe diagnostic at that logical resource and does not claim a complete Package or runnable Plan identity

#### Scenario: Managed content integrity mismatch
- **WHEN** stored bytes do not match the revision's declared content identity, digest, size, or regular-file constraints
- **THEN** the system fails closed without exposing bytes or paths and without analyzing a mixed or partially trusted Package

#### Scenario: Materialization fails partway
- **WHEN** serialization, verified reading, writing, flushing, or cleanup fails during disposable reconstruction
- **THEN** no partial Package becomes public or durable, the previous authoring state remains authoritative, and every removable temporary member is cleaned

### Requirement: Validation returns bounded field-addressable diagnostics
The system SHALL adapt the existing side-effect-free Core Benchmark validation levels to the exact disposable Package and SHALL aggregate independently detectable manifest, split, task, Protocol, resource, ground-truth, and logical plugin-reference problems. Each public diagnostic MUST have a stable code, severity, bounded safe message, member kind, Package-relative member path when known, member-local field path, and applicable task, resource, Agent, or revision identity. Multi-file task diagnostics MUST resolve to the originating member and local position rather than an aggregate synthetic index. Diagnostic ordering MUST be deterministic, the response MUST contain at most 100 diagnostics, and truncation MUST be explicit. Validation failure SHALL be an analysis result rather than an HTTP transport failure.

#### Scenario: Aggregate independent errors across members
- **WHEN** a revision contains independent manifest, task, Protocol, resource, and ground-truth errors
- **THEN** validation returns all detectable errors up to the bound in deterministic order without stopping at the first invalid member

#### Scenario: Locate an error in the second task file
- **WHEN** a task contract error originates in a non-first declared task file
- **THEN** the diagnostic identifies that safe Package-relative member and its member-local field path rather than a combined task-array offset

#### Scenario: Bound a large diagnostic set
- **WHEN** validation detects more than 100 independent diagnostics
- **THEN** the system returns the first 100 under the stable ordering and an explicit truncated fact without allocating or serializing an unbounded response

#### Scenario: Return invalid definitions as facts
- **WHEN** the request envelope and ownership are valid but the Benchmark definition is invalid
- **THEN** the HTTP command succeeds with `valid=false`, safe diagnostics, and only identities actually established by validation

### Requirement: Validation identities are truthful and independently gated
The validation response SHALL expose stable Core identities only after the corresponding source has been successfully validated: Package identity after a valid manifest, Package content identity after the declared closure is complete and verified, BenchmarkPlan identity after the selected split compiles, and ExperimentProtocol identity after the declared default Protocol parses. The system MUST NOT invent a missing identity, convert an authoring revision into a published Package revision, or interpret validation as execution, materialization, Contract Test, publication, or runtime proof. Logical plugin availability MUST be checked only through an explicitly injected metadata-only catalog; when that catalog cannot prove availability, the check MUST remain unverified and MUST NOT import or construct plugin code.

#### Scenario: Return partial truthful identities
- **WHEN** the manifest is valid but the selected split or default Protocol is invalid
- **THEN** the response may return the established Package identity but omits unavailable Plan or Protocol identities and explains the failure through diagnostics

#### Scenario: Validate a complete Package
- **WHEN** the exact declared closure, selected split, and default Protocol satisfy their contracts
- **THEN** the response returns the stable Package, content, Plan, and Protocol identities computed by the existing Core canonical contracts

#### Scenario: Plugin availability is not safely knowable
- **WHEN** a logical plugin reference is structurally valid but no metadata-only catalog can prove its availability
- **THEN** validation preserves the logical reference, marks availability unverified, and does not import or instantiate the plugin

### Requirement: Dry-run verifies immutable Agent revisions independently
The dry-run command SHALL accept one to 16 explicit saved Agent revision selections and SHALL revalidate each immutable revision through the existing Studio Agent revision verifier. Each accepted selection MUST return the exact Agent identity, revision identity, and recomputed AgentGraph canonical identity. A request MUST reject duplicate Agent identities even when their revision identities differ, MUST NOT accept a caller-supplied AgentGraph hash as authority, and MUST keep AgentConfig/AgentGraph compilation independent from BenchmarkTask/BenchmarkPlan compilation. Agent validation failures MUST be safe, bounded, field-addressable dry-run facts and MUST prevent schedule construction without changing either resource.

#### Scenario: Verify saved Agent revisions
- **WHEN** every selected Agent revision exists, belongs to its Agent, contains a valid compile snapshot, and recomputes to the stored canonical graph identity
- **THEN** dry-run returns the exact verified Agent/revision/AgentGraph identities for planning

#### Scenario: Reject duplicate Agent dimensions
- **WHEN** a request selects two revisions of the same Agent identity
- **THEN** dry-run rejects the ambiguous dimension before schedule construction instead of collapsing the selections by Agent ID

#### Scenario: Reject invalid Agent revision evidence
- **WHEN** a selected Agent revision is missing, belongs to another Agent, has no valid compile snapshot, or recomputes to a different canonical identity
- **THEN** dry-run returns a safe Agent-addressed failure and no schedule while leaving Benchmark and Agent revision state unchanged

### Requirement: Dry-run produces a complete bounded deterministic plan
After Benchmark validation and Agent revision verification succeed, the system SHALL use the selected split, selected task identities, verified Agent identities, and declared default ExperimentProtocol to derive a deterministic schedule. An empty task selection SHALL mean all tasks in the selected split; an explicit selection MUST contain at most 100 unique task identities and every identity MUST belong to that split. The system MUST compute `repeats × selected tasks × selected Agents` before schedule allocation, MUST reject a result above 10,000 entries, and MUST return either the complete ordered schedule or no schedule. The response SHALL include the existing stable Package, content, Plan, Protocol, and AgentGraph identities plus deterministic budget, fairness-warning, output-layout, and schedule facts.

#### Scenario: Plan all tasks in a split
- **WHEN** a valid request supplies an empty task selection and the declared Protocol keeps the aggregate schedule within bounds
- **THEN** dry-run returns the complete deterministic schedule for every task in the selected split across the verified Agents and repeats

#### Scenario: Plan an explicit task subset
- **WHEN** a caller supplies a valid unique subset of at most 100 task identities
- **THEN** dry-run includes only those selected tasks and preserves the existing deterministic schedule ordering and seed derivation semantics

#### Scenario: Reject unsupported schedule cardinality before allocation
- **WHEN** repeats multiplied by selected tasks and selected Agents would exceed 10,000 schedule entries
- **THEN** dry-run returns an explicit unsupported-cardinality diagnostic and no partial schedule without constructing the oversized tuple

#### Scenario: Report fairness and budget facts
- **WHEN** the declared Protocol disables comparable TaskInstance reuse, supplies unequal planning conditions, or declares bounded resource budgets
- **THEN** dry-run returns the existing deterministic budget projection and explicit fairness warnings without claiming statistical fairness or runtime enforcement evidence

### Requirement: Materialization-dependent and runtime facts remain explicitly unverified
Dry-run SHALL distinguish definition-level planning facts from values that require initializer, environment, evaluator, device, model, network, secret, or runtime execution. Dynamic task parameters, rendered instructions, concrete TaskInstances, live device/App state, evaluator outcomes, output files, reports, trajectories, bundles, and runtime success MUST remain absent or explicitly unverified. The output-layout projection MUST describe only the planned relative structure and MUST NOT create directories or artifacts. Multi-task, repeat, or multi-Agent schedule preview MUST NOT be presented as support in the current single-worker execution slice.

#### Scenario: Dynamic task requires initializer materialization
- **WHEN** a selected task needs initializer-generated values or a rendered instruction
- **THEN** dry-run preserves the deterministic schedule template and marks materialization-dependent values unverified without invoking the initializer

#### Scenario: Preview output layout
- **WHEN** a valid dry-run computes an output layout
- **THEN** it returns only safe relative planned locations and creates no Experiment, TaskRun, report, trajectory, bundle, or runtime output directory

#### Scenario: Preview exceeds current worker execution scope
- **WHEN** a valid dry-run contains multiple tasks, repeats, or Agents
- **THEN** the response keeps the definition-level plan but explicitly states that this does not prove the current Studio worker can execute that cardinality

### Requirement: Validation and dry-run HTTP resources are strict and side-effect free
The local Studio HTTP service SHALL provide strict schema-1 JSON `POST` commands at `/studio/benchmark-authoring/drafts/{draftId}/validate` and `/studio/benchmark-authoring/drafts/{draftId}/dry-run`. The commands MUST reject unknown or malformed envelope fields, preserve existing Host/origin/body-size protections, and return bounded safe errors: bad envelope as 400, hidden ownership as 404, stale current revision as 409, unsupported request or output capacity as 413, and unavailable private analysis storage as 503. Known routes with unsupported methods MUST return 405. The complete path MUST make zero calls to initializer, environment, evaluator, device, Agent execution, plugin construction, model, network, secret, Experiment, result, report, Replay, publication, migration, export, or Android boundaries.

#### Scenario: Call the validation HTTP command
- **WHEN** a same-origin caller posts a strict valid validation request for an owned current revision
- **THEN** the service returns a bounded schema-1 revision-bound validation response with private no-store semantics

#### Scenario: Reject unknown request fields
- **WHEN** a request includes a destination path, content identity, device profile, secret, runtime option, or any unknown field
- **THEN** the service returns a bounded 400 response without materializing content or entering Core compilation

#### Scenario: Analysis storage is unavailable
- **WHEN** the server cannot create or safely use its private disposable analysis root
- **THEN** the service returns a bounded 503 response without changing the draft, exposing a path, or returning partial analysis facts

#### Scenario: Prove the zero-side-effect boundary
- **WHEN** validation and dry-run are exercised through their complete HTTP journeys with fail-fast canaries installed at every runtime and external boundary
- **THEN** all canary invocation counts remain zero while deterministic definition-level results are returned

### Requirement: Compatibility and installation boundaries remain intact
The implementation SHALL preserve existing Benchmark Package CLI validate/dry-run behavior, legacy BenchmarkTask JSON loading, canonical Package/Plan/Protocol/AgentGraph identities, Stage 5.5A/B draft and content APIs, Catalog validation, Experiment preview/create, and current execution behavior. The capability MUST work from a clean installed wheel outside the repository without repository-relative imports or source paths. No database migration, React Validation mode, Contract Test, publication/migration workflow, worker expansion, retention/delete, PostgreSQL/object storage adapter, third-party process sandbox, or real Android claim SHALL be introduced by this change.

#### Scenario: Existing CLI and Catalog validation regressions
- **WHEN** existing Package fixtures are validated and dry-run through the public CLI and Catalog paths after this change
- **THEN** their accepted behavior and frozen canonical identities remain unchanged

#### Scenario: Analyze from an installed wheel
- **WHEN** the service is installed into a clean environment and analyzes a managed current revision from a repository-independent working directory
- **THEN** validation and dry-run complete using installed-package resources only and expose no repository source path

#### Scenario: Existing execution path remains narrow
- **WHEN** this change is installed beside the current single-worker Experiment implementation
- **THEN** no worker scheduling, lifecycle, Android, result, report, or Replay behavior changes

