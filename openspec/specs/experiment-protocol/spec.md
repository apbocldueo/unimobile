# experiment-protocol Specification

## Purpose
TBD - created by archiving change define-benchmark-package-and-experiment-protocol. Update Purpose after archive.
## Requirements
### Requirement: ExperimentProtocol V1 structure
系统 SHALL 定义严格的 `ExperimentProtocol` V1，至少包含 schema version、seed、正整数 repeats、任务顺序、任务物化复用策略、设备约束、App 约束、预算、隔离策略和失败策略。未知的核心策略值 MUST 被拒绝，而不是回退到隐式默认行为。

#### Scenario: Valid protocol
- **WHEN** 协议为所有必需策略提供合法值
- **THEN** 验证返回规范化 Protocol 和稳定 identity，不连接设备

#### Scenario: Invalid repeats
- **WHEN** repeats 为零、负数、布尔值或非整数
- **THEN** 验证失败并定位到 repeats

### Requirement: Deterministic seed and task order
Protocol SHALL 定义根 seed，以及固定顺序或由 seed 决定的确定性顺序策略。相同 Plan identity、Protocol identity 和 repeat index MUST 导出相同任务顺序描述。

#### Scenario: Fixed task order
- **WHEN** task order strategy 为 fixed
- **THEN** 系统使用按合同规范化的稳定顺序，不依赖文件发现顺序

#### Scenario: Seeded task order
- **WHEN** task order strategy 为 seeded 且输入 identity 与 repeat 相同
- **THEN** 顺序派生结果可复现

### Requirement: Fair task materialization policy
Protocol SHALL 明确动态任务是否在同一 repeat 中跨 Agent 复用。用于公平比较的默认策略 MUST 是先物化一次 TaskInstance 再复用给所有 Agent，而不是为每个 Agent 独立随机生成目标。

#### Scenario: Reuse enabled
- **WHEN** 多个 Agent 在同一 repeat 中运行且 `reuse_across_agents` 为 true
- **THEN** 后续运行时必须为它们绑定相同 TaskInstance identity

#### Scenario: Reuse disabled explicitly
- **WHEN** 用户显式关闭复用
- **THEN** Protocol 仍可验证，但系统必须把该实验标记为不满足默认配对公平条件

### Requirement: Device and application constraints
Protocol SHALL 能声明平台、locale、orientation、系统版本策略和逻辑 App 版本策略，但 MUST NOT 把某台设备 serial、登录凭据或 live device handle 写入协议。

#### Scenario: Compatible Android requirements
- **WHEN** 协议声明 Android、特定 locale、portrait 与兼容版本策略
- **THEN** 定义层验证成功并保留约束供后续运行时匹配

#### Scenario: Concrete device serial in protocol
- **WHEN** 协议试图保存 `emulator-5554` 等实际设备 serial
- **THEN** 验证拒绝该字段并说明设备绑定属于运行 provenance

### Requirement: Execution budgets
Protocol SHALL 支持正值预算，包括最大 Agent 交互步数、最大 Graph 节点激活数、任务超时，以及可选 token 上限。预算含义 MUST 独立于具体 Agent 范式。

#### Scenario: Valid multi-dimensional budget
- **WHEN** 协议同时设置交互、节点激活、超时和 token 上限
- **THEN** 所有预算进入 Protocol canonical identity

#### Scenario: Non-positive budget
- **WHEN** 任一已提供预算为零或负数
- **THEN** 协议验证失败并定位到对应预算字段

### Requirement: Reset and cleanup policy
Protocol SHALL 定义 reset 与 cleanup 的执行时机、是否要求验证 reset，以及失败时的处理策略。任务/Plan 声明“需要执行什么初始化或清理”，Protocol 声明“何时执行以及失败后怎么办”。

#### Scenario: Reset before each Agent
- **WHEN** reset policy 为 before_each_agent
- **THEN** 协议语义要求后续运行时在每个 Agent 获得任务前执行并记录 reset

