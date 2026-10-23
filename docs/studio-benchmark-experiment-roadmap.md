# Studio Stage 5：Benchmark Experiment 产品路线

本文固化 ZhiXing Studio Stage 5 的已对齐目标、产品形态、后端边界、分步实施
顺序与默认决策。Stage 5.1 已于 2026-07-27 实现 definition/composer 纵向切片，
Stage 5.2A 已于同日实现不执行设备副作用的持久 Experiment resource，Stage 5.2B
随后实现第一条单 Worker/fake-device 可执行后端切片。2026-07-28 将原 5.2C 进一步
拆为 5.2C-1 event stream、5.2C-2 publication/Replay 和 5.2C-3 startup recovery；
其中 5.2C-1、5.2C-2、5.2C-3、5.3、5.4A、5.4B、5.4C 与 5.4D-1/2/3 已
实现并验证；Stage 5.4 已完成，5.5A authoring resource、5.5B-1/2/3、5.5C-1/2
validation/dry-run resource/view、5.5D Contract Tests 与 5.5E-1 validated freeze、
5.5E-2 publication/export 与 5.5E-3 legacy migration 也已实现并验证。原 5.5E
永久拆为 5.5E-1 validated freeze、5.5E-2 publication/export 与 5.5E-3 legacy
migration；Stage 5.5 已完成。原单一 5.6 已永久拆为 5.6A explicit Android
profile/provenance、5.6B layered no-device acceptance、5.6C-1 real Android
service acceptance 与 5.6C-2 real Android browser acceptance；四项均已实现并验证。
5.6C-1 以真实 Android 正例/受控失败例闭合 durable service、managed publication、
Replay 与 terminal restart non-replay，5.6C-2 又以实际浏览器闭合 Catalog → Composer →
Monitor → Report/Evidence → Replay → Export、SSE/refresh 与 provenance 呈现。Stage 5
至此完成；Stage 5 内没有尚未执行的“current next”，后续范围必须另建 OpenSpec Change。

具体 requirement、API 字段、状态转换、任务和验收场景必须写入对应 OpenSpec
Change；每个 Change 只有在代码、自动化测试和相应运行证据完成后，才能被描述为
已实现。

## 一句话目标

将已经验证的 Benchmark Build–Run–Evaluate 后端，产品化为一个**持久、可恢复、
可监控、可评估、可比较的 Mobile Agent 研究实验工作台**。

Stage 5 不是在普通 Agent Run 结束后附加一个分数，也不是重新实现一套 Benchmark
Runtime。它要让 Mobile Agent 研究人员在 Studio 中完成以下闭环：

```text
选择 Benchmark 和 Task
        ↓
选择 Agent 的不可变 revision
        ↓
配置并预览 ExperimentProtocol / schedule
        ↓
创建可持久化 Experiment
        ↓
监控 TaskRun 生命周期与运行证据
        ↓
进入单次任务 Replay
        ↓
查看 Evaluation Tree、统计、比较与导出 bundle
```

完成 Stage 5 后，研究者应能在同一产品中复用已有 Benchmark Package、运行一个或
多个 Agent、观察实验进度、刷新后恢复现场、审阅每次任务证据，并导出可复核的实验
结果。BenchmarkPlan、ExperimentProtocol 和 AgentGraph 继续保持独立身份。

## 当前后端基础

截至 2026-07-26，Stage 5 的后端基础不是空白。仓库已经实现并测试：

- 旧 `BenchmarkTask` JSON 和新版 Benchmark Package 均可无设备副作用地编译为
  `BenchmarkPlan`；
- Package、Plan、TaskInstance 与 ExperimentProtocol 具有独立 canonical identity；
- metadata-only Catalog 可从显式本地目录和已安装 distribution 发现、查看和校验
  Benchmark，且这些操作不连接设备或执行任务；
- AndroidWorld Package 当前包含 81 个唯一任务，AppAgent Package 包含 45 个任务；
- ExperimentProtocol 可描述 seed、repeats、顺序、预算、设备/应用约束、隔离和
  failure policy；
- `BenchmarkExperimentRuntime` 可在共享设备会话中运行一个或多个 Agent、多个
  Task 和 repeats，并保留物化、reset、setup、Agent、evaluation、cleanup 生命周期；
- Agent `RunStatus` 与 Benchmark `PASS/FAIL/INVALID/SKIPPED` 分离；
- Evaluation Tree 支持 AND、OR、SEQUENCE、THRESHOLD 和 WEIGHTED，并保留叶子
  evaluator 证据；
- 报告支持 task/experiment 结果、micro/macro 指标、Wilson interval、paired
  comparison、公平性提示和可校验 bundle；
- CLI 已提供 `benchmark list`、`info`、`validate`、`run`、`init`、`dry-run`、
  `contract-test`、`report` 和 `trajectory`；
- `tests/benchmark` 在本轮 Stage 5 调研中得到 `90 passed` 的 fake/contract
  回归结果。

真实 Android 的已有证据、环境限制和声明边界继续以
[Benchmark 长期架构原则](benchmark-architecture.md)与
[真实 Android Benchmark 复验](benchmark-android-acceptance.md)为准。已有代表性
证据不等于全部 AndroidWorld/AppAgent 任务、任意 Agent、任意设备或统计显著性已经
得到验证。

## Stage 5.5 后的当前缺口

当前 React Studio 已用 `/benchmarks`、detail、`/experiments/new` 与
`/experiments/:experimentId` 替换
`/benchmark` 占位入口；Catalog/preview 使用严格 DTO 与 feature-local Composer
state，旧 `pipeline: unknown[]` 不再是活动领域事实。实现与验证边界见
[Studio Benchmark Catalog 与 Composer](studio-benchmark-catalog-composer.md)。

Stage 5.2A/5.2B 已提供 SQLite Experiment/TaskRun repository、稳定 identity、
immutable snapshot、幂等 create/cancel、runtime journal producer、单 Worker、
execution-boundary safe profile/device lease、bounded result 和查询 HTTP；5.2C-1
已经开放连续 event page 与 named SSE；5.2C-2 已将正式报告、轨迹、bundle、受管
artifact 与 native Replay 纳入 schema 6 的持久边界；5.2C-3 已增加可执行
composition 独占 ownership 与保守 startup recovery。5.3 已接通 durable create、
strict Benchmark DTO、HTTP backfill + named SSE、ordered TaskRun Monitor、
accepted-only Cancel 与 terminal native Replay handoff。实现与验证边界见
[Studio Benchmark Experiment Monitor](studio-benchmark-monitor.md)。当前缺口是：

