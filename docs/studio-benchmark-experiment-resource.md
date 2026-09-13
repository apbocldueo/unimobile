# Studio Benchmark Experiment Resource（Stage 5.2A）

本文记录 2026-07-27 已实现并验证的 Stage 5.2A 持久资源边界。它是
[Stage 5 路线图](studio-benchmark-experiment-roadmap.md)和
[Benchmark Experiment 规范合同](studio-benchmark-experiment-contracts.md)的实现说明，
不是对 5.2C-1/2/3 durability 或真实 Android 执行能力的声明。文中“5.2B 尚未实现”的
表述是 5.2A 完成时的历史边界；5.2B 后续实现事实见
[Studio Benchmark Execution Worker](studio-benchmark-execution-worker.md)。

## 目的和完成形态

Stage 5.1 可以发现 Benchmark、选择不可变 Agent revision、配置 Protocol 并预览
schedule，但预览结果只存在于一次请求响应中。5.2A 要解决的是：在任何设备或模型
执行前，将经过后端重新验证的实验定义变成一个稳定、可重启查询、可幂等重试的
Experiment 资源。

变更前：

```text
完整 definition → validate / compile / schedule preview
                              └── 响应结束后没有 Experiment 资源
```

变更后：

```text
完整 create request
    │
    ├── durable clientRequestId 已存在
    │       ├── 同内容 → 立即返回原 Experiment
    │       └── 不同内容 → idempotency conflict
    │
    └── 不存在
            ↓
       prepare definition 一次
            ↓
       重算 preview fingerprint
            ↓
       构造有界 immutable snapshot + planned TaskRuns
            ↓
       SQLite 单事务提交 Experiment + TaskRuns + accepted event
```

提交后的资源状态是 `accepted`，不是 `running`。Stage 5.2A 不启动 worker，不解析
真实 device profile，不连接 ADB，不物化 TaskInstance，不调用插件、模型、
initializer、evaluator 或 scheduler。

## 已实现合同

### 资源和 DTO

- `StudioBenchmarkExperimentCreateRequestV1` 必须提交 `schemaVersion`、
  `clientRequestId`、`previewFingerprint` 和完整 Stage 5.1 preview definition；
- `ExperimentDefinitionSnapshotV1` 内联保存完整已验证 AgentGraph snapshot、
  BenchmarkPlan、ExperimentProtocol、安全来源事实、profile metadata、schedule、
  fingerprints 和当时的执行限制；
- canonical snapshot JSON 在写事务前按 UTF-8 测量，最大为 `2,097,152` bytes；
- Experiment、TaskRun、cancellation、availability 和 journal envelope 均为严格、
  versioned、camelCase 公共 DTO；
- 公共资源只发布已经实现的 self、cancel 和 TaskRun links，并明确返回
  `executes=false`、`eventStream=false`、`replay=false`、`reports=false`。

Snapshot 和响应不得包含 Package asset bytes、宿主绝对路径、SQLite 文件名、原始
device serial、secret、live handle、插件/模型实例或数据库 locator。

### HTTP

已实现以下 route；`/api` 前缀与无前缀形式均由现有 Studio HTTP boundary 支持：

```text
POST /studio/benchmark-experiments
GET  /studio/benchmark-experiments/{experimentId}
POST /studio/benchmark-experiments/{experimentId}/cancel
GET  /studio/benchmark-experiments/{experimentId}/task-runs
GET  /studio/benchmark-experiments/{experimentId}/task-runs/{taskRunId}
```

首次 create 和同内容重试都返回 `202` versioned wrapper，并用 `created` 区分是否为
首次提交。TaskRun list 按 `(order, taskRunId)` 稳定排序，使用 1–100 的有界 limit
和 versioned、checksummed、Experiment-scoped opaque cursor。跨 Experiment 查询
TaskRun 返回安全 not-found。

