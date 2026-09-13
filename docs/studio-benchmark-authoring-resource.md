# Studio Benchmark Authoring Resource

本文记录 Stage 5.5A
`implement-studio-benchmark-authoring-resource-5-5a` 在 2026-07-30 的已验证实现
边界。它建立 Benchmark authoring 的持久草稿、不可变修订、受管内容和安全导入
资源；它不是编辑器、验证器、dry-run、Contract Test Kit 或发布流程，也没有新增
真实 Android、真实多 Agent Worker 或 Benchmark 运行证据。

## 解决的问题

此前 Benchmark Package 可以通过 Python/CLI scaffold、validate 和 dry-run，但
Studio 没有一个可在重启后重建、可并发保存、且不暴露宿主路径的 authoring 资源。
若直接让浏览器或 API 修改工作区 Package，会产生四类风险：

- 可变文件无法稳定表达修订、幂等和并发冲突；
- Catalog import 可能引用随后变化的源目录，或越过声明闭包复制额外文件；
- resource/ground-truth 二进制可能被塞进 JSON 或暴露绝对路径；
- “保存草稿”可能错误地触发插件、设备、模型、secret、Experiment 或 Replay。

5.5A 将这些责任拆成一条 definition-only 数据流：

```text
template name / opaque available Catalog entry
        │
        ▼
private scaffold or declared-closure snapshot
        │  path/type/size/hash/drift checks
        ▼
server-owned immutable content objects
        │
        ▼
strict parsed authoring document (status=unvalidated)
        │
        ▼
immutable revision ── current pointer ── mutable draft metadata
        │
        └── idempotent create/save command facts
```

涉及层：

- `zhixing/studio/benchmark_authoring_models.py`：严格 schema-1 DTO、安全 JSON、
  路径、identity、inventory 和容量边界；
- `benchmark_authoring_repository.py` 与 `database.py`：SQLite schema 8、
  draft/revision/command 持久化、CAS 和 keyset page；
- `benchmark_authoring_storage.py`：数据库同级、server-owned、content-addressed
  本地内容存储；
- `benchmark_authoring_import.py` 与 `benchmark_service.py`：三种 scaffold 和
  Catalog 声明闭包的内部路径型 adapter；
- `benchmark_authoring_service.py`、`benchmark_composition.py` 与 `httpd.py`：
  应用服务、进程级 composition 和最小 HTTP resource；
- focused、adjacent、完整 Studio 与 clean-wheel 自动化证据。

## Authoring document 与容量边界

`StudioBenchmarkAuthoringDocumentV1` 是安全、已解析、但允许语义尚不完整的多文件
文档。它固定包含：

- `benchmark.yaml` 的 parsed manifest mapping；
- 按 Package-relative path 排序的 task JSON arrays；
- 按 Package-relative path 排序的 Protocol JSON/YAML mappings；
- metadata-only resource/ground-truth inventory；
- 固定逻辑目录 `assets` 与 `ground_truth`；
- 明确的 `status: unvalidated`。

它拒绝 unknown fields、非 JSON 值、NaN/Infinity、重复 identity/path、非规范或向上
穿越路径、宿主绝对路径和已经解析出的 secret 值。secret reference 可以保留；
Android 设备路径仍被当作任务数据，而不是宿主文件能力。

边界集中为：

| 项目 | 上限 |
|---|---:|
| authoring definition JSON | 2 MiB |
| 总声明成员数 | 256 |
| 单个 resource/ground-truth | 64 MiB |
| 单次 Catalog import 总字节 | 256 MiB |
| draft page | 100 |
| 后续 diagnostics contract | 100 |

definition fingerprint 对完整规范 JSON 计算 canonical hash。resource 只暴露稳定
logical id/path、allowlisted metadata、size、`sha256:` digest 和 opaque
`benchmark-content-*` identity；不序列化源路径、受管存储路径或文件句柄。