- Stage 5.4 的 Report、History、统计比较、Evidence Viewer 与 Export 已完成；
- 第一条 Worker 切片仍限制为一个 Agent、一个 Task、一个 repeat；
- 5.5A 已提供持久 draft、immutable revision、server-owned managed content 和
  安全 scaffold/Catalog import；
- 5.5B-1 已提供 React definition editor、template/Catalog create、lossless
  structured editing、显式 task JSON buffer、dirty/reset/reload/conflict 和只读
  resource inventory；
- 5.5B-2 已提供 owner-scoped managed-content upload/replace/logical-remove、
  bounded raw streaming、byte-bound idempotency、revision CAS 和 exact historical
  read；
- 5.5B-3 已提供 URL-owned definition/resource modes、clean-baseline gate、React
  inventory/upload/replacement/missing repair/confirmed logical removal、selected-
  only exact HEAD、uncertain retry 和 historical-result current non-regression；
- 5.5C-1 已提供 revision-bound validation/dry-run resource，5.5C-2 已提供 URL-owned
  React Validation mode、clean gate、frozen Agent revisions、stale-result discard、
  diagnostic navigation 和完整有界 schedule 展示；5.5D 已提供 exact-revision、
  coverage-aware fake-fixture Contract Tests 和 URL-owned React mode；5.5E-1 已提供
  validated immutable freeze，5.5E-2 已提供 managed Catalog publication 与
  deterministic Package export；5.5E-3 已提供 bounded legacy JSON Preview、
  structured diff 与 exact Confirm。Stage 5.5 已完成；5.6A 已提供 strict trusted
  profile、schema-11 private binding、exact-target authority、跨 Run/Benchmark target
  lease 和两轴 evidence origin。5.6B 已以 14 场景有界 proof ledger、production
  fake Studio chain、Core `2×2×2`/Studio `1×1×1` 分离边界、actual-backend 浏览器
  和 installed external Package 完成分层无设备验收。5.6C-1/C-2 已分别闭合真实
  Android Studio service 与实际浏览器证据链；当前缺口不再是 Stage 5 内的待实现项，
  而是由后续独立 Change 决定是否扩展 Worker cardinality、扩大真机矩阵或准备论文演示。

因此，Stage 5 的主要复杂度不是画几个页面，而是给成熟的运行内核增加一层可靠的
Studio 产品服务，并保持已有 Benchmark 语义、公平性和证据链不变。

## 产品形态与路由

Stage 5 在视觉上属于同一个 Benchmark“试验场”，逻辑上使用独立路由：

- `/benchmarks`：Catalog、搜索、筛选和 Package 概览；
- `/benchmarks/:benchmarkId`：任务、资源、默认 Protocol 和校验信息；
- `/experiments/new`：选择 Agent revision、Task、Protocol 并预览 schedule；
- `/experiments/:experimentId`：实验状态、TaskRun 队列、实时阶段和部分结果；
- `/experiments/:experimentId/report`：最终结果、Evaluation Tree、比较、警告和导出。

普通 Agent Run 与 Benchmark Experiment 是两个独立产品资源：

```text
普通任务
Agent revision → StudioRun → Live Workbench → Replay

Benchmark 实验
Agent revision(s) + BenchmarkPlan + ExperimentProtocol
                         ↓
                    Experiment
                         ↓
              TaskRun(s) → Replay(s)
                         ↓
             Evaluation / Report / Bundle
```

二者可以复用 Graph、Virtual Phone、Inspector、event projection、artifact 和 Replay
组件，但不得把 Experiment 压缩成普通 Run 的几个可选字段。

## 目标服务边界

Stage 5 的目标结构为：

```text
Studio React
    │
    ├── Benchmark metadata HTTP
    ├── Experiment command/query HTTP
    ├── durable event query + SSE
    └── managed report/artifact access
    │
StudioBenchmarkExperimentService
    ├── SQLite Experiment Repository
    ├── durable Experiment Event Journal
    ├── Scheduler / Cancel / Startup Recovery
    ├── immutable Agent revision binding
    ├── TaskRun → native Replay registration
    └── managed Report / Trajectory / Bundle
    │
现有 Benchmark Core
    ├── Catalog / Compiler
    ├── BenchmarkPlan / ExperimentProtocol
    ├── BenchmarkExperimentRuntime
    ├── Evaluation Tree
    └── Reporting / Trajectory
```

Studio 服务层负责持久化、并发命令、恢复、投影和安全访问；现有 Benchmark Core
继续负责定义、物化、运行、评估和报告语义。Stage 5 不应在 Graph Runtime kernel
加入 Benchmark 特判，也不应复制 Evaluation 或统计实现。

SQLite 是第一版持久化实现，但 service/repository 边界必须允许未来增加 PostgreSQL
adapter。领域合同、HTTP DTO、Experiment identity 和事件语义不得依赖 SQLite 特性。

## 分步实施

Stage 5 拆分为 5.0–5.6，避免用一个超大 Change 同时修改领域合同、持久化、执行、
实时 UI、统计展示和 authoring。

### 5.0 `define-studio-benchmark-experiment-contracts-5-0`

只定义合同和设计，不修改应用代码。

需要确定：

- Benchmark Catalog、Benchmark detail 和 Task metadata DTO；
- Experiment、TaskRun、Evaluation、Report 与 artifact resource；
- Experiment/TaskRun 状态机、终止状态和部分结果语义；
- Agent revision、BenchmarkPlan、ExperimentProtocol 与 schedule snapshot 的绑定；
- create/get/cancel、event query/SSE、report/artifact 和 Replay 关系；
- durable event envelope、cursor、幂等、重连和 startup recovery；
- cancel 在 queued、running、evaluation、cleanup 和 terminal 阶段的行为；
- SQLite repository port 与未来 PostgreSQL adapter 的边界；
- secret、device profile、模型响应、Prompt、宿主路径和 artifact 的安全策略；
- fake、浏览器、重启恢复和真实 Android 的分层验收矩阵。

完成形式：OpenSpec proposal、design、requirements 和 tasks 达到 apply-ready，并成为
5.1–5.6 的共同合同来源。5.0 本身不以页面或 API 可运行作为完成标准。

### 5.1 `implement-studio-benchmark-catalog-composer-5-1`

建立无设备副作用的 Catalog 与 Experiment Composer 纵向切片：

