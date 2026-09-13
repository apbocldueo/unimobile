# Studio Benchmark Evidence Viewer

本文记录 Stage 5.4D-2
`implement-studio-benchmark-evidence-viewer-5-4d2` 的已验证实现边界。它描述
2026-07-30 的代码、自动化测试和 no-device 浏览器证据；不把当时尚未实现的
Export、真实 Android 或自动失败诊断写成该 Change 的已完成能力。

## 解决的问题

5.4B 已能严格解析 Core TaskRun report 并展示 Evaluation Tree，但叶子 evidence
只显示 descriptor。浏览器不能根据 `artifactRef` 猜文件名、artifact id 或存储
路径，也不能把未受限响应直接读入内存。

5.4D-2 将这个缺口收口为一条受控链路：

```text
Evaluation leaf artifactRef
        ↓ exact causal match
closed Experiment inventory
        ↓ same Experiment + same Studio TaskRun + exactly one
strict parsed links.content capability
        ↓ bounded stream + MIME/size contract
media-specific adapter
        ↓ escaped text / bounded PNG / download-only
React-local disposable Viewer
```

涉及层：

- `shared/api`：通用的有界字节响应合同；
- `entities/benchmark-report`：因果解析、媒体策略与内容适配；
- `features/benchmark-reporting`：Viewer 本地状态、取消和资源释放；
- `widgets/benchmark-report-workbench`：把 leaf open intent 接入既有 Report；
- 既有 Benchmark managed resolver/HTTP：scope、availability、size/hash 与响应头
  权威；
- no-device fixture、前后端合同测试和真实浏览器 journey。

## 因果归因合同

`resolveBenchmarkEvidence` 只接受已收口的 bounded full inventory。成功需要：

```text
inventory.experimentId             == current Experiment
descriptor.experimentId            == current Experiment
descriptor.taskRunId               == selected Studio TaskRun
descriptor.causalIdentity          == leaf artifactRef
visible match count                == 1
inventory.nextCursor               == null
```

它不会回退到：

- artifact kind；
- artifact id；
- Core TaskRun id；
- 文件名或后缀；
- path-shaped `artifactRef`；
- Experiment-scoped descriptor；
- storage reference、宿主路径或 bundle 扫描。

零匹配与多匹配分别是 `reference-unavailable` 和 `ambiguous-reference`。隐藏
descriptor 不进入 inventory；`hiddenCount` 只作为聚合事实显示，不能归因给具体
leaf。可读取 item 也会再次通过 strict inventory item parser，unsafe/rebuilt
content link 不能进入加载器。

## 有界字节传输

`studioBoundedByteRequest` 不调用 `response.text()`、`blob()` 或
`arrayBuffer()`。调用者必须提供：

- strict capability path；
- `AbortSignal`；
- descriptor `Content-Type`；
- descriptor byte size；
- Viewer policy maximum。

读取顺序：

1. descriptor size 超过 policy 时在 fetch 前拒绝；
2. 非成功响应只进入稳定的 Studio error envelope；
3. 规范化后的 `Content-Type` 必须精确相等；
4. `Content-Length` 必须存在、为 canonical non-negative integer 且等于
   descriptor size；
5. `ReadableStream` 分块读取，任一时刻不得超过 descriptor 或 policy；
6. EOF 后实际字节数仍必须精确相等；
7. 只返回由当前 selection 拥有的 `Uint8Array`，不进入共享缓存。

`Cache-Control: private, no-store` 和
`X-Content-Type-Options: nosniff` 继续由现有 backend content route 提供。浏览器
不重复计算 SHA-256：managed resolver 在打开 stream 前已经验证 size/hash；前端
验证 MIME、声明长度、实际长度和 preview policy。

## 媒体策略

| Content type | Viewer 行为 | 上限/验证 |
|---|---|---|
| `application/json` | UTF-8 parse、确定性 pretty text | 2 MiB |
| `application/x-ndjson` | 每个非空行独立 parse、保持顺序 | 2 MiB |
| `application/xml` | escaped source text，不解析 DOM | 2 MiB |
| `text/plain` | escaped `<pre>` text | 2 MiB |
| `image/png` | temporary Blob URL | 8 MiB、PNG signature、IHDR、每轴 4096、总像素 16,777,216 |
| `application/zip` | browser download handoff | 不 fetch preview、不嵌入、不解压、不声明完成 |

非 allowlist media 不会生成下载 action。JSON、XML、text 中的 HTML/script-looking
内容只作为 React text node 渲染，未使用 `dangerouslySetInnerHTML`。

## 状态与资源生命周期

Viewer 将 backend availability 与本地 preview failure 分开：

```text
idle / resolving / loading
ready-text / ready-image / download-only
no-reference / reference-unavailable / ambiguous-reference
pending / not-produced / excluded / missing / corrupt / failed
oversized / size-mismatch / mime-mismatch / invalid-content / request-failed
```

`available`、`redacted`、`truncated` 始终保留在 descriptor badge 中。preview
失败不会修改持久 availability，也不会覆盖 Experiment report、aggregate、
TaskRun、Evaluation 或 Replay state。

selection 只存在于 Report workbench 的 React local state：

- 不进入 URL；
- 不进入 Zustand/localStorage；
- artifact body 不进入 TanStack Query；
- 展开 Evaluation Tree 或 refresh Report 不会自动加载 body；
- close、换 evidence、换 TaskRun、换 scope 和 unmount 都会 abort；
- 迟到 success/failure 被忽略；
- 每个 PNG object URL 在替换或 unmount 时精确 revoke。

