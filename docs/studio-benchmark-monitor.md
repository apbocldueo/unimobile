# Studio Benchmark Experiment Monitor

本文记录 Stage 5.3 `implement-studio-benchmark-monitor-5-3` 已实现并验证的
Benchmark Experiment Monitor 边界。它是永久状态说明，不替代 OpenSpec 中的
requirement、设计和任务记录。

截至 2026-07-28，React Studio 已能够从 Composer 显式创建 durable Experiment，
并在 `/experiments/:experimentId` 中通过 Stage 5.2 的 HTTP resource、event page、
named SSE 和 native Replay 事实重建 Monitor。这里的“实时”指持续接收已提交的
durable journal，不表示浏览器直接观察设备，也不表示具备视频流、UI XML 或 Agent
节点 activation 证据。

## 目的与完成形态

Stage 5.3 解决的是“Experiment 已经在后端执行，但研究者无法在 Studio 中可靠地
观察、刷新恢复和进入证据审阅”的产品缺口。

完成后的用户路径是：

```text
Catalog / detail
      ↓
Composer validate + deterministic preview
      ↓ explicit create with stable intent identity
durable Experiment
      ↓
/experiments/:experimentId
      ├─ HTTP: Experiment / ordered TaskRuns
      ├─ event page: fixed high-water backfill
      ├─ named SSE: journal / heartbeat
      ├─ accepted-only explicit Cancel
      └─ terminal TaskRun → explicit durable Replay
```

刷新页面时，Monitor 不依赖内存中的 Composer、SSE buffer 或页面选择状态重建
Experiment 事实。它重新读取后端 resource 和 event cursor；这使深链接、刷新和
断线恢复拥有同一语义。

## 复用的后端事实

本 Change 没有新增或修改 Benchmark 后端能力。它消费以下已验证 Stage 5.2 合同：

- 5.2A：immutable Experiment snapshot、stable planned TaskRun、幂等 create/cancel；
- 5.2B：单 Worker/fake-device execution、durable runtime journal、bounded result；
- 5.2C-1：bounded event page、continuous cursor、named SSE、heartbeat；
- 5.2C-2：managed report/trajectory/bundle、native TaskRun Replay；
- 5.2C-3：accepted/starting requeue、uncertain in-flight interruption、
  finalizing publication-only recovery。

浏览器不能用 event 文本推导 lifecycle、outcome、evaluation、publication 或
recovery。上述字段始终以重新查询得到的 Experiment/TaskRun resource 为准。

## 前端边界

实现遵守 `docs/studio-frontend-architecture.md` 的 FSD-lite 方向：

```text
app/routes
    ↓
pages/experiment-monitor
    ↓
widgets/benchmark-experiment-workbench
    ↓
features/benchmark-experiment-monitor
    ↓
entities/benchmark-experiment
    ↓
shared/api + shared/lib
```

主要职责如下：

- `entities/benchmark-experiment`
  - versioned Experiment、TaskRun、event page/envelope、availability、diagnostic 和
    safe-link DTO；
  - 严格 parser，拒绝未知 schema version、非法 identity/cursor/cardinality、
    跨 Experiment TaskRun、冲突字段和不安全 link；
  - TanStack Query key、query/mutation 和 HTTP API。
- `features/experiment-composer`
  - 保留当前成功 preview 的 exact request 与 fingerprint；
  - 语义编辑立即使 preview/create 资格失效；
  - 一次用户 create 意图只生成一个 client request identity，未知结果重试复用同一
    identity 和内容。
- `features/benchmark-experiment-monitor`
  - event acceptance、连接状态机、resource refresh coalescing；
  - TaskRun 选择、follow/lock、rail collapse、Cancel 确认；
  - resource-driven view model，不从 journal payload 发明领域事实。
- `widgets/benchmark-experiment-workbench`
  - TaskRun rail 位于复用的 `ThreePaneWorkbenchLayout` 外；
  - Graph、Virtual Phone、Inspector 接收 typed view model。
- `pages/experiment-monitor`
  - 稳定解析 Experiment deep link；
  - 独立处理 loading、not found、resource error、TaskRun partial error、
    reconnecting、integrity frozen 和 retry。

没有向旧的无 owner 全局目录新增 Benchmark 状态。

## Event session

event session 使用连续 sequence 和 canonical fingerprint 验证 durable prefix：

```text
start
  ↓
HTTP backfill to captured high-water
  ↓
SSE ?after=<verified cursor>
  ├─ heartbeat ───────────────→ freshness only
  ├─ exact duplicate ─────────→ ignore, no resource refetch
  ├─ next sequence ───────────→ accept + coalesced resource refresh
  ├─ gap ─────────────────────→ close SSE → HTTP repair → reconnect
  ├─ disconnect ──────────────→ bounded reconnect → HTTP backfill
  ├─ terminal event ──────────→ HTTP terminal drain → terminal
  └─ identity/content conflict → frozen integrity state
```

关键约束：

- fixed high-water 先把启动时历史前缀读完，再连接 SSE；
- SSE 总是显式携带 exclusive `after` cursor；
- heartbeat 与 exact duplicate 不触发 resource refetch；
- gap、断线和 reconnect 都从最后验证 cursor 开始；
- terminal 只有在 HTTP page 确认 drain 完成后成立；
- 同 sequence 不同 fingerprint、同 identity 不同内容等不可恢复冲突会冻结最后验证
  prefix，必须由用户显式 retry；
