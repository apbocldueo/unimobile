# agent-graph-compilation Specification

## Purpose
TBD - created by archiving change define-agent-graph-ir. Update Purpose after archive.
## Requirements
### Requirement: Compiler 输出统一且可追踪
系统 SHALL 为每种受支持的 authoring surface 提供显式 compiler，输出 AgentGraph、
canonical identity、source-to-graph 映射和编译诊断。Compiler MUST 先严格解析源格式，
再建立稳定逻辑 ID、映射 NodeContract、typed ports 和节点语义，最后调用同一个
AgentGraph validator；它 MUST NOT 实例化组件、解析真实密钥、连接设备、调用模型或
写持久化存储。

Studio source map SHALL 能定位 document ID、nested canvas path、canvas node/edge ID、
logical node path、contract port ID 和 document property path。Presentation locator
MUST NOT 进入 AgentGraph canonical identity。

#### Scenario: 编译失败可定位回源文档
- **WHEN** Studio 某个节点产生 AgentGraph 端口错误
- **THEN** 编译结果能把诊断映射回对应 Studio document、canvas node/edge 和 contract
  port

#### Scenario: 嵌套 Subgraph 编译失败
- **WHEN** inline Subgraph 内的节点配置无效
- **THEN** source map 保留父级 canvas path、内部 canvas node 和 logical node path，
  前端无需通过字符串猜测定位

#### Scenario: 编译保持无副作用
- **WHEN** Studio 文档引用合法组件、SecretRef 和设备服务 contract
- **THEN** compiler 仅使用显式 Catalog 声明完成验证，不实例化组件、不解析 secret、
  不连接设备且不写 SQLite

### Requirement: Python AgentGraph 构造入口
Python 用户 SHALL 能够使用公开的 AgentGraph 模型、节点、端口、边、Predicate 和 FeedbackPolicy 直接构造并 canonicalize 图，而无需 YAML 或 Studio。该入口 MUST 与未来 AgentBuilder 分离，且本能力不要求提供完整链式 Builder DSL。

#### Scenario: 纯 Python 构造图
- **WHEN** 用户用公开模型创建合法 Mobile Agent 图
- **THEN** 系统返回通过校验且可 hash 的 AgentGraph

### Requirement: 图原生 YAML 编译
系统 SHALL 定义带独立 schema version 和 contract version 的图原生 Agent YAML，能够声明逻辑节点、NodeContract/组件绑定、typed edges、Router、State、Local Loop、Subgraph、条件、interaction feedback 和图策略，并 SHALL 无损编译为对应 AgentGraph。Graph YAML 的 schema version MUST 与旧 AgentConfig V1 明确区分；扩展 contract 校验 MUST 使用显式注入 catalog且不得自动导入插件。

#### Scenario: 编译 Graph YAML
- **WHEN** 图原生 YAML 声明合法组件节点、类型化边和有界反馈
- **THEN** compiler 生成语义等价的 AgentGraph

#### Scenario: 编译 contract 1.0 Graph YAML
- **WHEN** 现有图原生 YAML 声明合法核心 role、类型化边和有界 feedback
- **THEN** compiler 生成与变更前 canonical hash 相同的 AgentGraph V1

#### Scenario: 编译 contract 1.1 ReAct YAML
- **WHEN** Graph YAML 声明 Reasoning、Router、Tool contract 和有界 local Loop
- **THEN** compiler 使用显式 catalog 生成可校验且可 canonicalize 的组合图

#### Scenario: 把旧 YAML 误当 Graph YAML
- **WHEN** 文档声明 AgentConfig V1 envelope
- **THEN** loader 路由到兼容 compiler 而不是按图原生 schema 猜测字段

### Requirement: Studio FlowDocument 编译
Studio compiler SHALL 严格把 `StudioFlowDocument` schema 2 / AgentGraph contract 1.1
语义编译为 canonical AgentGraph。它 SHALL 支持 contract-ref component、single/fallback
binding、input、output、condition、router、state、loop、subgraph、GraphInterface、
GraphPolicies、typed data/control edge 和 bounded feedback。

Compiler SHALL 把 stable logical ID 与 canvas ID 分离，从显式 NodeContract Catalog
解析稳定 port ID，并递归编译 inline nested document。它 MUST 排除位置、图标、描述、
viewport、主题、时间戳和 revision 等 presentation/authoring 字段，MUST 拒绝无法安全
映射的 wildcard、VerifiedPlan、动态表达式和未知 contract。

#### Scenario: 编译 contract 1.1 component
- **WHEN** Studio schema 2 节点声明 exact NodeContract ref 和一个合法 component binding
- **THEN** compiler 生成对应 contract 1.1 component node 并保留 candidate 顺序、版本、
  params、dependencies 和 execution policy

#### Scenario: 编译 Router、State、Loop 和 Subgraph
- **WHEN** Studio 文档声明 structured Router、typed State、bounded Loop 和 nested
  Subgraph
- **THEN** compiler 生成语义等价的 contract 1.1 结构并通过公共 validator

