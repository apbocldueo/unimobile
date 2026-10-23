# studio-benchmark-experiment-event-stream Specification

## Purpose
定义 Benchmark Experiment 持久事件 journal、连续查询、可恢复 SSE、终态与 recovery 事件以及 Live/Replay 投影边界。
## Requirements
### Requirement: Experiment event stream 必须以持久 journal 为事实源
系统 SHALL 为每个 Benchmark Experiment 保存版本化
`StudioBenchmarkEventEnvelope` journal。每个 envelope MUST 包含 Experiment identity、
严格递增 sequence、stable event identity、timestamp、source、versioned kind 和安全
payload，并可显式关联 TaskRun、Benchmark phase、nested Agent run/node/activation 与
source-local sequence。任何 source-local sequence MUST NOT 替代 Experiment journal
sequence。

#### Scenario: 保存 Benchmark lifecycle event
- **WHEN**event adapter 收到 TaskRun evaluation start
- **THEN**journal 分配下一 Experiment sequence，并保留 TaskRun、phase 和原始 source identity

#### Scenario: Agent 与 service sequence 重叠
- **WHEN**nested Agent event 和 Experiment service event 都具有 source sequence 4
- **THEN**二者获得不同 journal sequence，且各自 source/sequence 均保留

### Requirement: 事件必须先提交再对 live 客户端可见
Event append SHALL 在通知 SSE waiter 或更新 live projection 前原子持久化。若 journal
写入失败，execution service MUST NOT 继续产生无法审计的新设备副作用；它 SHALL
请求协作取消并以 evidence failure 收口，同时保留最后已确认 high-water mark。

#### Scenario: 正常发布 event
- **WHEN**journal append 成功
- **THEN**HTTP query 可读取该 event 后 waiter 才被通知

#### Scenario: event 写入失败
- **WHEN**SQLite/event repository 无法提交一个 Runtime event
- **THEN**SSE 不发送该 event，服务请求安全停止且不伪造 sequence

### Requirement: Event query 必须提供有界连续 backfill
Studio HTTP SHALL 提供 Experiment-scoped event query，接受 exclusive `after` cursor
和有界 limit，返回按 journal sequence 排序的 events、next cursor、high-water mark
和 terminal flag。服务 MUST 验证 cursor，并 MUST NOT 静默跳过保留范围中的 sequence
缺口。

#### Scenario: 分页补齐断线 events
- **WHEN**客户端从 sequence 20 请求两页后续 events
- **THEN**拼接结果从 21 连续开始、无重复无遗漏，next cursor 是最后返回 sequence

#### Scenario: cursor 超过 high-water mark
- **WHEN**客户端提交未来 cursor
- **THEN**服务返回 invalid-cursor error，不把它表示为暂无新事件

### Requirement: SSE 必须使用 named event、cursor 恢复和 heartbeat
Experiment SSE SHALL 使用 journal sequence 作为 SSE `id`，使用版本化 named event
和 JSON data，支持 `Last-Event-ID` 及等价显式 cursor，并执行 backfill-before-wait。
空闲连接 SHALL 发送不推进 cursor 的 heartbeat；客户端断开 MUST NOT 取消或改变
Experiment。

#### Scenario: SSE 重连
- **WHEN**客户端确认 sequence 12 后断线并用 `Last-Event-ID: 12` 重连
- **THEN**服务从 13 开始补发持久 events，不重新执行 TaskRun

#### Scenario: 空闲 heartbeat
- **WHEN**Experiment 暂时没有新事件
- **THEN**连接收到 heartbeat/comment，projection cursor 保持不变

#### Scenario: 浏览器关闭连接
- **WHEN**SSE socket 被关闭
- **THEN**handler 释放连接资源，Experiment lifecycle 与 cancellation 不改变

### Requirement: Event kinds 必须版本化并可渐进扩展
Journal SHALL 至少区分 Experiment lifecycle、TaskRun lifecycle、Benchmark phase、
nested Agent event、artifact availability、result/report availability、recovery 和
terminal kinds。未知的未来 kind MUST 能被旧客户端保留 cursor 并忽略或显示
unsupported，而不得使整个 stream 无法继续。

