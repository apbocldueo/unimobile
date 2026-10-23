# Studio Benchmark Reporting Resource（Stage 5.4A）

本文记录 `implement-studio-benchmark-reporting-resource-5-4a` 已验证的实现边界、
资源合同、前端消费方式、验证证据和后续交接。总体产品目标与 5.4A–5.4D 的固定顺序
见 [Studio Stage 5.4 Benchmark Reporting 路线](studio-benchmark-reporting-roadmap.md)。

截至 2026-07-29，5.4A 已建立可供后续报告页面消费的资源层；它没有实现 Report、
History 或 Export 页面。

## 一句话结果

Studio 现在可以在不连接设备、不启动 Worker、也不扫描 artifact 目录的前提下：

1. 稳定分页查询已经持久化的 Benchmark Experiments；
2. 分页查询某个 Experiment 的安全 artifact metadata；
3. 通过后端给出的显式 link 有界读取并严格解析正式 Core Experiment/TaskRun report。

这一步把“后端已经生成报告”和“前端可以安全理解报告”连接起来，但没有把资源合同
误写成已经完成的报告工作台。

## 解决的 Agent 工程问题

Stage 5.2C-2 已经把 Core report、trajectory、bundle 和 Replay 纳入受管发布边界，
Stage 5.3 也能监控一个 durable Experiment；但此前仍有三处断点：

- 没有公共 Experiment history collection，刷新后无法从稳定分页资源重新发现历史；
- 没有 Experiment 级 artifact inventory，前端若想找 TaskRun report 只能猜路径；
- Core report 使用 `snake_case` 且包含统计与递归 Evaluation Tree，前端没有严格、
  有界、版本化的实体合同。

5.4A 涉及的层次是：

```text
SQLite schema-6 durable facts
    ├─ Experiment snapshot / lifecycle / availability
    └─ managed artifact descriptors
             │ metadata only
             ▼
repository ports + SQLite adapters
             ▼
StudioBenchmarkExperimentService
             ▼
HTTP history / inventory / existing content resources
             ▼
frontend entities
    ├─ benchmark-experiment history
    └─ benchmark-report inventory + Core report parsers
```

AgentGraph、Benchmark Core 的运行/评估/统计语义和设备执行边界均未修改。

## 已实现的后端资源

### Experiment history

```http
GET /studio/benchmark-experiments?limit=<1..100>&cursor=<opaque>
```

响应是 compact history page，顺序固定为：

```text
(acceptedAt DESC, experimentId DESC)
```

cursor 保存最后一个 `(acceptedAt, experimentId)` exclusive boundary，并包含版本和
canonical checksum。翻页期间插入更新记录不会让已经返回的条目重复；相同时间戳以
Experiment identity 稳定打破平局。

每条 history item 只包含：

- Experiment lifecycle、terminal reason 和时间戳；
- immutable snapshot 中的 Catalog entry、Package、split、Agent/revision identity；
- planned TaskRun count；
- outcome/report/replay/trajectory/bundle availability；
- 已经实现且与 availability 一致的 self、TaskRuns、artifacts、report、bundle link。

它不返回完整 definition、AgentGraph、BenchmarkPlan、Protocol、设备绑定、process
owner 或当前 Catalog 推断的可变标题。因此即使原 Package 已移动或删除，历史事实仍
来自当时的 immutable snapshot。

### Experiment artifact inventory

```http
GET /studio/benchmark-experiments/{experimentId}/artifacts
    ?limit=<1..100>&cursor=<opaque>
```

资源按 `artifactId ASC` 稳定分页；cursor 带 checksum 且绑定 Experiment。repository
只选择 `artifact_id` 和 `descriptor_json`，不会读取 `storage_ref`、打开 artifact、
复算 hash、解析 bundle 或扫描目录。

可见 descriptor 保留：

- Experiment/TaskRun scope；
- kind、availability、content type、size、SHA-256；
- provenance 和 causal identity；
- 仅在 `available`、`redacted`、`truncated` 时生成的精确 content link。

`pending`、`not_produced`、`excluded`、`missing`、`corrupt` 和 `failed` 仍可见，
但没有 content link。`hidden` descriptor 完全不出现在 `items` 中；页面只获得
不含 identity 的 `hiddenCount`。

### 既有 report/content 资源保持权威

5.4A 没有创建第二套报告格式。以下既有 link 仍由受管 resolver 提供内容：

