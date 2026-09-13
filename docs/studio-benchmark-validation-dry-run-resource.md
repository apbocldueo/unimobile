# Studio Benchmark Validation / Dry-run Resource

本文记录 Stage 5.5C-1
`implement-studio-benchmark-validation-dry-run-resource-5-5c1` 的实际实现、验证证据和
边界。它把 exact current Benchmark authoring revision 接到已有 Core
validate/dry-run 语义，但不执行 initializer、evaluator、Agent、设备或 Experiment。

## 状态与范围

截至 2026-08-01，本 Change 已实现并验证：

- revision-bound schema-1 validation/dry-run request 与 response DTO；
- exact draft/revision ownership、分析前与返回前两次 current-pointer 检查；
- 私有、一次性、closed-inventory Benchmark Package 重建和全路径清理；
- 最多 100 条、确定性排序、字段可定位且不泄露私有路径/内容 identity 的 diagnostics；
- 分阶段且独立门控的 Package、Package content、BenchmarkPlan、
  ExperimentProtocol identity；
- 1–16 个 immutable Agent revision 的重新验证与 AgentGraph canonical identity
  重算，且不信任调用方 hash；
- 最多 100 个显式 task、空选择表示整个 split、最多 10,000 条完整 schedule 的
  deterministic dry-run；
- budget、fairness warning、相对 output layout、dynamic materialization 与 current
  worker scope 的显式 unverified facts；
- strict same-origin HTTP POST、bounded errors、`private, no-store`；
- schema 8 不变、无 migration、无持久 validation cache、无 authoring revision
  状态变更；
- focused、完整相关回归、clean-wheel、restart、HTTP 全链路副作用 canary 和
  OpenSpec strict validation。

本 Change 没有实现 React Validation mode、Contract Test、publish/migrate、Worker
扩容、真实 Android acceptance、PostgreSQL、object storage 或 retention/delete。
`BenchmarkTask` JSON 与 `AgentConfig`/`AgentGraph` 继续保持独立合同。

## Agent / Benchmark 问题与前后流程

5.5A–5.5B-3 已能安全保存 definition 与 managed content，但 revision 始终只是
`unvalidated`。已有 CLI validate/dry-run 又面向文件系统 Package 与 Agent YAML，不能
直接把浏览器 draft、私有 content identity 或调用方声称的 AgentGraph hash当权威。

```text
before
  immutable authoring revision ──→ durable definition/content facts
  Core Package validate/dry-run ──→ filesystem Package / Agent input
  两条路径没有 revision-bound、side-effect-free 的服务桥接

after
  POST draft/{draftId}/validate|dry-run
                 │
          exact-current check #1
                 │
     private disposable Package materialization
       ├─ deterministic definition members
       └─ verified managed-content streaming
                 │
       Core parse / compile / pure projection
       ├─ independently gated identities
       ├─ field-addressable diagnostics
       └─ immutable Agent revision verification
                 │
          exact-current check #2
                 │
      bounded definition-level facts only
                 │
         disposable tree removed

  initializer / evaluator / device / runtime / result ── never entered
```

双重 current check 防止分析期间并发保存后返回看似仍属于 current revision 的结果。
它不锁住编辑操作；代价是发生并发推进时丢弃已完成的临时分析并返回 409。

## 分层与责任

- `benchmark_authoring_analysis_models.py`：strict request/result、diagnostic、identity、
  Agent verification、schedule/budget/warning/layout DTO 与容量常量；
- `benchmark_authoring_errors.py`：安全的 400/404/409/413/503 domain errors；
- `benchmark_authoring_materializer.py`：一次性 Package、closed inventory、verified
  streaming、fsync 与 cleanup；
- `benchmark_authoring_analysis.py`：exact-current application service、phased
  compilation、Agent revision verification 与 pre-allocation cardinality gate；
- `zhixing/benchmark/loaders.py`：保留 task aggregate index 到原 member/local index 的
  provenance，使第二个 task file 的错误仍能定位到原文件；
- `zhixing/benchmark/authoring/dry_run.py`：从已验证 Plan/Protocol/Agent facts 生成纯
  schedule projection，CLI 与 Studio 共用；
- `benchmark_composition.py` / `httpd.py`：仅在 durable authoring/content 已配置时
  组合服务，并复用既有 Host、Origin、body、response 安全边界。

该分层没有把 authoring revision 伪装成 published Package revision，也没有建立第二套
compiler 或前端自算 identity。

## 已验证合同

### 1. Exact current、ownership 与持久状态不变

