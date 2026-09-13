# Studio Benchmark Package Publication / Export

本文记录 Stage 5.5E-2
`implement-studio-benchmark-publish-export-5-5e2` 的已实现边界、设计、验证证据与
后续限制。它描述的是 2026-08-02 已在本仓库验证的行为，不把规划中的 legacy
migration、Benchmark execution 或真实 Android 能力写成已完成事实。

## 解决的问题

5.5E-1 已能把 exact-current authoring revision 重新验证并冻结为 closed immutable
Package revision，但当时只有 exact read：Catalog 不能发现它，用户也不能获得可校验的
版本化 Package。直接把 draft、workspace 目录或当前 Catalog root 暴露给发布流程会重新
引入 mutable source、宿主路径、版本覆盖与并发读不一致问题。

E-2 在以下层之间建立了显式 release boundary：

- E-1 immutable validation attestation 与 frozen Package revision；
- schema 10 storage-neutral release repository；
- database-sibling managed Package tree 与 deterministic ZIP store；
- process-local copy-on-write immutable Catalog snapshot owner；
- scoped HTTP metadata/content capability；
- URL-owned React Release workspace。

它没有调用 device、model、secret、Package plugin、initializer/evaluator、Agent、
Benchmark Runtime、Experiment、TaskRun result、report/trajectory/bundle、Replay 或
Android boundary。

## 前后执行流

E-2 之前：

```text
authoring revision
    -> E-1 exact-current revalidation
    -> immutable validation attestation
    -> closed frozen Package revision
    -> exact GET only
```

E-2 之后，publication 与 export 是两个独立命令：

```text
owned frozen Package revision
    -> re-open and verify every frozen member
    -> publication ---------------------> export
       |                                  |
       | materialize exact Package tree  | write deterministic ZIP v1
       | side-effect-free compile        | re-open and verify central directory
       | semantic conflict check         | verify membership/size/SHA-256
       | durable schema-10 commit         | durable schema-10 commit
       | copy-on-write Catalog swap       | exact GET/HEAD capability
       v                                  v
 managed Catalog entry                browser-owned download
```

Publish 不会自动 Export，Export 也不会自动 Publish。两者只消费 Package revision
identity，不读取 mutable draft current pointer、5.5C transient result 或 5.5D Contract
Test result。

## Durable identity 与 schema 10

Release 使用独立 opaque identity：

- `benchmark-package-publication-<32 hex>`；
- `benchmark-package-export-<32 hex>`；
- managed Catalog `benchmark-entry-<32 hex>`；
- E-1 `packageRevisionId`、`validationAttestationId`、`packageContentIdentity` 与
  `closureIdentity` 保持原值。

命令 body 只有 `schemaVersion` 与 `clientRequestId`。服务端把 operation、owning draft、
Package revision 与 contract version 纳入 request fingerprint；相同命令重试返回原结果，
相同 command identity 搭配不同语义则返回安全 idempotency conflict。

SQLite schema 10 在 schema 9 上单调增加四组 durable authority：

- `studio_benchmark_package_publications`；
- `studio_benchmark_publication_commands`；
- `studio_benchmark_package_exports`；
- `studio_benchmark_export_commands`。

迁移不重写 draft、authoring revision、attestation、frozen member 或既有 Experiment 行。
private locator 在数据库中只能是匹配 resource identity 的 opaque ID，不能携带绝对路径或
storage key authority。重启时先重新校验 durable relationship、JSON bounds、private
storage 与 frozen closure，再把 managed publications 重建进初始 Catalog snapshot。

## Frozen closure 与 managed storage

Publication/export 共用一个 private frozen-member reader。每次 release 都重新检查：

- owning draft、Package revision、attestation 与 closure identity；
- logical path、ordinal、kind、media type、content identity；
- 每个 member 的 regular-file、size 与 SHA-256；
- complete membership、无 duplicate/extra、无 absolute/traversal/symlink path；
- per-member、aggregate closure 与 archive capacity。

Publication 先在 database-sibling private staging 中写入完整 Package-relative tree，再以
exclusive regular-file write、fsync 与 atomic rename 提升为 final immutable tree。Catalog
metadata 只从该 final tree 通过 side-effect-free Package reader 编译；它不指向 workspace
`benchmarks/`、`data/`、原始 Catalog root 或 authoring content object directory。

Export contract `studio-benchmark-package-zip-v1` 固定：

- frozen logical-path order；
- ZIP stored entries；
- UTF-8 logical names；
- timestamp `1980-01-01 00:00:00`、Unix creator、mode `0644`；
- 无 directory entry、comment、extra、encryption 或 inherited source metadata。

临时 ZIP 完成后会重新打开并验证 central directory、顺序、成员内容、member count、
archive size 与 SHA-256，再原子提升。改变 CWD、storage root、source formatting/mtime、
locale 或重启服务不会改变同一 frozen closure 的归档字节。

