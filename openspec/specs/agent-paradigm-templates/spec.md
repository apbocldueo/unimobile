# agent-paradigm-templates Specification

## Purpose
TBD - created by archiving change generalize-agent-graph-paradigms. Update Purpose after archive.
## Requirements
### Requirement: 策略由 AgentGraph 模板表达
系统 SHALL 为 Modular、Reflection、ReAct、Planner-and-Execute、UGround 和顺序 Manager/Operator/Critic Multi-Agent 提供可校验的 AgentGraph golden template。新增模板 MUST NOT 要求新增范式专用 Runtime、Kernel 分支或 `Agent.step()` 子类。

#### Scenario: Kernel 不识别范式名称
- **WHEN** 六种模板由同一个 Kernel 执行
- **THEN** Kernel 依据 contract、端口和控制结构调度，源码中不存在按这些范式名称选择流程的分支

### Requirement: 每种模板证明其关键控制语义
每种 template SHALL 使用 fake typed components/services 验证其区别性语义：Modular 组件主干、Reflection 动作后纠正、ReAct tool loop、Planner-and-Execute plan iteration/replan、UGround semantic target grounding、Multi-Agent typed message 协作。

#### Scenario: UGround 独立 Grounder 节点
- **WHEN** UGround template 执行需要定位的语义目标
- **THEN** Reasoning 输出先进入 Grounder contract，再由 grounding result 形成可执行 Action，组件内部不隐藏该连接

#### Scenario: Planner-and-Execute 触发 replan
- **WHEN** Executor step result 命中 replan 条件
- **THEN** template 通过 Router/Loop 返回 Planner，而不是由 Kernel 特判 Planner

### Requirement: 组件替换与拓扑修改正交
模板中的 ComponentBinding SHALL 可替换而不改变 NodeContract 和控制拓扑；用户 SHALL 可增删或重连合法节点而不修改组件实现或 Kernel。

#### Scenario: 替换 ReAct Reasoning
- **WHEN** 用户把 ReAct template 的 Reasoning binding 换成另一个兼容实现
- **THEN** 图仍通过校验并按相同 Router/Loop 结构执行

### Requirement: 旧策略行为作为迁移基线
旧 `ModularAgent`、`ReflectionAgent`、`MultiAgent` 和 `UGroundAgent` SHALL 保留为兼容路径和行为基线。旧 `agent_type` 只有在对应 template 的组件调用顺序、关键状态和结果通过对照测试后才能由兼容 compiler 支持；未验证类型 MUST 返回 unsupported 诊断。

#### Scenario: 未完成 parity 的旧策略
- **WHEN** 调用方请求编译尚未通过对照测试的 agent_type
- **THEN** compiler 保留旧执行路径并返回明确 unsupported，不生成近似图

### Requirement: fake 范式证据边界
范式模板测试 SHALL 证明控制流、类型传播、状态、循环、子图和事件契约，但 MUST NOT 被报告为真实 Android 稳定性、任务成功率、外部插件兼容性或 Benchmark 正确性的证据。

#### Scenario: 文档报告测试结果
- **WHEN** 六种 fake template 测试通过
- **THEN** 项目只声明 Kernel 已支持这些代表性控制结构，并继续列出真实设备和 Benchmark 未验证项