#### Scenario: 旧客户端遇到新 event kind
- **WHEN**stream 中出现客户端不识别但 envelope/schema 合法的新 kind
- **THEN**客户端推进并持久化 cursor、忽略或显示 unsupported event，后续已知 event 继续投影

#### Scenario: envelope schema 不支持
- **WHEN**客户端收到不兼容 major schema
- **THEN**客户端停止事实投影并显示 version error，不猜测 payload 字段

### Requirement: 慢客户端不得反压 Benchmark Runtime
SSE delivery SHALL 从持久 journal 分页读取并使用每连接有界状态。Runtime append
MUST NOT 等待任何特定客户端消费；连接数、page size、heartbeat、write timeout 和
单 event size MUST 有可配置上限。

#### Scenario: 一个 monitor 停止读取
- **WHEN**某 SSE 客户端持续落后而另一个正常消费
- **THEN**Runtime 和正常客户端继续，慢连接安全关闭后可用 cursor 恢复

#### Scenario: event payload 超限
- **WHEN**Runtime evidence 大于 inline event limit
- **THEN**journal 保存有界 typed artifact reference/diagnostic，不把大型内容写入 SSE frame

### Requirement: Event append 必须幂等并检测 identity 冲突
Journal SHALL 以 `(experiment_id, stable_event_identity)` 和 sequence 约束事件。相同
identity 与 canonical payload fingerprint 的重试 MUST 返回原 sequence；相同 identity
但 fingerprint 不同 MUST 产生 integrity conflict，并阻止冲突内容进入 query/SSE
投影。

#### Scenario: event sink 重试
- **WHEN**adapter 使用相同 stable identity 和内容重复 append
- **THEN**repository 返回原 event，不增加 sequence

#### Scenario: identity 内容冲突
- **WHEN**相同 stable identity 被用于不同 TaskRun 或 payload
- **THEN**append 失败并触发安全 integrity handling，两个内容不会混合

### Requirement: Experiment 必须最多有一个 terminal event
无论 completed、cancelled、failed 或 interrupted，Experiment SHALL 最多提交一个
terminal journal event。该 event MUST 在最终 Experiment snapshot、TaskRun facts、
result/report/replay availability 和 high-water mark 已持久化后提交；SSE 在发送所有
已提交 events 与 terminal event 后 SHALL 正常结束。

#### Scenario: 正常完成
- **WHEN**TaskRuns、report availability 和 Replay links 已收口
- **THEN**journal 提交唯一 terminal event，客户端可停止重连并通过 query 读取最终资源

#### Scenario: cancel 与 completion 竞争
- **WHEN**cancel finalizer 与 runtime completion 几乎同时收口
- **THEN**journal 只有一个与 repository 终态一致的 terminal event

### Requirement: Recovery 决策必须成为 durable event
Startup recovery SHALL 为每个被处理的非终态 Experiment 提交版本化、bounded 且经过
安全处理的 recovery event，至少记录 previous lifecycle、decision、受影响 TaskRuns、
prior journal high-water mark 和 attempt identity。Requeue、interrupt、
publication-only 和 finalize-only decision MUST 使用稳定 kind，并在对应状态改变对
scheduler、publisher、query 或 SSE 可见前原子提交。Payload MUST NOT 包含 raw process
owner、数据库/lock 路径、设备 serial、凭据或大型 evidence。Recovery MUST NOT 通过
内存日志或 HTTP 文案隐式改变状态。

#### Scenario: accepted Experiment 重新入队
- **WHEN** recovery 确认尚无副作用并重新入队
- **THEN** journal 原子记录 requeue decision，原 Experiment identity、既有 sequence 与 cursor 连续

#### Scenario: starting Experiment 重置
- **WHEN** recovery 将 side-effect-free `starting` attempt 重置为 `accepted`
- **THEN** recovery event 记录旧 lifecycle 与 requeue decision，但不包含内部 owner 或设备 locator

#### Scenario: running Experiment 被中断
- **WHEN** recovery 不安全重跑 in-flight TaskRun
- **THEN** journal 先记录 interrupt decision 和 prior high-water，再提交 TaskRun terminal facts，最后提交唯一 Experiment terminal event

#### Scenario: finalizing 只重试 publication
- **WHEN** recovery 发现 immutable TaskResult 且 publication transaction 未提交
- **THEN** journal 记录 publication-only decision，后续 publication facts 与 terminal event 沿同一连续 cursor 提交

