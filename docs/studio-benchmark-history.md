# Studio Benchmark Experiment History（Stage 5.4D-1）

本文记录
`implement-studio-benchmark-history-5-4d1`
已经实现并验证的 durable Experiment History、精确筛选、游标、React 页面、
安全边界和证据限制。Stage 5.4 的完整顺序仍以
[Studio Stage 5.4 Benchmark Reporting 路线](studio-benchmark-reporting-roadmap.md)
为准。

## 结论

Stage 5.4D-1 已把 5.4A 的只读 Experiment collection 扩展为可从 URL 重建的
Benchmark History：

- 后端支持 lifecycle、immutable Catalog identity、scheduled Agent identity 和
  accepted time 的精确组合筛选；
- continuation cursor 绑定规范化筛选 identity，不能跨筛选复用；
- `/experiments` 显示 durable Experiment、source、Agent/revision、时间、
  planned TaskRun 数量和五条独立 availability；
- History 只沿服务返回的 Monitor/Report link 导航，不猜测 Replay、Viewer、
  Export 或文件路径；
- 查询和页面不会启动 worker、连接设备、解析 secret 或读取 artifact body。

这一步完成的是“重新发现并进入实验”，不是 Evidence Viewer 或二进制导出。它
完成时的下一步是 `implement-studio-benchmark-evidence-viewer-5-4d2`；5.4D-2
与 5.4D-3 现均已实现，当前下一步是 Stage 5.5 Benchmark authoring。

## Agent 工程问题与涉及层

5.4A 的 collection 能按 newest-first keyset 分页，但不能表达完整研究工作流所需的
筛选。只在浏览器过滤当前页会产生三个错误：

1. 结果不是全量 durable Experiment 的子集；
2. 下一页 cursor 不知道筛选 identity；
3. 当前 Catalog/Agent registry 会覆盖已经删除或改名的历史 identity。

本 Change 跨越以下层：

```text
HTTP query
    ↓ strict parse
HistoryFilterV1
    ↓
Experiment service
    ↓
SQLite repository
    ├─ immutable snapshot Catalog identity
    ├─ scheduled TaskRun Agent membership
    ├─ current lifecycle
    └─ acceptedAt / experimentId keyset
    ↓ compact public page
TanStack Query entity
    ↓
/experiments URL state
    ↓
History rows → Monitor / Report
```

设备、worker、plugin/model、managed artifact content 和 Replay resolver 不进入这条
读取路径。

## 后端合同

### Filter DTO

`StudioBenchmarkExperimentHistoryFilterV1` 是 strict immutable DTO，字段为：

| 字段 | 语义 |
|---|---|
| `lifecycle` | 当前 durable Experiment lifecycle 的精确值 |
| `catalogEntryId` | immutable definition snapshot 中的 Catalog identity |
| `agentId` | 至少一个 scheduled TaskRun 的精确 Agent identity |
| `acceptedFrom` | inclusive lower bound，Unix epoch milliseconds |
| `acceptedBefore` | exclusive upper bound，Unix epoch milliseconds |

时间必须是 JavaScript safe integer，且同时存在时满足：

```text
acceptedFrom < acceptedBefore
```

Catalog/Agent 使用 stable exact identity，不做模糊搜索、文件名匹配或当前 registry
反查。已删除的 Catalog/Agent 仍能按 durable identity 找到。

### HTTP query

入口保持：

```text
GET /studio/benchmark-experiments
```

允许的 query 参数只有：

```text
limit
cursor
lifecycle
catalogEntryId
agentId
acceptedFrom
acceptedBefore
```

unknown、duplicate、blank、非法枚举、非法 identity、非规范整数、unsafe integer 和
反向时间范围都会返回 bounded safe error。旧的无筛选调用仍保持兼容。

### Repository predicates

Repository 使用固定 SQL 模板和参数绑定：

- lifecycle 读取 `studio_benchmark_experiments.lifecycle_state`；
- Catalog 从 canonical `snapshot_json` 的
  `$.source.catalogEntryId` 做 exact match；
