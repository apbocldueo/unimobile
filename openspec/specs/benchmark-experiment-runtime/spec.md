# benchmark-experiment-runtime Specification

## Purpose
TBD - created by archiving change integrate-benchmark-plan-graph-runtime. Update Purpose after archive.
## Requirements
### Requirement: 统一 Benchmark Experiment Runtime
系统 SHALL 提供公开的 Benchmark Experiment Runtime，以一个 `BenchmarkPlan`、一个 `ExperimentProtocol` 和一个或多个具名 `ExecutableAgent` 为输入，生成确定性执行日程并返回结构化 suite 结果。该 Runtime MUST 编排现有 Graph Runtime，而 MUST NOT 调用 `AgentRunner`、把 Benchmark 分支加入 Graph Kernel，或根据数据集和任务 ID执行特判。

#### Scenario: 单 Agent 执行 Plan
- **WHEN** 调用者提交有效 Plan、Protocol 和一个 ExecutableAgent
- **THEN** Runtime 按 Protocol 顺序执行选定任务并返回包含每任务结果的 suite 结果

#### Scenario: 禁止旧 Runner 回退
- **WHEN** 测试令 `AgentRunner` 的构造和 `run` 调用立即失败
- **THEN** 新 Benchmark Runtime 的 fake-device 完整执行仍然成功

### Requirement: 公平 TaskInstance 物化
Runtime SHALL 在执行设备初始化前把每个任务模板物化为 `TaskInstance`，使用由 Protocol seed、Plan identity、task ID 和 repeat index 确定性派生的 seed。`reuse_across_agents` 为 true 时，同一 repeat 中的所有 Agent MUST 获得同一个已物化实例和 identity；物化 MUST NOT 依赖 AgentGraph 或实际设备。

#### Scenario: 跨 Agent 复用实例
- **WHEN** 两个 Agent 在同一 repeat 中运行一个动态任务且复用开启
- **THEN** generator 只执行一次，两个任务结果记录相同 TaskInstance identity、参数和最终 instruction

#### Scenario: 显式关闭复用
- **WHEN** Protocol 关闭 `reuse_across_agents`
- **THEN** Runtime 为每个 Agent 独立物化并在 suite 结果中保留非配对公平警告

#### Scenario: 物化失败
- **WHEN** 某个 task initializer 无法解析或执行
- **THEN** Runtime 产生 materialization 失败阶段并按 Protocol 将相关运行标记为 INVALID 或指定结果，且不连接设备执行 Agent

### Requirement: Suite、repeat 与多 Agent 编排
Runtime SHALL 根据 Protocol 的 repeats 和任务顺序策略构建稳定日程，并支持同一 AgentGraph 运行普通任务和 BenchmarkTask、同一 BenchmarkPlan 运行不同 AgentGraph。每个 `Agent × TaskInstance` 组合 MUST 产生独立结果，suite 停止或继续 MUST 由对应阶段的 failure policy 决定。

#### Scenario: Seeded 多任务顺序
- **WHEN** 相同 Plan、Protocol 和 repeat 被执行两次
- **THEN** 两次日程中的任务顺序和实例 seed 派生描述完全相同

#### Scenario: 同一 Plan 比较两个 Agent
- **WHEN** 调用者用两个不同 canonical hash 的 ExecutableAgent 运行同一个 Plan
- **THEN** suite 结果分别归属两个 Agent identity，并共享 Protocol 要求复用的 TaskInstance

### Requirement: 每任务独立 RuntimeContext
每个 Agent 与 TaskInstance 的运行 SHALL 使用新的 `RuntimeContext`、AgentState、run ID、事件序列和 artifact namespace。RuntimeContext MUST 记录安全的 AgentGraph、BenchmarkPlan、ExperimentProtocol 与 TaskInstance identity，但 MUST NOT 保存 secret、live plugin、未清洗设备对象或绝对输出路径到公共结果。

#### Scenario: 连续运行两个任务
- **WHEN** 同一 ExecutableAgent 在 suite 中执行两个 TaskInstance
- **THEN** 第二个任务不继承第一个任务的 Memory fallback、最后观察、动作、事件序号或 artifact namespace

#### Scenario: 安全上下文结果
- **WHEN** RuntimeContext 包含设备、模型、event sink 和 artifact 服务
- **THEN** BenchmarkTaskResult 只保留安全 identity、状态与引用，不遍历或序列化服务对象

### Requirement: 统一设备会话与 Graph Runtime 执行
一次串行 suite 执行 SHALL 显式选择并复用满足 Protocol 约束的设备会话，reset/setup、Graph Runtime、evaluator 与 cleanup MUST 使用该会话。Agent 阶段 MUST 通过 `ExecutableAgent` 和 `AndroidGraphRuntime` 执行；Benchmark Runtime MUST NOT 创建另一套截图、推理、动作循环。

#### Scenario: Fake device 全生命周期
- **WHEN** 调用者提供记录调用的 fake Android device
- **THEN** initializer、Graph Runtime 和 evaluator 观察到同一设备 identity，且设备调用顺序与生命周期一致