#### Scenario: finalizing 只完成终态
- **WHEN** recovery 发现无需 publication 的 terminal TaskRun facts
- **THEN** journal 记录 finalize-only decision 后提交唯一 Experiment terminal event，不伪造 result 或 Replay event

#### Scenario: terminal Experiment 保持不可变
- **WHEN** startup scan 遇到 terminal Experiment
- **THEN** journal 不追加 recovery event，既有 terminal event 继续保持唯一且为该 Experiment 最后一个事件

#### Scenario: commit 前 recovery 失败
- **WHEN** recovery event 与对应 aggregate transition 的 transaction 回滚
- **THEN** event query、SSE waiter 和 scheduler 均看不到该 attempt，下一次 startup 可以重新决策

#### Scenario: 同一 recovery attempt 重试
- **WHEN** repository 以相同 stable recovery event identity 和 canonical payload 重试
- **THEN** journal 返回原 sequence，不增加重复 decision event；内容冲突则按 event integrity contract 拒绝

### Requirement: Live 与 Replay projection 必须能共享事实而不共享传输状态
Experiment monitor SHALL 先通过有界 HTTP page 连续 backfill 到一次查询所得
high-water，再以最后确认的 Experiment-local sequence 建立 named SSE，并分别维护
authoritative facts、transport/cursor state、visual follow state 和用户 selection。
Event 到达 MAY 使 Experiment 与 TaskRun query 失效并触发刷新，但客户端 MUST NOT
从 event stream 自行推导 recovery、evaluation、terminal outcome 或持久 resource。
客户端 MUST 接受 canonical content 相同的精确重复、用 HTTP backfill 修复 gap、
保留 unknown versioned kind 并推进 cursor；无法恢复的 continuity 或 identity/content
冲突 MUST 冻结最后已验证前缀而不得静默跳过。TaskRun terminal 后进入 Replay 时 MUST
使用持久 evidence envelope，而不是把当前 SSE 内存缓存冒充 Replay。

#### Scenario: 用户锁定历史 TaskRun
- **WHEN**新 event 到达但用户已选择旧 TaskRun
- **THEN**authoritative projection/cursor 继续前进，selection 保持锁定并提示可回到当前

#### Scenario: terminal 后打开 Replay
- **WHEN**TaskRun 显示 replay available
- **THEN**客户端通过显式 Replay link 加载持久 envelope，不依赖仍然打开的 SSE buffer

#### Scenario: backfill 后进入 live
- **WHEN**Monitor 首次加载且 durable journal 已包含多页历史 events
- **THEN**客户端先连续读取到固定 high-water，再从最后确认 sequence 建立 SSE，不丢失两阶段交界处提交的 event

#### Scenario: SSE gap 可恢复
- **WHEN**客户端确认 sequence 14 后收到 sequence 17
- **THEN**客户端通过 event page 获取并验证 15 与 16 后再投影 17

#### Scenario: 重连收到精确重复
- **WHEN**SSE 重发一个 sequence、event identity 与 canonical content 均已确认的 envelope
- **THEN**客户端不重复应用事实且 cursor 保持单调

#### Scenario: event 完整性冲突
- **WHEN**相同 sequence 或 event identity 出现不同 canonical content，或缺口无法从 durable page 补齐
- **THEN**客户端冻结最后已验证前缀、停止 live 推进并显示完整性错误

#### Scenario: event 只触发权威资源刷新
- **WHEN**客户端收到 terminal 或 recovery event
- **THEN**客户端刷新 Experiment 与 TaskRun resource，并以资源响应作为 lifecycle 与 outcome 的权威事实

### Requirement: Stage 5.2A journal 必须先建立 aggregate audit foundation
Stage 5.2A SHALL 使用正式 versioned `StudioBenchmarkEventEnvelope` 和 typed journal
port 原子保存 aggregate-originated accepted、accepted cancellation、TaskRun terminal
与唯一 Experiment terminal facts。首次 accepted event MUST 与 Experiment 和 planned
TaskRuns 在同一 create transaction 提交；accepted-cancel events MUST 与对应 lifecycle
变更在同一 cancel transaction 提交。Sequence SHALL 从 1 严格递增，stable event
identity 与 canonical payload fingerprint MUST 检测相同 identity 的内容冲突。

