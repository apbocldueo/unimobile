# Studio Benchmark Validated Freeze

本文记录 Stage 5.5E-1
`implement-studio-benchmark-validated-freeze-5-5e1` 的实际实现、验证证据、设计取舍与
边界。它把 exact current Benchmark authoring revision 重新做一次 server-owned、完整、
definition-only 的全 split 验证，形成独立 immutable validation attestation，并冻结
closed immutable Package revision。它不发布 Catalog、不导出 Package、不迁移 legacy
BenchmarkTask JSON，也不执行 Agent、Benchmark、插件、设备、模型或网络。

## 状态与范围

截至 2026-08-01，本 Change 已实现并验证：

- strict schema-1 freeze request、all-split validation fact、attestation、Package revision、
  ordered member 与 result DTO；未知字段、类型 coercion、unsafe path、host path、secret、
  live object、非有限值和无界集合均 fail closed；
- exact-current preflight、early idempotency lookup、response-loss retry、request-ID
  fingerprint conflict 与 atomic final-current commit；
- 对 manifest 声明的全部 split 顺序做 FULL compile 与 definition-only dry-run，而不是只
  验证 UI 当前选择的 split；任何 split 失败都会阻止 attestation 和 Package revision；
- manifest、task split、全部 Protocol、asset 与 file-backed ground truth 的 closed member
  closure；definition 采用 canonical UTF-8 JSON bytes，binary member 流式校验 size 与
  SHA-256；
- path/CWD/mtime/JSON-whitespace-neutral 的稳定 logical-path-sorted inventory 与 closure
  identity；未声明源文件、未引用 content object 和私有 storage key 不进入结果；
- SQLite schema 9 的 immutable validation attestation、Package revision、ordered member
  mapping 与 scoped freeze-command durability；schema 8 数据可单调升级，不重写旧行；
- strict local POST/GET HTTP resource、private `Cache-Control: no-store`、安全错误映射与
  restart reconstruction；
- mixed definition/content、多 split、多 Protocol、inline/file-backed ground truth、
  managed content、late current change、missing/corrupt content、DB failure 与 clean-wheel
  验证；
- 完整 Studio backend `344 passed`、frontend 80 files / 367 tests、typecheck、lint、
  production build、相关回归、clean-wheel 与 OpenSpec strict validation。

成功 freeze 只证明该 exact revision 的声明与 managed bytes 在固定 validation contract
下形成了完整、可重建的 definition-level Package closure。`executionEvidence`、
`realDeviceEvidence`、`modelEvidence`、`packagePluginEvidence` 与
`publicationEvidence` 始终为 false；5.5C transient result 和 5.5D fake-fixture result
都不授予资格。

## Agent / Benchmark 问题与前后流程

5.5A/B 提供 durable authoring revisions 与 managed content，5.5C 提供 transient
validation/dry-run，5.5D 提供 disposable fake contract facts。它们都不能作为后续发布的
immutable authority：草稿可能已变化、用户可能只分析了一个 split、浏览器结果可能刷新即
消失，Contract Test 也不覆盖真实 Package code。E-1 因此在 server 端重新建立一条可持久、
可审计且不混入执行证据的 freeze boundary。

```text
before
  authoring revision ── transient validate/dry-run ── disposable facts
                    └─ fake Contract Tests ───────── disposable facts
  no durable validated authority / no closed frozen Package revision

after
  exact current draft revision + idempotent command
                    │
           early durable retry lookup
                    │
       private disposable materialization
                    │
       every manifest-declared split
        FULL compile + bounded dry-run
                    │
        closed definition/content closure
        canonical JSON + verified binaries
                    │
       final current-pointer recheck
                    │ one SQLite transaction
        ┌───────────┴────────────┐
  immutable attestation   immutable Package revision
                         + ordered member mapping
                    │
             scoped exact GET only

  Catalog mutation / export / migration / runtime / device / model
  / Package plugin construction / Experiment ── never supplied
```

## 分层与依赖边界

- `benchmark_authoring_freeze_models.py`：strict wire/durable contracts、validation contract
  version、request fingerprint、fixed safety facts 与 closure identity；
