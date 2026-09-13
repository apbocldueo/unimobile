# studio-benchmark-layered-acceptance Specification

## Purpose
Defines the reproducible no-device acceptance evidence that must connect Core Benchmark semantics, Studio durability, browser behavior, and installed-package boundaries before Stage 5 can begin fresh real Android acceptance.
## Requirements
### Requirement: Layered acceptance must publish one bounded causal evidence summary
Stage 5.6B SHALL produce a versioned, deterministic, machine-readable acceptance summary that identifies every required scenario and relates its safe Experiment, planned TaskRun, Core TaskRun, Replay, report, trajectory, manifest, bundle, and managed-artifact identities when those facts exist. The summary MUST record lifecycle/outcome facts, evidence origin, verification state, zero-side-effect canaries, commands or suite identities, and explicit claim limits; it MUST NOT include raw device targets, secrets, host paths, live objects, artifact bytes, or fabricated identities for unavailable evidence.

#### Scenario: Complete acceptance evidence
- **WHEN** all required no-device gates complete successfully
- **THEN** one bounded summary contains every required scenario, its causal identities and facts, `contract_fixture`/`fake_device` provenance, `realDeviceEvidence=false`, zero forbidden-effect canaries, and the statement that no real Android acceptance was executed

#### Scenario: Required scenario or causal fact is missing
- **WHEN** a required scenario is absent or a declared report, Replay, event, or artifact identity cannot be reconstructed from authoritative resources
- **THEN** layered acceptance fails rather than marking the gate complete or inventing a replacement fact

#### Scenario: Acceptance is repeated with the same immutable inputs
- **WHEN** the same fixture versions, seeds, and scenario definitions are run again in an isolated workspace
- **THEN** scenario ordering, semantic outcomes, causal relationships, and claim limits remain equal while runtime-generated opaque identities may differ

### Requirement: Actual Studio fake lifecycle acceptance must preserve independent outcomes
Layered acceptance SHALL drive representative Experiments through the actual Studio create, durable repository, scheduler, worker, Core Runtime, result, publication, and terminal boundaries using only explicit deterministic fake-device authority. It MUST distinguish service lifecycle, Agent status, Benchmark outcome, evaluation, publication availability, and evidence origin rather than reducing them to one success flag.

#### Scenario: Fake PASS completes the full durable chain
- **WHEN** a deterministic Agent completes a fake task and the evaluator passes
- **THEN** the Experiment and TaskRun complete once, Agent status is SUCCESS, Benchmark outcome is PASS, managed report/trajectory/bundle and native Replay are reconstructable, and all execution evidence remains fake

#### Scenario: Controlled fake FAIL keeps Agent success independent
- **WHEN** a deterministic Agent ends normally without satisfying the evaluator
- **THEN** Agent status is SUCCESS, Benchmark outcome is FAIL, INVALID count is zero, evaluation evidence is retained, and the service terminal reason remains completed

#### Scenario: Device context is invalid before actions
- **WHEN** exact fake authority succeeds but Core preflight detects an incompatible platform, locale, orientation, or required App
- **THEN** the TaskResult is INVALID with safe context-check facts and no initializer, Agent, model, evaluator, or action side effect

#### Scenario: Cancellation crosses accepted and active boundaries
- **WHEN** cancellation is requested before execution in one scenario and during cooperative fake execution in another
- **THEN** both scenarios preserve a legal durable transition sequence, stop new side effects at the next safe boundary, retain confirmed partial facts, and publish at most one terminal event

#### Scenario: Cleanup policy produces skipped work only in Core evidence
- **WHEN** the Core multi-task fixture stops a suite after a cleanup failure
- **THEN** executed evaluation evidence is preserved and remaining work is SKIPPED, while the Studio single-Task acceptance does not claim multi-Task Worker support

### Requirement: Service durability acceptance must prove event and recovery causality
Layered acceptance SHALL verify idempotent create and retry, commit-before-notify journal behavior, continuous bounded event backfill, named SSE cursor recovery, slow-client isolation, local ownership, conservative startup recovery, immutable results, publication recovery, and unique terminal facts against durable authoritative resources. Recovery MUST NOT replay uncertain Agent or device effects.

#### Scenario: Create response is lost and retried
- **WHEN** a client repeats the same create intent after an unknown response outcome
- **THEN** both responses resolve to one Experiment, one planned schedule, one private binding authority, and one accepted event

#### Scenario: SSE disconnects and reconnects
- **WHEN** a client disconnects after a committed sequence and reconnects with the last observed event identity
- **THEN** bounded backfill and named SSE continue without a gap or duplicate semantic transition and terminal drain completes from the durable high-water mark

#### Scenario: Slow subscriber coexists with worker progress
- **WHEN** one SSE client stops consuming while another client and the worker continue
- **THEN** the slow client is isolated or closed without blocking journal append, queries, publication, or the Experiment terminal transition

#### Scenario: Process stops during uncertain execution
- **WHEN** startup recovery finds work that may already have crossed an Agent or device side-effect boundary
- **THEN** it records an interruption and unique terminal facts without rerunning the Agent, initializer, evaluator, or device action

#### Scenario: Process stops after result before publication
- **WHEN** startup recovery finds a committed immutable TaskResult whose managed publication is incomplete
- **THEN** it retries only idempotent publication/finalization, preserves the existing result identity and cancellation facts, and does not rerun Core execution

