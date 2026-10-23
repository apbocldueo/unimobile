# benchmark-evaluation-v2 Specification

## Purpose
TBD - created by archiving change complete-benchmark-evaluation-and-reporting. Update Purpose after archive.
## Requirements
### Requirement: Typed Evaluation Result V2
The system SHALL define a versioned, JSON-compatible evaluator result containing evaluator identity, execution status, pass decision, optional normalized score, reason, duration, usage availability, typed evidence references, and safe metadata. Execution failure, invalid configuration, and a valid negative task judgment MUST remain distinguishable.

#### Scenario: Successful positive evaluation
- **WHEN** a leaf evaluator completes and establishes that its criterion passed
- **THEN** it returns a V2 result with completed status, `passed: true`, and the evidence supporting that decision

#### Scenario: Evaluator infrastructure failure
- **WHEN** a leaf evaluator cannot execute because its dependency or observation source failed
- **THEN** it returns an error or invalid status rather than converting the infrastructure failure into a normal failed criterion

#### Scenario: Usage unavailable
- **WHEN** an evaluator provides no token or model usage information
- **THEN** the result records usage as unavailable rather than reporting a fabricated zero

### Requirement: Unified safe evidence contract
Evaluation evidence SHALL use typed, namespaced evidence kinds including `system.state`, `visual.image`, `text.match`, `trajectory.sequence`, `artifact.file`, and open `custom.*` kinds. Evidence MUST contain safe values or artifact references and MUST NOT embed secrets, absolute paths, raw device serials, live runtime objects, or unbounded binary payloads.

#### Scenario: Visual evaluator evidence
- **WHEN** a visual evaluator uses a screenshot to make a decision
- **THEN** its result references a sanitized artifact and records the visual evidence kind without embedding the live image object

#### Scenario: Custom evaluator evidence
- **WHEN** an external evaluator emits a namespaced `custom.vendor.metric` evidence item with JSON-compatible safe fields
- **THEN** the result preserves the item without requiring a kernel change

#### Scenario: Unsafe evidence value
- **WHEN** evidence contains a secret-like field, absolute host path, raw device identifier, or non-serializable object
- **THEN** safe export rejects or redacts the unsafe value and emits a structured diagnostic

### Requirement: Complete recursive evaluation result
Every executed leaf and composite node SHALL produce a path-addressable result. The tree result SHALL preserve child order, node decision, score when applicable, duration, reason, evidence references, and explicit `SKIPPED` children for branches not executed by declared short-circuit behavior.

#### Scenario: Failed AND child
- **WHEN** an AND node evaluates one passing child and one failing child
- **THEN** both child results and the composite failure rationale remain available

#### Scenario: OR short circuit
- **WHEN** an OR node passes and its declared behavior skips later children
- **THEN** the result contains the evaluated child and explicit `SKIPPED` results for the unevaluated branches

### Requirement: Threshold and weighted composition
The evaluator tree SHALL support `THRESHOLD` nodes with exactly one explicit threshold mode, `min_passed` or `min_ratio`, and `WEIGHTED` nodes with positive finite child weights and an explicit normalized `pass_threshold`. These nodes SHALL evaluate all children by default so their aggregate decision retains complete evidence.

#### Scenario: Minimum-count threshold passes
- **WHEN** a THRESHOLD node declares `min_passed: 2` and two of three completed children pass
- **THEN** the node passes and records the passed count, eligible count, and configured threshold

#### Scenario: Weighted score fails
- **WHEN** weighted child scores produce a normalized aggregate below `pass_threshold`
- **THEN** the node fails while preserving every child score, weight, and contribution

#### Scenario: Invalid weighted configuration
- **WHEN** a weight is non-finite, zero, negative, or the pass threshold is outside the normalized range
- **THEN** contract validation fails before evaluator execution

### Requirement: Legacy evaluator result normalization
Legacy evaluator outputs SHALL be accepted only through an explicit compatibility adapter that converts known legacy result and boolean shapes into V2. The adapter MUST preserve available reason and evidence, MUST NOT invent evidence, and SHALL map a legacy boolean to score `1.0` or `0.0`.

#### Scenario: Legacy structured result
- **WHEN** a legacy evaluator returns its documented result object
- **THEN** the adapter produces an equivalent V2 decision and preserves all safely representable fields

#### Scenario: Unsupported legacy output
- **WHEN** a legacy evaluator returns an unknown object shape
- **THEN** normalization produces a typed compatibility error rather than relying on object truthiness