- Benchmark list/detail/task/validate HTTP API；
- Agent immutable revision 选择；
- Task、split、repeats、seed、order、budget 和安全 device profile 配置；
- 确定性 schedule preview 与创建前诊断；
- 替换 `/benchmark` 占位页，建立 `/benchmarks` 和 `/experiments/new`。

完成后，用户可以在 Studio 中发现 Benchmark、查看任务、选择一个 Agent revision、
配置第一版 Protocol 并预览将要运行的任务，但还不执行真实 Experiment。该目标已于
2026-07-27 实现；验证事实见
[Stage 5.1 实现文档](studio-benchmark-catalog-composer.md)。

### 5.2 Experiment Service（拆分为 5.2A–5.2C-3）

5.2 的产品目标仍是建立可靠的 Experiment 执行服务。原计划把 repository、执行
worker、journal/SSE、recovery、artifact 和 Replay 放在一个 Change 中；2026-07-27
先拆为 5.2A resource、5.2B worker、5.2C durability。2026-07-28 再将仍然过大的
5.2C 按依赖拆为三个可独立验收的 Change。该拆分不改变 5.0 已确定的
Experiment/TaskRun、状态机、事件、安全或结果合同。

#### 5.2A `implement-studio-benchmark-experiment-resource-5-2a`

建立不执行设备副作用的持久资源基础：

- versioned Experiment、TaskRun、definition snapshot 和 journal DTO/typed ports；
- SQLite repository schema、transaction/CAS 与未来 PostgreSQL adapter 合同；
- immutable definition snapshot、稳定 planned TaskRun identity 和幂等 create；
- create 时重新编译并复核 preview fingerprint，拒绝 definition drift；
- create/get/cancel-request/TaskRun query HTTP，原子提交 initial event；
- accepted Experiment 在浏览器关闭或服务重启后仍可查询；
- 第一版永久保存，不提供 delete、retention、quota 或自动清理。

完成标准是 `preview → create → experimentId → restart → GET` 保持同一 snapshot、
TaskRuns 和 cursor；相同 request identity/content 返回同一 Experiment，冲突内容被
拒绝；整个 Change 使用 no-device spies 证明没有 profile resolve 或设备连接。

该目标已于 2026-07-27 实现并通过事务故障注入、并发 create/cancel、HTTP 重启、
完整后端回归和 clean-wheel 安装验证；已验证实现、复验命令与 5.2B 边界见
[Studio Benchmark Experiment Resource](studio-benchmark-experiment-resource.md)。
这里的 `accepted` 只表示持久资源已提交，不表示 worker 已启动或 Benchmark 正在运行。

#### 5.2B `implement-studio-benchmark-execution-worker-5-2b`

让已持久的 Experiment 执行第一条后端纵向切片：

- bounded single-worker scheduler 和 execution preflight；
- 只在 execution boundary 解析安全 device profile；
- 复用现有 `BenchmarkExperimentRuntime`，不复制 Benchmark lifecycle；
- Experiment/TaskRun lifecycle、Benchmark phases、Agent status 与 Benchmark outcome；
- event append、result/availability 持久化和事务化终态竞争；
- cooperative cancel 以及 evaluation/cleanup 已产生事实的保留；
- fake-device success、FAIL、INVALID、cancel、device/evidence failure 验收。

第一条执行切片固定为：**一个 Agent、一个 Benchmark、一个 Task、一个 repeat**。
DTO 继续使用复数结构；超限整体拒绝。真实 Android 仍放在 5.6。

该目标已实现：本进程新提交的 accepted Experiment 可由 durable single worker
串行 claim；pure preflight 先验证 snapshot、Package/resource、AgentGraph 和 component
availability，再进入私有 evidence、safe profile、device lease 和正式
`BenchmarkExperimentRuntime`；planned/Core identity、runtime journal、三条结果轴、
bounded TaskResult、cooperative cancellation 和 schema 5 事务均已接通。验证事实、
复验命令和未实现的 5.2C-1/2/3 边界见
[Studio Benchmark Execution Worker](studio-benchmark-execution-worker.md)。

#### 5.2C-1 `implement-studio-benchmark-event-stream-5-2c1`

把 5.2B 已经生产的 durable journal 开放为可靠的客户端事件传输：

- Experiment-scoped event page、opaque cursor 和有界连续 backfill；
- named SSE、`Last-Event-ID` 恢复、heartbeat 和唯一 terminal 收口；
- append-before-notify，SSE 只传输已提交的 journal facts；
- 每连接有界状态和慢客户端隔离，不反压 Benchmark Runtime；
- 打开真实 event/eventStream capability 与 links，并保持 payload 安全上限。

完成标准是：客户端先 GET backfill、再连接 SSE，刷新或断线后能从同一 high-water
mark 连续恢复，terminal 后不会缺失或重复事件。该 Change 不做 startup recovery、
managed artifact、Replay 或 React Monitor。

该目标已实现：`StudioBenchmarkEventPageV1`、连续性与 high-water integrity query、
commit-after-notify waiter、named SSE、`Last-Event-ID`、id-less heartbeat、
terminal drain、连接 cap、socket write timeout、truthful capability/links 和安全
canary 均已有自动化证据。具体合同、复验命令、观察到的普通 Run 时序 flake 和剩余
边界见 [Studio Benchmark Event Stream](studio-benchmark-event-stream.md)。

#### 5.2C-2 `implement-studio-benchmark-publication-replay-5-2c2`

把 5.2B 延后的 Benchmark 正式证据纳入 Studio 管理边界：

- 幂等发布正式 task/experiment report、trajectory、manifest 和 bundle；
- Experiment/TaskRun-scoped managed artifact metadata、hash、size、content type、
  availability 和安全 resolver；
- 拒绝 path traversal、absolute path、symlink escape、跨 Experiment 引用和
  integrity mismatch；
- terminal TaskRun 原子注册为 native Replay；
- Replay 保留 Agent status、Benchmark outcome、失败/中断前缀和安全 artifact identity；
- Prompt、完整模型响应、secret、raw serial 与导出使用统一 capture/export 策略。

完成标准是：terminal TaskRun 可沿 typed links 查询正式 publication、下载允许的
artifact/bundle 并打开 native Replay；失败只改变对应 availability，不覆盖已提交
result。该 Change 不实现 5.4 的报告统计界面。

