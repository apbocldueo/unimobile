# studio-benchmark-android-service-acceptance Specification

## Purpose
Define the bounded, opt-in evidence required to prove that the existing Studio Benchmark service completes representative positive and controlled-negative Experiments on one explicitly selected real Android target without broadening product claims.
## Requirements
### Requirement: Real-Android acceptance must use explicit immutable selections
Stage 5.6C-1 SHALL run only after the operator explicitly selects one configured safe device profile, one Package and task, one Protocol, one repeat, and one immutable Agent revision for each Experiment. The positive and controlled-negative scenarios MUST use the same profile, Package, task, Protocol, and repeat in isolated durable workspaces, and acceptance MUST fail closed before execution if any selected identity or private target authority is missing, changed, or ambiguous.

#### Scenario: Operator confirms the bounded matrix
- **WHEN** the operator supplies valid safe selections and explicitly starts real-Android acceptance
- **THEN** exactly one positive Experiment and one controlled-negative Experiment are created with one Agent, one task, and one repeat each, while the private target remains server-local

#### Scenario: Selection is incomplete or authority drifts
- **WHEN** a required immutable identity is absent or the selected profile no longer resolves to its pinned exact target
- **THEN** acceptance stops before initializer, Agent, evaluator, model, or Android action effects and does not substitute another device or revision

### Requirement: Positive acceptance must prove independent Agent, Benchmark, and device outcomes
The representative positive Experiment SHALL pass through the production Studio repository, scheduler, worker, durable journal, Core Benchmark Runtime, and Android action boundary. It MUST reach one completed Experiment and TaskRun terminal state, record Agent `SUCCESS`, Benchmark `PASS`, and evaluator `PASS`, and independently demonstrate the expected Android device-state delta rather than deriving device success solely from the evaluator result.

#### Scenario: Representative task succeeds on the selected target
- **WHEN** the selected immutable positive Agent revision performs the bounded task through the production Android action boundary
- **THEN** the Experiment and TaskRun complete exactly once, Agent status is `SUCCESS`, Benchmark outcome is `PASS`, evaluator evidence passes, and an independent before/after device observation records the expected new state

#### Scenario: Evaluator passes without independent device evidence
- **WHEN** the evaluator reports success but the independent device-state observation is absent, inconclusive, or inconsistent
- **THEN** the positive acceptance gate fails and the run is not reported as verified real-Android service evidence

### Requirement: Controlled-negative acceptance must preserve normal Agent completion
The controlled-negative Experiment SHALL use an immutable Agent revision that ends normally without satisfying the same task evaluator. It MUST produce Agent `SUCCESS`, Benchmark `FAIL`, evaluator `FAIL`, `INVALID=0`, and no success-state device delta. The negative outcome MUST NOT be manufactured through preflight, setup, cleanup, cancellation, timeout, unavailable authority, or infrastructure failure.

#### Scenario: Agent intentionally omits the success action
- **WHEN** the controlled Agent completes normally without performing the task's success action
- **THEN** the Experiment terminates as completed, Agent status is `SUCCESS`, Benchmark outcome is `FAIL`, the evaluator is false, `INVALID=0`, and the independent device observation finds no new success-state evidence

#### Scenario: Infrastructure failure resembles a negative result
- **WHEN** preflight, setup, cleanup, device authority, cancellation, timeout, or service infrastructure fails
- **THEN** the run is classified outside the controlled-negative gate and cannot satisfy Stage 5.6C-1 negative evidence

### Requirement: Each real execution must close managed evidence and service resources
For both scenarios, acceptance SHALL reconstruct the immutable TaskResult, strict report, trajectory, manifest, bundle, native Replay projection, managed artifact inventory, and applicable evidence/export resources from authoritative Studio identities. Every declared managed member MUST be readable through its exact scoped service resource and pass the existing size, checksum, media-type, and causal-ownership checks; unavailable or corrupt required evidence MUST fail the scenario rather than be inferred or fabricated.

#### Scenario: Terminal publication is complete
- **WHEN** a scenario reaches terminal publication
- **THEN** all required result, report, trajectory, manifest, bundle, Replay, inventory, evidence, and export facts resolve to the same Experiment and TaskRun and every declared managed member passes exact integrity checks

