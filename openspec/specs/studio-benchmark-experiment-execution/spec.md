# studio-benchmark-experiment-execution Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-execution-worker-5-2b. Update Purpose after archive.
## Requirements
### Requirement: Accepted Experiment 必须通过持久队列串行执行
Stage 5.2B SHALL 将已提交的 `accepted` Experiment 视为持久待执行事实，并由一个
process-scoped single-worker dispatcher 领取。Worker MUST 通过 repository
compare-and-swap 将一个具体 Experiment 从 `accepted` claim 为 `starting`；同一
Experiment 不得同时存在两个执行 owner。进程内 scheduler MUST NOT 保存无界 pending
payload queue，等待项的定义和顺序 SHALL 继续以 repository 中的稳定资源为事实源。

#### Scenario: 两个 Experiment 连续创建
- **WHEN**第一个 Experiment 正在运行时第二个有效 Experiment 被持久创建
- **THEN**第二个保持 accepted 且不被判为 device/scheduler failure，并在第一个释放 worker 后被串行 claim

#### Scenario: 重复唤醒同一 Experiment
- **WHEN**create 重试或并发通知多次请求 dispatcher 处理同一 accepted identity
- **THEN**最多一个 claim 成功且 Benchmark Runtime 只执行一次该 Experiment

#### Scenario: worker claim 与 accepted cancel 竞争
- **WHEN**worker 和 cancel command 同时竞争 accepted Experiment
- **THEN**repository 只提交一个合法前向结果：开始执行或 cancelled-before-start，不产生部分设备执行

### Requirement: Execution preflight 必须先于设备和插件副作用
Worker SHALL 在解析 runtime device profile、获取设备 handle、运行 initializer、
evaluator、Agent 或模型前，重新验证 immutable snapshot 的 schema、snapshot
fingerprint、V1 cardinality、planned schedule、AgentGraph/Plan/Protocol canonical
identity、Catalog source、Package content、声明 resource digest、组件可绑定性和受控
evidence storage capacity。任一失败 MUST 以安全稳定错误终止 Experiment/TaskRun，
且 MUST NOT 连接设备或执行 Benchmark plugin。

#### Scenario: Package 在 create 后漂移
- **WHEN**snapshot 中的 Package/content/Plan identity 与 execution 时允许来源不再一致
- **THEN**worker 在 profile resolve 和设备调用前终止为 definition/resource preflight failure，并保留原 snapshot

#### Scenario: resource digest 无法验证
- **WHEN**Task 声明的 resource 或 ground-truth logical URI 缺失、越界或 digest 不匹配
- **THEN**worker 不 materialize TaskInstance、不连接设备，并记录有界 resource diagnostic

#### Scenario: evidence storage 不足
- **WHEN**preflight 无法为该 Experiment 保证受控 evidence namespace 和最低写入容量
- **THEN**Experiment 以 service failure 收口，不删除旧 Experiment 或 artifact 腾空间，设备调用数为零

### Requirement: Worker 必须从 Experiment snapshot 重建执行输入
Worker SHALL 只从 Experiment-owned immutable snapshot 读取 AgentGraph、
BenchmarkPlan、ExperimentProtocol、task selection、schedule、derived seed 和安全
profile identity。它 MUST 重新验证 canonical identities，并通过正式 component
discovery/binding 产生 fresh `ExecutableAgent`；当前 Agent revision、当前 Package
默认值、浏览器 draft、进程内 preview cache 或客户端提交的运行对象 MUST NOT 改写
已接受定义。

#### Scenario: Agent 保存了新 revision
- **WHEN**Experiment accepted 后同一 Agent 又保存当前 revision
- **THEN**worker 仍执行 snapshot 中的旧 revision/AgentGraph identity

#### Scenario: snapshot AgentGraph 被篡改
- **WHEN**持久 body 与持久 canonical graph identity 不一致
- **THEN**worker 在 component 和设备副作用前以 graph-integrity failure 终止