该目标已实现：完整 Core `BenchmarkSuiteResult` 在 bounded Studio 投影之外保留给
正式 writer；schema 6 持久化独立 publication component availability、受管 artifact
metadata 与显式 Replay 映射；report、trajectory、manifest、Studio experiment bundle
和允许的 runtime evidence 使用稳定 opaque identity 发布；resolver 在读取时复核
scope、size 与 SHA-256，并把 missing/corrupt 状态级联关闭到 TaskRun、Experiment 和
Replay。terminal TaskRun 被投影为 provenance 为 `native_benchmark_task_run` 的显式
Replay，同时保留 Agent status、Benchmark outcome、journal 前缀和同一 artifact
identity。具体实现、测试与限制见
[Studio Benchmark Publication 与 Replay](studio-benchmark-publication-replay.md)。

#### 5.2C-3 `implement-studio-benchmark-startup-recovery-5-2c3`

在 event transport 与 publication 已稳定后补齐服务重启恢复：

- 可证明尚无执行副作用的 accepted Experiment 安全重新入队；
- 无法证明设备动作边界的 in-flight Experiment 收口为 interrupted，不静默重跑；
- TaskResult 已落盘的 finalizing Experiment 只按 identity 幂等重试 publication，
  不重新运行 Agent；
- terminal Experiment 保持 immutable；
- 每次 recovery decision 写入 durable journal，重复启动不重复执行、发布或产生
  第二个 terminal event。

完成标准是：构造 accepted、running、finalizing、terminal 四类重启 fixture，分别
观察到 requeue、interrupted、publication-only retry 和 immutable，并证明没有未知
设备副作用被重放。

该目标已实现：schema 6 无需升级；typed recovery candidate/decision/summary、
SQLite owner/lifecycle CAS、恢复事件、OS 自动释放的本地 workspace 独占锁和
pre-scheduler startup barrier 已接通。`accepted` 与 side-effect-free `starting`
保持原 identity/snapshot/schedule 后回队；`running`/`cancelling` 只以
`interrupted` 收口；`finalizing` 只调用既有幂等 publisher 或直接 finalize；
terminal/current-owner 保持 no-op。事务 rollback、旧 worker 迟到写、SSE backfill、
publication/Replay 崩溃窗口和 clean-wheel 安装均有自动化证据。具体实现、复验命令
与限制见
[Studio Benchmark Startup Recovery](studio-benchmark-startup-recovery.md)。

5.2A、5.2B 与 5.2C-1/2/3 都属于同一个 Stage 5.2 service 合同，不新增竞争性的
状态机或 DTO。Stage 5.2 durability 已完成；Stage 5.3 只消费这些后端事实并已
实现；Stage 5.4A reporting resource、5.4B single-Experiment Report View 与
5.4C comparison/metrics、5.4D-1 filtered History、5.4D-2 Evidence Viewer 与
5.4D-3 Export 也已完成。原 5.4D history/evidence/export 已永久拆为 5.4D-1
History、5.4D-2 Evidence Viewer 与 5.4D-3 Export，并已按顺序完成。随后
进入 Stage 5.5，并已完成 5.5A authoring resource 与 5.5B-1/2/3；
原 5.5B Package Editor 已
永久细分为 5.5B-1 definition editor、5.5B-2 managed content backend 和
5.5B-3 resource editor；5.5C-1 validation/dry-run resource 与 5.5C-2
validation/dry-run view、5.5D Contract Tests 与 5.5E-1 validated freeze、5.5E-2
publication/export 也已完成；
原 5.5E 已永久细分为 5.5E-1 validated freeze、5.5E-2 publication/export 与
5.5E-3 legacy migration 也已完成；5.6A
`implement-studio-benchmark-android-profile-5-6a` 与 5.6B
`validate-studio-benchmark-layered-acceptance-5-6b` 均已完成；5.6C-1
`validate-studio-benchmark-android-service-5-6c1` 与 5.6C-2
`validate-studio-benchmark-android-view-5-6c2` 也已完成，Stage 5 已闭合。Core Runtime 已有多 Task、
repeats 和多 Agent fake/历史真机证据，但 Studio Worker 仍只验证
1 Agent × 1 Task × 1 repeat；5.6 验收不得把两者合并为同一支持声明。

### 5.3 `implement-studio-benchmark-monitor-5-3`

实现 `/experiments/:experimentId`：

- Experiment 总状态、TaskRun 队列、当前 lifecycle stage 和阶段耗时；
- HTTP backfill + named SSE，刷新和断线后恢复；
- running/terminal TaskRun 选择、Cancel 和安全错误展示；
- 复用 Stage 2–4 的只读 Graph、Virtual Phone、Inspector 和 Replay；
- terminal TaskRun 必须能够进入 Replay。

第一版不要求每个正在执行的 TaskRun 都拥有完整独立 Live Workbench；可以先提供
Experiment 级监控和 terminal Replay，再按证据需要扩展 child live route。

该目标已实现：Composer 以 stable create intent 提交 exact preview definition；
`/experiments/:experimentId` 从 authoritative Experiment/TaskRun resource 重建，
按 fixed high-water 完成 HTTP backfill 后从 explicit cursor 连接 named SSE，并对
duplicate、gap、disconnect、terminal drain 和 integrity conflict 做确定性处理。
TaskRun rail 支持历史选择 lock/return-to-current；Graph 保持 immutable，截图、
UI XML 与 node activation 缺失时明确 `not_captured`；Cancel 只在 accepted 状态
显式确认，Replay 只从 terminal TaskRun resource 显式进入。前端 107 项、相关
Stage 5.2 后端合同 108 项通过，并完成无设备真实浏览器状态验收；这不构成真实
Android 证据。详情见
[Studio Benchmark Experiment Monitor](studio-benchmark-monitor.md)。

### 5.4 `implement-studio-benchmark-reporting-5-4`

该阶段先按产品责任分为 5.4A、5.4B、5.4C 与 5.4D；经过 5.4D 前置调研后，
history query/cursor、evidence content security 与 binary export 被确认属于三个
独立风险域。因此实际永久实施顺序为六个 Change：

1. 5.4A `implement-studio-benchmark-reporting-resource-5-4a`：strict report/history/
   artifact inventory DTO 与缺失的公共 resource（已实现）；
2. 5.4B `implement-studio-benchmark-report-view-5-4b`：单 Experiment report、
   TaskRun result 和 Evaluation Tree（已实现）；
3. 5.4C `implement-studio-benchmark-comparison-metrics-5-4c`：micro/macro、
   Wilson、paired comparison 和 fairness（已实现）；