#### Scenario: 只修改 presentation
- **WHEN** 用户只修改节点位置、viewport、label、icon 或折叠状态
- **THEN** Studio document revision 可以变化，但 canonical graph mapping/hash 不变

#### Scenario: 无效端口或未知 contract
- **WHEN** edge 引用不存在的 contract port，或 component 引用未注入 Catalog 的 contract
- **THEN** compiler 返回精确 source diagnostic 且不生成可运行 AgentGraph

#### Scenario: schema 1 迁移
- **WHEN** importer 收到 FlowDocument schema 1 / contract 1.0
- **THEN** 系统通过显式 migrator 产生 schema 2 草稿或 migration diagnostics，不在
  contract 1.1 compiler 内静默猜测旧字段

#### Scenario: Action 节点编译
- **WHEN** Studio schema 2 FlowDocument 包含配置为 exact action executor contract 的
  Action 卡片
- **THEN** compiler 生成使用稳定 typed action/action-result ports 的 component 节点

#### Scenario: 旧 VerifiedPlan 端口
- **WHEN** schema 1 FlowDocument 使用无法无歧义映射的 `verifiedPlan` 或 wildcard 分支
  传递业务数据
- **THEN** migrator/compiler 返回迁移诊断，而不是生成错误的 contract 1.1 AgentGraph

### Requirement: 稳定逻辑 ID 规则
所有 compiler SHALL 保留显式逻辑 ID。对于默认 profile 中唯一的核心角色，compiler MAY 确定性地以角色名补全逻辑 ID；当同一角色出现多个节点或补全存在歧义时，源文档 MUST 显式提供逻辑 ID。

#### Scenario: 唯一 Reasoning 自动命名
- **WHEN** 源定义仅有一个 Reasoning 且没有逻辑 ID
- **THEN** compiler 可确定性地使用 `reasoning`

#### Scenario: 多个 Reasoning 缺少 ID
- **WHEN** 源定义含多个 Reasoning 且未提供稳定逻辑 ID
- **THEN** compiler 拒绝生成依赖声明顺序或随机值的身份

### Requirement: AgentConfig V1 兼容编译
系统 SHALL 保留现有 AgentConfig V1 loader 和 canonical mapping，并 SHALL 为明确支持的 `modular_agent` 配置提供兼容 compiler。Compiler MUST 将现有 Perception 列表保留为有序 fallback 绑定，将 Planner、Reasoning、Memory 和 Verifier 映射为对应节点，并在旧配置没有动作组件时注入稳定的内置 legacy ActionExecutor 引用。

#### Scenario: 编译现有 ModularAgent YAML
- **WHEN** 一个通过现有契约和 registry validation 的 `modular_agent` AgentConfig V1 被请求编译
- **THEN** compiler 生成包含等价组件选择、参数、fallback 顺序和默认动作执行边界的 AgentGraph

#### Scenario: Benchmark JSON 不参与 AgentGraph
- **WHEN** 编译 AgentConfig V1
- **THEN** compiler 不读取、合并或转换 BenchmarkTask JSON

### Requirement: 未支持旧架构安全降级
Reflection、MultiAgent、UGround 或其他旧 AgentConfig 只有在对应 graph template 已通过行为对照测试后才能由兼容 compiler 支持。尚未验证的类型 MUST 继续保留旧构建与执行路径；compiler MUST 返回明确 unsupported-compilation 诊断，且 MUST NOT 生成近似线性图或阻止旧 YAML 运行。

#### Scenario: 编译尚未支持的 MultiAgent
- **WHEN** 调用方请求把尚未完成行为等价验证的 `multi_agent` V1 配置编译为 AgentGraph
- **THEN** compiler 返回明确的不支持诊断且原 AgentConfig 仍可交给旧 AgentFactory

#### Scenario: 已验证 Reflection template
- **WHEN** Reflection template 已通过旧/新调用顺序、反馈状态和 Action 对照，且用户请求编译 `reflection_agent`
- **THEN** compiler 可使用稳定模板填充配置中的组件 binding

#### Scenario: 尚未验证的 MultiAgent
- **WHEN** 调用方请求编译未完成 parity 的 `multi_agent` V1 配置
- **THEN** compiler 返回明确不支持诊断且原 AgentConfig 仍可交给旧 AgentFactory

### Requirement: Compiler 等价性与回归测试
系统 SHALL 维护 Python、graph-native YAML 和 Studio schema 2 的 contract 1.1 golden
fixtures，并 SHALL 保留 contract 1.0 Studio、AgentConfig YAML、graph YAML 和 Benchmark
JSON 契约测试。代表性 ReAct、Planner-and-Execute 和外部 typed component 图在语义和
显式 Catalog 相同时 MUST 产生相同 canonical AgentGraph identity。

#### Scenario: 三 authoring surface ReAct parity
- **WHEN** Python Builder、graph-native YAML 和 Studio schema 2 声明相同 contract、
  binding、Router、Loop 和 logical IDs
- **THEN** 三者的 canonical mapping 和 hash 相同

#### Scenario: 保存后重载
- **WHEN** Studio schema 2 文档保存为 revision、从 SQLite 重载并再次编译
- **THEN** canonical mapping/hash 与保存时的有效 compile snapshot 相同

