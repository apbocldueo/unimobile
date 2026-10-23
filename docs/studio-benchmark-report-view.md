# Studio Benchmark Report View（Stage 5.4B）

本文记录 `implement-studio-benchmark-report-view-5-4b` 已验证的实现、身份桥接、
状态边界、前端交互、验证证据和后续交接。Stage 5.4 的统计、历史与导出边界仍以
[Studio Stage 5.4 Benchmark Reporting 路线](studio-benchmark-reporting-roadmap.md)
为准；5.4A 的后端与 DTO 起点见
[Studio Benchmark Reporting Resource](studio-benchmark-reporting-resource.md)。

截至 2026-07-30，5.4B 已实现并通过自动化测试和 no-device 浏览器验收。它没有
新增 Benchmark 计算、真实 Android 运行、多 Agent 比较、History 或 Export。

## 一句话结果

用户现在可以从已发布 report 的 Benchmark Monitor 进入
`/experiments/:experimentId/report`，按稳定计划顺序选择 TaskRun，分别审阅
service lifecycle、Agent status、Benchmark outcome、canonical identities、
lifecycle stages、Evaluation Tree 与有界 evidence descriptor，并从明确可用的
TaskRun 进入原生 Replay。

页面只投影后端已经发布和校验的事实。它不会重新计算 outcome、Evaluation
aggregation 或统计指标，也不会把 Evaluation Tree 描述成自动根因诊断。

## 解决的 Agent 工程问题

5.4A 已经提供严格 Core report parser、Experiment artifact inventory 和受控内容
读取，但仍缺少一条可重建的产品路径：

```text
before
Monitor / managed reports / native Replay
  └─ 各资源存在，但用户没有单 Experiment 报告审阅工作台

after
authoritative Experiment + TaskRuns
  ├─ explicit Experiment report link
  ├─ bounded Experiment artifact inventory
  ├─ strict Core Experiment report
  ├─ selected Studio TaskRun
  ├─ exact scoped TaskRun report descriptor/content
  └─ explicit native Replay link
            ↓
    reconstructable Report workbench
```

涉及的前端层次为：

```text
app/routes
    ↓
pages/experiment-report
    ↓
widgets/benchmark-report-workbench
    ↓
features/benchmark-reporting
    ↓
entities/benchmark-report + entities/benchmark-experiment
    ↓
shared/api + shared/lib
```

Monitor 的 SSE session、Benchmark Worker、Core publisher、SQLite schema 和设备边界
均未修改。

## 真实发布合同与身份桥接

### Studio 与 Core run identity 不相同

Studio TaskRun resource 使用稳定的 `taskRunId`，Core report 使用 32 位十六进制
`coreTaskRunId`。页面不能把二者展平为一个虚构 identity。

一个 TaskRun report 只有同时满足下列条件才可进入可用状态：

1. Core Experiment report 的 run summary 指向 `coreTaskRunId`；
2. 选中的 Studio TaskRun 的 `coreTaskRunId` 与 summary 相同；
3. inventory descriptor 绑定同一 Experiment 和 Studio `taskRunId`；
4. descriptor 的 causal identity 精确等于 summary `reportRef`；
5. content link 是后端提供的同 scope link；
6. TaskRun report 内的 Experiment、Agent、Task、repeat、plan、protocol、
   AgentGraph 和 task-instance identity 与已选资源一致。

缺失、歧义或任一 identity 冲突都局部失败，页面不靠文件名、数组位置或标题猜测。

### Publisher-shaped report

Core schema `1.0` 仍使用 `snake_case`，前端 entity boundary 映射到 typed
`camelCase` model。5.4B 保持 5.4A 的：

- exact version、kind 和 unknown-field rejection；
- 2 MiB report body 上限；
- Evaluation 最多 32 层、2,000 个节点；
- outcome、rate、interval 和 cardinality 校验；
- same-service scoped link 校验。

Evaluation token 只接受 finite number、`null` 或精确的 `"<redacted>"`。安全导出
的 `"<redacted>"` 在 UI 中显示为 unavailable evidence，不被解释为 token 值、
score 或判定。

## 可重建查询与状态模型

Report route 是：

```text
/experiments/:experimentId/report
/experiments/:experimentId/report?taskRun=<studio-task-run-id>
```

刷新或深链时，页面从以下 durable resource 重建，不读取 Monitor 的 SSE event
session，也不依赖浏览器持久化 report state：

