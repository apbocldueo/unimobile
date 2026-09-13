# agent-graph-contract Specification

## Purpose
TBD - created by archiving change define-agent-graph-ir. Update Purpose after archive.
## Requirements
### Requirement: AgentGraph V1 版本化封装
系统 SHALL 提供严格、可序列化且无运行副作用的 `AgentGraph` V1 模型。该模型 MUST 包含 `schema_version`、`contract_version`、`profile`、节点集合、边集合和图策略，并 SHALL 将执行语义与可选的展示信息分离。

#### Scenario: 构造最小图
- **WHEN** Python 调用方使用版本 1、`mobile_agent` profile、合法节点、边和策略构造 AgentGraph
- **THEN** 模型构造成功且不发现插件、不连接设备、不读取密钥、不创建运行目录

#### Scenario: 拒绝未知图字段
- **WHEN** AgentGraph 执行语义对象包含契约未声明的字段
- **THEN** 结构校验失败并返回该字段的精确路径

### Requirement: 固定六类核心 Agent 角色
`mobile_agent` profile SHALL 保留六类面向用户的稳定核心契约：`perception`、`planner`、`reasoning`、`memory`、`action_executor` 和 `verifier`。系统 MUST 将 `Action` 视为 Reasoning 产生的数据对象，将 `action_executor` 视为执行该对象的组件契约；LLM、Grounder、Device、BenchmarkInitializer 和 Evaluator MUST NOT 被误报为六类核心角色。六类核心契约 MUST NOT 被解释为 AgentGraph 允许出现的封闭全集，图 MAY 通过显式 NodeContract catalog 使用基础设施或扩展契约。

#### Scenario: 查询核心角色目录
- **WHEN** 调用方读取 AgentGraph 核心角色目录
- **THEN** 系统按稳定标识返回且只返回六类核心角色，同时通过独立 contract catalog 暴露扩展契约

#### Scenario: 区分 Action 与 ActionExecutor
- **WHEN** 图中 Reasoning 的 `action` 输出连接到动作执行组件
- **THEN** 目标节点契约为 `action_executor` 且其输出数据类型为 `action_result`

#### Scenario: 图使用 Grounder 扩展契约
- **WHEN** AgentGraph 引用显式 catalog 中的 Grounder NodeContract
- **THEN** profile 不因其不是六类核心角色而拒绝该节点

### Requirement: 节点种类与逻辑身份
AgentGraph SHALL 支持 `component`、`input`、`condition`、`router`、`state`、`subgraph`、`loop` 和 `output` 节点。每个节点 MUST 拥有图内唯一、稳定且与 UI 实例 ID 分离的逻辑 `id`；组件节点 MUST 声明 NodeContract、执行策略和组件绑定，内置控制/组合节点 MUST 使用各自结构化契约而非伪装成插件组件。子图内部节点 SHALL 通过父级 path 获得稳定层级身份。

#### Scenario: 同一逻辑节点具有不同画布实例 ID
- **WHEN** authoring surface 的随机实例 ID 与逻辑 ID 不同
- **THEN** compiler 使用逻辑 ID 作为 AgentGraph 节点 ID且 presentation ID 不影响语义身份

#### Scenario: 重复逻辑 ID
- **WHEN** 同一图作用域内两个节点声明相同逻辑 ID
- **THEN** AgentGraph 结构校验在执行前拒绝该图

#### Scenario: 子图中同名节点
- **WHEN** 两个不同子图各自包含 logical ID 为 `reasoning` 的节点
- **THEN** 系统通过不同父级 node path 区分它们且不把它们视为同一节点

### Requirement: 组件绑定与有序候选
组件节点 SHALL 使用包含 namespace、name、可选版本、参数和依赖引用的组件绑定。绑定 MAY 包含有序候选列表和显式 fallback 策略；候选顺序属于执行语义并 MUST 被保留。已解析的密钥值 MUST NOT 作为组件绑定字段进入 AgentGraph。

#### Scenario: 保留 Perception fallback 顺序
- **WHEN** 一个 Perception 节点绑定多个有序候选并声明 fallback 策略
- **THEN** AgentGraph 保留候选顺序且 canonical form 将顺序视为有意义

#### Scenario: 使用密钥引用
- **WHEN** 组件参数需要 API key
- **THEN** AgentGraph 保存结构化 secret reference 或未解析占位符，而不是保存实际密钥值

### Requirement: 稳定类型化端口目录
系统 SHALL 从一个后端端口目录定义角色与内置节点的输入、输出、数据类型、必需性和基数。V1 MUST 至少定义 `task_input`、`device_observation`、`plan_result`、`perception_result`、`memory_context`、`action`、`action_result`、`verifier_result`、`control` 和 `run_result` 类型，且 Studio 不得成为端口语义的独立来源。

#### Scenario: Verifier 输出类型
- **WHEN** 调用方检查 Verifier 节点的输出端口
- **THEN** 端口类型为 `verifier_result` 而不是 `verified_plan`

#### Scenario: Perception 输入类型
- **WHEN** 调用方检查 Perception 节点的输入端口
- **THEN** 端口接收完整 `device_observation` 而不是仅接收截图字符串

