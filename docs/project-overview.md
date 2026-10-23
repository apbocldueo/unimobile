# ZhiXing 新版项目总览

## 项目定位

ZhiXing 是一个 backend-first 的 Mobile Agent 基础设施，用于组合、运行、扩展和
公平评估移动端 Agent。它希望解决的不是“写死一个能操作手机的 Agent”，而是让
开发者可以：

- 使用 YAML 或 Python SDK 拼装不同结构的 Mobile Agent；
- 复用内置组件，或从独立 Python/Git distribution 加载外部组件；
- 让同一 AgentGraph 运行普通任务或进入 Benchmark；
- 让同一 Benchmark 在一致环境中评估多个 AgentGraph；
- 在 Android 设备上执行真实动作，并保留可审计的结果与轨迹。

新版后端的核心关系是：

```text
Agent YAML / Python SDK
          │
          ▼
      AgentGraph ───────────────┐
                               │
Benchmark JSON / Package       │
          │                    │
          ▼                    ▼
     BenchmarkPlan     Graph / Device Runtime
          │                    │
          └──── ExperimentProtocol ────┐
                                       ▼
                             Build → Run → Evaluate
                                       │
                                       ▼
                         Result / Report / Trajectory
```

`AgentGraph`、`BenchmarkPlan` 和 `ExperimentProtocol` 是三个相互独立的定义。
Benchmark 不是挂在 Agent 后面的一个布尔判断，而是与 Agent 构建并列的产品线。

## 核心模型

### AgentGraph：Agent 的语义表示

AgentGraph 描述 Agent 由哪些组件、节点、边、状态、条件和有界反馈组成。Python
SDK 和图原生 YAML 会编译为同一种 AgentGraph；表达方式不同但语义相同时，它们
具有相同 canonical identity。

Graph Runtime 执行的是通用图语义，不应包含 camera、具体 Benchmark、具体插件
或某一种 Agent 范式的硬编码分支。新的 Agent 范式应优先通过组件、条件、循环和
可复用子图表达，而不是新增一套 Kernel。

### Component：可组合的能力单元

组件使用正式的类型、配置和调用合同，运行时接收 `RuntimeContext`。内置组件与
外部组件进入同一个 Catalog、绑定和执行流程。

第三方组件可以作为 wheel、editable source 或固定 Git commit 安装，并通过
`zhixing.components` Entry Point 被发现。Contract Test Kit 用于检查声明、配置、
输入输出和安全诊断，但第三方 Python 代码当前仍在宿主进程中运行，不等于已经
获得进程沙箱或权限隔离。

### Graph Runtime 与设备边界

Runtime 负责节点调度、状态、条件、反馈、预算、生命周期事件和结构化结果。
Android/Harmony 设备实现位于 `zhixing/devices/`；设备观察与动作副作用必须经过
显式边界，例如 `ObservationProvider` 和 `ActionExecutor`。

当前新版 Graph Runtime 的真实闭环证据以 Android 为主。已有代表性内置图和外部
组件增强图在 emulator 上执行成功，但这不证明任意 AgentGraph、任意任务或任意
Android/Harmony 设备均已支持。

### Benchmark：独立的定义、执行与报告系统

旧 `BenchmarkTask` JSON 继续保留。新版还支持带 identity、version、tasks、
assets、ground truth 和默认 Protocol 的 Benchmark Package，并将其无副作用地
编译为 `BenchmarkPlan`。

`ExperimentProtocol` 单独描述 seed、repeats、预算、设备/App 约束、reset、
cleanup 和 failure policy。`BenchmarkExperimentRuntime` 使用同一个设备会话编排：

```text
materialization → reset → setup → evaluator pre-hook
                → AgentGraph → evaluation → cleanup → reporting
```

Evaluation Tree 支持 AND、OR、SEQUENCE、THRESHOLD 和 WEIGHTED 等组合，并保留
叶子 evaluator 的结构化证据。Agent `RunStatus.SUCCESS` 与 Benchmark
PASS/FAIL/INVALID/SKIPPED 是不同事实：Agent 正常结束并不自动代表任务完成。

