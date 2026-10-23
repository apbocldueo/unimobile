# benchmark-config-contract Specification

## Purpose
TBD - created by archiving change define-config-contracts. Update Purpose after archive.
## Requirements
### Requirement: Canonical BenchmarkTask V1 structure
The system SHALL define a strict `BenchmarkTask` V1 model with required non-empty `id` and `instruction`, required `type`, `task_initializer`, `environment_initializer`, and `evaluator`, plus optional `app`, `requires_login`, and positive `max_steps`. Unknown task-level fields and legacy field names MUST be rejected.

#### Scenario: Valid canonical Benchmark task
- **WHEN** a task uses `id`, `instruction`, canonical initializer fields, and a valid evaluator tree
- **THEN** structural validation succeeds and returns a canonical `BenchmarkTask` value

#### Scenario: Legacy Benchmark task fields
- **WHEN** a task uses `task`, `params_config`, `setup_config`, `eval_type`, or plugin-level `type` in place of canonical fields
- **THEN** validation fails with precise field errors and no legacy conversion is attempted

#### Scenario: Invalid maximum steps
- **WHEN** `max_steps` is zero, negative, non-integral, or boolean
- **THEN** validation fails at `max_steps`

### Requirement: BenchmarkSuite collection contract
The system SHALL define `BenchmarkSuite` as a non-empty ordered collection of `BenchmarkTask` values and SHALL require task IDs to be unique within the suite.

#### Scenario: Valid task collection
- **WHEN** a JSON root array contains one or more valid tasks with unique IDs
- **THEN** suite validation succeeds and preserves source order

#### Scenario: Duplicate task identifier
- **WHEN** two tasks in one suite have the same `id`
- **THEN** validation fails and identifies the duplicate ID and conflicting task locations

#### Scenario: Empty suite
- **WHEN** the JSON root is an empty array
- **THEN** validation fails before benchmark execution

### Requirement: Task initializer plugin calls
`task_initializer` SHALL be an ordered mapping from generated variable names to plugin calls containing a non-empty `name` and an optional open `params` mapping. A dynamic task MUST define at least one task initializer; a static task MAY define initializers when deterministic setup values still need generation.

#### Scenario: Ordered dependent initializers
- **WHEN** an initializer parameter references a variable produced by an earlier initializer
- **THEN** semantic validation succeeds and preserves initializer order

#### Scenario: Forward initializer reference
- **WHEN** an initializer parameter references a variable that is not defined by an earlier initializer
- **THEN** semantic validation fails at the referencing parameter path

#### Scenario: Dynamic task without initializer
- **WHEN** task type is `dynamic` and `task_initializer` is empty
- **THEN** semantic validation fails

### Requirement: Environment initializer plugin calls
`environment_initializer` SHALL be an ordered list of plugin calls containing a non-empty `name`, optional open `params`, and optional `namespace`, `category`, and `meta` routing fields supported by the runtime. Validation MUST preserve list order because reset, injection, and setting operations are order-sensitive.

#### Scenario: Ordered environment setup
- **WHEN** a task contains multiple valid environment initializer calls
- **THEN** validation succeeds and canonical output preserves their order

#### Scenario: Environment initializer supplied as object
- **WHEN** `environment_initializer` is an object rather than an array
- **THEN** structural validation fails before `BenchmarkPipeline` iteration

### Requirement: Recursive evaluator tree
The evaluator contract SHALL distinguish leaf evaluators from composite evaluators. A leaf evaluator MUST contain a non-empty category `name` and `params.method`. A composite evaluator MUST use `name: composite`, MUST choose `AND`, `OR`, `SEQUENCE`, `THRESHOLD`, or `WEIGHTED`, and MUST contain a non-empty recursive `rules` list. `THRESHOLD` MUST define exactly one valid `min_passed` or `min_ratio`; `WEIGHTED` MUST define a normalized `pass_threshold` and one positive finite weight per child. The legacy alias `eval_composite` MUST be rejected.

#### Scenario: Valid leaf evaluator
- **WHEN** an evaluator contains a category name and a non-empty `params.method`
- **THEN** structural validation succeeds

#### Scenario: Nested composite evaluator
- **WHEN** a composite contains valid leaf or composite child rules at multiple depths
- **THEN** structural validation succeeds for the complete recursive tree

#### Scenario: Empty composite rules
- **WHEN** a composite evaluator has no rules
- **THEN** validation fails at `evaluator.params.rules`