- `benchmark_authoring_freeze.py`：从 exact authoring document 派生 declared closure，编码
  definition bytes，并通过 content store 校验 binary members；
- `benchmark_authoring_freeze_service.py`：all-split analyzer 与 freeze orchestration；它只
  依赖 repository、existing private compiler/materializer、closure builder、clock 和 opaque
  identity factory；
- `benchmark_authoring_repository.py` / `database.py`：schema-9 migration、strict row
  reconstruction、early retry、atomic commit 与 draft-scoped exact read；
- `benchmark_authoring_storage.py`：沿用 server-owned content-addressed store，并增加
  canonical definition bytes 的 atomic promotion；
- `httpd.py` / `benchmark_composition.py`：接入 existing local Studio Host 与 application
  composition，不增加 React state、Catalog publisher、exporter 或 migration service。

service dependency graph 中没有 device、model、secret、network、plugin registry、Agent
runner、Benchmark runner、Experiment、report、Replay、Catalog mutation 或 export
capability。这是构造级边界，不依赖调用者“记得不调用”。

## 已验证合同

### 1. Exact current、all-split 与独立 attestation

请求只接受 `schemaVersion`、`clientRequestId` 和 `revisionId`。服务在私有重建前确认
ownership/current，在每个 split 分析结束后再次确认 current，并在最终事务中第三次以
expected revision 做 CAS。并发 save 发生在任何一个窗口都会返回 409，不会让旧 revision
获得新的 freeze authority。

all-split analyzer 按 manifest split 顺序逐一复用 5.5C-1 compiler：验证 Package、task、
Protocol、ground-truth binding、dependency、budget、完整 deterministic schedule、fairness
与 relative output layout。总 split 上限 64，aggregate schedule 上限 10,000；diagnostic、
warning、unverified 与 member 都有独立上限。任何错误或截断都会整体失败，不产生 partial
attestation。

成功后创建新的 `ValidationAttestationV1`，而不是把既有 authoring revision 的
`unvalidated` 状态改名。attestation 固定绑定 draft、authoring revision、document
fingerprint、validation contract version、Core Package/content identities、每个 split 的
Plan/Protocol identity、task/schedule/budget/layout/fairness/unverified facts 与明确 safety
facts。

### 2. Closed immutable Package closure

closure 只允许 authoring document 已声明的成员：

- `benchmark.yaml` manifest；
- manifest 指向的全部 task split；
- authoring document 中的全部 Protocol members；
- manifest assets；
- task 引用的 file-backed ground truth。

manifest、task 与 Protocol 的 strict authoring documents 以 canonical JSON 编码；JSON 是
合法 YAML 子集，同时避免原始缩进、key order 和工作目录影响 frozen bytes。inline JSON
ground truth 仍是 task definition 的普通数据，不被错误提升为独立 binary member。binary
members 必须从 opaque content identity 打开，并在 bounded streaming 中同时匹配声明 size
与 SHA-256。

成员按 normalized POSIX logical path 排序，每项记录 kind、media type、size、SHA-256 与
immutable content identity。`closureIdentity` 对这些语义字段做 canonical hash，不包含
ordinal/storage path/mtime/CWD；ordinal 只作为数据库中完整顺序的重建保护。

### 3. 身份不能互相替代

| 身份 | 回答的问题 | 不能作为 |
| --- | --- | --- |
| authoring document fingerprint | exact revision 文档是否相同 | Package member capability |
| Core Package identity | `publisher/name@version` 是什么 | 内容相同证明 |
| Core Package content identity | Core 编译所见内容语义是否相同 | frozen byte closure 的下载能力 |
| Plan / Protocol identity | 每个 split 的计划与协议是否相同 | 其他 split 的证据 |
| closure identity | 完整 ordered member metadata/bytes 是否相同 | Catalog publication 状态 |
| attestation / Package revision ID | 哪个 durable immutable resource | canonical semantic hash |
| request fingerprint | 同一 client request 的 payload 与 validation contract 是否相同 | authoring fingerprint |