每次运行可生成版本化 result、run/experiment report、JSONL trajectory、manifest
和可校验 bundle。Trajectory 用于审计和人工定位失败阶段；项目目前不宣称自动
失败诊断。

## 当前已经验证的能力

- Python SDK 与图原生 YAML 可以构造、验证、绑定和运行 AgentGraph；
- 内置组件可组合为真实 Android Agent，并由可配置 Verifier 控制反馈与结束；
- 外部组件具有作者 API、Contract Test Kit、Entry Point 发现、Catalog 解析和
  RuntimeContext 运行证据；
- wheel、editable 和固定 Git commit 三种外部组件来源已通过干净环境验证；
- AndroidWorld 与 AppAgent 已包装为首批 Benchmark Package，旧 Benchmark JSON
  路径继续保留；
- BenchmarkPlan、ExperimentProtocol 与 ExecutableAgent 已进入统一 Graph
  Runtime，不依赖旧 AgentRunner；
- fake device 已覆盖多任务、多 Agent、repeats、公平复用、失败和预算语义；
- `emulator-5554` 上已验证内置 SDK/YAML 拍照 PASS、合法提前结束的受控 FAIL、
  两个不同 AgentGraph 的 paired comparison、外部组件参与真实图，以及独立外部
  Benchmark Package；
- 真实验收同时检查 Agent 状态、Evaluator Result V2、Benchmark outcome、
  MediaStore 增量、报告、trajectory 和 bundle，而不是相信 Agent 自报成功；
- 完整回归在该验收里程碑结束时为 380 项测试通过。
- Studio Agent Builder 已建立严格 capability schema 3、统一安全 Component Catalog、
  deterministic AgentGraph 1.1 lowering、完整 projection/source map、SQLite immutable
  revision、optimistic conflict 和本地 HTTP API；
- React Builder 只展示 Input、Output、六个核心能力与批准的 Grounder/Tool 扩展；LLM、
  设备服务、控制节点和 Benchmark 生命周期对象分别由 Inspector、lowering 或 Benchmark
  产品线拥有。旧 schema-1/2 revision 继续可读，但不能启动新 Run/Experiment。详见
  [Studio Mobile Agent 能力组件创作](studio-agent-capability-authoring.md)；
- Studio schema-3 编译图已通过通用 fake Runtime；本变更的 focused backend、通用 Graph、
  Catalog 与组件回归及完整前端 Vitest 已通过，前端 typecheck、lint 和隔离 production build
  已通过。clean-wheel、数据库迁移和浏览器证据以本变更最终验证记录为准，不沿用旧里程碑数字。
- Studio Stage 2 已建立版本化离线 Replay envelope、SQLite 索引、受控 Local Artifact
  Store、legacy/native 显式导入、安全 artifact/bundle API，以及真实 History 和
  三栏 Replay 工作台；
- Replay 的纯投影保留 Benchmark lifecycle 与 AgentGraph 两层因果序列，独立显示
  Agent status 与 Benchmark outcome，并通过真实 Android 摘录和 fake 完整证据验证
  图状态、截图、Inspector、双轨播放、锁定和失败跳转；当前完整后端回归为 415 项通过。
- Studio Stage 3 已建立 revision-bound 普通 Agent Run、SQLite lifecycle/event/artifact
  repositories、bounded single-worker scheduler、协作取消、Android execution adapter、
  durable event query/SSE、managed debug evidence 和 terminal native Replay；
- fake Android 已验证 success、failure、step limit、device failure、accepted/running
  cancel、device busy、evidence failure、service restart、SSE reconnect/heartbeat、
  opaque artifact 和 hidden Prompt 策略；相关 Studio、Graph/Runtime 与 clean-wheel
  合并回归为 153 项通过。当前没有新增真实 Android Stage 3 smoke，因此不据此声明真实
  设备通用能力。
