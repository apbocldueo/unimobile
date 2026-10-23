# Studio Stage 5.4：Benchmark Reporting 产品与实施路线

本文固化 `implement-studio-benchmark-reporting-5-4` 的目的、当前后端基础、产品
形态、事实边界和进一步拆分。它是 Stage 5 总路线的专题补充；每个子 Change 的
requirement、设计、任务和验收矩阵仍应进入对应 OpenSpec artifact。

截至 2026-07-30，Stage 5.4A reporting resource、5.4B single-Experiment
Report View、5.4C comparison/metrics、5.4D-1 filtered durable History 与
5.4D-2 Evidence Viewer、5.4D-3 Export 已实现；Stage 5.3 已完成 durable
Experiment create、Monitor、event recovery、accepted-only Cancel 和 terminal
Replay handoff。原 5.4D history/evidence/export 已永久拆为 5.4D-1、5.4D-2 与
5.4D-3 三个独立 Change，并已按顺序完成。Stage 5.4 已收口，当前下一步固定为
Stage 5.5 Benchmark authoring。Stage 5.4 不重新实现既有 Monitor 或 Replay
行为。

## 一句话目标

将后端已经持久化和校验的 Benchmark result、report、Evaluation Tree、
trajectory、artifact 与 bundle，产品化为一个**可解释、可审阅、可比较、可导出**
的研究实验报告工作台。

Stage 5.3 回答：

> 实验现在运行到哪里？

Stage 5.4 回答：

> 实验最终表现如何，结论来自什么证据，结果能否被别人复核？

## 完成形态

目标路径：

```text
/experiments/:experimentId
        ↓ terminal / report available
/experiments/:experimentId/report
        ├─ Experiment summary
        ├─ service lifecycle
        ├─ Agent status
        ├─ Benchmark outcome
        ├─ TaskRun result
        ├─ Evaluation Tree + leaf evidence
        ├─ agent metrics / uncertainty
        ├─ paired comparison / fairness warnings
        └─ report / trajectory / artifact / bundle export

Experiment history
        ├─ paginated durable Experiments
        ├─ filter by lifecycle / Agent / Benchmark
        └─ reopen Monitor / Report / Replay
```

报告页不是前端统计计算器。正式 outcome、denominator、micro/macro、Wilson、
paired matching、fairness warning 和 Evaluation aggregation 都来自后端报告；
浏览器只做严格解析、事实投影和安全交互。

## 已验证的后端起点

### 已经存在

Benchmark Core 与 Stage 5.2C-2 已验证：

- `BenchmarkTaskResult` 与 run report；
- `BenchmarkExperimentReport`；
- PASS/FAIL/INVALID/SKIPPED 分离；
- Agent status 与 Benchmark outcome 分离；
- AND/OR/SEQUENCE/THRESHOLD/WEIGHTED Evaluation Tree；
- leaf evaluator evidence；
- per-Agent counts、eligible denominator、micro/macro；
- duration mean/median/sample variance；
- 95% Wilson interval；
- paired/unpaired comparison、matched/unmatched、wins/ties；
- fairness warning 与固定 `significance_claimed=false`；
- managed report、trajectory、bundle 与 artifact；
- read-time size/hash/scope integrity closure；
- TaskRun native Replay。

已开放的主要 HTTP 入口：

```text
GET /studio/benchmark-experiments/{experimentId}
GET /studio/benchmark-experiments/{experimentId}/task-runs
GET /studio/benchmark-experiments/{experimentId}/task-runs/{taskRunId}
GET /studio/benchmark-experiments/{experimentId}/report
GET /studio/benchmark-experiments/{experimentId}/bundle
GET /studio/benchmark-experiments/{experimentId}/artifacts/{artifactId}
GET /studio/benchmark-experiments/{experimentId}/task-runs/{taskRunId}/artifacts
GET /studio/benchmark-experiments/{experimentId}/task-runs/{taskRunId}/artifacts/{artifactId}
GET /studio/replays/{replayId}
```