### Requirement: Core capability and Studio cardinality evidence must remain separate
Stage 5.6B SHALL verify Core multi-Task, repeats, multi-Agent scheduling, deterministic seeds, TaskInstance reuse, independent outcomes, paired comparison, and fairness warnings with a fake deterministic experiment. In a separate Studio negative gate, preview/create and defensive execution preflight MUST reject any definition beyond `1 Agent × 1 Task × 1 repeat` as a whole before device/runtime effects. The acceptance summary MUST report these as distinct capabilities and MUST NOT infer Studio multi-cardinality support from Core results.

#### Scenario: Core executes the comparison matrix
- **WHEN** Core receives at least two Agents, two Tasks, and two repeats under a fixed Protocol
- **THEN** the complete deterministic schedule executes, comparable runs share the required TaskInstance identities, outcome counts and fairness warnings are preserved, paired scope is explicit, and no statistical-significance claim is made

#### Scenario: Studio preview exceeds its public limit
- **WHEN** Composer preview contains multiple Agents, selected Tasks, or repeats
- **THEN** it returns the stable unsupported-cardinality diagnostic before create, profile resolution, device, plugin, model, or Experiment persistence effects

#### Scenario: A durable snapshot is tampered beyond the defensive limit
- **WHEN** malformed or future durable input reaches execution with more than one Agent, TaskRun, selected Task, schedule entry, or repeat
- **THEN** worker preflight rejects the complete Experiment before target authority or Core execution and does not truncate to the first item

### Requirement: Installed-package acceptance must be repository independent
Layered acceptance SHALL build and install ZhiXing in an isolated environment and independently install a Benchmark Package distribution discoverable through the public Benchmark metadata entry point. From a working directory outside the repository, the installed Studio service MUST discover and compile that Package, create and complete an explicit fake-device Experiment, and serve its report, trajectory, manifest, bundle, Replay, and scoped GET/HEAD resources without importing repository source paths or invoking ADB, real devices, models, network services, or secrets.

#### Scenario: Installed external Package completes a fake Experiment
- **WHEN** an isolated installed Studio selects the externally distributed Package, one immutable Agent revision, one task, one repeat, and an injected fake profile
- **THEN** the actual durable Experiment reaches its expected terminal outcome and every declared managed resource is readable and integrity-consistent from installed code and packaged metadata

#### Scenario: Repository source is unavailable
- **WHEN** the isolated process runs from an unrelated directory with repository roots absent from import and Package lookup paths
- **THEN** Catalog discovery and execution still succeed without falling back to source-tree files or absolute locators

#### Scenario: Forbidden boundary canaries are installed
- **WHEN** ADB discovery, real-device construction, model/secret resolution, and external network calls are replaced by fail-fast canaries
- **THEN** installed layered acceptance completes with every forbidden counter equal to zero

### Requirement: Browser acceptance must use an actual fake Studio backend
Stage 5.6B SHALL complete a deterministic no-device browser journey against an actual Studio HTTP service configured with a safe fake profile, durable worker, publication, reporting, Replay, and artifact resources. The journey MUST traverse Catalog → Composer preview/create → Monitor → Report/Evidence → Replay → Export using authoritative links and preserve state across refresh and SSE disconnect. Static response fixtures MAY remain for bounded error-state presentation but MUST NOT be the only evidence for the end-to-end journey.

#### Scenario: Browser completes the fake product journey
- **WHEN** a user selects the acceptance Package, Agent revision, task, Protocol, and fake profile and explicitly creates an Experiment
- **THEN** the browser follows the returned identities through terminal Monitor, Report and selected TaskRun evidence, native Replay, and Export preparation/handoff without reconstructing resource links

#### Scenario: Browser refreshes and reconnects during execution
- **WHEN** the page refreshes or SSE disconnects after at least one durable event
- **THEN** the route, query reconstruction, backfill, and reconnect recover the same Experiment and TaskRun facts without duplicating execution or losing confirmed events

#### Scenario: Browser reviews unavailable and bounded evidence
- **WHEN** report, evidence, Replay, or export resources are pending, missing, corrupt, hidden, truncated, oversized, or download-only
- **THEN** each component preserves its local truthful state, unsafe content remains inert, other authoritative facts stay visible, and the UI does not claim a completed download or fresh real Android execution

### Requirement: No-device acceptance must not strengthen product claims
Every 5.6B artifact and human-readable handoff SHALL identify all execution as no-device/fake evidence, preserve `realDeviceEvidence=false`, and state that Stage 5.6C-1/2 remain required for fresh real Android service/browser proof. Acceptance MUST NOT change Worker cardinality, runtime semantics, public canonical identities, legacy BenchmarkTask JSON, AgentConfig/AgentGraph independence, or claim PostgreSQL, distributed ownership, third-party sandboxing, broad device compatibility, model quality, automatic diagnosis, or statistical significance.

#### Scenario: Fake acceptance passes every gate
- **WHEN** the complete 5.6B matrix passes
- **THEN** the milestone is described only as layered no-device acceptance and the next planned change remains real Android service acceptance `validate-studio-benchmark-android-service-5-6c1`

#### Scenario: Presentation resembles a real Android result
- **WHEN** a fixture contains Android-shaped screenshots, profile labels, task names, URLs, or historical Replay facts
- **THEN** neither the acceptance summary nor documentation upgrades the environment to real Android without fresh source-execution facts