- Studio Stage 4 已把 Builder `Run`/`Save & Run`、普通 task launch、可刷新 live route、
  HTTP backfill + named SSE、共享 Live/Replay evidence projection、只读 AgentGraph、
  Virtual Phone、Run Inspector、typed 模型响应 evidence、协作 Cancel 与 terminal
  Replay handoff 连接为前端闭环；
- Stage 4 focused backend 为 61 项通过，Studio/Runtime 合并回归为 157 项通过，
  clean-wheel/package boundary 为 15 项通过，前端 68 项通过且 typecheck、lint、build
  成功；真实浏览器 fake-device smoke 覆盖 Save & Run、刷新恢复、Cancel 和 cancelled
  Replay 交接。当前没有 Stage 4 真实 Android UI smoke，因此 fake 结果不作为真机证据。
- Studio 普通 Run readiness 已把 required component dependency 形式化到 ComponentSpec/
  Catalog，Builder 显式编辑 LLM provider/model/SecretRef，服务端从受信文件加载 SecretRef
  mapping 与安全 Device Profile，并在新 Run durable acceptance 前做 exact 静态检查；
  Worker 继续负责动态 binding、target、lease 和执行竞态。已知配置错误不再产生零步骤
  History，历史 revision 不重写，环境配置不改变 canonical identity。使用与迁移见
  [Studio Agent Run Readiness](studio-agent-run-readiness.md)。
- Studio 标准 Mobile Agent 能力模板在画布上只表达 Input、核心/批准能力、Output 与有界
  interaction；后端 lowering 的执行图仍显式包含 DeviceObserve、ActionRequest、runtime
  ActionExecutor、terminal predicate 和 feedback。Android Runtime 不再在 Kernel 前自动
  截图或补 observation。旧 schema-1/2 revision 保持可读但会在 ordinary Run/Benchmark
  policy gate 前无副作用阻断；Live/Replay 用 projection map 聚合 generated activation，并
  只从正式 DeviceObserve 事实投影设备帧。fake-device 已验证两次观察、中间一次 TAP 与
  terminal RunResult；没有新增真实 Android 证明。
  详见 [Studio Agent 显式反馈闭环](studio-agent-feedback-loop.md)。
- Studio Stage 5.1 已建立进程级 immutable Benchmark Catalog snapshot、安全
  list/detail/tasks/validate/device-profile HTTP、共享 Agent revision canonical
  verifier，以及复用正式 ExperimentProtocol 和 `build_schedule()` 的确定性 preview；
- React 已提供 `/benchmarks`、`/benchmarks/:benchmarkId` 和 `/experiments/new`，
  支持来源筛选、task/revision/profile/Protocol 选择、显式验证、preview fingerprint、
  ordered schedule 和语义修改后的 stale 状态。Stage 5.1 不创建或运行 Experiment，
  也没有新增真实 Android 证据。
- Studio Stage 5.2A 已建立 immutable Experiment snapshot、稳定 planned TaskRun、
  SQLite schema 4、幂等 create、accepted cancel 和 TaskRun 查询；Stage 5.2B 已升级
  schema 5，并接入本进程单 Worker、pure preflight、安全 profile/device lease、
  正式 `BenchmarkExperimentRuntime`、durable journal producer、cooperative cancel
  和 bounded TaskResult；
- 5.2B 第一条执行切片固定为一个 Agent、一个 Task、一个 repeat。fake-device、
  Studio、Benchmark、packaging 和 clean-wheel 验证已通过；完整后端验证为
  `531 passed`。这不证明真实 Android Stage 5 执行；
- Stage 5.2C-1 已实现 event query/SSE，5.2C-2 已实现 managed
  publication/native Replay，5.2C-3 已实现本地唯一 executable ownership 与保守
  startup recovery；`accepted`/side-effect-free `starting` 可回队，不确定的
  `running`/`cancelling` 只收口为 interrupted，`finalizing` 不重跑 Agent；
