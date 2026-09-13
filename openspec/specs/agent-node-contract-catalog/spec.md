# agent-node-contract-catalog Specification

## Purpose
TBD - created by archiving change generalize-agent-graph-paradigms. Update Purpose after archive.
## Requirements
### Requirement: 标准核心契约与开放扩展契约并存
系统 SHALL 提供版本化 NodeContract catalog。六类 Mobile Agent 核心契约 `perception`、`planner`、`reasoning`、`memory`、`action_executor` 和 `verifier` MUST 保持稳定，但 catalog MUST 允许显式加入 Grounder、Tool、DeviceObserve 和用户扩展契约，而不修改 GraphExecutionKernel。

#### Scenario: 查询核心契约
- **WHEN** 调用方读取默认 catalog
- **THEN** 系统返回六类稳定核心契约及其版本化端口，同时允许 catalog 中存在明确标记的基础设施或扩展契约

#### Scenario: 显式加入 Grounder 契约
- **WHEN** 调用方把合法 Grounder NodeContract 注入 catalog
- **THEN** validator 和 binder 能处理该契约且 Kernel 不增加 Grounder 专用分支

### Requirement: NodeContract 定义类型化调用边界
NodeContract SHALL 声明稳定 contract ID、版本、输入/输出端口、逻辑数据类型、必需性、基数、invocation adapter 类别和副作用分类。外部组件作者 SHALL 为每个非内置且非显式 `any` 的逻辑数据类型提供确定的运行时类型绑定；同一逻辑数据类型 ID 的不兼容绑定 MUST 在 catalog/definition 合并阶段被拒绝。ComponentBinding SHALL 继续只描述具体组件候选、参数、依赖和 secret 引用，MUST NOT 代替 NodeContract、运行时类型绑定或 ComponentSpec。

#### Scenario: 契约与实现分离
- **WHEN** 两个节点引用同一个 Reasoning NodeContract 但绑定不同组件
- **THEN** 两个节点具有相同端口协议且保留各自独立的组件绑定与逻辑身份

#### Scenario: 不兼容实现
- **WHEN** 组件实现不能满足节点引用的 invocation adapter 或输出契约
- **THEN** binding 在节点执行前返回 contract/implementation mismatch

#### Scenario: 声明自定义逻辑类型
- **WHEN** 外部 Tool contract 使用 `example.media_snapshot` 作为端口类型并提供对应 Python runtime type
- **THEN** validator 和调用边界能校验该端口值而无需修改 Kernel 的角色分支

#### Scenario: 自定义类型绑定冲突
- **WHEN** 两个显式定义把同一个逻辑类型 ID 绑定为不兼容 Python 类型
- **THEN** 合并在组件实例化和设备分配前失败且不任意选择一种类型

#### Scenario: 未绑定的外部类型
- **WHEN** 外部 Contract 使用未知逻辑类型且既未提供 runtime type binding 也未显式使用 `any`
- **THEN** 定义预检返回 unknown-runtime-type 而不是默认接受任意对象

### Requirement: Contract catalog 显式注入且编译无副作用
扩展 NodeContract catalog SHALL 由调用方显式传入 compiler、validator 或 binder。本能力 MUST NOT 要求导入插件实现、自动发现 entry point、解析真实 secret 或连接设备；外部插件自动发现属于后续能力。

#### Scenario: 仅编译扩展图
- **WHEN** 调用方使用显式 extension catalog 编译含 Tool 节点的 Graph YAML
- **THEN** 编译可完成类型和端口检查且不会实例化 Tool 组件

#### Scenario: 缺少扩展 catalog
- **WHEN** 图引用非内置 contract 且调用方未提供对应 catalog
- **THEN** 系统返回稳定的 unknown-contract 诊断而不是猜测端口

### Requirement: 同契约多节点实例
AgentGraph SHALL 允许同一 NodeContract 出现多个具有独立 logical ID、binding、状态和事件身份的节点。系统 MUST NOT 根据 role 或 contract ID 假设图中只有一个 Planner、Reasoning、Verifier 或其他组件节点。

#### Scenario: Manager 与 Operator 共用 Reasoning 契约
- **WHEN** 图包含 `manager_reasoning` 和 `operator_reasoning` 两个 Reasoning contract 节点
- **THEN** 两个节点可绑定不同组件并在事件、状态和 canonical identity 中保持独立

### Requirement: 类型化移动设备 runtime service 契约
默认 NodeContract catalog SHALL 提供版本化 DeviceObserve 与 ActionExecutor runtime service contracts。DeviceObserve MUST 以类型化 observation request 为输入并输出 DeviceObservation；ActionExecutor MUST 以 ActionExecutionInput 为输入并输出 ActionResult。两者 SHALL 声明不同副作用类别，且 contract 不得依赖 Android 具体实现。

#### Scenario: 绑定 Android services
- **WHEN** Android 图把 DeviceObserve 与 ActionExecutor 节点分别绑定到 Android observation/action services
- **THEN** binder 验证端口与 invocation adapter 兼容，Kernel 只通过 contract 调用 service

#### Scenario: 绑定 fake services
- **WHEN** 相同图绑定满足同一 contracts 的 fake observation/action services
- **THEN** 图无需修改即可在无真实设备环境执行

#### Scenario: 错误绑定通用 any service
- **WHEN** 节点声明类型化 ActionExecutor contract 但绑定只接受任意未声明 request/result 的 service
- **THEN** binder 在设备运行前报告 contract/implementation mismatch

### Requirement: 设备 service contract 表达副作用与终止边界
ActionExecutor contract SHALL 声明设备动作副作用类别，但实际 interaction 是否发生 MUST 由 ActionResult 的类型化 effect 字段确认。DeviceObserve SHALL 声明只读设备副作用；DONE、FAIL、校验失败和命令执行前失败 MUST NOT 被计为已执行物理动作。

#### Scenario: 点击成功
- **WHEN** ActionExecutor 完成真实 TAP 并返回已执行 effect
- **THEN** Runtime 可将该 activation 计为一次物理 interaction

#### Scenario: DONE 终止
- **WHEN** ActionExecutor 返回 DONE 且 effect 表示未接触设备
- **THEN** Runtime 结束 Agent，但不增加物理 interaction 计数

#### Scenario: 设备命令前失败
- **WHEN** ActionExecutor 在参数校验阶段失败
- **THEN** Runtime 保留失败结果且不把 contract 静态副作用标签解释为已发生动作

