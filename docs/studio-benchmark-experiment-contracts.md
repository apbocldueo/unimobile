# Studio Benchmark Experiment 合同

状态：**Stage 5.0 合同已接受；Stage 5.1–5.4 与 5.5A 已实现**

适用 Change：`define-studio-benchmark-experiment-contracts-5-0`
最后核对：2026-07-28

本文把 Stage 5.0 OpenSpec requirements 落为后续 5.1–5.6 共用的资源、DTO、状态机、
安全和验收合同。OpenSpec specs 是规范性事实源；本文提供长期入口、字段解释和
可解析示例。

文中“当前已有”只指本轮审计过的后端能力；“SHALL/MUST/目标”均为后续实现要求，
不能据此宣称 Studio Benchmark 产品已经完成。

## 1. 目的与边界

Studio Benchmark 的目标是把现有 Build–Run–Evaluate 后端产品化为持久、可恢复、
可监控、可评估和可比较的研究实验工作台：

```text
Agent revision(s)        Benchmark Package        ExperimentProtocol
        │                        │                         │
        └────────────────────────┴─────────────────────────┘
                                 │
                    ExperimentDefinitionSnapshotV1
                                 │
                         BenchmarkExperiment
                                 │
             ┌───────────────────┴───────────────────┐
             │                                       │
          TaskRun(s)                         Experiment report
             │                                       │
       native Replay(s)                 trajectory / bundle
```

普通 `StudioRun` 与 Benchmark Experiment 是两个资源：

- 普通 Run：一个 Agent revision 执行一条普通 task；
- Benchmark Experiment：一个或多个 Agent revision 在同一 Plan/Protocol 下执行
  planned TaskRuns，并产生外部 evaluation 和跨运行报告。

Experiment 可以复用 Stage 2–4 的 repository、journal、artifact、Replay 和三栏投影
模式，但不能成为 `StudioRun` 的几个可选字段。Benchmark Runtime 与 Graph Runtime
的执行语义仍由后端负责，Studio 不实现第二套 evaluator 或统计计算。

本合同不实现应用代码，不包含 Benchmark authoring、多设备分布式调度、
pause/checkpoint、节点重试、实时视频、网页设备控制、自动诊断或 PostgreSQL adapter。

## 2. 当前后端复审与复用点

| 现有边界 | 已核对事实 | Stage 5 复用方式 | 不得误述 |
| --- | --- | --- | --- |
| `zhixing.benchmark.BenchmarkCatalog` | 显式目录与 installed distribution；metadata-only candidate；歧义检测 | 5.1 HTTP adapter | Stage 5.1 API 已实现；不是 Experiment runtime |
| `compile_benchmark_package/suite` | JSON/Package → `BenchmarkPlan`；definition validation 无设备副作用 | detail/validate/preview 的 Plan 事实源 | validate 不证明任务运行成功 |
| `ExperimentProtocol` | seed、repeats、order、reuse、budget、device/App、isolation、failure policy | Composer 只编辑正式 schema | 前端不定义竞争性默认值 |
| `build_schedule/materialize_task` | 确定性 schedule；runtime 才产生具体 `TaskInstance` | preview 只展示 planned entry | preview 不运行 generator |
| `BenchmarkExperimentRuntime` | 多 Task、多 Agent、repeats、共享 device session 和完整 lifecycle | 5.2B worker 已包装同步 Runtime；5.2C-3 只恢复安全服务边界 | Studio Worker 当前只开放 1 Agent × 1 Task × 1 repeat；不支持 in-flight checkpoint resume |
| `BenchmarkLifecycleEvent` | 有序 Benchmark phase 事件 | 5.2B 写入 Experiment durable journal；5.2C-1 开放连续 query/SSE；5.2C-3 追加恢复决定 | 公共 transport 与恢复事件已实现；SSE 不是新的事实源 |
| `BenchmarkTaskResult/SuiteResult` | Agent status 与 PASS/FAIL/INVALID/SKIPPED 分离 | TaskRun/Experiment result source | service lifecycle 不等于 outcome |
| `EvaluationNodeResult` | AND/OR/SEQUENCE/THRESHOLD/WEIGHTED 与叶子证据 | Inspector/report 的 Evaluation Tree | 前端不得重建 evaluator |
| `BenchmarkExperimentReport` | micro/macro、Wilson、paired、fairness、`significance_claimed=false` | 5.4 report DTO 的事实源 | 小样本不等于统计显著 |
| reporting writer / verifier | report、JSONL trajectory、hash manifest、bundle | 5.2C-2 通过 server-owned staging 与 managed artifact 发布 | 已验证正式单切片发布；不是 5.4 reporting UI |
| Stage 3 Studio Run ports | SQLite repository、CAS、idempotent create/cancel | 5.2A/5.2B 已按相同模式建立独立 Experiment aggregate | 普通 Run 与 Benchmark Experiment 仍是不同资源 |
| Stage 3 durable journal/SSE | append-before-notify、cursor、heartbeat、terminal | 建立 Experiment-scoped journal | Run journal 与 Experiment journal 身份不同 |
| Stage 2/3 Replay | `ReplayEvidenceEnvelope`、opaque artifact、native Run publication | 5.2C-2 由 TaskRun publisher 原子注册显式 native Replay | 已验证 fake-device TaskRun；不是任意真机任务 |
| Stage 4 workbench | factual/visual/selected state 分离 | 5.3 monitor 复用共享只读能力 | Stage 5.1 已替换占位页；monitor 仍未实现 |

本轮回归命令：

```bash
env PYTHONPATH=tests UV_CACHE_DIR="$(mktemp -d)" \
  uv run --extra dev python -m pytest -q tests/benchmark
```

2026-07-26 的实际结果是 `90 passed in 2.54s`。它证明当前 Benchmark
contract/runtime/reporting fake 与单元回归通过，不是新的真实 Android 证据。

## 3. 版本、命名和 HTTP 公共约定

### 3.1 JSON 约定

- HTTP DTO 使用 `camelCase`；adapter 显式映射现有 Python `snake_case`；
- 每个顶层 DTO 有整数 `schemaVersion`，首版为 `1`；
- canonical identity 使用后端原值，例如 `sha256:<64 hex>`；
- resource identity 是 opaque string，客户端不得解析前缀以推断存储；
- 时间使用 UTC epoch milliseconds；
- resource response 通过 `links` 给出后续入口，客户端不得拼文件名或宿主路径；
- list 使用 opaque cursor；event journal 使用 Experiment-scoped 非负整数 cursor；
- 未知不兼容 major schema 必须报错，不能猜字段。

