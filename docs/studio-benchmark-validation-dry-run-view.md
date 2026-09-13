# Studio Benchmark Validation / Dry-run View

本文记录 Stage 5.5C-2
`implement-studio-benchmark-validation-dry-run-view-5-5c2` 的实际实现、验证证据、
设计取舍和边界。它把 5.5C-1 的 revision-bound、无副作用 validation/dry-run
资源接入 Benchmark authoring workbench，但不执行 Benchmark、Agent、设备、
Contract Test、publication 或 migration。

## 状态与范围

截至 2026-08-01，本 Change 已实现并验证：

- `/benchmark-drafts/:draftId/edit?mode=validation` URL-owned Validation mode，
  不支持的 mode 仍安全回落到 Definition；
- 只允许 clean saved baseline、exact current revision 且无 conflict、remote-newer、
  definition/content/analysis pending 时显式发起分析；进入页面不会自动请求；
- bounded split/task discovery、whole-split 空 `taskIds` 语义，以及最多 100 个
  task 的显式 scope；
- cursor-backed Agent 列表与 1–16 个不可变 `{agentId, revisionId}` frozen pair；
  metadata 刷新不会静默推进已选 revision；
- validation 与 dry-run 各自独立的 not-run、pending、valid/invalid、transport-failed
  和 stale 状态，结果不进入 TanStack durable query cache；
- partial Package/content/Plan/Protocol identities、字段级 diagnostics、unverified facts
  与始终可见的 `executionEvidence=false`、`unvalidated` 边界；
- dry-run verified Agent/AgentGraph、budget、fairness warning、relative output layout，
  以及最多 10,000 条完整 schedule 的每页 50 条本地分页；
- diagnostic 到 Definition member、managed resource 或 frozen Agent row 的显式导航；
  未映射字段保留完整安全 breadcrumb，不虚构控件或 caret focus；
- revision、split、task、Agent、save/content success、409、Reset 与 Reload 后的
  abort/discard/reconciliation；
- no-device 真实浏览器 journey、完整 Studio 回归、相关后端回归、typecheck、lint、
  production build 和 OpenSpec strict validation。

本 Change 没有新增后端 API、SQLite migration、持久 analysis result、execution、
Contract Test、publish/migrate、Worker 扩容、真实 Android、PostgreSQL、object storage
或 retention/delete。`BenchmarkTask` JSON 与 `AgentConfig`/`AgentGraph` 保持独立合同。

## Agent / Benchmark 问题与前后流程

5.5C-1 已能从 exact current authoring revision 产生有界分析事实，但用户仍无法在
Studio 中安全选择 immutable Agent revision、发起请求、处理晚到响应，或从 diagnostic
回到对应编辑位置。若 UI 只围绕一个通用 loading/result flag 拼接，很容易把旧 revision
结果显示在新 definition 上，或者把 schedule preview 误写成 runnable proof。

```text
before
  authoring workbench ── Definition / Resources
  5.5C-1 HTTP ───────── revision-bound validation / dry-run facts
  两者之间没有显式 gate、request owner、stale reconciliation 或诊断导航

after
  stable draft route + ?mode=validation
                  │
       authoritative draft/current query
       + feature-local editable baseline
                  │
          pure clean-analysis gate
                  │
   explicit split/tasks + frozen Agent revisions
                  │
        explicit Validate / Dry-run
                  │
     generation-bound transient request/result
       ├─ partial identities + diagnostics
       ├─ complete bounded schedule pages
       └─ budget/fairness/layout/unverified facts
                  │
      diagnostic intent → workbench coordinator
       ├─ Definition member + safe field breadcrumb
       ├─ exact current managed resource
       └─ frozen Agent row

  initializer / evaluator / Agent / device / Experiment ── never entered
```

浏览器旅程实际发现并修复了两个会破坏这条流程的问题：首次 authoritative workbench
水合时，空状态被误判为 eligibility loss 并显示 stale；同一个 revision ID 上的显式
Reload 没有清空 feature-local 临时分析。前者改为只在 `eligible: true → false` 时失效，
后者以显式 analysis epoch 重建会话，同时不改变 URL 或服务端 revision identity。

## 分层与状态所有权

- `entities/benchmark-authoring`：strict schema-1 request/result parser、owner-scoped
  API 和 transient TanStack mutation；unknown/unsafe/oversized/contradictory响应 fail
  closed，且强制 `executionEvidence=false`；
- `features/benchmark-validation-dry-run/model`：pure gate、bounded definition
  discovery、cursor-backed Agent query、frozen selection、request owner、generation 与
  late-result reconciliation；
- `features/benchmark-validation-dry-run/ui`：Validation inputs、独立 result panels、
  complete local schedule pagination 和 truthfulness boundary；