#### Scenario: 创建 accepted aggregate
- **WHEN**Experiment create transaction 提交成功
- **THEN**journal 已包含唯一 sequence-1 accepted event，Experiment high-water mark 为 1

#### Scenario: 相同 create 重试
- **WHEN**客户端对已创建 Experiment 提交 same-content idempotent retry
- **THEN**服务返回现有 resource，journal 不追加第二个 accepted event

#### Scenario: accepted cancel 收口
- **WHEN**accepted Experiment 被成功取消
- **THEN**cancellation、TaskRun terminal 和唯一 Experiment terminal facts 与终态原子可见，sequence 连续

### Requirement: Stage 5.2A 不得发布尚未实现的 live event transport
Stage 5.2A resource MAY 暴露持久 event high-water mark，但 HTTP links 和 capability
metadata MUST NOT 声称 event query、SSE、heartbeat、runtime event adapter 或 live
projection 已可用。后续 transport SHALL 读取同一 durable journal，不得用进程内缓存
建立竞争性事实源。

#### Scenario: 查询 Stage 5.2A Experiment links
- **WHEN**客户端 GET 一个 accepted 或 accepted-cancelled Experiment
- **THEN**响应不包含 event query 或 SSE link，且 high-water mark 只描述已提交 journal facts

#### Scenario: 服务重启
- **WHEN**Stage 5.2A 服务使用同一数据库重启
- **THEN**high-water mark 与 journal sequence 仍由持久记录确定，不从内存重建或伪造

### Requirement: Stage 5.2B runtime producer 必须写入同一 durable journal
Stage 5.2B SHALL 将 worker lifecycle、TaskRun lifecycle 和
`BenchmarkExperimentRuntime` phase events 适配为正式 versioned
`StudioBenchmarkEventEnvelope`，并写入 5.2A 已建立的 Experiment-local journal。
Experiment journal sequence SHALL 是唯一投影 cursor；Benchmark Core sequence SHALL
只作为 `sourceSequence` provenance。Producer MUST 使用稳定 event identity 和 canonical
fingerprint，使相同内容重试幂等、相同 identity 不同内容产生 integrity conflict。

#### Scenario: Core phase event 被提交
- **WHEN**Benchmark Runtime 发出一个 evaluation start event
- **THEN**journal 追加一个关联 planned TaskRun 的 versioned phase event，并分别保留 Experiment sequence 与 Core source sequence

#### Scenario: 相同 producer event 重试
- **WHEN**worker 以同一 stable event identity 和 canonical content 重试 append
- **THEN**repository 返回原 sequence，不增加 duplicate event 或 high-water mark

#### Scenario: source identity 内容冲突
- **WHEN**同一 stable event identity 被用于不同 planned TaskRun 或 payload
- **THEN**journal 拒绝冲突内容、请求安全取消，并保留最后成功提交的连续 sequence

### Requirement: Runtime event 必须使用 planned TaskRun scope
Runtime producer SHALL 通过 agent、task、repeat、planned entry 和 definition identity
把 Core event 映射到唯一 planned TaskRun。公共 envelope 的 `taskRunId` MUST 使用
5.2A planned identity；Core task-run/Agent-run identities MAY 作为有界 provenance，
但 MUST NOT 替换 resource identity。无法唯一映射的事件 MUST 触发 integrity failure，
不得猜测归属。

#### Scenario: Core 与 Studio identity 格式不同
- **WHEN**Core event 携带裸 hash task-run identity 而 Studio 使用 `task-run-*` identity
- **THEN**envelope 归属稳定 Studio TaskRun，并在 provenance 中保留安全 Core identity

#### Scenario: event 坐标不在 schedule 中
- **WHEN**Core event 的 task/repeat/agent 与 immutable planned schedule 不匹配
- **THEN**producer 不把该 event 写到任意 TaskRun，worker 进入安全 integrity failure 收口