没有实现或发布 event query/SSE、report、bundle、Replay、pause、retry、delete 或
runtime-control route。

### SQLite 和 repository

共享 Studio SQLite migration boundary 现在单调管理 schema 1–4：

- schema 1：Agent document/revision；
- schema 2：Replay；
- schema 3：StudioRun/event/artifact；
- schema 4：Benchmark Experiment、TaskRun 和 Experiment event。

已有 `SQLiteAgentDocumentRepository`、`SQLiteStudioRunRepository` 和 Replay
storage 保持原 public imports/constructors，并委托给同一连接与 migration policy。
Experiment application service 依赖 database-neutral typed repository port；SQLite
只是第一版 adapter，未来 PostgreSQL adapter 不应改变 HTTP DTO、identity 或领域
状态语义。

首次 create 在一个 `BEGIN IMMEDIATE` transaction 中提交 Experiment、canonical
request、全部 planned TaskRuns、sequence-1 accepted event 和 high-water mark。
唯一 client request identity 解决并发首次创建；竞争失败者读取并比较已提交事实，
不会重新生成另一个 schedule。

### accepted-only cancel

5.2A 没有 worker，因此 cancel 只处理 `accepted`：

```text
accepted Experiment
    ├── cancellation event
    ├── scheduled TaskRun → terminal / cancelled_before_start
    ├── TaskRun outcomeAvailability = not_produced
    ├── TaskRun terminal event
    └── Experiment → terminal / cancelled + unique terminal event
```

上述变化在一个事务中完成。任何注入失败都会整体回滚；重复取消已终态 Experiment
返回当前事实，不追加 event，也不推进 high-water mark。

## 已验证证据

2026-07-27 在 `unimobile` 环境完成：

```bash
uv run pytest -q tests/studio/test_benchmark_experiment_resource.py
# 21 passed

uv run pytest -q tests/studio
# 122 passed

uv run python -m compileall -q zhixing/studio \
  tests/studio/test_benchmark_experiment_resource.py

uv run pytest -q tests/benchmark/test_architecture_compatibility.py \
  tests/packaging/test_public_import.py \
  tests/packaging/test_benchmark_package_boundary.py
# 7 passed

uv run env PYTHONPATH=tests pytest -q
# 502 passed in 63.64s

uv run pytest -q tests/packaging/test_isolated_install.py
# 1 passed；构建 wheel、在仓库外的干净 venv 安装并执行新旧 Studio 冒烟

/Users/maczhen/.npm/_npx/abab5bd700860149/node_modules/.bin/openspec \
  validate implement-studio-benchmark-experiment-resource-5-2a --strict
# Change ... is valid
```

不设置 `PYTHONPATH=tests` 的裸 `uv run pytest -q` 会在三个既有 runtime 测试的
`from graph.helpers` 收集处失败；这是仓库测试模块路径前提，不是 5.2A 测试失败。
本轮未安装 `ruff`，因此没有把 ruff 结果列为通过证据。

自动化覆盖：

- empty/1/2/3 → schema 4、重复打开、并发 migration 和 future schema 拒绝；
- create/cancel 每个事务边界的故障注入与无部分写入；
- 并发相同 create、不同内容冲突、并发 cancel、连续 sequence 和单 terminal event；
- preview → HTTP create → query → 服务重启 → 原 snapshot/TaskRun 查询；
- 丢响应重试、提交后 Package 漂移、首次 drift conflict 和 exactly-one accepted event；
- accepted cancel、`cancelled_before_start`、`not_produced` 与重复取消 no-op；
- opaque cursor、跨 Experiment scope、snapshot size、安全错误和 Host boundary；
- 干净 wheel 中新 Experiment public imports/schema 与旧 StudioRun/Replay 路径。

本轮没有真实 Android trajectory，也没有执行 Benchmark task；因此这些测试只证明
定义、持久化、并发、查询和安全合同。

## 手动复验

