# Studio Benchmark Contract Tests

本文记录 Stage 5.5D
`implement-studio-benchmark-contract-tests-5-5d` 的实际实现、验证证据、设计取舍和
边界。它在 exact current Benchmark authoring revision 上显式运行 server-owned、
reviewed fake fixtures，检查 initializer、environment 和 evaluator 的逻辑合同；它不
执行 Package 提供的代码、真实 Benchmark/Agent、设备、模型、网络、密钥、Experiment、
publication 或 migration。

## 状态与范围

截至 2026-08-01，本 Change 已实现并验证：

- immutable Core fixture profile/descriptor、case、coverage、diagnostic、safety 和 report
  合同，以及最多 1,000 cases、100 diagnostics、32 profiles 的公共上限；
- initializer/environment/evaluator occurrence discovery、task/member-local stable case
  identity、caller seed + case identity 的 order-independent case-local seed；
- exact fixture matching、role-specific input/output validation、fresh-scope repeated call、
  observable isolation、promised determinism、environment lifecycle 与 evaluator
  compatibility normalization；
- `passed`、`failed`、`skipped` 三态，以及相互独立的 `complete` 和
  `executedChecksPassed` aggregate facts；
- unsafe evidence fail-closed：secret/path/device-serial/live-object/unbounded/non-JSON
  结果不会进入公共 case、diagnostic、HTTP 或日志；
- reviewed `studio-safe-v1@1.0.0` profile，以及明确标记为 `declaration-only` 的旧 CLI
  compatibility path；
- 与 5.5C-1 共用的 exact-revision private disposable Package compiler；validation 和
  dry-run 的 DTO、identity、canonical hash、cleanup 与 HTTP 行为不变；
- metadata-only profile GET、strict no-store Contract Test POST、稳定错误状态与无 SQLite
  migration 的 Studio composition；
- `/benchmark-drafts/:draftId/edit?mode=contract-tests` 第四个 URL-owned authoring mode，
  clean saved-baseline gate、explicit run、request owner/generation、late discard、409
  reconciliation、filter、25-case local pagination 与 diagnostic navigation；
- no-device 真实浏览器 journey、完整 Studio/后端回归、typecheck、lint、production build、
  repository-independent clean-wheel install 与 OpenSpec strict validation。

结果只证明 reviewed fake fixture 在可信服务进程内观察到的逻辑合同事实。它不把 revision
改成 `validated`，不持久结果，也不授予 5.5E publication eligibility。

## Agent / Benchmark 问题与前后流程

5.5C-1/2 能证明 authoring definition 可编译并生成 deterministic plan/schedule，但不能
证明定义里写到的 initializer、environment 或 evaluator logical reference 满足调用合同。
旧 CLI 的 declaration fixture 能检查声明，却容易被误解为真实 plugin 已运行；Studio
此前也没有可重建、可区分缺失覆盖与执行失败的产品表面。

```text
before
  exact revision ── validate / dry-run ── pure definition and planning facts
  CLI contract-test ── declaration-only compatibility
  Studio ── no explicit fixture profile, coverage semantics, or disposable result

after
  authoritative current draft revision
                │
       explicit split / seed / profile
                │
  shared private disposable Package compiler
                │ FULL compile, no runtime resolution
       bounded reference discovery (<= 1,000)
                │
     server-owned reviewed fake profile
       ├─ initializer contract
       ├─ environment setup/reset/cleanup contract
       └─ evaluator normalize/evidence contract
                │
     strict revision-owned disposable result
       ├─ passed / failed / skipped
       ├─ complete / executedChecksPassed
       ├─ safe diagnostics + exact member path
       └─ fixed negative safety facts

  Package code / device / model / network / secret / Agent / Experiment
  / output path / publication / persistence ── never supplied
```

## 分层与状态所有权

- `zhixing.benchmark.authoring.testing`：纯 Core fixture contracts、registry、discovery、
  runner、compatibility adapter 和 reviewed default profile；