`unvalidated` 是正式事实，不是失败状态。5.5A 接受安全但语义不完整的中间草稿，
例如暂时缺字段的 task mapping；是否符合 `BenchmarkTask`、Protocol 或 schedule
合同属于 5.5C-1，对应 React 展示与诊断导航属于 5.5C-2。

## 持久 draft、revision 与命令语义

SQLite schema 8 只增加：

```text
studio_benchmark_authoring_drafts
studio_benchmark_authoring_revisions
studio_benchmark_authoring_commands
```

draft 保存名称、时间和一个 current revision pointer；revision 保存 ordinal、
parent、完整严格 document、fingerprint、provenance 与创建时间，写入后不可修改。
command 表以 `(command_scope, client_request_id)` 为键保存 request fingerprint 和
原始结果 identity。

创建和保存都在单一 SQLite transaction 中完成：

```text
create:
  request fingerprint
    → existing equal command ? original result
    → prepare source
    → draft + revision 1 + current pointer + command

save:
  request fingerprint
    → existing equal command ? original result
    → baseRevisionId == currentRevisionId ?
    → append immutable child + advance pointer + command
```

相同 scope/request id 与相同 fingerprint 返回原结果，并设置 `created=false`；
相同 request id 携带不同 payload 返回 idempotency conflict。save retry 的命令查找
先于 base revision 判断，因此成功响应丢失后的精确重试不会被新 current pointer
误判为 stale。

两个 writer 基于同一 revision 并发保存时，SQLite serialization 和 transaction
内 current-pointer 比较保证最多一个成功；另一个收到只携带安全
`currentRevisionId` 的 409。失败的 revision、command 或 pointer 写入整体回滚。
exact revision 查询同时要求 draft ownership；跨 draft identity 返回 404，不泄露
revision 是否存在。

draft list 使用 `(updated_at DESC, draft_id ASC)` 的 checksummed keyset cursor，
页大小限制为 1–100。重启后 repository 从 SQLite 和受管 content object 重建同一
draft/revision 事实，不依赖内存注册表。

## 受管内容与安全导入

默认 authoring root 是 SQLite 文件的同级
`<database-name>.benchmark-authoring/`，包含私有 staging 和按 digest 分布的不可变
objects。写入流程为：

```text
bounded stream
  → temporary regular file
  → byte count + SHA-256
  → flush/fsync
  → atomic os.replace
  → parent directory fsync where supported
  → opaque content identity
```

相同内容去重；已有 object 在复用前重新校验 size/hash。读取也重新校验 regular
file、identity、size/hash。写入或 finalize 失败会清理 temporary file，不注册
部分 object。

模板创建只接受 `minimal`、`dynamic-task` 或 `composite-evaluation`，并通过已有
scaffold API 写入全新的私有临时目录；调用方不能传 destination 或 `force`，清理
只作用于该 staging directory。

Catalog 创建只接受 opaque、当前 `available` 的 `catalogEntryId`。内部
`StudioBenchmarkAuthoringCatalogSource` 才持有源 root，公共 Catalog DTO 仍不暴露
路径。import：

1. 解析 manifest 并确定声明的 task、default Protocol、resource 与 ground-truth
   闭包；
2. 对每个路径逐级 `lstat`，拒绝 absolute、`..`、symlink 和 non-regular member；
3. 在支持时用 `O_NOFOLLOW` 打开，并比较 open 前、file descriptor 与 open 后
   stat，检测替换；
4. 流式复制到受管 content store，并校验声明 size/digest；
5. 重新验证 Catalog snapshot/package/protocol/source fingerprint；
6. 仅在完整 snapshot 一致时提交 draft/revision。

未声明文件被忽略且不会进入 identity；缺失声明 bytes、超限、混合 snapshot 或
源漂移会在数据库提交前失败。原 Catalog 树从不被改写。

## HTTP resource

同一资源同时接受 `/studio/...` 与既有 `/api/studio/...` normalization：

```text
POST /studio/benchmark-authoring/drafts
GET  /studio/benchmark-authoring/drafts?limit=&cursor=
GET  /studio/benchmark-authoring/drafts/{draftId}
GET  /studio/benchmark-authoring/drafts/{draftId}/revisions/{revisionId}
POST /studio/benchmark-authoring/drafts/{draftId}/revisions
```