先准备一个 Stage 5.1 可 preview 的 Benchmark Package、已保存 Agent revision 和
安全 profile ID，然后用独立数据库启动：

```bash
uv run python -m zhixing.studio serve \
  --host 127.0.0.1 \
  --port 8765 \
  --database /tmp/zhixing-stage5a.sqlite3 \
  --benchmark-package /absolute/path/to/package \
  --no-installed-benchmarks
```

将完整 preview definition 保存为 `/tmp/preview-request.json`：

```bash
curl -sS -H 'Content-Type: application/json' \
  --data @/tmp/preview-request.json \
  http://127.0.0.1:8765/studio/benchmark-experiments/preview \
  > /tmp/preview-response.json
```

用响应中的 `previewFingerprint` 和原完整 definition 形成：

```json
{
  "schemaVersion": 1,
  "clientRequestId": "manual-experiment-request-1",
  "previewFingerprint": "<preview response fingerprint>",
  "definition": "<the complete preview request object>"
}
```

保存为 `/tmp/create-request.json` 后执行：

```bash
curl -sS -H 'Content-Type: application/json' \
  --data @/tmp/create-request.json \
  http://127.0.0.1:8765/studio/benchmark-experiments
```

预期 `202`、`created=true`、`lifecycle=accepted`、`executes=false`。原样再发一次应
返回同一 `experimentId` 和 `created=false`。用返回的 identity 查询：

```bash
curl -sS http://127.0.0.1:8765/studio/benchmark-experiments/<experimentId>
curl -sS \
  'http://127.0.0.1:8765/studio/benchmark-experiments/<experimentId>/task-runs?limit=1'
```

停止服务后用同一 `--database` 重启，响应中的 definition、TaskRun identity/order 和
high-water mark 应保持一致。accepted cancel：

```bash
curl -sS -H 'Content-Type: application/json' \
  --data '{"schemaVersion":1,"clientRequestId":"manual-cancel-1"}' \
  http://127.0.0.1:8765/studio/benchmark-experiments/<experimentId>/cancel
```

预期 Experiment 为 `terminal/cancelled`，planned TaskRun 为
`terminal/cancelled_before_start` 且 `outcomeAvailability=not_produced`。重复 cancel
不改变 event high-water mark。服务日志和响应中不应出现设备连接、scheduler 启动、
model/plugin 调用、宿主 Package 路径或 raw serial。

Definition drift 可通过 preview 后修改 Package 或 Agent revision，再用一个新的
`clientRequestId` 提交旧 fingerprint 复验：预期 `409
benchmark.experiment.definition_conflict` 且无新资源；已成功请求的同内容重试仍应
返回原 Experiment。

## 剩余限制与 5.2B 交接

Stage 5.2A 仍有以下明确限制：

- Experiment 只会处于 `accepted` 或因 accepted cancel 进入 terminal，不会执行；
- 没有 worker ownership、queue polling、startup re-enqueue 或 execution preflight；
- 没有在 execution boundary 解析 device profile；
- 没有 TaskInstance materialization、Benchmark phase orchestration、runtime event
  append、evaluation/result publication 或 cooperative in-flight cancellation；
- event journal 已持久保存初始/取消事实，但没有公共 event page、SSE 或 recovery；
- 没有 report/artifact/trajectory/bundle publication 和 native Replay promotion；
- 第一版永久保存，不提供 quota、retention、delete 或自动清理；
- PostgreSQL 只有 adapter seam，没有实现 adapter；
- React Composer 继续是 preview-only，没有创建按钮或 Experiment Monitor。

该交接后来由 Stage 5.2B 按上述边界完成：它消费这里的 durable accepted aggregate，
没有重建另一套 Experiment DTO、状态机或 repository。后续依次是 5.2C-1 公共
event query/SSE、5.2C-2 managed artifact/report/trajectory/bundle 与 native Replay、
5.2C-3 startup recovery；三者不得重新合并为一个超大 Change。
