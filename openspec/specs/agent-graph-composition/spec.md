# agent-graph-composition Specification

## Purpose
TBD - created by archiving change generalize-agent-graph-paradigms. Update Purpose after archive.
## Requirements
### Requirement: Subgraph 具有类型化公开边界
Subgraph 节点 SHALL 声明子图内容或固定语义引用、typed input/output mapping、状态共享策略和执行预算。父图只能通过声明端口与子图交换值，MUST NOT 依赖子图内部随机节点 ID 或隐藏全局变量。

#### Scenario: Operator 子图返回 Action proposal
- **WHEN** 父图把 Task、Plan 和 Observation 输入 Operator subgraph
- **THEN** 子图只通过声明输出返回 Action proposal，父图不能直接读取其私有中间节点

### Requirement: 子图状态隔离与显式共享
Subgraph SHALL 默认拥有隔离的 subgraph state。需要共享的 run state 或 runtime service MUST 在图中显式声明；子图 private AgentState MUST NOT 被兄弟子图隐式修改。

#### Scenario: Manager 与 Critic 私有历史
- **WHEN** Manager 和 Critic subgraph 各自写入 private message history
- **THEN** 两份历史保持隔离，只有显式输出的 message 可被另一子图消费

### Requirement: 层级身份和确定性事件
每个 Subgraph activation SHALL 产生稳定层级 node path、父 activation ID 和独立预算信息。相同语义图在相同输入下 MUST 产生可复现的层级调用顺序；随机 canvas ID 和 Python 对象地址不得进入身份。

#### Scenario: 层级 Reasoning 事件
- **WHEN** `manager/operator` 子图中的 `reasoning` 节点执行
- **THEN** RunEvent 能以类似 `manager/operator/reasoning` 的稳定 path 定位该调用

### Requirement: 递归与预算受静态和运行时约束
Validator SHALL 拒绝直接或间接递归 Subgraph 引用。每个 Subgraph MUST 声明或继承有限 activation/iteration budget；运行时达到预算时 SHALL 产生结构化失败或声明的边界策略。

#### Scenario: 间接递归
- **WHEN** graph A 引用 graph B 且 graph B 再引用 graph A
- **THEN** 执行前校验返回完整引用链且不进入绑定

#### Scenario: 子图预算耗尽
- **WHEN** 子图达到 activation budget 仍未返回
- **THEN** Kernel 停止该子图，不启动后续内部节点，并把错误传播到父节点策略

### Requirement: 第一版 Multi-Agent 使用确定性顺序协作
本能力 SHALL 支持多个 Agent subgraph 通过 typed message、plan、proposal 和 critique 顺序协作。第一版 MUST NOT 并行调度多个 Agent，也 MUST NOT 允许多个子图无仲裁地并发执行设备副作用。

#### Scenario: Manager、Operator、Critic 顺序运行
- **WHEN** Multi-Agent 模板执行一次协作循环
- **THEN** Manager 先输出 plan，Operator 再输出 proposal，Critic 最后决定 revise、execute 或 finish

