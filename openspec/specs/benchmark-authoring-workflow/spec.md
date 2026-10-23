# benchmark-authoring-workflow Specification

## Purpose
TBD - created by archiving change complete-benchmark-evaluation-and-reporting. Update Purpose after archive.
## Requirements
### Requirement: Benchmark Package scaffold
The installed CLI SHALL provide a Benchmark Package scaffold command with at least `minimal`, `dynamic-task`, and `composite-evaluation` templates. Generated packages MUST follow the documented `benchmarks/<package>/` content layout, use valid relative resource references, and pass structural validation without requiring a device.

#### Scenario: Create minimal package
- **WHEN** an author initializes a new package from the minimal template
- **THEN** the command creates a manifest, task content, and concise README that validate without executing plugins

#### Scenario: Refuse destructive overwrite
- **WHEN** the requested destination already contains files
- **THEN** the scaffold command refuses to overwrite them unless the caller uses an explicit supported replacement mode

### Requirement: Side-effect-free Benchmark dry-run
The system SHALL provide a dry-run that compiles the Benchmark Package or JSON, compiles and binds selected Agent definitions, resolves logical metadata and declared dependencies, derives the execution schedule, and checks protocol fairness, budgets, and output layout. Dry-run MUST NOT connect to a device, invoke a model, execute initializer or evaluator plugins, mutate an environment, or create runtime result claims.

#### Scenario: Dynamic task without fixture materialization
- **WHEN** a dynamic task requires an initializer value unavailable during dry-run
- **THEN** dry-run marks materialization-dependent checks as unverified and still reports the deterministic schedule template

#### Scenario: Fairness mismatch
- **WHEN** a multi-Agent protocol disables TaskInstance reuse or otherwise prevents paired comparison
- **THEN** dry-run succeeds only according to the protocol contract and emits an explicit fairness warning

### Requirement: Benchmark Contract Test Kit
The system SHALL provide a package-focused Contract Test Kit that invokes only explicit fake fixtures for task initializer, environment adapter, and evaluator references. Each fixture SHALL be registered through a typed descriptor that identifies its logical contract kind and stable fixture identity; the kit MUST NOT resolve or execute Package-supplied code merely because a logical plugin reference appears in a Benchmark definition. For every bounded reference occurrence, the kit SHALL return a stable case identity, the checks that executed, safe field-addressable diagnostics, and exactly one `passed`, `failed`, or `skipped` status. It SHALL test role-level input and output contracts, deterministic seeded behavior where the fixture promises determinism, fresh-scope observable isolation, evaluator evidence safety, environment lifecycle compatibility, and JSON-serializable bounded output without using a real device by default.

The kit MUST derive case-local seeds deterministically from the caller seed and stable case identity so case ordering does not change fixture facts. A case SHALL be `passed` only when a matching explicit fixture executed every required check successfully, `failed` when an executed fixture violates its contract or safety boundary, and `skipped` when no matching safe fixture is registered or the selected profile intentionally withholds a required capability. Missing fixture coverage MUST NOT be reported as passed, while a skipped case MUST remain distinct from a contract failure. Aggregate output SHALL expose passed, failed, and skipped counts plus separate completeness and executed-check-success facts; it MUST NOT collapse a mixed or incomplete run into an unqualified success.

Default Contract Tests MUST receive no device, model, network, secret, Agent-execution, Experiment, output-publication, or real-runtime service. Public results, diagnostics, and logs MUST reject or redact secret-shaped values, host paths, device serials, live objects, and private capabilities. A trusted server or test process MAY register fake fixtures, but in-process fixture execution MUST be identified truthfully as trusted code rather than a process-sandbox guarantee. Real-device profiles remain separate evidence and MUST NOT strengthen or replace the default fake-fixture result.

#### Scenario: Deterministic initializer contract
- **WHEN** an initializer fixture declares seeded determinism and the kit invokes fresh instances twice for the same case-local seed and parameters
- **THEN** the safely serialized values are equivalent and the case records deterministic and isolation checks as passed

#### Scenario: Non-deterministic evaluator contract
- **WHEN** an evaluator fixture declares seeded determinism but returns different normalized evidence for the same case-local seed
- **THEN** the evaluator case is failed with a safe field-addressable determinism diagnostic rather than accepted as an evaluator result

#### Scenario: Unsafe evaluator evidence
- **WHEN** an evaluator fixture returns a secret, host absolute path, raw device serial, unsupported live object, or unbounded evidence
- **THEN** the case is failed with bounded safe diagnostics and the unsafe value is absent from serialized output and logs

#### Scenario: Environment lifecycle compatibility
- **WHEN** reset, setup, and cleanup references have matching fake fixtures in the selected profile
- **THEN** the kit checks each declared phase through fresh fake scopes in stable declaration order and reports each occurrence independently without touching a device

#### Scenario: Explicit fixture is unavailable
- **WHEN** a valid logical initializer, environment, or evaluator reference has no matching fixture in the selected profile
- **THEN** the occurrence is skipped with a stable coverage reason and is not counted as passed or failed

#### Scenario: Observable fixture state leaks between scopes
- **WHEN** repeated fresh-scope invocations reveal shared mutable state or order-dependent output for an isolation-promising fixture
- **THEN** the case is failed with an isolation diagnostic while other bounded cases continue

#### Scenario: Result capacity is exceeded
- **WHEN** the Package would require more Contract Test cases or diagnostics than the public bound
- **THEN** the kit rejects before unbounded allocation or returns an explicitly bounded result according to the applicable boundary and never silently drops cases while claiming completeness

#### Scenario: Default profile has no runtime capability
- **WHEN** default Contract Tests execute with fail-fast canaries installed at device, model, network, secret, Agent execution, Experiment, and publication boundaries
- **THEN** every canary remains untouched while only registered fake fixtures produce bounded evidence

#### Scenario: Trusted fixture is not a sandbox claim
- **WHEN** a server or third-party test process registers an in-process fake fixture
- **THEN** the result identifies the trusted fixture profile and `processSandbox=false` rather than claiming arbitrary code containment

#### Scenario: Explicit real-device extension
- **WHEN** a package author separately opts into a documented real-device profile
- **THEN** that profile remains outside the default Contract Test result and is reported as additional evidence without changing the fake-fixture facts

#### Scenario: Existing public CLI remains compatible
- **WHEN** an existing generated Package invokes the public `benchmark contract-test` CLI without selecting a new Studio profile
- **THEN** the command retains a deterministic declaration-only compatibility path, labels its evidence level truthfully, and preserves its documented exit behavior without claiming real plugin execution

### Requirement: Authoring documentation and examples
The project SHALL document the distinction between package input, framework code, reusable Benchmark plugins, examples, tests, import tooling, and `temp/benchmark-runs` output. Documentation SHALL include scaffold, validate, dry-run, contract-test, run, report, and comparison commands with expected observations, and examples SHALL remain small teaching assets rather than formal benchmark datasets.

#### Scenario: Follow the authoring path
- **WHEN** a developer follows the documented minimal-package workflow in a clean project environment
- **THEN** the generated package validates, dry-runs, and passes the default fake-fixture contract checks

#### Scenario: Inspect permanent architecture
- **WHEN** a contributor reads the Benchmark architecture document
- **THEN** each target folder has a single stated responsibility and runtime output is explicitly forbidden as package input