#### Scenario: component 无法绑定
- **WHEN**snapshot 引用的 component 在 execution environment 中不可解析或合同不兼容
- **THEN**worker 返回安全 binding failure，不回退到旧 `AgentRunner` 或修改 Graph Runtime kernel

### Requirement: Worker 必须委托现有 Benchmark Experiment Runtime
通过 preflight 的执行 SHALL 调用现有 `BenchmarkExperimentRuntime` 完成
TaskInstance materialization、reset、setup、evaluator pre-hook、Agent、evaluation 和
cleanup。Studio worker MUST NOT 复制 Benchmark schedule、Evaluator Tree、outcome、
failure policy、Graph execution loop 或统计实现，也 MUST NOT 在 Graph Runtime kernel
增加 Studio/Benchmark 特判。

#### Scenario: fake-device PASS
- **WHEN**一个符合 V1 cardinality 的 snapshot 在 fake device 上完成 Agent 和 evaluator
- **THEN**worker 持久化 Core 产生的正式 phases、Agent status、PASS outcome 和 TaskResult

#### Scenario: Agent SUCCESS 但 evaluator FAIL
- **WHEN**Graph Runtime 成功而正式 evaluator 返回 false
- **THEN**Experiment 正常 terminal/completed，TaskRun 同时保留 Agent SUCCESS 与 Benchmark FAIL

#### Scenario: initializer 导致 INVALID
- **WHEN**Core 按 Protocol 将 initializer/evaluator infrastructure failure 归类为 INVALID
- **THEN**worker 保存 INVALID 与实际未产生的 Agent availability，不将其改写成普通 Agent failure

### Requirement: Planned TaskRun identity 必须映射到 Core provenance
Worker SHALL 保持 5.2A 创建的 planned `taskRunId` 为 Studio resource identity。Core
materialization 后产生的 TaskInstance identity、Core task-run identity、Agent run
identity和 source-local event sequence SHALL 作为 provenance 附加，MUST NOT 覆盖
planned identity。V1 一个 Agent、一个 Task、一个 repeat 的映射 MUST 同时核对
agent、task、repeat、order 和 canonical definition，不能仅按数组位置猜测。

#### Scenario: 动态 TaskInstance 成功物化
- **WHEN**Core 为 planned entry 产生动态 TaskInstance 和不同格式的 Core task-run identity
- **THEN**GET 仍使用原 planned TaskRun identity，并返回 Core/TaskInstance identities 作为运行事实

#### Scenario: Core 结果坐标不匹配
- **WHEN**Core 返回的 agent、task 或 repeat 无法唯一匹配 planned entry
- **THEN**worker 以 integrity failure 停止收口，不把结果挂到错误 TaskRun

### Requirement: Device profile 只能在 execution boundary 解析并独占租赁
Worker SHALL 在纯 preflight 成功且再次检查 cancellation 后，才把公共
`deviceProfileId` 解析为当前私有 binding，并 MUST 将其与 accepted aggregate 的 pinned
binding fingerprint 比较。匹配后，worker SHALL 只验证 exact target 的 ready 状态，
在任何设备操作前获取基于 private target identity 的进程内独占租约，并再次检查
cancellation。Worker MUST NOT 使用 `serial=None`、在线设备数量或显示名称回退选择设备；
多个 profile 或 Run/Experiment 只要指向同一 target 就 MUST 共享同一租约。租约 MUST
在 success、failure、cancel 和未知异常路径释放；raw serial、private fingerprint、
device handle 和 ADB 参数 MUST NOT 进入 snapshot、journal、result、report、Replay 或 HTTP。

#### Scenario: profile 不可用
- **WHEN**execution 时安全 profile 不存在、没有 exact target 或无法解析
- **THEN**Experiment 以安全 device-profile failure 收口且没有 initializer、Agent 或 evaluator 副作用

