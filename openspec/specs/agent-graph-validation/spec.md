# agent-graph-validation Specification

## Purpose
TBD - created by archiving change define-agent-graph-ir. Update Purpose after archive.
## Requirements
### Requirement: 分层且确定的图诊断
系统 SHALL 在不实例化组件和设备的情况下执行 AgentGraph 结构、端口、profile、可达性、循环与反馈校验，并 SHALL 返回包含稳定错误码、严重级别、节点/边标识和精确字段路径的确定性诊断集合。系统 MUST 尽可能一次返回所有独立问题，而不是只报告首个错误。

#### Scenario: 一个图包含多个独立错误
- **WHEN** 图同时包含未知端口、缺失必需角色和不可达节点
- **THEN** validator 一次返回三个可定位诊断且顺序稳定

#### Scenario: 无设备环境验证
- **WHEN** 在没有 ADB、模型凭据和可选模型依赖的环境中验证 AgentGraph
- **THEN** 校验完成且不产生设备、网络或模型副作用

### Requirement: 节点、端口和边结构校验
Validator SHALL 检查节点 ID 唯一性、节点种类、角色与绑定一致性、边端点存在性、方向、端口存在性和输入基数。Data edge 的源类型 MUST 能赋值给目标端口接受类型，control 和 feedback edge MUST 遵守各自端点约束。

#### Scenario: 不兼容数据类型
- **WHEN** `plan_result` 输出连接到只接受 `device_observation` 的端口
- **THEN** validator 返回类型不兼容诊断并标识源、目标和两个类型

#### Scenario: 单值端口有多个输入
- **WHEN** 两条 data edge 连接到 cardinality 为 single 的同一输入端口
- **THEN** validator 拒绝该图并列出冲突边

### Requirement: Mobile Agent profile 必需性校验
默认 `mobile_agent` profile SHALL 要求至少一个 Perception、至少一个 Reasoning、恰好一个主要 ActionExecutor，以及可用的任务与 Observation 输入来源。每个存在节点的必需端口 MUST 由 data edge、图输入或契约声明的 Runtime binding 满足。

#### Scenario: 缺少 ActionExecutor
- **WHEN** 图具有 Perception 和 Reasoning 但没有主要 ActionExecutor
- **THEN** profile 校验返回缺失必需角色诊断

#### Scenario: 可选 Planner 缺席
- **WHEN** 图不包含 Planner 且 Reasoning 的 plan 端口为可选
- **THEN** validator 不产生缺失 Planner 或 plan 输入错误

### Requirement: 可达性与终止路径校验
Validator SHALL 从图输入和生命周期入口计算可达节点，并 SHALL 报告不可达节点、孤立组件、永远不能激活的条件分支以及无法到达 ActionExecutor、Output 或显式终止语义的非终止死路。

#### Scenario: 孤立 Memory 节点
- **WHEN** Memory 节点既不接收写入也不向任何消费者提供 context
- **THEN** validator 报告该节点不可参与运行

#### Scenario: Reasoning 输出无消费者
- **WHEN** Reasoning 产生 Action 但没有路径到 ActionExecutor 或终止输出
- **THEN** validator 报告非终止死路

### Requirement: 普通子图必须无环
Validator SHALL 在移除所有 feedback edge 后对剩余 data 和 control 子图执行循环检测。剩余子图 MUST 是 DAG；任何由普通边形成的循环 MUST 被拒绝并返回可读循环路径。

#### Scenario: Memory 与 Reasoning 普通边成环
- **WHEN** Memory 和 Reasoning 通过普通 data/control edges 构成循环
- **THEN** validator 拒绝该图并提示使用具备明确语义的 feedback edge 或重新建模状态通道

#### Scenario: 无环普通图
- **WHEN** 移除 feedback edges 后所有节点可拓扑排序
- **THEN** 普通循环校验成功

### Requirement: Feedback edge 必须形成受支持的真实反馈环
每条 feedback edge SHALL 从允许产生反馈的结果或 Condition 分支指向类型兼容的后续迭代输入，并 MUST 与非 feedback 路径共同形成真实返回环。V1 Validator MUST 拒绝缺少返回路径、超过系统上限、目标不兼容或形成嵌套/重叠反馈环的结构。

#### Scenario: 合法单一反馈环
- **WHEN** Reasoning 到 ActionExecutor 到 Verifier 存在普通路径且 Verifier 通过有界 feedback edge 返回 Reasoning
- **THEN** feedback 校验成功