4. 5.4D-1 `implement-studio-benchmark-history-5-4d1`：全量 Experiment history、
   后端精确筛选、filter-bound keyset cursor 与 Monitor/Report handoff
   （已实现）；
5. 5.4D-2 `implement-studio-benchmark-evidence-viewer-5-4d2`：scoped artifact
   inventory、causal evidence 解析与有界安全 Viewer（已实现）；
6. 5.4D-3 `implement-studio-benchmark-export-5-4d3`：独立
   report/trajectory/bundle 下载、single-flight、manifest/excluded-evidence 与
   no-device 浏览器闭环（已实现）。

总体实现 `/experiments/:experimentId/report` 和实验历史：

- Agent status 与 Benchmark outcome 分轨展示；
- task、suite、agent 和 experiment 指标；
- Evaluation Tree 与叶子 evidence；
- micro/macro、Wilson interval、公平性警告；
- 多 Agent paired comparison、wins/ties 和样本限制；
- report、trajectory、artifact 和完整 bundle 导出。

界面不得把描述性小样本结果写成统计显著性结论；必须展示后端提供的
`significance_claimed` 和公平性/样本警告。

5.4A 已补齐 paginated Experiment history、Experiment 级 artifact inventory、
strict Core report/Evaluation Tree parser 和 bounded loader，具体实现与验证见
[Studio Benchmark Reporting Resource](studio-benchmark-reporting-resource.md)。
5.4B 已实现可重建的单 Experiment Report、Studio/Core run identity bridge、
TaskRun deep-link selection、三条事实轴、Evaluation Tree、partial failure 和原生
Replay handoff，具体实现与 no-device 浏览器证据见
[Studio Benchmark Report View](studio-benchmark-report-view.md)。5.4C 已实现
strict Experiment aggregate projection、per-Agent metrics、paired comparison、
fairness warning、significance boundary 和独立有界分页，具体实现与 synthetic
presentation 证据限制见
[Studio Benchmark Comparison and Metrics](studio-benchmark-comparison-metrics.md)。
5.4D-1 已实现 strict filter、schema 7、filter-bound cursor v2 与可重建
`/experiments`，具体实现与证据限制见
[Studio Benchmark Experiment History](studio-benchmark-history.md)。5.4D-2
已实现 exact causal resolver、strict content capability、bounded stream、
escaped text、dimension-bounded PNG、download-only ZIP 与 disposable
React-local Viewer，具体实现与证据限制见
[Studio Benchmark Evidence Viewer](studio-benchmark-evidence-viewer.md)。正式
Export 已通过共享 GET/HEAD resolver、安全 attachment/CORS headers、strict
manifest、refresh + HEAD preparation、per-artifact single-flight 与 browser-owned
handoff 完成，具体实现、clean-wheel 与 no-device 浏览器证据见
[Studio Benchmark Export](studio-benchmark-export.md)。Stage 5.4 已完成，随后
进入 5.5，并完成 5.5A resource、5.5B-1/2/3、5.5C-1/2、5.5D 与 5.5E-1/2；
Stage 5.5 与 5.6A/B/C-1/C-2 均已完成；Stage 5 已没有待执行 change。
5.4D 不增加
Experiment 级猜测 Replay link：History 只消费权威
Experiment link，实际 Replay handoff 继续使用具体 TaskRun 的 `links.replay`。
完整拆分、事实边界与验收顺序见
[Studio Stage 5.4 Benchmark Reporting 路线](studio-benchmark-reporting-roadmap.md)。

### 5.5 Benchmark authoring

Stage 5.5 永久拆成五个工作流、十个按依赖排序的可执行 Change：5.5A、
5.5B-1/2/3、5.5C-1/2、5.5D 与 5.5E-1/2/3。这样既避免把持久资源、React 编辑、二进制内容能力、
无副作用验证、可执行 Contract Test 和 publication/migration 混成一次交付，也
避免把 manifest、task 与 Protocol 人为拆成无法独立验收的半个编辑器：

1. 5.5A `implement-studio-benchmark-authoring-resource-5-5a`（已实现）：
   strict schema-1 parsed authoring document、SQLite schema 8 durable draft/current
   pointer、immutable revision、scoped command idempotency、server-owned content
   object、私有三模板 scaffold、Catalog declared-closure copy-import、
   optimistic save、bounded HTTP resource 和 restart reconstruction。完整边界与
   no-device/clean-wheel 证据见
   [Studio Benchmark Authoring Resource](studio-benchmark-authoring-resource.md)；
2. 5.5B-1 `implement-studio-benchmark-definition-editor-5-5b1`（已实现）：新增
   `/benchmark-authoring` 入口与 `/benchmark-drafts/:draftId/edit` 稳定资源路由，
   消费 5.5A draft/revision/CAS HTTP，提供 template/Catalog 创建、Draft
   list/open、structured manifest/split/Protocol editor、显式 JSON task buffer、
   inline JSON ground truth、dirty/reset/reload/conflict 和离开保护。TanStack Query
   只保存服务端资源，feature-local store 保存 baseline、working document、raw
   buffer、base revision 与 conflict；语法损坏 JSON 只能留在客户端。结构化编辑
   必须无损保留未知扩展字段；resource 与文件型 ground truth inventory 此时只读。
   完整边界、自动化与 no-device browser 证据见
   [Studio Benchmark Definition Editor](studio-benchmark-definition-editor.md)；
3. 5.5B-2 `implement-studio-benchmark-authoring-content-5-5b2`（已实现）：新增后端
   draft-owned managed-content upload/exact-read/replace/logical-remove command，
   capability 必须由 draft/revision/resource identity 精确限定，不得把
   `contentIdentity` 暴露为全局 bearer token。写入必须有容量限制、流式摘要、
   command idempotency、base-revision CAS、临时对象晋升与失败清理；replace 生成
   新 immutable content identity，remove 只在新 revision 解除引用，不删除旧
   revision 仍需的字节。本 Change 不增加 React resource editor、quota、retention
   或全局 content GC。完整边界、自动化与 clean-wheel 证据见
   [Studio Benchmark Authoring Managed Content](studio-benchmark-authoring-content.md)；
4. 5.5B-3 `implement-studio-benchmark-resource-editor-5-5b3`（已实现）：在 5.5B-2
   上增加 URL-owned definition/resource modes、asset 与文件型 ground-truth
   inventory/upload/replace/missing repair/confirmed logical removal UI、clean saved
   baseline gate、selected-only exact HEAD、uncertain exact retry 和 historical-result
   current non-regression。成功后只用权威 immutable revision 重建会话；UI 显示
   media type、size、SHA-256、missing、conflict 与 failure 事实，不把上传成功描述
   为 semantic validation。完整边界、自动化与 no-device browser 证据见
   [Studio Benchmark Resource Editor](studio-benchmark-resource-editor.md)；
