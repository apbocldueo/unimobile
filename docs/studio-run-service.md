# Studio Run Service

本文记录 Studio Stage 3 已实现的普通 Agent Run 后端纵向切片。它让一个已保存且编译
有效的 Agent revision 在本地 Android 运行，并通过 HTTP、durable journal、SSE、
managed artifact 和原生 Replay 提供可审计证据。

这不是 Benchmark 执行入口。`AgentConfig`/AgentGraph 与 `BenchmarkTask` 仍是独立合同。
Stage 3 也不包含暂停、checkpoint、节点重试、实时视频或浏览器控制真机。

## 已实现数据流

```text
POST Run
  → 校验普通 task DTO
  → 先解析已有 clientRequestId 或内容冲突
  → 加载 valid immutable revision
  → 重算 AgentGraph canonical hash
  → exact static readiness（组件/依赖/SecretRef/Profile）
       └─ blocked：不创建 Run、event、artifact 或 scheduler work
  → SQLite 原子创建 accepted Run
  → bounded single-worker scheduler
  → 重新校验 snapshot/dependency/SecretRef 并 bind_execution_plan
  → evidence preflight + device-profile lease
  → AndroidGraphRuntime
       ├─ AgentGraph DeviceObserve activation → screenshot/UI XML
       ├─ bounded feedback → later DeviceObserve activation
       ├─ durable Run event journal → SSE/query
       ├─ screenshot/UI XML/action/manifest → managed artifacts
       └─ component debug → summary + response/hidden Prompt artifacts
  → 持久化 RunResult
  → trusted native Run → Replay
  → 唯一 run.terminal event
```

Run 绑定自包含的 revision snapshot；后续保存新 revision 不会改变已接受 Run 的图。
SQLite 只保存结构化 metadata 和相对 storage reference，大内容保存在数据库旁的
Local Artifact Store。Application service 依赖 repository protocols，不依赖 SQLite
row ID 或 SQL；PostgreSQL 可在后续 Change 中实现同一协议，不需要改变 HTTP DTO。

普通 Studio Run 将 `TaskInput` 和不含设备证据的 `ObservationRequest` 交给图边界。
`AndroidGraphRuntime` 只为图中正式 `DeviceObserve`/`ActionExecutor` service 注入设备实现，
不会在 Kernel 调度前截图、补写 observation 或添加隐藏 interaction。每张截图都必须对应
一次成功的 DeviceObserve activation；非终止 ActionResult 必须通过图声明的有界 feedback
到达下一次 DeviceObserve，DONE/FAIL 则通过 terminal control 到达 Output。typed
`ActionResult` 统一进入最终 RunResult，失败前已经提交的 observation、动作和 artifact
继续保留。

旧 Studio 线性 revision 仍可读取、导出和用于历史审计，但若缺少正式 DeviceObserve、
ActionRequest、terminal gate 或有界 feedback，ordinary Android Run readiness 会在创建
Run、调用模型或触碰设备之前阻断。该边界不删除 Python SDK、AgentConfig YAML、
`ModularAgent`、`AgentRunner` 或独立 `BenchmarkTask` JSON 公共入口。标准模板、诊断和
复验说明见 [Studio Agent 显式反馈闭环](studio-agent-feedback-loop.md)。

## 启动

仓库根目录：

```bash
conda run -n unimobile python -m zhixing.studio serve \
  --host 127.0.0.1 \
  --port 8765 \
  --database temp/studio.sqlite3 \
  --secrets ./secrets.yaml \
  --device-profile-config ./studio/device-profiles.json
```

配置路径相对启动命令的当前工作目录解析，而不是相对 `zhixing/studio/` Python 包解析。
例如文件实际位于仓库的 `studio/device-profiles.json` 时必须使用上面的路径；传入不存在的
`./device-profiles.json` 会被安全地拒绝为“必须是 regular file”。

不传 `--database` 时，服务按 workspace identity 使用操作系统用户数据目录，而不是把
绝对 workspace path 写入公开 DTO。`temp/studio.sqlite3` 只适合本地演示和复验。

