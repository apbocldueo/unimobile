# Studio Benchmark Comparison and Metrics

本文记录 Stage 5.4C
`implement-studio-benchmark-comparison-metrics-5-4c` 的已验证实现、事实边界、
验证证据和后续交接。Stage 5.4 的总体顺序与非目标仍以
[Studio Stage 5.4 Benchmark Reporting 路线](studio-benchmark-reporting-roadmap.md)
为准。

截至 2026-07-30，5.4C 已实现并验证。它证明 Studio 能严格展示正式
schema-1.0 Experiment report 中已有的指标、比较和公平性事实；合成多 Agent
fixture 只证明页面合同，不证明当前 Studio Worker 已支持真实多 Agent 执行。

## 目的与完成形态

5.4B 已经让用户看到单个 Experiment、TaskRun、Evaluation Tree 和 Replay，但
正式 Experiment report 中已有的聚合统计仍未进入页面。5.4C 解决的是：

> 如何让研究者读懂各 Agent 的样本、成功率、不确定性、耗时和成对比较，同时
> 不让浏览器重新计算 Benchmark 结论，也不把描述性小样本包装成显著性结论？

完成后的 `/experiments/:experimentId/report` 顺序为：

```text
durable Experiment resource
        +
strict schema-1.0 Experiment report
        ↓ identity check + pure projection
Experiment Results
        ├─ PASS / FAIL / INVALID / SKIPPED
        ├─ per-Agent eligible denominator
        ├─ micro / macro success
        ├─ duration mean / median / sample variance
        ├─ Wilson 95% interval
        ├─ usage coverage
        ├─ pairwise matched / unmatched / wins / ties
        ├─ fairness warning
        └─ always-visible descriptive-only boundary
        ↓
existing TaskRun rail → Evaluation Tree → verified facts
```

用户现在可以在同一 Report 页面审阅正式聚合结果，并切换 TaskRun 查看局部证据；
TaskRun 选择或局部报告失败不会改变或清空已经验证的 Experiment 聚合事实。

## Agent 问题与涉及层

问题不是“画一张成功率图”，而是跨四层保持统计语义和证据身份：

| 层 | 责任 |
|---|---|
| Benchmark Core | 产生正式 counts、denominator、metrics、comparison 和 warning |
| Studio entity | 严格解析 schema-1.0 report，并校验 Experiment/report identity |
| reporting feature | 做纯事实投影、格式化、分页和独立状态管理 |
| Report page/widget | 展示可访问表格、局部错误、TaskRun 证据和 Replay handoff |

`BenchmarkExperimentReport` 仍是唯一正式统计模型。5.4C 没有新增后端指标、第二套
report DTO 或新的 HTTP 请求。

## 执行流：之前与之后

### 之前

```text
Experiment resource ────────┐
TaskRun selection/query ────┼─→ Report workbench
TaskRun report/Evaluation ──┘

schema-1.0 aggregate metrics/comparisons
        └─ 已解析，但没有产品化展示
```

### 之后

```text
Experiment resource + strict Experiment report
        ↓ immutable identity validation
pure aggregate projection
        ↓
independent Experiment Results state

TaskRun URL selection + TaskRun report + Evaluation
        ↓
existing local evidence state
```

两条状态链只在同一页面组合，不互相充当事实源。选择另一个 TaskRun、TaskRun report
损坏、`evaluation=null`、Replay 不可用或 inventory 内容读取失败，都不能抹掉
available aggregate projection。反过来，Experiment report 损坏、被替换或 identity
冲突时，页面 fail closed，不保留陈旧聚合数字。

## 正式投影合同

纯投影位于
`studio/src/features/benchmark-reporting/model/benchmarkComparisonMetrics.ts`。
它只读取严格 parser 已验证的字段，并保持后端数组顺序。

### Outcome 与 denominator

- 顶层只展示 PASS、FAIL、INVALID、SKIPPED 的正式 count；
- 不从四个 count 推导顶层 eligible denominator；
- `eligibleCount` 只在对应 Agent 行中展示；
- `eligibleCount=0` 是有效事实，不转成 missing。

### Per-Agent metrics

每行保留：

- outcomes；
- `eligibleCount`；
- micro/macro success rate；
- duration mean、median 与 sample variance；
- Wilson 95% interval；
- usage covered/eligible；
- 后端给出的 Agent 顺序。

格式化规则是确定性的：

| Source | 展示 |
|---|---|
| rate `0` | `0.0%`，不是 unavailable |
| duration `0` | `0 ms` |
| variance `0` | `0 ms²` |
| nullable metric `null` | `Unavailable` |
| eligible `0` | 明确展示零样本 |
| partial usage | 展示 covered/eligible，不补算缺失调用 |