`clientRequestId` 只在 draft scope 内幂等。相同 ID + 相同 fingerprint 在 response loss 后
直接返回原结果且不重跑分析；相同 ID + 不同 fingerprint 返回 409。不同 command ID 可以对
同一 current revision 产生独立 attestation/Package revision，这是审计资源语义，不是
content deduplication 语义。

### 4. Schema 9 与原子可见性

schema 9 新增：

- `studio_benchmark_validation_attestations`；
- `studio_benchmark_package_revisions`；
- `studio_benchmark_package_revision_members`；
- `studio_benchmark_freeze_commands`。

foreign keys、draft ownership、attestation/package one-to-one、member ordinal/path uniqueness、
declared member count 与 command result 关系在写入和读取时共同校验。读取发现缺 member、
ordinal gap、identity/count 不一致或 bounded JSON 损坏时 fail closed，不返回“尽量可用”的
Package。

canonical definition objects 与 verified binary objects 先进入 immutable content-addressed
store，随后 attestation、Package revision、完整 members 和 command result 在一个 SQLite
事务中原子提交。若最终 DB commit 失败，可能留下不可达 content object，但不会出现可查询
的 partial Package authority；当前没有 retention/GC。

### 5. Local HTTP resource

```text
POST /studio/benchmark-authoring/drafts/{draftId}/package-revisions
GET  /studio/benchmark-authoring/drafts/{draftId}/package-revisions/{packageRevisionId}
```

POST 新建返回 201，exact idempotent retry 返回 200；GET 只通过 owning draft 返回 immutable
metadata，重启后不依赖 mutable current draft。没有 list、member download、publish、export
或 migration route。成功和失败均为 private `no-store`；公共 JSON 不包含 bytes、host path、
managed path、storage key、secret 或 live capability。

malformed/unknown request 为 400，foreign ownership 隐藏为 404，stale/current 或
idempotency conflict 为 409，预工作容量失败为 413，private storage/service unavailable 为
503，known route unsupported method 为 405。missing declared content 是 definition
eligibility failure；已存在但 size/digest 不符的 managed object 是 storage integrity failure。

## 验证证据

### Focused、回归与 HTTP

```bash
UV_CACHE_DIR=/tmp/unimobile-uv-cache uv run pytest -q \
  tests/studio/test_benchmark_authoring_freeze.py
# 12 passed

UV_CACHE_DIR=/tmp/unimobile-uv-cache uv run pytest -q \
  tests/studio/test_benchmark_http.py
# 14 passed

UV_CACHE_DIR=/tmp/unimobile-uv-cache uv run pytest -q tests/studio
# 344 passed

UV_CACHE_DIR=/tmp/unimobile-uv-cache uv run pytest -q \
  tests/studio/test_benchmark_authoring_resource.py \
  tests/studio/test_benchmark_authoring_content.py \
  tests/studio/test_benchmark_authoring_materializer.py \
  tests/studio/test_benchmark_authoring_analysis.py \
  tests/studio/test_benchmark_authoring_contracts.py \
  tests/studio/test_benchmark_authoring_freeze.py
# 相关 Stage 5.5 backend suites passed

UV_CACHE_DIR=/tmp/unimobile-uv-cache uv run pytest -q tests/benchmark
# 113 passed

PYTHONPATH=.:tests UV_CACHE_DIR=/tmp/unimobile-uv-cache uv run pytest -q \
  tests/contracts tests/graph tests/runtime \
  tests/benchmark/test_authoring.py \
  tests/benchmark/test_contract_testing.py
# 91 passed
```

HTTP/full Studio tests 需要允许本机 loopback socket；这不是产品外部网络能力。

### Frontend non-regression

```bash
cd studio
npm run test
# 80 files / 367 tests passed
npm run typecheck
npm run lint
npm run build
# passed; 607 modules transformed
```

production build 仍报告既有大 chunk warning；E-1 没有新增 React route、mode、button 或
client state。

### Clean wheel 与 failure injection

```bash
UV_CACHE_DIR=/tmp/unimobile-uv-cache uv run pytest -q \
  tests/packaging/test_benchmark_authoring_install.py \
  -m packaging_acceptance
# 4 passed
```

