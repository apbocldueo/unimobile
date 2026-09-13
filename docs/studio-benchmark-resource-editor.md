# Studio Benchmark Resource Editor

本文记录 Stage 5.5B-3
`implement-studio-benchmark-resource-editor-5-5b3` 的实际实现、验证证据与已知边界。
它把 5.5B-2 已验证的 managed-content 命令接入 5.5B-1 draft workbench，提供
React 资源编辑体验；它不是 Benchmark validation、execution、publication 或
migration 的完成声明。

## 状态与范围

截至 2026-07-31，本 Change 已实现并验证：

- draft editor 的 URL-owned `definition` / `resources` 两种模式，`definition` 为安全
  默认值，直接访问和刷新均可重建资源模式；
- strict schema-1 upload/replace/logical-remove response 解析，以及 exact
  draft/revision/resource `HEAD` 可用性检查；
- asset 与 file-backed ground truth 的分组 inventory、新资源上传、保持逻辑
  identity/path 的 replacement、missing-content repair 和显式确认的 logical remove；
- clean saved baseline gate：dirty、invalid/unapplied task buffer、definition save、
  content pending、conflict、remote-newer 与 revision mismatch 均 fail closed；
- byte-bound 命令重试 identity：只有 operation、owner、base revision、metadata 和
  同一个浏览器 `File` 都未改变时才复用 `clientRequestId`；
- aligned success 使用返回的 immutable revision 重建 definition/resource 会话；
  historical exact retry 先保留历史 revision cache，再权威读取 current pointer，
  不回退当前编辑器；
- lazy selected-resource `HEAD`，分别显示 unchecked、pending、readable、404
  missing、unavailable 与 header-contract failure；
- focused/full Studio、typecheck、lint、独立临时目录 production build、5.5A/
  5.5B-2 backend regression 和 no-device real-browser journey。

本 Change 没有修改 Python backend、Benchmark runtime、AgentGraph runtime、device、
initializer/evaluator、plugin/model/secret、Experiment、Report、Replay、validation、
publication、migration 或 export 行为。`BenchmarkTask` JSON 与
`AgentConfig`/`AgentGraph` 仍是独立合同。

## 用户问题与前后流程

5.5B-2 已提供安全的 managed-content capability，但 5.5B-1 React inventory 仍只读。
真正的难点不是上传控件，而是不能让浏览器从脏 definition、过期 revision 或不确定
网络结果发出不可解释的字节命令。

```text
before
  React definition editor ──→ read-only resource metadata
  5.5B-2 HTTP             ──→ upload / replace / logical remove / exact HEAD
  两者尚未形成安全用户流程

after
  /benchmark-drafts/:draftId/edit?mode=resources
                    │
                    ├─ TanStack Query: current draft/revision + server facts
                    ├─ definition store: saved baseline + working document
                    └─ resource feature: selected File / confirmation / retry intent
                                      │
                             clean-baseline gate
                                      │
                  raw File command + base revision + request identity
                                      │
                strict response ──────┼────── 409 / failure
                    │                 │          └─ preserve local state
                    ├─ aligned result ───────→ adopt exact returned revision
                    └─ historical retry ────→ cache returned revision
                                              refetch authoritative current
```

## 分层与状态所有权

实现遵守 [Studio frontend architecture](studio-frontend-architecture.md)：

- `shared/api`：新增通用 raw-body JSON transport；设置调用方给出的 media type，
  `Content-Length` 仍由浏览器管理，并保留 bounded error envelope 与 abort；
- `entities/benchmark-authoring`：strict DTO/parser、owner-scoped API、exact `HEAD`、
  TanStack Query keys/mutations 和 current non-regression cache reconciliation；
- `features/benchmark-resource-editor`：命令 intent、clean gate、availability projection、
  bounded transient session 和资源编辑 UI；
- `features/benchmark-definition-editor`：继续独占 baseline、working document、raw task
  buffer、dirty/conflict，并新增 definition save-pending 事实；
- `widgets/benchmark-definition-workbench`：拥有 URL mode，组合两个 feature，处理
  content success/conflict 与 definition rehydrate；
- `pages` / `app`：继续只提供稳定 draft route，不新增独立资源 bearer route。

服务器状态只在 TanStack Query；definition 编辑态只在 definition feature store；
文件、移除确认、错误和未确认命令 identity 只在 resource feature。两个 peer feature
不互相 import，由 widget 通过公开 props/callbacks 组合。

## 已验证合同

### 1. raw-body 与 strict response

