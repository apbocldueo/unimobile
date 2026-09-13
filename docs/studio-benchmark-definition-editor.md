# Studio Benchmark Definition Editor

本文记录 Stage 5.5B-1
`implement-studio-benchmark-definition-editor-5-5b1` 的实际实现、验证证据与已知
边界。它是 Stage 5.5A durable authoring resource 之上的 React definition-only
编辑切片，不是 validation、execution、publication 或 managed-content mutation
的完成声明。

## 状态与范围

截至 2026-07-31，本 Change 已实现并验证：

- 独立 `/benchmark-authoring` 入口和
  `/benchmark-drafts/:draftId/edit` 稳定草稿路由；
- 对 Stage 5.5A draft、revision、document、resource、create/save 与安全错误响应
  的 strict schema-1 前端解析；
- template/Catalog 创建、Draft list/open，以及不确定 create 响应的同意图重试；
- manifest、split、applications、plugins、default Protocol、Protocol 与 inline
  JSON ground truth 的结构化编辑；
- 每个 task file 独立的浏览器内 raw JSON buffer、显式 Parse/Apply、语法错误定位
  与保存阻塞；
- baseline/working document、dirty、reset、reload、remote-newer、optimistic save
  和 409 conflict 的 feature-local 编辑会话；
- resource 与文件型 ground truth 的只读权威清单；
- focused/full Studio、typecheck、lint、production build、相邻 5.5A backend
  regression 和 no-device real-browser journey。

本 Change 没有新增或修改 Benchmark runtime、AgentGraph runtime、device、
initializer/evaluator、model、secret、Experiment、Report 或 Replay 行为。
`BenchmarkTask` JSON 与 `AgentConfig`/`AgentGraph` 仍是独立合同。

## 用户问题与前后流程

5.5A 已经能安全持久化 immutable authoring revision，但缺少浏览器里的 definition
编辑会话。若 React 组件直接把服务器响应当表单状态，后台 refetch、语法损坏的
JSON、并发保存和扩展字段都可能造成静默覆盖或信息丢失。

```text
before
  CLI / file Package
        or
  5.5A HTTP draft + immutable revision
        ↓
  没有 React definition editor

after
  /benchmark-authoring
    ├─ template create ──────────────┐
    ├─ opaque Catalog copy create ──┤
    └─ bounded draft list/open ─────┘
                                      ↓
                         strict Stage 5.5A DTO
                                      ↓
  TanStack Query server state ──→ feature-local editing session
                                 ├─ saved baseline
                                 ├─ working parsed document
                                 ├─ per-task raw JSON buffers
                                 ├─ base revision
                                 └─ conflict / remote-newer facts
                                      ↓
                       explicit Apply JSON + optimistic Save
                                      ↓
                       new immutable unvalidated revision
```

## 分层与所有权

实现遵守
[Studio frontend architecture](studio-frontend-architecture.md) 的单向依赖：

- `entities/benchmark-authoring`：strict schema、opaque identity、typed API、
  TanStack Query keys/hooks、测试 fixture；
- `features/benchmark-definition-editor`：lossless document patch、task buffers、
  create/save intent 和 feature-local Zustand session；
- `widgets/benchmark-definition-workbench`：远端查询与编辑会话编排、Save/Reset/
  Reload、离开保护与 conflict UX；
- `pages/benchmark-authoring`：Draft list、template/Catalog 创建和重试；
- `pages/benchmark-draft-edit`：稳定资源路由入口；
- `app`：路由注册与 Benchmark sidebar 导航。

服务器事实只进入 TanStack Query。baseline、working document、raw buffers、选择状态
和冲突事实只进入 draft-scoped feature store。组件没有本地 `fetch`，也没有把
editor session 混入全局 app store。

## 已验证合同

### 1. strict entity 与 API

前端会 fail closed 解析版本、opaque ids、pagination、draft/current revision、
exact revision、authoring document、resource metadata、create/save result 与安全
错误。开放的 manifest、Protocol、task、ground-truth JSON mapping 允许扩展字段，
但外围 DTO、枚举和容量形状保持严格。

API 仅复用 Stage 5.5A 已有能力：

- bounded draft page；
- current draft detail；
- exact immutable revision；
- template/Catalog create；
- optimistic save。

