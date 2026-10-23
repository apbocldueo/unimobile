# external-component-authoring-api Specification

## Purpose
TBD - created by archiving change define-external-component-authoring-api. Update Purpose after archive.
## Requirements
### Requirement: 公共组件作者基类具有明确层次
系统 SHALL 在 `zhixing.components` 提供同步、泛型的 `BaseComponent[InputT, OutputT]`，并为 Perception、Planner、Reasoning、Memory、ActionExecutor 和 Verifier 六类 AgentGraph 核心角色提供固定输入/输出契约的公共抽象基类。系统 SHALL 将 Grounder 或自定义 typed node、LLM/Device runtime service、BenchmarkInitializer/Evaluator 分别标记为扩展、服务和 Benchmark 组件，不得把这些类别重新宣传为六类核心 AgentGraph 角色。

#### Scenario: 编写核心 Verifier
- **WHEN** 作者继承公共 `BaseVerifier` 并实现规范的 `invoke(input, runtime)`
- **THEN** 静态工具和组件预检均将其识别为接受 `VerifierInput`、返回 `VerifierResult` 的 Verifier 实现

#### Scenario: 缺少抽象入口
- **WHEN** 作者声明 `BaseReasoning` 子类但未实现 `invoke`
- **THEN** Python 抽象基类机制阻止该实现被实例化

#### Scenario: 编写非核心 Tool
- **WHEN** 作者通过通用 typed component 和显式 Tool NodeContract 定义组件
- **THEN** 该组件可以保留自定义端口而不会向六类核心角色枚举增加 Tool 分支

### Requirement: ComponentSpec 分离实现与可发现身份
系统 SHALL 提供不可变 `ComponentSpec`，至少描述 namespace、name、组件版本、精确 NodeContract 引用、实现、配置模型、ZhiXing 兼容范围和运行时类型绑定。创建 `ComponentSpec` MUST NOT 自动修改全局 PluginRegistry、扫描安装环境、实例化组件、读取 secret 或连接设备。

#### Scenario: 描述可复用组件
- **WHEN** 作者为一个 `BasePerception` 实现创建合法 `ComponentSpec`
- **THEN** 调用方可以在不实例化实现的情况下读取其安全身份、配置 Schema 和 Contract 引用

#### Scenario: 拒绝角色与 Contract 不一致
- **WHEN** `ComponentSpec` 把 `BaseVerifier` 实现声明为 Reasoning 核心 Contract
- **THEN** 定义预检返回稳定的 role/contract mismatch 且不构造组件

#### Scenario: 安全查看组件描述
- **WHEN** 调用方序列化或记录 `ComponentSpec` 的公共描述
- **THEN** 输出不包含实现实例、factory 内部状态、secret 值或 live service

### Requirement: 装饰器提供低门槛但非无契约的作者路径
系统 SHALL 提供 `@component` 作者接口，将带完整类型标注的同步函数或类关联到同一种 `ComponentSpec`。装饰器 MUST 保持被装饰对象可调用，不得依靠 import 副作用完成全局注册；缺少角色或精确 NodeContract、输入/输出类型或稳定身份的定义 MUST 被拒绝。

#### Scenario: 包装本地函数
- **WHEN** SDK 用户用 `@component` 装饰接受 `VerifierInput` 和 `RuntimeContext`、返回 `VerifierResult` 的同步函数
- **THEN** 系统生成可预检的 Verifier `ComponentSpec`，且用户无需创建 ABC 子类

#### Scenario: 拒绝未声明类型函数
- **WHEN** 函数组件省略输入或返回类型且没有通过显式参数提供等价类型信息
- **THEN** 定义预检失败而不是把函数视为 `Any -> Any`

#### Scenario: 拒绝异步 V1 组件
- **WHEN** 作者装饰 async function、generator function 或返回 awaitable 的 V1 组件
- **THEN** 作者 API 或 Contract Test Kit 报告同步协议不兼容

### Requirement: 配置先验证再构造
`ComponentSpec` SHALL 允许作者提供 Pydantic 配置模型。绑定新式组件时，系统 MUST 在组件构造和设备分配前验证声明参数；默认构造路径 SHALL 把验证后的字段作为显式构造参数，依赖和 secret MUST 继续通过独立 resolver 边界注入，不得进入配置 Schema 的公共序列化结果。

#### Scenario: 合法配置
- **WHEN** AgentGraph 参数满足组件配置模型
- **THEN** resolver 使用规范化配置构造新的组件实例

