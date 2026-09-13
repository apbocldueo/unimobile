# studio-run-execution Specification

## Purpose
定义 Studio Run 从不可变图 snapshot 到 Android Graph Runtime 的组件绑定、设备租约、证据预检、取消和确定性收口合同。
## Requirements
### Requirement: 执行编排必须重新验证 snapshot 并显式绑定组件
worker SHALL 从 Run-owned snapshot 解析 `AgentGraph`，使用正式 canonical 算法重新验证
hash，并通过显式 production component resolver 与 `bind_execution_plan` 建立 run-scoped
bound plan。编译/验证阶段 MUST 保持无设备连接、无 secret resolution 和无组件实例化；
这些副作用只允许在已经接受的 execution boundary 内发生。

#### Scenario: snapshot 和 hash 有效
- **WHEN** worker 读取与 revision compile snapshot 一致的 AgentGraph
- **THEN** worker 绑定该图并将 immutable execution identity 写入 Run lifecycle event

#### Scenario: 持久 snapshot 被破坏
- **WHEN** graph body 重新计算的 canonical hash 与 Run snapshot 不同
- **THEN** worker 在组件或设备副作用之前以 graph-integrity failure 终止

#### Scenario: 所选组件无法解析
- **WHEN** snapshot 引用缺失、不可用或 role 不兼容的 component
- **THEN** binding 返回结构化 error，Run 失败且不尝试连接设备

### Requirement: 首版生产执行必须复用 Android Graph Runtime
生产 adapter SHALL 调用现有 `AndroidGraphRuntime`、`RuntimeContext`、显式
ObservationProvider/ActionExecutor 和 `RunArtifactStore` 语义；不得复制 Graph scheduler、
直接从 HTTP handler 拼接 ADB 命令或绕过 device boundaries。测试 adapter SHALL 支持
确定性 fake device/executor。

#### Scenario: 执行真实 Android Run
- **WHEN** 本地配置提供可用 Android device profile 且 binding 成功
- **THEN** worker 通过 Android Graph Runtime 执行，设备观察和动作经过正式 service boundary

#### Scenario: fake device 合同测试
- **WHEN** test harness 注入确定性 fake device
- **THEN** 同一 orchestration、event、cancel、result 和 Replay 流程运行且无需 ADB

#### Scenario: 请求 Harmony 或未支持 runtime
- **WHEN** Stage 3 客户端请求 Android 之外的 runtime kind
- **THEN** 服务在产生设备副作用前返回明确 unsupported-runtime error

### Requirement: 本地单设备必须有显式排他租约
执行服务 SHALL 用独立 `DeviceLease` boundary 保证同一 private target identity 同时最多
有一个拥有者，而不是仅按 public profile ID 隔离。首版没有持久队列：设备忙时新请求
MUST 明确失败或拒绝启动，不得让两个 Run，或 Run 与 Benchmark Experiment，通过相同
或不同 profile 并发控制同一设备。HTTP、event 与持久 evidence MUST NOT 暴露原始
device serial、private target identity 或 binding fingerprint。

#### Scenario: 第二个 Run 竞争设备
- **WHEN** Run A 持有设备租约且 Run B 通过相同或不同 profile 请求同一 private target
- **THEN** Run B 以 `device_busy` 收口或创建被拒绝，且不执行任何设备动作

#### Scenario: Benchmark 与 Run 竞争同一 target
- **WHEN** Benchmark Experiment 已持有 target lease 且普通 Run 请求同一 target
- **THEN**普通 Run 安全失败，两个执行产品不会并发控制设备

#### Scenario: worker 终止释放租约
- **WHEN** Run success、failure、cancel 或抛出异常
- **THEN** orchestration 在 finally boundary 释放 target-level 租约，使后续 Run 或 Experiment 可取得设备

### Requirement: 证据存储必须在设备副作用前完成 preflight
worker SHALL 在绑定完成且设备操作开始前分配受控 run evidence namespace，验证
repository/artifact store 可写、安全 root、配置的保留预警和最低可用空间。若无法合理保证
本次证据写入，Run MUST 在设备副作用前终止；运行中证据写入失败 MUST 停止继续执行而
不得静默丢弃。

#### Scenario: artifact root 不可写
- **WHEN** evidence namespace preflight 失败
- **THEN** Run 以 evidence-storage failure 终止且不连接设备

#### Scenario: 运行中磁盘写入失败
- **WHEN** screenshot、UI XML、debug artifact 或 event 无法原子提交
- **THEN** 服务请求协作式取消，保留已确认 evidence 并以明确 partial availability 收口

#### Scenario: 达到配置预警但仍可保证写入
- **WHEN** Studio 存储超过默认 20GB 预警阈值但容量和写入检查仍通过
- **THEN** 服务记录/返回 storage warning，不自动删除旧 evidence，也不隐瞒预警

### Requirement: worker 必须执行确定性的 Run 收口
orchestrator SHALL 将所有正常返回和预期异常映射为正式 `RunResult`，按顺序提交剩余
events、result、artifact inventory、原生 Replay 和唯一 terminal event。未知异常 MUST
在最外层转化为安全 failure result；异常文本不得泄露 secret、raw serial 或宿主绝对路径。

#### Scenario: Android Runtime 返回 DEVICE_FAILURE
- **WHEN** AndroidGraphRuntime 返回 `RunStatus.DEVICE_FAILURE`
- **THEN** Run、terminal event 和 Replay 都保存同一状态和已确认 evidence