每个命令必须提交 `revisionId` 和显式 `split`。revision 必须属于 URL 中的 draft 且在
分析开始和返回前都仍是 current。foreign owner 返回 404；stale 返回 409，且只携带安全
的 current revision identity。

重复 validation 返回字节稳定的同一结果，draft current pointer、revision ordinal、
document fingerprint 和 `unvalidated` 状态均不改变。没有 command idempotency row、
validation cache、new revision 或 migration。

### 2. 私有一次性 Package 与完整性闭包

materializer 在 server-owned staging namespace 内创建新目录，确定性序列化 manifest、
task files 和 Protocol files，再通过既有 `open_verified` 边界流式复制 revision 声明的
managed resource。它同时守住：

- normalized Package-relative path 与 closed declared inventory；
- regular-file、content identity、SHA-256、size 和 aggregate capacity；
- definition/member byte limits；
- partial write、flush、compiler exception、missing/corrupt content 和正常返回后的清理。

missing resource 可成为 logical resource diagnostic；digest/size/identity drift、symlink、
unsafe storage 或无法安全 cleanup 均 fail closed。公共 DTO、error 和 diagnostic 不返回
host path、temporary path、private content identity、secret 或 raw bytes。

### 3. Diagnostics 与独立 identity 门控

validation 尽可能聚合 manifest、split、task、Protocol、resource、ground truth 与
metadata-only plugin-reference 问题，而不是只返回第一个错误。每条 public diagnostic
有 stable code/severity/message、semantic member kind、已验证的 Package-relative
member path、member-local field path 与可适用的 task/resource/Agent/revision identity。

结果最多 100 条，排序固定，截断显式。语义无效仍是 HTTP 200 的 `valid=false`，且只
返回实际建立的 identity：

- manifest 成功后才有 Package identity；
- closed declared closure 完整验证后才有 Package content identity；
- selected split 成功编译后才有 BenchmarkPlan identity；
- default Protocol 成功解析后才有 ExperimentProtocol identity。

focused fixture 的 Package identity 为 `tests/analysis@0.1.0`；clean-wheel fixture 为
`tests/wheel-analysis@0.1.0`。content/Plan/Protocol/AgentGraph identities 均为既有 Core
canonical `sha256:` identity，并在重复调用与 restart 后保持相等；没有新增替代 hash。

### 4. Immutable Agent revision 与 deterministic dry-run

dry-run 接受 1–16 个显式 Agent/revision pair。每个 immutable revision 都通过既有 Studio
verifier 重新编译/核对 snapshot 和 canonical AgentGraph identity；missing、foreign、
invalid snapshot/graph 或 canonical mismatch 形成 Agent-addressed failure，并阻止 schedule。
同一 Agent 的两个 revision 不会被折叠，而是在 schedule 前拒绝。

空 `taskIds` 表示 selected split 全部任务；非空选择必须唯一、最多 100 个且都属于该
split。服务在调用 schedule builder 前计算 `repeats × tasks × Agents`：大于 10,000 返回
413 且不分配 partial schedule；恰好 10,000 返回完整确定性 schedule。结果复用既有 seed、
ordering、budget、fairness 与 relative output-layout semantics。

多 task、repeat 或 Agent 的 schedule 只是 definition-level preview。响应明确带
`current-worker-cardinality` unverified fact；这不证明当前 single-worker Experiment
路径能执行该矩阵。

### 5. HTTP 与副作用边界

canonical resources 是：

```text
POST /studio/benchmark-authoring/drafts/{draftId}/validate
POST /studio/benchmark-authoring/drafts/{draftId}/dry-run
```

服务也沿用既有 `/api` 前缀归一化。它拒绝 query、unknown envelope 字段、destination、
content identity、device profile、secret 或 runtime option。状态语义为：400 malformed、
404 hidden ownership/unconfigured、409 stale、413 request/output capacity、503 private
analysis storage/integrity unavailable、405 known route wrong method；语义 invalid 是 200。
成功与错误 JSON 均有 bounded serialization；私有结果设置
`Cache-Control: private, no-store`。

完整 HTTP journey 在以下边界安装 fail-fast canary：initializer、environment、evaluator、
device、Agent execution、plugin construction、model、network、secret、Experiment、
TaskRun/result、report、trajectory/bundle、Replay、publication、migration、export 和
Android。唯一允许的网络连接是测试客户端到其 exact loopback fixture；所有业务 canary
计数均为 0，analysis staging 最终为空。

## 验证证据

### Focused 与完整相关回归