## Catalog publication semantics

Catalog 使用固定安全 managed source identity
`studio-managed-benchmark-publications`。发布时的 readable Package identity 是
`publisher/name@version`：

- 没有同版本时创建一个 managed publication；
- managed source 中同版本同 content 时返回既有 publication；
- configured source 中同版本同 content 时保留两个明确 source，并附 equivalent-source
  warning；
- 任一 readable source 中同版本不同 content 时安全冲突，不覆盖当前 entry；
- 不同 semantic version 保持独立 entry。

Composition 通过 snapshot owner 提供 immutable capture。一个 list/detail/task/Composer
请求从开始到结束只看同一个 snapshot。发布者在单 writer lock 下从 captured current
构造完整 next snapshot，durable commit 后以一次 reference swap 替换 current。并发 reader
因此只能看到完整旧 snapshot 或完整新 snapshot；旧 cursor 在 replacement 后明确 stale，
不会在新 snapshot 中猜测 continuation。已经提交的 Experiment definition snapshot 不随
Catalog replacement 改写。

SQLite commit 与 process-local reference swap 不是同一个硬件事务。实现把 swap 设计为
commit 后的 non-throwing operation；若进程在两者之间崩溃，重启 recovery 以 durable
publication 为事实源重建 Catalog，而不是回滚或重写源目录。

## HTTP resources

已实现的 owner-scoped resources：

```text
GET  /studio/benchmark-authoring/drafts/{draftId}/package-revisions
POST /studio/benchmark-authoring/drafts/{draftId}/package-revisions/{packageRevisionId}/publications
GET  /studio/benchmark-authoring/drafts/{draftId}/package-revisions/{packageRevisionId}/publications/{publicationId}
POST /studio/benchmark-authoring/drafts/{draftId}/package-revisions/{packageRevisionId}/exports
GET  /studio/benchmark-authoring/drafts/{draftId}/package-revisions/{packageRevisionId}/exports/{exportId}
GET  /studio/benchmark-authoring/drafts/{draftId}/package-revisions/{packageRevisionId}/exports/{exportId}/content
HEAD /studio/benchmark-authoring/drafts/{draftId}/package-revisions/{packageRevisionId}/exports/{exportId}/content
```

前端经 `/api/studio/...` 同源调用。Package page 使用 bounded draft-scoped cursor；exact
resource 必须同时匹配 draft、Package revision 与 publication/export identity。隐藏 ownership
返回 404；malformed request、stale cursor、semantic/idempotency conflict、capacity、integrity、
storage outage 与 unsupported method 使用既有 bounded error envelope。

GET/HEAD 共用 exact resolver，并重新检查 final regular file、size、digest 与 ownership。
HEAD 与 GET 返回一致的 `Content-Type`、`Content-Length`、`X-Content-SHA256`、safe
`Content-Disposition`、`Cache-Control: private, no-store`、`X-Content-Type-Options:
nosniff` 和 origin/CORS policy；HEAD 不返回 body。

## React Release workspace

Draft edit route 新增 URL-owned `mode=release` 和可选 `packageRevisionId`。TanStack Query
拥有 Package revision/publication/export server facts；既有 feature-local authoring store
继续只拥有 editable baseline/document/raw buffer。组件本地只保留 confirmation、当前
selection 与 unchanged uncertain-command retry intent。

Freeze 只在以下条件同时成立时可用：

- local baseline clean；
- task JSON buffer 可解析且已 apply；
- baseline revision 等于 query current revision；
- 没有 remote-newer/conflict；
- 没有其他 authoring command pending。

Freeze、Publish、Export 分别显式触发。Publish/Export confirmation 展示 Package、content、
closure identity 以及 `executionEvidence=false`、`realDeviceEvidence=false`。Download 先用
HEAD 校验 media type、size、digest 与 filename，再把 authoritative `contentLink` 交给浏览器
原生下载；archive bytes 不进入 React state、TanStack Query cache 或 edit store。

## 验证证据

本 Change 最终观测到：

- focused release model/repository/storage/service/security：`10 passed`；
- focused authoring suites：`52 passed`；
- Studio + packaging suites：`381 passed`；
- complete backend regression：`765 passed`；
- complete frontend：`84 test files / 376 tests passed`；
- TypeScript `tsc -b`、ESLint 与 Vite production build 通过；
- repository-independent clean-wheel publish/export acceptance：`1 passed`；
- AST docstring audit对本 Change Python files 无缺失报告；
- no-device real-browser journey 完成 dirty gate、Freeze、Publish、Catalog visibility、
  refresh/deep link、Export、HEAD/native download、unknown selection、light/dark theme 与
  adjacent settings route；
- 浏览器 fixture 中 publication/export 各调用 1 次；initializer、environment、evaluator、
  Agent、device、plugin construction、model、network、secret、Experiment、TaskRun result、
  report/Replay、runtime export 与 Android 调用均为 0；
