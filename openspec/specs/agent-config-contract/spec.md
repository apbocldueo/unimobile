# agent-config-contract Specification

## Purpose
TBD - created by archiving change define-config-contracts. Update Purpose after archive.
## Requirements
### Requirement: Canonical AgentConfig V1 envelope
The system SHALL define a strict `AgentConfig` V1 model for Agent YAML with required `schema_version`, `agent_type`, `device`, and `agent.components` fields. The `schema_version` value MUST identify version 1, and unknown fields outside explicitly extensible `params` mappings MUST be rejected.

#### Scenario: Valid V1 Agent YAML
- **WHEN** a YAML document contains `schema_version: 1`, a non-empty registered-style `agent_type`, a top-level device reference, and valid Agent components
- **THEN** structural validation succeeds and returns a canonical `AgentConfig` value

#### Scenario: Missing or unsupported schema version
- **WHEN** an Agent YAML document omits `schema_version` or supplies a value other than version 1
- **THEN** validation fails with an error located at `schema_version`

#### Scenario: Unknown envelope field
- **WHEN** an Agent YAML document includes an unrecognized field outside an explicitly extensible `params` mapping
- **THEN** validation fails with an error containing the exact field path

### Requirement: Top-level device definition
The `AgentConfig` contract SHALL require device selection through a top-level `device` object containing a non-empty `name` and an optional `params` mapping. The contract MUST reject `agent.components.action` as a device definition.

#### Scenario: Top-level Android or Harmony device
- **WHEN** the document defines `device.name` and optional device parameters at the top level
- **THEN** structural validation accepts the device reference without connecting to the device

#### Scenario: Legacy action component
- **WHEN** the document defines `agent.components.action`
- **THEN** validation fails and directs the caller to use the top-level `device` field

### Requirement: Typed Agent component slots
The `AgentConfig` contract SHALL require `perception`, `reasoning`, and `memory` slots and SHALL permit optional `planner`, `verifier`, and `grounder` slots. A component reference MUST contain a non-empty `name`, an optional open `params` mapping, and an optional LLM reference. Only `perception` MAY be either one component reference or a non-empty ordered list of component references; all other slots MUST contain one component reference.

#### Scenario: Single perception component
- **WHEN** `agent.components.perception` contains one valid component reference
- **THEN** structural validation succeeds

#### Scenario: Ordered perception fallback list
- **WHEN** `agent.components.perception` contains a non-empty list of valid component references
- **THEN** validation preserves list order for runtime fallback behavior

#### Scenario: Multiple reasoning components
- **WHEN** `agent.components.reasoning` is a list
- **THEN** validation fails because the runtime consumes reasoning as a single component

#### Scenario: Missing core component
- **WHEN** perception, reasoning, or memory is absent
- **THEN** validation fails before Agent construction with the missing slot path

### Requirement: LLM reference and fallback semantics
The contract SHALL represent an LLM reference with a non-empty `name` and optional open `params` mapping. Components that require an LLM MUST resolve either a component-local `llm` reference or `global_config.default_llm`; validation MUST permit unresolved secret placeholders such as `${api_key}` while preserving them verbatim.

#### Scenario: Component-local LLM
- **WHEN** an LLM-dependent component contains a structurally valid local `llm` reference
- **THEN** semantic validation treats that component as having an LLM configuration

#### Scenario: Global default LLM
- **WHEN** an LLM-dependent component has no local `llm` and `global_config.default_llm` is valid
- **THEN** semantic validation applies the global default without mutating the original component parameters

#### Scenario: Missing required LLM
- **WHEN** a configured component is known to require an LLM and neither local nor global LLM configuration exists
- **THEN** semantic validation fails at that component slot

#### Scenario: Secret placeholder is preserved
- **WHEN** an LLM parameter contains `${api_key}` or another syntactically valid placeholder
- **THEN** contract validation succeeds without resolving or logging the secret value

### Requirement: Agent strategy compatibility validation
Semantic validation SHALL enforce strategy-specific component dependencies without instantiating the Agent. `multi_agent` MUST have a planner when manager-per-step behavior is enabled, `uground_agent` MUST have a grounder, and any configured planner MUST have memory available for plan persistence.

#### Scenario: Valid MultiAgent strategy
- **WHEN** `agent_type` is `multi_agent`, manager-per-step behavior is enabled, and planner, perception, reasoning, and memory are configured
- **THEN** semantic validation succeeds

#### Scenario: MultiAgent missing planner
- **WHEN** `agent_type` is `multi_agent`, manager-per-step behavior is enabled, and planner is absent
- **THEN** semantic validation fails with a strategy compatibility error