upload/replace 直接发送浏览器 `File`/`Blob`，不做 JSON/Base64 包装；remove 发送零
body。调用方只设置权威 media type，浏览器生成 `Content-Length`。所有成功 payload
在进入 cache/UI 前经过 strict parser；未知 envelope key、错误 operation、owner
不一致、resource projection 不一致或 remove 后资源仍存在都会 fail closed。

`contentIdentity` 仍只是 metadata。前端没有从它构造 GET/HEAD/download capability，
exact read 必须同时拥有 draft、immutable revision 和 logical resource identity。

### 2. clean saved baseline gate

资源命令只有在以下事实同时成立时可发出：

```text
saved baseline exists
  AND query current exists
  AND baseline == query current
  AND definition clean + parsed + applied
  AND no definition save/content command pending
  AND no conflict/remote-newer fact
```

因此用户必须先 Save 或 Reset definition。资源命令 pending 时 definition Save/Reset 和
第二个资源命令也被阻止，避免两个 revision writer 在浏览器内竞争。

### 3. 命令重试与 current non-regression

不确定的 5xx/网络结果保留命令 intent 和本地 `File`。完全相同的重试复用
`clientRequestId`；metadata、File object、operation、draft 或 base revision 任一变化
都会退休旧 identity。

服务端 exact retry 可能返回第一次已提交的历史 revision，同时 draft current 已被
别的提交推进。前端始终缓存这个 exact immutable revision，但不会用它覆盖 current
detail；而是读取权威 current，再用最新 revision 重建 definition baseline、working
document 和资源会话。该设计牺牲一次额外 GET，换取不回退当前编辑状态。

### 4. inventory、availability、replace 与 remove

inventory 只显示 current immutable revision 的 server-owned descriptor，按 asset /
file-backed ground truth 分组并确定性排序。选中资源时才发 exact `HEAD`，不进行
inventory-wide N+1 探测。

- readable：展示响应验证后的 media type、size 与 filename；
- missing：明确声明仍存在且可用 replacement 修复；
- unavailable/header failure：不猜测可读性，允许显式 Retry HEAD；
- replacement：保留 logical ID/kind/path，只接受服务端返回的新 size/digest/content
  identity；
- logical remove：需要确认，只在新 revision 移除声明，不重写 manifest/task 引用，
  不删除旧 immutable revision 仍需的字节。

上传、替换和移除后的 revision 仍明确显示 `unvalidated`。UI 没有 preview/download，
也不把文件存在或摘要匹配描述为 Benchmark 语义正确。

### 5. 冲突、失败与会话清理

409 保留用户选择的文件与本地 definition，建立 conflict/remote-current 事实并要求
显式 `Reload Remote`。capacity/storage/5xx、malformed response 和 availability
失败不会乐观修改 inventory。draft/revision 改变或 selected resource 被移除时，
过期 selection、File、确认框、错误和 retry intent 都会被清理；file input 按
revision remount，避免浏览器控件残留旧文件名。

## 验证证据

### Frontend focused 与全量自动化

```bash
cd studio

npm test -- --run \
  src/shared/api/httpClient.test.ts \
  src/entities/benchmark-authoring/model/benchmarkAuthoring.schema.test.ts \
  src/entities/benchmark-authoring/api/benchmarkAuthoringApi.test.ts \
  src/entities/benchmark-authoring/api/benchmarkAuthoring.queries.test.ts \
  src/features/benchmark-resource-editor/model/benchmarkResourceModels.test.ts \
  src/features/benchmark-resource-editor/ui/BenchmarkResourceEditor.test.tsx \
  src/features/benchmark-definition-editor/model/benchmarkDefinitionEditorStore.test.ts \
  src/widgets/benchmark-definition-workbench/BenchmarkDefinitionWorkbench.test.tsx \
  src/pages/benchmark-draft-edit/benchmarkAuthoringRoutes.test.tsx
# 9 files passed, 57 tests passed

npm test
# 70 files passed, 309 tests passed

npm run typecheck
# passed

npm run lint
# passed

tmp_output="$(mktemp -d /private/tmp/zhixing-studio-b3-dist.XXXXXX)"
npm exec vite -- build --outDir "$tmp_output"
# passed; 593 modules transformed
# JS 929.94 kB, gzip 273.31 kB
# Vite retained the existing >500 kB chunk-size warning
```

focused tests 覆盖 raw transport、strict/malformed parser、URL encoding、零 body、
cache non-regression、intent reuse/retirement、clean gate、availability、session cleanup、
upload/file-backed ground truth、missing repair、replace、confirmed remove、dirty/pending/
conflict、URL mode、aligned/historical rehydrate，以及不存在 content-identity capability。