- synthetic leakage audit 扫描 public DTO、Catalog projection、SQLite release values、
  managed Package tree、ZIP、logs 与 source content bytes，未发现 secret、device serial、
  host path、live-object repr 或 private locator 泄漏，且 source bytes 不变。

可复现命令：

```bash
uv run pytest -q tests/studio/test_benchmark_authoring_release.py
PYTHONPATH=tests uv run pytest -q tests/studio tests/packaging
PYTHONPATH=tests uv run pytest -q
PYTHONPATH=tests uv run pytest -q \
  tests/packaging/test_benchmark_authoring_install.py::test_installed_wheel_publishes_and_exports_frozen_package

cd studio
npm test
npm run typecheck
npm run lint
npm run build
npm run smoke:benchmark-authoring
```

最后一条启动 `http://127.0.0.1:8766/benchmark-authoring`。进入 seeded draft 的 Release
mode 后，预期 dirty edit 禁用 Freeze；Reset/Reload 后可 Freeze；Publish 后 Catalog 出现
`Managed Browser Release`；Export 后 Download 先做 HEAD，再显示“下载已交给浏览器”；
`/api/studio/benchmark-authoring/fixture-canaries` 中除 release publication/export 外均为 0。

HTTP 手工检查可使用：

```bash
curl -i -X POST -H 'Content-Type: application/json' \
  --data '{"schemaVersion":1,"clientRequestId":"manual-publish-1"}' \
  'http://127.0.0.1:<port>/studio/benchmark-authoring/drafts/<draft-id>/package-revisions/<package-revision-id>/publications'

curl -i -X POST -H 'Content-Type: application/json' \
  --data '{"schemaVersion":1,"clientRequestId":"manual-export-1"}' \
  'http://127.0.0.1:<port>/studio/benchmark-authoring/drafts/<draft-id>/package-revisions/<package-revision-id>/exports'

curl -I \
  'http://127.0.0.1:<port>/studio/benchmark-authoring/drafts/<draft-id>/package-revisions/<package-revision-id>/exports/<export-id>/content'
```

首次成功命令返回 201；相同 payload 重试返回 200 且 identity 不变。HEAD 必须无 body，
且 size、digest、media type 与 safe attachment filename 匹配 export descriptor。

## 取舍、失败模式与限制

- 选择 managed copy 而不是让 Catalog 直接读取 E-1 content objects：多一次存储，但得到
  coherent Package-relative tree、独立 publication lifetime 和 closed source boundary。
- 选择 ZIP stored 而不是 compressed ZIP/tar：归档可能更大，但跨平台 metadata 和压缩器
  差异更少，byte determinism 更可审计。
- 选择 process-local copy-on-write snapshot：并发 reader 一致，但多进程 live publication
  coordination 尚未实现；重启 recovery 只解决 durable reconstruction。
- content-first/metadata-second failure 可能留下不可达 private immutable tree/ZIP；它不可被
  API 查询，也不会进入 Catalog，但当前没有 retention/GC/delete 产品合同。
- schema 10 是向前单调迁移；旧 binary 必须拒绝未知 schema，而不是尝试 downgrade。
- managed storage 仍是本地 database-sibling filesystem；未实现 object storage、quota、
  retention、delete 或 distributed lock。
- Release 只证明 frozen closure、Catalog visibility 和 archive integrity。它不证明
  Contract Test pass、Agent/Benchmark execution、模型质量、设备兼容或真实 Android。
- 既有 worker 仍限制一个 Agent、一个 Task、一个 repeat；E-2 没有扩大执行 cardinality。
- E-2 本身未实现 legacy BenchmarkTask JSON migration；后续 5.5E-3 已在独立边界内
  完成，详见 [Studio Benchmark Legacy Migration](studio-benchmark-legacy-migration.md)。

## 当前下一步

该文档记录的是 5.5E-2 历史边界。后续
`implement-studio-benchmark-legacy-migration-5-5e3` 已提供 bounded
preview/diff/confirm，把 legacy BenchmarkTask JSON 转成新的 `unvalidated` draft，同时保留
原文件、拒绝字段、duplicate task identity、Protocol/ground-truth truthfulness 和
idempotency 边界。Stage 5.5 已完成；下一项固定为 Stage 5.6 real Android acceptance。

## 事实来源

- Stage 5.5E-1/2/3 顺序与声明边界来自用户固化路线和本 Change OpenSpec artifacts；
- E-1 frozen revision、Catalog/Composer 与 authoring content store 是此前已验证基础；
- Coding Agent 实现或审查了 schema/repository、storage、service、Catalog snapshot、HTTP、
  React、fixture、tests，并运行本文列出的验证命令；
- requirement、design 与完整 acceptance scenarios 保存在本 Change，归档前不得把未运行
  的真实 Android 或 migration 行为添加为完成证据。