#### Scenario: 反馈边没有正向路径
- **WHEN** feedback edge 的目标无法通过普通路径到达其源
- **THEN** validator 报告该边不是可执行的真实反馈环

#### Scenario: 重叠反馈环
- **WHEN** 两条 feedback edges 产生共享节点且无法独立计数的重叠循环
- **THEN** V1 validator 以不支持的图结构拒绝该配置

### Requirement: Predicate 静态校验
Validator SHALL 检查结构化谓词操作符、字段路径存在性（在可知 schema 范围内）以及比较值类型。未知操作符、明显不存在的稳定字段或不兼容比较 MUST 在运行前失败。

#### Scenario: Verifier 布尔字段比较
- **WHEN** 谓词比较 `VerifierResult.is_success` 与布尔值
- **THEN** predicate 校验成功

#### Scenario: 数值操作符比较字符串
- **WHEN** `gt` 操作符用于已知字符串字段和非数值比较
- **THEN** validator 返回谓词类型错误

### Requirement: 可直接消费的校验结果
Validator SHALL 返回包含 `is_valid`、errors 和 warnings 的稳定结果对象，并 SHALL 提供安全 JSON 表示供 CLI、测试和 Studio 使用。诊断 MUST NOT 包含完整 prompt、密钥值或任意插件对象 repr。

#### Scenario: Studio 显示端口错误
- **WHEN** Studio 后端请求校验一个端口类型错误的 FlowDocument 编译结果
- **THEN** 返回的安全诊断包含逻辑节点和端口标识，足以在画布中定位错误

### Requirement: NodeContract 解析先于端口校验
Validator SHALL 使用内置与显式注入 catalog 解析每个 contract reference，再检查端口、数据类型、基数、执行特征和组件 binding compatibility。未知 contract MUST 在任何组件解析或运行服务调用前失败。

#### Scenario: 未注入 Tool 契约
- **WHEN** 图引用 Tool contract 但 validator catalog 不包含该版本
- **THEN** 校验返回包含 node ID、contract ID 和 version 的稳定诊断

### Requirement: Router 与 State 静态校验
Validator SHALL 检查 Router case 顺序、predicate 字段和类型、唯一 default、输出映射，以及 State key、类型、作用域、初值和读写兼容性。

#### Scenario: Router 缺少 default
- **WHEN** Router 声明多个 cases 但没有 default output
- **THEN** 执行前校验失败

#### Scenario: State 类型冲突
- **WHEN** 节点向声明为 plan_result 的 state key 写入 action
- **THEN** validator 返回源端口与 state 类型不兼容诊断

### Requirement: Local Loop 结构和预算校验
Validator SHALL 拒绝未封装在 Loop 或 legacy feedback 中的普通循环，并检查 Loop body、输入输出映射、until predicate、正数 max_iterations、exhausted policy 和有限预算。嵌套 Loop MUST 遵守图级深度和总预算限制。

#### Scenario: 无界 ReAct 循环
- **WHEN** ReAct tool loop 未声明 max_iterations
- **THEN** 模型或 validator 在绑定前拒绝该图

### Requirement: Subgraph 引用与递归校验
Validator SHALL 解析 inline 或固定语义 Subgraph reference，验证父子端口映射、状态共享、预算和 contract version，并拒绝直接/间接递归、可变未固定引用和超过深度限制的组合。

#### Scenario: 父子端口不兼容
- **WHEN** 父图把 action 端口连接到子图声明的 task_input
- **THEN** validator 返回包含父节点 path 和子图 input 的类型诊断

#### Scenario: 递归引用链
- **WHEN** A 引用 B、B 引用 C、C 引用 A
- **THEN** validator 返回完整引用链且不进入 binding

### Requirement: 通用 Kernel profile 不强制 Modular 角色集合
contract 1.1 通用图校验 SHALL 依据 contract、端口、显式服务和终止路径判断可运行性，不得无条件要求 Perception、Reasoning 或 ActionExecutor。旧 `mobile_agent` contract 1.0 profile 的必需角色校验 MUST 保持兼容。

#### Scenario: 纯 Tool ReAct 子图
- **WHEN** 一个有限 local subgraph 只包含 Reasoning、Router 和 Tool 且将 decision 返回父图
- **THEN** 通用校验不因缺少 ActionExecutor 拒绝该子图

