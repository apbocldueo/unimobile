# legacy-component-adapters Specification

## Purpose
TBD - created by archiving change define-zhixing-component-protocol. Update Purpose after archive.
## Requirements
### Requirement: Legacy components adapt to canonical invocation
The system SHALL provide role-specific adapters that expose canonical `invoke(input, runtime)` behavior for existing Perception `perceive`, Planner `make_plan`, Reasoning `think`, Memory lifecycle, Verifier `verify`, Grounder `ground`, LLM `generate`, Device primitive, Benchmark initializer `generate`/`execute`, and Evaluator `evaluate` implementations. ActionExecutor compatibility SHALL cover the current Action-to-Device behavior even though no legacy ActionExecutor class exists.

#### Scenario: Invoke an unchanged built-in
- **WHEN** an existing built-in component implements only its current role method
- **THEN** the corresponding adapter accepts the canonical typed input and returns the canonical typed output without modifying the built-in class

#### Scenario: Cover every requested role
- **WHEN** the adapter catalog is inspected or tested with lightweight representative components
- **THEN** all eleven public roles have a documented legacy mapping or, for ActionExecutor, a compatibility implementation matching current Runner behavior

### Requirement: Invocation-native components adapt to the current engine
The system SHALL provide reverse role adapters for current Agent and Benchmark engine entry points so a component that implements only canonical `invoke` can be exercised by existing orchestration code without changing Agent YAML or Benchmark JSON formats.

#### Scenario: Use a new Perception in the current Agent
- **WHEN** a Python component implements canonical Perception `invoke` but not `perceive`
- **THEN** the reverse adapter presents a compatible `perceive` method and returns the same canonical `PerceptionResult`

#### Scenario: Use a new Evaluator in the current Benchmark pipeline
- **WHEN** an invocation-native Evaluator is adapted for the existing evaluator entry point
- **THEN** `evaluate(context)` returns the legacy-compatible evaluation result while preserving the canonical result meaning

### Requirement: Deterministic Reasoning return normalization
The legacy Reasoning adapter SHALL accept both a canonical legacy `Action` return and the currently shipped `(Action, raw_response)` tuple. Canonical invocation MUST return `Action`; raw response information MUST be preserved under one documented reserved metadata key or a sanitized event. The reverse adapter MUST reconstruct the tuple shape expected by the current Agent engine.

#### Scenario: Adapt UniversalReason
- **WHEN** the adapter invokes the current UniversalReason implementation and it returns `(action, response)`
- **THEN** canonical callers receive the same Action with the response preserved according to the documented compatibility rule

#### Scenario: Adapt an Action-only legacy reasoner
- **WHEN** a legacy Reasoning implementation returns only Action
- **THEN** canonical invocation succeeds and the reverse tuple uses an empty raw response rather than failing tuple unpacking

### Requirement: Explicit stateful and tagged-operation mappings
Memory, Device, and BenchmarkInitializer adapters MUST dispatch only documented tagged input variants to their matching legacy operations. They MUST reject incompatible variants with a deterministic protocol/input error rather than guessing from arbitrary dictionary keys.

#### Scenario: Reset legacy Memory
- **WHEN** canonical Memory receives the reset variant through a legacy adapter
- **THEN** exactly the legacy `clear` behavior runs and a reset result is returned

#### Scenario: Reject initializer variant mismatch
- **WHEN** a task-parameter generator receives an environment-initialization variant
- **THEN** the adapter reports the role and expected variant without executing either legacy operation

### Requirement: Central role-aware adaptation and validation
The system SHALL provide a central adaptation/validation function that accepts an expected role, an instance, and a target interface. It MUST preserve already-conforming instances, select an explicit role adapter when compatible, and otherwise raise a sanitized `ComponentProtocolError` identifying the role, class name, expected entry point, and safe discovered method names.

#### Scenario: Component already conforms
- **WHEN** an instance already implements the target role's canonical invocation contract
- **THEN** adaptation returns it without double-wrapping or triggering component execution

#### Scenario: Component has no compatible entry point
- **WHEN** an object implements neither canonical invoke nor the expected legacy role methods
- **THEN** adaptation fails before the run with a deterministic diagnostic that does not include object repr, configuration secrets, or prompt content

### Requirement: Execution failures remain distinct from conformance failures
Adapters MUST NOT convert exceptions raised by a conforming component's business execution into protocol-shape errors. When an adapter adds context, it MUST preserve exception chaining and sanitize messages that cross public diagnostics or event boundaries.

#### Scenario: Device fails during action execution
- **WHEN** an adapted Device raises while performing a valid request
- **THEN** the failure is represented or propagated as an execution failure rather than claiming the Device lacks the protocol

### Requirement: Existing configuration workflows remain compatible
Adding protocols and adapters MUST NOT remove, rename, or change the meaning of existing plugin registry names, Agent YAML fields, Benchmark JSON fields, or legacy role methods. Existing configuration contract validation and representative current factory/pipeline construction MUST continue to work.

#### Scenario: Validate retained configurations
- **WHEN** the existing Agent YAML and canonical Benchmark JSON fixtures are validated after the component protocol is installed
- **THEN** they produce the same `AgentConfig` and `BenchmarkSuite` contract objects without requiring Python component code

#### Scenario: Build from an existing plugin name
- **WHEN** a current YAML component reference resolves through the registry
- **THEN** it resolves the same plugin class and may be adapted after instantiation without changing its registered identity

### Requirement: Adapter imports preserve optional dependency isolation
Importing the adapter catalog or validating a lightweight instance MUST NOT autodiscover all plugins or import optional OpenAI, vision, Harmony, or Benchmark-only stacks. Missing optional dependencies MUST remain isolated to discovery/instantiation of the component that requires them.

#### Scenario: Import adapters in a base installation
- **WHEN** a clean base environment imports every public adapter and error type
- **THEN** import succeeds without loading optional provider, vision, Harmony, or Benchmark-only modules

