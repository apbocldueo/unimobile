# benchmark-plan-compilation Specification

## Purpose
TBD - created by archiving change define-benchmark-package-and-experiment-protocol. Update Purpose after archive.
## Requirements
### Requirement: Unified BenchmarkPlan compilation
系统 SHALL 将独立的现有 `BenchmarkSuite` JSON 或一个 `BenchmarkPackage` 编译为同一种 typed `BenchmarkPlan`。Plan SHALL 表达任务模板、所选 split、initializer、环境要求、Evaluator Tree、资源与 ground truth 引用、App 要求和插件逻辑引用。

#### Scenario: Compile standalone JSON
- **WHEN** 用户提交符合现有合同的独立 Benchmark JSON
- **THEN** 编译器生成有效 `BenchmarkPlan`，且不要求用户先创建 Package

#### Scenario: Compile package split
- **WHEN** 用户选择有效 Package 的一个 split
- **THEN** 编译器生成只包含该 split 任务及其引用闭包的 `BenchmarkPlan`

#### Scenario: Invalid source contract
- **WHEN** 输入 JSON、manifest 或选定 split 不满足相应合同
- **THEN** 编译失败并返回结构化诊断，不产生部分可执行 Plan

### Requirement: Side-effect-free compilation
BenchmarkPlan 编译 MUST 是无设备副作用过程。编译器 MAY 读取显式本地声明和资源以验证摘要，但 MUST NOT 连接设备、调用模型、解析 secret、执行 task initializer、环境 initializer、evaluator、cleanup，或实例化插件实现。

#### Scenario: Compile dynamic tasks
- **WHEN** Package 包含动态任务和随机生成插件声明
- **THEN** Plan 保留生成器逻辑引用但不生成参数或渲染最终 instruction

#### Scenario: Unknown plugin reference during structural compilation
- **WHEN** Plan 包含当前环境未安装的插件逻辑引用
- **THEN** 结构编译仍不导入或执行插件，并按所选验证级别返回可定位诊断

### Requirement: Pure and serializable BenchmarkPlan
`BenchmarkPlan` MUST 只包含 JSON-compatible typed values、逻辑引用和内容摘要；它 MUST NOT 包含绝对路径、当前工作目录、live component、device handle、secret、打开的文件或运行时对象。

#### Scenario: Serialize compiled plan
- **WHEN** 一个有效输入完成编译
- **THEN** Plan 可稳定序列化并在另一进程中反序列化为等价语义

#### Scenario: Runtime object supplied to compiler
- **WHEN** 输入试图把设备对象、插件实例或非 JSON-compatible 值放入 Plan
- **THEN** 编译失败并指出非法字段

### Requirement: Structured compilation diagnostics
编译器 SHALL 聚合可独立检测的结构、语义、资源和引用错误，并为每个诊断提供稳定代码、严重级别、来源、task ID（若可知）与精确字段路径。

#### Scenario: Multiple independent package errors
- **WHEN** Package 同时包含缺失资源、未知 split 和两个任务合同错误
- **THEN** 编译器返回所有可独立检测的诊断，而不是在首个错误后停止

#### Scenario: Safe diagnostic output
- **WHEN** 输入附近存在 secret、设备标识或本机绝对路径
- **THEN** 诊断仅暴露必要的逻辑标识和安全相对路径，不回显敏感值或 live object

### Requirement: TaskInstance contract without materialization side effects
系统 SHALL 定义 `TaskInstance` typed contract，至少包含 Plan/task identity、repeat、seed 派生信息、已生成参数、渲染后的 instruction、绑定后的 ground truth 与 instance identity。本 Change 的 Plan 编译 MUST NOT 自动创建 TaskInstance。

#### Scenario: Pre-materialized instance validation
- **WHEN** 调用者提交字段完整且与 Plan task 对应的预物化 TaskInstance
- **THEN** 系统可无设备副作用地验证并计算其 identity

#### Scenario: Plan compilation of a dynamic task
- **WHEN** 编译动态 BenchmarkTask
- **THEN** 输出仍是任务模板 Plan，且不伪造已物化参数或 TaskInstance

### Requirement: Legacy path preservation
新增编译入口 MUST 与现有 Benchmark JSON loader、公共合同导入和旧 BenchmarkPipeline 并存；在后续新运行路径通过行为等价验证前，不得让旧入口暗中改用未验证的新执行语义。

#### Scenario: Existing V1 JSON loader
- **WHEN** 现有调用方继续使用旧公开 API 加载 V1 JSON
- **THEN** 原加载结果和错误行为保持兼容

#### Scenario: Explicit new compiler use
- **WHEN** 调用方选择新的 BenchmarkPlan 编译 API
- **THEN** 系统只执行定义层编译，不启动旧或新 Benchmark 运行 Pipeline

### Requirement: BenchmarkPlan 保留可执行生命周期声明
BenchmarkPlan 编译 SHALL 保留每个任务的 reset、setup、evaluator pre/evaluate 和 cleanup 逻辑声明及其稳定顺序，但 MUST NOT 在编译阶段解析 live plugin、生成参数、连接设备或执行任何生命周期操作。

#### Scenario: 编译带 cleanup 的 Package
- **WHEN** Package 中的任务声明显式 reset/setup 和 cleanup
- **THEN**输出 Plan 可序列化地保留这些调用，供 Experiment Runtime 后续解析

#### Scenario: 编译不执行生命周期
- **WHEN** reset、setup 或 cleanup 插件在被调用时会产生设备副作用
- **THEN**只编译和验证 Plan 不调用这些插件

### Requirement: Canonical evaluation semantics in BenchmarkPlan
BenchmarkPlan compilation SHALL retain typed evaluator node semantics, threshold parameters, child weights, evidence policy references, and child order. These values SHALL participate in canonical BenchmarkPlan identity, while existing AND, OR, and SEQUENCE inputs with unchanged semantics MUST retain their previously verified canonical identities.

#### Scenario: Weighted threshold changes identity
- **WHEN** two otherwise equal Plans use different WEIGHTED pass thresholds or child weights
- **THEN** their canonical identities differ

#### Scenario: Existing Plan identity stability
- **WHEN** an existing AndroidWorld or AppAgent Package with only legacy-supported composite logic is recompiled after this change
- **THEN** its canonical BenchmarkPlan identity matches the frozen pre-migration fixture

### Requirement: Evaluation contract validation remains side-effect free
Compilation and validation of V2 evaluation declarations MUST NOT import or invoke evaluator implementations, read live device state, load binary evidence, call a model, or create report artifacts. They SHALL validate only declared structure, safe logical references, and canonical values at the selected validation level.

#### Scenario: External evaluator absent
- **WHEN** a Package references an external evaluator unavailable in the current environment
- **THEN** structural compilation preserves the logical reference and reports availability according to the selected validation level without importing plugin code

#### Scenario: Report output during compilation
- **WHEN** a caller only compiles a BenchmarkPlan
- **THEN** no run report, trajectory, bundle, or `temp/benchmark-runs` directory is created

