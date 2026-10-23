# agent-graph-runtime-observability Specification

## Purpose
TBD - created by archiving change implement-agent-graph-runtime. Update Purpose after archive.
## Requirements
### Requirement: 每个执行节点具有成对生命周期事件
Graph Runtime SHALL 为每个实际开始执行的节点先产生一个 `start` RunEvent，并在该次调用结束时产生且只产生一个 `complete` 或 `fail` RunEvent。事件 MUST 包含 run_id、全局单调 sequence、step、逻辑 node_id、role、component、phase、kind 和 timestamp；未激活分支 MAY 产生 `node_skipped`，但不得伪造 start/complete。

#### Scenario: 节点成功
- **WHEN** Perception 节点成功返回 PerceptionResult
- **THEN** 事件流中该次调用存在相邻可关联的 start 和 complete，且没有 fail

#### Scenario: 节点抛出异常
- **WHEN** Reasoning 节点在 start 后抛出异常
- **THEN** 事件流中该次调用存在 start 和一个 fail，且不存在 complete

#### Scenario: 条件分支未激活
- **WHEN** false control 分支未被 Condition 激活
- **THEN** 该分支节点没有 start/complete/fail 事件，系统可选地产生带原因的 node_skipped

### Requirement: 事件次序与运行阶段可重建
RunEvent sequence SHALL 在单次运行中严格递增，并 SHALL 使消费者能够按 run、step、phase 和 node_id 重建实际执行顺序。反馈触发、fallback 切换、运行终止和状态转换 MUST 具有结构化事件或结构化事件 payload。

#### Scenario: 跨步骤反馈事件
- **WHEN** Verifier 失败触发从步骤 0 到步骤 1 的反馈
- **THEN** 事件流记录 feedback edge、当前计数、上限、源步骤和目标步骤，且步骤 1 的节点事件 sequence 更大

#### Scenario: fallback 候选切换
- **WHEN** 当前候选失败并切换到下一候选
- **THEN** 事件流能关联逻辑 node_id、非敏感候选标识和切换结果

### Requirement: RuntimeContext 与事件上下文一致
事件生产者 SHALL 从当前运行的 RuntimeContext 和调度帧取得 run_id 与 step，不得为单个节点另建不相关的运行身份。节点 complete/fail 事件 SHALL 记录可计算耗时或明确的起止时间。

#### Scenario: 同一运行身份
- **WHEN** 一次运行产生多个节点和反馈事件
- **THEN** 所有事件 run_id 与传入各组件的 RuntimeContext.run_id 相同

#### Scenario: 节点耗时
- **WHEN** 节点调用完成
- **THEN** complete 或 fail 事件包含非负 duration 或可无歧义计算该耗时的时间字段

### Requirement: 事件只保存安全摘要
RunEvent payload SHALL 使用稳定、可序列化的输入输出摘要，并 MUST 对 secret、authorization、token、password 和显式敏感依赖值进行屏蔽。默认事件 MUST NOT 内嵌完整截图二进制、任意组件对象或不可序列化设备句柄。

#### Scenario: 组件参数包含 API key
- **WHEN** 组件绑定通过 secret provider 获得真实 API key
- **THEN** start、complete、fail、fallback 和最终 RunResult 的序列化内容均不包含该值

#### Scenario: Observation 包含截图
- **WHEN** 节点输入包含 DeviceObservation screenshot path 或图像数据
- **THEN** 默认事件只记录安全引用和必要元数据，不复制完整图像载荷

### Requirement: 结构化 RunResult 保留最终运行证据
Graph Runtime SHALL 返回可序列化 RunResult，至少包含 run_id、RunStatus、step_count、最终输出、ActionResult 列表、RunEvent 列表、最终 AgentState 安全快照和可选结构化错误。结果 MUST 区分 SUCCESS、FAILURE、STEP_LIMIT、CANCELLED 和 DEVICE_FAILURE。

#### Scenario: 成功运行结果
- **WHEN** fake device 上的 AgentGraph 显式成功终止
- **THEN** RunResult 为 SUCCESS，包含已执行动作、节点事件和最终状态快照

#### Scenario: 节点失败结果
- **WHEN** 组件节点失败且无恢复策略
- **THEN** RunResult 为 FAILURE，包含对应 fail 事件和可定位到 node_id 的结构化错误

#### Scenario: 结果可序列化
- **WHEN** 调用方把 RunResult 导出为 JSON
- **THEN** 输出不依赖 Python 对象地址且不包含组件实例、设备句柄或真实 secret

### Requirement: fake runtime 可验证完整语义
系统 SHALL 提供不依赖真实 Android 设备和外部模型的 fake ObservationProvider、fake ActionExecutor 与可编排 fake components，用于断言生命周期、输入传播、条件、反馈、事件和结果。测试 MUST 验证行为，而不能仅以代码路径被调用作为通过依据。

#### Scenario: 顺序图验收
- **WHEN** 测试执行固定输出的最小顺序图
- **THEN** 断言组件输入、调用顺序、动作结果、事件配对和最终 RunStatus 全部符合契约

#### Scenario: 反馈图验收
- **WHEN** fake Verifier 按预定序列先失败后成功
- **THEN** 测试断言发生重新观察、重新感知、反馈值进入下一步、计数正确且最终成功

