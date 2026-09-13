# Studio Benchmark Event Stream（Stage 5.2C-1）

本文记录已经实现并验证的 Stage 5.2C-1 Benchmark Experiment 事件查询与 SSE
传输边界。它建立在
[Stage 5.2A durable resource](studio-benchmark-experiment-resource.md)和
[Stage 5.2B execution worker](studio-benchmark-execution-worker.md)之上。

本文不代表 Stage 5.2C-2 publication/Replay、5.2C-3 startup recovery 或 React
Monitor 已经完成。

## 目的与完成形态

5.2B 已经把 service、worker、Benchmark Core 和 terminal facts 写入
Experiment-scoped SQLite journal，但浏览器只能查询 Experiment/TaskRun snapshot。
5.2C-1 的目标是让客户端可靠地读取这个 journal，而不是再建立一个内存事件事实源。

变更前：

```text
Benchmark worker
      ↓ synchronous append
SQLite durable journal
      └── private repository test helper
```

变更后：

```text
producer transaction
      ↓ COMMIT
SQLite durable journal ───────→ bounded GET page
      │
      └── payload-free notify → query-first / wait / re-query
                                      ↓
                             bounded named SSE
                                      ↓
                      Last-Event-ID reconnect / heartbeat
```

SQLite journal 始终是唯一事实源。process-local notifier 只降低等待延迟，不保存
payload；通知丢失时，下一次 heartbeat re-query 仍会发现已提交事件。

## 已实现公共合同

### Event page

```http
GET /studio/benchmark-experiments/{experimentId}/events?after=0&limit=100
```

响应是严格的 `StudioBenchmarkEventPageV1`：

```json
{
  "schemaVersion": 1,
  "experimentId": "experiment-...",
  "items": [],
  "nextCursor": 0,
  "highWaterMark": 0,
  "terminal": false
}
```

- `after` 是非负、exclusive、Experiment-local 的 sequence 位置 cursor；
- cursor 不是 event identity，不支持跨 Experiment 比较；
- HTTP 默认 page size 为 100，repository 合同限制在 1..500；
- `items` 必须按 sequence 连续升序；
- `nextCursor` 只在实际返回事件后推进；
- query 同时验证 envelope、event id、fingerprint、sequence、row count、最大
  sequence 和 aggregate high-water；
- malformed/negative/future cursor 返回 400；
- scoped Experiment 不存在返回 404；
- sequence gap、高水位、fingerprint 或 terminal event 冲突返回 409；
- `terminal=true` 仅表示 Experiment 已终态、最终 high-water 是唯一
  `experiment.terminal`，并且当前客户端已经 drain 到该位置。

空 terminal page 是合法的：客户端已经在最终 cursor 时，`items=[]` 且
`terminal=true`。

### SSE

```http
GET /studio/benchmark-experiments/{experimentId}/events/stream
Last-Event-ID: 12
```

也可以使用 `?after=12`。两者同时存在时数值必须一致，否则在发送 200 前返回 400。
future cursor 同样在建立 stream 前拒绝。

每条 durable event 使用固定 frame：

```text
id: 13
event: journal
data: {"schemaVersion":1,...}
```

固定 `journal` event name 允许旧客户端收到尚不认识的 future `kind`，仍能安全推进
cursor。domain kind、source、phase 和 payload 保留在版本化 envelope 中。

空闲时发送：

```text
event: heartbeat
data: {"schemaVersion":1}
```

heartbeat 不带 `id`，因此不推进 journal cursor。SSE 始终先 backfill，再 wait，
再重新查询 SQLite。只有 terminal event 已经交付给该客户端后，连接才关闭。
浏览器刷新、断网或主动关闭只释放 transport，不调用 Experiment cancel。

## durability、并发与资源边界

### Commit-after-notify

`SQLiteStudioBenchmarkExperimentRepository` 接受可选的 payload-free
`event_commit_hook`。create、claim、phase transition、runtime append、cancel、
TaskResult、TaskRun finish 和 Experiment finalization 只有在包含新 event 的事务
COMMIT 后才通知。

- rollback 不通知；
- event identity 幂等重试没有新增 sequence 时不通知；
- 一个事务追加多个 event 只通知一次；
- notifier 异常不会把已经提交的事实伪装成失败或回滚；
- 安全日志只记录 Experiment identity，不记录 callback exception/payload。

### Waiter 与连接

- Run 与 Benchmark 共享 identity-neutral bounded condition primitive，但保留各自
  DTO、repository、error domain 和 service；
- Benchmark waiter registry 默认最多保留 1000 个正在等待的 Experiment key；
- HTTP server 默认最多允许 32 个并发 Benchmark SSE；
- 容量耗尽在发送 `200 text/event-stream` 前返回 503；
- SSE batch 固定为 100，单连接只保留 cursor 和当前 bounded page；
- 默认 heartbeat 为 15 秒，配置上限 60 秒；
- 默认 socket write timeout 为 20 秒，配置上限 120 秒；
- 慢客户端写超时、断开、terminal 和 server shutdown 都会释放连接 lease；
- 慢客户端不会阻塞 worker append、普通 event query 或其他快速客户端。