### 3.2 安全错误 envelope

所有 Stage 5 HTTP 错误使用同一种顶层结构：

```json
{
  "schemaVersion": 1,
  "requestId": "request-example-01",
  "error": {
    "code": "benchmark.definition_conflict",
    "message": "The selected definition changed after preview.",
    "retryable": false,
    "field": "previewFingerprint",
    "diagnostics": [
      {
        "code": "benchmark.plan_identity_changed",
        "severity": "error",
        "sourcePointer": "benchmark.catalogEntryId"
      }
    ]
  }
}
```

`message` 与 diagnostics 必须有界并经过清洗；不得包含 SQL、数据库位置、Catalog
root、Package 绝对路径、raw device serial、secret 或相邻资源 identity。

### 3.3 产品路由与目标 HTTP

| 产品路由 | 目标 HTTP resource |
| --- | --- |
| `/benchmarks` | `GET /studio/benchmarks` |
| `/benchmarks/:benchmarkId` | detail、tasks、validate |
| `/experiments/new` | preview、create |
| `/experiments/:experimentId` | Experiment、TaskRuns、events、SSE、cancel |
| `/experiments/:experimentId/report` | report、artifact、bundle |
| `/runs/:runId/replay` | 通过 TaskRun 返回的显式 Replay link 进入 |

目标 HTTP 路由：

```text
GET  /studio/benchmarks
GET  /studio/benchmarks/{benchmarkId}
GET  /studio/benchmarks/{benchmarkId}/tasks
POST /studio/benchmarks/{benchmarkId}/validate
POST /studio/benchmark-experiments/preview
POST /studio/benchmark-experiments
GET  /studio/benchmark-experiments/{experimentId}
POST /studio/benchmark-experiments/{experimentId}/cancel
GET  /studio/benchmark-experiments/{experimentId}/task-runs
GET  /studio/benchmark-experiments/{experimentId}/task-runs/{taskRunId}
GET  /studio/benchmark-experiments/{experimentId}/events
GET  /studio/benchmark-experiments/{experimentId}/events/stream
GET  /studio/benchmark-experiments/{experimentId}/report
GET  /studio/benchmark-experiments/{experimentId}/artifacts/{artifactId}
GET  /studio/benchmark-experiments/{experimentId}/bundle
```

其中 list/detail/tasks/validate、device profiles 和 preview 已由 Stage 5.1 实现；
create/get/cancel 与 TaskRun 由 5.2A/5.2B 实现，events/SSE 由 5.2C-1 实现，
report、artifact、bundle 与显式 native Replay 入口由 5.2C-2 实现；5.2C-3 在
composition 启动时完成内部 recovery，不增加公共 recovery route。React Monitor 与
5.4 reporting UI 仍未实现。

## 4. Catalog 与 Composer DTO

### 4.1 Catalog list

请求参数：

- `limit`：有界正整数；
- `cursor`：服务签发 opaque cursor；
- `query`、`platform`、`sourceKind`：可选 metadata filter。

响应示例：

```json
{
  "schemaVersion": 1,
  "items": [
    {
      "catalogEntryId": "benchmark-entry-android-world-v1",
      "packageIdentity": "zhixing/android-world@1.0.0",
      "title": "AndroidWorld",
      "version": "1.0.0",
      "sourceKind": "catalog",
      "splits": [
        {
          "name": "test",
          "taskCount": 81
        }
      ],
      "availability": "available",
      "warnings": []
    }
  ],
  "nextCursor": null
}
```

`catalogEntryId` 选择一个具体来源；`packageIdentity` 是可读语义 identity。相同
Package identity 来自多个不等价来源时，服务返回不同 entry 与 ambiguity diagnostic，
不按发现顺序覆盖。

### 4.2 Detail、task 与 validate

Detail 额外返回 Package content identity、platform/App/plugin requirements、
resource/ground-truth 摘要和默认 Protocol。Task page 使用稳定
`(taskId, split)` 排序并返回 opaque cursor；不返回 initializer/evaluator live instance。

Validate 响应示例：

```json
{
  "schemaVersion": 1,
  "catalogEntryId": "benchmark-entry-android-world-v1",
  "valid": true,
  "identities": {
    "package": "zhixing/android-world@1.0.0",
    "packageContent": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "benchmarkPlan": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "experimentProtocol": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  },
  "diagnostics": []
}
```

| 操作 | 读 manifest | 读 task | 校验 resource digest | 连接设备 | 执行插件/Agent/模型 |
| --- | --- | --- | --- | --- | --- |
| list | 是，最小元数据 | 是，split count semantic index | 否 | 否 | 否 |
| detail/task | 是 | 是 | 否 | 否 | 否 |
| validate | 是 | 是 | 是 | 否 | 否 |
| preview | 重新编译 selected split | 是 | 否；由显式 validate 负责 | 否 | 否 |

### 4.3 Preview request

DTO 从第一版开始使用复数 `agentRevisions`，即使 5.2B 第一条执行切片只允许一个：

```json
{
  "schemaVersion": 1,
  "agentRevisions": [
    {
      "agentId": "agent-research-baseline",
      "revisionId": "revision-0001"
    }
  ],
  "benchmark": {
    "catalogEntryId": "benchmark-entry-android-world-v1",
    "split": "test",
    "taskIds": [
      "AndroidWorld_6"
    ]
  },
  "protocol": {
    "schemaVersion": "1.0",
    "seed": 42,
    "repeats": 1,
    "taskOrder": {
      "strategy": "fixed"
    },
    "taskMaterialization": {
      "reuseAcrossAgents": true
    },
    "device": {
      "platform": "android",
      "locale": "en-US",
      "orientation": "portrait",
      "versionPolicy": "compatible"
    },
    "budget": {
      "maxInteractions": 15,
      "maxActivations": 200,
      "timeoutSeconds": 600
    },
    "isolation": {
      "reset": "before_each_agent",
      "cleanup": "after_each_run",
      "requireVerifiedReset": true
    }
  },
  "deviceProfileId": "profile-local-android"
}
```

后端重新加载 immutable valid revision，验证 graph canonical hash，并使用正式
ExperimentProtocol normalizer。未保存 draft、显示名称或客户端提交的 graph body
不能替代 revision。

### 4.4 Preview response

