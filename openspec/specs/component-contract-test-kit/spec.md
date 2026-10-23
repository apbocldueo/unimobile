# component-contract-test-kit Specification

## Purpose
TBD - created by archiving change define-external-component-authoring-api. Update Purpose after archive.
## Requirements
### Requirement: Contract Test Kit 可独立验证组件定义
系统 SHALL 提供公共 Contract Test Kit，用于验证 `ComponentSpec` 的身份、兼容范围、配置模型、NodeContract、角色基类、调用签名和运行时类型绑定。测试工具 MUST 可在第三方仓库中直接调用，并返回稳定、可断言且不包含 secret 的诊断。

#### Scenario: 合法定义
- **WHEN** 第三方测试把合法 Verifier `ComponentSpec` 交给定义检查
- **THEN** Test Kit 报告定义通过并列出已验证的 Contract 身份

#### Scenario: 错误输出标注
- **WHEN** Reasoning 实现的返回标注与 `Action` 不兼容
- **THEN** Test Kit 在调用真实模型或设备前返回输出签名诊断

#### Scenario: 兼容范围不满足
- **WHEN** ComponentSpec 声明的 ZhiXing 版本范围不包含当前测试版本
- **THEN** Test Kit 返回明确的兼容性失败而不是继续构造组件

### Requirement: Test Kit 支持安全构造和调用 fixture
Test Kit SHALL 为内置 DTO 提供最小标准输入和 fake `RuntimeContext`，并 SHALL 允许作者显式提供配置、依赖、输入和 runtime fixture。Test Kit MUST 对实际返回值执行类型和端口校验，并 MUST 区分定义、构造和执行失败。

#### Scenario: 使用标准 Verifier fixture
- **WHEN** Verifier 不需要外部依赖且作者运行标准角色测试
- **THEN** Test Kit 使用 fake 输入和 RuntimeContext 调用一次组件并确认返回 `VerifierResult`

#### Scenario: 需要 LLM 依赖
- **WHEN** Reasoning 组件声明 LLM 依赖
- **THEN** 作者可注入 fake LLM fixture 完成测试，而 Test Kit 不读取真实 API key

#### Scenario: 动态返回错误
- **WHEN** 方法标注正确但测试调用实际返回字符串
- **THEN** Test Kit 报告 invocation output mismatch，并保留定义检查已通过这一事实

### Requirement: Test Kit 不执行未授权外部副作用
默认 Contract Test Kit MUST 不连接真实设备、不访问网络、不调用真实模型、不扫描已安装插件，也不得执行声明为设备动作的 ActionExecutor，除非作者显式提供受控 fake service 和调用 fixture。

#### Scenario: 测试 ActionExecutor
- **WHEN** 作者测试 ActionExecutor 且未提供 fake device service
- **THEN** Test Kit 只完成静态与构造检查，并明确报告调用检查被安全跳过

#### Scenario: 提供 fake device
- **WHEN** 作者显式提供记录调用的 fake device 和无副作用动作 fixture
- **THEN** Test Kit 通过 RuntimeContext 注入 fake service 并验证 ActionResult，不连接 ADB

### Requirement: Test Kit 验证运行级实例隔离
对于声明为有状态或 run-scoped 的组件，Test Kit SHALL 能通过 ComponentSpec 构造至少两个实例并验证 factory 不返回同一可变实例。Memory 等有状态组件的标准测试 MUST 验证 reset 和不同运行上下文不会隐式共享状态。

#### Scenario: 错误复用单例 Memory
- **WHEN** Memory ComponentSpec 的 factory 为两个 run 返回同一可变对象
- **THEN** Test Kit 报告 instance isolation failure

#### Scenario: 独立 Memory 运行
- **WHEN** 两个 Memory 实例分别使用不同 RuntimeContext 执行 append/read
- **THEN** 第二个实例不包含第一个实例写入的 fragment

### Requirement: Test Kit 输出可用于 CI 和人工定位
Test Kit SHALL 提供适合 pytest/CI 的失败断言以及结构化结果摘要。诊断 MUST 包含失败阶段、组件安全身份、Contract 和错误代码，但 MUST NOT 包含对象 repr、prompt、凭据、设备句柄或任意依赖内部状态。

#### Scenario: pytest 失败
- **WHEN** 作者在 pytest 中调用官方 Contract Test Kit 且组件违反配置契约
- **THEN** 测试以非通过状态结束，并显示稳定错误代码和安全字段路径

#### Scenario: Secret 出现在异常中
- **WHEN** 第三方构造函数异常文本包含常见 secret 字段
- **THEN** Test Kit 对公开诊断进行脱敏并保留原异常类型分类

### Requirement: Contract Test Kit 聚合验证 ComponentBundle
Test Kit SHALL 提供公共 Bundle 级检查入口，对合法 `ComponentBundle` 中的全部 `ComponentSpec` 按稳定组件身份顺序执行现有定义、构造、调用和实例隔离检查。聚合结果 MUST 保留逐组件 checks、skipped 与 diagnostics，一个组件失败 MUST NOT 遮蔽其他组件的检查结果。

#### Scenario: Bundle 全部组件通过
- **WHEN** 第三方 provider 的 Bundle 包含多个合法且无副作用的组件
- **THEN** Bundle 检查报告总体通过，并按稳定顺序包含每个组件的通过结果

#### Scenario: Bundle 中一个组件执行失败
- **WHEN** Bundle 中一个组件返回错误类型而其他组件合法
- **THEN** 聚合结果报告总体失败、定位失败组件及 invocation 阶段，并仍保留其他组件的检查结果

### Requirement: Bundle 聚合检查保持副作用授权边界
Bundle 级检查 MUST 复用单组件 Test Kit 的默认安全策略，不得因为聚合执行而向组件注入 Device、ActionExecutor、LLM、网络客户端或真实模型能力。调用方 MAY 按组件安全身份显式提供受控 fixture，但敏感角色没有明确授权时 MUST 记录 invocation 跳过而不是由框架调用真实副作用。组件 factory 与构造函数仍属于受信任第三方代码；Test Kit 不提供进程沙箱，也不保证第三方构造代码自身无副作用。

#### Scenario: Bundle 包含 ActionExecutor
- **WHEN** provider Bundle 包含 ActionExecutor 且 doctor 未获得副作用授权
- **THEN** 聚合检查完成其定义、构造和隔离检查，并把 invocation 记录为安全跳过

#### Scenario: 作者提供受控 fixture
- **WHEN** 插件侧 pytest 为指定敏感组件提供 fake service、输入和显式授权
- **THEN** Test Kit 只把这些受控 fixture 注入 invocation，不由框架连接真实 Android、创建真实模型客户端或读取真实 secret

### Requirement: Bundle 检查结果适合 CLI 与 CI
Bundle 检查 SHALL 提供不可变结构化结果和 pytest 友好断言。结果 MUST 包含 Bundle schema version、稳定组件身份、Contract、检查阶段和安全错误码，MUST 有界且不得包含对象 repr、原始 traceback、secret、凭据 URL、设备句柄或依赖内部状态。

#### Scenario: CLI doctor 序列化结果
- **WHEN** doctor 把 Bundle 检查结果输出为 JSON
- **THEN** 输出字段稳定、排序确定并可由 CI 根据总体状态和逐组件诊断断言

#### Scenario: 构造异常包含敏感信息
- **WHEN** Bundle 中组件的构造异常包含 token 或带凭据 URL
- **THEN** 聚合结果保留安全错误分类并对敏感片段脱敏和限长