普通 Run 不再假定 `local-android`。浏览器只能从服务端安全目录选择
`deviceProfileId`；空目录阻止提交，多个 Profile 要求显式选择，raw ADB serial 永不进入
请求。SecretRef 与 Profile 的受信文件格式、readiness API 和安全边界详见
[Studio Agent Run Readiness](studio-agent-run-readiness.md)。

## HTTP 合同

服务同时接受 `/api/studio/...` 和兼容的 `/studio/...`。

### 创建普通 Run

```bash
curl -sS -X POST http://127.0.0.1:8765/api/studio/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "schemaVersion": 1,
    "clientRequestId": "research-run-001",
    "agentId": "<saved-agent-id>",
    "revisionId": "<valid-revision-id>",
    "task": {
      "text": "Open Settings and finish",
      "metadata": {"experimentTag": "local-smoke"}
    },
    "deviceProfileId": "research-android"
  }'
```

静态 readiness 通过时预期 HTTP `202`；已知组件、依赖、SecretRef 或 Profile 错误同步
返回安全诊断，并且没有 durable side effect。响应包含 opaque `runId`、revision/canonical identity、lifecycle、
result/Replay availability 和 event high-water mark，不包含 graph body、数据库路径、
设备 serial 或 live object。同一 `clientRequestId` 与相同内容重试返回同一 Run；
相同 ID 配不同内容返回 `studio.run.idempotency_conflict`。

Benchmark-shaped task、secret/token/password、raw serial、宿主绝对路径、过深或过大的
metadata 会在创建前被拒绝。

### 查询与取消

```bash
curl -sS http://127.0.0.1:8765/api/studio/runs/<runId>

curl -sS -X POST \
  http://127.0.0.1:8765/api/studio/runs/<runId>/cancel \
  -H 'Content-Type: application/json' \
  -d '{"schemaVersion": 1}'
```

取消是持久、幂等、协作式请求。`accepted` Run 可在无设备副作用时取消；运行中的
模型/设备调用不会被宣称为强制中止，Runtime 在下一个 activation 安全边界观察信号。
重复取消 terminal Run 返回同一不可变结果，不产生第二个 terminal event。

### 事件查询与 SSE

```bash
curl -sS \
  'http://127.0.0.1:8765/api/studio/runs/<runId>/events?after=0&limit=100'

curl -N \
  -H 'Last-Event-ID: 0' \
  http://127.0.0.1:8765/api/studio/runs/<runId>/events/stream
```

`after` 与 SSE `Last-Event-ID` 都表示“最后已确认 journal sequence”。服务先从 SQLite
回填，再等待新 commit；journal 使用固定 `event: journal` 和版本化 durable data
envelope。空闲时同时发送 heartbeat comment 与固定 `event: heartbeat`，heartbeat
没有 journal data/id，不进入 Replay 或推进 cursor。写入慢、断线或重复连接不会阻塞
producer 或改变 Run。收到唯一 `run.terminal` 后，SSE 在发送全部 high-water mark
以内事件后关闭。

### Artifact 与 Replay

```bash
curl -o artifact.bin \
  http://127.0.0.1:8765/api/studio/runs/<runId>/artifacts/<artifactId>

curl -sS http://127.0.0.1:8765/api/studio/replays/<runId>

curl -o replay.zip \
  http://127.0.0.1:8765/api/studio/replays/<runId>/bundle
```

Artifact 只能用 `runId + artifactId` 读取；服务验证 ownership、regular file、managed
root、size、SHA-256 和 allowlisted content type。cross-run、path traversal、symlink
escape、缺失/损坏内容和 hidden Prompt 均被拒绝。

完整模型响应在被组件 hook 捕获时默认保存为可读取 artifact。完整 Prompt 会先 redaction，
再作为 `sensitive_prompt` hidden artifact 持久化；普通 Run/Replay artifact endpoint
和默认 Replay bundle 都不返回 Prompt 内容。超限文本按 UTF-8 字节截断，并记录
`truncated` availability 与 original size。