```json
{
  "schemaVersion": 1,
  "previewFingerprint": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "identities": {
    "benchmarkPlan": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "experimentProtocol": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  },
  "agentRevisions": [
    {
      "agentId": "agent-research-baseline",
      "revisionId": "revision-0001",
      "agentGraph": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    }
  ],
  "executionLimits": {
    "maxAgents": 1,
    "maxSelectedTasks": 1,
    "maxRepeats": 1,
    "multiAgentComparison": false
  },
  "schedule": [
    {
      "plannedEntryId": "planned-entry-0001",
      "agentId": "agent-research-baseline",
      "taskId": "AndroidWorld_6",
      "repeat": 0,
      "order": 0,
      "derivedSeed": 918273,
      "taskInstance": {
        "availability": "pending_materialization",
        "identity": null,
        "parameters": null
      }
    }
  ],
  "diagnostics": []
}
```

Preview 是纯规划：

- 相同规范化输入必须得到相同 fingerprint、identities、entry identity 和顺序；
- 动态任务只显示 derived seed 与 `pending_materialization`；
- 不运行 generator，不伪造 TaskInstance，不连接 profile 对应设备；
- `unsupported_cardinality` 拒绝整个超限请求，不能截断 Agent/task/repeat。

### 4.5 Preview → create 防漂移

Create 是 stateless revalidation，不依赖浏览器内存或临时 preview cache：

```json
{
  "schemaVersion": 1,
  "clientRequestId": "experiment-request-0001",
  "previewFingerprint": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "definition": {
    "agentRevisions": [
      {
        "agentId": "agent-research-baseline",
        "revisionId": "revision-0001"
      }
    ],
    "catalogEntryId": "benchmark-entry-android-world-v1",
    "split": "test",
    "taskIds": [
      "AndroidWorld_6"
    ],
    "protocolIdentity": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "deviceProfileId": "profile-local-android"
  }
}
```

服务重新解析 revision、Catalog entry、Plan、tasks、Protocol 和资源摘要。结果与
fingerprint 不同则返回 `benchmark.definition_conflict`，不创建 Experiment、不连接
设备。相同 `clientRequestId + canonical request fingerprint` 重试返回同一 Experiment；
同 request identity 不同内容返回 conflict。

## 5. Experiment 与 TaskRun

### 5.1 `ExperimentDefinitionSnapshotV1`

Snapshot 原子持久化：

```json
{
  "schemaVersion": 1,
  "snapshotFingerprint": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "agents": [
    {
      "agentId": "agent-research-baseline",
      "revisionId": "revision-0001",
      "agentGraphIdentity": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "snapshotRef": "agent-snapshot-0001"
    }
  ],
  "benchmark": {
    "catalogEntryId": "benchmark-entry-android-world-v1",
    "packageIdentity": "zhixing/android-world@1.0.0",
    "benchmarkPlanIdentity": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "planDefinitionRef": "definition-artifact-plan-0001",
    "resources": [
      {
        "logicalUri": "asset://camera-reference",
        "sha256": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
      }
    ]
  },
  "protocol": {
    "identity": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "bodyRef": "definition-artifact-protocol-0001"
  },
  "deviceProfileId": "profile-local-android",
  "plannedTaskRuns": [
    {
      "taskRunId": "benchmark-task-run-0001",
      "plannedEntryId": "planned-entry-0001",
      "agentId": "agent-research-baseline",
      "taskId": "AndroidWorld_6",
      "repeat": 0,
      "order": 0,
      "derivedSeed": 918273
    }
  ],
  "executionLimits": {
    "maxAgents": 1,
    "maxSelectedTasks": 1,
    "maxRepeats": 1
  }
}
```

Plan body/Protocol body 可作为受控 definition artifact 保存；SQLite 不保存大型 asset。
Worker 在任何设备副作用前从允许来源解析所需 resource 并验证 snapshot digest。来源
移动或 digest 改变时以 definition/resource preflight failure 收口，不能使用当前同名
Package 代替。

### 5.2 Experiment resource

```json
{
  "schemaVersion": 1,
  "experimentId": "benchmark-experiment-0001",
  "serviceLifecycle": "running",
  "terminalReason": null,
  "cancellationRequested": false,
  "snapshotFingerprint": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "counts": {
    "planned": 1,
    "terminal": 0,
    "pass": 0,
    "fail": 0,
    "invalid": 0,
    "skipped": 0,
    "outcomeNotProduced": 1
  },
  "availability": {
    "result": "pending",
    "report": "pending",
    "trajectory": "pending",
    "bundle": "pending"
  },
  "eventHighWaterMark": 8,
  "acceptedAt": 1785000000000,
  "startedAt": 1785000001200,
  "terminalAt": null,
  "links": {
    "self": "/studio/benchmark-experiments/benchmark-experiment-0001",
    "taskRuns": "/studio/benchmark-experiments/benchmark-experiment-0001/task-runs",
    "events": "/studio/benchmark-experiments/benchmark-experiment-0001/events",
    "eventStream": "/studio/benchmark-experiments/benchmark-experiment-0001/events/stream",
    "report": "/studio/benchmark-experiments/benchmark-experiment-0001/report",
    "bundle": "/studio/benchmark-experiments/benchmark-experiment-0001/bundle"
  }
}
```

### 5.3 TaskRun resource

```json
{
  "schemaVersion": 1,
  "experimentId": "benchmark-experiment-0001",
  "taskRunId": "benchmark-task-run-0001",
  "serviceLifecycle": "evaluating",
  "serviceTerminationReason": null,
  "agentId": "agent-research-baseline",
  "taskId": "AndroidWorld_6",
  "repeat": 0,
  "taskInstance": {
    "availability": "available",
    "identity": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    "reuseVerified": true
  },
  "benchmarkPhases": [
    {
      "phase": "materialization",
      "status": "success"
    },
    {
      "phase": "agent",
      "status": "success"
    },
    {
      "phase": "evaluation",
      "status": "running"
    }
  ],
  "agentStatus": {
    "availability": "available",
    "value": "success"
  },
  "benchmarkOutcome": {
    "availability": "pending",
    "value": null
  },
  "replay": {
    "availability": "pending",
    "replayId": null,
    "link": null
  }
}
```

### 5.4 分离状态轴

Experiment service lifecycle：

```text
accepted ─→ starting ─→ running ─→ finalizing ─→ terminal
    │           │           │
    └───────────┴───────────┴─→ cancelling ─→ finalizing/terminal
```

