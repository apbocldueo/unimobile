# agent-graph-canonicalization Specification

## Purpose
TBD - created by archiving change define-agent-graph-ir. Update Purpose after archive.
## Requirements
### Requirement: 执行语义 canonical projection
系统 SHALL 从已通过结构校验的 AgentGraph 生成只包含执行语义的 canonical projection。Projection MUST 包含图/契约版本、profile、节点逻辑身份、角色、生命周期、组件绑定、候选顺序、语义参数、端口契约、边、谓词、反馈策略和图策略；MUST 排除 presentation、坐标、图标、描述、创建/更新时间、运行状态、随机 UI/edge ID、设备 serial 和 Run ID。

#### Scenario: 移动画布节点
- **WHEN** 同一 Studio Agent 只改变节点坐标和缩放
- **THEN** 编译后的 canonical projection 保持不变

#### Scenario: 修改组件参数
- **WHEN** 组件的非展示参数发生变化
- **THEN** canonical projection 发生变化

### Requirement: 确定性 canonical JSON
Canonicalizer SHALL 递归排序对象键，将节点按逻辑 ID 排序，将不具备顺序语义的边按稳定语义元组排序，并以固定 UTF-8 紧凑 JSON 规则输出。系统 MUST 拒绝 NaN、Infinity、非 JSON 值和无法稳定表示的对象；具有语义的候选与策略顺序 MUST NOT 被排序破坏。

#### Scenario: 声明顺序不同
- **WHEN** 两个等价 AgentGraph 仅节点和边声明顺序不同
- **THEN** canonical JSON 字节完全相同

#### Scenario: Fallback 顺序不同
- **WHEN** 两个图的 Perception fallback 候选顺序不同
- **THEN** canonical JSON 不同

### Requirement: SHA-256 语义身份
系统 SHALL 以 canonical JSON 的 UTF-8 字节计算 SHA-256，并 SHALL 以 `sha256:<hex>` 格式返回 AgentGraph canonical hash。Hash 计算 MUST 在同一契约版本和输入语义下可重复。

#### Scenario: 重复计算 hash
- **WHEN** 同一 AgentGraph 在独立进程中重复 canonicalize
- **THEN** 两次 hash 完全相同

#### Scenario: 修改反馈上限
- **WHEN** feedback edge 的 `max_iterations` 从 1 改为 2
- **THEN** canonical hash 改变

### Requirement: 三种 authoring surface 的身份等价
Python AgentGraph、图原生 YAML 和 Studio FlowDocument SHALL 通过各自 compiler 产生同一个 canonical AgentGraph。系统 MUST 提供至少一个包含六类角色中的必需角色、一个可选角色、条件和有界反馈的三输入 golden fixture，并 MUST 同时断言 canonical mapping 与 hash 相等。

#### Scenario: 同一 Agent 的三种定义
- **WHEN** golden Agent 分别从 Python、YAML 和 Studio FlowDocument 编译
- **THEN** 三个 canonical mappings 和三个 canonical hashes 完全相同

#### Scenario: Studio 展示名称不同
- **WHEN** Studio 只修改节点展示标题而逻辑 ID 和执行配置不变
- **THEN** 其 hash 仍与 Python/YAML 定义相同

### Requirement: Secret-safe canonicalization
AgentGraph MUST 只接受结构化 secret reference 或未解析占位符进入语义配置，canonicalizer MUST NOT 读取环境变量、secrets.yaml 或运行上下文来解析密钥。安全表示和测试失败信息 MUST 对 secret-like 值进行脱敏。

#### Scenario: 两个开发者使用不同实际 API key
- **WHEN** 两个运行环境使用同名 secret reference 但真实密钥不同
- **THEN** AgentGraph canonical hash 相同且 canonical JSON 不含任一实际密钥

### Requirement: Contract version 参与身份
`contract_version` SHALL 参与 canonical form。任何可能改变端口、类型兼容、生命周期或边解释方式的不兼容契约升级 MUST 使用新 contract version，从而避免旧 hash 被错误解释为新语义。

#### Scenario: 契约版本变化
- **WHEN** 图的 contract version 改变而其他字段不变
- **THEN** canonical hash 改变

### Requirement: 新控制与组合语义参与 canonical identity
contract 1.1 canonical projection SHALL 包含 NodeContract ID/version、Router case 顺序、State 声明、Loop body/policy、Subgraph semantic content或固定 hash、端口映射、状态共享和执行预算。运行计数、activation ID、对象地址和 runtime service 实例 MUST 被排除。

#### Scenario: 修改 Loop 上限
- **WHEN** 两张图只有 local Loop max_iterations 不同
- **THEN** canonical hash 不同

#### Scenario: 仅层级展示不同
- **WHEN** 两张 Subgraph 的节点位置、标签和图标不同但执行语义相同
- **THEN** canonical hash 相同

### Requirement: 旧 V1 canonical hash 保持稳定
加载和执行 contract 1.0 图时，系统 MUST 使用既有 canonical projection，使所有已记录 golden hash 在本变更后保持完全相同。内置 role 到 NodeContract 的兼容映射不得被额外写入旧 projection。

#### Scenario: 现有 golden graph
- **WHEN** 当前 `agent_graph_v1.yaml` 在新版本中 canonicalize
- **THEN** 输出 JSON 和 SHA-256 hash 与变更前基线完全相同

### Requirement: 子图引用必须内容稳定
非内联 Subgraph reference SHALL 包含不可变版本或语义内容 hash。可变路径、未固定别名或运行时解析结果 MUST NOT 单独决定 canonical identity。

#### Scenario: 可变 latest 引用
- **WHEN** Subgraph 只引用 `latest` 且没有解析后的固定版本/hash
- **THEN** canonicalization 返回诊断而不是产生貌似稳定的 hash