### Requirement: 三类边的明确语义
AgentGraph SHALL 区分 `data`、`control` 和 `feedback` 边。Data edge MUST 在兼容端口间传递业务值，control edge MUST 只控制节点激活，feedback edge MUST 表示跨迭代的有界反馈；系统 MUST NOT 使用通配数据类型模拟条件分支的数据传递。

#### Scenario: Data edge 传递感知结果
- **WHEN** Perception 输出连接到 Reasoning 的感知输入
- **THEN** 边类型为 data 且携带 `perception_result`

#### Scenario: 条件分支不传递任意数据
- **WHEN** Condition 的 true 分支激活一个节点
- **THEN** 分支使用 `control` 边，业务数据通过独立 data edge 提供

### Requirement: Mobile Agent 生命周期
旧 contract 1.0 组件节点 SHALL 继续支持 `on_run_start`、`per_step`、`post_action`、`stateful` 和 `terminal` 生命周期，以保持 Planner、Perception/Reasoning、Verifier 和 Memory 的既有语义。contract 1.1 图 SHALL 以通用 execution policy、activation、State scope、Loop 和 Subgraph 表达调度，不得要求 GraphExecutionKernel 把核心角色映射到固定 Mobile 阶段。兼容 facade MUST 能把旧生命周期确定性转换为 Kernel execution plan。

#### Scenario: Planner 只在任务开始运行
- **WHEN** contract 1.0 Planner 节点生命周期为 `on_run_start`
- **THEN** compatibility facade 使其每个 Run 至多激活一次并复用 PlanResult

#### Scenario: 新图每轮重新规划
- **WHEN** Planner contract 节点位于显式 Loop body 且受 activation control 驱动
- **THEN** Kernel 按图结构多次调用 Planner而不依赖 Planner 角色特判

#### Scenario: Verifier 校验前后状态
- **WHEN** 图显式连接动作前后 Observation、Action 和 ActionResult 到 Verifier
- **THEN** Verifier 按端口就绪执行，Kernel 不通过固定 `post_action` 角色分支猜测输入

### Requirement: 结构化条件谓词
Condition 节点和条件边 SHALL 使用由字段路径、受支持操作符和值构成的结构化谓词。V1 MUST 至少支持 `eq`、`ne`、`truthy`、`falsy`、`exists`、`gt`、`gte`、`lt` 和 `lte`，并 MUST NOT 执行 YAML、JSON 或 Studio 提供的任意 Python/JavaScript 表达式。

#### Scenario: 根据 Verifier 结果分支
- **WHEN** 条件谓词声明 `field: is_success`、`operator: eq`、`value: false`
- **THEN** 系统把它保存为可校验结构而不是动态求值代码字符串

#### Scenario: 拒绝可执行表达式
- **WHEN** 条件配置尝试提供 `eval(...)` 或任意脚本
- **THEN** 契约校验拒绝该配置且不执行表达式

### Requirement: 有界反馈策略
每条 feedback edge SHALL 显式声明触发谓词、`max_iterations` 和 `on_exhausted`。`max_iterations` MUST 是 1 到 10 的整数，`on_exhausted` MUST 是 `fail`、`continue` 或 `terminate`；反馈数据 MUST 由源端口类型安全地提供给目标端口。

#### Scenario: 合法验证反馈
- **WHEN** Verifier 失败结果通过 feedback edge 返回 Reasoning 且最大反馈次数为 2
- **THEN** AgentGraph 契约接受该有界反馈策略

#### Scenario: 无界反馈
- **WHEN** feedback edge 未声明最大次数或声明非正数
- **THEN** 契约校验在运行前拒绝该图

### Requirement: 可选角色不等于忽略失败
Planner、Memory 和 Verifier MAY 不出现在一个具体 AgentGraph 中，Reasoning 对应输入 SHALL 因此允许缺省；Perception、Reasoning 和主要 ActionExecutor SHALL 构成默认最小可运行角色集合。节点一旦存在，其执行失败 MUST NOT 因角色可选而被隐式忽略。

#### Scenario: 无 Planner 的反应式 Agent
- **WHEN** 图包含 Perception、Reasoning 和 ActionExecutor，但不包含 Planner
- **THEN** profile 校验允许 Reasoning 的计划输入为空

#### Scenario: 可选节点运行失败
- **WHEN** 已存在的 Verifier 节点在未来 Runtime 中执行失败且没有显式错误策略
- **THEN** 可选角色声明不授权 Runtime 静默跳过该失败

### Requirement: 组件节点引用版本化 NodeContract
contract 1.1 的组件节点 SHALL 引用稳定 contract ID 和版本；旧核心 role SHALL 有无歧义的内置 contract 映射。NodeContract reference、execution policy 和层级组合字段属于执行语义，MUST 与 presentation 分离。

#### Scenario: 旧 role 映射核心契约
- **WHEN** 系统加载 contract 1.0 的 `role: reasoning` 节点
- **THEN** compatibility model 将其视为内置 Reasoning contract 且不改变旧序列化或 canonical hash