允许转换：

| 当前 | 允许下一状态 | 说明 |
| --- | --- | --- |
| accepted | starting、cancelling、terminal | 已持久但可能尚未有副作用 |
| starting | running、cancelling、terminal | preflight/binding |
| running | cancelling、finalizing、terminal | 正在调度 TaskRun |
| cancelling | finalizing、terminal | 等待安全边界并收口 |
| finalizing | terminal | 不向 cancelling 逆转；cancel request 仍可记录 |
| terminal | 无 | immutable |

Terminal reason：

- `completed`：schedule 按 Protocol 正常收口，不代表全部 PASS；
- `cancelled`：持久用户取消阻止了后续调度；
- `failed`：service/evidence/finalization 出现正式失败；
- `interrupted`：startup recovery 无法安全续跑 in-flight work。

Startup recovery 只使用内部 typed repository/ownership port，不新增 HTTP 状态机：

| 持久状态 | 已实现决定 | 禁止行为 |
| --- | --- | --- |
| accepted | 原 identity/snapshot/schedule 转移 owner 并回队 | 创建第二个 Experiment 或 schedule |
| starting | recovery-only reset 到 accepted，随后重跑纯 preflight | 直接续接旧线程或跳过 preflight |
| running/cancelling | 保留已提交前缀并以 interrupted 原子收口 | 自动重放 Agent/设备动作 |
| finalizing + result | 缺 publication 时调用既有幂等 publisher，否则只 finalize | 重跑 Runtime 或覆盖已提交 publication |
| finalizing + no result | 从 TaskRun terminal reason 只做 finalize | 构造结果、报告、bundle 或 Replay |
| terminal/current owner | no-op | owner transfer、事件或 scheduler wake |

SQLite 首版在可执行 composition 生命周期内持有 OS 自动释放的 database-scoped 独占
ownership；definition-only Catalog/Composer 不获取该锁。schema 6 已能表示全部恢复
事实，因此 5.2C-3 没有增加迁移版本。

TaskRun service lifecycle：

```text
scheduled → preparing → running → evaluating → cleaning_up → terminal
     └─────────────── 可按真实 failure/skip 跳到 cleaning_up/terminal
```

Benchmark phases 继续使用 Core 的 materialization、reset、setup、evaluator_pre、
agent、evaluation、cleanup，状态至少保留 pending/running/success/failure/skipped/
unverified。它们不与 service lifecycle 合并。

Agent status 使用 Core 的 `success/failure/step_limit/cancelled/device_failure`，只有
Agent 实际运行后才存在。Benchmark outcome 只接受
`pass/fail/invalid/skipped`，只有正式 `BenchmarkTaskResult` 产生后才存在。

Availability 词汇：

- `pending`：预期稍后产生；
- `available`：已提交且可读；
- `not_produced`：按真实流程没有产生；
- `not_captured`：运行发生但没有采集该证据；
- `excluded` / `hidden` / `redacted`：安全策略结果；
- `missing` / `corrupt` / `failed`：声明、完整性或 publication 失败；
- `truncated`：有界捕获。

未开始就取消的 TaskRun 是 `cancelled_before_start +
benchmarkOutcome.not_produced`，不能伪造 SKIPPED。若 Benchmark Core 已正式产生
SKIPPED，才显示 SKIPPED。

### 5.5 Command/query 与 pagination

- Create 成功返回 `202 Accepted`，此时 Experiment、snapshot、planned TaskRuns 和
  initial journal event 已提交；
- GET 在 worker 未开始时也能读取 accepted resource；
- TaskRun list 使用稳定 `(order, taskRunId)` 和 opaque cursor；
- Cancel response 返回 `requested`、当前 lifecycle 和 cooperative guarantee；
- identity/cursor/fingerprint 错误使用第 3.2 节 envelope；
- CAS 竞争只允许一个 terminal transition 获胜。

### 5.6 Cooperative cancel

| 收到 cancel 的位置 | 持久行为 | 运行保证 | 不保证 |
| --- | --- | --- | --- |
| accepted / starting，无副作用 | 保存 request；不启动新 TaskRun | 以 cancelled 收口 | pause/resume |
| Agent 运行 | 保存 request；发 cancellation signal | 下一个安全边界停止后续 activation/TaskRun | 中断当前模型、设备或 Python 调用 |
| evaluation | 保留已产生 evaluation；停止新 TaskRun | 当前不可中断操作返回后收口 | 丢弃或改写 PASS/FAIL |
| cleanup | 保留 phase evidence；按 Protocol 完成必要 cleanup | 不调度新 TaskRun | 强杀 cleanup |
| finalizing | 保持 finalizing；允许幂等 publication | 已有 TaskResult 不丢失 | 回退到 running |
| terminal | 幂等返回既有资源 | 不新增 terminal event | 改写结果 |

Cancel 是 Experiment command，不是 kill、pause、checkpoint 或 retry。

### 5.7 Startup recovery

| 旧状态 | 可证明事实 | 首版恢复 |
| --- | --- | --- |
| accepted/starting | 无 TaskRun/device side effect | 重新验证同一 snapshot 后原 identity 入队 |
| running/cancelling | in-flight device effect 可能发生 | 不重跑；保留 journal/evidence；TaskRun/Experiment interrupted |
| finalizing | TaskResults 完整，只有 publication 未完成 | 按 identity 幂等重试 report/Replay/bundle publication |
| terminal | 已有不可变终态 | 只读 |

每个 decision 写入 durable recovery event。无法证明操作未发生时，选择“不重做”，
避免把两个物理执行混成一个 TaskRun。

## 6. Persistence、journal 与 SSE

### 6.1 Typed ports

| Port | 职责 | SQLite V1 | PostgreSQL 兼容要求 |
| --- | --- | --- | --- |
| `BenchmarkExperimentRepository` | request、snapshot、lifecycle、cancel、result availability、recovery query | versioned tables + transaction/CAS | 同一 identity/idempotency/transition contract suite |
| `BenchmarkTaskRunRepository` | planned/runtime facts、phase、status、Replay availability | structured bounded rows | 不暴露 row ID/SQL |
| `BenchmarkExperimentEventJournal` | append、page、high-water mark、terminal uniqueness | Experiment-local sequence | transactionally equivalent sequence/idempotency |
| `BenchmarkExperimentArtifactStore` | definition/evidence/report/bundle content | managed local root + hash | backend 可变，opaque identity 不变 |
| `BenchmarkReplayPublisher` | TaskRun → native Replay | 调用现有 Replay repository/store | 返回相同公共 Replay DTO |