1. Experiment detail；
2. bounded TaskRun pages；
3. bounded opaque-cursor artifact inventory；
4. explicit Experiment report link；
5. 选中 Studio TaskRun 对应的 exact TaskRun report content link。

inventory 每页最多 100 条，总读取上限 2,000 条；重复 cursor、跨 Experiment
scope 或越界页会失败关闭。TaskRun 默认选择按 report 的稳定计划顺序决定，URL
中不存在或越权的 `taskRun` 不会被静默接受。

Experiment、TaskRun list、inventory、Experiment report、选中 TaskRun report、
Evaluation 和 Replay 保持独立状态与重试入口。一次失败后的 stale report 不会继续
伪装成当前事实。

### 状态矩阵

| 状态 | 页面行为 |
|---|---|
| `loading` | 显示当前组件正在读取，不投影旧内容 |
| `not_found` | 明确 Experiment 或 report 不存在 |
| `non_terminal` | 保留 Experiment identity，说明尚未 terminal |
| `pending` | 显示 publication pending，不主动猜 report URL |
| `not_produced` | 明确后端没有生成该组件 |
| `failed` | 显示 publication 失败并提供局部 retry |
| `missing` | 保留已验证 siblings，指出选中 artifact 缺失 |
| `corrupt` | 停止消费失败完整性校验的内容 |
| `compatibility` | 显示版本或字段合同不兼容 |
| `integrity` | 显示跨资源 identity/causal 冲突 |
| `available` | 展示严格解析并完成身份连接的内容 |
| `unavailable` | 对没有权威证据的局部事实明确置空 |

## 报告工作台

### Header 与导航

Report header 展示：

- Experiment identity 和 Package identity；
- lifecycle 与 publication availability；
- Benchmark plan 和 Experiment protocol identity；
- Back to Monitor；
- scoped Refresh。

Monitor 只有在 authoritative `reports` capability、`reportAvailability=available`
且 explicit report link 同时存在时才显示 `Open Report`。

### TaskRun rail 与 facts inspector

TaskRun rail 按 report 的 plan order 排列，选中项同步到 URL；每项展示 Agent、
Task、repeat、service lifecycle、Agent status 和 Benchmark outcome。

Inspector 始终把三条状态轴分开：

| 轴 | 权威来源 |
|---|---|
| Service lifecycle | Studio TaskRun resource |
| Agent status | Core/Runtime result |
| Benchmark outcome | Core Benchmark evaluation |

合法的 `Agent success + Benchmark fail` 不会被合成一个“失败”或“成功”。Inspector
还展示 Core run、AgentGraph、task instance 等 canonical identities，以及已经发布
的 lifecycle stages。

Replay 按钮只来自选中 Studio TaskRun 的 authoritative Replay availability、ID 和
link，并跳转到既有 `/runs/:replayId/replay`，Report 不创建第二套 Replay。

### Evaluation Tree

Evaluation Tree 使用 node `path` 作为稳定 identity，并要求全树唯一：

- 保留原始 child order；
- 展示 status、`true`/`false`/`null` pass、score、duration、reason；
- 展示 short-circuit 与 evaluator result；
- 只有展开的 descendants 才挂载到 DOM；
- 默认只展开能帮助定位首个非通过/异常分支的有界路径；
- leaf evidence 只展示 kind、artifact reference presence 和安全结构摘要；
- 不打开 artifact body，不构造下载 URL，不暴露 secret 或宿主路径。

Tree 的用途是审计与人工 failure localization，不是自动失败诊断。

## no-device fixture 与人工验收

`studio/scripts/benchmark-monitor-smoke-fixture.mjs` 提供 publisher-shaped 场景：

- report ready；
- report pending；
- report failed；
- report corrupt；
- TaskRun report missing；
- null Evaluation；
- authoritative Replay resource；
- exact `"<redacted>"` token。

启动：

```bash
cd studio
node scripts/benchmark-monitor-smoke-fixture.mjs
npm run dev -- --host 127.0.0.1
```

浏览器人工路径：

```text
Monitor
  → Open Report
  → select TaskRun
  → URL gains ?taskRun=<studio-task-run-id>
  → inspect/collapse/expand Evaluation
  → Open authoritative Replay
  → OFFLINE REPLAY
```

2026-07-30 实际观察：