Report endpoint 当前返回正式 Core JSON document，字段使用 Core
`snake_case`；Experiment/TaskRun resource 使用 Studio `camelCase`。5.4 必须在
entity boundary 显式适配，不能让页面直接消费松散字典。

### Stage 5.4 的已验证收口边界

5.4A 已增加 paginated `GET /studio/benchmark-experiments`、Experiment 级
artifact inventory、strict report DTO 和有界 Evaluation Tree parser。5.4B 已增加
单 Experiment Report route、可重建查询、TaskRun 选择、Evaluation Tree 与 Replay
handoff。5.4C 已增加正式 outcome/per-Agent metric、pairwise comparison、fairness
warning 和 significance boundary 的严格页面投影。5.4D-1 已增加 filter-bound
cursor v2、lifecycle/Catalog/Agent/accepted time 后端筛选和可重建
`/experiments` React History。5.4D-2 已增加 exact causal resolver、strict
content capability、bounded stream、media allowlist 与 disposable Viewer。
5.4D-3 已增加四类现有 managed content capability 的共享 GET/HEAD resolver、
安全 attachment/CORS headers、strict manifest、closed-inventory material
projection、refresh + exact HEAD preparation、per-artifact single-flight 和
browser-owned 大文件 handoff。

因此 Stage 5.4 已形成 History → Report → Viewer → Replay → Export 闭环，同时
继续消费 5.4A–C 的受控资源与正式统计事实。它没有猜测 managed 文件名、拼接宿主
路径、扫描 bundle、在浏览器重算正式统计，也没有把浏览器 handoff 写成下载完成。

## 事实与展示边界

### 三条状态轴

界面必须并列展示，不能合并为一个成功/失败：

| 事实 | 示例 | 所有者 |
|---|---|---|
| Service lifecycle | terminal / interrupted / cancelled | Studio Experiment resource |
| Agent status | success / failure / step_limit | Agent Runtime result |
| Benchmark outcome | PASS / FAIL / INVALID / SKIPPED | Benchmark evaluation/report |

合法组合包括：

```text
Agent status = success
Benchmark outcome = fail
```

表示 Agent 正常结束，但没有满足任务判定。

### 分母与不确定性

- PASS 与 FAIL 进入 eligible denominator；
- INVALID 与 SKIPPED 单独计数；
- micro/macro、Wilson interval 和 duration statistics 来自后端；
- `null` 不是 0，缺少样本时显示 unavailable；
- 小样本结果只能作为描述性事实；
- UI 必须展示 `significance_claimed`，不得用排名、颜色或文案暗示后端没有声明的
  显著性。

### Comparison

只有 report 明确提供 comparison 时才展示：

- left/right Agent identity；
- paired；
- matched count；
- unmatched eligible count；
- left wins / right wins / ties；
- fairness warnings；
- significance claimed。

当前 Studio Worker 第一条执行切片仍限制一个 Agent、一个 Task、一个 repeat。
因此 5.4 可以实现严格 comparison 合同和 fixture UI，但不得宣称当前 Studio 已
真实执行多 Agent comparison。真实产品路径要等后续 scheduler 扩展并重新验收。

### Evidence 与导出

- artifact 只能从 scoped opaque identity 和后端 resource link 打开；
- readable artifact 必须保留 availability、content type、size、hash、provenance
  与 causal identity；
- hidden、missing、corrupt、failed、not_produced 必须分别展示；
- Prompt、secret、raw serial、宿主绝对路径和 hidden evidence 不得进入普通 viewer；
- report、trajectory 和 bundle 是不同组件，某一组件失败不得抹掉其他已验证组件；
- bundle 下载不能被描述为 bundle 校验成功；校验状态必须来自后端 verifier 或明确
  的客户端校验流程。

## 前端架构方向