Domain、HTTP 和 React 不得依赖 SQLite row ID、SQL、database path、SQLite timestamp 或
锁语义。首版不实现 PostgreSQL，只要求未来 adapter 通过相同 contract tests。

Experiment、TaskRun、event、result 和 artifact metadata 默认永久保存，浏览器关闭、
失败或重启不能触发自动清理。首版没有 delete/quota API。Evidence preflight 无法保证
安全写入时，应在设备副作用前拒绝新 Experiment，而不是删除旧证据腾空间。

### 6.2 `StudioBenchmarkEventEnvelopeV1`

```json
{
  "schemaVersion": 1,
  "experimentId": "benchmark-experiment-0001",
  "sequence": 9,
  "eventId": "benchmark-event-evaluation-start-0001",
  "fingerprint": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
  "timestamp": 1785000002500,
  "source": "benchmark_runtime",
  "kind": "benchmark.phase.started.v1",
  "taskRunId": "benchmark-task-run-0001",
  "benchmarkPhase": "evaluation",
  "agentRunIdentity": "agent-runtime-run-0001",
  "nodePath": null,
  "activationId": null,
  "sourceSequence": 7,
  "payload": {
    "status": "running"
  }
}
```

Sequence 是 Experiment journal 的唯一 cursor；Benchmark/Agent source sequence 只作为
provenance。`(experimentId, eventId)` + canonical fingerprint 保证相同重试幂等；
同 identity 不同 fingerprint 是 integrity conflict。

Event kind registry：

| Kind family | 例子 | 主要消费者 |
| --- | --- | --- |
| Experiment lifecycle | `experiment.lifecycle.changed.v1` | monitor header |
| TaskRun lifecycle | `task_run.lifecycle.changed.v1` | task queue |
| Benchmark phase | `benchmark.phase.started.v1`、`completed.v1`、`failed.v1` | phase lane |
| nested Agent | `agent.runtime.event.v1` | graph/phone/inspector projection |
| artifact | `artifact.availability.changed.v1` | evidence panel |
| result/report | `result.availability.changed.v1` | partial/report link |
| recovery | `experiment.recovery.decided.v1` | audit |
| terminal | `experiment.terminal.v1` | stop reconnect |

旧客户端遇到未知合法 kind 时推进 cursor 并忽略/显示 unsupported；不兼容 major
envelope 时停止事实投影，不能猜 payload。

### 6.3 Event page

```json
{
  "schemaVersion": 1,
  "experimentId": "benchmark-experiment-0001",
  "items": [],
  "nextCursor": 9,
  "highWaterMark": 9,
  "terminal": false
}
```

`after` 是 exclusive cursor。未来 cursor 返回 `invalid_cursor`；保留范围内出现 sequence
缺口是 integrity failure，不能静默跳过。

### 6.4 Named SSE

```text
id: 9
event: benchmark.phase.started.v1
data: {"schemaVersion":1,"experimentId":"benchmark-experiment-0001","sequence":9}
```

- 支持 `Last-Event-ID` 和等价显式 cursor；
- 总是 backfill-before-wait；
- heartbeat/comment 不推进 cursor；
- 断开连接不取消 Experiment；
- 每连接状态、page size、heartbeat、write timeout、连接数和 event size 有界；
- 慢客户端可关闭并用 cursor 重连，不反压 Runtime；
- event 必须先提交 journal，再通知 waiter；
- journal 写失败时不发送该 event，并请求安全停止新的设备副作用；
- 最多一个 `experiment.terminal.v1`，它在最终 resource/availability/high-water mark
  提交后出现；SSE 发送完后正常结束。

Live factual projection、自动跟随视觉状态和用户 selection 分开。terminal TaskRun 进入
Replay 时加载持久 envelope，不把 SSE 内存缓存冒充 Replay。

## 7. Result、report、artifact 与 Replay

### 7.1 TaskRun result

```json
{
  "schemaVersion": 1,
  "taskRunId": "benchmark-task-run-0001",
  "identities": {
    "agentRevision": "revision-0001",
    "agentGraph": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "benchmarkPlan": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "experimentProtocol": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "taskInstance": "sha256:1111111111111111111111111111111111111111111111111111111111111111"
  },
  "agentStatus": "success",
  "benchmarkOutcome": "fail",
  "phases": [
    {
      "phase": "agent",
      "status": "success",
      "durationMs": 1520,
      "evidenceRefs": []
    },
    {
      "phase": "evaluation",
      "status": "success",
      "durationMs": 120,
      "evidenceRefs": [
        "artifact-evaluation-0001"
      ]
    }
  ],
  "evaluation": {
    "path": "root",
    "name": "all_checks",
    "operator": "and",
    "isPass": false,
    "shortCircuited": false,
    "children": [
      {
        "path": "root/0",
        "name": "expected_state",
        "status": "success",
        "isPass": false,
        "score": 0.0,
        "children": []
      }
    ]
  }
}
```

`agentStatus=success + benchmarkOutcome=fail` 是合法事实。Initializer infrastructure
failure 可以产生 INVALID 且 Agent status 不存在。Cleanup failure 不得覆盖已经产生的
Evaluation Result；最终 outcome 由 Protocol/Core 决定。

### 7.2 Experiment report

```json
{
  "schemaVersion": 1,
  "sourceReportIdentity": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
  "experimentId": "benchmark-experiment-0001",
  "final": true,
  "counts": {
    "pass": 1,
    "fail": 1,
    "invalid": 0,
    "skipped": 0
  },
  "agentMetrics": [
    {
      "agentId": "agent-research-baseline",
      "eligibleCount": 2,
      "successRateMicro": 0.5,
      "successRateMacro": 0.5,
      "wilsonInterval95": [
        0.0945,
        0.9055
      ]
    }
  ],
  "comparisons": [],
  "fairnessWarnings": [],
  "significanceClaimed": false
}
```

PASS/FAIL 是 eligible denominator；INVALID/SKIPPED 单独计数。UI 只投影正式 backend
report，不重算分母、Wilson、paired matching 或 evaluator aggregation。运行中只显示
带 `final=false`、planned/terminal counts 与 high-water mark 的 partial facts，不提前
产生 final report identity 或显著性结论。