- Agent 使用 scoped TaskRun `EXISTS`；
- accepted time 使用 `[acceptedFrom, acceptedBefore)`；
- keyset boundary 使用
  `(accepted_at DESC, experiment_id DESC)` 的 exclusive continuation。

没有把客户端字段名或自由文本拼进 SQL。

### Cursor v2

新 cursor 是 checksummed opaque v2，绑定：

- `acceptedAt`；
- `experimentId`；
- canonical filter fingerprint；
- cursor version。

由此得到：

```text
同筛选 + 同 cursor       → 继续同一查询
不同筛选 + 旧 cursor     → 拒绝
篡改 body/checksum        → 拒绝
v1 cursor + 无筛选        → 兼容
v1 cursor + 任意筛选      → 拒绝
```

排序键中的 `acceptedAt` 和 `experimentId` 是持久 identity 边界。新增且排在 cursor
之前的 Experiment 不会插入后续页。

### SQLite schema 7

schema 7 是 index-only migration，新增：

```text
studio_benchmark_experiments_history_order
studio_benchmark_experiments_catalog_history
studio_benchmark_task_runs_agent_experiment
```

迁移不改写 snapshot、TaskRun、event、publication 或 artifact。它支持 schema 6
升级、重复打开、事务回滚和历史测试夹具残留索引。

## 前端产品合同

### 路由所有权

Benchmark History 使用：

```text
/experiments
```

普通 Studio Run/Replay History 继续使用：

```text
/history
```

两类资源没有合并。`/experiments/new`、Monitor、Report 和 TaskRun Replay route
保持原语义。

### URL 是筛选事实源

页面使用 strict parser/serializer 管理：

- filters；
- `limit`；
- opaque forward cursor。

Apply/Clear 会重置 cursor。刷新和 deep link 能重建相同查询；invalid URL 显示明确
错误并提供安全第一页重置。前进分页写入 URL，返回上一页使用浏览器 Back，因此
首版没有发明 reverse cursor。

### 行展示

每个 History row 展示：

- Experiment identity；
- current lifecycle 与 terminal reason；
- immutable Catalog/source/package identity；
- immutable Agent/revision identity；
- accepted、updated、terminal timestamp；
- planned TaskRun count；
- outcome、report、Replay、trajectory、bundle 五条独立 availability。

Catalog/Agent autocomplete 只提供当前 registry suggestion，不修改已经存在于 URL
或历史行中的 durable identity。

### 导航边界

页面只消费 strict same-service link：

- `links.self` → Monitor；
- available `links.report` → Report。

Experiment-level `replayAvailability=available` 只显示提示。真正 Replay handoff
仍属于具体 TaskRun 的 `links.replay`。History 不构造：

- guessed Replay URL；
- artifact Viewer URL；
- Export/download URL；
- storage path 或 managed filename。

## 状态与失败处理

页面独立处理：

- initial loading；
- page transition，保留上一页内容；
- backend error 与同 URL retry；
- invalid URL 与 reset；
- unfiltered empty；
- filtered empty；
- partial availability；
- Report unavailable。

Report 不可用时没有 Report link；其余可验证事实仍可显示。

## 安全与副作用边界

自动化和真实浏览器 canary 已确认 History response/UI 不公开：

- AgentGraph body；
- Experiment Protocol body；
- prompt 或 secret；
- raw device serial；
- storage ref 或 host path；
- artifact bytes；
- guessed Replay link。

History 会读取 durable Experiment/TaskRun metadata 和 immutable snapshot 中用于
身份投影的字段，但不会打开 managed artifact content。

## 已验证证据

### Backend

```bash
uv run pytest -q \
  tests/studio/test_benchmark_experiment_history.py \
  tests/studio/test_benchmark_reporting_resource.py \
  tests/studio/test_benchmark_experiment_resource.py \
  tests/studio/test_benchmark_publication_replay.py \
  tests/studio/test_benchmark_startup_recovery.py \
  tests/studio/test_benchmark_event_stream.py \
  tests/studio/test_benchmark_execution_worker.py
```

实际结果：

```text
119 passed
```

