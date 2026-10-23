# agent-graph-control-flow Specification

## Purpose
TBD - created by archiving change generalize-agent-graph-paradigms. Update Purpose after archive.
## Requirements
### Requirement: Run、Interaction、Activation 与 Iteration 分离
系统 SHALL 区分完整 Run、物理设备 Interaction Step、节点 Activation 和 Local Loop Iteration。一次 Interaction Step MAY 包含多个组件、工具和子图 activation；local iteration MUST NOT 自动增加 interaction step 或触发设备观察。

#### Scenario: ReAct 在动作前调用两个工具
- **WHEN** ReAct local loop 在产生设备 Action 前依次调用两个 Tool 节点
- **THEN** 事件记录多个 activation 和 iteration，但仍属于同一个 interaction step

### Requirement: 结构化多路 Router
Router SHALL 按声明顺序对 typed input 求值结构化 cases，并在一次 activation 中只激活第一个命中的分支；Router MUST 声明 default 分支，且 MUST NOT 执行配置提供的任意代码。

#### Scenario: Tool、Action 与 Finish 三路路由
- **WHEN** Reasoning decision 匹配 Tool case
- **THEN** Router 只激活 Tool control output，不激活 Action 或 Finish output

#### Scenario: 无 case 命中
- **WHEN** 输入不匹配任何声明 case
- **THEN** Router 激活 default 分支并记录选择依据

### Requirement: 类型化作用域状态
系统 SHALL 提供显式 StateStore，状态声明 MUST 包含稳定 key、数据类型、作用域和初值/缺省语义。首版 SHALL 支持 `run`、`interaction`、`subgraph` 和 `loop` 作用域；读写 MUST 经声明的端口或状态操作发生。

#### Scenario: Planner 保存计划游标
- **WHEN** Planner-and-Execute 图把 current plan index 写入 run scope
- **THEN** 后续 loop iteration 可读取该值且其他未授权 scope 不会获得隐式副本

#### Scenario: Loop 状态退出后清理
- **WHEN** local Loop 完成
- **THEN** loop-scoped 状态不泄漏到后续独立 loop，run-scoped 状态继续存在

### Requirement: Local Loop 是有界结构化控制流
Local Loop SHALL 引用一个 body subgraph、显式输入输出映射、until predicate、正整数 `max_iterations` 和 exhausted policy。普通 data/control edge MUST NOT 形成未声明循环；local Loop MUST NOT 隐式执行设备观察或推进 interaction step。

#### Scenario: ReAct 工具循环正常退出
- **WHEN** loop body 的 Router 产生 device-action decision 且 until predicate 命中
- **THEN** Loop 输出该 decision 并在未超过上限时结束

#### Scenario: Local Loop 耗尽
- **WHEN** loop 达到 max_iterations 仍未命中退出条件
- **THEN** 系统执行声明的 fail、continue 或 terminate 策略并保留 iteration 证据

### Requirement: Interaction feedback 与 Local Loop 语义独立
现有 feedback edge SHALL 继续表示跨 Interaction Step 的有界反馈，并在下一 step 重新经过显式或兼容观察链。Local Loop SHALL 表示同一 interaction 内部的控制迭代；两者的计数、事件和 exhausted policy MUST 独立。

#### Scenario: Verifier 触发下一次设备观察
- **WHEN** 动作后 Verifier feedback 命中
- **THEN** Runtime 推进 interaction step 并重新观察，而不是把它计为当前 local loop iteration

