# Studio Benchmark Authoring Managed Content

本文记录 Stage 5.5B-2
`implement-studio-benchmark-authoring-content-5-5b2` 在 2026-07-31 的已验证实现
边界。它为 5.5A 的持久 Benchmark draft/revision 增加 draft-owned 受管内容写入
与精确历史读取，但没有增加 React resource editor、语义 validation、dry-run、
Contract Test、publication、migration 或 Benchmark execution。

## 解决的问题与涉及层

5.5A 已能在安全导入时把 Package resource 复制到 server-owned content store，
5.5B-1 也能只读展示 resource inventory；但浏览器还不能在不接触宿主路径的前提下
新增、替换或移除 asset 与文件型 ground truth，也不能读取某个不可变 revision
实际引用的字节。

如果把 `contentIdentity` 直接暴露为下载 bearer token，或让调用方把任意路径写进
revision，会破坏 draft ownership、历史可重建性和路径安全。5.5B-2 因此增加一条
owner-scoped、definition-only 数据流：

```text
draft + exact base revision + logical resource metadata + raw bytes
                              │
                              ▼
                   strict query/DTO preflight
                              │
                              ▼
               bounded stream → SHA-256 → fsync → atomic promotion
                              │
                              ▼
          complete document projection（strict + manifest inventory）
                              │
                              ▼
             immutable child revision + draft current-pointer CAS

exact draft + revision + resource
              │ ownership and declared facts
              ▼
regular-file / size / content-identity / SHA-256 verification
              │
              ▼
        attachment-only GET or bodyless HEAD
```

涉及层：

- `benchmark_authoring_models.py`：schema-1 upload/replace/remove/result DTO，
  resource id、Package-relative path、kind、media type 和 canonical fingerprint；
- `benchmark_authoring_content.py`：严格 query parser、双 inventory 投影、
  database-neutral 内容应用服务和 typed exact-read result；
- `benchmark_authoring_protocols.py`、`benchmark_authoring_repository.py`：
  exact verified stream 与既有 command fact 查询能力；
- `benchmark_authoring_storage.py`：descriptor-based regular-file、size 和
  SHA-256 完整性闭合；
- `benchmark_composition.py` 与 `httpd.py`：process composition、raw-body action
  route 和 owner-scoped GET/HEAD；
- focused、完整 Studio、Benchmark、前端与 clean-wheel 自动化证据。

AgentConfig/AgentGraph 和 BenchmarkTask JSON 仍是独立合同；本 Change 没有修改
Graph Runtime kernel、Agent strategy、Benchmark evaluator 或 Worker lifecycle。

## 严格命令与完整文档投影

三个命令都使用 schema 1、draft-local `clientRequestId`、精确
`baseRevisionId` 和 route-owned `resourceId`：

| 命令 | 额外输入 | 语义 |
|---|---|---|
| upload | `kind`、Package-relative `path`、`Content-Type`、raw bytes | 新增 logical resource |
| replace | `Content-Type`、raw bytes | 保持 id/kind/path，仅替换权威 bytes/metadata |
| remove | 无 body metadata | 在新 revision 中解除 logical reference |

upload 只允许 `assets/...` 对应 `asset`、`ground_truth/...` 对应
`ground_truth`。路径拒绝 absolute、`..`、反斜线、空 segment 和宿主路径字段；
media type 拒绝控制字符、逗号和 response-header 注入。query 必须与操作的字段集合
完全相等、每个字段恰好出现一次；unknown、duplicate、missing、destination、
`contentIdentity`、host/source path 和 secret-bearing 扩展在 repository/storage
访问前失败。

每次写入都从 exact base revision 构造一份完整
`StudioBenchmarkAuthoringDocumentV1`：

- strict `resources` 与 manifest `resources` 必须一一对应；
- known id/kind/path/media type/digest/size 必须完全一致；
- 重复 id/path、缺字段、private content identity 或矛盾 inventory 会 fail closed；
- upload 同时向两份 inventory 新增 declaration；
- replace 保留 logical id/kind/path 和 manifest resource 上未知但安全的扩展；
- remove 同时从两份 next-revision inventory 移除 declaration；
- manifest 顶层未知安全扩展、task files、Protocol files、inline ground truth 和固定
  logical directories 无损保留；
- 两份 resource inventory 都按 Package path 确定性排序。

remove 不改写 task 或 inline definition 中可能出现的普通字符串引用。后续 validation
需要把悬空语义引用报告为 diagnostics；本阶段不猜测也不自动修复。

## 流式写入、revision 与幂等/CAS

upload/replace 复用 5.5A 的 64 MiB 单 resource 上限和本地 content-addressed
store。服务不信任客户端摘要或 size，而是在单次 bounded stream 中计算：