- `features/benchmark-definition-editor`：只公开 typed member/focus intent 与安全
  field breadcrumb；raw task JSON 仍由 definition feature-local buffer 持有；
- `features/benchmark-resource-editor`：只接受 exact current revision 的 controlled
  logical-resource selection；HEAD、availability、confirmation 与 retry 仍为 resource
  feature 所有；
- `widgets/benchmark-authoring-workbench`：组合权威 server facts、local editor status、
  URL mode、pending/conflict 与 diagnostic intent，不跨 feature 读取内部 store；
- `benchmark-authoring-smoke-fixture.mjs`：提供严格 no-device HTTP/browser 状态与
  forbidden-business-boundary sentinel，不模拟真实运行结果。

TanStack Query 继续拥有 durable server state；editable definition、raw JSON、baseline、
conflict 与分析会话分别属于对应 feature-local state。Validation result 是 disposable
definition-level fact，刷新或输入 owner 改变后必须显式重跑。

## 已验证合同

### 1. Clean saved-baseline gate

分析按钮只有在以下事实同时成立时可用：draft/revision identity 完整、baseline 与
working document clean、baseline/current revision 相等、无 optimistic conflict、无
remote-newer、definition/content command 未 pending，且当前 analysis 未 pending。每个
blocked state 都有确定原因与 corrective action；dirty 不会被自动保存，进入 Validation
mode 也不会自动分析。

### 2. Immutable Agent 与 revision-bound ownership

Agent candidate 通过既有 metadata-only cursor API 加载；没有 current revision 的 Agent
不可选择。同一 Agent 不得重复加入，选择后冻结 exact revision pair；后续 candidate
metadata advance 不会改写 pair。validation owner 绑定 draft/revision/split/task，dry-run
owner 还绑定 frozen Agent pairs；owner 或 session generation 不一致的晚到响应被丢弃。

revision advance、draft switch、409、Reload 与 Reset 清空全部 obsolete results；split、
task 或 Agent 改变只失效受影响结果。Abort 只是取消等待，服务端是否已完成由 HTTP
边界决定，因此 UI 从不把 aborted request 当成功事实。

### 3. Truthful partial result 与 diagnostic navigation

validation 和 dry-run 不共享一个“总体成功”状态。HTTP transport failure 不伪造成
semantic invalid；413 不保留 partial schedule；409 清除旧结果并提供 Reload Remote。
已建立 identity 才展示，没有 placeholder hash。

每条 diagnostic 只消费服务端提供的 member kind/path、field path 与 scoped identity。
workbench 可切换到 Definition、Resources 或保持 Validation 并聚焦 frozen Agent；对开放
extension field/raw task path 只显示安全 breadcrumb，不声称通用 JSON editor 已完成精确
caret 定位。foreign/missing resource request 被拒绝，不改变 resource-local selection。

### 4. Complete bounded schedule，不是 execution proof

dry-run 只接受后端 strict parser 通过的完整 schedule，公共上限为 10,000 条。UI 每页
固定 50 条，页数从完整数组计算，不二次排序、不重算、不静默截断；10,000 条时 DOM
仍只渲染当前页。budget、fairness、relative output layout 和 unverified facts 原样展示。

每个结果状态都显示 revision 仍为 `unvalidated` 且 `executionEvidence=false`。页面没有
Run、Contract Test、Publish、Migrate、device 或 runtime 控件。多 Task、repeat、Agent
的 schedule 仍只是规划投影，不证明当前 Worker 可执行该矩阵。

## 验证证据

### Studio 与相邻后端回归

```bash
cd studio
npm test -- --run
# 76 files / 350 tests passed

npm run typecheck
npm run lint
npm run build
# passed; 601 modules transformed

cd ..
uv run pytest -q \
  tests/studio/test_benchmark_authoring_analysis.py \
  tests/studio/test_benchmark_authoring_content.py \
  tests/studio/test_benchmark_authoring_materializer.py \
  tests/studio/test_benchmark_authoring_resource.py \
  tests/studio/test_benchmark_http.py \
  tests/benchmark/test_authoring.py \
  tests/benchmark/test_compiler_catalog_cli.py \
  tests/benchmark/test_models_identity.py
# 133 passed in 8.71s
```

前端完整 suite 覆盖 strict parser/API/mutation、gate/session、10,000 schedule DOM、
diagnostic navigation、URL/workbench、Definition/Resources non-regression；后端 suite
确认 5.5C-1 HTTP/analysis、5.5A/B、SQLite schema 8、canonical identity、CLI、legacy
BenchmarkTask 和既有 worker 行为未因纯前端 Change 改变。production build 保留既有
大 chunk warning；它不是本 Change 新增的运行错误。

