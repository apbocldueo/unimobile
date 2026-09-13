# Studio Benchmark Legacy Migration

本文记录 Stage 5.5E-3
`implement-studio-benchmark-legacy-migration-5-5e3` 的已实现边界、设计、验证证据与
限制。它描述的是 2026-08-02 在本仓库验证过的 legacy `BenchmarkTask` JSON
迁移能力；迁移只创建新的 `unvalidated` authoring draft，不是 validation、Contract
Test、freeze、publication、export、execution 或真实 Android 证明。

## 解决的问题与输入边界

旧版独立 `BenchmarkTask` JSON 数组仍是受支持合同，但 5.5A–E-2 的 authoring
资源面只接受 schema-1 Package document、私有 template/Catalog import 和 frozen
Package。直接把浏览器路径交给服务端、让普通 create endpoint 接受 raw JSON，或在
导入时静默修补旧字段，会绕过 Preview 审阅、破坏来源身份，并让兼容入口与 Package
authoring 责任混在一起。

E-3 增加一个单独的 bounded migration boundary：

- 浏览器读取用户明确选择的文件并提交 UTF-8 `sourceText`，服务端不接受 host path、
  URL 或 destination；
- source 最大 1 MiB，数组最多 100 个 entry，diagnostic 最多 100 条；
- 只接受 standalone `BenchmarkTask` V1；pre-V1/rejected fields、非有限 JSON、
  unsafe authoring values、重复 task ID 或不合法结构使 Preview non-confirmable；
- task mapping 与 source order 原样保留，不 rename、drop、deduplicate 或 semantic
  rewrite；JSON canonical representation 的变化单独报告；
- Package wrapper 的 publisher/name/version/title/platform/split/task member 全部由用户
  显式输入；不会发明 Protocol、default Protocol、ground truth、resource bytes；
- plugin declaration 只从 initializer、environment setup/reset/cleanup 和 evaluator
  leaf 的现有显式引用机械推导；App login 信息不完整时保守留作 post-migration work。

App 登录投影使用确定规则：任一 task 明确 `requires_login=true` 则声明 true；同 App
全部明确 false 才声明 false；存在未声明事实且没有 true 时不生成确定声明，而是要求
作者后续审阅。

## Preview / Confirm 执行流

```text
Browser-selected File
  -> browser reads exact UTF-8 text
  -> POST legacy-migrations/preview
  -> pure bounded V1 analyzer
  -> source facts + diagnostics + structured diff + post work
  -> no durable write, no capability acquisition

Explicit Confirm
  -> resubmit exact source + complete target + Preview authority + request ID
  -> server reruns complete analyzer
  -> compare current migration contract and recomputed Preview fingerprint
  -> existing atomic find-or-create authoring command
  -> new draft + ordinal-1 immutable unvalidated revision
  -> legacy_migration provenance
  -> authoritative editor navigation
```

Preview service receives no repository or runtime capability。Confirm service 只持有现有
authoring repository 与 pure analyzer；它不持有 managed-content upload、Catalog source、
validation、Contract Test、freeze/release、worker、device、Agent、model、secret、
Experiment、report/trajectory 或 Replay boundary。

## Identity 与 durable authority

迁移有四层显式 SHA-256 identity：

- `sourceFingerprint`：exact submitted UTF-8 bytes，空白与 object-key representation
  的变化也会改变它；
- `migrationContractIdentity`：版本化的 source/task/plugin/App/Package/evidence
  transformation policy；
- `candidateDocumentFingerprint`：完整 schema-1 candidate authoring document；
- `previewFingerprint`：source、完整 target intent、migration contract 与 candidate
  document 的闭包。

Confirm 的 command fingerprint 还绑定 `clientRequestId` 与上述完整 authority。相同请求
在响应丢失后返回原 draft/revision；相同 request ID 搭配改变后的 source/target/authority
安全冲突。服务端在任何 durable mutation 前重新运行 analyzer，因此旧 Preview、修改后的
文件、target drift 或 contract drift 都不能创建 draft。

成功 revision 的 provenance 只保存 bounded display/identity facts：source basename、
source/Preview/document/contract fingerprints 与 entry/unique counts。它不保存 source
text、host path 或文件 capability。E-3 复用 SQLite schema 10 与既有 atomic authoring
command/draft/revision/current-pointer 事务，没有 schema 11 或旧行 rewrite；重启从 durable
revision/provenance 重建，不再读取原文件。

## Structured diff 与 truthfulness

Preview 返回：

- source name、UTF-8 size、entry/unique counts、source fingerprint；
- retained/renamed/removed/deduplicated/rewritten counts；除 retained 外固定为 0；
- wrapper、declaration、omission、representation 四类 bounded diff entry；
- mechanically derived plugin/App IDs；
- source-index、field-path 与 bounded task ID 诊断；
- Protocol、ground truth、resource/login 等 explicit post-migration work；
- validation、Contract Test、freeze、publication、export、execution 与 device 全部 false。

AppAgent canonical source得到 45 entries / 45 unique，全部 retained；AndroidWorld legacy
source包含 82 entries / 81 unique，第二个 `AndroidWorld_72` 位于 source index 72，因而
non-confirmable。这个结果不会把 duplicate 自动删成现有 81-task Package。

## HTTP resources 与安全

```text
POST /studio/benchmark-authoring/legacy-migrations/preview
POST /studio/benchmark-authoring/legacy-migrations/confirm
```

Preview 成功返回 200；Confirm fresh create 返回 201，exact replay 返回 200，stale
Preview/contract 或 command reuse conflict 返回 409。unknown fields、unsupported schema、
method/query、malformed safe name/Package identity/task path、non-object body 与 oversized
source 使用 bounded error envelope。两条 route 都是 private/no-store，并继承 Studio
loopback Host、Origin/CORS 与 request-size policy。响应与请求日志不回显 source text、
host path、internal exception、secret、content capability 或 live object。