```text
raw request stream
  → private staging regular file
  → exact byte count + SHA-256
  → flush/fsync
  → digest-addressed immutable object
  → atomic promotion + directory fsync
```

正文不进入 2 MiB JSON reader，也不会一次性装入应用内存。相同 bytes 按 digest
去重；replace 即使复用逻辑 id，也会由实际 bytes 得到权威 content identity。
完全相同 bytes 与 media type 的 replace 被视为 no-op 并拒绝，不创建空 revision。

command fingerprint 绑定：

- operation；
- draft/base/resource identity；
- upload 的 kind/path 或 replace/remove 的稳定 kind/path；
- 实际 SHA-256 与 size；
- upload/replace 的 media type。

第一次成功写入调用既有 schema-8 `save_revision` transaction，追加 immutable child、
推进 current pointer 并记录 command fact。精确重试返回原 revision 且
`created=false`；即使 draft current 已继续前进，已知 command 仍可重读 bytes、
重算相同 fingerprint 后返回原结果。相同 request id 携带不同 bytes/metadata 返回
idempotency conflict。

新 command 若 base 已 stale，会在读取 caller stream 前返回 409，并携带安全
`currentRevisionId`。两个 writer 对同一 base 竞争时，transaction 内 CAS 最多允许
一个推进 current pointer；另一个冲突，历史 revision 不被覆盖。

remove 只追加一个不含该 resource 的 revision。旧 revision 和其 immutable content
object 均保留并继续可读；本 Change 没有物理 delete、quota、retention 或 GC。

## 精确 owned content capability

内部 exact read 必须同时提供：

```text
draftId + revisionId + resourceId
```

repository 先验证 revision 属于该 draft，再在 revision strict inventory 中找到
resource，最后才取得 private `contentIdentity`。调用方不能用
`/content/{contentIdentity}` 探测对象；该旧猜测路径继续返回 404。

在返回可读 stream 前，本地 adapter 使用 `O_NOFOLLOW`（平台支持时）打开 descriptor，
并验证：

1. descriptor 指向 regular file；
2. exact size 等于 revision 声明；
3. `contentIdentity` 内 digest 等于 revision `sha256`；
4. descriptor 全量重算 SHA-256 等于 identity。

验证完成后 stream seek 回 0。missing、symlink、directory、size drift 或 digest
corruption 都在响应 body 开始前失败，且错误不包含宿主路径。replace/remove 后，
旧 revision 仍按原 resource facts 精确读取；新 revision 中不存在的 resource 和
跨 draft/revision 探测返回 404。

## HTTP surface

`/studio/...` 与 `/api/studio/...` normalization 均支持：

```text
POST /studio/benchmark-authoring/drafts/{draftId}/resources/{resourceId}/upload
POST /studio/benchmark-authoring/drafts/{draftId}/resources/{resourceId}/replace
POST /studio/benchmark-authoring/drafts/{draftId}/resources/{resourceId}/remove

GET  /studio/benchmark-authoring/drafts/{draftId}/revisions/{revisionId}/resources/{resourceId}/content
HEAD /studio/benchmark-authoring/drafts/{draftId}/revisions/{revisionId}/resources/{resourceId}/content
```

action metadata 是 URL-percent-encoded 的 exact query；content bytes 只在 body。
upload/replace 要求一个 `Content-Type` 和一个非负十进制 `Content-Length`；chunked、
duplicate/missing/malformed length、short/overlong source 和超过 64 MiB 的声明均
拒绝。remove 要求 `Content-Length: 0`。已知 route 的错误 method 返回 405。

新 revision 返回 201，精确 retry 返回 200；stale CAS 为 409，容量为 413，
missing scope 为 404，受管存储不可用为 503。错误 body 延续既有有界 JSON envelope，
不回显 query secret、bytes、content identity、数据库异常或宿主路径。

verified GET/HEAD 返回 revision 声明的 media type 和 exact length，并固定：

- `Content-Disposition: attachment; filename="<resourceId>"`；
- `Cache-Control: private, no-store`；
- `X-Content-Type-Options: nosniff`；
- 既有 Host 与 same-origin CORS policy；
- HEAD 无 body；
- 不支持 Range，也不以内联方式执行 SVG/HTML 等 active content。

## Composition、故障语义与 schema

配置 SQLite database 时，Benchmark composition 在同一个既有 schema-8 repository
和 private content store 上创建 content application service；无 database 的
definition-only composition 仍保持该能力为 `None`。本 Change 没有数据库 migration，
Studio schema 仍为 8。

内容与 SQLite 不存在跨文件系统/数据库的原子 transaction。采用 content-first
顺序保证任何可见 revision 都只引用已完整晋升的 bytes：