create source 是严格 discriminated union：

- `template`：template、publisher、packageName、version；
- `catalog`：catalogEntryId。

save 必须提供 `clientRequestId`、`baseRevisionId` 和完整 strict document。新建
create/save 返回 201；精确幂等重试返回 200。响应继承 private/no-store、安全
Host/CORS 与 body-size policy。稳定错误映射为：

- 400：strict DTO、identity、cursor 或 unsupported route；
- 404：unknown/unavailable Catalog、draft 或非 owned revision；
- 409：idempotency reuse、stale revision、source drift 或完整性冲突；
- 413：definition/member/resource/total/body 容量；
- 503：repository 或 managed-content storage failure。

错误 body 不包含提交值、宿主路径、raw SQLite/Pydantic 异常、secret 或 device
handle。

## Composition 与零副作用边界

提供 database path 时，process-scoped Benchmark composition 构造一个 repository、
managed content store、package adapter 和 authoring application service；没有
database 的 definition-only composition 保持 authoring 为 `None`。这没有改变
已有 Catalog definition-only 行为，也不取得 Worker/recovery execution ownership。

完整 service journey 使用 canary instrument 覆盖 initializer、environment、
evaluator、device、component/plugin、model、secret、runtime、scheduler、
Experiment、publication 和 Replay；模板 create/get/list/save 全程调用数为零。
Catalog import 只复制 definition/resource bytes，不实例化 Package 声明的插件。

## 自动化验证

可复验命令：

```bash
uv run pytest -q \
  tests/studio/test_benchmark_authoring_resource.py \
  tests/studio/test_benchmark_http.py \
  tests/studio/test_benchmark_startup_recovery.py

uv run pytest -q \
  tests/benchmark/test_authoring.py \
  tests/benchmark/test_compiler_catalog_cli.py

uv run pytest -q tests/studio

uv run pytest -q \
  tests/packaging/test_benchmark_authoring_install.py \
  -m packaging_acceptance

uv run pytest -q \
  tests/packaging/test_benchmark_authoring_install.py \
  tests/packaging/test_benchmark_history_install.py \
  tests/packaging/test_benchmark_export_install.py
```

2026-07-30 实际结果：

- focused authoring/resource/HTTP/composition/restart：`67 passed`；
- 既有 Benchmark scaffold/authoring/Catalog/CLI：`19 passed`；
- complete Studio backend regression：`257 passed`；
- isolated clean-wheel no-device create/import/save/restart：`1 passed`；
- authoring、schema-8/History upgrade 与既有 export 的组合 clean-wheel
  regression：`3 passed`；
- production module compile 与导入、全部新/修改函数 docstring audit：通过。

clean-wheel 测试构建实际 wheel，在隔离 venv 和仓库外工作目录运行，并断言
`zhixing` 来自该 venv。它创建 template draft、导入 Catalog Package、保存 ordinal
2、重新构造 service、读取两个 draft，并在 Catalog source 可重读时验证 create
retry 返回原结果。

主要失败注入包括：

- non-finite、resolved secret、absolute/traversal、duplicate/unsorted inventory；
- symlink、non-regular、missing declared bytes、source definition drift；
- member、definition、单 resource 和总 import 上限；
- atomic finalize failure 与 repository transaction failure；
- 同 base concurrent writers、stale base 和 conflicting idempotency reuse；
- 跨 draft revision probing；
- 全部 runtime/device/plugin/model/secret/Experiment/report/Replay canary。

这些是本地 SQLite、无设备、临时文件和 clean-wheel 证据；没有运行前端 build，
因为 5.5A 没有修改 `studio/` 前端；也没有真实浏览器、真实 Android、真实外部
不受信插件或 publication 证据。

## 设计取舍

- parsed strict document，而不是任意 raw text：安全、identity 和持久重建简单，
  但无法保存语法损坏的 JSON/YAML 缓冲区；5.5B-1 需要在客户端处理编辑中的 raw
  text，再只提交可解析结构。
