# Studio Benchmark Export

本文记录 Stage 5.4D-3
`implement-studio-benchmark-export-5-4d3` 在 2026-07-30 的已验证实现边界。
它描述正式 report、trajectory、publication manifest、bundle 与允许下载 evidence
的准备和浏览器交接；不把浏览器接管写成下载完成，也不把 no-device fixture 写成
真实 Android 或真实 multi-Agent 执行证据。

## 解决的问题

5.4D-2 已能安全预览有界 evidence，但正式报告材料仍缺少统一导出交互。前端如果
直接 fetch 大 bundle，会把完整二进制长期放进 JavaScript 内存；如果只渲染一个
链接，又无法在 handoff 前发现 stale、missing、corrupt 或跨 scope descriptor。

5.4D-3 将该缺口收口为两条分离的数据路径：

```text
metadata control plane
  Experiment + TaskRuns + closed artifact inventory
        → strict export projection
        → refresh authoritative metadata
        → exact HEAD through managed resolver
        → prepared / retryable local state

browser data plane
  exact refreshed links.content
        → ordinary attachment anchor
        → browser/OS owns transfer
        → UI records handoff only
```

涉及层：

- `zhixing/studio/httpd.py`：四类既有 content capability 的共享 GET/HEAD 响应
  合同；
- `shared/api`：strict local capability 与无 body HEAD 响应验证；
- `entities/benchmark-report`：strict publication manifest、export API 与材料
  identity；
- `features/benchmark-reporting`：closed-inventory projection、per-artifact
  single-flight、refresh/prepare/retry 与 Export drawer；
- `widgets/benchmark-report-workbench`：接入已有 Report，不复制 Viewer/Replay；
- no-device fixture、前后端合同测试、clean-wheel 和真实浏览器 journey。

本 Change 没有增加数据库 schema、新 artifact identity、新 bundle builder 或新的
下载 endpoint。

## 后端 GET/HEAD 合同

以下四类既有 exact capability 同时支持 GET 与 HEAD：

```text
/studio/benchmark-experiments/{experimentId}/report
/studio/benchmark-experiments/{experimentId}/bundle
/studio/benchmark-experiments/{experimentId}/artifacts/{artifactId}
/studio/benchmark-experiments/{experimentId}/task-runs/{taskRunId}/artifacts/{artifactId}
```

GET 与 HEAD 共用 `_handle_benchmark_content` 和 managed
`open_artifact()` resolver。处理顺序保持一致：

1. 校验 opaque Experiment、TaskRun 与 artifact identity；
2. 校验 same-Experiment/same-TaskRun scope 和 component availability；
3. 打开 server-owned regular file；
4. 重新计算 size/hash 并在异常时持久收口为 `missing` 或 `corrupt`；
5. 产生相同的安全响应头；
6. HEAD 关闭已验证 stream，不发送 body；GET 流式发送 body。

成功响应提供：

```text
Content-Type: <allowlisted exact media type>
Content-Length: <canonical exact bytes>
Content-Disposition: attachment; filename="<safe opaque filename>"
Cache-Control: private, no-store
X-Content-Type-Options: nosniff
```

report 与 bundle route 使用由已校验 Experiment identity 派生的
`<experimentId>.report.json` 和 `<experimentId>.zip`；generic artifact route
只使用 opaque artifact id。文件路径、storage ref 和不可信 metadata 不进入
filename。配置允许的浏览器 Origin 可以使用 HEAD，并能读取
`Content-Disposition`、`Content-Length` 和 `Content-Type`；其他 Origin 仍不被
开放。

HEAD 会和 GET 一样完整读取并 hash 大文件。这是 integrity-over-I/O 的明确取舍，
不是 range probe。HEAD 与后续 GET 之间仍可能存在 TOCTOU，因此 GET 必须再次通过
同一 resolver；前端永不把 HEAD 成功写成下载完成或客户端 digest 验证。

## Closed-inventory export projection

Export 只消费当前 Report 已收口的：

- authoritative Experiment resource；
- authoritative TaskRun page；
- 完整且 `nextCursor=null` 的 bounded Experiment artifact inventory。

