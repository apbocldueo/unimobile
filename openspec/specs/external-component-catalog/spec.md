# external-component-catalog Specification

## Purpose
TBD - created by archiving change discover-external-component-plugins. Update Purpose after archive.
## Requirements
### Requirement: ComponentBundle 原子声明正式外部组件
系统 SHALL 提供不可变且版本化的 `ComponentBundle`，由一个 provider 原子声明一个或多个携带 `ComponentSpec` 的正式组件。Bundle MUST 拒绝空组件集合、未知 schema version、裸组件实例、裸旧 Registry 类和不具备 ComponentSpec 的鸭子类型对象。

#### Scenario: 一个包声明多个组件
- **WHEN** provider 返回包含 Perception、Reasoning 和 Verifier 三个合法 ComponentSpec 的 Bundle
- **THEN** 系统把三者作为同一 provider 的 catalog fragment 进行预检和合并

#### Scenario: provider 返回裸类
- **WHEN** Entry Point 返回普通 Python 类列表而不是合法 ComponentBundle
- **THEN** provider loading 返回稳定 bundle-type-invalid 且不把这些类写入旧 Registry

#### Scenario: Bundle 中存在非法定义
- **WHEN** Bundle 中任一 ComponentSpec 的签名、角色、Contract 或兼容范围非法
- **THEN** 整个 Bundle 不进入 Catalog，其他独立 provider 仍可继续处理

### Requirement: ComponentCatalog 不可变且合并确定
系统 SHALL 将成功加载的 Bundle 合并为不可变 `ComponentCatalog`，并按 `namespace:name@component-version` 索引正式组件。合并顺序 MUST 确定；多个来源声明相同完整身份、外部组件与内置组件身份冲突或同一 provider 内重复身份时 MUST 失败，系统不得 silent overwrite 或采用最后导入者。

#### Scenario: 两个 provider 声明相同组件
- **WHEN** provider A 与 provider B 都声明 `acme:camera_verifier@1.0.0`
- **THEN** Catalog 构建返回 component identity conflict 且不选择任一实现

#### Scenario: 外部组件覆盖内置身份
- **WHEN** 外部 Bundle 声明与内置 Catalog 相同的 namespace、name 和 version
- **THEN** Catalog/bootstrap 拒绝该冲突并保留内置 Catalog 原状

#### Scenario: 组件身份互不冲突
- **WHEN** 多个 provider 声明不同完整身份的合法组件
- **THEN** Catalog 以稳定顺序包含全部组件且调用方无法修改其内部索引

### Requirement: 组件版本解析必须明确
Catalog resolver SHALL 按 GraphComponentRef 的 namespace、name 和可选 version 查找组件。显式 version MUST 精确匹配；省略 version 仅在 namespace/name 唯一匹配一个版本时有效，多版本匹配 MUST 返回 ambiguity，系统不得自动选择最新版或依赖安装顺序。

#### Scenario: 精确版本匹配
- **WHEN** 图引用 `acme:camera_verifier@1.1.0` 且 Catalog 存在该版本
- **THEN** resolver 返回精确 ComponentSpec

#### Scenario: 省略版本且唯一
- **WHEN** 图引用 `acme:camera_verifier` 且 Catalog 只有一个对应版本
- **THEN** resolver 确定性返回该版本

#### Scenario: 省略版本但存在多个版本
- **WHEN** Catalog 同时包含同一 namespace/name 的两个版本且图未声明 version
- **THEN** resolver 返回 component-version-ambiguous 并列出安全版本集合

#### Scenario: 版本不存在
- **WHEN** 图请求的精确组件版本不存在
- **THEN** resolver 返回 component-version-not-found 且不回退到其他版本

### Requirement: Contract 与 runtime type 随 Catalog 显式合并
系统 SHALL 从 Bundle 内 ComponentSpec 提取 NodeContract 与 runtime type bindings，形成可显式传入 compiler、validator 和 binder 的 Catalog。相同 Contract ID/version 定义相等时 MAY 去重，定义不同时 MUST 失败；相同 logical runtime type ID 绑定到不兼容 Python 类型时 MUST 在组件构造和设备分配前失败。

#### Scenario: 两个组件共享相同 Contract
- **WHEN** 同一或不同 provider 的两个组件携带定义完全相同的版本化 NodeContract
- **THEN** Catalog 合并保留一个等价 Contract 并允许两个组件引用它