- Report ready 显示 1 个 TaskRun、terminal/service、success/Agent、pass/Benchmark；
- `fixture-leaf` 可展开，折叠根节点后 descendant 不再挂载，再展开后恢复；
- exact redacted token 显示为 `token unavailable (safely redacted)`；
- TaskRun 选择写入 Studio TaskRun URL identity；
- Replay 进入 `OFFLINE REPLAY`，显示 `partial`，并明确没有截图、UI 或真实设备证据；
- pending 保留 Experiment identity，并显示 publication pending；
- corrupt 显示完整性失败，不展示旧 report；
- missing TaskRun report 保留 Experiment summary 与三轴事实，仅局部 Evaluation 缺失；
- null Evaluation 明确显示 `This TaskRun report has no Evaluation Tree`，仍保留
  stages 和 Replay；
- 浏览器控制台没有 error。

该 journey 是 deterministic no-device fixture 验收，不是 Android trajectory、
真实性能或多 Agent 实验证据。

## 自动化验证证据

### Frontend

```bash
cd studio
npm test
npm run typecheck
npm run lint
npm run build
node --check scripts/benchmark-monitor-smoke-fixture.mjs
```

实际结果：

- `41` 个 Vitest 文件、`145` 个 tests 通过；
- TypeScript checking 通过；
- ESLint 与 FSD public-import checks 通过；
- Vite production build 成功，`556` modules transformed；
- fixture JavaScript syntax check 通过；
- build 仍有既有的 JavaScript chunk 大于 500 kB warning。

测试覆盖 publisher shape、Studio/Core identity 冲突、2 MiB/2,000-node bounds、
deterministic selection、所有跨资源 identity mismatch、opaque cursor bounds、
partial failure、stale rejection、Evaluation tri-state/collapse/redaction、Monitor
和 Replay route handoff。

### Focused backend regression

```bash
.venv/bin/python -m pytest -q \
  tests/studio/test_benchmark_reporting_resource.py
```

实际结果：`6 passed`。这确认 5.4B 没有改变既有 reporting HTTP/repository 合同。

## 关键设计取舍

- 选择跨资源 strict projection，而不是页面直接拼接松散 JSON；
- 选择 URL-owned Studio TaskRun selection，而不是只存在 React state 中；
- 选择 query reconstruction，而不是复用 Monitor event session；
- 选择独立组件失败状态，而不是一个请求失败清空全部报告；
- 选择 path-keyed lazy Evaluation Tree，而不是 array-index key 或一次挂载全部节点；
- 选择 explicit Replay handoff，而不是从 report reference 猜 Replay identity；
- 选择安全 evidence descriptor，而不是在 5.4B 提前实现 viewer/download。

代价是资源 round trip 多于扁平大响应，Core 增加 report version 时也必须显式增加
adapter；这些成本换取了可审计身份、刷新可恢复性与 fail-closed 边界。

## 已知限制与后续交接

- 当前 Stage 5 Worker 的真实产品切片仍是 single Agent/single Task/single repeat；
- 5.4B 当时不展示 agent metrics、micro/macro、Wilson interval、comparison 或
  fairness；这些已由 5.4C 增加；
- 不包含 Experiment History、artifact viewer、report/trajectory/bundle export；
- 不包含 retention/delete、PostgreSQL、对象存储或真实 Android 验收；
- no-device Replay 只有结构证据，没有截图、UI XML、activation 或 device action；
- Evaluation Tree 支持人工定位，不能自动声明根因；
- production bundle 仍有既有大 chunk warning。

该文档完成时的下一步是
`implement-studio-benchmark-comparison-metrics-5-4c`；该 Change 现已实现。它只
投影后端已经给出的 counts、eligible denominator、micro/macro、duration
statistics、Wilson interval、paired/unpaired comparison、fairness warning 和
`significance_claimed`，没有在浏览器重新计算正式指标，也没有把 synthetic
fixture 说成真实多 Agent 证据。验证详情见
[Studio Benchmark Comparison and Metrics](studio-benchmark-comparison-metrics.md)。
原 5.4D 已在后续前置调研中永久拆分；5.4D-1
`implement-studio-benchmark-history-5-4d1` 已实现，当前下一步固定为
`implement-studio-benchmark-evidence-viewer-5-4d2`，之后是
`implement-studio-benchmark-export-5-4d3`。