继续遵守：

```text
app/routes
    ↓
pages/experiment-report + pages/experiment-history
    ↓
widgets/benchmark-report-workbench
    ↓
features/benchmark-reporting
    ↓
entities/benchmark-report + existing benchmark-experiment/artifact
    ↓
shared/api + shared/lib
```

约束：

- report DTO/parser/API 属于 entity，不导入 React Router、page 或 widget；
- Evaluation Tree projection、metric formatting、comparison selection 和 export
  intent 属于 feature；
- page 负责 route/loading/not-found/partial/failure composition；
- artifact bytes 不进入 Zustand 或 TanStack Query 长期缓存；
- 不把 reporting state 写回 5.3 event session；
- 不向旧的无 owner 全局 buckets 新增代码。

## 永久拆分顺序

### 5.4A `implement-studio-benchmark-reporting-resource-5-4a`

先建立可消费且可测试的 reporting resource boundary：

- 定义 strict versioned Experiment report、run summary、agent metric、
  comparison、fairness warning、Evaluation Tree、artifact inventory 与 history
  summary DTO；
- 显式适配 Core report `snake_case` 与 Studio resource `camelCase`；
- 拒绝 unsupported version/kind、非法 denominator、越界 rate/interval、
  comparison cardinality、跨 Experiment/TaskRun identity 和 unsafe link；
- 增加 paginated Experiment history query；
- 增加 Experiment 级 artifact inventory，以 opaque descriptor 暴露 report、
  trajectory、bundle 和允许的 evidence；
- 复用现有 managed resolver，不新增直接文件路径；
- 添加 frontend entity API/Query 和 backend HTTP/repository contract tests；
- 证明 metadata query 无设备副作用，不读取 artifact body。

完成后达到：

> 前端能够安全、严格、可分页地获取“有哪些 Experiment、正式 report 是什么、
> 有哪些可用 artifact”，但还没有完整报告页面。

该目标已实现：后端增加 newest-first checksummed keyset history 与
Experiment-bound metadata-only artifact inventory；前端增加 strict history、
inventory、Core Experiment/TaskRun report 和 bounded Evaluation Tree entity。
相关后端回归 `89 passed`，前端 `121 passed`，typecheck/build 和 clean-wheel
无设备读取均通过。具体合同、复验命令与证据限制见
[Studio Benchmark Reporting Resource](studio-benchmark-reporting-resource.md)。
该条是 5.4A 完成时的历史交接；5.4B、5.4C 与 5.4D-1/2/3 均已实现，
当前下一步固定为 Stage 5.5。

### 5.4B `implement-studio-benchmark-report-view-5-4b`

实现 `/experiments/:experimentId/report` 的单 Experiment 报告主体：

- loading、not found、not terminal、report pending/failed/corrupt/available；
- Experiment identity、definition identity 和 publication status；
- service lifecycle、Agent status、Benchmark outcome 三轴；
- TaskRun/run summary 列表和稳定选择；
- Evaluation Tree 递归展示、short-circuit/status/score；
- leaf evidence descriptor 与 Replay handoff；
- partial component failure 不阻断其余已验证事实；
- refresh/deep-link reconstruction。

完成后达到：

> 单 Agent/单 Task 的真实 Stage 5.2 report 已经能被用户解释和审阅。

该目标已实现：`/experiments/:experimentId/report` 从 durable Experiment、
TaskRuns、bounded inventory 和 explicit report links 独立重建；Studio TaskRun 与
Core run identity 通过 `coreTaskRunId` 和 exact causal reference 连接；页面提供
稳定 TaskRun URL 选择、service/Agent/Benchmark 三轴、canonical identities、
lazy accessible Evaluation Tree、局部 failure/retry 和原生 Replay handoff。
no-device 浏览器 journey 已覆盖 ready、pending、corrupt、missing TaskRun report、
null Evaluation 与 Replay；前端 `145 passed`、typecheck、lint、build 通过，focused
backend reporting regression `6 passed`。这不是 Android 或 multi-Agent 证据。
具体实现与复验命令见
[Studio Benchmark Report View](studio-benchmark-report-view.md)。下一步固定为 5.4C。
该“下一步”是 5.4B 完成时的历史交接；5.4C 已实现。