#### Scenario: 非法配置
- **WHEN** YAML 或 SDK 参数缺少必需字段或包含被配置模型禁止的未知字段
- **THEN** 绑定在构造实现和创建 Android runtime service 前返回结构化配置诊断

#### Scenario: SecretRef 保持边界
- **WHEN** 组件依赖声明包含 SecretRef
- **THEN** 配置描述和错误中仅保留引用身份，真实值只在运行时 resolver 中提供

### Requirement: 新式组件与兼容组件具有明确接纳策略
正式新式外部组件 SHALL 通过 `ComponentSpec` 和对应 ABC 或 `@component` 包装器进入严格作者路径。未携带 `ComponentSpec` 但满足结构化 Protocol 的对象 MAY 继续用于显式本地 SDK 组合；现有旧方法组件 SHALL 继续通过 Legacy Adapter 接入。系统 MUST 在诊断中区分新式定义错误、结构化本地组件和旧接口适配失败。

#### Scenario: 显式本地鸭子类型组件
- **WHEN** SDK 用户显式注入一个具有兼容 typed `invoke` 但没有 `ComponentSpec` 的本地对象
- **THEN** 现有结构化调用能力保持可用，但该对象不被声明为可发现或可发布的新式组件

#### Scenario: 旧内置组件
- **WHEN** 内置组件仅实现 `perceive`、`think` 或其他已支持旧入口
- **THEN** Legacy Adapter 保持其现有行为，且不要求旧类继承新的公共 ABC

#### Scenario: 新式定义校验失败
- **WHEN** 一个携带 `ComponentSpec` 的实现违反其声明 Contract
- **THEN** 系统不得回退到宽松鸭子类型路径来绕过错误

### Requirement: 公共作者 API 保持基础安装可导入
导入公共 ABC、`ComponentSpec`、`@component` 和定义校验器 MUST 不扫描插件、不导入可选模型/视觉/设备/Benchmark 栈、不访问网络或设备、不创建文件，并 MUST 保持现有 `zhixing` 根导出列表不变。

#### Scenario: 基础 wheel 导入
- **WHEN** 用户在仅安装基础依赖的干净环境中导入外部组件作者 API
- **THEN** 导入成功且未加载 OpenAI、Torch、Transformers、OpenCV 或 Harmony 依赖

#### Scenario: 导入不注册
- **WHEN** 一个进程只导入 `zhixing.components`
- **THEN** 全局 PluginRegistry 内容不会因为作者 API 而变化

### Requirement: Formal ComponentSpec 必须能够声明 declarative dependency slots
外部 component author SHALL 能在正式 ComponentSpec 中声明一个有界、metadata-only 的
dependency slot 集合。每个 slot SHALL 包含稳定名称、required 标志、允许的 component
category/namespace 和安全 authoring schema；声明 MUST 参与 definition validation 和 safe
metadata，但 MUST NOT 包含 resolved dependency、secret value、factory、client 或 live object。

#### Scenario: 外部 Reasoning 需要 LLM
- **WHEN** provider 声明一个需要 `llm` 的外部 Reasoning component
- **THEN**其 ComponentSpec safe metadata 和 Studio Catalog 暴露同一个 required LLM slot，Builder 无需识别实现类名称

#### Scenario: Dependency slot 声明非法
- **WHEN** provider 使用重复/非法 slot identity、可执行 schema 或 secret 默认值
- **THEN** component definition validation 拒绝该声明，并以 provider-scoped 安全 diagnostic 隔离失败

#### Scenario: 旧外部 ComponentSpec 未声明 slot
- **WHEN**现有 provider 使用不包含 dependency slot 的兼容 ComponentSpec
- **THEN**系统按空 slot 集合加载它，既有 component identity、config、invocation 和 binding 行为不变

### Requirement: Dependency Slot metadata 必须进入确定性组件身份元数据
Dependency slot 声明 SHALL 被安全、确定性地序列化到 ComponentSpec metadata 和 Catalog
version 输入，使 authoring/compile surface 能检测声明变化；它 MUST NOT 改变现有 component
identifier 或在运行时自动注入未声明依赖。

#### Scenario: Provider 增加 required dependency
- **WHEN**同一 component version 的 provider metadata 增加 required dependency slot
- **THEN** Catalog version 改变且 Studio Validate 重新检查引用文档，不静默生成 runtime default