#### Scenario: 旧配置回归
- **WHEN** 执行现有 AgentConfig、contract 1.0 Studio 和 BenchmarkTask fixture 测试
- **THEN** 本变更不删除旧 YAML/JSON/Studio importer 支持且既有契约继续通过

### Requirement: Python 与 YAML 支持相同组合语义
Python AgentGraph model、公开 AgentGraphBuilder 和 Graph YAML compiler SHALL 支持相同的 contract reference、组件 binding、Router、State、Loop、Subgraph、条件与 feedback 结构，并在语义和逻辑 ID 相同时产生相同 canonical graph。Builder MUST 只生成 AgentGraph contract 1.1，不得实例化组件、解析密钥、连接设备或嵌入执行回调。Studio authoring 不属于本变更的实现范围，但现有 FlowDocument compiler MUST 继续回归通过。

#### Scenario: Python 与 YAML Planner-and-Execute
- **WHEN** 两种 authoring surface 声明相同 plan state、iterator loop 和 execute subgraph
- **THEN** 编译结果具有相同 canonical hash

#### Scenario: Python 与 YAML Android ReAct
- **WHEN** Builder 与 graph-native YAML 声明相同 DeviceObserve、Perception、Reasoning、ActionExecutor 和有界反馈图
- **THEN** 编译结果具有相同 canonical hash 且都能交给同一 contract 1.1 binder

### Requirement: 兼容策略模板参数化而非复制图
旧 AgentConfig compiler SHALL 从版本化内置 template 实例化 graph，并只把已验证 strategy 参数和 component bindings 注入声明位置。Compiler MUST NOT 为每个配置复制一套手写编排算法。

#### Scenario: UGround 组件填充
- **WHEN** 受支持 UGroundAgent 配置包含 perception、reasoning、grounder 和 memory
- **THEN** compiler 把组件绑定填入固定 UGround template 且保留 Reasoning→Grounder→ActionExecutor 拓扑

### Requirement: 可执行 YAML 路由保持 envelope 明确
统一 YAML 入口 SHALL 根据显式 `kind: agent_graph` 或 AgentConfig V1 envelope 选择 compiler，不得根据节点字段猜测格式。新可执行 CLI 对 graph-native YAML SHALL 走 contract 1.1 新路径；对尚未通过 contract 1.1 parity 的 AgentConfig V1 类型 MUST 返回兼容提示或显式走旧入口，MUST NOT 生成近似图。

#### Scenario: graph-native YAML 进入新路径
- **WHEN** 用户通过新 CLI 加载 `kind: agent_graph` 且 contract version 为 1.1 的文档
- **THEN** loader 返回 AgentGraph compilation result 并继续统一可执行 Agent 绑定

#### Scenario: 未支持旧策略
- **WHEN** 新 CLI 收到尚未具有验证模板的 AgentConfig V1
- **THEN** 系统不连接设备并提示使用旧兼容入口或受支持模板

### Requirement: 运行时字段不污染编译身份
Compiler SHALL 只把 Agent 行为语义放入 canonical AgentGraph。任务文本、设备 serial、artifact root、真实 secret 和 CLI 选项 MUST 由运行/绑定配置携带，不得因编译来源不同写入会改变 hash 的 metadata。

#### Scenario: 两个文件位置
- **WHEN** 内容相同的 graph-native YAML 从两个不同绝对路径编译
- **THEN** source map 保留各自路径，但 AgentGraph canonical hash 相同

### Requirement: Studio Compiler 必须验证必需 declarative dependencies
Studio compiler SHALL 使用显式注入的 Component Catalog dependency-slot metadata 验证每个
selected candidate 的必需 dependency 是否存在、结构合法、category/namespace 兼容且
Secret 字段保持 SecretRef 形式。失败诊断 MUST 定位到 nested canvas path、component
candidate 和 dependency property；compiler MUST NOT 通过导入 Python implementation 或
检查构造函数来猜测依赖。

#### Scenario: Reasoning 缺少 LLM dependency
- **WHEN** Studio 文档选择需要 `llm` 的 Universal Reasoning 但 candidate dependencies 为空
- **THEN** compiler 返回稳定 missing-required-dependency diagnostic、定位对应节点，并且不生成 valid runnable revision

#### Scenario: LLM dependency 使用 SecretRef
- **WHEN** candidate 声明 Catalog 允许的 LLM reference 且 API key 为合法 SecretRef
- **THEN** compiler 保留 dependency semantics 到 AgentGraph 和 canonical identity，但不解析 SecretRef

#### Scenario: Python/YAML/Studio 声明相同依赖
- **WHEN** 三种 authoring surface 声明相同 component refs、params、dependencies 和 logical IDs
- **THEN** 它们产生相同 canonical AgentGraph mapping/hash，Studio 不添加运行时专属隐式默认

#### Scenario: 当前环境没有 Secret 值
- **WHEN** Studio document 的 SecretRef 结构合法但当前服务尚未配置对应真实值
- **THEN** compile 仍可生成语义 valid AgentGraph，环境缺失由 Runtime Readiness 单独报告