### 5.4C `implement-studio-benchmark-comparison-metrics-5-4c`

增加指标、比较和公平性投影：

- counts 与 eligible denominator；
- micro/macro；
- duration mean/median/sample variance；
- Wilson interval；
- paired/unpaired、matched/unmatched、wins/ties；
- fairness warning 与 significance boundary；
- missing/null/zero、小样本、INVALID/SKIPPED 的视觉与文案约束；
- 不在浏览器重新计算正式指标；
- synthetic multi-Agent fixture 验证 UI，证据标记为 fixture；
- 只有在后续真实 Studio multi-Agent execution 完成后，才能增加真实 comparison
  产品声明。

完成后达到：

> 页面可以诚实展示后端给出的统计与比较，但不会把描述性结果包装成显著性结论。

该目标已实现：页面从 strict schema-1.0 Experiment report 纯投影四类 outcome、
per-Agent eligible denominator、micro/macro、duration、sample variance、Wilson、
usage coverage、pairwise matching/wins/ties 与 fairness warning；aggregate state
只依赖 Experiment resource 和正式 Experiment report，不受当前 TaskRun、
Evaluation 或 Replay 局部失败影响。指标与比较使用独立有界本地分页，null、zero、
zero-eligible、小样本、partial/no matching 和 unknown warning 均有确定性展示；
significance boundary 折叠后仍可见。前端完整回归 43 files、158 tests，focused
后端 reporting 15 tests，typecheck、lint、build 和 no-device browser journey
通过。合成三 Agent 数据只证明 presentation contract，不证明当前 Worker 已支持
multi-Agent 执行。具体实现、复验命令与限制见
[Studio Benchmark Comparison and Metrics](studio-benchmark-comparison-metrics.md)。
该文档完成时的下一步是 5.4D-1；5.4D-1/2/3 现均已实现，当前下一步
固定为 Stage 5.5。

### 5.4D：History、Evidence 与 Export 闭环

原计划名 `implement-studio-benchmark-history-export-5-4d` 同时跨越三类风险：

- History 需要扩展后端 repository/HTTP/query/cursor 合同，否则前端只能错误地
  筛选当前页；
- Evidence Viewer 需要维护 causal identity、scope、content type、size 和
  availability 安全边界；
- Export 需要处理二进制/大文件传输、重复点击、错误恢复、manifest 和
  excluded-evidence 提示。

此外，现有 Experiment history 只提供 aggregate `replayAvailability`，不提供
Experiment 级 Replay link；权威 Replay link 属于具体 TaskRun。将三者一次实现会
迫使页面在合同尚未稳定时猜测 Replay、文件路径或下载完成状态。因此原 5.4D
永久拆成以下三个 Change，并严格按顺序实施。

#### 5.4D-1 `implement-studio-benchmark-history-5-4d1`

先完成可重建、可筛选的 durable Experiment History。

后端范围：

- 保留 5.4A newest-first `(acceptedAt, experimentId)` keyset order 和有界 page；
- 在 repository、service 与 HTTP boundary 增加 lifecycle、Benchmark immutable
  source identity、Agent identity 和 accepted time range 的精确筛选；
- Benchmark 首版筛选以 durable `catalogEntryId` 为请求 identity，
  `packageIdentity` 继续用于显示和证据核对，不做模糊文件名匹配；
- Agent 首版筛选以 `agentId` 为请求 identity，revision 仍在结果中展示；如
  OpenSpec proposal 证明 revision filter 必需，再显式加入而非复用自由文本；
