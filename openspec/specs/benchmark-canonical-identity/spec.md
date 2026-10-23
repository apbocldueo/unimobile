# benchmark-canonical-identity Specification

## Purpose
TBD - created by archiving change define-benchmark-package-and-experiment-protocol. Update Purpose after archive.
## Requirements
### Requirement: Versioned canonicalization contract
系统 SHALL 为 Benchmark 规范化定义独立的 schema version 与 canonicalization version，并使用确定性 JSON-compatible payload 计算 SHA-256 identity。相同语义在支持的平台与进程之间 MUST 产生相同结果。

#### Scenario: Repeat canonicalization
- **WHEN** 同一对象在不同进程中重复规范化
- **THEN** canonical payload 字节和 SHA-256 identity 完全相同

#### Scenario: Canonicalization version changes
- **WHEN** 未来规范化规则发生不兼容变化
- **THEN** 系统要求提升 canonicalization version，而不是静默改变旧 identity

### Requirement: Benchmark Package identity
Package SHALL 同时暴露人类可读的 `publisher/name@semver` 与基于规范内容、任务入口及资源摘要的 content identity。相同可读版本下的内容漂移 MUST 产生不同 content identity 和验证诊断。

#### Scenario: Same version and same content
- **WHEN** 两个 Package 的可读身份和规范内容相同
- **THEN** 它们具有相同 content identity

#### Scenario: Same version with changed content
- **WHEN** Package 未提升版本但任务或资源内容发生变化
- **THEN** content identity 改变，系统可报告 same-version content drift

### Requirement: BenchmarkPlan canonical identity boundaries
Plan canonical payload SHALL 包含 Package identity（若有）、所选 split、按 task ID 规范化的任务语义、task initializer、reset/setup/cleanup、Evaluator Tree 声明、App 要求、资源与 ground truth 摘要及插件逻辑引用。它 MUST 排除绝对路径、`cwd`、设备 serial、AgentGraph identity、输出目录、secret、README、时间戳、声明顺序中的非语义差异和 live instance。

#### Scenario: Package relocated
- **WHEN** 语义相同的 Package 被复制到不同绝对路径并编译
- **THEN** 两个 `BenchmarkPlan` canonical hash 相同

#### Scenario: Task declaration order differs
- **WHEN** 两个 Package 仅 task 文件声明顺序不同且 task ID 与语义集合相同
- **THEN** 两个 Plan canonical hash 相同，因为执行顺序由 ExperimentProtocol 管理

#### Scenario: Evaluator semantics change
- **WHEN** 某任务的 evaluator 方法、参数或组合逻辑发生变化
- **THEN** Plan canonical hash 改变

#### Scenario: 生命周期语义改变
- **WHEN** 某任务的 reset/setup/cleanup 插件、参数、阶段或相对顺序发生变化
- **THEN** Plan canonical hash 改变

#### Scenario: Documentation changes
- **WHEN** 只修改 README、注释或本地输出目录
- **THEN** Plan canonical hash 不变

### Requirement: TaskInstance identity boundaries
TaskInstance canonical payload SHALL 覆盖 Plan identity、task ID、repeat、seed 派生标识、已生成参数、最终 instruction 与绑定 ground truth；它 MUST 排除分配给哪个 Agent、实际设备 serial 和运行 artifact 路径。

#### Scenario: Reuse instance across Agents
- **WHEN** 两个 Agent 在同一 repeat 中接收相同的物化任务数据
- **THEN** 它们看到相同 TaskInstance identity

#### Scenario: Generated target changes
- **WHEN** 动态参数或最终 instruction 中的目标发生变化
- **THEN** TaskInstance identity 改变

### Requirement: ExperimentProtocol identity independence
ExperimentProtocol SHALL 独立规范化并计算 identity。Protocol identity MUST 覆盖公平策略，但 MUST 排除实际设备 serial、secret 和输出路径；改变 Protocol 不得改变 AgentGraph 或 BenchmarkPlan identity。

#### Scenario: Budget changes
- **WHEN** 仅修改最大交互步数或超时
- **THEN** Protocol identity 改变，而 Plan identity 保持不变

#### Scenario: Runtime binding changes
- **WHEN** 仅把协议绑定到另一台满足相同约束的设备
- **THEN** Protocol identity 不变，实际设备信息留给后续运行 provenance

### Requirement: Identity-safe public representation
身份计算和展示 MUST NOT 序列化 API key、token、password、设备句柄、live plugin instance 或未经清洗的环境变量。

#### Scenario: Sensitive value appears near identity input
- **WHEN** 调用者提供包含敏感字段的扩展数据
- **THEN** 系统拒绝该字段或将其排除并产生安全诊断，且 identity payload 不包含原值