#### Scenario: Unsupported composite logic
- **WHEN** composite logic is not `AND`, `OR`, `SEQUENCE`, `THRESHOLD`, or `WEIGHTED`
- **THEN** validation fails at `evaluator.params.logic`

#### Scenario: Invalid threshold configuration
- **WHEN** a THRESHOLD node declares both threshold modes, neither mode, a non-positive count, or a ratio outside the accepted normalized range
- **THEN** validation fails at the exact threshold field

#### Scenario: Invalid weighted configuration
- **WHEN** a WEIGHTED node has a missing, non-finite, zero, or negative child weight or an invalid pass threshold
- **THEN** validation fails before registry resolution or execution

#### Scenario: Legacy composite alias
- **WHEN** evaluator name is `eval_composite`
- **THEN** validation fails and identifies `composite` as the canonical V1 name

### Requirement: Placeholder consistency
Semantic validation SHALL collect `${name}` placeholders recursively from `instruction`, initializer parameters, environment initializer parameters and metadata, and evaluator parameters. Every placeholder MUST be available from an earlier task initializer or from an explicitly documented runtime-provided variable set; unresolved placeholders MUST fail validation rather than remain in the executed task.

#### Scenario: All placeholders resolve
- **WHEN** every placeholder refers to a previously generated task variable or documented runtime variable
- **THEN** semantic validation succeeds without generating any values

#### Scenario: Missing task variable
- **WHEN** instruction or evaluation configuration references `${category}` but no initializer or runtime variable defines `category`
- **THEN** validation fails and reports every unresolved reference path

#### Scenario: Unused initializer variable
- **WHEN** an initializer generates a variable that is not referenced elsewhere in the task
- **THEN** validation succeeds and MAY emit a non-fatal diagnostic

### Requirement: Registry-backed Benchmark resolution
The system SHALL provide a registry-backed validation level for task generators, environment initializers, leaf evaluator methods, and composite logic. Registry validation MUST resolve each plugin in the same namespace used by `BenchmarkPipeline` and `EvaluatorFactory` without executing generators, environment operations, evaluators, device commands, or model calls.

#### Scenario: Valid Benchmark plugin graph
- **WHEN** all initializer names and evaluator methods resolve in their runtime namespaces
- **THEN** registry validation succeeds without changing environment state

#### Scenario: Unknown evaluator method
- **WHEN** a leaf evaluator category exists but `params.method` is not registered under that evaluator namespace
- **THEN** validation fails at the evaluator method path

#### Scenario: Ambiguous environment plugin
- **WHEN** an environment plugin name resolves under multiple sub-namespaces and no namespace or category disambiguates it
- **THEN** validation fails with the matching namespaces and requests explicit routing

### Requirement: Side-effect-free contract validation and diagnostics
Structural, semantic, and registry-backed Benchmark validation SHALL return deterministic JSON-compatible model output and structured diagnostics with task index, task ID when available, and exact field path. These validation levels MUST NOT generate random task values, initialize environments, build evaluators, connect to devices, or invoke models.

#### Scenario: Canonical dataset contract test
- **WHEN** a designated V1 Benchmark JSON file is validated in an isolated test process
- **THEN** every task is checked and all diagnostics are returned without starting benchmark execution

#### Scenario: Multiple invalid tasks
- **WHEN** a suite contains errors in more than one task
- **THEN** validation reports all independently detectable contract errors rather than stopping after the first invalid task

### Requirement: 显式 Benchmark 生命周期操作
`BenchmarkTask` SHALL 在保持现有字段兼容的前提下，允许环境操作显式声明 `reset` 或 `setup` 阶段，并允许可选的有序 `cleanup_initializer` 操作列表。每个 cleanup 调用 SHALL 使用与环境 initializer 相同的插件调用合同；验证 MUST 覆盖其中的 placeholder、路由字段和 JSON-compatible 参数。

#### Scenario: 带 reset/setup/cleanup 的任务
- **WHEN**任务把清理 App 数据标记为 reset、把资源注入标记为 setup，并声明 cleanup 操作
- **THEN**合同验证成功且 canonical 输出保留三个阶段内部的声明顺序

#### Scenario: 旧任务没有阶段字段
- **WHEN**现有 BenchmarkTask 只包含旧的 environment_initializer 列表
- **THEN**合同仍可加载，运行期 MAY 根据已解析插件 namespace 兼容推断 reset/setup，但 MUST 产生可审计的兼容信息而非静默猜测

#### Scenario: cleanup 中存在未知占位符
- **WHEN** cleanup 参数引用未定义的 `${target}`
- **THEN**语义验证失败并定位到 cleanup_initializer 的准确路径