- 时间范围必须声明 inclusive lower bound 与 exclusive upper bound，拒绝反向、
  越界或非法时间；
- continuation cursor 必须绑定规范化筛选、排序和边界；篡改、跨筛选复用和旧
  query 复用必须失败，不能悄悄返回另一组数据；
- 无筛选的既有 history 调用继续可用，不增加设备、插件、secret 或 artifact body
  副作用。

前端范围：

- 新增 `/experiments` route 和 `pages/experiment-history`，归属 Benchmark 模块；
- 保留 `/history` 作为普通 Studio Run/Replay history，不把两类资源混成一张表；
- filter、cursor/page navigation 和选中项由 URL/query state 拥有，刷新和 deep
  link 能重建同一查询；
- 每行展示 Experiment、lifecycle、Benchmark source、Agent/revision、时间、
  planned TaskRun count 和独立 evidence availability；
- 只使用 history item 的 `self`、`taskRuns`、`report`、`artifacts`、`bundle`
  等权威 link 进入 Monitor 或 Report；
- `replayAvailability=available` 只能提示存在 Replay。真正进入 Replay 必须先
  解析具体 TaskRun 并使用 `taskRun.links.replay`；不得根据 Experiment 或
  TaskRun identity 拼路径；
- 若未来要求 history row 一步直达 Replay，必须先增加“恰好一个可用 Replay”
  的显式 typed handoff 合同；多 TaskRun 时不得选择任意一个 Replay。

完成后达到：

> 研究者可以从全量 durable Experiment 中稳定筛选并重新进入 Monitor 或 Report，
> 但 History 不伪造证据链接，也不承担证据渲染和文件导出。

最低验收：

- repository/HTTP 测试覆盖单筛选、组合筛选、同 timestamp tie、空页、翻页期间
  新增记录、cursor tamper 和 cross-filter cursor；
- strict frontend parser/query/route 测试覆盖 URL 重建、分页、空状态、局部
  availability 和无权威 Replay link；
- no-device 浏览器 fixture 覆盖筛选、刷新、Monitor/Report 往返；
- 验证 history metadata query 不读取 artifact body、不连接设备。

该目标已实现：后端增加 strict immutable History filter、schema 7 index-only
migration、固定参数化 SQL 与 checksummed filter-bound cursor v2；legacy cursor
v1 只对无筛选查询兼容。前端增加 exact `/experiments`、URL-owned filter/cursor、
durable deleted identity、五条独立 availability、Monitor/Report authoritative
handoff 和同 URL retry；Experiment-level Replay 只提示，不构造 action。相关后端
回归 `119 passed`，前端 `47 files / 168 tests`、typecheck、lint、build、独立
clean-wheel schema 6→7 和 no-device 真实浏览器 journey 均通过。具体合同、复验
命令与 lifecycle pagination 限制见
[Studio Benchmark Experiment History](studio-benchmark-history.md)。该句是
5.4D-1 完成时的历史交接；5.4D-2/3 现已实现，当前下一步固定为 Stage 5.5。

#### 5.4D-2 `implement-studio-benchmark-evidence-viewer-5-4d2`

在已有 Report 与 Experiment-bound inventory 上完成安全 Evidence Viewer。

范围：

- 从 Evaluation leaf 的 causal `artifactRef` 在 bounded Experiment inventory
  中做 exact、same-Experiment、same-TaskRun 的唯一解析；
- 只打开 descriptor 返回的 scoped `links.content`，不得根据 artifact id、kind、
  文件名、storage ref 或宿主路径构造 URL；
- JSON、NDJSON、XML 与纯文本使用独立有界 byte/text loader，并始终转义显示；
- PNG 只有在 content type、size 和 availability 均允许时预览；
- ZIP 和未知/不可预览的 allowlisted content type 只提供下载意图，不以内嵌方式
  执行或渲染；
