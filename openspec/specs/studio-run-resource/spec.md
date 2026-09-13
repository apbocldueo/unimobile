# studio-run-resource Specification

## Purpose
定义 Studio 普通 Agent Run 的不可变 revision 绑定、版本化请求、持久生命周期、HTTP 控制与可替换 repository 合同。
## Requirements
### Requirement: Run 必须绑定不可变且可验证的 Agent revision
系统 SHALL 只接受已经通过正式编译验证并保存的 Agent revision。创建 Run 时 MUST 在
同一持久化边界内保存 revision identity、AgentGraph 1.1 body、canonical hash、
presentation snapshot、source map 和 compile contract version；后续 revision 或草稿变化
MUST NOT 改变该 Run 的语义身份。

#### Scenario: 使用有效 revision 创建 Run
- **WHEN** 客户端提交一个存在且状态为 valid 的不可变 revision
- **THEN** Run 保存自包含 snapshot，并且 snapshot 的 graph body 重新计算得到相同 canonical hash

#### Scenario: 尝试运行未保存草稿
- **WHEN** 客户端只提交可变 FlowDocument、当前草稿或不存在的 revision identity
- **THEN** 服务拒绝创建 Run，并要求调用方先 Validate 且保存新 revision

#### Scenario: Run 创建后 Agent 又保存新 revision
- **WHEN** 已创建 Run 所属 Agent 后续产生一个不同 revision
- **THEN** 原 Run 继续引用创建时 snapshot，不跟随新的 current revision

### Requirement: Run 请求必须是版本化且有界的普通任务输入
Run create DTO SHALL 包含 schema version、client request identity、Agent/revision
identity、任务文本、可选有界结构化 metadata 和可选安全 device profile identity。
接口 MUST NOT 将 BenchmarkTask JSON、原始 ADB serial、宿主路径、secret 或任意运行对象
作为普通 Run 输入合同。

#### Scenario: 提交普通 Agent 任务
- **WHEN** 客户端提交非空 task text、合法 metadata 和已配置的 device profile identity
- **THEN** 服务按普通 Agent Run 接受请求，不构造 Benchmark lifecycle 或 evaluation

#### Scenario: 请求超过大小或结构限制
- **WHEN** task text、metadata 深度、成员数或序列化大小超过版本化限制
- **THEN** 服务在运行或连接设备之前返回结构化 validation error

#### Scenario: 请求包含原始设备 serial 或 secret
- **WHEN** 客户端 metadata 包含被安全策略识别的 raw serial、token 或 password
- **THEN** 服务拒绝请求，且持久 Run 记录和错误响应不包含原值

### Requirement: 幂等创建必须返回同一 Run 或明确冲突
系统 SHALL 使用 client request identity 和规范化请求 fingerprint 提供幂等创建。在同一
workspace 中，重复提交 identity 与 fingerprint 都相同的请求 MUST 返回同一 Run；identity
相同但 fingerprint 不同的请求 MUST 返回 conflict，且不得创建第二个 Run。

#### Scenario: HTTP 响应丢失后重试创建
- **WHEN** 客户端以相同 client request identity 和相同请求内容重试
- **THEN** 服务返回首次创建的 run identity 和当前状态，不重复执行 Agent

#### Scenario: 复用 identity 提交不同 revision
- **WHEN** client request identity 已存在但新请求引用不同 revision 或 task
- **THEN** 服务返回安全 conflict，并保留原 Run 不变

### Requirement: Run 生命周期与执行结果必须分离且持久
Run 资源 SHALL 使用持久 lifecycle state 表示 `accepted`、`starting`、`running`、
`cancelling` 和 `terminal`，并在 terminal 时独立保存正式 `RunResult.status`、kernel
status、安全错误、计数、usage 和最终输出摘要。Run 状态变化 MUST 遵守单向状态机并使用
事务或 compare-and-swap 防止并发覆盖。

#### Scenario: 成功完成
- **WHEN** Runtime 返回终止 `RunResult` status `success`
- **THEN** Run lifecycle 原子进入 terminal，并保存完整安全结果摘要和终止时间

#### Scenario: Runtime 失败
- **WHEN** 绑定、设备、执行或证据写入返回结构化失败
- **THEN** Run 进入 terminal，保存相应 RunStatus、错误 code 和截至失败点的已确认事实

#### Scenario: 并发终止竞争
- **WHEN** cancel、Runtime completion 和 service recovery 同时尝试终止同一 Run
- **THEN** 只有一个合法 terminal transition 获胜，后续操作读取同一不可变终态