5. 5.5C-1 `implement-studio-benchmark-validation-dry-run-resource-5-5c1`（已实现）：
   将 exact current immutable revision 通过私有、一次性 Package materialization
   适配到已有 validate/dry-run，增加 revision-bound strict DTO/HTTP、
   field-addressable diagnostics、稳定 Package/Plan/Protocol/AgentGraph identities、
   有界 deterministic schedule、budget、fairness warning、output layout 和明确
   unverified materialization。实现保持 SQLite schema 8，验证前后均检查 current，
   通过 immutable Agent revision verifier 与 pre-allocation 10,000 cap 生成完整规划，
   并以 HTTP canary、cleanup、restart 和 clean-wheel 证明零 runtime side effect。完整
   边界、证据、取舍与限制见
   [Studio Benchmark Validation / Dry-run Resource](studio-benchmark-validation-dry-run-resource.md)；
6. 5.5C-2 `implement-studio-benchmark-validation-dry-run-view-5-5c2`（已实现）：在
   5.5C-1 上增加 URL-owned React Validation mode、clean saved baseline gate、
   frozen immutable Agent revision 选择、generation/owner-bound transient result、
   revision-bound stale-result 处理、typed diagnostic navigation，以及对 partial
   identities、完整有界 schedule、budget/fairness/layout/unverified/no-execution 事实的
   诚实展示。页面不自动分析、不持久结果、不推进 `unvalidated` revision，也没有 Run、
   Contract Test、Publish 或 Migrate 控件。完整边界、自动化和 no-device browser 证据见
   [Studio Benchmark Validation / Dry-run View](studio-benchmark-validation-dry-run-view.md)；
7. 5.5D `implement-studio-benchmark-contract-tests-5-5d`（已实现）：显式
   exact-revision fake-fixture initializer/environment/evaluator Contract Tests，提供
   stable case-local seed、fresh-scope observable isolation、lifecycle/evaluator
   normalization、bounded safe result、passed/failed/skipped 与独立 completeness/
   executed-check facts；device/network/model/secret/runtime 默认禁止。React
   `contract-tests` mode 只允许 clean saved baseline 显式运行，并以 strict request
   owner/generation 处理 late/stale result。完整边界、自动化、clean-wheel 和
   no-device browser 证据见
   [Studio Benchmark Contract Tests](studio-benchmark-contract-tests.md)；
8. 5.5E-1 `implement-studio-benchmark-validated-freeze-5-5e1`（已实现）：对 exact current
   revision 重新验证全部声明 split 与完整 definition/content 闭包，以独立 immutable
   validation attestation 记录资格，再冻结 closed immutable Package revision。既有
   authoring document、fingerprint 与 revision 不原地改写；5.5C transient result 和
   5.5D fake-fixture pass 都不能直接成为 freeze/publication 资格。实现以 canonical
   definition bytes、verified managed binary members、SQLite schema 9 atomic commit、
   scoped idempotency、exact HTTP read、restart 与 clean-wheel 证明完整 closure 和零
   runtime side effect；完整边界、证据、取舍与限制见
   [Studio Benchmark Validated Freeze](studio-benchmark-validated-freeze.md)；
9. 5.5E-2 `implement-studio-benchmark-publish-export-5-5e2`（已实现）：只消费 5.5E-1 frozen
   Package revision，通过 database-sibling server-owned managed Package store 显式
   publish，并以新的 immutable Catalog snapshot 原子替换当前 snapshot。相同
   `publisher/name@version` 的相同内容可幂等返回，不同内容必须冲突；Export 从同一
   frozen revision 生成稳定排序、固定元数据和完整性可校验的确定性 Package，不写入
   workspace `benchmarks/`、`data/` 或任何源 Catalog tree。SQLite schema 10、
   scoped GET/HEAD、URL-owned React Release mode、重启恢复、clean-wheel 与 no-device
   browser 证据见
   [Studio Benchmark Package Publication / Export](studio-benchmark-package-publication-export.md)；
10. 5.5E-3 `implement-studio-benchmark-legacy-migration-5-5e3`（已实现）：对 bounded legacy
    BenchmarkTask JSON 提供 side-effect-free preview、结构化 diff 与 explicit confirm。
    confirm 必须重新计算 source/preview fingerprint 并幂等创建新的 `unvalidated`
    draft；重复 task ID、V1 拒绝字段或不安全输入必须阻止 confirm，不能自动改名、
    发明 Protocol/ground truth、修改原文件，或直接 freeze/publish。完整 identity、
    schema-10 Confirm、React ownership、clean-wheel 与 AppAgent/AndroidWorld browser
    证据见
    [Studio Benchmark Legacy Migration](studio-benchmark-legacy-migration.md)。

5.5B-1 第一版 JSON task surface 使用客户端 raw text buffer、显式 parse/apply 和
清晰语法错误，不为此引入 Monaco/CodeMirror 等重型编辑器依赖；仅可解析、安全的
结构才能提交 5.5A revision。5.5B-1/2/3 均不实现 Benchmark 拖拽画布，也不扩展
`pipeline: unknown[]`。复杂 initializer/evaluator 继续走后端插件扩展；trusted
third-party code 不是进程沙箱保证。5.5C-1/2 的 validation/dry-run result 是无副作用、
非持久的 definition-level fact，不把 `unvalidated` revision 变成 runnable/publishable
Package；5.5A/B/C 不得提前伪造 5.5D 或 5.5E-1/2/3 的事实，5.5D fake-fixture pass 也
不得被描述为 validated revision、publication eligibility 或真实执行证明。

### 5.6 分层与真实 Android 验收

原 `validate-studio-benchmark-android-5-6` 不是一个可执行 mega-change，而是以下
四项永久有序 change 的 umbrella。拆分原因是 explicit device authority、无设备
回归闭合、后端真机副作用与浏览器产品证据具有不同失败面和完成证据，不能用一次
真机 smoke 同时证明。

#### 5.6A `implement-studio-benchmark-android-profile-5-6a`（已实现）

- 用安全 `deviceProfileId` 显式绑定私有 serial/device session，原始 serial 不进入
  普通 DTO、事件、日志、报告链接或浏览器状态；