Multi-Agent report 必须展示 paired、matched count、unmatched eligible count、
wins/ties、fairness warnings、样本量和 `significanceClaimed`。两个 repeats 等小样本
只能作为描述性结果。

### 7.3 Artifact descriptor 与 bundle

```json
{
  "schemaVersion": 1,
  "experimentId": "benchmark-experiment-0001",
  "taskRunId": "benchmark-task-run-0001",
  "artifactId": "artifact-evaluation-0001",
  "kind": "evaluation_evidence",
  "availability": "available",
  "contentType": "application/json",
  "size": 256,
  "sha256": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
  "provenance": "benchmark_evaluator",
  "causalIdentity": "benchmark-task-run-0001:evaluation"
}
```

Resolver 以 Experiment/TaskRun + opaque artifact identity 查找，拒绝绝对路径、`..`、
symlink escape、目录、未知 content type、跨 Experiment 引用和 digest mismatch。
Readable artifact 必须具有 content type、size/hash 与 availability。

Bundle manifest 示例：

```json
{
  "schemaVersion": 1,
  "kind": "studio_benchmark_experiment_bundle",
  "experimentId": "benchmark-experiment-0001",
  "members": [
    {
      "name": "reports/experiment-report.json",
      "size": 2048,
      "sha256": "sha256:5555555555555555555555555555555555555555555555555555555555555555"
    }
  ],
  "excludedEvidence": [
    {
      "kind": "sensitive_prompt",
      "reason": "hidden_by_default"
    }
  ]
}
```

成员只使用安全相对名称，公共 verifier 校验 size/hash/identity。默认 export 排除 hidden
Prompt，并保证其内容不从 event、report 或其他 bundle member 间接泄漏。

### 7.4 Terminal TaskRun → native Replay

Publication 输入是已持久：

```text
Experiment snapshot
  + TaskRun journal slice
  + Agent RunResult
  + Benchmark phases / Evaluation Result
  + managed artifact inventory
  → BenchmarkReplayPublisher
  → explicit replayId + /runs/{replayId}/replay
```

- publisher 在 metadata 原子提交后才让 History 可见；
- TaskRun 保存显式 `replayId/link/availability`，客户端不推导；
- Replay 同时保留 Agent status 与 Benchmark outcome；
- 失败、中断和取消保留 journal high-water mark 前缀；
- 启动前取消没有 Agent/outcome 时，不创建空成功 Replay；availability 是
  `not_produced`，或审计 envelope 明确标记对应事实未产生；
- live artifact identity、hash、causal identity 和 availability 在 Replay 中保持；
- publication 失败不删除 TaskResult，记录 `replay_finalization_failed` 并允许幂等重试；
- native path 不扫描 `temp/benchmark-runs`，与显式 legacy import 通过 provenance 区分。

## 8. 安全合同矩阵

| 数据 | SQLite metadata | Journal/SSE | 普通 HTTP/Inspector | Replay | 默认 bundle |
| --- | --- | --- | --- | --- | --- |
| API key、token、password、authorization | 禁止原值 | 禁止原值 | 禁止 | 禁止 | 禁止 |
| 完整模型响应 | descriptor；内容进受控 artifact | 仅 typed ref/summary | 已捕获且清洗后可按策略读取 | 可按策略读取 | 可包含允许内容 |
| 完整 Prompt | hidden availability；内容进隐藏 artifact | 不暴露 identity/content | 不可读取 | 默认不可读取 | 内容排除并声明 |
| raw device serial / ADB 参数 | 禁止；只存 profile 与安全 provenance | 禁止 | 禁止输入与输出 | 禁止 | 禁止 |
| 宿主绝对路径 / Catalog root | 禁止 | 禁止 | opaque identity/link | 禁止 | 禁止 |
| live Device/client/plugin/model object | 拒绝序列化 | 拒绝 | 禁止 | 禁止 | 禁止 |
| screenshot/UI XML | descriptor + opaque ref | typed ref | hash 校验后读取 | identity 保持 | 按策略包含 |
| external Package metadata | 安全 publisher/version/source kind | 有界 identity | 不返回安装路径 | provenance only | provenance only |
| evaluation/report | 有界结构或 artifact ref | availability/ref | 正式 backend projection | 保留 | hash manifest |

所有写入路径共享 sanitizer、深度/成员/string/event/artifact 大小限制。安全测试使用
synthetic canary 并扫描 SQLite、artifact、HTTP、SSE、Replay 和 export；公共文档与
fixture 不放入真实 credential。

## 9. Requirement 到后续 Change 的所有权

5.0 只定义和永久化合同，不实现 application code。5.2 的合同保持不变，但实现
owner 细分为 5.2A resource、5.2B worker、5.2C-1 event stream、5.2C-2
publication/Replay 与 5.2C-3 startup recovery。每项 requirement 的首要 owner：