### Requirement: Journal append failure 必须阻止新的执行副作用
每个 Benchmark lifecycle event SHALL 在 Runtime 开始下一项可观察副作用前同步提交
journal。Append 失败 MUST 不通知任何 live consumer，MUST 触发共享 cooperative
cancellation signal，并 MUST 使 worker 停止启动新的 phase、Agent activation 或
TaskRun。系统不宣称能够回滚该 event 之前已完成的外部操作，且 SHALL 保留最后成功
提交的 journal high-water mark。

#### Scenario: phase start append 失败
- **WHEN**reset start event 无法持久化
- **THEN**reset initializer 不执行，cancellation 被请求，resource 以 journal service failure 收口

#### Scenario: phase complete append 失败
- **WHEN**设备调用已返回但对应 complete event 无法提交
- **THEN**worker 不启动下一 phase，保留先前已提交证据并报告 journal failure，不声称回滚设备调用

### Requirement: Stage 5.2B terminal event 必须与最终事实一致
Worker SHALL 在 Experiment、TaskRun、bounded result 和所有本阶段 availability 已持久
收口后提交最多一个 `experiment.terminal.v1`。Cancel、completion、journal failure 和
worker failure 竞争时，失败竞争者 MUST 读取当前 immutable terminal fact；迟到 runtime
event MUST NOT 推进 terminal Experiment 的 journal。

#### Scenario: 正常 completed
- **WHEN**TaskRun result、outcome 和 lifecycle 均已提交
- **THEN**唯一 terminal event 与 terminal/completed resource 一致且成为本阶段最后 high-water mark

#### Scenario: terminal 后迟到 event
- **WHEN**旧 callback 在 terminal commit 后尝试 append phase event
- **THEN**repository 拒绝 event，Experiment lifecycle 和 high-water mark 不被改写

### Requirement: Stage 5.2B 不得提前发布 public event transport
Stage 5.2B MAY 为测试和后续 composition 提供 typed internal event query/append port，
但 HTTP links 和 capability metadata MUST 继续声明 event query、SSE、heartbeat 和
live projection 不可用。Stage 5.2C SHALL 读取本 Change 产生的同一 durable journal，
而不得迁移到进程内 event cache。

#### Scenario: 运行中查询 Experiment resource
- **WHEN**worker 已写入多个 runtime journal events
- **THEN**resource high-water mark 前进但不包含未实现的 events 或 eventStream link

#### Scenario: 进程内 worker 完成
- **WHEN**Experiment terminal 且 journal 已保存全部本阶段事件
- **THEN**重启后内部 repository 仍能读取相同 sequence，公共 SSE 能力仍不被宣称

### Requirement: Stage 5.2C-1 必须提供有界且连续的 Experiment event page
系统 MUST 通过 `GET /studio/benchmark-experiments/{experimentId}/events` 返回严格版本化的 `StudioBenchmarkEventPageV1`。查询 MUST 使用非负 Experiment-local sequence 作为 exclusive positional cursor，限制每页数量，并返回有序 `items`、`nextCursor`、查询时的 `highWaterMark` 和 drain-aware `terminal`；cursor 超出 high-water、journal sequence 不连续或持久 high-water 与事件事实不一致时 MUST 返回稳定、安全且可区分的错误，不得静默跳过事件。

#### Scenario: 有界 backfill 连续推进
- **WHEN** 客户端从 `after=0` 分页读取一个拥有多页 durable events 的 Experiment
- **THEN** 每页 items 按连续 sequence 升序返回，`nextCursor` 指向本页最后一个事实，且所有页面组合后既无重复也无缺口

#### Scenario: 拒绝非法或未来 cursor
- **WHEN** 客户端提交 malformed、负数或大于当前 `highWaterMark` 的 cursor
- **THEN**系统在返回任何事件前以稳定 4xx 错误拒绝请求，且不修改 Experiment 或 journal

#### Scenario: 持久 journal 完整性冲突
- **WHEN**查询发现 sequence gap、重复位置或 Experiment high-water 与已提交事件不一致
- **THEN**系统以稳定 integrity conflict 拒绝该页而不是返回看似连续的不完整历史

