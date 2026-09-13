# Studio Benchmark 分层无设备验收

本文记录 Stage 5.6B
`validate-studio-benchmark-layered-acceptance-5-6b` 已验证的事实、证据边界和可复现
命令。它是 5.6A 显式设备 authority 与 5.6C 真实 Android 验收之间的 no-device
回归闭环，不是新的产品资源，也不授予真实 Android 能力。

## 问题与涉及层

Stage 5 的 Core Runtime、Studio 持久服务、event/SSE、startup recovery、managed
publication、Report、Evidence、Replay、Export 和 React 页面此前分别有测试，但分散
通过不能证明同一 Experiment 的事实能跨层重建。静态浏览器 fixture 能显示错误态，
也不能证明 Composer 创建的 Experiment 真的经过 Worker 和 Core。

5.6B 连接以下层，但不创建第二套生命周期：

```text
Benchmark Package + immutable Agent revision + Protocol + fake profile
                              |
                              v
Catalog -> Composer -> durable Experiment/TaskRun -> Worker -> Core Runtime
                              |                         |
                              v                         v
                       journal / SSE              TaskResult
                              \                         /
                               v                       v
                         managed publication -> Report/Evidence
                                      |          |
                                      v          v
                                  native Replay  Export
```

生产 `StudioApplicationService`、SQLite repositories、scheduler、event waiter、
recovery owner、publisher、reporting、Replay 和 managed resolver 仍是权威 owner。
验收代码只注入 deterministic fake device/environment、稳定 seed、取消 barrier 和
明确 failure point。

## 前后执行流

以前：

```text
focused Core / repository / SSE / Replay tests
static browser response fixture
clean-wheel profile composition
  -> 各自成立，但没有一个安全、可机器检查的因果闭环
```

现在：

```text
authoritative product resources
  -> 14 个稳定场景
  -> bounded causal proof ledger
  -> exact scenario/order/identity/claim/canary validation
  -> actual-backend browser + external-Package clean-wheel + full regressions
```

proof ledger 是 disposable test artifact。它不进入 Studio HTTP、SQLite、Report、
Replay 或 bundle schema，避免形成 acceptance-only API 和第二事实源。

## Proof ledger 合同

`scripts/studio_benchmark_layered_acceptance.py` 定义 schema version 1，固定 fixture
version、14 个场景的顺序、最多 32 个场景、每场景最多 48 个标量事实、最多 64 个
命令和有界 identity 集合。它关联但不合并以下事实：

- Experiment、planned TaskRun、Core TaskRun、Agent run 和 durable event identity；
- report、trajectory、manifest、bundle、managed artifact 和 native Replay identity；
- service lifecycle、Agent status、Benchmark outcome、evaluation 与 publication；
- `contract_fixture` acquisition、`fake_device` environment、
  `realDeviceEvidence=false`；
- ADB discovery、真实设备构造、外部网络、模型、secret 和 repository-source fallback
  六个 forbidden-effect canary，全部必须为零；
- 固定 claim limits：没有执行真实 Android 验收、Studio Worker 仍为
  `1 Agent × 1 Task × 1 repeat`、不声称统计显著性、5.6C-1/2 仍然必需。

重复运行允许 opaque runtime ID 改变，但 scenario ordering、结果语义、identity
presence/cardinality、因果 join、canary 与 claim limits 必须一致。缺场景、重复终态、
无法解析的 identity、宿主绝对路径、raw target、secret-shaped text、artifact bytes 或
加强后的产品声明都会 fail closed。

## 已验证场景矩阵

| 场景 | 验证事实 |
| --- | --- |
| `studio_fake_pass` | PASS 经过 create、Worker、Core、publication、Report、Replay 和 artifacts，且终态唯一 |
| `studio_fake_fail` | Agent `SUCCESS` 与 Benchmark `FAIL` 独立，`INVALID=0`，evaluation 保留 |
| `studio_context_invalid` | 不兼容 context 在 initializer、Agent、model、evaluator 和 action 前被拒绝 |
| `studio_cancel_accepted` | accepted work 可取消，合法终态且至多一个 terminal event |
| `studio_cancel_active` | active work 在 cooperative safe boundary 停止并保留已确认事实 |
| `studio_create_retry` | 未知 create response 后相同 intent 只产生一个 Experiment、schedule、binding 和 accepted event |
| `studio_sse_reconnect` | bounded backfill、named SSE、`Last-Event-ID` 与 terminal drain 连续 |
| `studio_slow_client` | 慢订阅者不阻塞 journal、查询、Worker、publication 或终态 |
| `studio_recovery_interrupted` | 不确定 running/cancelling work 被中断，不重放设备或 Agent 副作用 |
| `studio_recovery_publication` | finalizing 只重试幂等 publication/finalization，保留 immutable result identity |
| `core_multi_cardinality` | Core 以 2 Agents × 2 Tasks × 2 repeats 执行完整 8-run matrix、稳定 seed、TaskInstance reuse 和 fairness facts |
| `studio_cardinality_rejected` | Studio public preview/create 与 defensive worker 对超出 1×1×1 的输入整体拒绝且副作用为零 |
| `installed_external_package` | 独立安装的 Benchmark distribution 从 metadata 发现并完成 durable fake Experiment 与完整 publication |
| `actual_backend_browser` | 真浏览器使用实际 fake backend 完成 Catalog → Composer → Monitor → Report/Evidence → Replay → Export |