没有为 resource bytes 合成 content URL，也没有把 `contentIdentity` 当作 bearer
token。

### 2. 无损结构化编辑

字段更新通过 immutable path patch 修改目标位置，未触及字段保持原值。member
inventory 由 Package-relative path 稳定排序；manifest/split/Protocol/inline
ground truth 的结构化输入只替换自己的路径。因此未知 extension fields 能跨
编辑、保存与重新 hydrate 保留。

第一版没有引入 Monaco、CodeMirror 或 Benchmark drag canvas。普通可访问表单和
受控 textarea 降低了依赖与交付面，代价是没有大型文档的高级导航和增量语法服务。

### 3. task raw JSON buffer

每个 task file 有独立 raw buffer。用户输入先保留在浏览器内存：

```text
raw text
  ├─ syntax error ───────→ 显示 line/column，阻止 Save
  ├─ parse success only ─→ 标记 unapplied，阻止 Save
  └─ Apply JSON ─────────→ 更新 working document，允许继续保存
```

语法损坏或尚未 Apply 的文本不会发给后端，也不会被描述为已持久化。本地刷新或
关闭页面会丢失这些 buffer；本 Change 没有 durable local recovery。

### 4. optimistic concurrency 与命令重试

create/save command intent 根据语义输入生成稳定 request identity。相同输入在
结果不确定时重试会复用原 identity；输入改变或成功响应会退休旧 intent。

Save 使用当前 baseline revision 作为 `baseRevisionId`。成功时用服务端返回的
immutable revision 重新 hydrate baseline、working document 和 raw buffers。
安全 409 只记录权威 `currentRevisionId`，保留本地工作，不自动 merge、不自动
覆盖。用户必须显式选择：

- `Reset`：回到当前本地 saved baseline，不发请求；
- `Reload Remote`：丢弃本地内容并采用权威 current revision；
- 手工协调后重新保存。

后台 refetch 发现新 current revision 时只显示 remote-newer，不覆盖 dirty session。

### 5. 路由保护与负向产品边界

dirty、invalid buffer 或 unapplied buffer 会触发 browser unload 和 Studio
anchor navigation 确认；Reset/Reload 也需要在会丢数据时显式确认。保护只承诺本
Change 已接管的浏览器关闭/刷新与 Studio 链接点击，不声称提供 crash recovery
或持久草稿恢复。

页面始终显示 `definition only · unvalidated`，且没有 Validate、Run、Publish、
Export、Upload、Replace 或 Remove 动作。只读 resource facts 仅展示服务端返回的
path、kind、media type、size、digest、content identity、availability 与
provenance；展示成功不等于 resource 可读、可改或 definition 已验证。

## 验证证据

### Frontend 自动化

```bash
cd studio

npm test -- --run \
  src/entities/benchmark-authoring \
  src/features/benchmark-definition-editor \
  src/widgets/benchmark-definition-workbench \
  src/pages/benchmark-authoring \
  src/pages/benchmark-draft-edit \
  src/app/shell/BenchmarkModuleSidebar.test.tsx
# 11 files passed, 35 tests passed

npm test
# 67 files passed, 288 tests passed

npm run typecheck
# passed

npm run lint
# passed

npm run build
# passed; Vite transformed 587 modules
# output JS about 908.96 kB, gzip about 267.90 kB
# Vite retained the general >500 kB chunk-size warning
```

focused tests 覆盖 strict/malformed response、pagination、template/Catalog create、
uncertain retry、extension-field preservation、structured/JSON editing、
invalid/unapplied buffers、dirty/reset/reload、remote-newer、successful rehydrate、
409 conflict、route/sidebar 与缺失的越权动作。

### 相邻 5.5A backend regression

项目文档指定的 `unimobile` conda 环境在本机缺少 `pytest`，因此首次
`conda run -n unimobile python -m pytest ...` 没有进入测试收集。随后使用仓库
可复现的 uv 环境执行：

```bash
uv run pytest \
  tests/studio/test_benchmark_authoring_resource.py \
  tests/studio/test_benchmark_http.py \
  -k authoring -q
# 37 passed, 3 deselected in 1.80s
```

该结果证明本次前端 Change 没有要求改变 5.5A identity、CAS、HTTP 或
definition-only 后端合同；它不是完整 backend suite 或 clean-wheel 复验。

### no-device real-browser journey