- online/offline/unauthorized、多个设备、platform/locale/orientation 与 profile
  漂移在 Agent 动作前 fail closed，不回退到“唯一在线设备”；
- 建立 fake fixture、historical Replay 与 fresh real Android 的证据来源边界；页面和
  durable resource 不得仅凭 profile 名称推断真机事实；
- 只建立运行前置 authority、safe provenance 与自动化 fake/contract 证据，不执行
  Android Benchmark，不产生新的 device success claim。

实现采用 strict schema-1 trusted JSON、无配置空 resolver、SQLite schema 11 atomic
private binding、exact-target process-local shared lease，以及 acquisition/environment
两轴来源。验证证据为包含 clean-wheel profile acceptance 的完整后端 `828 passed`、
该用例独立 `1 passed`、5.6A focused backend `149 passed`、完整前端
`88 files / 391 tests`、
typecheck 与 lint；全部为 no-device/fake/contract evidence。配置、回滚和限制见
[Studio Benchmark Android Profile 与证据来源](studio-benchmark-android-profile.md)。

#### 5.6B `validate-studio-benchmark-layered-acceptance-5-6b`（已实现）

- fake-device：成功、FAIL、INVALID、SKIPPED、取消、部分结果、evidence/publication
  failure、interruption 与 cleanup；
- repository/service：幂等命令、刷新、SSE/Last-Event-ID 重连、慢客户端、进程重启、
  recovery、唯一 terminal 与不重放不确定副作用；
- browser：Catalog → Composer → Monitor → Report/Evidence → Replay → Export，包含
  refresh/disconnect/theme 与权威 link；
- package：clean wheel、installed external Benchmark Package 与无隐式 source path；
- protocol/fairness：Core Runtime 继续验证 multi-Task、repeats、多 Agent、
  TaskInstance reuse 与 paired/fairness；Studio Worker 则验证 1×1×1 超限被整体拒绝，
  不截断执行，也不声称已扩容；
- 全部结果明确为 fake/no-device evidence，不授予真实 Android 能力。

实现以 14 个稳定场景的 versioned bounded proof ledger 连接 safe causal identities，
并使用 production Studio service/repository/worker/Core/publication/Replay composition。
actual-backend 真浏览器完成 Catalog → Composer → Monitor → Report/Evidence → Replay →
Export，刷新重建同一 durable facts；独立安装的 Benchmark distribution 在 repository
之外完成 clean-wheel durable fake Experiment，六个 forbidden-effect canary 为 0。
验证证据为 focused `28 passed`、external-Package clean-wheel `1 passed`、完整后端
`857 passed`、完整前端 `88 files / 392 tests`，以及 typecheck、lint、build 和两类
浏览器 gate。所有执行均为 `contract_fixture/fake_device`，
`realDeviceEvidence=false`；完整边界见
[Studio Benchmark 分层无设备验收](studio-benchmark-layered-acceptance.md)。

#### 5.6C-1 `validate-studio-benchmark-android-service-5-6c1`（已实现）

- 由用户明确选择 5.6A 配置的安全 profile、一个 immutable Agent revision、一个
  Package/task 和一个 repeat；
- 代表性正例必须同时满足 Agent SUCCESS、Benchmark PASS、evaluator PASS、独立
  device state delta，以及可加载 result/report/trajectory/bundle；
- 受控负例必须是 Agent 正常结束但未完成任务，得到 Agent SUCCESS、Benchmark FAIL、
  INVALID=0 和无新增 device evidence，不能通过破坏 preflight/setup/cleanup 制造；
- 两个 Experiment 都必须经过实际 Studio repository、worker、durable journal、
  managed publication、native Replay、report/evidence/export 和 terminal restart
  non-replay 边界；
- 原始 serial、secret、live device/component、宿主绝对路径不得进入公共或受管产物。

本轮固定 `stage-5-6-acceptance`、Android `en-US` portrait、
`zhixing/android-world@1.0.0` / `AndroidWorld_6`、seed 42、两条 immutable revisions
与一次 repeat。正例为 Agent success + Benchmark/evaluator pass + 独立图片增量 1；
受控失败为 Agent success + Benchmark/evaluator fail + `INVALID=0` + 图片增量 0。
managed closure、exact GET/HEAD、native Replay 与 terminal restart non-replay 均通过，
source/replay provenance 分别为 fresh real true 与 historical real-source false，私有
authority 扫描为 0。完整证据见
[Studio Benchmark 真实 Android 服务验收](studio-benchmark-android-service.md)。

#### 5.6C-2 `validate-studio-benchmark-android-view-5-6c2`（已实现）

- 在真实 Studio backend 上完成 Catalog → Composer → Monitor → Report/Evidence →
  Replay → Export 浏览器闭环；
- 验证 SSE reconnect/refresh、TaskRun 选择、独立 Agent status/Benchmark outcome、
  Evaluation Tree、managed artifact、native Replay 与浏览器下载 authority；
- 页面必须分别标识 fresh real Android、historical Replay 与 fake fixture，不能从
  URL、标题、profile ID 或截图外观推断 provenance；
- 本 change 不修改 runtime/worker 语义，只闭合 UI 合同、人工观察与证据清单。

实际浏览器创建两条新的真实 Android Experiment；两条 event stream 均连续到 19/19，
Monitor/Report/Replay refresh 后身份与 outcome 不漂移，正例 PASS、受控失败 FAIL，
Replay 明确保持 `replay_projection / real_android / false`。Export 完成 refresh+HEAD 与
browser handoff，不声称下载完成。最终 C-2 ledger 扫描 236 项公开/留存证据，
`privateValuesFound=0`；完整前端 `89 files / 399 tests`、完整后端 `921 passed`，并通过
typecheck、lint 与 production build。完整证据见
[Studio Benchmark 真实 Android 浏览器验收](studio-benchmark-android-view.md)。

5.6 的真机证据只证明明确设备、locale/orientation、Package/task、Agent revision、
App 版本与单次验收配置。代表性正例/负例不能表述为全量 Benchmark 通过率、通用
模型能力、任意 Android 兼容或统计显著性。Studio multi-Task/repeats/multi-Agent
worker expansion 若未来需要，必须作为独立产品 change，不能藏在 5.6B/C 验收中。

## 已接受的默认决策

后续 Change 默认遵守以下决定，除非实现证据表明需要显式修改 OpenSpec：