Core multi-cardinality 与 Studio product limit 是两段独立证据。前者不能升级为 Studio
Worker 已支持 multi-Task、repeats 或 multi-Agent；5.6B 没有扩容 Worker。

## 浏览器与安装边界

实际后端浏览器 journey 使用 `scripts/studio_benchmark_layered_acceptance_server.py`
启动生产 HTTP/service composition，并只向 stdout 输出一个安全 bootstrap JSON。实测：

- Catalog 选择 Package/task、Composer 选择 immutable Agent revision、Protocol 和
  fake profile，preview 后显式 create；
- Monitor 到达 completed，显示一个 TaskRun、Agent success、Benchmark pass、
  `19/19` durable cursor、publication available 和 no-real-Android warning；
- 刷新后重建相同 Experiment、TaskRun 与 cursor，没有重复执行；
- Report 显示 PASS、独立 Agent/Benchmark 轴、Evaluation 和 canonical identities，
  没有 significance claim；
- native Replay 显示 `native_benchmark_task_run`、`fake_device`、
  `realDeviceEvidence=false`，并加载 38 个事件/时刻；
- Export preparation 先刷新 metadata 并执行 exact `HEAD`，浏览器接管下载后页面不
  声称观察到 OS 传输完成；manifest 有 11 个 closed-inventory members，且排除 hidden
  prompt；
- light/dark theme 均实际切换，浏览器控制台无 unexpected error。

静态 fixture 仅作为支持性 presentation evidence：它验证 JSON 中的
`<script>inert</script>` 以文本显示、ZIP 只下载不解压，以及 pending、missing、
corrupt、oversized、hidden 状态彼此局部隔离。它不能独立满足端到端 browser gate。

clean-wheel gate 在隔离环境安装 ZhiXing wheel 和独立 Benchmark distribution，从
repository 之外的 working directory 通过 installed metadata/resource 发现 Package，
完成一个 durable fake Experiment，并核对 report、trajectory、manifest、bundle、
native Replay 和 scoped GET/HEAD 的 checksum、length、identity 与内容一致性。六个
forbidden-effect canary 均为零。

## 最小缺陷修复

分层验收暴露并修复了三个不扩张合同的缺陷：

- Studio 默认 Catalog 的 action executor identifier 对齐公开注册项
  `zhixing.service.action_executor@1.0`；
- Core cleanup-stop 在已完成 evaluation 后保留结果，只把尚未执行的后续工作标为
  `SKIPPED`；
- React Replay strict parser 接受后端已定义的
  `native_benchmark_task_run` provenance；fake-device 与 partial-integrity banner
  分别渲染，互不遮挡。

此外，production benchmark composition 只增加可选的显式 resolver-factory 注入，
默认 production composition 不变。

## 验证证据

2026-08-02 的观察结果：

| Gate | 命令 | 结果 |
| --- | --- | --- |
| 5.6B focused | `env PYTHONPATH=tests .venv/bin/python -m pytest -q tests/studio/test_benchmark_layered_acceptance.py` | `28 passed` |
| external Package clean wheel | `.venv/bin/python -m pytest -q tests/packaging/test_studio_benchmark_layered_acceptance_install.py` | `1 passed` |
| backend full regression | `env PYTHONPATH=tests .venv/bin/python -m pytest -q` | `857 passed` |
| frontend typecheck | `cd studio && npm run typecheck` | passed |
| frontend lint | `cd studio && npm run lint` | passed |
| frontend unit/component | `cd studio && npm test` | `88 files / 392 tests passed` |
| frontend production build | `cd studio && npm run build` | passed；保留既有 large-chunk warning |
| actual-backend browser | 启动 acceptance server 后执行真实浏览器 journey | full causal journey passed；0 unexpected console errors |
| static browser fixture | `cd studio && npm run smoke:benchmark-monitor` 后检查失败态 | supporting presentation checks passed；0 console errors |