## 后端与安全边界

本 Change 没有新增 endpoint、数据库 schema 或生产后端模块。它复用
`LocalStudioBenchmarkManagedArtifactStore.open_artifact` 和现有 Experiment/
TaskRun content routes。回归证明：

- cross-Experiment/cross-TaskRun 请求为 scoped not-found；
- hidden/unreadable descriptor 无法打开；
- 成功响应带 allowlisted exact content type、exact content length、
  private no-store 和 nosniff；
- read-time 文件缺失将 availability 收口为 `missing`，清空 content type/hash，
  后续 inventory 不再返回 link；
- read-time size/hash 不一致将 availability 收口为 `corrupt`，同步收口 publication/
  Replay integrity；
- error envelope 不包含 storage ref、宿主绝对路径或 artifact body。

既有 publisher security canary 继续证明 Prompt、API key、raw device serial 和
host path 不进入 durable public material。前端新增 canary 证明 script-looking
source 保持 inert，原始 backend error message 不进入 Viewer。Evidence Viewer
仍不能证明任意历史 artifact 本身不含 secret；publication policy 是第一道权威
边界。

## 验证证据

可复验命令：

```bash
cd studio
npm test -- --run
npm run typecheck
npm run lint
npm run build
node --check scripts/benchmark-monitor-smoke-fixture.mjs

cd ..
uv run pytest -q \
  tests/studio/test_benchmark_experiment_resource.py \
  tests/studio/test_benchmark_execution_worker.py \
  tests/studio/test_benchmark_event_stream.py \
  tests/studio/test_benchmark_publication_replay.py \
  tests/studio/test_benchmark_startup_recovery.py \
  tests/studio/test_benchmark_reporting_resource.py \
  tests/studio/test_benchmark_experiment_history.py \
  tests/studio/test_replay_backend.py
```

实际结果：

- frontend：`52 files / 214 tests passed`；
- typecheck、lint、production build：通过；
- relevant backend/resource/worker/event/publication/recovery/reporting/
  History/Replay：`129 passed`；
- focused resolver/header/integrity closure：`8 passed`；
- fixture JavaScript syntax check：通过；
- production build 仍只有既有的大 chunk warning，没有 build failure。

没有执行新的 clean-wheel：生产 backend/package 文件和 schema 都未改变；本 Change
只增加前端、fixture、测试和文档。已有 5.2C-2/5.4A 的 clean-wheel managed
resolver 证据，加上本次 129 项安装边界相关回归，足以验证复用合同；这里不声明
新的 clean-wheel 证明。

## no-device 浏览器 journey

本地 fixture：

```bash
cd studio
npm run smoke:benchmark-monitor
npm run dev -- --host 127.0.0.1
```

真实浏览器已验证：

```text
History
  → report-ready durable row
  → Report / selected TaskRun / expanded leaf
  → explicit JSON open（此前不请求 body）
  → switch ZIP download-only
  → close / reopen redacted
  → pending / duplicate / oversized / MIME mismatch
  → bounded 1×1 PNG
  → native TaskRun Replay
```

观察结果：

- HTML/script-looking JSON 只显示为文本；
- ZIP 文案明确只是 browser handoff，不声称 download/verification complete；
- hidden aggregate 不归因到 leaf；
- duplicate causal identity fail closed；
- Replay route 与既有 partial/no-device 事实保持可用；
- journey 结束时浏览器应用错误日志为空。

fixture 不启动 worker、设备、插件、模型或 SSE；它不构成真实 Android、真实
multi-Agent scheduler、统计显著性或自动 failure diagnosis 证据。

## 取舍与替代方案

- 复用 bounded full inventory，而不是增加 causal-reference endpoint：避免新增
  服务权威，但最多需要读取 2,000 个 metadata item。
- selection 使用 React local state，而不是 Query cache：retry 略多样板，但 byte
  生命周期可审计。
- backend 校验 SHA，frontend 校验 transport shape：避免重复 digest 计算和竞争性
  integrity fact。
- XML 只看 source，ZIP 只 handoff：牺牲内嵌便利，避免主动内容和解压攻击面。
- Viewer 是 Report 内的非 modal aside：可切换 leaf，同时不创建新的 route/state
  ownership。

## 限制与失败情况

- full inventory 仍受 2,000 item 上限；超过时无法归因，不会猜测；
- hidden aggregate 无法说明某个具体 causal ref 是否被隐藏；
- PNG 只验证 preview 前缀和尺寸，不是完整图像格式/语义证明；
- 浏览器 handoff 没有 download completion receipt；
- 不读取 ZIP manifest，不做 export single-flight；
- 不提供 retention/delete、PostgreSQL/object storage、大规模性能或真实 Android
  证据；
- structured trajectory 和 Viewer 支持人工审阅，不是自动根因分析。

## 历史交接与当前状态

5.4D-2 完成时的下一步是：

```text
implement-studio-benchmark-export-5-4d3
```

5.4D-3 负责正式 report/trajectory/bundle/evidence Export、metadata refresh、
per-artifact single-flight、double-click 协调、manifest/excluded-evidence 展示和
truthful browser handoff。它必须复用本 Viewer 的 capability/availability 边界，
不能把 ZIP 解压、点击开始或 response headers 冒充导出完成。

该交接现已完成，具体实现见
[Studio Benchmark Export](studio-benchmark-export.md)。Stage 5.4 已收口，当前
下一步固定为 `implement-studio-benchmark-authoring-5-5`。