- Studio Stage 5.3 已让 Composer 显式创建 durable Experiment，并提供
  `/experiments/:experimentId` Monitor：strict Experiment/TaskRun/event DTO、
  HTTP backfill + named SSE、cursor/gap/reconnect/integrity handling、ordered
  TaskRun rail、accepted-only Cancel、truthful missing-evidence UI 和 terminal
  native Replay handoff。前端 107 项、相关后端合同 108 项通过，并完成 no-device
  真实浏览器验收；没有新增真实 Android 能力；
- Studio Stage 5.4A 已增加 newest-first checksummed keyset Experiment history、
  Experiment-bound metadata-only artifact inventory，以及 strict Core schema 1.0
  Experiment/TaskRun report 和 bounded Evaluation Tree 前端 entity。相关后端回归
  89 项、前端 121 项、typecheck/build 和 clean-wheel 无设备报告读取均通过；
- Studio Stage 5.4B 已实现可重建的单 Experiment Report、Studio/Core run identity
  bridge、TaskRun deep link、三条事实轴、Evaluation Tree、partial failure 和原生
  Replay handoff；
- Studio Stage 5.4C 已实现正式 schema-1.0 Experiment outcome、per-Agent
  micro/macro、duration、sample variance、Wilson、usage coverage、pairwise
  comparison、fairness warning 和 significance boundary 的纯前端投影。完整 Studio
  43 files/158 tests、focused backend reporting 15 tests、typecheck、lint、build
  与 no-device browser journey 通过；三 Agent 数据是 synthetic presentation
  fixture，不证明真实 multi-Agent Worker；
- Studio Stage 5.4D-1 已实现 strict immutable History filter、SQLite schema 7
  index-only migration、filter-bound checksummed cursor v2 和 URL-owned
  `/experiments`；5.4D-2 已实现 exact same-Experiment/same-TaskRun causal
  evidence 解析、strict scoped content capability、有界 stream、escaped
  JSON/NDJSON/XML/text、dimension-bounded PNG、download-only ZIP 和可销毁
  React-local Viewer；5.4D-3 已实现四类 managed content route 的共享 GET/HEAD
  resolver、安全 attachment/CORS headers、strict manifest 与 closed-inventory
  export projection、refresh + exact HEAD preparation、per-artifact
  single-flight，以及 browser-owned 大文件 handoff。完整 Studio 57 files/254
  tests、typecheck、lint、build、相关后端 129 项、no-device
  History→Report→Viewer→Replay→Export 浏览器 journey 和独立 clean-wheel
  验收通过。Stage 5.4 已完成；
- Studio Stage 5.5A 已实现 strict schema-1 Benchmark authoring document、
  SQLite schema 8 durable draft/current pointer、immutable revision、scoped
  command idempotency、server-owned content objects、private template scaffold、
  Catalog declared-closure copy-import、optimistic save、bounded HTTP resource
  和 restart reconstruction。完整 Studio `257 passed`、既有 Benchmark
  authoring/Catalog `19 passed`、focused `67 passed` 与 clean-wheel no-device
  create/import/save/restart 验收通过；runtime/device/plugin/model/secret/
  Experiment/report/Replay canary 调用数为零。该证据不包含 React editor、
  validation/dry-run、Contract Test、publication/migration 或真实 Android；
  原 5.5B editor 已永久拆为 definition editor、managed-content backend 和
  resource editor 三个顺序 Change；
- Studio Stage 5.5B-1 已实现独立 `/benchmark-authoring` 与 draft edit 路由、
  strict authoring entity/API、template/Catalog create、lossless structured
  manifest/split/Protocol/inline-ground-truth editing、显式 client-local task JSON
  buffer、draft-scoped baseline/working state、dirty/reset/reload、idempotent retry、
  optimistic conflict 和只读 resource inventory。focused `35 passed`、完整 Studio
  `288 passed`、typecheck、lint、build、相邻 authoring backend `37 passed` 与
  no-device Chromium journey 通过；该证据不包含 managed-content mutation、
  validation/dry-run、Contract Test、publication/migration、execution 或真实
  Android；