terminal Run 由 trusted finalizer 直接注册为 `native_studio_run` Replay，不调用 legacy
Benchmark importer，不扫描 `temp/`。成功、失败、取消、step limit、device failure 和
service restart 都保留已确认 journal prefix、RunResult、artifact inventory 与真实
availability。Replay 发布失败不会让半成品进入 History；Run 保留稳定错误 code，后续
可安全重试。

## 存储、恢复与容量

- 默认 SQLite schema 使用 additive migration，当前 Run/Event/Artifact 为 schema 3；
- 默认 live evidence root 位于数据库旁的 `artifacts/live/`；
- 单 artifact 默认上限 32 MiB，单 Run 默认 2 GiB；
- 可用空间必须保留至少 256 MiB；
- managed 内容达到默认 20 GiB 时记录 soft warning，但不会自动删除；
- 服务重启不会从中间 activation 恢复。旧 process owner 的非终止 Run 收口为
  `studio.run.service_restarted` failure、生成 partial-prefix Replay，并且不重放动作。

Stage 3 没有 quota 管理 UI、自动清理或删除 API。换 PostgreSQL 只替换结构化 repository；
大型 artifact 仍需要独立、受控、可校验的 content store 设计。

## 可复现验证

```bash
# Stage 3 contracts、repository、evidence、scheduler、native Replay、HTTP/SSE
PYTHONPATH=tests uv run pytest -q \
  tests/studio/test_run_models_repository.py \
  tests/studio/test_run_artifacts_debug.py \
  tests/studio/test_run_event_performance.py \
  tests/studio/test_run_execution.py \
  tests/studio/test_run_replay_http.py

# Stage 1/2 与相关 Graph/Android Runtime 回归
PYTHONPATH=tests uv run pytest -q \
  tests/studio \
  tests/graph \
  tests/runtime/test_generalized_kernel.py \
  tests/runtime/test_android_graph_runtime.py \
  tests/runtime/test_runtime_contract.py

# clean wheel
uv run pytest -q \
  tests/packaging/test_artifacts.py \
  tests/packaging/test_isolated_install.py

# OpenSpec
/Users/maczhen/.npm/_npx/abab5bd700860149/node_modules/.bin/openspec \
  validate implement-studio-run-service-3 --strict
```

截至 2026-07-26，上述 Studio、Graph/Runtime 与 packaging 合并相关回归为
`153 passed`，Change strict validation 通过。

截至 2026-08-03，Studio 标准模板已改为显式 DeviceObserve → Perception → Reasoning →
ActionRequest → ActionExecutor → terminal/feedback 闭环，Android Runtime 的 pre-Kernel
首帧兼容注入已移除。确定性 fake-device 与真实 Studio HTTP/event/SSE/native Replay
测试覆盖 `observe → TAP → feedback → observe → DONE`、显式 FAIL、模型/设备失败、
feedback 耗尽和 step limit。本次没有执行新的真实 Android Run。

自动化 fake-device 只证明合同、调度与证据闭环。当前对话没有用户明确选择可用的真实
Android profile/serial，因此本阶段真实 Android smoke **未验证**；不得用 fake 结果
替代真实设备证据。

## 已知限制

- 仅本地单用户、单进程、默认单 worker；性能测试不外推远程或多租户规模；
- 默认 composition 当前使用 built-in resolver；需要外部 component environment 时必须
  由宿主显式注入；
- 无 pause/checkpoint/resume、节点 retry、实时视频、浏览器触控真机或 Benchmark Run；
- active 模型/设备调用只能协作取消，无法安全强停；
- SQLite metadata 与本地文件系统不是跨介质事务；实现使用 staging、hash 和可重试
  finalization 缩小窗口，但完全磁盘故障仍可能需要 operator 修复；
- Replay 用于审计与人工失败定位，不提供自动根因诊断；
- 尚无 PostgreSQL、远程对象存储、多用户授权、自动清理或删除语义。