普通 `POST /studio/benchmark-authoring/drafts` 的 template/Catalog source union 仍然关闭；
raw text 或 `legacy_migration` 不能绕过 Confirm。

## React ownership 与用户流程

`/benchmark-authoring` 在既有 Template/Catalog forms 旁提供独立 Legacy JSON card；它不向
`/benchmark-drafts/:draftId/edit` 增加 migration mode。

- TanStack Query 只拥有 Confirm 后的 authoritative draft/revision；Preview 不进入 query
  cache，也不乐观合成 draft；
- feature-local Zustand session 保存 selected `File`、source text、target form、generation、
  当前 Preview owner 与 uncertain Confirm intent；组件卸载/刷新会全部清空；
- file replacement 或任一 target edit 立即递增 generation、清空 Preview 与 Confirm
  authority；late Preview 只有 owner generation 仍匹配时才能采用；
- Confirm request ID 只在完整 semantic key 未变化且结果不确定时复用；409 会废弃
  Preview 并要求重新 Preview；
- fresh/replayed authoritative success 才更新 query caches、invalidate draft pages，并导航
  到 `/benchmark-drafts/:draftId/edit` 由现有 editor 重新 hydrate。

界面持续显示 definition-only banner、source/diff/diagnostic/post-work facts 与 false evidence，
non-confirmable Preview 的 Confirm 按钮保持禁用。

## 验证证据与复现

最终观测到：

- focused analyzer/model/service/repository/provenance：`25 passed`；
- migration real-HTTP contract：`3 passed`；
- authoring/HTTP/Package focused regression：`167 passed`；
- complete backend：`794 passed`；
- complete frontend：`88 test files / 390 tests passed`；
- TypeScript typecheck、ESLint 与 Vite production build 通过；build 保留既有的单 chunk
  大于 500 kB 提示；
- repository-independent clean-wheel Preview→Confirm→restart acceptance：`1 passed`；
- no-device real-browser journey完成 AppAgent file select、45/45 Preview、structured review、
  target edit/stale、re-Preview、Confirm/navigation、backend disconnect uncertain retry、
  AndroidWorld 82/81 duplicate rejection 与 refresh disposal；浏览器 console error 为 0；
- browser临时 SQLite 中 authoring drafts 为 2，Experiment、artifact、Replay、frozen
  Package、publication 与 export 都为 0；clean-wheel service capability 只有 repository
  与 analyzer；canonical source digest 前后相同。

可复现命令：

```bash
uv run --extra dev python -m pytest -q \
  tests/studio/test_benchmark_authoring_migration.py
uv run --extra dev python -m pytest -q \
  tests/studio/test_benchmark_http.py -k legacy_migration_http
PYTHONPATH=tests uv run --extra dev python -m pytest -q
PYTHONPATH=tests uv run --extra dev python -m pytest -q \
  tests/packaging/test_benchmark_authoring_install.py \
  -k migrates_legacy_json

cd studio
npm test
npm run typecheck
npm run lint
npm run build
```

裸完整 pytest 不含 `PYTHONPATH=tests` 时，三个既有 runtime module 无法解析
`tests/graph` helper；正式入口必须设置该变量。受限 sandbox 还需要允许 loopback socket
与 isolated-wheel dependency install。

手工启动：

```bash
PYTHONPATH=tests uv run python -m zhixing.studio serve \
  --host 127.0.0.1 --port 8765 --database /tmp/zhixing-studio.sqlite3
cd studio && npm run dev -- --host 127.0.0.1
```

访问 `http://127.0.0.1:5173/benchmark-authoring`，选择 JSON 后显式 Preview；改变任一
target 后旧 review 应立即消失。AppAgent 应显示 45/45；AndroidWorld legacy source 应
显示 82/81、`AndroidWorld_72` 和 `source[72]`，且 Confirm disabled。Confirm 成功后
editor 应显示 `unvalidated` 与 `legacy_migration` provenance。

## 取舍、失败模式与限制

- 选择 source text 而不是 server-side path：1 MiB body 会重复提交，但消除了任意文件
  读取与路径 authority；
- 选择 complete reanalysis 而不是信任 Preview cache：Confirm 多一次纯分析成本，但不会
  接受 drifted source/target/contract；
- 选择 exact task preservation 而不是自动升级：作者仍需处理 duplicate、Protocol、ground
  truth、resource 与 login facts，但迁移不会悄悄改变 Benchmark 语义；
- Preview 是 transient，刷新后必须重新选择文件；source bytes 不持久化意味着服务端不能
  在没有用户输入时重放 Preview；
- trusted V1 plugin identifier 只作为 declaration metadata；迁移不 import、instantiate 或
  sandbox plugin code；
- 没有批量目录/URL migration、pre-V1 converter、自动 merge、自动 Protocol/ground-truth
  synthesis、content upload、migration history、delete/retention 或 object storage；
- 当前 worker 仍限制一个 Agent、一个 Task、一个 repeat；E-3 没有扩大执行 cardinality；
- 所有 evidence false，所以成功迁移不能支持执行质量、设备兼容、统计或真实 Android 声明。

## 事实归属

- Stage 5.5 拆分、迁移守恒规则、Preview/Confirm 权限边界与证据限制来自用户固化路线和
  OpenSpec；
- Coding Agent 完成代码、测试、clean-wheel、真实浏览器旅程、永久文档与验证命令；
- 未验证的 Stage 5.6 multi-cardinality/real-Android 能力没有写成完成事实。