- `StudioBenchmarkAuthoringRevisionCompiler`：唯一 exact-current load、private materialize、
  FULL compile、diagnostic/identity 与 cleanup boundary；5.5C-1 和 5.5D 注入同一实例；
- `StudioBenchmarkContractTestApplicationService`：profile-first lookup、request ownership、
  Core runner projection、invalid-definition zero-case result 和 final current recheck；
- Studio HTTP：只公开 bounded profile metadata 和 strict result，不公开 factory、import
  location、host path、managed content identity 或 private fixture object；
- `entities/benchmark-authoring`：strict TypeScript parser、profile query 与 owner-scoped
  transient mutation；unknown、oversized、unsafe-path、contradictory response fail closed；
- `features/benchmark-contract-tests`：pure gate、split/seed/profile input、generation/request
  owner、disposable result、filters/pagination 和 presentation；
- `BenchmarkDefinitionWorkbench`：组合第四个 mode、全 authoring command pending gate 与
  typed diagnostic intent，不读取 peer feature 内部 store；
- smoke fixture：只模拟 bounded HTTP/result states，并记录禁止业务边界调用计数，不模拟
  真实 plugin、device 或 runtime 证据。

TanStack Query 继续拥有 draft/current/profile server state；editable baseline/document/raw
buffers 仍属于 Definition feature。Contract Test result 只存在于当前浏览器 feature session，
刷新、Reload、save/content success、owner/input/generation 变化后需要显式重跑。

## 已验证合同

### 1. Stable case identity 与 seeded determinism

case identity 由 `taskId + member-local field path + kind + logicalName` canonical 产生；
exact Plan identity 保存在外层 result ownership，不进入 case-local seed identity。这样既能
用外层 identity 证明结果来自哪个 Plan，又能保证无关 task/case 的增删或重排不改变既有
fixture seed/output。全局 task array index 只用于回到 authoring document，不参与 identity。

当 descriptor 声明 deterministic 时，runner 使用相同 case-local seed 和安全复制参数创建
两个 fresh fixture scopes；规范化输出不等、scope 复用或可观察 lifecycle 泄漏均为
`failed`。该检查只能证明可观察合同隔离，不能证明可信进程内代码不存在不可见全局副作用。

### 2. Coverage-aware 三态

- `passed`：精确 kind/logical-name fixture 已匹配，并且每个 required check 实际成功；
- `failed`：fixture 已执行，但 input/output、determinism、isolation、lifecycle、evaluator
  normalization、evidence safety 或 serialization 违反合同；
- `skipped`：没有匹配的 safe fixture，或 profile 明确不提供该 capability；它不是 pass。

`complete` 仅表示没有 skipped coverage；`executedChecksPassed` 仅表示已执行 cases 没有
failed。全 skipped 可以是 `complete=false` 且 `executedChecksPassed=true`，mixed 也不会
被压成含糊的“success”。invalid definition 返回 field-addressable precondition diagnostics
和 zero cases，不调用 fixture。

### 3. Trust 与 evidence safety boundary

profile 由服务器显式注册，ID/version 唯一且 capability allowlist fail closed；profile
metadata 公开，factory 不公开。default fixture context 不含 device、model、network、
secret、Agent execution、Experiment、output path、publication、persistence 或 runtime
resolver。Package logical reference 永远不会触发 import/entry point/plugin construction。

fixture 仍在可信服务进程内执行，因此 `processSandbox=false`。异常只投影稳定类型与预定义
安全消息；任意 exception message、host path、token、serial、live object 或无界结果不会
回显。真实设备 profile、third-party hard sandbox 与强制终止不属于 5.5D。

### 4. Exact-revision command 与 HTTP

```text
GET  /studio/benchmark-authoring/contract-test-profiles
POST /studio/benchmark-authoring/drafts/{draftId}/contract-tests
```