```http
GET /studio/benchmark-experiments/{experimentId}/report
GET /studio/benchmark-experiments/{experimentId}/artifacts/{artifactId}
GET /studio/benchmark-experiments/{experimentId}/task-runs/{taskRunId}/artifacts/{artifactId}
```

inventory link 是一次可尝试读取的 capability，不替代读取时的 scope、size 和
SHA-256 校验。如果读取把 artifact 闭合为 `missing` 或 `corrupt`，后续 detail、
history 和 inventory 会保留失败事实并移除可读 link。

## 前端严格合同

### History 与 inventory

`entities/benchmark-experiment` 负责 history item/page、history API/query，以及
Experiment detail 的可选 artifact-inventory link。

`entities/benchmark-report` 负责：

- Experiment artifact inventory parser/API/query；
- `benchmark_experiment_report` schema `1.0` parser；
- `benchmark_run_report` schema `1.0` parser；
- bounded report loader；
- Core causal reference 到同 scope readable inventory item 的唯一匹配。

所有 link 都必须是精确的 same-service scope。一个看似安全但含有其他
Experiment、TaskRun 或 artifact identity 的 `/studio/` link 也会被拒绝。

### Core Experiment report

前端保留 Core JSON 的权威性，只把 `snake_case` 映射为 typed `camelCase` model。
严格校验包括：

- exact kind、schema version 和字段集合；
- PASS/FAIL/INVALID/SKIPPED 非负整数；
- `eligibleCount = pass + fail`；
- rate/Wilson interval 位于 `[0, 1]` 且上下界有序；
- run summary、Agent metric 和 Agent pair 唯一性；
- `matchedCount = leftWins + rightWins + ties`；
- schema 1.0 固定 `significanceClaimed = false`；
- Experiment/TaskRun/Agent/task/repeat identity 一致。

浏览器不会重算 outcome、micro/macro、Wilson interval、paired matching、
Evaluation aggregation 或 significance。

### TaskRun report 与 Evaluation Tree

Experiment report 中的 `report_ref` 只是 bounded causal identity，不是 URL。前端
必须在同一 Experiment/TaskRun inventory 中找到恰好一个 readable
`task_report`，再跟随该 item 的 content link。

TaskRun report parser 保留：

- Agent status 与 Benchmark outcome 两条独立事实轴；
- TaskRun、Agent、task、repeat 和 canonical identities；
- lifecycle stages、usage、evaluator result 和 evidence；
- Evaluation Tree 的 status、score、short-circuit 与 `true`/`false`/`null`
  三态判断。

递归深度上限为 32，总节点上限为 2000；文本、数组成员和数字也有明确边界。超过
2 MiB 的声明或实际 report body 会在 JSON 解析前失败。

## 副作用与安全边界

history 和 inventory 查询：

- 不解析 device profile；
- 不构造 device、plugin、model 或 Runtime component；
- 不唤醒 scheduler/worker；
- 不进入 Monitor SSE session；
- 不读取或缓存 artifact body；
- 不返回 SQLite row、storage reference、宿主路径或 bundle member path。

只有用户或后续页面显式跟随 readable content link 时，才读取一个 report body。
report bytes 不进入 Zustand，server state 由可重建的 TanStack Query key 管理。

## 关键设计取舍

- 选择 compact history projection，而不是分页复制完整 immutable definition；
- 选择 keyset cursor，而不是会被新插入记录扰动的 offset；
- 选择 committed descriptor metadata，而不是目录扫描；
- 选择 Core 原始报告 + 前端 strict adapter，而不是后端再生成一套可能漂移的
  Studio 报告；
- 选择 causal reference 与 inventory capability 连接，而不是从文件名拼接 URL；
- 选择失败关闭矛盾文档，而不是在浏览器修正或重新计算正式统计；
- 复用 schema 6，没有为了尚未测得的性能问题增加 denormalized table 或迁移。

代价是未来 Core report 增加版本时必须显式新增 parser；history filter 和大规模
索引也留到有真实需求与测量证据后处理。

## 验证证据

### 后端与回归

```bash
.venv/bin/python -m pytest -q \
  tests/studio/test_benchmark_reporting_resource.py \
  tests/studio/test_benchmark_publication_replay.py \
  tests/studio/test_benchmark_startup_recovery.py \
  tests/studio/test_benchmark_event_stream.py \
  tests/studio/test_benchmark_experiment_resource.py
```

预期：`89 passed`。其中 reporting-resource focused tests 为 `6 passed`，覆盖
tie ordering、翻页期间插入、非法/cross-scope cursor、compact snapshot projection、
hidden aggregation、可读/不可读 link、unknown Experiment、integrity closure 和
HTTP envelope。