- Studio Stage 5.5B-2 已实现 strict owner-scoped upload/replace/logical-remove
  command、complete coherent document projection、64 MiB bounded raw streaming、
  server-derived digest/size、byte-bound idempotency、base-revision CAS、exact
  draft/revision/resource GET/HEAD、regular-file/size/digest integrity closure 和
  content-first failure safety。focused authoring `56 passed`、完整 Studio
  `281 passed`、Benchmark `94 passed`、前端 `67 files / 288 tests passed`、
  typecheck、lint、production build 与 clean-wheel content/restart journey 通过；
  全部 runtime/device/plugin/model/network/secret/Experiment/report/Replay/
  migration/export canary 为零。该证据不包含 React resource mutation、
  validation/dry-run、Contract Test、publication/migration、execution 或真实
  Android；content-first transaction 失败仍可能留下不可达 immutable object，
  当前没有 GC；
- Studio Stage 5.5B-3 已实现 URL-owned definition/resource modes、strict raw-body
  content command client、clean saved-baseline gate、asset/file-backed-ground-truth
  inventory、upload、replacement/missing repair、confirmed logical remove、selected-
  only exact HEAD、exact uncertain retry 与 historical-result current non-regression。
  focused `9 files / 57 tests`、完整 Studio `70 files / 309 tests`、typecheck、lint、
  独立临时目录 production build、相邻 authoring backend `64 passed` 与 no-device
  real-browser journey 通过。该证据不包含 validation/dry-run、Contract Test、
  publication/migration、execution、真实 Android、多文件续传、retention/GC 或
  object storage；
- Studio Stage 5.5C-1 已通过私有一次性 Package materialization，把 exact current
  immutable authoring revision 接到 strict revision-bound validation/dry-run HTTP，
  提供 partial Package/content/Plan/Protocol identities、字段级 diagnostics、immutable
  Agent revision verification、最多 10,000 条完整 deterministic schedule、budget、
  fairness、relative output layout 与 unverified facts，同时保持 schema 8 和零 runtime
  side effect。相关 focused/完整回归、clean-wheel、restart 与 HTTP canary 已通过；
- Studio Stage 5.5C-2 已实现 URL-owned React Validation mode、clean saved-baseline
  gate、1–16 个 frozen immutable Agent revisions、generation/owner-bound transient
  analysis、partial identities、diagnostic navigation、完整 schedule 的 50 条本地分页，
  以及 truthful budget/fairness/layout/unverified/no-execution presentation。完整 Studio
  `76 files / 350 tests`、typecheck、lint、build、相邻后端 `133 passed` 与 no-device
  real-browser journey 通过；该证据不包含 execution、Contract Test、publication/
  migration 或真实 Android；
- Studio Stage 5.5D 已实现 exact-current-revision fake-fixture Contract Tests、
  server-owned `studio-safe-v1` profile、initializer/environment/evaluator 三类
  occurrence、stable case-local seed、fresh-scope observable isolation、evaluator
  normalization、passed/failed/skipped coverage、独立 complete/executed-check facts、
  1,000-case/100-diagnostic bounds、strict no-store HTTP，以及 URL-owned React
  Contract Tests mode。完整 Studio `80 files / 367 tests`、广域后端 `697 passed`、
  clean-wheel `3 passed`、typecheck、lint、build 和 no-device real-browser journey
  通过；15 个 runtime/external business-boundary sentinel 均为 0。该证据不包含
  Package plugin execution、process sandbox、真实 device/model/network、Agent/
  Benchmark execution、validated status、publication/migration 或真实 Android；