server shutdown 会关闭 Benchmark waiter registry、唤醒正在等待的 handler，并释放
process-local 状态；SQLite Experiment/event facts 不会被删除。

## capability 与 links

完整 event-enabled composition 返回：

```json
{
  "executes": true,
  "cancelAccepted": true,
  "cancelActive": true,
  "eventStream": true,
  "replay": false,
  "reports": false
}
```

并增加：

```json
{
  "events": "/studio/benchmark-experiments/{id}/events",
  "eventStream": "/studio/benchmark-experiments/{id}/events/stream"
}
```

Definition-only 或测试中的 partial composition 继续返回 `eventStream=false`，并省略
两个链接。Stage 5.2C-1 不开放 Replay/report capability 或 link。

## 安全边界

Event page 和 SSE 只序列化已经由 `StudioBenchmarkEventEnvelopeV1` 校验并写入 SQLite
的 facts。payload 仍受 depth/member/text、总文本 48 KiB 和 encoded 64 KiB 上限。
API key、token、password、secret、raw serial、`device_handle`、host path 和 live
objects 会被 redacted/excluded；unknown future kind 不会绕过 envelope 校验。

错误响应使用稳定、有限的 safe message，不回显请求 cursor、SQLite path、payload
或内部 exception。5.2C-1 还补齐了共享 sanitizer 对 `device_handle` key 的识别。

## 自动化复验

新增事件流专项：

```bash
uv run --extra dev pytest \
  tests/studio/test_benchmark_event_stream.py -q
```

预期：`12 passed`。覆盖：

- DTO camelCase、分页、restart、future cursor；
- sequence/high-water/fingerprint/terminal corruption；
- commit-after-notify、rollback、丢通知和 notifier failure；
- GET page、404/400/409；
- SSE backfill、`Last-Event-ID`、heartbeat、terminal drain；
- 两个并发 consumer、连接 cap、真实 socket 写超时和 server shutdown；
- fake-device Benchmark Core 的 service/runtime/terminal facts；
- unknown kind 与 secret/device canary。

完整 Benchmark resource/worker/event transport：

```bash
uv run --extra dev pytest \
  tests/studio/test_benchmark_event_stream.py \
  tests/studio/test_benchmark_experiment_resource.py \
  tests/studio/test_benchmark_execution_worker.py -q
```

预期：`58 passed`。

普通 Run event 回归：

```bash
uv run --extra dev pytest \
  tests/studio/test_run_models_repository.py \
  tests/studio/test_run_replay_http.py \
  tests/studio/test_run_event_performance.py -q
```

预期：`30 passed`。

完整 Studio 与后端：

```bash
uv run --extra dev pytest tests/studio -q
uv run env PYTHONPATH=tests pytest -q
```

预期分别为 `159 passed` 和 `543 passed`。

clean-wheel：

```bash
uv run --extra dev pytest tests/packaging/test_isolated_install.py -q
```

预期：`1 passed`。测试从当前源码构建 wheel，在仓库外隔离环境安装，并验证
`StudioBenchmarkEventPageV1`、`BenchmarkEventNotifier`、
`DurableBenchmarkEventService` 和 SQLite repository 可从安装包组合。

语法与 OpenSpec：

```bash
uv run --extra dev python -m compileall -q zhixing tests
/Users/maczhen/.npm/_npx/abab5bd700860149/node_modules/.bin/openspec \
  validate implement-studio-benchmark-event-stream-5-2c1 --strict
```

## 验证中观察到的限制

项目说明中的 `unimobile` Conda 环境当前没有 `pytest`，因此本次自动化使用锁文件
支持的 `uv run --extra dev`。首次裸 `uv run pytest -q` 还会因为没有
`PYTHONPATH=tests` 而无法导入 `tests/graph` helper；正式完整后端入口是上文命令。

完整后端第一次运行出现一个普通 Run terminal cancel 的 high-water 时序失败：
第一次 GET 观察到 high-water 4，随后的 idempotent cancel 观察到 5。该用例单独连续
运行 5 次均通过，完整后端复跑为 543/543；没有证据表明它由 Benchmark event transport
引入，也没有把它描述为已定位或已修复。

## 该 Change 交接时未实现

- 5.2C-2 managed report/trajectory/bundle、artifact resolver 和 native Replay
  在本 Change 交接时尚未实现，现已由后续 Change 完成；
- 5.2C-3 accepted/starting requeue、uncertain in-flight interrupt 和 finalizing
  recovery 在本 Change 交接时尚未实现，现已由后续 Change 完成；
- React Benchmark Monitor 和前端 SSE consumer；
- 多 Agent、多 Task、多 repeat 与统计汇总；
- PostgreSQL adapter、quota、retention、delete 或自动 cleanup；
- SSE 跨进程 push/broker；多进程客户端依靠 durable heartbeat polling 发现其他进程
  commit；
- 真实 Android 验收。fake-device 与 HTTP 测试不能证明任意设备、Agent 或 Benchmark。

5.2C-2 publication/Replay 与 5.2C-3 startup recovery 现已完成；下一步是 Stage 5.3
React Monitor。