### 5.5A / 5.5B-2 backend regression

```bash
UV_CACHE_DIR=/private/tmp/zhixing-uv-cache uv run pytest -q \
  tests/studio/test_benchmark_authoring_resource.py \
  tests/studio/test_benchmark_authoring_content.py
# 56 passed

UV_CACHE_DIR=/private/tmp/zhixing-uv-cache uv run pytest -q \
  tests/studio/test_benchmark_http.py
# 8 passed
```

HTTP suite 需要绑定本机临时回环端口；受限沙箱中会在 fixture setup 阶段得到
`PermissionError`，允许 loopback bind 后重跑为 8/8。该结果证明前端消费既有
backend contract；本 Change 没有修改 runtime 或 Python package，因此未将
clean-wheel 作为本 Change 的完成证据。

### no-device real-browser journey

fixture 支持通过 `ZHIXING_AUTHORING_FIXTURE_DIST` 指向独立 production build：

```bash
cd studio
ZHIXING_AUTHORING_FIXTURE_DIST=/private/tmp/<build-dir> \
  node scripts/benchmark-authoring-smoke-fixture.mjs
# http://127.0.0.1:8766/benchmark-authoring
```

真实 in-app Chromium 中实际观察到：

1. 直接访问 `?mode=resources` 并在刷新后保持资源模式；
2. definition Title 变脏后切回资源页，upload 被阻止并给出具体原因；
3. 上传 file-backed ground truth 后只用服务端返回事实生成 revision 2；
4. 选中资源时才执行 exact `HEAD`，404 missing 与 readable 状态分离；
5. 用 replacement 修复 seed missing asset，生成 revision 3；
6. 显式确认 logical remove，生成 revision 4 且 inventory 清除当前声明；
7. `retry-asset` 第一次提交已落盘但 fixture 返回 503，页面保持不确定状态；
8. 未改变输入再次提交复用 request identity，收到历史 result 后重新加载 current
   revision 6，没有回退到命令 revision；
9. 应用页面 console error 为 0。

这是确定性的 no-device product journey，不是 production storage、多用户竞争、真实
Android、任意文件安全或大规模上传证据。

## 设计取舍、限制与失败情况

- 选择 clean-baseline gate，而不是让 definition/content 两类写入并行：revision
  历史更可解释，但用户需要先 Save 或 Reset；
- 选择 exact retry + authoritative current GET，而不是相信 retry response 的 current
  revision：避免状态回退，代价是历史 retry 多一次请求；
- 选择 selected-only `HEAD`，而不是预探测整个 inventory：避免 N+1 与无界请求，
  代价是未选择资源保持 unchecked；
- 选择 logical remove，而不是物理删除：保护 immutable history，代价是可能保留不可达
  content；当前没有 quota、retention 或 GC；
- 浏览器 `File` 与 uncertain intent 只存在内存；刷新、崩溃或重新选文件会退休原
  identity，无法在刷新后自动续传；
- 没有 Range/resume、多文件批量操作、拖放、inline preview/download、内容扫描、
  object storage、PostgreSQL 或跨标签 writer lock；
- 409 不自动 merge；用户必须 Reload Remote 或手工协调；
- logical remove 不自动修复 definition 引用；后续 validation 必须报告悬空引用；
- revision 仍为 `unvalidated`；没有 diagnostics、dry-run、Contract Test、publish、
  migration、execution、multi-Task/repeats/multi-Agent 或真实 Android acceptance。

## 后续进展

5.5C-1
`implement-studio-benchmark-validation-dry-run-resource-5-5c1` 已完成：它将 exact
current immutable revision 通过私有、一次性 Package materialization 接到既有
validate/dry-run，并保持 initializer/evaluator、设备、plugin construction、model、
secret 与 runtime 边界零调用。完整实现与证据见
[Studio Benchmark Validation / Dry-run Resource](studio-benchmark-validation-dry-run-resource.md)。
当前下一项固定为 5.5C-2，在该资源之上增加 URL-owned React Validation mode、
诊断导航与 revision-bound stale-result 交互。

## 事实来源

- 用户决定并固化了 Stage 5.5 的八个可执行 Change 及其先后顺序；
- 5.5B-2 的安全后端 capability 来自已归档且验证过的实现；
- Coding Agent 实现并验证了本 Change 的 shared/entity/feature/widget、fixture、测试
  与文档；
- requirement 与验收场景见当前 OpenSpec change，归档前仍应执行 strict validate。