- Studio Stage 5.5E-1 已实现 exact-current、all-declared-split definition-only
  revalidation、独立 immutable validation attestation、canonical definition bytes、
  verified managed binary closure、SQLite schema 9 atomic freeze durability、scoped
  idempotency、exact HTTP read 与 restart reconstruction。focused `12 passed`、完整
  HTTP `14 passed`、完整 Studio backend `344 passed`、Benchmark `113 passed`、
  contracts/graph/runtime `91 passed`、完整 Studio frontend `80 files / 367 tests`、
  typecheck、lint、build 与 clean-wheel `4 passed`；原 authoring revision/current/
  fingerprint/`unvalidated` status 不变，且
  runtime/publication evidence 始终为 false。该证据不包含 Package plugin、Agent/
  Benchmark execution、Catalog publish、export、migration 或真实 Android。
  原 5.5E 已进一步拆为 validated freeze、publication/export 与 legacy migration
  三个顺序 Change；
- Studio Stage 5.5E-2 已实现 frozen Package revision page、SQLite schema 10
  publication/export authority、共享 frozen-closure revalidation、database-sibling
  managed Package/ZIP storage、copy-on-write immutable Catalog snapshot、semantic
  version/content conflict、deterministic ZIP v1、exact scoped metadata/GET/HEAD，以及
  URL-owned React Release mode。完整后端 `765 passed`、Studio+packaging `381 passed`、
  focused release `10 passed`、完整前端 `84 files / 376 tests`、typecheck、lint、
  production build、repository-independent clean-wheel acceptance 与 no-device
  real-browser Freeze→Publish→Catalog→Export→HEAD/download journey 通过；runtime、
  device、model、network、secret、Agent/Benchmark、Experiment、report/Replay 与
  Android canary 均为 0。该证据只证明 immutable closure publication/export 和
  archive integrity，不证明 execution、Contract Test、真实 Android、object storage、
  multi-process publication coordination、retention/delete 或 legacy migration。
  该条 legacy migration 是 E-2 当时的交付边界；后续 E-3 已独立实现。完整边界见
  [Studio Benchmark Package Publication / Export](studio-benchmark-package-publication-export.md)。
- Studio Stage 5.5E-3 已实现 legacy standalone BenchmarkTask V1 JSON 的 1 MiB/
  100-task bounded browser source-text Preview、结构化守恒 diff、duplicate/pre-V1/
  unsafe source fail-closed、exact source/target/contract/document authority、完整重算
  Confirm、schema-10 atomic idempotent unvalidated draft、`legacy_migration`
  provenance 与 disposable React session。AppAgent 45/45 可确认；AndroidWorld legacy
  source 的 82/81 与第二个 `AndroidWorld_72`/source[72] 明确阻止 Confirm；完整后端
  `794 passed`、完整前端 `88 files / 390 tests`、clean-wheel 与 no-device real-browser
  journey 通过，所有 runtime/release products 保持为 0。该证据不包含 Package
  validation、Contract Test、freeze、publication/export、Agent/Benchmark execution、
  model/device 或真实 Android。Stage 5.5 已完成。原单一 Stage 5.6 已永久拆为
  5.6A explicit Android profile/provenance、5.6B layered no-device acceptance、
  5.6C-1 real Android service acceptance 与 5.6C-2 real Android browser acceptance；
  该条 legacy migration 是 Stage 5.5 的最终交付边界。完整边界见
  [Studio Benchmark Legacy Migration](studio-benchmark-legacy-migration.md)。
- Studio Stage 5.6A 已实现 strict trusted JSON profile、无配置空目录、SQLite schema
  11 atomic private Experiment binding、exact-target authority、Run/Benchmark 共用的
  process-local target lease，以及 acquisition/environment 两轴 TaskResult/Replay
  evidence origin。包含 clean-wheel profile acceptance 的完整后端 `828 passed`，该
  用例独立 `1 passed`，5.6A focused backend `149 passed`，完整前端
  `88 files / 391 tests`
  并通过 typecheck/lint；全部是 no-device/fake/contract evidence，没有新增真实 Android
  claim。raw serial、配置路径、private fingerprint、target key 和 live device 不进入
  公开 DTO、event、report、trajectory、Replay 或 bundle。完整合同、配置和回滚边界见
  [Studio Benchmark Android Profile 与证据来源](studio-benchmark-android-profile.md)。