`projectBenchmarkExportMaterials` 在纯函数边界生成：

- Experiment report；
- Experiment bundle；
- Studio publication manifest；
- 按 Studio TaskRun 分组的 trajectory、task report 和其他可下载 evidence；
- Experiment-scoped other evidence；
- 独立 unavailable state；
- aggregate hidden count。

projection 要求每个可下载材料都保留原 descriptor、scope 和 exact
`links.content`。它不会根据 kind、reference、artifact id 或文件后缀拼 URL，也
不会从 bundle 内部反推 manifest。inventory 未收口、超过 2,000 item、identity
冲突或 capability 不安全时整体 fail closed。

一个 report、trajectory 或 evidence 失败不会禁用 bundle；同理 bundle 失败不会
覆盖已经验证的 report、Evaluation、metrics 或 Replay。

## Strict publication manifest

Export drawer 只通过 manifest descriptor 的 scoped capability 获取
`studio-publication-manifest.json`。parser 上限为 2 MiB 和 2,000 members，并严格
验证：

- schema/kind；
- Experiment 与 TaskRun identity；
- member reference、kind、media type、size、SHA-256、scope 和 availability；
- member reference 唯一性与 canonical digest summary；
- excluded evidence 的 allowlisted shape。

界面显示 bundle identity、member count、总字节、每个 member 的 reference/kind/
scope/hash，以及 `excludedEvidence`。Prompt 的默认 hidden policy 可以被明确
审阅，但不会显示 Prompt body。secret、raw device serial、绝对路径、storage ref
和后端原始异常也不会进入该视图。

manifest review 不是 bundle verifier：浏览器不解压 ZIP，也不重新计算所有 member
digest；正式 bundle 的写入和 read-time integrity 仍由后端 publication boundary
权威控制。

## Prepare、single-flight 与 handoff

每个 export target 使用稳定 key 独立管理：

```text
idle
  → refreshing metadata
  → verifying exact HEAD
  → ready
  → browser handoff

refreshing / verifying
  → stale / unavailable / missing / corrupt / request failed
  → retry
```

准备操作会重新获取 Experiment、TaskRuns 和完整 inventory，再重新投影目标。只有
刷新后仍存在同一 artifact identity、scope、availability、MIME、size 和 exact
capability 时才发送 HEAD。HEAD 必须返回成功状态、相同 normalized
`Content-Type`、canonical `Content-Length` 和 attachment disposition。

同一 artifact 的 prepare 使用 single-flight；快速双击不会产生两个并发 HEAD。
不同 artifact 可以独立准备。换 Experiment、换 TaskRun、reset 或 unmount 会 abort
请求并通过 generation guard 忽略迟到结果。失败后 single-flight 会释放，用户可
重新 refresh/prepare；不会回退到宿主文件系统或旧 link。

ready 后的下载 action 是普通 `<a href>`。report、trajectory、manifest、bundle
和其他证据都由浏览器直接消费 exact managed capability；JavaScript 不 fetch 大
文件 body、不创建 bundle Blob，也不观察 OS transfer completion。界面只显示：

> Link handed to the browser. Browser/OS transfer completion is not observed.

## UI 与已有功能边界

Export 是 Report workbench 内的非 modal drawer：

- header 的显式 Export 按钮打开；
- Escape、Close 与焦点恢复可访问；
- Experiment materials、TaskRun groups、other evidence、unavailable 和 hidden
  区域独立；
- other evidence 使用有界本地分页；
- manifest review 与 prepare/download 分开；
- TaskRun selection 改变时关闭旧 manifest review，但不修改 Report URL ownership。

Viewer 仍负责有界预览，Replay 仍使用具体 TaskRun 的权威 `links.replay`。Export
没有复制 causal resolver、媒体预览器或 Replay route，也没有启动 Monitor event
session。

## 自动化验证

可复验命令：