页面提供 metric definitions and units；它不把 micro/macro、Wilson 或 sample
variance 从 run rows 重新计算出来。

### Pairwise comparison

每行保留：

- 左右 Agent 的原始 orientation；
- matched task count；
- left-only/right-only unmatched count；
- left wins、right wins 和 ties；
- report 中的固定顺序。

页面只做以下展示分类：

```text
matched = 0                 → no matched scope
matched > 0, unmatched = 0 → fully matched
matched > 0, unmatched > 0 → partially matched
```

这不是新的 statistical interpretation，也不会产生 winner、ranking 或 superiority
label。

### Fairness 与显著性边界

- 已知 warning code 映射为安全、有限的读者说明；
- 未知 code 保留原始有界 code，并使用通用说明，不静默丢弃；
- Experiment Results 可用时始终显示：
  `Descriptive results only. No statistical significance is claimed.`；
- 折叠细节不会隐藏这条边界；
- UI 不使用冠军色、奖杯、胜者排序或推断性图表。

## 状态、分页与界面

`useBenchmarkExperimentReport` 从已经存在的 Experiment report query 派生
`states.aggregate`，没有新增请求。Experiment Results 位于 report header/publication
notice 之后、TaskRun–Evaluation–Facts 三栏之前，并使用全宽区域。

指标表和比较表各自拥有本地分页：

- 默认每页 25；
- 每页硬上限 50 个 mounted data rows；
- 保持后端稳定顺序；
- report identity 改变时重置页码；
- 不写 URL、query cache、Zustand 或 `localStorage`。

单 Agent report 的 comparison 列表为空时是合法完成态，不是错误。聚合区域自己的
loading、unavailable、corrupt 和 retry 状态不会把 Experiment resource 或下方
TaskRun 事实一起清空。

## 合成浏览器证据

无设备 fixture 新增了明确的合成身份：

```text
Experiment:
  experiment-ffffffffffffffffffffffffffffffff
Package:
  fixture/synthetic-comparison-metrics@1.0.0
Source:
  synthetic-comparison-metrics-fixture
```

它提供三个 synthetic Agent、四个相互一致的 Studio/Core TaskRun，以及正式
publisher-shaped report/reference，覆盖：

- PASS/FAIL/INVALID/SKIPPED 各一个；
- numeric zero 与 nullable metric；
- zero eligible 和 partial usage；
- partially matched 与 no matched comparison；
- 已知与未知 fairness warning；
- 小样本、稳定顺序和独立分页合同。

这只验证 React projection、route reconstruction 和页面交互。当前真实 Studio
Worker 仍是 single Agent、single Task、single repeat；fixture 不能升级为
multi-Agent scheduler、真实 Android 或统计显著性证据。

## 自动化与浏览器验证

在仓库根目录复验：

```bash
cd studio
npm test -- --run
npm run typecheck
npm run lint
npm run build
node --check scripts/benchmark-monitor-smoke-fixture.mjs

cd ..
.venv/bin/python -m pytest -q \
  tests/benchmark/test_reporting.py \
  tests/studio/test_benchmark_reporting_resource.py
```

2026-07-30 的观察结果：

- focused projection/state/component/route：20 tests passed；
- 完整 Studio：43 files、158 tests passed；
- TypeScript 与 ESLint：通过；
- production build：通过，保留既有 `>500 kB` chunk warning；
- fixture syntax：通过；
- focused Core/Studio reporting backend：15 tests passed；
- 后端首次在受限沙箱内因临时 HTTP 端口绑定 `EPERM` 失败；在允许本地端口绑定的
  同一环境用同一命令重跑后全部通过，这不是产品回归。

手工浏览器复验：

```bash
# terminal 1
cd studio
npm run smoke:benchmark-monitor

# terminal 2
cd studio
npm run dev -- --host 127.0.0.1
```

打开：

```text
http://127.0.0.1:5173/experiments/experiment-ffffffffffffffffffffffffffffffff/report
http://127.0.0.1:5173/experiments/experiment-99999999999999999999999999999999/report
```

已观察到：

- synthetic 页面展示 3 个 Agent、4 种 outcome、2 个 comparison 和 warning；
- TaskRun URL 切换后 aggregate 表保持同一事实；
- refresh 保留 TaskRun deep link，并从 durable fixture 重新构建 aggregate；
- collapse 后 significance boundary 仍可见；
- 当前 single-Agent fixture 展示有效 empty comparison state；
- 两张表分别具有 `Per-Agent metrics` 与 `Pairwise comparisons` accessible name；
- 1280×720 视口没有 document-level 横向溢出；
- console error count 为 0；仅有既有 React Router v7 future warnings。