#### Scenario: worker 抛出未知异常
- **WHEN** execution adapter 未预期地抛出异常
- **THEN** outer boundary 生成安全 FAILURE result 并尝试完成同一收口序列

### Requirement: 服务重启不得伪造 checkpoint 恢复
服务启动时 SHALL 扫描由旧 process owner 留下的非终止 Run。由于 Stage 3 没有持久
checkpoint，这些 Run MUST 原子收口为 `RunStatus.FAILURE` 和
`studio.run.service_restarted`，保存截至最后 high-water mark 的部分 evidence 并生成
可回放终态；系统 MUST NOT 自动重跑已执行 activation。

#### Scenario: running Run 期间进程退出
- **WHEN** 新服务实例发现旧 owner 的 running Run
- **THEN** 它提交 interruption result、Replay 和唯一 terminal event，不重新执行组件

#### Scenario: accepted Run 尚无副作用
- **WHEN** 新实例发现旧 owner 的 accepted Run
- **THEN** 它仍明确收口为 interrupted，而不是猜测请求是否可以安全重放

### Requirement: 取消检查必须覆盖副作用安全边界
orchestrator SHALL 在 binding 后、取得设备租约前、开始 Runtime 前以及 Runtime activation
边界检查持久 cancellation request，并将同一 request 连接到
`SimpleCancellationSignal`。已经开始的外部调用可以自然返回，但返回后 MUST 在下一个
安全边界停止调度后续 activation。

#### Scenario: binding 期间收到取消
- **WHEN** cancel 在 component binding 完成前被持久化
- **THEN** worker 不获取设备租约，并以 CANCELLED 收口

#### Scenario: 模型调用期间收到取消
- **WHEN** cancellation request 在不可中断的模型调用中到达
- **THEN** 服务显示 cancelling，调用返回后不调度下一个 activation，最终记录 CANCELLED

### Requirement: Studio Run device authority 必须使用 exact private target
Studio Run SHALL resolve a browser-facing profile only to an explicitly configured exact private
target or an explicitly injected deterministic fake device. Production execution MUST NOT accept
an unbound profile, pass `serial=None` into Android Runtime, or select a device because it is the
only ready target. Missing, offline, unauthorized, changed, or unsupported targets MUST fail before
observation, Agent, model, or action side effects and MUST expose only safe error codes.

#### Scenario: Run service has no configured Android profile
- **WHEN**a client requests `local-android` but the trusted profile directory is empty
- **THEN**Run creation or execution fails safely without ADB discovery or implicit target selection

#### Scenario: Multiple devices are ready
- **WHEN**a configured Run profile pins one exact target while multiple Android devices are online
- **THEN**Android Runtime receives only the pinned target and does not use unique-device selection

#### Scenario: Deterministic fake device is injected
- **WHEN**a test composition explicitly binds a fake device target
- **THEN**the existing Run orchestration, event, cancel, result, and Replay contracts remain testable without ADB

### Requirement: Studio Run Composition 必须显式注入 Secret Provider
普通 Agent Run 和 Benchmark execution composition SHALL 共享明确配置的、只存在于服务端
进程的 Secret Provider 与 Device Profile authority，并将它们注入各自 production component
resolver。Resolver MUST 只按 AgentGraph 中的 SecretRef identity 解析值，不得从浏览器
request、FlowDocument metadata、Run metadata 或进程日志获取 credential。

#### Scenario: LLM dependency 在执行边界绑定
- **WHEN** accepted Run snapshot 声明 OpenAI LLM dependency 且 Secret Provider 含所需 identity
- **THEN** run-scoped resolver 构造 LLM 并以 `llm_client` 注入 Planner/Reasoning，真实值不进入 Run snapshot 或 evidence

#### Scenario: 多个组件共享同一 LLM ref
- **WHEN** Planner 和 Reasoning 声明语义相同的 LLM dependency
- **THEN** resolver 按现有 run-scoped binding/caching 语义提供兼容实例，不把 live client 写入 Runtime Debug Payload

### Requirement: Execution Boundary 必须重新检查可变 Readiness
worker SHALL 在正式 binding、evidence 和设备边界继续重新验证 immutable snapshot、
component/SecretRef resolution、Profile authority、target state 和 lease。创建前 Readiness
MUST NOT 被当作真实 Android、模型调用或设备可用性的证明。

#### Scenario: Secret 在 acceptance 后不可用
- **WHEN** Run 已接受但执行前 Secret Provider 因进程 composition 变化无法解析引用
- **THEN** worker 在设备副作用前以结构化 binding failure 收口，并保留正式 Run/Replay 证据链

#### Scenario: 设备在 readiness 后离线
- **WHEN** static readiness 通过但 exact target 在执行边界为 offline
- **THEN** worker 返回正式 device-offline status/code，且 UI 可与“未配置 Profile”区分

### Requirement: 运行时构造错误不得作为依赖发现机制
Production binding MUST 依赖已验证的 Graph dependency declaration；系统 MUST NOT 通过捕获
`__init__` missing positional argument 等任意 Python TypeError 来发现 authoring 所需依赖。
意外构造错误仍 SHALL 被清理并形成安全 failure，但不能替代 Catalog/compiler/readiness 合同。

#### Scenario: 历史 Graph 绕过新版编译
- **WHEN** 一个缺少 required dependency 的历史 snapshot 到达 execution adapter
- **THEN**显式 binding validation 返回稳定 dependency error，而不是向用户展示原始 Python constructor TypeError

