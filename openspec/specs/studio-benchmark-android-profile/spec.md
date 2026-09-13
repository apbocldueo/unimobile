# studio-benchmark-android-profile Specification

## Purpose
Define the trusted local Android profile authority that binds safe Studio identities to exact private targets, prevents silent retargeting, and records truthful execution-evidence provenance without exposing device serials.
## Requirements
### Requirement: Android profiles must come from versioned trusted local configuration
Studio SHALL load Android execution profiles only from an explicit versioned server-local configuration. Every production profile MUST have a unique safe `deviceProfileId`, label, Android platform, and one exact private target; an absent configuration SHALL produce an empty executable profile directory rather than an implicit `local-android` binding. The browser and ordinary public APIs MUST NOT submit, read, or replace the private target.

#### Scenario: Service starts without profile configuration
- **WHEN** Studio starts without an explicit trusted Android profile configuration
- **THEN** all no-device resources remain available, the safe executable profile directory is empty, and no ADB discovery occurs

#### Scenario: Explicit production profile is loaded
- **WHEN** a valid versioned local configuration binds `local-android` to one private Android target
- **THEN** Studio publishes only its safe ID, label, platform, and configured state while retaining the exact target exclusively in the trusted server boundary

#### Scenario: Two profiles alias the same target
- **WHEN** trusted configuration binds two public profile IDs to the same private target
- **THEN** configuration is rejected with a safe diagnostic before the service advertises either binding

#### Scenario: Configuration contains an incomplete binding
- **WHEN** a production profile omits its exact private target or attempts implicit unique-device selection
- **THEN** the profile is rejected and Studio does not synthesize a fallback binding

### Requirement: Accepted work must pin private binding authority
When an executable Benchmark Experiment is accepted, Studio SHALL atomically pin a private binding fingerprint for the selected profile together with the accepted aggregate. The fingerprint MUST be stable across restart for unchanged trusted configuration, MUST change when the private target changes, and MUST remain outside public definition snapshots and managed artifacts. Execution SHALL compare the pinned fingerprint with current authority and MUST NOT silently retarget accepted work.

#### Scenario: Service restarts with unchanged binding
- **WHEN** an accepted side-effect-free Experiment is recovered after restart with the same trusted private target
- **THEN** the current binding matches the pinned fingerprint and the Experiment remains eligible for normal scheduling

#### Scenario: Profile is rebound before execution
- **WHEN** an accepted Experiment pinned profile A but current trusted configuration maps the same profile ID to another target
- **THEN** execution fails with a stable binding-drift diagnostic before device access or Benchmark plugin side effects

#### Scenario: Atomic create fails while pinning authority
- **WHEN** persistence fails between creating the Experiment aggregate and its private binding record
- **THEN** neither the Experiment nor a partial binding authority becomes visible

### Requirement: Device authority must fail closed before Benchmark actions
After pure definition and storage preflight, Studio SHALL resolve only the pinned exact target, verify that it is present and ready, acquire a target-level exclusive lease, and recheck cancellation before entering Benchmark Runtime. Missing, offline, unauthorized, drifted, ambiguous, or busy targets MUST terminate safely before initializer, evaluator, Agent, model, or other task actions. Studio MUST NOT fall back to another online Android device.

#### Scenario: Configured target is offline
- **WHEN** the pinned target is reported offline or unauthorized at execution
- **THEN** the Experiment records a bounded device-authority failure and performs no Benchmark action

#### Scenario: Multiple unrelated devices are online
- **WHEN** several Android devices are ready but the selected profile pins exactly one of them
- **THEN** Studio verifies and leases only the pinned target without ambiguity or fallback

#### Scenario: Device context differs from Protocol
- **WHEN** exact-target authority succeeds but Core observes a platform, locale, orientation, or required-App mismatch
- **THEN** existing Core preflight produces its pre-action `INVALID` semantics and Studio does not replace it with a competing service outcome

### Requirement: Execution evidence provenance must use independent acquisition and environment facts
Studio SHALL represent evidence provenance with separate bounded facts for acquisition (`fresh_execution`, `replay_projection`, `imported_excerpt`, or `contract_fixture`) and execution environment (`real_android`, `fake_device`, or `unverified`). A configured profile, successful preview, URL, title, screenshot appearance, Replay transport, or historical artifact MUST NOT by itself set `real_android` or grant current real-device evidence.

#### Scenario: Fake-device contract execution
- **WHEN** a deterministic fake profile produces a TaskResult and native Replay projection
- **THEN** the source result records `contract_fixture` plus `fake_device`, while Replay records its projection acquisition separately and preserves `fake_device`

#### Scenario: Native Replay from a real execution
- **WHEN** a future verified real-Android TaskRun is projected into native Replay
- **THEN** Replay records `replay_projection` while preserving the source environment as `real_android` rather than claiming a new fresh execution

#### Scenario: Profile exists but no execution occurred
- **WHEN** a client only lists, previews, or accepts a configured Android profile
- **THEN** no result is marked as fresh execution or real-device evidence

### Requirement: Private device authority must never enter public or managed evidence
Raw serials, ADB arguments, private binding fingerprints, live device handles, and trusted configuration paths MUST NOT appear in HTTP DTOs, SSE events, diagnostics, logs, TaskResults, reports, trajectories, Replay envelopes, artifact metadata, bundles, or browser state. Safe outputs SHALL use only opaque profile identities, bounded provenance facts, check outcomes, and stable public error codes.

#### Scenario: Private target appears in an internal exception
- **WHEN** target readiness or lease acquisition raises an exception containing the raw serial or configuration path
- **THEN** public terminal facts contain only the stable safe error code and bounded redacted message

#### Scenario: Managed evidence is scanned
- **WHEN** tests scan the database, events, reports, Replay, and exported bundles after fake authority paths
- **THEN** no raw serial, ADB argument, live handle representation, private fingerprint, or trusted configuration path is present