- artifact bytes 不进入 Zustand，也不进入 TanStack Query 长期缓存；关闭 viewer
  后应允许释放；
- `hidden` 只显示 aggregate hidden count；`redacted`、`truncated`、`excluded`、
  `missing`、`corrupt`、`failed`、`not_produced`、`oversized` 和 content-type
  mismatch 分别展示，不折叠成一个通用 error；
- report、trajectory、bundle 和 leaf evidence 保持独立 component state，一个
  artifact 的失败不得覆盖其他已验证事实；
- 不显示 Prompt、secret、raw serial、绝对路径、storage ref 或后端原始异常。

完成后达到：

> 用户可以从 Evaluation Tree 定位到后端授权的具体证据并安全审阅，同时能明确
> 区分“没有捕获、策略排除、不可见、已损坏、过大”和“可读取”。

最低验收：

- strict inventory/content contract、重复 causal reference、跨 scope 和 unsafe
  link 测试；
- 文本上限、PNG、ZIP download-only、XML escape、MIME mismatch、hash/size
  read-time closure 和释放测试；
- Report route 覆盖 available/hidden/missing/corrupt/oversized/partial；
- security canary 证明路径、secret、Prompt 和 hidden evidence 不泄漏。

该目标已实现：Evaluation leaf 只通过 same-Experiment、same-Studio-TaskRun、
exact causal identity 在 closed bounded inventory 中唯一解析，并只消费 strict
`links.content` capability；通用 bounded stream 在分配前后验证 descriptor
size、policy、MIME、`Content-Length` 和实际长度。JSON/NDJSON/XML/text 仅转义
显示，PNG 校验 signature/IHDR/dimensions，ZIP 只提供 download handoff。Viewer
selection、abort 和 Blob URL 由 React local state 独占，换 scope/TaskRun、
close 与 unmount 均可销毁；backend resolver 的 read-time missing/corrupt
closure 与安全响应头也有回归证据。前端 `52 files / 214 tests`、相关后端
`129 passed`、typecheck、lint、build、fixture syntax 与 no-device
History→Report→Viewer→Replay 浏览器 journey 均通过。具体合同、复验命令和限制
见 [Studio Benchmark Evidence Viewer](studio-benchmark-evidence-viewer.md)。

#### 5.4D-3 `implement-studio-benchmark-export-5-4d3`

最后完成正式材料导出和浏览器闭环。

范围：

- report、trajectory、bundle 和其他允许下载的 evidence 分别消费权威 scoped
  link 与独立 availability，不因一个组件失败禁用全部导出；
- 导出前通过 metadata control plane 刷新 descriptor/availability，并对同一
  artifact 建立单独 single-flight；重复点击不得并发准备同一下载；
- 小型预览继续走 bounded fetch；大文件下载通过浏览器直接消费 managed resolver
  link，避免 JavaScript 把后端允许的 128 MiB 级 artifact 长期保存在内存；
- UI 只能声明“下载请求已交给浏览器”，不能把点击或响应开始描述为“导出成功”；
- resolver 报告 missing/corrupt/failed 后，刷新 authoritative inventory、解除
  single-flight 并提供明确 retry；不得降级为直接文件系统读取；
- 显示 bundle identity、manifest member/hash 摘要和
  `studio-publication-manifest.json` 的 `excludedEvidence`；manifest 本身也必须
  通过 inventory/scoped link 获取，不能扫描 ZIP 推断；
- bundle 是 publication 阶段已生成的不可变正式材料，5.4D-3 不新增前端打包器、
  隐式 bundle regeneration 或新的导出状态机；
- 完成 fake/no-device 浏览器 journey：
  `History → Report → Evaluation evidence → Replay → Export`。

完成后达到：

> 研究者可以导出后端已经发布和验证的正式材料，并看见材料 identity、包含内容、
> 排除内容与独立失败状态；前端不把“开始下载”冒充“完整性验证成功”。

最低验收：