#### Scenario: Contract 定义冲突
- **WHEN** 两个组件为相同 Contract ID/version 声明不同端口
- **THEN** Catalog 构建返回 contract conflict 且不进入 binding

#### Scenario: runtime type 冲突
- **WHEN** 两个组件把相同 logical type ID 绑定到不同 Python DTO
- **THEN** Catalog 构建返回 runtime-type conflict 且不实例化任何组件

### Requirement: Catalog resolver 接入现有 AgentGraph binding
系统 SHALL 提供 `CatalogComponentResolver`，按 GraphComponentRef 返回正式 ComponentSpec，并由现有 binder 完成配置、角色、Contract、兼容范围、依赖和 run-scoped 构造。GraphExecutionKernel MUST 不感知 provider、distribution、PyPI、Git 或本地来源，也不得为外部组件增加名称分支。

#### Scenario: YAML 图解析外部 Verifier
- **WHEN** YAML 编译得到引用外部 Verifier 的 AgentGraph，且调用方把发现环境的 Contract catalog 与 resolver 显式传入 binding
- **THEN** binder 预检并构造 Verifier，Kernel 通过普通 NodeContract invocation boundary 执行它

#### Scenario: Python SDK 使用同一组件
- **WHEN** Python SDK 构建的 AgentGraph 引用相同 namespace、name、version 和参数
- **THEN** 同一个 Catalog resolver 返回相同 ComponentSpec 语义并走相同 binding 路径

#### Scenario: 自定义 Tool
- **WHEN** 外部 Bundle 提供自定义 typed Tool、NodeContract 和 runtime type binding
- **THEN** validator 与 binder 使用显式扩展 Catalog 接入该节点，Kernel 无需新增 Tool 或 provider 分支

### Requirement: 发现来源不得改变 AgentGraph canonical identity
distribution 名称、distribution 版本、Entry Point、安装路径、Git revision、commit ID、加载状态和 DiscoveryReport MUST NOT 写入 AgentGraph 或参与 canonical hash。只有图中声明的组件 namespace、name、可选 component version、参数引用和图语义参与身份计算。

#### Scenario: wheel 与 editable 来源
- **WHEN** 同一组件定义分别从 wheel 和本地 editable distribution 发现并用于编译相同 Agent
- **THEN** 两个 AgentGraph 得到相同 canonical hash，来源差异仅存在于非语义 provenance

#### Scenario: provider distribution 升级但图语义不变
- **WHEN** distribution 版本变化但解析到的 ComponentSpec identity、Contract 和图声明不变
- **THEN** AgentGraph canonical hash 不因 distribution metadata 变化

### Requirement: 高层 bootstrap 与低层纯函数边界分离
系统 SHALL 允许 SDK 或 `zhixing run` 在用户显式启动时执行 discovery 并组装 `DiscoveredComponentEnvironment`。低层 Graph compiler、validator、canonicalizer 和 GraphExecutionKernel MUST NOT 自行扫描 Entry Point；它们只接收调用方显式提供的 Catalog/Resolver。

#### Scenario: 仅编译图
- **WHEN** 调用方只执行低层 YAML 或 Python AgentGraph 编译
- **THEN** 系统不枚举 Entry Point、不加载 provider 且不构造组件

#### Scenario: 高层运行外部组件图
- **WHEN** 用户明确通过高层运行入口执行引用外部组件的图
- **THEN** 入口先构建发现环境，再把明确的 Contract catalog 和 resolver 传给校验与 binding

### Requirement: 现有组件来源保持兼容
引入外部 Catalog 后，显式 mapping、结构化本地组件、BuiltInComponentResolver、旧 PluginRegistry 和 Legacy Adapter SHALL 保持现有行为。正式外部 ComponentSpec 校验失败时 MUST 不降级到任一宽松兼容路径；旧 CWD loader 和全包扫描 MAY 保留但不得成为新 Catalog 的隐式输入。

#### Scenario: 显式 mapping
- **WHEN** SDK 调用方继续把本地组件 mapping 直接传给 binder
- **THEN** 现有显式绑定路径继续工作且无需运行 external discovery

#### Scenario: 内置旧组件
- **WHEN** 图只引用 BuiltInComponentCatalog 中的旧组件
- **THEN** 内置 resolver 与 Legacy Adapter 继续按原路径工作，不要求安装外部 provider

#### Scenario: 正式外部组件非法
- **WHEN** Catalog 中的正式 ComponentSpec 在 binding 预检失败
- **THEN** 系统返回正式定义错误而不是改用同名旧 Registry 类或鸭子类型对象