- unmount、navigation、SSE disconnect 只清理连接，绝不发送 Cancel。

event audit summary 是有界的，并且不持久化或展示任意 payload 内容。

## Monitor 产品行为

### Experiment header

Header 只展示 authoritative Experiment lifecycle、TaskRun 完成数、connection 和
cursor。Cancel 仅在 accepted resource 明确允许时显示；点击后必须二次确认，并使用
single-flight mutation。terminal race 会刷新 resource，而不是在浏览器中覆盖状态。

### TaskRun rail

TaskRun 按后端 planned order 稳定排列。默认选择当前可执行 TaskRun；用户选择历史
TaskRun 后进入 lock，不会因 SSE/resource 更新被强制跳走，并可显式“回到当前
TaskRun”。TaskRun 查询错误局部显示，不会抹去 Experiment header 或 event 状态。

### Graph、Phone 与 Inspector

- Graph 来自 immutable Agent snapshot，保持静态，不把 Benchmark phase 映射为
  Agent node activation；
- 缺少已提交截图、UI XML 或 live activation 时，明确显示 `not_captured`；
- Virtual Phone 不使用占位截图、上一帧或模拟 UI 冒充当前设备证据；
- Inspector 展示 lifecycle、timing、phase、Agent status、Benchmark outcome、
  publication availability、safe diagnostic、connection/cursor 和有界 event summary。

### Replay

Replay 按钮只在 terminal TaskRun 同时满足以下条件时出现：

- `replayAvailability === "available"`；
- 存在合法 `replayId`；
- resource 提供安全 replay link。

点击按钮才导航到 `/runs/:replayId/replay`。Monitor 不会自动跳转，也不会从 live
event buffer 拼装 Replay。

## 无设备浏览器 smoke fixture

`studio/scripts/benchmark-monitor-smoke-fixture.mjs` 是只监听
`127.0.0.1:8765` 的确定性验收服务。它不导入 runtime、plugin 或 device code，
也不执行 Agent。运行：

```bash
cd studio
npm run smoke:benchmark-monitor
npm run dev -- --host 127.0.0.1
```

然后访问服务启动时打印的固定 URL。固定 identity 覆盖：

- `experiment-111…111`：active/live；
- `experiment-222…222`：terminal、Replay `not_produced`；
- `experiment-333…333`：terminal、显式 Replay 可用；
- `experiment-444…444`：not found；
- `experiment-555…555`：accepted-only Cancel 确认；
- `experiment-666…666`：首次 SSE 断线、`reconnecting → live`；
- `experiment-777…777`：延迟 resource 的 loading；
- `experiment-888…888`：sequence gap 导致 integrity frozen。

Composer 的 validate → preview → create、未知结果幂等重试和成功 Monitor 跳转由
`benchmarkRoutes.test.tsx` 的同一 no-device fixture 验证；Monitor 的 backfill、
SSE、disconnect/recovery、terminal/Replay 和 integrity variant 由
`benchmarkEventSession.test.ts`、`ExperimentMonitorPage.test.tsx` 和上述真实浏览器
fixture 共同验证。

## 验证证据

2026-07-28 的本 Change 验证结果：

```bash
cd studio
npm test
# 30 files, 107 tests passed

npm run typecheck
npm run lint
npm run build
# 均成功；Vite 仅报告既有 >500 kB chunk 提示

node --check scripts/benchmark-monitor-smoke-fixture.mjs
# 成功
```

后端消费合同回归：

```bash
uv run pytest -q \
  tests/studio/test_benchmark_experiment_resource.py \
  tests/studio/test_benchmark_execution_worker.py \
  tests/studio/test_benchmark_event_stream.py \
  tests/studio/test_benchmark_publication_replay.py \
  tests/studio/test_benchmark_startup_recovery.py
# 108 passed
```

真实浏览器通过固定 no-device fixture 检查了 loading、active、SSE reconnect、
Cancel 确认与取消终态、terminal、Replay available/unavailable、not found 和
integrity frozen。1280×720 视口下 document 与主工作区没有横向 overflow。

## 限制与 5.4 交接

Stage 5.3 不证明或不实现：

- 真实 Android Benchmark 执行；
- 多 Task、repeats 或多 Agent 调度扩展；
- live screenshot、UI XML、视频或 Agent node activation；
- thread/checkpoint resume；
- 报告统计、Evaluation Tree、paired comparison、history 和 export UI；
- PostgreSQL、对象存储、quota、retention 或 delete；
- 自动失败诊断。

下一 Change 固定为
Stage 5.4 reporting，并已永久拆为 5.4A reporting resource、5.4B report 与
Evaluation Tree、5.4C comparison/metrics、5.4D history/evidence/export。第一步
是 `implement-studio-benchmark-reporting-resource-5-4a`。它们应基于已持久化
report、trajectory、artifact 和 bundle 构建 `/experiments/:experimentId/report`
与实验历史，并保持 Agent status 与 Benchmark outcome 分轨、样本/公平性警告以及
不夸大统计结论。完整顺序见
[Studio Stage 5.4 Benchmark Reporting 路线](studio-benchmark-reporting-roadmap.md)。
它们不应重新实现 Monitor event session 或从前端重算正式指标。