#### Scenario: UGroundAgent missing grounder
- **WHEN** `agent_type` is `uground_agent` and the grounder slot is absent
- **THEN** semantic validation fails before Agent construction

### Requirement: Registry-backed Agent resolution
The system SHALL provide an explicit registry-backed validation level that verifies `agent_type`, device, component, and LLM names against their required namespaces. Registry validation MUST NOT instantiate a device, component, Agent, or LLM and MUST report plugin discovery failures separately from unknown configured names.

#### Scenario: All configured names resolve
- **WHEN** every configured name exists in its required plugin namespace
- **THEN** registry validation succeeds without device access, network access, or model calls

#### Scenario: Component exists in the wrong namespace
- **WHEN** a configured name exists in the registry but not under the namespace required by its component slot
- **THEN** validation fails at that slot and identifies the required namespace

#### Scenario: Plugin module failed discovery
- **WHEN** registry bootstrap could not import a module needed to establish the catalog
- **THEN** validation reports the discovery failure distinctly rather than claiming that the configured component is merely unknown

### Requirement: Deterministic Agent contract output
Successful validation SHALL produce a deterministic, JSON-compatible canonical mapping suitable for `AgentFactory` input and JSON Schema generation. Structural and semantic validation MUST be free of device, filesystem-artifact, network, and model-call side effects.

#### Scenario: Canonical model output
- **WHEN** a valid Agent YAML document is loaded and validated
- **THEN** the resulting canonical mapping preserves component order, open parameter values, and secret placeholders while applying documented defaults

#### Scenario: Validation in an isolated test
- **WHEN** structural and semantic validation run in a process without ADB, HDC, model credentials, or optional model dependencies
- **THEN** validation completes without attempting external operations

### Requirement: AgentConfig V1 到 AgentGraph 的兼容编译边界
系统 SHALL 在不改变现有 AgentConfig V1 envelope、slot 校验、canonical mapping 和旧 AgentFactory 行为的前提下，为已具有版本化且通过行为对照测试的 Agent 类型提供显式 AgentGraph compiler。Compiler MUST 保留组件参数、LLM 引用、fallback 顺序、strategy 参数和可选节点，并 SHALL 使用模板声明的稳定 ActionExecutor/运行服务引用；编译 MUST 在配置与 registry validation 之后、组件实例化和设备连接之前完成。

#### Scenario: 受支持 ModularAgent 配置
- **WHEN** 一个有效 `modular_agent` AgentConfig V1 通过结构、语义和 registry validation 后被请求转换
- **THEN** 系统生成可验证和可 canonicalize 的 AgentGraph，同时保持原 canonical AgentConfig 不变

#### Scenario: 受支持 UGroundAgent 配置
- **WHEN** UGround template 已通过 parity 且配置具有合法 grounder 及依赖组件
- **THEN** compiler 使用该模板生成显式 Grounder 节点和类型化连接，而不是把 grounding 隐藏在 Reasoning

#### Scenario: 原有 YAML 执行路径仍可用
- **WHEN** 调用方不请求 AgentGraph 编译或配置的旧 Agent 类型尚未支持编译
- **THEN** 原 AgentConfig 仍可按既有 AgentFactory/Runner 路径运行

#### Scenario: 未支持架构不伪造图
- **WHEN** 任意旧 agent_type 尚未有已验证模板却被请求转换
- **THEN** compiler 返回明确不支持诊断，而不是猜测或生成语义不完整的 AgentGraph

### Requirement: Agent 与 Benchmark 配置继续正交
AgentConfig V1 到 AgentGraph 的编译 SHALL 只描述 Agent 架构和组件绑定。Compiler MUST NOT 读取或内嵌 BenchmarkTask JSON、环境初始化器、task initializer 或 evaluator tree，且现有 Benchmark 配置契约 MUST 保持独立。

#### Scenario: 同一个 AgentGraph 使用不同 BenchmarkTask
- **WHEN** 同一 AgentConfig 编译结果随后与两个不同 BenchmarkTask 配对
- **THEN** AgentGraph canonical hash 不因 BenchmarkTask 内容而改变

### Requirement: AgentConfig 保持兼容入口而非通用图全集
AgentConfig V1 的固定 slots 和 `agent_type` SHALL 继续服务旧配置兼容，但新 Router、State、Loop、Subgraph 和任意 extension contract 不要求反向塞入 AgentConfig V1。需要完整组合能力的用户 SHALL 使用 Python AgentGraph 或 graph-native YAML。

#### Scenario: 新图包含两个 Reasoning 节点
- **WHEN** 用户构建 Manager/Operator graph
- **THEN** 系统允许通过 graph-native authoring 表达，不要求把 AgentConfig V1 的 reasoning slot 改成任意嵌套结构