```bash
cd studio
npm run smoke:benchmark-authoring
# fixture: http://127.0.0.1:8766/benchmark-authoring
```

在真实 in-app Chromium 中观察到：

1. entry 可列出并打开 seeded draft；
2. `dynamic-task` template 的第一次 create 收到注入式 uncertain 503，页面没有
   猜测导航；相同输入重试打开第一次已提交的 draft；
3. structured Title 修改成功；
4. task JSON 输入 `[` 时显示 `Unexpected end of JSON input`，Save 被禁用；
5. 有效 JSON 在 Apply 前显示 unapplied，Apply 后 Save 可用；
6. Save 生成 revision 2，并仍明确显示 `unvalidated`；
7. Reset 回到 saved baseline，Reload Remote 采用服务端 current revision；
8. 注入式 409 显示 current revision，本地 `Conflict Title` 未被覆盖；
9. resource inventory 只显示 metadata，没有 content link 或 mutation action；
10. Catalog opaque entry 可创建新的 Catalog-origin draft；
11. 页面不存在 Validate、Run、Publish、Export、Upload、Replace、Remove 按钮；
12. journey 结束时浏览器 console error 数为 0。

fixture 是确定性的 no-device presentation evidence，不是 production backend、
真实 Catalog、大规模文档、真实 Android 或多用户负载证据。

## 取舍、限制与失败情况

- 选择 feature-local in-memory raw buffers，而不是把无效 JSON 发给 5.5A：
  后端 identity 更安全，但刷新后无法恢复未 Apply 文本。
- 选择 full-document optimistic revision save，而不是字段级 patch/CRDT：
  可复用 5.5A CAS 且历史清晰，但冲突只能手工协调，不能自动 merge。
- 选择结构化表单加 JSON textarea，而不是大型编辑器依赖：首个切片较小且可访问，
  但缺少 schema autocomplete、diff、折叠和大型文件虚拟化。
- 离开保护覆盖 browser unload 和 Studio anchor navigation；不构成通用 crash
  recovery、跨标签锁或任意 imperative history transition 的完整拦截。
- Catalog create 只消费当前已加载的 opaque Catalog page；没有客户端全局枚举、
  路径输入或 source 浏览器。
- resource/file-backed ground truth 仍只读；missing/corrupt 事实只被展示，不能在
  本 Change 修复。
- revision 仍为 `unvalidated`；没有 diagnostics、dry-run、Contract Test、
  publish、migration、execution 或真实 Android acceptance。
- 没有 Benchmark drag canvas、multi-Task/repeats/multi-Agent Worker 扩展、
  PostgreSQL、object storage、retention/delete 或任意第三方代码沙箱声明。

## 历史交接与当前下一步

下一项固定为
`implement-studio-benchmark-authoring-content-5-5b2`。它只新增后端 exact-read 与
upload/replace/logical-remove command，不增加 React resource editor。关键边界：

- capability 由 owning draft/revision/resource 精确限定；
- bounded streaming、权威 media type/size/SHA-256 与 command idempotency；
- 所有 mutation 使用 base-revision CAS；
- bytes 临时写入、校验、原子晋升，失败不留下可见半成品；
- replace 产生新的 immutable content identity；
- remove 只在新 revision 解除引用，不删除旧 revision 仍依赖的 bytes；
- 不把 content command 成功描述为 semantic validation。

5.5B-2 现已完成，验证边界见
[Studio Benchmark Authoring Managed Content](studio-benchmark-authoring-content.md)。
5.5B-3 现已完成，并把这些能力接入 React resource editor；验证边界见
[Studio Benchmark Resource Editor](studio-benchmark-resource-editor.md)。当前下一步
是 5.5C-1 side-effect-free validation/dry-run resource；5.5C-2 随后增加
React Validation view。

## 事实来源

- 用户决定 Stage 5.5 永久拆为 5.5A、5.5B-1/2/3、5.5C-1/2、5.5D
  与 5.5E，并要求逐步实现；
- OpenSpec Change 固化了本切片的 requirement、design、tasks 与验收场景；
- Coding Agent 完成了本页列出的代码、命令、真实浏览器 journey 与文档记录；
- Stage 5.5A 的已验证后端边界见
  [Studio Benchmark Authoring Resource](studio-benchmark-authoring-resource.md)。