#### Scenario: 设备约束不满足
- **WHEN**实际设备平台、locale、orientation、系统或 App 版本不满足 Protocol/Plan 要求
- **THEN**相关运行在 Agent 执行前被标记为 INVALID，并记录安全的 preflight 诊断

### Requirement: 分阶段生命周期与失败策略
每个任务运行 SHALL 依次表达 reset、setup/initializer、evaluator pre-hook、Agent、evaluation 和 cleanup 阶段，并为每个实际执行阶段发出带 task/agent/instance 关联的 `start`、`complete` 或 `fail` 生命周期事件。阶段失败 MUST 按 Protocol 独立处理，后续阶段不得静默覆盖已有证据。

#### Scenario: Agent 失败后仍可评估
- **WHEN** Agent 阶段失败且 failure policy 为 `evaluate_if_possible`
- **THEN** Runtime 在证据充分时继续 evaluator，同时保留 Agent 失败状态和 evaluation 结果

#### Scenario: cleanup 失败
- **WHEN** evaluator 已 PASS 但 cleanup 失败
- **THEN**结果保留 PASS evaluator 证据、单独记录 cleanup 失败，并按 cleanup policy 决定最终 outcome 与 suite 是否继续

#### Scenario: 未执行阶段
- **WHEN** initializer 失败导致 Agent 不应启动
- **THEN** Agent 与 evaluation 阶段被明确记录为 SKIPPED，而不是缺失或伪造成功事件

### Requirement: 结构化 BenchmarkTaskResult 与 SuiteResult
系统 SHALL 定义安全、可序列化的 `BenchmarkTaskResult` 和 `BenchmarkSuiteResult`。TaskResult MUST 包含四类 canonical identity、task/repeat/Agent 归属、最终 `PASS`、`FAIL`、`INVALID` 或 `SKIPPED` outcome、分阶段结果、Agent `RunResult`、evaluation 结果、耗时、usage、事件和 artifact 引用；SuiteResult MUST 保留有序 TaskResult、计数与公平警告。

#### Scenario: Agent 成功但 evaluator 失败
- **WHEN** Graph Runtime 返回 `RunStatus.SUCCESS` 而 Evaluator Tree 返回 false
- **THEN** TaskResult 保留 Agent 成功并将 Benchmark outcome 设为 FAIL

#### Scenario: 基础设施无效
- **WHEN** verified reset 或 evaluator 基础设施失败并被策略定义为 invalidate
- **THEN** TaskResult outcome 为 INVALID，且不计为普通 Agent 任务失败

### Requirement: Evaluator Tree 结构化证据
Runtime SHALL 按 BenchmarkTask 显式声明构建 Evaluator Tree，不得自动猜测 evaluator 或 ground truth。每个执行过的叶子 evaluator SHALL 返回独立的 Evaluation Result V2，包括安全状态、通过判断、可选分数、耗时、逻辑路径和 typed evidence 引用。AND、OR、SEQUENCE、THRESHOLD 和 WEIGHTED 节点 SHALL 保留完整子结果、组合决策和适用的短路信息，而不只返回最终布尔值。

#### Scenario: AND 子节点失败
- **WHEN** AND 树中第一个叶子通过而第二个叶子失败
- **THEN** TaskResult 同时包含两个叶子结果及 AND 失败原因

#### Scenario: OR 短路
- **WHEN** OR 树的一个分支通过并触发短路
- **THEN** 已执行分支保留结果，未执行分支标记 SKIPPED，并记录短路依据

#### Scenario: Threshold 完整证据
- **WHEN** THRESHOLD 节点达到通过阈值
- **THEN**默认仍执行并保留所有子节点结果，除非合同显式定义了其他可审计行为

#### Scenario: Weighted 组合
- **WHEN** WEIGHTED 节点完成所有有效子节点
- **THEN** TaskResult 保留每个权重、子分数、贡献值、聚合分数和最终阈值判断

### Requirement: Benchmark 运行 CLI
已安装的 `zhixing` console script SHALL 提供 `zhixing benchmark run`，允许选择本地目录或 Catalog identity、split、可选 task ID、一个或多个 graph-native Agent、Protocol、Android serial 和 artifact root。CLI MUST 委托公共编译、加载和 Experiment Runtime API，并以稳定退出码及安全 JSON/文本摘要表达 suite 结果。

#### Scenario: 运行一个 Package 任务
- **WHEN** 用户指定 AndroidWorld Package、一个 task ID、Agent YAML、Protocol 和 serial
- **THEN** CLI 编译定义、运行统一生命周期并输出 TaskResult outcome 与 artifact 引用

#### Scenario: 定义或绑定失败
- **WHEN** Benchmark、Protocol 或 Agent 在设备连接前无法编译或绑定
- **THEN** CLI 返回非零退出码和结构化安全诊断，不执行 initializer 或设备动作

### Requirement: Fake 与真实 Android 验收
实现 MUST 使用 fake device 覆盖完整 suite 语义，并至少对一个首批内置 Package 的真实 Android BenchmarkTask 运行 initializer、Graph Runtime、evaluator 与 cleanup。真实成功声明 MUST 同时具有结构化 TaskResult、Graph `RunResult`、evaluator PASS 与设备证据。