POST strict schema-1 request 只接受 `revisionId`、`split`、bounded integer `seed` 和
`fixtureProfileId`。服务在 materialization 前解析 profile，并在 work 前后检查 revision
仍为 draft current。结果绑定 draft/revision/document fingerprint/request fingerprint、
split/seed、profile ID/version、Package/content/Plan/Protocol identities。

HTTP 保留既有 Host/origin/content/body 限制和 private `Cache-Control: no-store`。malformed
或 profile failure 为 400，隐藏 ownership 为 404，stale 为 409，pre-execution capacity
为 413，未配置/存储不可用为 503，unsupported method 为 405；容量失败不返回 partial
cases，也不做 fixture work。

### 5. React authority 与 diagnostic navigation

进入 `mode=contract-tests` 只加载 bounded profile metadata，不自动保存或运行。按钮仅在
clean saved baseline、exact current revision、无 dirty/unapplied JSON/conflict/remote-newer
且所有 authoring commands idle 时可用。

visible result 必须同时匹配 draft/revision/fingerprint/split/seed/profile ID+version、feature
generation 和 active request owner。Abort 只取消等待；晚到响应还要经过 owner/generation
提交门。409 清空结果并要求 Reload Remote。diagnostic 通过 workbench public intent 回到
exact task member 和安全 field breadcrumb；open JSON path 不虚构 caret-level focus。

## 验证证据

### 自动化与 production build

```bash
UV_CACHE_DIR=/private/tmp/zhixing-contract-tests-uv uv run pytest -q \
  tests/benchmark/test_contract_testing.py \
  tests/benchmark/test_authoring.py \
  tests/studio/test_benchmark_authoring_analysis.py \
  tests/studio/test_benchmark_authoring_contracts.py
# 64 passed

PYTHONPATH=tests UV_CACHE_DIR=/private/tmp/zhixing-contract-tests-uv \
uv run pytest -q tests/benchmark tests/studio tests/graph tests/contracts \
  tests/runtime tests/sdk tests/catalog tests/components \
  -m "not android_acceptance"
# 697 passed

cd studio
npm run test
# 80 files / 367 tests passed
npm run typecheck
npm run lint
npm run build
# passed; 607 modules transformed
```

完整后端回归覆盖 scaffold/validate/dry-run/contract-test CLI、legacy BenchmarkTask JSON、
Package/Plan/Protocol identity、5.5A/B/C、Catalog、Experiment worker、reporting、Replay、
Export、AgentConfig 和 AgentGraph。production build 仍有既有 large-chunk warning；本
Change 没有把它提升为功能失败。

### Clean wheel

```bash
UV_CACHE_DIR=/private/tmp/zhixing-contract-tests-uv uv run pytest -q \
  tests/packaging/test_benchmark_authoring_install.py \
  -m packaging_acceptance
# 3 passed
```

验收从源码构建 wheel/sdist，在独立 venv 安装依赖，并从 repository-independent working
directory 发现 `studio-safe-v1`、创建 immutable draft revision、运行 deterministic exact-
revision Contract Tests。结果为一个 `file_exist` passed case，draft/current/status 不变、
SQLite 仍为 schema 8、private staging 清空、公共 JSON 无工作目录泄漏，所有 external/
runtime capability facts 为 false。

### No-device 真实浏览器 journey

真实浏览器覆盖 direct `mode=contract-tests` 和 Not run、dirty title gate、save revision、
seed 0 mixed、seed 1 passed-complete、seed 2 failed、seed 3 all-skipped、diagnostic 跳转到
`tasks/test.json` 与 field breadcrumb、seed change stale、seed 409 current conflict、显式
Reload Remote 后回到 clean Not run。initializer/environment/evaluator、Agent execution、
device、plugin construction、model、network、secret、Experiment、TaskRun/result、report/
Replay、Contract Test、publication/migration/export 和 Android 共 15 个禁止业务边界计数
全部为 0。

浏览器控制器会阻止直接把 raw sentinel JSON 作为页面打开，因此 sentinel 在同一次 smoke
server session 中通过 read-only loopback HTTP 验证；可见产品旅程本身全部由真实浏览器
执行。这不把浏览器工具自身网络行为描述为产品能力。

