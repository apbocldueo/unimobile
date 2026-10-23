# studio-run-event-stream Specification

## Purpose
定义 Studio live Run 的持久事件 journal、连续查询、SSE 恢复、幂等性、背压隔离与唯一终止事件合同。

## Requirements

### Requirement: 事件流必须以持久 journal 为事实源
系统 SHALL 为每个 Run 保存版本化 `StudioRunEventEnvelope` journal。每个 envelope MUST
包含 run identity、严格递增的 journal sequence、stable event identity、timestamp、
source、kind、schema version 和安全 payload；包装原生 `RunEvent` 时 MUST 同时保留其
runtime sequence、node path、activation 和 interaction identity。

#### Scenario: 保存一个 Runtime event
- **WHEN** Runtime event sink 收到 activation complete 事件
- **THEN** journal 分配下一个 sequence，持久保存原生 runtime identity 与安全 payload

#### Scenario: 服务事件与 Runtime sequence 重叠
- **WHEN** Run lifecycle 事件和原生 Runtime event 都使用自己的 source-local sequence
- **THEN** journal 使用独立严格递增 sequence 排序，并保留各自原始 sequence 而不覆盖

### Requirement: 事件必须先持久化再对 live 客户端可见
event sink SHALL 在通知 SSE waiter 之前原子提交 journal event。若 journal 持久化失败，
执行服务 MUST NOT 继续产生无法审计的副作用；它 SHALL 请求取消并以 evidence failure
终止或收口 Run，同时保留最后已确认 high-water mark。

#### Scenario: 正常发布事件
- **WHEN** journal append 成功
- **THEN** 查询和 SSE 都能读取该 event，随后 waiter 才被唤醒

#### Scenario: SQLite append 失败
- **WHEN** Runtime event 无法写入 journal
- **THEN** 服务不向 SSE 声称该 event 已提交，并停止继续无证据执行

### Requirement: Event query 必须提供有界连续 backfill
Studio HTTP SHALL 提供 run-scoped event query，接受 exclusive `after` cursor 和有界
limit，返回严格按 journal sequence 排序的 events、next cursor、high-water mark 和
terminal flag。服务 MUST 验证 cursor，不得静默跳过保留范围内的 sequence 缺口。

#### Scenario: 分页补齐离线期间事件
- **WHEN** 客户端从最后确认 sequence 请求后续两页
- **THEN** 两页连接后无重复、无遗漏，next cursor 等于最后返回 sequence

#### Scenario: cursor 超过 high-water mark
- **WHEN** 客户端提交未来 sequence
- **THEN** 服务返回结构化 invalid-cursor error，不把它降级为“没有新事件”

### Requirement: SSE 必须支持标准 cursor 恢复和 heartbeat
SSE endpoint SHALL 将 journal sequence 作为 `id`，使用版本化 event name 和 JSON data，
支持 `Last-Event-ID` 以及等价显式 cursor，先 backfill 再等待新提交。空闲连接 SHALL
发送不改变 cursor 的 heartbeat；HTTP 重连 MUST NOT 触发新 Run 或重新执行组件。

#### Scenario: SSE 中途断线并重连
- **WHEN** 客户端确认 sequence 12 后断线，再以 `Last-Event-ID: 12` 重连
- **THEN** 服务从 13 开始补发持久 events，且已完成 activation 不重复执行

#### Scenario: 空闲连接心跳
- **WHEN** Run 暂时没有新 event
- **THEN** 服务周期性发送注释或 heartbeat frame，且 projection cursor 不前进

#### Scenario: HTTP 客户端关闭连接
- **WHEN** SSE socket 被关闭
- **THEN** handler 释放连接资源，但不取消、失败或改变 Run

### Requirement: 慢客户端不得反压 Runtime
SSE delivery SHALL 从持久 repository 分页读取，并使用每连接有界状态；Runtime event
commit MUST NOT 等待任何特定客户端消费。服务 MUST 对连接数、page size、heartbeat 和
写超时提供配置边界。

#### Scenario: 一个客户端停止读取
- **WHEN** 某 SSE 客户端持续落后而另一个客户端正常消费
- **THEN** Runtime 和正常客户端继续工作，慢连接最终安全关闭并可用 cursor 重连

### Requirement: 重复 event 与 identity 冲突必须可辨别
Repository SHALL 以 `(run_id, stable_event_identity)` 和 journal sequence 约束事件。
内容相同的重试 append MUST 幂等返回原记录；identity 相同但 fingerprint 不同 MUST
产生 integrity conflict，并阻止冲突内容进入投影。

#### Scenario: event sink 重试同一事件
- **WHEN** append 使用相同 identity 和相同 canonical payload 重试
- **THEN** repository 返回原 sequence，不增加第二条 journal event

#### Scenario: 相同 identity 内容不同
- **WHEN** append 使用已存在 identity 但 payload fingerprint 不同
- **THEN** repository 报告 integrity conflict，两个版本都不被混合消费

### Requirement: 每个 Run 必须具有唯一终止 journal event
无论 success、failure、step limit、cancel、device failure 或 service interruption，
Run SHALL 最多提交一个 `run.terminal` event。该 event MUST 引用已持久 RunResult、
最终 high-water mark 和 Replay availability；SSE 在发送所有已提交 events 和 terminal
event 后 SHALL 正常结束。

#### Scenario: 正常终止 live stream
- **WHEN** RunResult、Replay 和 terminal event 已提交
- **THEN** SSE 客户端收到唯一 terminal event 后可停止重连并通过 Run query 读取结果

#### Scenario: completion 与 cancel 竞争
- **WHEN** Runtime completion 和取消收口几乎同时发生
- **THEN** journal 只包含一个与最终 RunResult 一致的 terminal event
