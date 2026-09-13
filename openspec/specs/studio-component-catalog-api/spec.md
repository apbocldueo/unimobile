# studio-component-catalog-api Specification

## Purpose
TBD - created by archiving change implement-studio-agentgraph-1-1-builder. Update Purpose after archive.
## Requirements
### Requirement: 统一 Studio Component Catalog
系统 SHALL 为 Studio 提供版本化、确定性排序的统一 Component Catalog，合并框架内置
组件、内置 NodeContract 和显式批准的外部 Component Catalog。Catalog SHALL 是新版
Builder 的组件、contract、port、config schema、availability 和 provider provenance
真相；前端 MUST NOT 维护决定编译语义的第二份封闭注册表。

#### Scenario: 查询内置和外部组件
- **WHEN** Studio 请求 Component Catalog 且一个外部 provider 已通过正式发现合同加载
- **THEN** response 同时包含内置与外部组件的安全 metadata，并用稳定 identity 区分
  provider 和版本

#### Scenario: 外部组件未安装
- **WHEN** 已保存文档引用当前 Catalog 中不存在的外部 component/version
- **THEN** Catalog/compile 返回 availability diagnostic，不静默替换为同名其他版本

### Requirement: 完整 NodeContract 与 typed ports
每个可 author 的 component SHALL 暴露 exact contract ID/version、input/output port ID、
direction、logical data types、required、cardinality、adapter、side-effect、
idempotency 和 execution features。Core role MAY 作为展示分类，但 MUST NOT 成为封闭
组件集合。

#### Scenario: ActionExecutor 端口
- **WHEN** Builder 查询动作执行组件
- **THEN** Catalog 声明 `action` input、`action_result` output 和非幂等设备副作用，
  前端不使用旧 VerifiedPlan 或 wildcard 端口

#### Scenario: 未知扩展 contract
- **WHEN** 外部组件提供 Studio 未见过的合法 NodeContract
- **THEN** Builder 根据 contract ports 生成通用卡片和连线能力，不要求修改组件名称
  白名单

### Requirement: 安全 Config Schema
Catalog SHALL 为组件提供严格、安全的 config JSON Schema 和必要的受限 display hints。
Schema MUST NOT 包含 secret 默认值、live implementation、factory、client 或设备对象。
Secret 字段 SHALL 以 SecretRef authoring 方式表达。

#### Scenario: Secret 参数
- **WHEN** 一个 LLM 或组件配置需要 API key
- **THEN** Builder 表单请求 secret reference name，不从 Catalog 获得或保存实际 secret

#### Scenario: 未知 schema 控件
- **WHEN** config schema 使用前端没有专用控件的受支持 JSON 类型
- **THEN** Builder 使用通用 schema renderer 或明确只读/unsupported diagnostic，不
  执行 provider supplied JavaScript

### Requirement: Catalog 构建无运行副作用
Catalog assembly MAY 加载显式批准 provider 的声明 bundle，但 MUST NOT 实例化组件、
解析 secret、连接设备、调用模型或创建 Runtime。Provider failure SHALL 以独立安全
diagnostic 返回，不得使无关成功组件消失。

#### Scenario: 一个 provider 加载失败
- **WHEN** 多个外部 provider 中一个声明加载失败
- **THEN** Catalog response 保留其他成功组件并包含失败 provider 的安全 code/type，
  不回显内部路径或任意 exception payload

### Requirement: Catalog 版本与缓存一致性
Catalog response SHALL 包含由安全语义 metadata 确定性派生的 `catalogVersion`。Compile
request MAY 携带客户端观察的版本；若版本不匹配且可能影响 document，compiler SHALL
返回 compatibility warning/error，不静默按旧端口或 config schema 编译。

#### Scenario: Catalog 在编辑期间变化
- **WHEN** 用户打开文档后安装或移除一个 provider
- **THEN** 下次 compile 报告 Catalog 版本变化，并对受影响 binding 给出定位诊断

### Requirement: Component Catalog HTTP API
系统 SHALL 提供 `GET /studio/components/catalog`，返回版本化 Catalog、安全 provider
report 和缓存 metadata。API MUST 对 payload 有界并使用稳定错误 envelope。

#### Scenario: 正常请求 Catalog
- **WHEN** 本地 Studio 客户端请求 Catalog
- **THEN** API 返回可 JSON 序列化且不含 implementation/live object 的确定性 payload

### Requirement: 旧 Registry 兼容而非新语义真相
现有 `/studio/builder/agent-registry` 和旧 PluginRegistry-based payload SHALL 保持可用，
用于 legacy UI/schema 1 migration；新版 AgentGraph 1.1 Builder MUST NOT 从该 payload
决定正式 NodeContract、ports 或 canonical component binding。

#### Scenario: 旧页面继续加载
- **WHEN** 旧 `/builder` 兼容页面请求 agent-registry
- **THEN** endpoint 仍返回旧 payload，但新版 schema 2 compile 只使用正式 Catalog

### Requirement: Catalog 必须声明组件依赖槽
Component Catalog SHALL 为每个可 author component 提供确定性的 declarative dependency
slot metadata，包括稳定名称、是否必需、允许的组件 category/namespace 和安全 authoring
schema。内置与外部组件的依赖事实 MUST 来自后端正式声明；前端 MUST NOT 根据显示名称、
Python class name 或角色白名单猜测 `llm_client` 等构造依赖。

#### Scenario: 查询 Universal Reasoning
- **WHEN** Builder 查询 `agent.reasoning:universal_reasoning@1`
- **THEN** Catalog 声明必需的 `llm` dependency slot，并指向可 author 的 LLM component reference schema

#### Scenario: 组件不需要外部依赖
- **WHEN** Catalog 描述一个不要求 declarative dependency 的组件
- **THEN** 它返回空 dependency-slot 集合，前端不显示虚构的模型配置

#### Scenario: Dependency metadata 改变
- **WHEN** provider 的 required dependency metadata 变化
- **THEN** `catalogVersion` 相应变化，已打开文档在下次 Validate 时得到兼容性/定位诊断

### Requirement: Dependency Schema 必须保持 SecretRef 安全边界
Dependency slot schema MAY 描述嵌套 component config 和 SecretRef 字段，但 MUST NOT 包含
真实 secret 默认值、resolved credential、implementation、factory、client、device 或任意
可执行 renderer。

#### Scenario: LLM dependency 需要 API Key
- **WHEN** Catalog 返回 OpenAI LLM 的配置 schema
- **THEN** API key 仅表达为必需 SecretRef identity，Catalog payload 不包含可用 API key