### OpenSpec 与范围审计

```bash
openspec validate implement-studio-benchmark-contract-tests-5-5d --strict
# Change 'implement-studio-benchmark-contract-tests-5-5d' is valid
```

proposal、specs、design、tasks、实现和永久文档已按 exact-revision ownership、coverage
semantics、trust boundary、case/result bounds、5.5C compatibility 与 5.5E handoff 逐项
对齐。新/改 Python 函数的 docstring 审计未发现缺失。

## 设计取舍、限制与失败情况

- 选择 server-owned reviewed fixtures，不执行 Package code；代价是第三方 logical
  reference 没有 fixture 时必须诚实 `skipped`；
- 选择可信进程内 lightweight fixtures，而不是 subprocess/container sandbox；速度和可移植
  性更好，但不能硬终止恶意/卡死 third-party code，所以 registry 不是开放执行入口；
- 选择 Plan identity 在 result owner、member identity 在 case seed；既保留 exact-result
  provenance，又避免无关 case 改变已有 seed；
- 选择 pre-discovery 1,000 cap 和 sequential stable execution；避免 partial authority，
  但超大 Package 必须先缩小 split/definition；
- 选择 disposable mutation/session，不持久 result；避免旧事实伪装成 current，代价是刷新
  或 Reload 后需要重跑；
- evaluator normalization 只证明兼容边界接受 fake output，不证明真实 evaluator、模型或
  Android 结果正确；
- fresh scopes 和重复输出只能发现可观察泄漏，不能证明所有隐藏状态隔离；
- 没有 revision `validated` promotion、publish/migrate、real-device profile、worker matrix
  扩展、PostgreSQL、object storage、retention/delete 或 Android acceptance。

## 手工复验

```bash
cd studio
npm run build
npm run smoke:benchmark-authoring
```

打开 fixture 输出的 seed draft URL，并追加 `?mode=contract-tests`：

1. 初始显示 Not run，且不会自动发起 Contract Test；
2. 在 Definition 修改字段后 Run 被 dirty gate 禁用，Save 后才恢复；
3. 选择 profile、split 和 seed，显式 Run 后能区分 passed/failed/skipped/mixed；
4. 点击 diagnostic 能回到 exact task member 和安全 breadcrumb；
5. 改 seed、save/content、Reset、Reload 或收到 409 后旧结果失去 authority；
6. 页面始终显示 in-process fake/no-device/no-publication/unvalidated 边界。

常见失败：未知 profile 或 malformed body 为 400；foreign draft 隐藏为 404；409 需要
Reload Remote；413 没有 partial result；503 表示服务/存储不可用；missing fixture 是
skipped 而不是 failed/pass。

## 当前下一步

原 5.5E 已永久拆为三个顺序 Change。5.5E-1
`implement-studio-benchmark-validated-freeze-5-5e1` 已通过重新验证 exact current
revision 的全部 split 和 closed content closure，以独立 attestation 冻结 immutable
Package revision；当前下一项固定为 5.5E-2 explicit publish/export，5.5E-3 才提供
preview/diff/confirm legacy Benchmark JSON migration。5.5D fake-fixture pass 不能单独
作为 freeze/publication 资格或真实执行证明。

## 事实来源

- 用户在既有 Stage 5.5 颗粒度上，根据已验证代码边界将原 5.5E 细分为 validated
  freeze、publication/export 与 legacy migration，使总数调整为十个，并保持依赖
  顺序与声明边界；
- 5.5A/B/C、Core Benchmark authoring、Catalog/worker/reporting 是此前验证事实；
- Coding Agent 实现并运行了本 Change 的 Core runner、shared compiler、strict DTO/HTTP、
  React feature、smoke fixture、自动化、clean-wheel、真实浏览器和本文档；
- requirement、design 与完整 acceptance scenario 保存在对应 OpenSpec Change 中。