1. Stage 5 拆分为 5.0–5.6；5.2 拆为 5.2A、5.2B、5.2C-1 event stream、
   5.2C-2 publication/Replay 和 5.2C-3 startup recovery，不建立覆盖 repository、
   execution、durability、Monitor 与 reporting 的超大 Change；
2. 5.0 只做合同、设计、任务和验收矩阵，不修改应用代码；
3. 5.1 先完成 Catalog、Task 选择和 schedule preview；
4. 5.2A 先建立持久资源，5.2B 接入 Experiment 执行；随后依次完成 5.2C-1 事件传输、
   5.2C-2 artifact/publication/Replay 和 5.2C-3 startup recovery；
5. 第一条可运行切片为一个 Agent、一个 Benchmark、一个 Task、一个 repeat；
6. fake-device 与浏览器闭环先行，真实 Android 验收放在 Stage 5 最后，并按
   5.6A、5.6B、5.6C-1、5.6C-2 顺序执行；
7. Core multi-Agent comparison 是已验证的 Benchmark Runtime/fairness 能力；Studio
   Worker 的 multi-Task/repeats/multi-Agent 扩容不属于 5.6 验收范围；
8. Benchmark authoring 在运行、监控和报告稳定后实施；
9. 替换旧 Benchmark 占位模型，不扩展无类型的 `pipeline: unknown[]`；
10. 普通 StudioRun 与 Benchmark Experiment 保持独立资源和入口；
11. 第一版使用 SQLite，通过 repository port 为 PostgreSQL 留出替换空间；
12. Stage 5 新前端代码继续遵循 FSD-lite
    `app → pages → widgets → features → entities → shared`。
13. 5.3 已完成，5.4 不重新实现 Monitor event session，也不在浏览器中重算正式
    report 指标。
14. 5.4 永久拆为 5.4A reporting resource、5.4B report/Evaluation Tree、5.4C
    comparison/metrics、5.4D-1 History、5.4D-2 Evidence Viewer 和 5.4D-3
    Export；必须按顺序实施。
15. 5.4A、5.4B、5.4C 与 5.4D-1/2/3 已完成；5.4C 只消费后端正式
    metrics/comparison/fairness 事实，不在浏览器重算，也不把 synthetic fixture
    描述为真实多 Agent 证据；5.4D-1 使用 durable identity 和 filter-bound
    cursor，不从当前 registry 或页面当前页推断历史；5.4D-2 只通过 exact causal
    identity 和 strict scoped capability 打开有界 evidence；5.4D-3 只从 closed
    inventory 消费权威 capability，用 HEAD 准备并把大文件交给浏览器，不声称
    下载完成。
16. Stage 5.5 永久拆为 5.5A resource、5.5B-1 definition editor、5.5B-2
    managed content backend、5.5B-3 resource editor、5.5C-1 validation/dry-run
    resource、5.5C-2 validation/dry-run view、5.5D Contract Tests、5.5E-1
    validated freeze、5.5E-2 publication/export 和 5.5E-3 legacy migration；
    5.5A、5.5B-1/2/3、5.5C-1/2、5.5D 与 5.5E-1/2/3 已完成，只证明持久安全
    authoring resource、definition/resource editor、managed-content backend、无副作用
    revision-bound validation/dry-run planning，以及 reviewed in-process fake-fixture
    Contract Test facts、exact-current all-split validation attestation、closed
    immutable Package revision、managed Catalog publication 与 deterministic Package
    export，以及 bounded preview/diff/confirm legacy migration。5.6A explicit Android
    profile/provenance、5.6B layered no-device acceptance 与 5.6C-1/2 real Android
    service/browser acceptance 均已完成，Stage 5 已闭合；不得把 migration、
    `unvalidated` revision、schedule preview、fake-fixture pass 或 E-1 freeze 描述为
    真实 execution；E-2 publication/export 也不等于 Agent/Benchmark execution、
    Contract Test evidence 或真实 Android 证据。
17. Stage 5.6 永久拆为 5.6A explicit profile/provenance、5.6B layered no-device
    acceptance、5.6C-1 real Android service acceptance 与 5.6C-2 real Android
    browser acceptance；原 `validate-studio-benchmark-android-5-6` 只作为 umbrella，
    不作为 executable change。5.6A 已实现且没有产生真机 success claim；5.6B 已分别
    验证 Core multi-cardinality 与 Studio 1×1×1 fail-closed boundary，并以 actual
    fake backend browser、external-Package clean wheel 和 bounded ledger 闭合 no-device
    证据，不在验收 change 中扩展 Worker cardinality。Stage 5 内不再指定 current next；
    后续产品扩容、矩阵扩展或论文演示准备必须单独立项并保持本节 claim limits。

## 跨阶段完成标准

- Catalog、compile、validate 和 schedule preview 不得连接设备、解析 secret 或执行
  Benchmark 插件；
- Experiment 必须绑定不可变 Agent revision 和不可变定义 snapshot；
- event journal 是刷新、重连和恢复的事实源，SSE 只是增量传输；
- create/cancel 等命令必须具有明确幂等语义；
- 取消、失败或重启不得丢失已经持久化的安全事件、结果和 artifact；
- Agent status、Benchmark outcome 和 service lifecycle 不得合并为单一状态；
- TaskRun 与 Replay 的身份映射必须显式，不根据文件名或 UI 标题推断；
- Studio 只能通过安全 device profile 选择设备，不直接接受任意 serial；
- Prompt、secret、原始 device serial、宿主绝对路径和 live object 不得进入普通
  API、事件、日志或导出；
- 统计与公平性字段来自后端报告，不在前端重新计算竞争性结果；
- 旧 Benchmark JSON、Package、CLI 和公共 Python API 在新路径取得验证前继续可用；
- 每个实现 Change 都必须同时验证后端合同、前端类型/构建、关键交互和相关
  packaging boundary。

## 非目标与后续方向

Stage 5 第一版不承诺：

- 多设备分布式并行调度；
- PostgreSQL 已实现，只保证 adapter 边界不被 SQLite 写死；
- 实时视频、网页内真实设备直接控制、暂停 checkpoint 或节点重试；
- Benchmark 拖拽式 authoring；
- 任意第三方插件的进程沙箱、签名和权限隔离；
- 自动失败根因诊断；
- 任意 Agent、任意设备、全部 AndroidWorld/AppAgent 任务通过；
- 小样本 paired comparison 具有统计显著性。

这些能力若进入范围，应建立独立 OpenSpec Change，不应在 Stage 5 实现过程中静默
扩大合同。