### No-device 真实浏览器旅程

fixture journey 覆盖：直接进入 `mode=validation` 且无自动命令、dirty 阻断、保存无效
revision、invalid validation、`.title` diagnostic navigation、修复并保存、valid
validation、冻结 Agent、60 条完整 schedule 的 50+10 两页、budget/fairness/unverified/
layout、split 改变后的 delayed response 丢弃、413、409、显式 Reload Remote，以及
Reload 后同 revision ID 的 transient session 清空。

fixture-installed sentinel 的 initializer、environment、evaluator、Agent execution、
device、plugin construction、model、network、secret、Experiment、TaskRun/result、
report、Replay、Contract Test、publication、migration、export 与 Android business
boundary 计数均为 0。该 sentinel 只约束应用 fixture 的业务边界，不把浏览器或测试工具
自身的遥测请求描述为产品网络能力。

### OpenSpec 与范围审计

```bash
openspec validate \
  implement-studio-benchmark-validation-dry-run-view-5-5c2 --strict
# Change 'implement-studio-benchmark-validation-dry-run-view-5-5c2' is valid
```

新/改函数已按适用输入、返回和失败补充 doc comment；scoped diff 对 FSD-lite 依赖方向、
owner/capacity、安全路径、truthfulness、future-control absence 和无关用户改动保留完成审计。

## 设计取舍、限制与失败情况

- 选择 transient mutation/session，而不是 durable query/result：避免把易过期分析当服务端
  当前事实，代价是刷新或 Reload 后必须重跑；
- 选择 frozen Agent pair，而不是跟随 current metadata：保证请求可重建，代价是用户需
  显式移除再选择新 revision；
- 选择 generation/owner discard + AbortSignal，而不是假设浏览器 abort 能撤回服务器：
  正确处理晚到响应，代价是服务端可能完成一个已被 UI 丢弃的无副作用计算；
- 选择每页 50 条完整本地分页而不是 virtualization：10,000 上限内更简单可测试，代价是
  首次响应仍需解析完整有界数组；
- diagnostic 只聚焦明确映射的控件；开放字段显示 breadcrumb，不承诺通用 JSON caret；
- reload epoch 是同 identity 的 UI reset 信号，不参与后端 canonical identity；
- 没有 durable validation lifecycle 或“validated” revision promotion；该冻结/发布语义
  属于 5.5E；
- 没有 Contract Test、第三方 process sandbox、runtime/Worker 扩容、真实 Android、
  PostgreSQL/object storage、retention/delete 证据。

## 手工复验

```bash
cd studio
npm run build
node scripts/benchmark-authoring-smoke-fixture.mjs
```

在 fixture 输出的 loopback URL 打开
`/benchmark-authoring`，新建或打开 draft，再进入 URL 中的 `mode=validation`。应观察到：

1. dirty、pending 或 stale current 时 Validate/Dry-run 被阻断并显示修正动作；
2. 只有显式点击才发请求，invalid diagnostic 能回到对应 member/field breadcrumb；
3. frozen Agent 显示 exact revision/AgentGraph，metadata 刷新不自动换 revision；
4. schedule 按 50 条分页完整展示，同时显示 budget、fairness、layout、unverified 与
   no-execution 边界；
5. 改 split/task/Agent、保存、409、Reset 或 Reload 后旧结果不再可见；
6. 页面不存在 Run、Contract Test、Publish 或 Migrate 控件。

常见失败：fixture 未启动会显示 transport error；413 是容量拒绝且没有 partial schedule；
409 要显式 Reload Remote；Abort 后可能仍有服务端无副作用计算，但晚到结果不会进入当前
session。该复验不连接 Android，也不验证 initializer/evaluator 或真实 Agent 执行。

## 当前下一步

下一项固定为 `implement-studio-benchmark-contract-tests-5-5d`：在现有 fake-fixture
Contract Test Kit 上建立显式 initializer/environment/evaluator Contract Test 产品边界，
区分 passed/failed/skipped，并保持 device/network/model/secret 默认禁止。它必须单独
证明隔离、seeded determinism、有界可序列化结果和 evidence safety；5.5C-2 的
validation/dry-run UI 不能作为这些证据。

## 事实来源

- 用户固化了当时的 Stage 5.5 executable change 顺序、5.5C-2 颗粒度和声明边界；
- 5.5C-1 HTTP/analysis、authoring/resource editor 与 Agent metadata 是此前验证事实；
- Coding Agent 实现并运行了本 Change 的 strict frontend contracts、state session、UI、
  workbench/navigation、fixture、自动化、真实浏览器 journey、范围审计与本文档；
- requirement、design 和完整验收场景保存在对应 OpenSpec Change 中。
