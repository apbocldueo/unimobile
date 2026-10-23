# component-invocation-protocol Specification

## Purpose
TBD - created by archiving change define-zhixing-component-protocol. Update Purpose after archive.
## Requirements
### Requirement: Generic synchronous component invocation
The system SHALL provide a public generic component protocol whose canonical entry point is `invoke(input, runtime) -> output`. The protocol MUST express input and output types and MUST define synchronous V1 behavior without returning conditional awaitables or streams. Structural conformance SHALL remain available for explicitly supplied local SDK objects, while a component represented as a formal reusable `ComponentSpec` MUST additionally satisfy its declared authoring base/decorator, NodeContract, configuration, and runtime type requirements.

#### Scenario: Implement an external component
- **WHEN** a Python user explicitly supplies an object with a compatible typed `invoke` method without inheriting a ZhiXing base class
- **THEN** the object satisfies the structural component contract for that local construction path but is not implicitly treated as a discoverable formal component

#### Scenario: Implement a formal reusable component
- **WHEN** an author creates a ComponentSpec for an ABC subclass or decorated typed callable
- **THEN** protocol-aware construction validates both structural invocation and the formal declaration before accepting it

#### Scenario: Invoke synchronously
- **WHEN** an orchestrator calls a V1 component with its role input and `RuntimeContext`
- **THEN** the call returns the declared role output directly rather than an awaitable or iterator

### Requirement: Complete role protocol coverage
The public component API SHALL define role-specific invocation protocols for Perception, Planner, Reasoning, Memory, Verifier, Grounder, LLM, Device, ActionExecutor, BenchmarkInitializer, and Evaluator. Each role MUST bind a documented typed input and output rather than exposing `Dict[str, Any] -> Any` as its primary contract. The API MUST distinguish the six core AgentGraph roles from extension nodes, runtime services, and BenchmarkTask components; the eleven invocation protocols MUST NOT redefine the fixed six-role AgentGraph terminology.

#### Scenario: Inspect the public role catalog
- **WHEN** a user imports the component protocol catalog
- **THEN** all eleven invocation protocols are present with declared input and output types and with category metadata that identifies their architectural layer

#### Scenario: Inspect AgentGraph core roles
- **WHEN** a user inspects the six core AgentGraph authoring bases
- **THEN** only Perception, Planner, Reasoning, Memory, ActionExecutor, and Verifier are classified as core roles

#### Scenario: Type a component pipeline
- **WHEN** a user connects a role output to the next role input according to the documented Agent flow
- **THEN** the public annotations expose mismatched connections to static tooling without requiring plugin execution

### Requirement: Canonical Agent role mappings
Perception SHALL accept a device observation and return `PerceptionResult`; Planner SHALL accept typed planning input and return the canonical plan result; Reasoning SHALL accept `ReasoningInput` and return `Action`; Verifier SHALL accept verification input and return verification result; Grounder SHALL accept grounding input and return a typed grounding result.

#### Scenario: Make one typed Agent decision
- **WHEN** an orchestrator passes a task, plan, perception, and memory context through the declared Agent role inputs
- **THEN** the Reasoning role returns one canonical `Action` that can be passed to ActionExecutor

#### Scenario: Ground a target
- **WHEN** a Grounder resolves a target description against a device observation
- **THEN** it returns named coordinates and optional confidence/metadata rather than an undocumented tuple

### Requirement: Canonical infrastructure role mappings
LLM SHALL accept a typed request and return text plus typed usage/metadata; Device SHALL accept documented tagged device requests and return typed device results; ActionExecutor SHALL accept an Action execution input and return `ActionResult`. Action execution MUST remain separate from Reasoning and from the Device's platform primitives.

#### Scenario: Execute a canonical action
- **WHEN** ActionExecutor receives a valid `Action` and a runtime containing a compatible Device
- **THEN** it maps the action to Device primitives and returns a typed result without requiring Reasoning to access the Device

#### Scenario: Record an LLM response
- **WHEN** an LLM component completes a request with provider usage data
- **THEN** the invocation result carries response text and normalized usage/metadata without requiring a second global return channel

### Requirement: Canonical stateful and Benchmark role mappings
Memory SHALL use documented tagged input/result variants for its shipped append, context read, reset, knowledge load, and experience retrieval behaviors. BenchmarkInitializer SHALL cover distinct task-parameter and environment-initialization variants without conflating generated values with environment success. Evaluator SHALL accept typed evaluation input and return Evaluation Result V2 with an explicit execution status, pass decision, optional normalized score, reason, duration, usage availability, typed safe evidence, and safe metadata. Existing documented evaluator result objects SHALL remain usable through an explicit compatibility adapter rather than changing the canonical V2 type.

#### Scenario: Read and mutate Memory
- **WHEN** an orchestrator invokes Memory with append, read, or reset variants
- **THEN** each operation returns the documented result variant and retains the current stateful semantics

#### Scenario: Initialize a Benchmark task
- **WHEN** BenchmarkInitializer receives a task-parameter input or environment input
- **THEN** it returns the matching generated-value or environment-status result and rejects an incompatible variant deterministically

#### Scenario: Invoke a V2 Evaluator
- **WHEN** an Evaluator receives a valid typed evaluation input
- **THEN** it returns the canonical V2 result directly and its evidence satisfies the safe evidence contract

#### Scenario: Invoke a legacy Evaluator
- **WHEN** the resolver identifies a supported legacy evaluator implementation
- **THEN** the compatibility adapter normalizes its documented output into V2 without changing the evaluator implementation or inventing evidence

### Requirement: Side-effect-free public component namespace
The protocols and data models SHALL be importable from a documented `zhixing.components` namespace. Importing that namespace MUST NOT change the deliberately small `zhixing` root exports and MUST NOT autodiscover plugins, import optional model/vision/device stacks, access devices or networks, read secrets, or create runtime files.

#### Scenario: Import with base dependencies
- **WHEN** a clean process with only the base distribution imports `zhixing.components`
- **THEN** all public protocol/model symbols are available without optional imports or observable runtime side effects

#### Scenario: Inspect root exports
- **WHEN** the component API is installed and a caller inspects `zhixing.__all__`
- **THEN** the existing stable root export list remains unchanged

### Requirement: Stable canonical object identity
The component namespace MUST re-export existing canonical Action, perception, plan, memory-fragment, and verification classes where their semantics are retained. It MUST NOT create public look-alike classes that fail identity checks against objects returned by current built-ins.

#### Scenario: Compare an existing Action
- **WHEN** a built-in Reasoning component returns the existing canonical `Action`
- **THEN** the value is accepted by the new Reasoning and ActionExecutor boundaries without copying it into an incompatible Action class