retry、陈旧事实移除、超过一页的 bounded pagination 和 identity replacement 由
component/hook/pure projection 测试确定性覆盖；成功 fixture 不人为伪造网络失败。

## 设计取舍

- 选择 strict report 的纯投影，而不是建立第二套统计模型；
- 选择 aggregate 与 selected TaskRun 两条独立状态链，而不是共用一个大
  loading/error gate；
- 选择事实表格而不是推断性图表，牺牲视觉冲击力以保留分母、null 和小样本边界；
- 选择本地有界分页，而不是为了正式 report 增加服务端分页或持久 UI 状态；
- 选择合成 multi-Agent presentation fixture，而不是等待尚未实现的 scheduler；
- 未选择浏览器重算 metrics、performance ranking、winner language 或 significance。

## 已知限制与失败情况

- 当前 Studio Worker 还不能用该页面证明真实 multi-Agent/multi-Task/repeat 执行；
- 没有 p-value、置信差显著性检验、效应量或胜者结论；
- unknown warning 只能安全展示，不能由前端推断含义；
- report 缺失、损坏、版本不兼容或 identity 冲突时，aggregate fail closed；
- 5.4C 不增加 History、artifact viewer、report/trajectory/bundle export；
- 不包含 PostgreSQL、对象存储、retention/delete 或真实 Android 验收；
- Evaluation Tree 仍用于人工定位，不是自动根因诊断；
- production bundle 仍有既有大 chunk warning。

原 5.4D 已在后续前置调研中永久拆分。5.4D-1
`implement-studio-benchmark-history-5-4d1` 已实现；当前下一步固定为
`implement-studio-benchmark-evidence-viewer-5-4d2`，之后是
`implement-studio-benchmark-export-5-4d3`。后两者复用已验证的 filtered
history、metadata-only inventory、scoped links 和 Report 页面，分别完成
evidence viewer 与受控 report/trajectory/bundle export；不得在前端猜宿主路径
或绕过 managed artifact resolver。

## 用户决策与 Coding Agent 工作

用户决定了 Stage 5.4 的产品目标、5.4A–5.4C 后继续按 5.4D-1/2/3 实施、先对齐
颗粒度再逐步实施，以及“只展示正式后端统计、不把 synthetic 证据说成真实能力”
的边界。

Coding Agent 本次完成了代码调查、OpenSpec artifact 落地、纯投影、状态隔离、
React UI、fixture、自动化测试、浏览器验收、命令执行和本文档整理。正式指标本身
来自既有 Benchmark Core/report，不是 Coding Agent 或浏览器新计算的研究结果。

## 30–60 秒面试说明

> 5.4B 已经能展示单个 TaskRun 和 Evaluation Tree，但 Experiment report 里的
> micro/macro、Wilson、耗时、paired comparison 和 fairness 还没有安全进入
> Studio。5.4C 没有再造统计模型，而是从严格解析并完成 identity 校验的
> schema-1.0 Experiment report 做纯投影；aggregate 状态只依赖 Experiment
> resource 和正式 report，所以切换或损坏某个 TaskRun 不会抹掉总体事实。页面
> 明确区分零和缺失、展示每 Agent denominator、保持 comparison orientation，并
> 永久显示“只做描述、不声明显著性”。我们用 158 个前端测试、15 个后端回归和
> 无设备浏览器 fixture 验证页面合同；multi-Agent 数据明确是 synthetic，当前
> Worker 仍只证明单 Agent/single Task/single repeat。

## 常见追问

1. **为什么不在前端从 TaskRun 重新算成功率？**  
   Core report 才拥有 eligibility、aggregation 和 fairness 语义。前端重算会产生
   第二事实源，并容易把 INVALID/SKIPPED 或缺失 usage 算错。

2. **为什么 aggregate 不依赖当前选中的 TaskRun？**  
   aggregate 是 Experiment 级正式结论；TaskRun 只是局部证据。两条状态链分开后，
   局部加载或损坏不会污染已验证总体事实。

3. **为什么 multi-Agent 只能使用 synthetic fixture？**  
   当前 Worker 的真实执行切片仍是单 Agent。fixture 能验证 parser、identity、
   React 和交互合同，但不能替代 scheduler 或 Android 运行证据。

4. **什么时候才能说某个 Agent 更好？**  
   只有后端增加经过设计和验证的统计推断合同、足够样本和公平配对证据后才可以。
   5.4C 明确保持 `significanceClaimed=false`，不输出 winner/ranking。