验收从源码构建并安装 wheel，从 repository-independent working directory 创建 managed
multi-split Package，freeze、retry、restart 后重建相同 member closure。source revision、
current pointer 和 `unvalidated` 状态不变，没有 runtime products。

failure injection 覆盖 schema-8 populated migration、foreign ownership、duplicate member、
corrupt row、invalid non-selected split、missing/corrupt managed content、concurrent save、
final-current rollback、response-loss retry、post-content DB failure 与 restart。测试确认失败
不会产生 queryable attestation、Package revision 或 command authority；device/model/
network/secret/plugin/initializer/evaluator/Agent/Benchmark/Experiment/publication/export/
runtime-output boundary 均未进入 service graph。

## 设计取舍、限制与失败情况

- 选择 freeze 时重新分析，而不是持久化 5.5C browser result；多一次同步计算，但 authority
  不依赖可能 stale、partial 或客户端所有的事实；
- 选择全部 manifest split，而不是调用者选择 split；大型 Package 成本更高，但不会把未验证
  split 隐藏在同一发布候选中；
- 选择 canonical JSON 保存 definition，而不是复制源 YAML formatting；获得稳定 bytes 与
  identity，代价是 frozen representation 不保留作者排版；
- 选择 content-first、metadata-second；DB 失败时不会有 partial authority，但可能留下不可达
  immutable objects，当前没有 GC；
- 选择每个成功 command 创建独立 opaque audit resources，不把相同 content 自动合并；
- synchronous freeze 没有 server-side cancellation/后台 job；容量上限负责在无界工作前拒绝；
- 没有 Package member download/list、React Freeze UI、Catalog publish、version conflict、
  deterministic export、legacy migration、retention/delete、object storage 或 PostgreSQL；
- 没有 Package plugin、initializer/evaluator、Agent/Benchmark、Experiment、device、model、
  network、secret 或 Android 执行，因此不能声称真实可运行或通过率；
- attestation 只证明固定 validation contract 下的 definition/content closure。validation
  contract 改版必须进入 request fingerprint，不能静默复用旧 command authority。

## 手工复验

可使用现有 Studio local Host 对一个 clean current draft 发起：

```bash
curl -i -X POST \
  -H 'Content-Type: application/json' \
  --data '{"schemaVersion":1,"clientRequestId":"manual-freeze-1","revisionId":"<revision-id>"}' \
  'http://127.0.0.1:<port>/studio/benchmark-authoring/drafts/<draft-id>/package-revisions'

curl -i \
  'http://127.0.0.1:<port>/studio/benchmark-authoring/drafts/<draft-id>/package-revisions/<package-revision-id>'
```

预期：首次 POST 为 201，相同 payload 重试为 200 且 IDs 不变；GET 返回同一 attestation、
Package revision 与完整 logical-path-sorted inventory；draft current、authoring fingerprint 和
status 不变。修改 draft 后用旧 revision freeze 应为 409；修改 request body 但复用相同
`clientRequestId` 也应为 409。

## 当前下一步

E-1 的直接后继 `implement-studio-benchmark-publish-export-5-5e2` 已实现：它只消费
E-1 frozen Package revision，显式发布到 server-owned managed Catalog source，并从同一
frozen closure 生成 deterministic versioned export。实现与证据见
[Studio Benchmark Package Publication / Export](studio-benchmark-package-publication-export.md)。
当前下一项固定为 E-3 legacy migration；Stage 5.6 Android acceptance 也仍是规划能力。

## 事实来源

- Stage 5.5E-1/2/3 顺序和边界来自用户固化路线与本 Change 的 OpenSpec artifacts；
- 5.5A/B/C/D、Core Package compiler 与 authoring content store 是此前已验证基础；
- Coding Agent 实现并运行了本 Change 的 model、schema/repository、closure、analyzer、
  service、HTTP、composition、failure-injection、regression、clean-wheel 与本文档；
- requirement、design 与完整 acceptance scenarios 保存在对应 OpenSpec Change 中。