#### Scenario: 异常路径验收
- **WHEN** fake component、ObservationProvider 或 ActionExecutor 注入异常
- **THEN** 测试分别断言 FAILURE 或 DEVICE_FAILURE、fail 事件以及后续节点未被执行

### Requirement: 层级节点事件可重建组合执行
RunEvent SHALL 增加稳定 `node_path`、parent activation ID 和 activation ID，使消费者能够重建 Subgraph 调用树。顶层旧节点的 `node_id` 和既有字段 MUST 保持兼容；层级 path MUST 来自逻辑身份而非随机实例 ID。

#### Scenario: Operator 子图节点事件
- **WHEN** `manager/operator` Subgraph 内的 `reasoning` 节点执行
- **THEN** start 与 complete/fail 事件共享 activation ID，并能通过 `manager/operator/reasoning` path 关联父调用

### Requirement: Interaction 与 Loop 事件维度分离
事件 SHALL 分别记录 interaction step、loop path、loop iteration 和节点 activation sequence。Local Loop iteration MUST NOT 被报告为新的设备 interaction step；feedback 推进 interaction 时 SHALL 记录源/目标 step。

#### Scenario: ReAct 两次工具调用
- **WHEN** ReAct 在 interaction step 0 内执行两个 local loop iteration
- **THEN** Tool 事件具有不同 iteration/activation，但 interaction step 均为 0

### Requirement: Router、State、Loop、Subgraph 和 Service 具有结构化事件
Router 分支选择、显式 State transition、Loop 进入/退出/耗尽、Subgraph 进入/返回/失败以及 runtime service 调用 SHALL 产生结构化安全事件。State 事件 MUST 记录 key/type/scope 和安全摘要，不得泄漏完整敏感值。

#### Scenario: Router 选择 Tool 分支
- **WHEN** Router 选择 Tool case
- **THEN** 事件记录 router node path、case ID 和目标 control port且不复制完整模型响应

#### Scenario: Subgraph 预算耗尽
- **WHEN** 子图达到预算
- **THEN** 事件记录预算类型、限制、已使用数量和父 activation，随后不出现新的子图内部 start

### Requirement: 范式模板 trace 可比较
fake template 测试 SHALL 使用语义 trace 比较节点 path、contract、branch、iteration、interaction 和终止状态，MUST 排除 timestamp、duration、随机 run/activation ID 等非确定值。

#### Scenario: Python 与 YAML ReAct 图
- **WHEN** Python 和 YAML 编译出 canonical 等价的 ReAct graph并绑定相同 fake components
- **THEN** 两次运行产生相同语义 trace

### Requirement: 真实设备事件关联 observation 与 action artifacts
Android DeviceObserve 和 ActionExecutor 的 start/complete/fail RunEvent SHALL 包含 run_id、activation identity、interaction、node path、目标设备安全标识和 artifact 安全引用。事件 MUST NOT 内嵌截图二进制、完整 UI XML、live device handle 或未经清理的 ADB 输出。

#### Scenario: 观察成功事件
- **WHEN** DeviceObserve 成功保存 screenshot 和 UI XML
- **THEN** complete 事件包含可解析到本次 run namespace 的 artifact 引用、sequence 和尺寸摘要

#### Scenario: 动作成功事件
- **WHEN** ActionExecutor 成功执行 TAP
- **THEN** complete 事件包含 action 类型、安全参数摘要和 effect_performed，不包含设备对象

#### Scenario: ADB 错误事件
- **WHEN** 设备命令失败
- **THEN** fail 事件包含错误类别、操作名称、是否发生副作用和已清理诊断，不泄漏任意命令环境或敏感文本

### Requirement: Android 失败保留截至失败点的证据
真实设备运行失败时，RunResult SHALL 保留失败前已完成的 events、ActionResults 和有效 artifact 引用，并记录失败的 node path、设备操作和结构化终止原因。系统 MUST NOT 因后续观察失败而删除此前成功写入的证据。

#### Scenario: 动作后设备断开
- **WHEN** 动作成功后设备在重新观察时断开
- **THEN** RunResult 为 DEVICE_FAILURE，保留动作前观察、成功动作结果及重新观察 fail 事件

#### Scenario: 首次观察失败
- **WHEN** 首个 DeviceObserve 无法获得截图
- **THEN** RunResult 包含该节点 start/fail 与设备诊断，且不存在伪造的 observation complete

### Requirement: 真实 smoke evidence 可被人工复核
真实 Android smoke test 的产物 SHALL 包含序列化 RunResult、按 sequence 排序的 RunEvent、至少动作前后 observation 引用和动作 effect。验收说明 MUST 给出用户可重复执行的设备预检、运行和证据查看步骤。

#### Scenario: 人工复核成功运行
- **WHEN** 用户按验收步骤执行 smoke test 并打开产物目录
- **THEN** 用户能从事件和截图顺序确认目标设备、节点执行顺序、动作副作用、动作后状态与最终 Agent outcome

#### Scenario: 只有 fake 证据
- **WHEN** 自动化 fake tests 全部通过但没有真实设备产物
- **THEN** 状态报告明确区分 fake 验证与未完成的真实 Android 验收