| Capability | Requirement | Owner |
| --- | --- | --- |
| catalog-composer | Studio Benchmark Catalog 必须复用 metadata-only 后端事实源 | 5.1 |
| catalog-composer | list、detail 与 task metadata 必须无运行副作用 | 5.1 |
| catalog-composer | Catalog entry 歧义必须显式 | 5.1 |
| catalog-composer | Studio validate 必须显式且无设备副作用 | 5.1 |
| catalog-composer | Composer 必须绑定不可变有效 Agent revision | 5.1 |
| catalog-composer | Protocol Composer 必须保留正式 ExperimentProtocol 语义 | 5.1 |
| catalog-composer | Schedule preview 必须确定、可解释且无执行副作用 | 5.1 |
| catalog-composer | Preview 与 create 必须防止定义漂移 | 5.1 |
| catalog-composer | 服务必须显式发布执行 cardinality 限制 | 5.1 发布，5.2B 执行 |
| catalog-composer | Benchmark Composer 路由必须使用正式 typed domain | 5.1 |
| experiment-resource | Benchmark Experiment 必须是独立持久资源 | 5.2A |
| experiment-resource | Experiment definition snapshot 必须不可变且可复核 | 5.2A |
| experiment-resource | Experiment create 必须幂等且先持久化 | 5.2A |
| experiment-resource | Planned TaskRun identity 必须稳定且与 runtime instance 分离 | 5.2A 规划，5.2B 物化 |
| experiment-resource | Experiment service lifecycle、终止原因和结果必须分离 | 5.2A 模型，5.2B 执行 |
| experiment-resource | TaskRun 必须分离 service、phase、Agent 与 Benchmark 状态 | 5.2A 模型，5.2B 执行 |
| experiment-resource | 状态转换必须事务化并抵抗并发终止 | 5.2A repository，5.2B worker |
| experiment-resource | Experiment HTTP 必须提供安全 command/query | 5.2A |
| experiment-resource | Cancel 必须幂等且明确为协作式 | 5.2A 持久命令，5.2B 运行响应 |
| experiment-resource | Cancel 不得丢弃 evaluation、cleanup 与 finalization 事实 | 5.2B |
| experiment-resource | Startup recovery 不得伪造 in-flight resume | 5.2C-3 |
| experiment-resource | 持久化必须通过可替换 typed repository port | 5.2A |
| experiment-resource | 第一版持久数据不得自动清理 | 5.2A |
| experiment-resource | Device binding 必须使用安全 profile | 5.2B |
| experiment-event-stream | Experiment event stream 必须以持久 journal 为事实源 | 5.2A port，5.2B 生产 |
| experiment-event-stream | 事件必须先提交再对 live 客户端可见 | 5.2B append，5.2C-1 notify |
| experiment-event-stream | Event query 必须提供有界连续 backfill | 5.2C-1 |
| experiment-event-stream | SSE 必须使用 named event、cursor 恢复和 heartbeat | 5.2C-1 |
| experiment-event-stream | Event kinds 必须版本化并可渐进扩展 | 5.2C-1 |
| experiment-event-stream | 慢客户端不得反压 Benchmark Runtime | 5.2C-1 |
| experiment-event-stream | Event append 必须幂等并检测 identity 冲突 | 5.2A repository，5.2B producer |
| experiment-event-stream | Experiment 必须最多有一个 terminal event | 5.2B terminal，5.2C-1 stream |
| experiment-event-stream | Recovery 决策必须成为 durable event | 5.2C-3 |
| experiment-event-stream | Live 与 Replay projection 必须能共享事实而不共享传输状态 | 5.3 |
| task-results | TaskRun result 必须保留三类独立事实 | 5.2B 持久化，5.3 展示 |
| task-results | Benchmark phases 与 Evaluation Tree 必须完整投影 | 5.4 |
| task-results | Result 与 evidence availability 必须是一等事实 | 5.2B result，5.2C-2 publication，5.3 展示 |
| task-results | Experiment report 必须来自正式 Benchmark reporting | 5.4 |
| task-results | Paired comparison 必须保留公平性和样本限制 | 5.4 |
| task-results | Report 和 artifact HTTP 必须使用显式 resource link | 5.2C-2 后端，5.4 展示 |
| task-results | Managed artifact 必须 scoped、可验证且安全 | 5.2C-2 |
| task-results | 敏感 evidence 必须沿用统一 capture/export 策略 | 5.2C-2，5.4 |
| task-results | Experiment bundle 必须版本化且可校验 | 5.4 |
| task-results | 运行中只能显示明确的 partial facts | 5.3 |
| task-results | Reporting route 必须展示 loading、partial、terminal 与失败状态 | 5.4 |
| replay-evidence | Terminal Benchmark TaskRun 必须原子注册为 native Replay | 5.2C-2 |
| replay-evidence | Benchmark native Replay 必须保留失败或中断前缀 | 5.2C-2，5.3 展示 |
| replay-evidence | Experiment TaskRun 提升必须保持 artifact 与安全 identity | 5.2C-2，5.3 展示 |
| benchmark-authoring-release | Publication/export 必须只消费 owned immutable Package revision | 5.5E-2 |
| benchmark-authoring-release | Frozen closure 必须在 materialization 与 archive finalize 时重新校验 | 5.5E-2 |
| benchmark-authoring-release | 同一 readable semantic version 的 divergent content 必须安全冲突 | 5.5E-2 |
| benchmark-authoring-release | Catalog reader 必须看到完整旧或新 immutable snapshot | 5.5E-2 |
| benchmark-authoring-release | Export 必须是 exact frozen membership 的 byte-deterministic versioned ZIP | 5.5E-2 |
| benchmark-authoring-release | GET/HEAD download authority 必须 exact scoped 且不暴露 private locator | 5.5E-2 |
| benchmark-authoring-release | Publication/export 不得修改 draft、源 Catalog tree 或授予 execution evidence | 5.5E-2 |
| device-authority | Studio 只能从 trusted bounded config 解析显式 profile；无配置必须为空且不能隐式选择唯一在线设备 | 5.6A |
| device-authority | Experiment 接受时必须原子固定私有 binding，公开 identity/DTO/event 不得包含 raw serial、配置路径或 private fingerprint | 5.6A / SQLite schema 11 |
| device-authority | Run 与 Benchmark 必须以 private target key 共用进程级 lease，并在租约内构造 exact session | 5.6A |
| evidence-origin | TaskResult/Replay 必须独立表达 acquisition 与 environment；配置/profile 名称不得授予 fresh real Android evidence | 5.6A |
| layered-acceptance | 14 个稳定场景必须通过 bounded versioned proof ledger 连接 Experiment、TaskRun、Core、event、publication、Replay 与 artifact safe identities | 5.6B |
| layered-acceptance | production fake Studio chain、actual-backend browser 与 installed external Package 必须分别闭合，静态 fixture 只能作为 presentation supporting evidence | 5.6B |
| layered-acceptance | Core `2×2×2` capability 与 Studio `1×1×1` fail-closed product limit 必须分开报告；六个 forbidden-effect canary 必须为 0 | 5.6B |

Stage 5.5 单独定义 Benchmark authoring；Stage 5.6 永久按 5.6A explicit Android
profile/provenance、5.6B layered no-device acceptance、5.6C-1 real Android service
acceptance 与 5.6C-2 real Android browser acceptance 对所有实现 owner 做分层验收。
原 `validate-studio-benchmark-android-5-6` 只是 umbrella，不作为 executable change。

## 10. 第一条执行切片

Stage 5.2B 首条可运行切片固定：

```text
1 immutable Agent revision
× 1 Benchmark Package
× 1 selected Task
× 1 repeat
× 1 safe device profile
```

DTO 仍使用 `agentRevisions[]`、`taskIds[]` 和正式 Protocol。服务发布：

```json
{
  "schemaVersion": 1,
  "executionLimits": {
    "maxAgents": 1,
    "maxSelectedTasks": 1,
    "maxRepeats": 1,
    "multiAgentComparison": false
  }
}
```