完整后端 suite 在普通受限 sandbox 中会因 loopback bind 权限和隔离安装无法联网而
产生环境性失败；在允许本机回环测试服务与既有依赖访问的相同源码环境中，同一命令
权威结果为 `857 passed`。这项环境说明不能替代任何失败测试。

## 取舍、替代方案与失败边界

- 选择小型代表场景加既有 focused matrices，而不是构造所有 failure cross-product；
  这样更易定位，但完整 fault coverage 仍由 owner-specific suites 提供。
- 选择 production composition 加 fake authority，而不是让 Node fixture 模拟 Worker；
  代价是实际 browser gate 需要本地 Python HTTP/SSE 服务。
- proof ledger 只保存 bounded safe facts，不复制所有公共响应或 artifact body；它证明
  identity closure，不是产品历史记录。
- recovery fixture 只在没有公开手段表达 crash window 时构造最小 durable precondition，
  且不能制造 success result。
- external Package 证明 distribution contract 与 source independence，不证明任意第三方
  代码安全；trusted plugin 仍不是进程 sandbox。

仍不支持或未证明：真实 Android service/browser、本轮的新鲜设备状态变化、Studio
multi-cardinality Worker、PostgreSQL/object storage、distributed ownership、
retention/delete、第三方 sandbox、任意设备/App/Benchmark 兼容、模型质量、自动失败
诊断或统计显著性。下一项固定为
`validate-studio-benchmark-android-service-5-6c1`，随后才是 5.6C-2 浏览器真机闭环。

## 可复现步骤

```bash
env PYTHONPATH=tests .venv/bin/python -m pytest -q \
  tests/studio/test_benchmark_layered_acceptance.py

.venv/bin/python -m pytest -q \
  tests/packaging/test_studio_benchmark_layered_acceptance_install.py

env PYTHONPATH=tests .venv/bin/python -m pytest -q

cd studio
npm run typecheck
npm run lint
npm test
npm run build
```

手动 actual-backend browser 验收：

```bash
env PYTHONPATH=tests .venv/bin/python \
  scripts/studio_benchmark_layered_acceptance_server.py \
  --workspace temp/studio-benchmark-layered-acceptance \
  --port 8765
```

读取 stdout 的单个 bootstrap JSON 中安全 URL/fixture identities；始终核对 warning
为 `fake device only; not real Android evidence`。结束时发送 SIGINT/SIGTERM，让 server、
worker 和 subscriber 正常 teardown。

## 30–60 秒面试说明

“Stage 5 各层原本都有测试，但没有一个证据能证明同一 Experiment 从 Composer 创建，
经过 SQLite、Worker、Core、SSE、publication，一直到 Report、Replay 和 Export 仍是
同一条因果链。我在不增加产品 API 的前提下做了一个 14 场景、版本化且有界的 proof
ledger，并用 production Studio composition 注入 deterministic fake device。它覆盖
PASS、Agent 成功但 Benchmark FAIL、pre-action INVALID、两种取消、重连、慢客户端、
两类恢复、Core 2×2×2 公平矩阵、Studio 1×1×1 拒绝、独立安装 Package 和真实浏览器
全链路。clean wheel 的 ADB、真实设备、网络、模型、secret、源码回退六个 canary 都是
零；后端 857、前端 392 项测试通过。这里证明的是 no-device/fake 分层闭环，真实
Android 正负例仍必须由下一步 5.6C-1 重新采集。”

## 常见追问

1. 为什么不把 proof ledger 做成产品 API？
   - 它只投影已有权威资源用于验收；持久化会制造第二事实源和 acceptance-only schema。
2. Core 2×2×2 已通过，为什么 Studio 仍不支持多 Agent？
   - Core Runtime 和 Studio Worker 是不同产品边界；Studio public/defensive gates 仍对
     超出 1×1×1 的请求整体拒绝且副作用为零。
3. 静态浏览器 fixture 还有什么价值？
   - 它高效覆盖 pending/missing/corrupt/oversized/download-only 等 presentation
     cross-product；真实因果链必须由 actual backend journey 证明。
4. 这能证明真实 Android 可用吗？
   - 不能。所有执行都是 `contract_fixture/fake_device`，明确
     `realDeviceEvidence=false`；5.6C-1/2 才能产生本轮 fresh real Android 证据。

## 贡献边界

- 用户确定 Stage 5.6 的拆分、必须先完成分层 no-device 证明、不得扩大 Worker 或真实
  Android 声明，以及永久文档和面试材料要求。
- Coding Agent 调查并连接现有 owner，编写 proof-ledger/harness/tests，执行 focused、
  clean-wheel、full-regression 和浏览器验证，修复验收暴露的最小兼容缺陷，并仅依据
  实际观察更新本文。