#### Scenario: Declared evidence is missing or cross-owned
- **WHEN** a required member is missing, corrupt, oversized, belongs to another Experiment or TaskRun, or cannot be reached through its authoritative link
- **THEN** service acceptance fails without copying an alternate artifact or weakening the integrity check

### Requirement: Evidence provenance must distinguish source execution from Replay
Every source TaskResult produced by the two accepted runs SHALL record acquisition `fresh_execution`, environment `real_android`, and `realDeviceEvidence=true` only after actual source execution on the pinned target. Native Replay SHALL preserve the source environment but record acquisition `replay_projection` and `realDeviceEvidence=false`; a profile label, task title, URL, screenshot appearance, or historical artifact MUST NOT independently grant real-device evidence.

#### Scenario: Fresh source result is published
- **WHEN** a scenario actually executes on the pinned Android target and its source result is committed
- **THEN** the TaskResult reports `fresh_execution`, `real_android`, and `realDeviceEvidence=true` together with the safe selected profile identity

#### Scenario: Native Replay is reconstructed
- **WHEN** the same TaskRun is projected into native Replay
- **THEN** Replay reports `replay_projection`, preserves `real_android` as source environment, and keeps `realDeviceEvidence=false` because Replay is not a new execution

### Requirement: Terminal restart must reconstruct without replaying effects
After each scenario reaches terminal publication, Stage 5.6C-1 SHALL stop and reopen the same durable workspace using unchanged trusted authority. The reopened service MUST reconstruct the same Experiment, TaskRun, TaskResult, publication, Replay, event high-water mark, and managed artifact identities, MUST retain exactly one terminal semantic transition, and MUST NOT rerun initializer, Agent, evaluator, Android actions, or publication-visible source execution.

#### Scenario: Terminal workspace is reopened
- **WHEN** the service restarts after a fully published positive or controlled-negative result
- **THEN** all authoritative identities and terminal facts remain stable, no duplicate terminal event appears, and independent effect counters plus device observations show no new execution side effect

#### Scenario: Restart would require uncertain source replay
- **WHEN** reconstruction cannot prove that terminal execution and publication are already committed
- **THEN** the scenario fails its terminal non-replay gate rather than rerunning any uncertain Agent or Android effect

### Requirement: Acceptance evidence must remain bounded and redact private authority
Stage 5.6C-1 SHALL emit a versioned, machine-readable, bounded summary that links only safe scenario, Experiment, TaskRun, result, publication, Replay, artifact, outcome, provenance, integrity, restart, and claim-limit facts. Raw serials, ADB arguments, trusted configuration paths, private binding fingerprints, target keys, secrets, live objects, host absolute paths, and sensitive exception text MUST NOT appear in public JSON, events, diagnostics, logs, TaskResults, reports, trajectories, Replay, inventories, manifests, bundles, exports, or the acceptance summary.

#### Scenario: Real-device evidence is scanned
- **WHEN** the database, event stream, logs, managed evidence, exports, and acceptance summary are scanned after both scenarios and restart
- **THEN** no private target or secret material is present and all device references use only safe profile and bounded provenance facts

#### Scenario: Private value appears in an internal failure
- **WHEN** an internal Android or configuration error contains a raw private value
- **THEN** persisted and public failure evidence contains only stable safe codes and bounded redacted text

### Requirement: Completion claims must require fresh manual evidence and remain narrow
Automated fake-device, no-device, definition-level, and regression tests SHALL remain useful prerequisites but MUST NOT complete Stage 5.6C-1. Completion requires fresh successful execution of both opt-in real-Android scenarios and every evidence, security, and restart gate. The handoff MUST bind claims to the selected device, platform context, Package/task/Protocol, Agent revisions, application versions, and single-repeat configuration, and MUST NOT claim broad Android compatibility, arbitrary Agent or task success, model quality, statistical significance, automatic diagnosis, browser acceptance, or expanded Studio Worker cardinality.

#### Scenario: Only automated regressions pass
- **WHEN** all fake/no-device tests pass but either real-Android scenario has not been executed successfully in the current acceptance campaign
- **THEN** Stage 5.6C-1 remains incomplete and documentation continues to identify real service evidence as pending

#### Scenario: Both real scenarios and all gates pass
- **WHEN** the positive, controlled-negative, publication, provenance, restart, integrity, and redaction gates all pass on the explicitly selected matrix
- **THEN** the milestone is reported only as bounded real-Android Studio service acceptance and the next planned change remains the 5.6C-2 real-browser journey

