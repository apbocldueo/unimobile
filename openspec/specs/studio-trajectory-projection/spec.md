# studio-trajectory-projection Specification

## Purpose
TBD - created by archiving change implement-studio-trajectory-replay-2. Update Purpose after archive.
## Requirements
### Requirement: 双层 trajectory 因果适配
Trajectory adapter SHALL 保留 Benchmark lifecycle 与嵌套 AgentGraph event 各自的
identity、sequence 和层级，并生成具有稳定 causal index 的 normalized moments。
Adapter MUST NOT 对不同 sequence domain 进行朴素全局 timestamp 排序。

#### Scenario: Benchmark agent phase 包含 Graph events
- **WHEN** agent phase 同时有 lifecycle start/complete 和按 sequence 排序的 RunEvent
- **THEN** normalized order 为 phase start、嵌套 Graph events、phase complete，并保留
  每个来源的原始 sequence

#### Scenario: 两个来源 timestamp 交错
- **WHEN** Benchmark 与 AgentGraph timestamp 因时钟粒度或写入顺序发生交错
- **THEN** adapter 仍按声明的生命周期嵌套和 source-local sequence 产生因果顺序

### Requirement: 确定性且幂等的纯 reducer
系统 SHALL 使用一个无网络、文件系统、计时器和 React 依赖的纯 reducer，从相同 snapshot
和 normalized moments 产生相同 Replay projection。重复 moment identity MUST 幂等忽略；
identity 冲突、倒序、缺口和非法 activation transition MUST 产生结构化 integrity
diagnostic。

#### Scenario: 从零重复投影
- **WHEN** 同一 envelope 的全部 moments 被分别投影两次
- **THEN** 两次得到相同 activation history、node aggregate、observation、action、
  Benchmark state 和 failure target

#### Scenario: 重复消费一个 moment
- **WHEN** reducer 再次收到已处理且内容一致的 moment identity
- **THEN** activation、计数、usage 和历史不重复增加

#### Scenario: 缺失中间 sequence
- **WHEN** offline trajectory 在某个 source sequence 出现缺口
- **THEN** reducer 标记 projection 为 partial/corrupt，只投影已验证前缀且不猜测缺失
  节点的结果

### Requirement: Activation 事实与节点聚合分离
Projection SHALL 以 activation ID、node path、parent activation、loop path、iteration
和 interaction step 保存每次执行事实。节点视觉状态 SHALL 是一个或多个 activation
的可重建聚合；feedback、iteration 和 exhausted MUST 作为 control badge 或 annotation，
不得伪造为 activation terminal status。

#### Scenario: Feedback 后同一节点再次执行
- **WHEN** trajectory 对同一 node path 记录两次 activation 并在中间包含
  `feedback_latched`
- **THEN** projection 保留两个 activation，节点显示 feedback/count badge，第一次结果
  不被第二次覆盖

#### Scenario: Bounded loop 执行三次
- **WHEN** fake contract trajectory 对一个 loop body 记录三个不同 iteration activation
- **THEN** 节点聚合显示三次执行，Inspector 可通过 activation identity 读取每次状态和
  evidence

#### Scenario: Activation 失败
- **WHEN** 一个 activation 收到 start 后收到 fail
- **THEN** 该 activation 进入 failure，节点聚合保留 failure 和历史，不把同一节点之前
  的成功 activation 删除

### Requirement: 未执行节点不得被伪造成有理由的 skipped
只有正式 skip evidence 能将 activation 或节点标记为 skipped。旧 trajectory 最终没有
activation 的 graph node SHALL 显示 `not observed` 或等价不确定状态，MUST NOT 从显示
标题、分支名称或未出现事件推断具体 skip reason。

#### Scenario: 旧分支运行没有 skip event
- **WHEN** final trajectory 中一个 graph node 从未 activation 且不存在正式 skip evidence
- **THEN** projection 将其标记为 not observed，不声称它因某个 condition 被 skipped

#### Scenario: 未来事件包含正式 skip
- **WHEN** normalized moment 明确携带兼容 schema 的 skip status 和 node identity
- **THEN** 同一 reducer 将节点/activation 投影为 skipped，并保留其正式 reason

### Requirement: Observation 和 Action 按 cursor 因果可见
Projection SHALL 仅使用当前 causal cursor 之前已经确认的 observation 和 action。
Virtual Phone 的 current observation MUST 与 observation identity 和 interaction step
绑定，不能显示未来截图或在缺失时把上一张冒充当前。

#### Scenario: Observation 完成前播放到节点 start
- **WHEN** cursor 位于 DeviceObserve start 与包含 screenshot reference 的 complete 之间
- **THEN** current observation 不提前切换到尚未完成的截图

#### Scenario: 当前 interaction 没有 screenshot
- **WHEN** cursor 进入一个没有可用 screenshot artifact 的 interaction
- **THEN** projection 返回明确 missing/not_captured 状态，并将上一张标记为历史而不是
  当前

#### Scenario: Action 后出现新 Observation
- **WHEN** action complete 之后、后置 observation complete 之前移动 cursor
- **THEN** projection 显示最新 action，同时保持前一张 observation 的历史标记，直到新
  observation 因果可见

### Requirement: Agent 结果与 Benchmark 结果独立投影
Projection SHALL 分别保存 Agent RunStatus/kernel status 与 Benchmark
PASS/FAIL/INVALID/SKIPPED、phase status 和 evaluation evidence。一个结果 MUST NOT
覆盖、改写或着色为另一个结果。

#### Scenario: Agent SUCCESS 但 Benchmark FAIL
- **WHEN** RunResult status 为 success 而 evaluation `is_pass` 为 false
- **THEN** projection 同时报告 Agent SUCCESS 与 Benchmark FAIL，Agent 成功节点不因
  evaluation 失败被改成 failure

#### Scenario: Agent FAILURE 导致 evaluation skipped
- **WHEN** Agent activation 失败且 Benchmark evaluation phase 为 skipped
- **THEN** projection 保留 Agent failure 和 Benchmark skipped 两个事实，并显示各自原因

### Requirement: 可复现的失败跳转目标
Projection SHALL 计算稳定 failure targets，优先级依次为首次 Agent activation failure、
Agent terminal failure、Benchmark evaluation failure 和其他 Benchmark infrastructure
failure。计算 MUST 基于正式事件和结果，不进行自动根因诊断。

#### Scenario: Reasoning activation 失败
- **WHEN** trajectory 中 Reasoning 首先产生 fail event
- **THEN** 首要 failure target 指向该 activation、node path 和 causal cursor

#### Scenario: 只有 Benchmark evaluation 失败
- **WHEN** Agent 完成成功且唯一失败是 Benchmark evaluation
- **THEN** 首要 failure target 指向 evaluation phase，不指向任意 Agent 节点

### Requirement: Replay 与未来 live 共用事实投影合同
Reducer 输入 SHALL 与传输方式无关，能够消费 trajectory adapter 或未来 event query/SSE
adapter 产生的相同 normalized moments。Stage 2 MUST 提供最终 projection fixture，供
后续 live 完成状态与从零 Replay 状态做一致性验证。

#### Scenario: 同一事实来自不同 adapter
- **WHEN** fake live adapter 和 Replay adapter 生成 identity、顺序和内容等价的 moments
- **THEN** reducer 产生相同 node state、activation history、current observation 和
  terminal result