#### Scenario: Fake 多 Agent 完整回归
- **WHEN** fake device 上运行包含动态任务、两个 Agent、两个 repeats 和失败分支的 Plan
- **THEN**测试验证公平复用、隔离 context、生命周期顺序、失败策略和 suite 计数

#### Scenario: 真实拍照任务
- **WHEN** AndroidWorld 拍照 BenchmarkTask 在显式 Android serial 上运行
- **THEN**只有 AgentGraph 完成且任务声明的 evaluator 检测到新增照片时 TaskResult 才能为 PASS

### Requirement: 旧 Benchmark 执行兼容
现有 `BenchmarkPipeline`、`AgentRunner`、旧 Benchmark JSON loader 和旧 CLI/脚本入口 SHALL 保持可用；新 API MUST 是显式选择的新路径，且不得暗中改变旧路径的返回类型或执行顺序。

#### Scenario: 旧 Pipeline 回归
- **WHEN**现有调用方继续实例化 BenchmarkPipeline 并运行旧 Agent
- **THEN**原入口仍可执行并通过既有兼容测试

### Requirement: Durable reporting handoff
Benchmark Experiment Runtime SHALL expose a writer boundary that derives versioned task-run and experiment artifacts from the completed structured results and event streams. Report writing failures MUST remain distinguishable from Agent or evaluator outcomes and MUST NOT mutate previously recorded runtime facts.

#### Scenario: Successful suite artifact write
- **WHEN** a suite completes with a configured artifact root
- **THEN** the Runtime writes or delegates writing of loadable run results, reports, trajectories, and an experiment manifest using safe relative references

#### Scenario: Report writer failure
- **WHEN** runtime execution and evaluation complete but durable artifact writing fails
- **THEN** the in-memory result preserves the original outcomes and records a separate reporting failure

### Requirement: Recursive safe runtime export
Every public Benchmark result and artifact export SHALL pass through the same recursive safety policy, including nested Graph `RunResult`, action results, error details, lifecycle events, evaluator evidence, and device provenance.

#### Scenario: Nested unsafe Graph field
- **WHEN** a nested Graph event contains an absolute path or raw device serial
- **THEN** the persisted Benchmark result and trajectory redact or reject the unsafe value according to policy while retaining a structured diagnostic

#### Scenario: Live service object in context
- **WHEN** a RuntimeContext holds a device, model, sink, or artifact service object
- **THEN** reporting serializes only approved identities and references and never recursively traverses the service

### Requirement: Benchmark Runtime 必须接受可选调用方 cancellation signal
`BenchmarkExperimentRuntime` SHALL 接受可选 caller-owned cooperative cancellation
signal，并在 materialization、共享 reset、每 TaskRun、Agent activation、evaluation、
cleanup 和后续 schedule 的安全边界观察它。未提供时 MUST 保持现有 deadline cancellation
默认行为；提供时 SHALL 与 Protocol timeout 组合，而不是移除 timeout。Signal 与 live
service object MUST NOT 进入 canonical identity、result、report 或 artifact。

#### Scenario: 未提供外部 signal
- **WHEN**现有 Python/CLI 调用方使用原参数运行 Benchmark
- **THEN**Runtime 保持既有 schedule、timeout、结果和默认 artifact 行为

#### Scenario: Agent 运行中请求取消
- **WHEN**外部 signal 在不可中断的模型或设备调用期间变为 cancelled
- **THEN**当前调用返回后的安全边界停止新的 activation/schedule，同时执行 Protocol 要求的必要 cleanup

#### Scenario: evaluation 完成后取消
- **WHEN**外部 signal 在 evaluation 已产生 PASS/FAIL、cleanup 尚未完成时触发
- **THEN**Runtime 保留 Evaluation 和 outcome 事实、完成必要 cleanup，并不把正式结果覆盖为空 cancellation

### Requirement: Benchmark Runtime 必须允许调用方延后 suite publication
Runtime SHALL 提供显式 runtime-only publication policy，使调用方可以在仍获得完整
in-memory `BenchmarkSuiteResult` 的情况下延后 task manifest、experiment report、
trajectory 和 bundle 写入。默认 policy MUST 保持现有 artifact finalization 行为；
publication policy、artifact root 和 writer service MUST NOT 影响 Plan、Protocol、
AgentGraph、TaskInstance 或 schedule canonical identity。

#### Scenario: 默认调用保持兼容
- **WHEN**现有调用方未指定 publication policy
- **THEN**Runtime 继续按当前行为写入 task manifests、report、trajectory 和 bundle 并返回 artifact refs

#### Scenario: Studio 延后 publication
- **WHEN**Stage 5.2B 使用 defer policy 执行第一切片
- **THEN**Runtime 返回 phases、Agent result、Evaluation 和 Benchmark outcome，但不生成或声明正式 report/bundle publication

#### Scenario: defer 模式 result 持久化失败
- **WHEN**Studio repository 无法提交返回的 bounded TaskResult
- **THEN**该失败由 Studio service lifecycle 处理，不被 Runtime 伪装为 Benchmark FAIL/INVALID