- mutable draft pointer + immutable revisions，而不是可变 Package 目录：提供可靠
  CAS、重启和审计语义，但每个 revision 会重复保存 definition JSON。
- content-addressed immutable objects，而不是把二进制放 SQLite：数据库保持有界且
  可移植；当前本地 adapter 没有 quota/GC，对象存储仍是后续能力。
- Catalog copy-import，而不是持久引用源目录：修订可重建且不受源漂移影响，但初次
  import 有额外 I/O 和存储成本。
- 保存安全中间态，而不是 save 即 validate：支持逐步 authoring，但 consumer 必须
  尊重 `unvalidated`，不得把 revision 当作 runnable/publishable Package。
- optimistic base revision，而不是锁住整个编辑会话：HTTP 无状态且冲突明确，但
  5.5B-1 必须提供可见 conflict/reload/reset 体验。

## 限制与下一步

5.5A 仍不提供：

- React Benchmark authoring route、structured editor、dirty/reset/conflict UI；
- raw unparsable task/manifest text 的服务端保存；
- validate、dry-run、field-addressable diagnostics 或 Contract Test Kit；
- validated revision freeze、Catalog publication、Package export 或 legacy JSON
  migration；
- resource mutation/delete、draft delete、quota、retention 或 content GC；
- PostgreSQL/object storage adapter、任意第三方代码的进程 sandbox；
- multi-Task/repeats/multi-Agent Worker 扩展或真实 Android acceptance。

原 5.5B editor 已永久拆为三个按依赖排序的 Change：

1. `implement-studio-benchmark-definition-editor-5-5b1`：构建独立
   `/benchmark-authoring` 与 `/benchmark-drafts/:draftId/edit` 路由，消费本
   Change 的 draft/revision/CAS resource，提供 template/Catalog 创建、
   structured manifest/split/Protocol、显式 JSON task buffer、inline JSON ground
   truth、dirty/reset/reload/conflict 与离开保护；resource 和文件型 ground truth
   inventory 保持只读；
2. `implement-studio-benchmark-authoring-content-5-5b2`：增加严格
   draft/revision/resource-scoped 的 managed-content upload/exact-read/replace/
   logical-remove 后端能力，并覆盖摘要、容量、幂等、CAS、临时对象晋升、失败清理
   和 immutable revision 保留边界；
3. `implement-studio-benchmark-resource-editor-5-5b3`：消费 5.5B-2，为 asset 与
   文件型 ground truth 增加 inventory/upload/replace/logical-remove UI；内容命令
   从 clean saved baseline 发起，成功后以返回 revision 重建编辑 baseline。

5.5B-1 与 5.5B-2 现已完成，验证边界分别见
[Studio Benchmark Definition Editor](studio-benchmark-definition-editor.md)与
[Studio Benchmark Authoring Managed Content](studio-benchmark-authoring-content.md)；
下一步固定为 `implement-studio-benchmark-resource-editor-5-5b3`。三个 Change
都不得提前
实现 5.5C-1/2 validation/dry-run resource/view、5.5D Contract Tests 或
5.5E publish/migrate，也不得把
resource 上传成功写成 Benchmark 语义有效或可执行的证明。

## 事实来源

- 用户先确定 Stage 5.5 必须按 5.5A–5.5E 的较细颗粒度实施；在 5.5A 完成后，
  又根据已验证的 metadata-only resource 与 JSON-only HTTP 边界，将原 5.5B
  永久细分为 5.5B-1/2/3，并要求先写入长期文档。
- Coding Agent 调查现有 Benchmark/Catalog/SQLite/HTTP 边界，生成本 Change 的
  DTO、repository、content/import adapter、service、composition、HTTP、测试和
  文档，并执行上述验证。
- 本文只把 5.5A 的实际代码和测试证据写成已实现事实；后续 Change
  的实现事实记录在各自长期文档，5.5C-1/2、5.5D 与 5.5E 仍是规划。