```bash
uv run pytest -q \
  tests/studio/test_benchmark_authoring_analysis.py \
  tests/studio/test_benchmark_http.py \
  tests/benchmark/test_authoring.py \
  tests/benchmark/test_compiler_catalog_cli.py \
  tests/benchmark/test_models_identity.py
# 68 passed in 7.62s

uv run pytest -q tests/studio tests/benchmark
# 412 passed in 31.07s
```

这些 suite 覆盖 strict DTO、diagnostic redaction/cap、multi-file provenance、exact-current
race、missing/corrupt resource、cleanup/fault injection、partial identity、Agent revision、
CLI/Catalog/canonical identity、legacy BenchmarkTask、Experiment preview/create、worker
regression，以及完整 HTTP 状态矩阵。

### Clean wheel、restart 与 schema

```bash
uv run pytest -q \
  tests/packaging/test_benchmark_authoring_install.py::\
test_installed_wheel_runs_revision_bound_validation_and_dry_run
# 1 passed in 9.13s
```

测试在 repository-independent working directory 中只从安装后的 wheel import，实际覆盖
valid、invalid、missing resource、stale current、Agent revision failure、exact 10,000
schedule、重复分析、restart identity reconstruction，并查询
`studio_schema_migrations` 的 `MAX(version) == 8`。analysis staging 结束为空，证明本
Change 没有引入 schema 9 或 durable analysis object。

### 静态与 OpenSpec 校验

```bash
uv run python -m compileall -q \
  zhixing/studio/benchmark_authoring_analysis_models.py \
  zhixing/studio/benchmark_authoring_errors.py \
  zhixing/studio/benchmark_authoring_materializer.py \
  zhixing/studio/benchmark_authoring_analysis.py \
  zhixing/studio/benchmark_composition.py \
  zhixing/studio/httpd.py \
  zhixing/benchmark/loaders.py \
  zhixing/benchmark/authoring/dry_run.py
# passed

openspec validate \
  implement-studio-benchmark-validation-dry-run-resource-5-5c1 --strict
# Change 'implement-studio-benchmark-validation-dry-run-resource-5-5c1' is valid
```

对本 Change 修改的 Python functions 执行 AST docstring audit 后，purpose 与适用的
Args/Raises/Returns 均完整；active-change scoped whitespace/diff check 通过。

## 设计取舍、限制与失败情况

- 选择 disposable reverse adapter，而不是让 Core compiler 读取数据库/content store：
  最大化复用现有 Package 语义，代价是每次复制受限 managed bytes 和额外临时 I/O；
- 选择双 current check，而不是长事务锁：不阻塞 authoring writer，代价是并发推进时
  已完成分析被丢弃；
- 选择独立门控 identity，而不是 all-or-nothing response：invalid definition 仍能给出
  已证实的上游事实，代价是客户端必须处理 partial identity；
- 选择 metadata-only plugin check：不会 import/construct third-party code，代价是无法
  证明的 availability 必须显示为 unverified；
- 选择 pre-allocation 10,000 固定上限而不是 silent truncation：结果完整且可解释，未来
  调整必须版本化；
- output layout 只是安全相对 projection，不创建目录、report、trajectory 或 bundle；
- dynamic parameters、rendered instruction、TaskInstance、live App/device state、evaluator
  outcome 和 runtime success 均缺席或 unverified；
- analysis 仍不把 revision 标记为 `validated`，也不使其 runnable/publishable；该 lifecycle
  属于 5.5E；
- 没有 React Validation view、Contract Test/process sandbox、worker expansion、真实设备、
  PostgreSQL/object storage 或 retention/GC 证据。

## 当前下一步

下一项固定为
`implement-studio-benchmark-validation-dry-run-view-5-5c2`：在本后端资源之上增加
URL-owned React Validation mode、clean saved-baseline gate、immutable Agent revision
选择、revision-bound stale-result 丢弃、diagnostic navigation，以及对 partial
identities、schedule、budget、fairness 和 unverified facts 的诚实展示。它不得新增
execution、Contract Test、publish 或 migration 控件。

## 事实来源

- 用户决定并固化了当时的 Stage 5.5 executable change 顺序与 truthfulness boundary；
- Core validate/dry-run、canonical identity、Agent revision verifier 与 authoring/content
  resources 是此前已验证的项目事实；
- Coding Agent 实现并运行了本 Change 的 service、DTO、materializer、HTTP、Core reuse、
  tests、clean-wheel、OpenSpec 校验与本文档；
- requirement 和完整验收场景保存在该 OpenSpec Change 中。