#### Scenario: Verified reset required
- **WHEN** `require_verified_reset` 为 true 且后续 reset 无法验证
- **THEN** failure policy 必须能把该 run 标记为无效，而非当作 Agent 失败

### Requirement: Stage-specific failure policy
Protocol SHALL 分别定义 materialization/initializer、Agent、evaluator 与 cleanup 失败时的任务状态、是否继续 suite，以及是否保留已有证据。失败策略 MUST 区分基础设施无效与 Agent 任务失败。

#### Scenario: Initializer failure
- **WHEN** initializer 阶段失败且策略为 invalidate
- **THEN** 后续运行时必须将 run 标记为基础设施无效，不计为 Agent 失败

#### Scenario: Agent failure with evaluable evidence
- **WHEN** Agent 阶段失败但策略允许 `evaluate_if_possible`
- **THEN** 后续运行时可继续 evaluator，同时保留 Agent 失败阶段与原始证据

#### Scenario: Cleanup failure after evaluation
- **WHEN** evaluator 已产出结果但 cleanup 失败
- **THEN** 后续运行时必须保留 evaluator 结果并另行记录 cleanup 失败，不得静默覆盖已有证据

### Requirement: Side-effect-free protocol validation
Protocol 的解析、规范化、identity 与定义层验证 MUST NOT 查询设备、检查已安装 App、执行 reset/cleanup、调用模型或读取 secret。

#### Scenario: Validate without Android
- **WHEN** 在没有 ADB 设备的进程中验证一个有效 Protocol
- **THEN** 验证成功并产生与有设备环境相同的规范化结果

### Requirement: ExperimentProtocol 运行时强制执行
Benchmark Experiment Runtime SHALL 强制执行经过验证的 ExperimentProtocol，而不是只把它记录为元数据。Runtime MUST 使用 Protocol 控制 repeats、任务顺序、TaskInstance 复用、设备/App preflight、交互与激活预算、协作式 timeout、reset/cleanup 时机和分阶段失败处理，并把实际采用的 Protocol identity 写入每个结果。

#### Scenario: Protocol 预算覆盖 Agent 默认值
- **WHEN** AgentGraph 的默认 max steps 高于 Protocol 最大交互预算
- **THEN**本次 Benchmark 运行在不改变 AgentGraph identity 的情况下使用更严格的 Protocol 上限

#### Scenario: 协作式 timeout
- **WHEN**任务达到 timeout 且 Graph Runtime 到达可取消边界
- **THEN**Runtime 取消 Agent 阶段、保留已有事件与 artifact，并按 Agent failure policy 继续处理

#### Scenario: token 预算不可观测
- **WHEN** Protocol 设置 token limit 但所用模型组件无法提供 usage
- **THEN**结果明确报告预算不可验证，且在要求严格验证时将运行标记为 INVALID，而不是假定未超限

### Requirement: reset 与 cleanup 时机落实
Runtime SHALL 根据 Protocol 的 isolation policy 调度任务声明的 reset 和 cleanup，并始终记录它们是否执行、验证、跳过或失败。`require_verified_reset` 为 true 时，缺少可验证成功结果 MUST 按 initializer failure policy 处理。

#### Scenario: before_each_agent
- **WHEN** reset policy 为 `before_each_agent`
- **THEN**每个 Agent 获得对应 TaskInstance 前都执行并记录该任务需要的 reset

#### Scenario: after_each_run
- **WHEN** cleanup policy 为 `after_each_run`
- **THEN**每个 Agent 与 TaskInstance 组合结束后执行 cleanup，即使 Agent 或 evaluator 已失败

#### Scenario: once
- **WHEN** reset 或 cleanup policy 为 `once`
- **THEN**Runtime 在 suite 规定的唯一边界执行一次，并在所有受影响任务结果中引用该阶段证据