#### Scenario: profile binding 漂移
- **WHEN**当前 private binding fingerprint 与 accepted Experiment 的 pinned fingerprint 不同
- **THEN**Experiment 以 stable binding-drift failure 收口，不连接旧 target、新 target 或其他在线设备

#### Scenario: exact target 不 ready
- **WHEN**所绑定 target 缺失、offline 或 unauthorized
- **THEN**worker 在 Benchmark Runtime 和任何 task action 前安全失败，公共 diagnostic 不包含 target serial

#### Scenario: 多个设备在线
- **WHEN**ADB 报告多个 ready 设备且其中一个是 profile 的 exact target
- **THEN**worker 只使用 exact target，不返回 ambiguity 也不选择其他设备

#### Scenario: 同一设备已被占用
- **WHEN**另一个 Run 或 Experiment 通过不同或相同 profile 已持有目标设备租约
- **THEN**当前 Experiment 不执行设备动作并保留可审计 device-busy service failure

#### Scenario: Protocol device context 不匹配
- **WHEN**exact target authority 成功但 Core preflight 发现 platform、locale、orientation 或 required-App 不匹配
- **THEN**Core 在 Agent action 前产生正式 INVALID/provenance，Studio 不改写为普通 service failure

#### Scenario: 执行抛出未知异常
- **WHEN**设备租约内的 worker 发生未分类异常
- **THEN**worker 释放 target-level 租约、移除 active cancellation signal，并通过唯一合法终态保存安全 failure

### Requirement: Worker 必须确定性收口生命周期和终态
Worker SHALL 以事务化前向转换投影 Experiment 的
`accepted → starting → running → finalizing → terminal` 与 cancellation 分支，以及
TaskRun 的
`scheduled → preparing → running → evaluating → cleaning_up → terminal`。完成全部
Core lifecycle SHALL 使用 Experiment terminal reason `completed`，无论正式 outcome
是 PASS、FAIL 还是 INVALID；preflight、journal、evidence 或未处理 service failure
SHALL 使用 `failed`。Worker MUST 在任一路径产生最多一个 immutable terminal
transition/event，并拒绝迟到 owner 的逆向写入。

#### Scenario: FAIL 正常收口
- **WHEN**TaskResult 正式 outcome 为 FAIL 且 cleanup/finalization 正常完成
- **THEN**TaskRun terminal/completed，Experiment terminal/completed，结果仍为 FAIL

#### Scenario: completion 与 cancel 竞争
- **WHEN**最后结果提交与 cancellation request 并发
- **THEN**repository 保存一条合法 transition 序列、一个 terminal reason 和一个 terminal event，已提交 outcome 不被覆盖

#### Scenario: worker callback 未处理异常
- **WHEN**执行 callback 在 Core result 提交前抛出未知异常
- **THEN**orchestrator 尽最大可能以 terminal/failed 收口并保留最后成功提交的 journal high-water mark

### Requirement: Stage 5.2B 必须执行严格第一切片
Stage 5.2B SHALL 只执行一个 Agent revision、一个 Benchmark Catalog entry、一个
selected Task 和一个 repeat。DTO SHALL 继续使用复数 Agent/task/schedule 结构；任何
超限 snapshot MUST 整体返回 `unsupported_cardinality` 并在设备副作用前终止，不得
截断或只运行第一项。真实 Android 支持 MUST NOT 仅由 fake-device 测试宣称。

#### Scenario: 合法第一切片
- **WHEN**snapshot 包含 1 Agent × 1 Task × 1 repeat 且 schedule 恰有一个 planned entry
- **THEN**worker 可以进入 execution preflight 和 fake-device Runtime 验收

#### Scenario: 两个 planned entries
- **WHEN**篡改或未来客户端提交两个 Agent、Task 或 repeats 导致多个 schedule entries
- **THEN**worker 在 profile resolve 前整体终止 unsupported-cardinality，不执行部分 schedule