- Studio Stage 5.6B 已实现 14 场景的有界 deterministic proof ledger，并通过
  production Studio fake composition 连接 create、SQLite、Worker、Core Runtime、
  event/SSE、recovery、managed publication、Report/Evidence、native Replay 与
  Export。Core `2 Agents × 2 Tasks × 2 repeats` 的完整 8-run fairness matrix 与
  Studio `1×1×1` 超限整体拒绝分别验证；clean wheel 从独立安装的 Benchmark
  distribution 完成 durable fake Experiment，ADB/真实设备/外部网络/model/secret/
  repository-source fallback 六个 canary 均为 0。actual-backend 真浏览器完成
  Catalog → Composer → Monitor → Report/Evidence → Replay → Export，刷新后重建同一
  Experiment/TaskRun；静态 fixture 只作为 failure-state presentation 的支持证据。
  focused `28 passed`、external-Package clean-wheel `1 passed`、完整后端
  `857 passed`、完整前端 `88 files / 392 tests`，并通过 typecheck、lint 和 build。
  所有该阶段执行均为 `contract_fixture/fake_device` 且
  `realDeviceEvidence=false`；其后的 5.6C-1/2 已独立完成真实 Android 验收。完整证明链、命令、取舍和限制见
  [Studio Benchmark 分层无设备验收](studio-benchmark-layered-acceptance.md)。
- Studio Stage 5.6C-1 已在一个明确 Android 虚拟设备、`en-US` portrait、
  `zhixing/android-world@1.0.0` / `AndroidWorld_6`、seed 42、两个 immutable Agent
  revisions、单 repeat 上完成真实 service 正例与受控失败例。正例为 Agent success、
  Benchmark/evaluator pass、独立图片增量 1；负例为 Agent success、Benchmark/evaluator
  fail、`INVALID=0`、图片增量 0。managed closure、native Replay、exact GET/HEAD、
  terminal restart non-replay 与私有 authority 零泄漏均通过。完整边界见
  [Studio Benchmark 真实 Android 服务验收](studio-benchmark-android-service.md)。
- Studio Stage 5.6C-2 已用实际浏览器创建两条新 Experiment 并闭合 Catalog → Composer
  → Monitor → Report/Evidence → Replay → Export。两条 event stream 均连续到 19/19，
  refresh/reconnect 未重复 source/device effect；fresh source、historical real-source
  Replay 与 fake fixture provenance 保持三分，Export 只声明 HEAD 后 browser handoff。
  C-2 ledger 扫描 236 项、私有 authority 为 0；完整前端 `89 files / 399 tests`、完整
  后端 `921 passed`，并通过 typecheck、lint 与 production build。Stage 5.6 与 Stage 5
  已完成；Stage 5 内没有新的 current-next change。完整边界见
  [Studio Benchmark 真实 Android 浏览器验收](studio-benchmark-android-view.md)。

上述结果只覆盖已记录的 emulator、locale/orientation、相机任务、示例外部分发包
和小样本比较，不构成通用模型能力、统计显著性或全量 Benchmark 通过率声明。

## 兼容与迁移边界

新版不会因为 Graph Runtime 已可用就立即删除旧路径：

- 旧 AgentConfig YAML、`ModularAgent` 和 `AgentRunner` 仍是兼容入口；
- 旧 BenchmarkTask JSON 与 Pipeline 仍需保持可用；
- 只有新路径取得明确行为等价证据后，旧实现才能逐步收敛；
- public imports、配置合同、canonical identity 和插件 identifier 不应被静默修改。