### 前端

```bash
cd studio
npm test
npm run smoke:benchmark-monitor
npm run typecheck
npm run build
```

预期：

- `33` 个 Vitest 文件、`121` 个 tests 通过；
- no-device fixture 在 `127.0.0.1:8765` 启动，并能返回预设 Monitor resource；
- TypeScript project build 通过；
- Vite production build 成功；当前仍有大于 500 kB 的 chunk warning。

`smoke:benchmark-monitor` 是持续运行的手工 fixture，需要在检查后用
`Ctrl-C` 停止。它证明无需设备的资源消费环境，不是 5.4B 报告页验收。

### Clean wheel

本轮构建并安装了：

```text
zhixing-0.1.0-py3-none-any.whl
```

隔离探针确认 `zhixing` 来自临时环境的 `site-packages`，不是源码树；在没有设备
配置的环境中读取到：

```text
history items       = 1
visible artifacts   = 15
hidden artifacts    = 0
report kind         = benchmark_experiment_report
report schema       = 1.0
```

探针还通过 managed resolver 实际打开并解析了已有 Experiment report，而不只是
检查 import 或方法存在。

### Evidence 边界

- 单 Agent/single Task/single repeat 报告来自当前 Stage 5 Worker + fake-device
  publication fixture；
- synthetic multi-Agent document 只验证 parser/cardinality/统计合同；
- 本 Change 没有执行新的真实 Android Benchmark；
- 测试不证明大规模 history 性能、任意未来 report schema、统计显著性或通用 Agent
  能力。

## 后续顺序

5.4A 完成后，固定下一步是：

1. 5.4B `implement-studio-benchmark-report-view-5-4b`：实现单 Experiment
   Report、TaskRun 选择和 Evaluation Tree；
2. 5.4C `implement-studio-benchmark-comparison-metrics-5-4c`：展示 Core 已给出的
   metrics、Wilson、comparison 和 fairness；
3. 原 5.4D 已在后续前置调研中拆为：
   - 5.4D-1 `implement-studio-benchmark-history-5-4d1`：History 与后端精确筛选；
   - 5.4D-2 `implement-studio-benchmark-evidence-viewer-5-4d2`：scoped
     evidence viewer；
   - 5.4D-3 `implement-studio-benchmark-export-5-4d3`：
     report/trajectory/bundle export。

多 Agent/multi-Task/repeat 调度扩展、PostgreSQL、retention/delete、checkpoint
resume 和真实 Android 验收仍不属于 5.4A–C 与 5.4D-1/2/3 的默认范围。

## 30–60 秒面试说明

“Benchmark 后端已经能生成正式报告和证据，但前端如果没有资源边界，就只能猜文件
路径或消费松散 JSON。我在 Studio service 上增加了 checksummed keyset history 和
Experiment-scoped metadata-only artifact inventory，并让可读内容只通过精确 scoped
link 暴露。前端再用独立 entity 严格解析 Core schema 1.0 报告，校验 denominator、
Wilson interval、comparison cardinality 和最多 32 层/2000 节点的 Evaluation Tree，
但不重算任何正式统计。验证覆盖 89 个相关后端回归、121 个前端测试、生产构建和
clean-wheel 的真实 report 读取。当前只完成资源层，报告页面和真实多 Agent 证据仍
是后续工作。”

## 常见追问

1. 为什么 history 不返回完整 Experiment？
   - 完整 definition 含 AgentGraph、Plan 和 Protocol，体积大且不适合列表；detail
     仍可沿 self link 查询。
2. 为什么 `report_ref` 不能直接当下载路径？
   - 它是 Core 的 causal identity；只有 inventory 的 scoped link 才是 HTTP
     capability，可避免路径推断和跨 Experiment 访问。
3. 为什么前端校验统计却不重算？
   - 校验用于拒绝内部矛盾；正式统计仍由 Benchmark Core 产生，避免形成竞争性事实源。
4. clean-wheel 证明了什么？
   - 证明安装产物包含新 repository/resource 代码，且无设备配置可以读取历史、
     metadata 和受管报告；它不证明真实 Android 执行或大规模性能。

## 贡献边界

- 用户确定了 Stage 5.4 的目标、5.4A–D 拆分、先资源后页面以及必须永久记录和如实
  区分 synthetic/runtime evidence 的要求。
- Coding Agent 完成了代码调查、OpenSpec artifact、后端/前端实现、测试与
  clean-wheel 命令执行，并依据实际输出更新本文；没有把计划能力描述成已完成。