- 单项 single-flight、double click、retry、availability refresh 和 independent
  failure 测试；
- report/trajectory/bundle content disposition、content type、size/hash failure
  与 excluded-evidence 测试；
- no-device browser journey 覆盖 History、Report、Viewer、TaskRun Replay 和
  Export；
- packaging 受影响时执行 clean-wheel，验证安装后仍不依赖源码路径；
- 明确记录浏览器下载交接不是下载完成回执，也不是新的真实 Android 证据。

该目标已实现：backend 让 report、bundle、Experiment artifact 与 TaskRun
artifact 四类既有 exact capability 共用同一 managed resolver 和 GET/HEAD
response helper，HEAD 不返回 body，并保持 scope、availability、size/hash 与
missing/corrupt closure。成功响应使用安全 attachment filename、allowlisted
MIME、exact length、private no-store、nosniff 与显式 CORS expose headers。
前端从 closed bounded inventory 纯投影独立 export materials，严格解析
`studio-publication-manifest.json`，每个 artifact 以 refresh metadata + exact
HEAD 单独准备和 single-flight，再通过普通 anchor 交给浏览器；大 bundle 从未由
JavaScript 预取。完整 Studio `57 files / 254 tests`、typecheck、lint、build、
fixture syntax，相关后端 `129 passed`，独立 clean-wheel GET/HEAD/missing/corrupt
验收，以及 no-device History→Report→Viewer→Replay→Export 浏览器 journey 均
通过。具体实现、复验命令与限制见
[Studio Benchmark Export](studio-benchmark-export.md)。

5.4D-1/2/3 全部完成后达到：

> 研究者可以重新找到历史 Experiment、审阅证据并导出后端已经验证的正式材料。

## 为什么不做成一个大 Change

原始 `implement-studio-benchmark-reporting-5-4` 同时包含：

- 新后端 history/inventory resource；
- 两套命名风格的严格 DTO 适配；
- recursive Evaluation Tree；
- metrics/comparison/fairness；
- artifact security；
- history、report、Replay 与 export 路由；
- 浏览器和 clean-wheel 验收。

一次实现会让后端合同、事实投影、统计表达和文件安全难以独立审查，也容易在 UI
先行时通过路径猜测绕开 managed resolver。5.4A/5.4B/5.4C 的第一次拆分已经隔离
resource、Report 和统计事实；5.4D-1/2/3 的第二次拆分继续隔离查询/游标、
证据内容安全和大文件导出。每一步都拥有明确的可执行完成标准，失败时不会污染
后续层。

## 验收顺序

每个子 Change 至少验证：

1. strict parser/API contract；
2. backend focused HTTP/repository tests；
3. frontend unit/route tests；
4. typecheck、lint、build；
5. no-device browser fixture；
6. security canary；
7. 文档与 interview note。

涉及 packaging 的后端新模块还要做 clean-wheel 验证。只有 Stage 5.6 的受控真实
Android 验收可以产生新的真实设备产品证据。

## 非目标

5.4A–C 与 5.4D-1/2/3 不包含：

- 多 Task/repeats/multi-Agent scheduler 扩展；
- Benchmark Package authoring；
- 真实 Android Stage 5 验收；
- PostgreSQL、对象存储、quota、retention/delete；
- 自动失败诊断；
- 前端重算 Benchmark outcome 或统计指标；
- live device video、checkpoint resume 或节点 retry。

## 下一步

Stage 5.4 完成后的下一步固定为：

```text
implement-studio-benchmark-authoring-5-5
```

5.5 应在已验证的 Catalog/Composer、durable Experiment、Monitor、Report、
History、Viewer 与 Export 合同之上产品化 Benchmark Package authoring；它不得
回退为无类型 `pipeline: unknown[]`，也不得把多 Task/multi-Agent scheduler、
PostgreSQL、retention/delete 或真实 Android 验收夹带进 authoring。