```text
finalized content object
        ↓
SQLite append revision + pointer CAS + command
```

source interruption、容量、hash、write/fsync、atomic promotion 失败都会清理 staging，
且不产生可见 revision。repository rollback 或 CAS 在 promotion 后失败时，旧 current
pointer 仍权威，也不会产生引用缺失/部分 bytes 的 revision；代价是可能留下一个
不可达但不可变的 finalized object。测试明确记录了这一窄 orphan trade-off，本
Change 没有伪造跨系统原子性，也没有顺带实现删除或 GC。

完整 content journey 对 initializer、environment、evaluator、device、Agent/plugin
construction、model、network、secret、Agent runtime、Experiment、report
publication、Replay、migration 和 export 做 fail-fast canary，观测调用数为零。

## 自动化验证

可复验命令：

```bash
UV_CACHE_DIR=/private/tmp/zhixing-uv-cache uv run pytest -q \
  tests/studio/test_benchmark_authoring_resource.py \
  tests/studio/test_benchmark_authoring_content.py

UV_CACHE_DIR=/private/tmp/zhixing-uv-cache uv run pytest -q \
  tests/studio/test_benchmark_http.py

UV_CACHE_DIR=/private/tmp/zhixing-uv-cache uv run pytest -q tests/studio
UV_CACHE_DIR=/private/tmp/zhixing-uv-cache uv run pytest -q tests/benchmark

cd studio
npm test
npm run typecheck
npm run lint
npm exec vite -- build --outDir /private/tmp/zhixing-studio-b2-dist

UV_CACHE_DIR=/private/tmp/zhixing-uv-cache uv run pytest -q \
  tests/packaging/test_benchmark_authoring_install.py \
  -m packaging_acceptance

/Users/maczhen/.npm/_npx/abab5bd700860149/node_modules/.bin/openspec \
  validate implement-studio-benchmark-authoring-content-5-5b2
```

2026-07-31 实际结果：

- 5.5A resource + 5.5B-2 focused service：`56 passed`；
- 完整 Benchmark authoring HTTP：`8 passed`；
- complete Studio backend：`281 passed`；
- complete Benchmark backend：`94 passed`；
- complete Studio Vitest：`67 files / 288 tests passed`；
- TypeScript typecheck、ESLint、独立临时目录 production build：通过；
- clean-wheel installed-package upload/read/replace/old-read/remove/retry/conflict/
  restart journey：`1 passed`；
- production compileall、全部新/修改函数 docstring audit、OpenSpec validate：通过。

production build 仍报告既有单一 JavaScript chunk 超过 500 kB 的非阻塞 warning；
本 Change 没有修改前端 bundle。HTTP 测试使用本地 loopback，clean-wheel 通过隔离
venv 和仓库外 workdir 证明安装包不依赖 repository `PYTHONPATH`。

## 限制与 5.5B-3 交接

当前已验证的是后端 capability，不是可视化资源编辑器：

- 5.5B-1 resource inventory 在 React 中仍只读；
- 没有 upload/replace/remove progress、conflict 或 missing-content UI；
- revision 始终是 `unvalidated`，上传成功不证明 task、Protocol 或 ground truth
  语义正确；
- 没有 draft delete、physical content delete、quota、retention 或 GC；
- 没有 PostgreSQL/object-storage adapter 或分布式 transaction；
- 64 MiB 对象 exact read 会先完整校验，再传输，保证 fail-before-body，但增加一次
  完整读取成本；
- 没有 Range/resume、病毒扫描或任意第三方内容安全判定；
- 没有 multi-Task/repeats/multi-Agent Worker 扩展或真实 Android 证据。

5.5B-3 现已完成，并只消费本文已验证的 owner-scoped capability：内容命令从
clean saved baseline 发起，成功后以权威 immutable revision 重新 hydrate；UI
展示 media type、size、digest、missing/conflict/failure 事实，并继续把 inline
JSON ground truth 留在 5.5B-1 definition data 中。验证边界见
[Studio Benchmark Resource Editor](studio-benchmark-resource-editor.md)。当前下一步
是 5.5C-1 side-effect-free validation/dry-run resource；5.5C-2 随后增加
React Validation view。

## 事实来源

- 用户决定把原 5.5B 永久拆为 definition editor、managed-content backend 和
  resource editor，并要求每个 Change 独立探索、实现、验证和归档；
- Coding Agent 实现并验证本 Change 的 DTO、projection、service、storage exact
  read、composition、HTTP、故障注入、clean-wheel 与永久文档；
- 本文只把 5.5B-2 的真实代码和测试结果写成已实现事实；后续 5.5B-3 的事实记录在
  独立永久文档中，5.5C-1/2、5.5D 与 5.5E 仍是规划能力。