超限返回 `unsupported_cardinality`，不得只运行第一项。Stage 5.6B 必须把 Core
Runtime 的 multi-task/repeats/multi-Agent fairness 证据与 Studio Worker 的 1×1×1
拒绝边界分别验证和报告；5.6 不负责解除该限制。未来若扩展 Studio cardinality，
必须使用同一 DTO/identity 并建立独立产品 change，不能混入验收工作。

## 11. 分层验收矩阵

| 层 | 必须验证 | 证据 | 不能据此声明 |
| --- | --- | --- | --- |
| definition | Catalog source、无设备 list/detail/validate、canonical preview、漂移 conflict | unit/contract + no-device spies | 实际任务成功 |
| repository | idempotency、CAS、pagination、restart、immutable terminal、adapter suite | SQLite contract tests | PostgreSQL 已实现 |
| events | append-before-notify、连续 backfill、Last-Event-ID、heartbeat、slow client、唯一 terminal | journal/SSE tests | 网络永不丢包 |
| fake lifecycle | success、FAIL、INVALID、SKIPPED、cancel、evidence failure、interruption、cleanup | fake-device integration | 真实 Android 兼容 |
| browser | Catalog → Composer → Monitor → Replay → Report → Export；刷新/断线/主题 | Vitest + real browser fake smoke | 真机 UI 已验收 |
| package | clean wheel、installed external Package、无隐式大型 asset | clean environment tests | 任意第三方包安全 |
| fairness | Core multi-task、repeats、multi-Agent、TaskInstance reuse、paired/fairness warning；Studio 1×1×1 超限整体拒绝 | 5.6B deterministic fake experiment + Studio negative contract | Studio Worker 已支持 multi-cardinality、统计显著或通用优越性 |
| device authority | safe profile 显式绑定 private serial/session、pre-action fail closed、无 raw serial 泄漏 | 5.6A contract/fake preflight | 已产生真实 Android 成功证据 |
| real Android service | 用户选择 profile/Agent/Package/task 的代表性正例与受控负例，完整 durable publication/Replay/restart | 5.6C-1 新采集 result/report/trajectory/bundle/device evidence | 浏览器真机闭环或全量 Benchmark 通过率 |
| real Android browser | Catalog → Composer → Monitor → Report/Evidence → Replay → Export，区分 fresh/fake/historical provenance | 5.6C-2 真实浏览器 + 设备观察 + durable identity 清单 | 新增 runtime 语义、任意设备兼容或模型质量 |

真实 Android 必须放在 5.6C-1/2，并由用户明确选择 5.6A 配置的安全 profile、Agent
和任务。5.6B fake、历史 Replay 和 5.6C fresh real Android 证据分别报告；profile
ID、URL、标题、截图外观或历史 Core artifact 均不能单独授予当前 Studio 真机证明。

## 12. 已知限制与后续

- Stage 5.1 已实现 React definition/preview route；5.2A/5.2B 已实现 Experiment
  endpoint、SQLite repository、单 Worker、persistent cooperative cancel、durable
  journal producer 和 bounded result，但没有 React Monitor；
- 5.2C-1 已实现公共 Experiment event page、连续 backfill、named SSE、heartbeat、
  reconnect 和慢客户端隔离；
- 5.2C-2 已实现 schema 6 managed report/trajectory/bundle publication、scoped
  artifact resolver、read-time integrity closure 和 explicit native Benchmark
  Replay；正式 HTTP 入口已开放，但 5.4 的报告统计界面尚未实现；
- 5.2C-3 已实现本地唯一 executable owner、accepted/starting requeue、
  running/cancelling interruption、finalizing publication/finalize-only recovery
  和 durable recovery events；它不恢复线程或重放不确定的设备动作；
- SQLite 是已实现的第一版 adapter；
- PostgreSQL 只有 storage-neutral contract，没有 adapter；
- retention 数据默认保留，但 quota/delete/cleanup 尚无产品合同；
- Stage 5.5A durable authoring resource、5.5B-1/2/3 definition/
  managed-content/resource editor、5.5C-1/2 validation/dry-run、5.5D Contract
  Tests 与 5.5E-1/2 validated freeze、publication/export 已实现；E-1 只新增 exact-current all-split
  definition-only attestation、closed immutable Package revision、SQLite schema 9
  atomic durability 与 scoped exact HTTP read；E-2 只新增 schema 10 release authority、
  managed Catalog publication、deterministic Package export 与 URL-owned Release
  workflow。二者都不授予 runtime/device evidence；5.5E-3 已增加 bounded
  source-text Preview、structured diff、exact reanalysis/Confirm、schema-10
  idempotent unvalidated draft、migration provenance 与 disposable React session，
  同样不授予 runtime/device evidence。Stage 5.5 已完成；Stage 5.6A 已实现 strict
  trusted profile、schema-11 private binding、exact-target shared lease 与两轴 evidence
  origin，但只具备 no-device/fake/contract evidence。5.6B 已以 production fake
  composition、14 场景 proof ledger、actual-backend browser、Core `2×2×2` 与
  Studio `1×1×1` 分离边界，以及 installed external Package clean wheel 完成分层
  no-device 验收；所有新执行均为 `contract_fixture/fake_device` 且
  `realDeviceEvidence=false`。5.6C-1/C-2 尚未实现，当前下一步为
  `validate-studio-benchmark-android-service-5-6c1`；
- 不支持分布式多设备调度、pause/checkpoint、节点重试、实时设备控制或自动失败诊断；
- 已有代表性 Android 证据不等于全部任务、设备、Agent 或统计结论。

## 13. 规范来源

- [Stage 5 产品路线](studio-benchmark-experiment-roadmap.md)
- [Benchmark 长期架构](benchmark-architecture.md)
- [Benchmark 运行与比较](benchmark-running.md)
- [Studio 前端架构](studio-frontend-architecture.md)
- [Studio Benchmark Validated Freeze](studio-benchmark-validated-freeze.md)
- [Studio Benchmark Package Publication / Export](studio-benchmark-package-publication-export.md)
- [Studio Benchmark Legacy Migration](studio-benchmark-legacy-migration.md)
- [Studio Benchmark Android Profile 与证据来源](studio-benchmark-android-profile.md)
- [当前已接受的 OpenSpec 合同](../openspec/specs)：早期 Stage 5.0 proposal/design
  为内部历史材料，不随公开源码发行。