覆盖 filter、schema 6→7、timestamp tie、组合查询、cursor v1/v2、tamper、
cross-filter、HTTP strictness、publication/recovery/event/worker 回归。

### Frontend

```bash
cd studio
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

实际结果：

```text
47 test files passed
168 tests passed
typecheck passed
lint passed
production build passed
```

生产构建仍报告既有主 bundle 超过 500 kB 的 warning；它不是本 Change 新增的
功能正确性失败，也不证明前端性能目标已经完成。

### Clean wheel

```bash
uv run pytest -q tests/packaging/test_benchmark_history_install.py
```

实际结果：

```text
1 passed
```

该测试构建并安装 wheel，在仓库外 cwd 中确认 `zhixing` 来自 isolated
`site-packages`，再用安装包完成 schema 6→7 和组合筛选；没有设备配置。

### No-device browser

启动：

```bash
cd studio
npm run smoke:benchmark-monitor
```

另一个终端：

```bash
cd studio
npm run dev -- --host 127.0.0.1
```

浏览器验收覆盖：

- `/experiments?limit=2`；
- lifecycle + Catalog + Agent + accepted range 组合筛选；
- refresh 后查询重建；
- cursor Next 与浏览器 Back；
- History → Monitor → Back → Report；
- Report unavailable；
- duplicate query reset；
- 自动 retry 耗尽后的同 URL 手动 retry；
- Replay/Viewer/Export/definition/secret/path/artifact-byte canary。

fixture 不启动 worker 或设备，不构成真实 Android 证据。

## 设计取舍

### 采用：后端精确筛选

浏览器只提交 filter；数据库先筛选再分页。代价是后端合同和索引增加，但结果语义
正确，cursor 可以绑定筛选。

拒绝的替代方案是“拉一页后前端过滤”，因为它不能表示全量 History。

### 采用：immutable identity

Catalog 来自 definition snapshot，Agent 来自 scheduled TaskRun。代价是显示名称
可能缺少当前 registry enrichment，但不会因为删除/改名丢失历史。

拒绝的替代方案是 join 当前 registry，因为它会改写过去事实。

### 采用：forward cursor + browser Back

首版只公开服务已有的 forward keyset cursor，上一页交给浏览器 history。代价是
不能任意跳页，但没有发明不受后端保证的 reverse cursor。

### 采用：Replay 仅提示

Experiment aggregate 只知道“至少存在 Replay”，不知道该进入哪个 TaskRun。
因此 History 不提供 Replay action。若以后需要一步直达，后端必须先给出唯一、
typed、scoped handoff。

## 已知限制与失败场景

- lifecycle 是 current mutable state，不是查询开始时的 snapshot。Experiment 在
  翻页期间改变 lifecycle，可能离开或进入某个 lifecycle filter；cursor 只稳定
  排序边界，不承诺 snapshot isolation；
- SQLite 首版没有证明大规模 History 性能或 PostgreSQL 等价行为；
- 没有 reverse cursor、任意页码、retention/delete 或全文搜索；
- History 不渲染 evidence content，不下载 report/trajectory/bundle；
- 仍未扩展 multi-Task/repeats/multi-Agent worker；
- no-device fixture 不证明真实 Android execution；
- structured trajectory 只支持审计和人工定位，不是自动失败诊断。

## 历史交接与当前状态

5.4D-1 完成时的下一步是：

```text
implement-studio-benchmark-evidence-viewer-5-4d2
```

5.4D-2 必须复用：

- 5.4A Experiment-bound artifact inventory 与 scoped content links；
- 5.4B Evaluation leaf causal references；
- 5.4D-1 History → Report/Monitor 导航。

它不能根据 artifact id、kind、文件名、storage ref 或 host path 构造内容 URL，
也不能把浏览器下载意图描述为下载完成。

该交接已由 5.4D-2 Evidence Viewer 与 5.4D-3 Export 按顺序完成。当前事实见
[Studio Benchmark Evidence Viewer](studio-benchmark-evidence-viewer.md) 与
[Studio Benchmark Export](studio-benchmark-export.md)；下一步固定为
`implement-studio-benchmark-authoring-5-5`。