## 当前不属于已完成能力

- Studio 运行暂停/checkpoint、节点重试、实时视频和真实设备控制体验仍未实现；
- Replay 不提供自动失败诊断、节点重试或
  PostgreSQL adapter；
- 插件 marketplace、框架自动下载 Git 仓库或自动安装依赖；
- 第三方插件的进程沙箱、签名校验和权限隔离；
- 任意 Agent 范式、任意第三方插件或全部 Android/Harmony 设备的兼容保证；
- AndroidWorld/AppAgent 全量真实设备通过率；
- 多设备并行调度、通用统计结论或自动失败诊断。

## 代码与内容边界

```text
zhixing/components/       公共组件合同与测试工具
zhixing/graph/            AgentGraph 模型、验证与编译
zhixing/runtime/          通用 AgentGraph Runtime
zhixing/devices/          Android/Harmony 设备操作边界
zhixing/catalog/          外部组件发现、Catalog 与解析
zhixing/benchmark/        Benchmark 定义、编译、运行、评估与报告
zhixing/plugins/          内置 Agent/Benchmark/LLM 原子插件
benchmarks/               可直接使用的正式 Benchmark Package
examples/                 Agent、外部组件和外部 Benchmark 示例
tests/                    合同、Runtime、兼容、Packaging 与验收测试
docs/                     长期架构、使用说明和工程记录
temp/benchmark-runs/      可删除运行产物，不是定义输入
studio/                   React Builder、Live Run、History/Replay、Benchmark
                           Catalog/Composer 与 durable Experiment Monitor
```

## 进一步阅读

- [AgentGraph 语义与编译](agent-graph.md)
- [通用 Graph Runtime 验收](generalized-agent-graph-acceptance.md)
- [Android Graph Runtime](android-graph-runtime.md)
- [内置 AgentGraph 真实闭环](builtin-agentgraph-runtime.md)
- [外部组件开发与发现](external-components.md)
- [外部插件完整验收](external-plugin-acceptance.md)
- [Benchmark 架构](benchmark-architecture.md)
- [Benchmark 开发](benchmark-authoring.md)
- [Benchmark 运行与比较](benchmark-running.md)
- [Studio Benchmark Authoring Resource](studio-benchmark-authoring-resource.md)
- [Studio Benchmark Definition Editor](studio-benchmark-definition-editor.md)
- [真实 Android Benchmark 复验](benchmark-android-acceptance.md)
- [后端路线图](roadmap.md)
- [Studio AgentGraph 1.1 Builder](studio-agentgraph-builder.md)
- [Studio Trajectory Replay](studio-trajectory-replay.md)
- [Studio Run Service](studio-run-service.md)
- [Studio Live Run Workbench](studio-live-run-workbench.md)
- [Studio Stage 5 Benchmark Experiment 路线](studio-benchmark-experiment-roadmap.md)
- [Studio Benchmark Experiment 合同](studio-benchmark-experiment-contracts.md)
- [Studio Benchmark Catalog 与 Composer](studio-benchmark-catalog-composer.md)
- [Studio Benchmark Experiment Monitor](studio-benchmark-monitor.md)
- [Studio Stage 5.4 Benchmark Reporting 路线](studio-benchmark-reporting-roadmap.md)
- [Studio Benchmark Reporting Resource](studio-benchmark-reporting-resource.md)
- [Studio Benchmark Report View](studio-benchmark-report-view.md)
- [Studio Benchmark Comparison and Metrics](studio-benchmark-comparison-metrics.md)
- [Studio Benchmark Experiment History](studio-benchmark-history.md)
- [Studio Benchmark Evidence Viewer](studio-benchmark-evidence-viewer.md)
- [Studio Benchmark Export](studio-benchmark-export.md)
- [Studio Benchmark 真实 Android 服务验收](studio-benchmark-android-service.md)
- [Studio Benchmark 真实 Android 浏览器验收](studio-benchmark-android-view.md)