```bash
cd studio
npm test
npm run typecheck
npm run lint -- --no-warn-ignored
npm run build
node --check scripts/benchmark-monitor-smoke-fixture.mjs

cd ..
uv run pytest -q \
  tests/studio/test_benchmark_experiment_resource.py \
  tests/studio/test_benchmark_execution_worker.py \
  tests/studio/test_benchmark_event_stream.py \
  tests/studio/test_benchmark_publication_replay.py \
  tests/studio/test_benchmark_startup_recovery.py \
  tests/studio/test_benchmark_reporting_resource.py \
  tests/studio/test_benchmark_experiment_history.py \
  tests/studio/test_replay_backend.py

uv run pytest -q \
  tests/packaging/test_benchmark_export_install.py \
  -m packaging_acceptance
```

实际结果：

- complete Studio：`57 files / 254 tests passed`；
- typecheck、lint、fixture syntax：通过；
- production build：通过；仅保留既有 `>500 kB` chunk warning；
- relevant backend resource/worker/event/publication/recovery/reporting/
  History/Replay：`129 passed`；
- isolated clean-wheel export acceptance：`1 passed`。

clean-wheel 测试在独立 venv 和仓库外 working directory 安装 wheel，并断言
`zhixing` 来自该环境的 `site-packages`。它真实启动已安装 HTTP server，验证四类
GET/HEAD header parity、report/trajectory/manifest/bundle body、ZIP 完整性、
Prompt hidden manifest policy、missing `404` 和 corrupt `409` closure。

## no-device 浏览器 journey

fixture 提供真实有界 report、trajectory、manifest 和一个有效的
4,194,462-byte uncompressed ZIP，以及 partial、missing、corrupt、hidden 和
script-looking canary。HEAD 对该 bundle 返回精确长度且没有 body；下载后的 ZIP
通过 `unzip -t`。

真实浏览器已完成：

```text
History
  → authoritative Report link
  → Evaluation Evidence Viewer
  → native TaskRun Replay
  → back to Report
  → Export drawer
  → manifest review
  → prepare report / trajectory / 4.0 MiB bundle
  → exact browser handoff
```

观察到：

- report、trajectory、bundle 各自准备并可独立 handoff；
- manifest 显示 2 个成员、scope/hash 和 Prompt hidden exclusion；
- unavailable、missing、corrupt 与 hidden 状态没有被折叠成通用成功/失败；
- bundle 在 prepare 阶段只走 metadata/HEAD，未被 JavaScript body preload；
- UI 始终使用 handoff 文案，没有伪造下载完成回执。

fixture 没有设备、Worker、插件、模型或 SSE 执行边界。这证明 no-device 浏览器
交互和请求合同，不证明真实 Android、真实多 Agent scheduler 或统计显著性。

## 设计取舍

- 使用 HEAD 而不是前端 fetch body：避免大文件 JS 内存，但多一次完整服务端 hash
  I/O。
- handoff 使用普通 anchor 而不是 File System Access API：跨浏览器合同更小，但
  无法提供 completion receipt 或保存位置。
- 复用 closed inventory 而不是增加 export session resource：没有第二套持久状态
  机，但页面关闭后 prepared 状态不会保留。
- manifest 单独严格获取而不是扫描 ZIP：保持 publication metadata 权威，但不会
  在客户端证明 ZIP 内每个 member。
- per-artifact single-flight 而不是全局 export lock：局部失败互不污染，但并行
  准备不同 artifact 仍会产生独立 resolver I/O。

## 限制与失败情况

- 浏览器 handoff 不是下载完成、文件落盘或用户打开文件的证明；
- HEAD 不是客户端 digest 验证，且 HEAD→GET 有 TOCTOU；GET 的重复验证才是最终
  权威；
- HEAD 会完整 hash 大文件，当前没有 range、resume 或对象存储 signed URL；
- inventory 与 manifest 分别受 2,000 item/member 上限，manifest 受 2 MiB 上限；
- prepared/single-flight 是当前页面内的 React local state，不跨刷新持久化；
- 不生成新 bundle，不做 retention/delete/quota、PostgreSQL 或 object storage；
- 当前真实执行切片仍是单 Agent × 单 Task × 单 repeat；
- 没有新增真实 Android trajectory，Viewer/Replay 仍只支持人工复核，不是自动
  failure diagnosis。

## 固定下一步

Stage 5.4 已完成。下一步是：

```text
implement-studio-benchmark-authoring-5-5
```