### Requirement: Stage 5.2C-1 SSE 必须支持 backfill、恢复、heartbeat 与终态 drain
系统 MUST 通过 `GET /studio/benchmark-experiments/{experimentId}/events/stream` 先读取 durable backfill，再等待新提交事实。客户端 MUST 能使用 `after` 或 `Last-Event-ID` 恢复；两者同时存在但不一致时 MUST 在建立 stream 前拒绝。每个 durable envelope MUST 作为固定 `event: journal` frame 发送并以 sequence 作为 SSE `id`；heartbeat MUST 是不带 journal id 的 named event且不得推进 cursor。只有 terminal Experiment 的唯一 terminal event 已成为最终 high-water 且客户端已 drain 到该位置时，stream 才 MUST 关闭。

#### Scenario: 刷新后从 high-water 继续
- **WHEN**客户端记录最后收到的 SSE id，断开后以该 `Last-Event-ID` 重连
- **THEN**服务先发送该 cursor 之后的 durable events，不重发已确认 sequence，也不跳过已提交 sequence

#### Scenario: 空闲连接收到 heartbeat
- **WHEN**客户端已追平 high-water 且 heartbeat 周期内没有新事件
- **THEN**服务发送不带 journal id 的 `event: heartbeat`，客户端 cursor 保持不变

#### Scenario: 终态事实 drain 后关闭
- **WHEN**terminal event 已提交但客户端仍落后于最终 high-water
- **THEN**服务先发送剩余所有 durable events，并仅在 terminal event 已交付后关闭连接

#### Scenario: 浏览器断开不取消 Experiment
- **WHEN**浏览器刷新、关闭页面或因网络原因断开 SSE
- **THEN**服务仅释放该连接的 transport/waiter 状态，不请求取消或改变 Experiment lifecycle

### Requirement: Stage 5.2C-1 live 通知必须发生在 durable commit 之后
系统 MUST 仅在包含新事件的数据库事务成功提交后通知本进程等待者。通知 MUST 只是降低读取延迟的提示，不得携带或缓存权威事件 payload；通知失败或丢失 MUST NOT 回滚已提交事实，等待者 MUST 能在有界 heartbeat 后重新查询 SQLite 并发现该事实。

#### Scenario: 提交失败不得产生 live 可见性
- **WHEN**一个事件事务在 commit 前失败或回滚
- **THEN**系统不通知 live 等待者且 page/SSE 均不能观察到该事件

#### Scenario: 通知器失败不损坏已提交事实
- **WHEN**事件已成功提交但 process-local notifier 抛错或通知丢失
- **THEN**producer 不得撤销持久事实，客户端在后续有界 re-query 中仍能读取该 sequence

### Requirement: Stage 5.2C-1 慢客户端必须被有界隔离
系统 MUST 对 event page size、每连接保留状态、SSE 写等待、waiter registry 和并发 SSE 连接数设置有限上限。每个连接只可保留当前 cursor 与有界 page；慢客户端、写超时或连接容量耗尽 MUST NOT 反压 Benchmark worker、阻塞其他客户端或造成无界内存增长。

#### Scenario: 慢客户端不阻塞 producer 与快速客户端
- **WHEN**一个 SSE consumer 停止读取而另一 consumer 与 worker 正常运行
- **THEN**慢连接在写超时或断开边界内被释放，worker 的 durable append 与快速客户端的读取继续推进

#### Scenario: 连接容量在响应前执行
- **WHEN**并发 SSE 连接已达到配置上限
- **THEN**新请求在发送 `200 text/event-stream` 之前收到稳定的服务容量错误，现有 stream 与 worker 不受影响

### Requirement: Stage 5.2C-1 public event transport 必须保持事实安全
Event page 与 SSE MUST 只序列化已经通过 `StudioBenchmarkEventEnvelopeV1` 验证、大小限制和敏感值清理的 durable facts。服务 MUST 保持 unknown future event kinds 可传输，并且 transport 日志或错误不得泄露 payload、凭据、设备句柄或内部异常细节。

#### Scenario: 版本化 unknown kind 可推进 cursor
- **WHEN**journal 中存在当前客户端未识别但符合 envelope contract 的 future kind
- **THEN**page 与固定 `journal` SSE frame 原样传输该 versioned envelope，sequence 仍正常推进

#### Scenario: 敏感 canary 不出现在 public transport
- **WHEN**runtime 输入或异常包含 token、password、API key 或 device handle canary
- **THEN**event page、SSE frame、HTTP error 与 server log 均不包含原始敏感值