### Requirement: Run HTTP API 必须提供安全创建、查询和取消
Studio HTTP SHALL 提供版本化 Run create、Run get 和 cancel command 接口。创建成功
SHALL 返回 `202 Accepted` 和可查询资源；查询 SHALL 返回当前 snapshot identity、
lifecycle、result availability 和 event high-water mark；所有错误 MUST 使用统一安全错误
envelope。

#### Scenario: 创建后立即查询
- **WHEN** 客户端收到 `202 Accepted` 后按 run identity 查询
- **THEN** 即使执行线程尚未开始，服务也返回已经持久化的 accepted Run

#### Scenario: 查询不存在的 Run
- **WHEN** 客户端请求未知或格式非法的 run identity
- **THEN** 服务返回安全 not-found/validation 响应，不泄露数据库或宿主路径细节

### Requirement: Cancel 命令必须幂等且明确是协作式取消
Cancel command SHALL 持久化 cancellation request，并向本进程中对应
`SimpleCancellationSignal` 发出信号。取消仅保证在 Runtime 的安全 activation 边界被观察；
接口 MUST NOT 声称已中断正在进行的模型调用、设备调用或 Python 函数，也不得伪装成
pause/checkpoint。

#### Scenario: 取消正在运行的 Run
- **WHEN** 用户对 running Run 发出 cancel
- **THEN** Run 进入 cancelling，Runtime 在下一个安全边界返回 CANCELLED 后再进入 terminal

#### Scenario: 在 worker 开始前取消
- **WHEN** 用户对 accepted Run 发出 cancel
- **THEN** worker 不执行组件或设备副作用，并以 CANCELLED 终止该 Run

#### Scenario: 重复取消终止 Run
- **WHEN** 客户端对已经 terminal 的 Run 重复发出 cancel
- **THEN** 服务幂等返回现有终态，不改写结果且不产生第二个终止事件

### Requirement: 持久层必须通过可替换 repository 合同隔离
Run、request、snapshot、lifecycle、result 和 cancellation metadata SHALL 通过 typed
repository protocol 访问。首版 SQLite adapter MUST 仅保存结构化数据，HTTP DTO 和
application service MUST NOT 暴露或依赖 SQLite row ID、SQL 文本或数据库路径。

#### Scenario: SQLite 重启后查询
- **WHEN** Studio 服务关闭并使用同一 workspace database 重新启动
- **THEN** 已提交 Run 的 snapshot、状态、结果和 cursor 仍可查询

#### Scenario: 未来替换 PostgreSQL
- **WHEN** PostgreSQL adapter 通过同一 repository contract suite
- **THEN** Run HTTP、execution service 和后续前端无需修改资源 identity 或 DTO

### Requirement: 新 Run 必须在 durable acceptance 前通过静态 Readiness
对尚未存在的 client request identity，Run application service SHALL 在创建持久 accepted
Run 前验证 exact revision 的 graph/hash、组件 dependency closure、SecretRef availability
和 selected safe Device Profile 静态存在性。已知失败 MUST 返回版本化安全 readiness error，
不得创建 Run、scheduler work、journal、artifact namespace 或 terminal failure Replay。

#### Scenario: Revision 缺少必需 LLM dependency
- **WHEN** 客户端尝试运行一个因兼容历史数据而仍可读取、但缺少 required `llm` dependency 的 revision
- **THEN** create 返回 graph-not-ready error，数据库中不出现 accepted/terminal Run

#### Scenario: SecretRef 未配置
- **WHEN** exact valid graph 引用服务端未配置的 SecretRef
- **THEN** create 返回 missing-secret readiness error，不构造 LLM、不连接设备且不泄露 secret 值

#### Scenario: Device Profile 不存在
- **WHEN** client 请求的安全 Profile identity 不在当前可信目录
- **THEN** create 返回 profile-unavailable readiness error，不持久 Run 且不执行 ADB discovery

#### Scenario: 幂等重试已经接受的请求
- **WHEN** 相同 client request identity/fingerprint 已经对应一个 durable Run，而当前环境随后发生变化
- **THEN** 服务优先返回原 Run 及其当前状态，不以新的 Readiness 结果破坏既有幂等身份

### Requirement: Readiness 错误必须与执行失败分离
Run create error SHALL 明确区分 revision/环境尚未就绪与已经 accepted Run 的 binding、设备、
runtime 或 evidence failure。客户端 MUST 能基于稳定 code 呈现修复入口，而不解析任意异常文本。

#### Scenario: 已知配置错误被同步拒绝
- **WHEN** Run 创建前可确定 LLM dependency、SecretRef 或 Profile 缺失
- **THEN** HTTP 返回安全 4xx readiness envelope，而不是 `202` 后产生 `kernelStatus=not_started` 的普通 failure Run

