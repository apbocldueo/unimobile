# benchmark-reporting Specification

## Purpose
TBD - created by archiving change complete-benchmark-evaluation-and-reporting. Update Purpose after archive.
## Requirements
### Requirement: Versioned durable Benchmark results
The system SHALL persist versioned, loadable task-run and experiment result documents derived from immutable runtime facts. A task-run report SHALL correspond to one `BenchmarkTaskResult`; an experiment report SHALL correspond to one `BenchmarkSuiteResult` and MAY contain multiple tasks, agents, and repeats without duplicating live runtime services.

#### Scenario: Persist and reload an experiment
- **WHEN** a suite completes and its result is written
- **THEN** a clean process can load the versioned document into an equivalent typed result without device or plugin access

#### Scenario: Unknown future schema version
- **WHEN** a loader receives a result schema version it does not support
- **THEN** it fails with a structured compatibility diagnostic instead of silently dropping fields

### Requirement: Honest metrics aggregation
Experiment reporting SHALL keep `PASS`, `FAIL`, `INVALID`, and `SKIPPED` counts separate and SHALL expose every denominator used for rates. It SHALL support task-level and Agent-level micro and macro success rates, duration mean and median, sample variance only when at least two eligible observations exist, and a documented binomial uncertainty interval for eligible pass/fail outcomes.

#### Scenario: Invalid run excluded from success denominator
- **WHEN** an Agent has one PASS, one FAIL, and one INVALID result
- **THEN** the success rate denominator is two, the INVALID count remains visible, and the report does not convert INVALID into FAIL

#### Scenario: Single observation variance
- **WHEN** only one eligible duration is available
- **THEN** the report marks sample variance unavailable rather than returning zero

#### Scenario: Micro and macro differ
- **WHEN** task groups have unequal numbers of eligible runs
- **THEN** the report exposes both calculations and their explicit grouping denominators

### Requirement: Fair multi-Agent comparison
Comparisons SHALL identify each Agent by safe stable identity and SHALL label results as paired only when the compared runs share the same BenchmarkPlan task, TaskInstance identity, repeat conditions, and applicable protocol settings. INVALID and SKIPPED outcomes MUST NOT be treated as Agent losses, and the report MUST NOT claim statistical significance without a declared method and sufficient eligible samples.

#### Scenario: Paired Agent comparison
- **WHEN** two Agents run the same reused TaskInstance under the same protocol
- **THEN** the report provides a paired outcome comparison and records the matched sample count

#### Scenario: Non-paired task instances
- **WHEN** two Agent results use different TaskInstance identities
- **THEN** the report labels the comparison unpaired and does not present it as a controlled head-to-head result

### Requirement: Unified downloadable trajectory
The system SHALL produce a versioned trajectory that combines Benchmark materialization, reset, setup, evaluator pre-hook, Agent execution, evaluation, and cleanup with nested AgentGraph events, observations, and actions. Ordering SHALL follow lifecycle nesting and per-source sequence information rather than a naive global timestamp sort.

#### Scenario: Agent event nesting
- **WHEN** an AgentGraph emits node events during the Benchmark Agent phase
- **THEN** the exported trajectory nests or correlates those events under the corresponding task run and Agent lifecycle span

#### Scenario: Controlled failure localization
- **WHEN** a task fails during evaluation after successful Agent execution
- **THEN** a reader can distinguish the successful Agent phase from the failed evaluation phase and inspect their respective safe evidence

### Requirement: Integrity-checked safe artifact bundle
Each experiment output SHALL use a stable relative layout containing an experiment manifest and report plus per-run result, report, trajectory, and artifact references. A downloadable bundle SHALL include relative paths and content hashes, reject symlinks and path traversal, and apply one recursive sanitizer to manifests, nested action results, error details, evidence, reports, and trajectories.

#### Scenario: Nested raw device serial
- **WHEN** a nested action result or error detail contains a raw Android serial
- **THEN** the exported files and bundle contain only the approved safe device provenance representation

#### Scenario: Artifact escapes experiment root
- **WHEN** an artifact reference resolves outside the experiment output root or through a symlink
- **THEN** bundle creation fails safely and identifies the logical reference without copying the target

#### Scenario: Bundle integrity verification
- **WHEN** a consumer verifies an unchanged bundle
- **THEN** every declared member hash matches; modifying a member causes verification to fail

