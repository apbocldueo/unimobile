# Studio Benchmark Execution Worker（Stage 5.2B）

本文记录 Stage 5.2B 已实现的 Benchmark Experiment 第一条可执行后端纵向切片。
它延续 [Stage 5 路线图](studio-benchmark-experiment-roadmap.md)、
[Experiment 合同](studio-benchmark-experiment-contracts.md)和
[Stage 5.2A 持久资源](studio-benchmark-experiment-resource.md)，但不代表 5.2C-1/2/3
后续三个 Change 的公共事件流、受管 publication/Replay 或启动恢复已经完成。

## 目的与完成形态

Stage 5.2A 只能把 preview 保存成 `accepted` Experiment。Stage 5.2B 解决的是：
由服务进程领取本进程新提交的 Experiment，从 immutable snapshot 重建执行输入，
在所有设备副作用前完成验证，然后把正式 Benchmark Core 的生命周期和结果原子
写回 planned TaskRun。

变更前：

```text
preview → durable Experiment(accepted) → query / accepted cancel
                                      └── 不执行 Benchmark
```

变更后：

```text
POST create commit
      ↓ post-commit enrollment + bounded wake
SQLite accepted aggregate
      ↓ CAS claim（单进程 owner）
pure immutable preflight
      ├── snapshot / cardinality / schedule
      ├── Package / Plan / Protocol / resources
      └── AgentGraph / component availability
      ↓
private evidence capacity → safe profile resolve → exclusive device lease
      ↓
fresh ExecutableAgent + BenchmarkExperimentRuntime
      ↓ synchronous durable event append
bounded TaskResult transaction
      ↓
TaskRun terminal → Experiment terminal
```

第一条切片严格限制为一个 Agent revision、一个 Benchmark Catalog entry、一个 Task、
一个 repeat。超过限制会在设备访问前整体失败，不会静默截断。公开 DTO 继续保留
复数结构，后续扩展不需要重新定义资源身份。

## 已实现边界

### Benchmark Core 兼容 seam

- `BenchmarkExperimentRuntime.run()` 新增可选 caller-owned cooperative
  cancellation；默认调用方式和 canonical identity 不变；
- caller signal 与 Protocol deadline 组合后传入 Agent Runtime，并在物化、shared
  reset、各阶段、Agent、evaluation、cleanup 和下一 schedule 的安全边界检查；
- cancellation 不强杀正在执行的 opaque 调用，必要 cleanup 仍运行，已经产生的
  evaluation 不被抹除；
- 新增 runtime-only publication policy，默认仍发布原 task manifest、report、
  trajectory 和 bundle；Studio 使用 `defer`，只取得完整内存结果，不制造未注册
  的公开 artifact。

### SQLite schema 5 与 repository

共享 Studio SQLite migration 单调升级到 schema 5。它保留 schema 4 的 Experiment、
planned TaskRun、cancel、terminal 和 event sequence 事实，同时扩展：

- process owner、Core TaskRun ID、Agent run ID 和 TaskInstance identity；
- `preparing/running/evaluating/cleaning_up/terminal` TaskRun lifecycle；
- TaskInstance、phase、Agent status、Benchmark outcome、Evaluation、result 和 Replay
  的独立 availability；
- bounded result JSON/fingerprint、阶段投影和生命周期时间戳；
- event source/source sequence/phase 与唯一 Experiment terminal event。

Application、orchestrator 和 scheduler 只依赖 typed repository operations：
enroll、next-work、claim、forward transition、cancel、idempotent event append、
result commit、pre-result finish 和 Experiment finalize。SQLite 是首个 adapter；
这些领域操作没有把 SQL row 或 SQLite locator 暴露给 HTTP，后续 PostgreSQL adapter
应实现同一 contract suite。

事务保证：

- event identity 相同且 fingerprint 相同会幂等返回，不同内容会冲突；
- result、availability、TaskRun terminal 和对应 event 要么一起提交，要么全部回滚；
- 已提交 PASS/FAIL/INVALID 不会被迟到 cancel 或旧 owner 用空结果覆盖；
- Experiment 最多一个 terminal event；
- result 已提交而 finalization 瞬时失败时，只重试原 completed/cancelled 解释，不会
  改写为 failed。

### Pure preflight 与 evidence/device boundary

Worker 只使用 Experiment snapshot，不读取当前 revision 作为执行事实。已接受后即使
Agent 保存了新 revision，仍执行 snapshot 中的旧 revision/AgentGraph。Pure preflight
会复核：

- snapshot fingerprint、第一切片 cardinality、planned coordinates 和 derived seed；
- Catalog source、Package identity/content、BenchmarkPlan 和 ExperimentProtocol；
- logical resource confinement/digest；
- AgentGraph canonical identity 与配置环境中的 component metadata availability。

这些检查不解析 runtime device profile，不获取设备 handle，不运行 task generator、
initializer、evaluator、Agent 或模型。通过后先在数据库旁建立永久、Experiment-scoped
的私有 evidence namespace，检查可写性和最低容量；随后才解析安全 profile、获取
进程内独占 lease 并进入 Core。公共资源只保存安全 logical reference，不返回宿主路径、
raw serial 或 live handle。

### 单 Worker、事件与取消

每个 composition 只有一个 long-lived daemon worker 和一个有界 `Event` wake flag，
没有每个 Experiment 一个 `Future`，也没有无界内存 definition queue。待执行定义和
顺序仍来自 SQLite，按 `(acceptedAt, experimentId)` 选择。第二个 Experiment 在忙时
保持 `accepted`，前一个释放 slot 后再执行。

5.2B 只 enrollment 本进程新提交的 accepted row。启动时不会擅自领取旧进程留下的
accepted/in-flight work；这是 5.2C-3 的 recovery 决策。

Core lifecycle event 会同步映射到 planned TaskRun journal：

- Studio `task-run-*` 始终是公共 resource identity；
- Core TaskRun、TaskInstance、Agent run 和 Core source sequence 只是 provenance；
- append 在 Core 进入下一 effect 前完成；
- append 失败会取消 shared signal 并抛出，后续 effect 不再启动；已经发生的外部
  effect 不会被虚假描述为已回滚。

Cancel 永远先提交 SQLite cancellation，再通知 active signal：

- accepted cancel 仍原子收口为 `cancelled_before_start`；
- starting/running 进入 `cancelling`，在安全边界停止新工作并保留 cleanup/evaluation；
- finalizing 的 late cancel 不覆盖已提交 outcome；
- terminal cancel 返回 immutable 当前事实；
- active registry 只是进程内通知优化，SQLite 才是权威事实。

### Result 与 HTTP

Result projector 只复制显式 typed facts，不遍历或保存完整 `RunResult`：

- planned/Core TaskRun、Agent/revision、task/repeat/order、Graph/Plan/Protocol/
  TaskInstance identities；
- service terminal reason、Benchmark phases、Agent `RunStatus`、Benchmark outcome；
- bounded Evaluation Tree、usage、公平性警告、安全 logical refs 和 diagnostics。

嵌套数据使用统一 sanitizer，并有 depth、member、text 和 256 KiB encoded JSON 上限。
secret、raw serial、绝对路径和 live object 会被 redacted、excluded 或截断；完整
runtime event history 不会在 result JSON 中重复。

沿用 Stage 5.2A 的 create/get/cancel/TaskRun HTTP 路由。完整 execution composition
真实返回：

```json
{
  "executes": true,
  "cancelAccepted": true,
  "cancelActive": true,
  "eventStream": false,
  "replay": false,
  "reports": false
}
```

Definition-only 测试 composition 继续返回 `executes=false/cancelActive=false`。
没有 event、Replay 或 report link。`StudioHTTPServer.server_close()` 会释放普通 Run
和 Benchmark 两个 scheduler，但不会删除 Experiment、result 或私有 evidence。

## 自动化与手工复验

最小 fake-device 纵向复验：

```bash
UV_CACHE_DIR=/tmp/zhixing-uv-cache \
uv run pytest -q \
  tests/studio/test_benchmark_execution_worker.py \
  tests/studio/test_benchmark_experiment_resource.py \
  tests/benchmark/test_experiment_runtime.py
```

预期可观察到：

- PASS、Agent SUCCESS + Benchmark FAIL、INVALID、materialization failure、
  device mismatch 和 cleanup failure 都由正式 Core 产生并被 Worker 持久化；
- 两个 accepted Experiment 串行执行，重复 wake 不重复执行；
- planned TaskRun ID 与 Core TaskRun ID 不同但映射稳定；
- active cancel 先出现 cancellation journal，再出现 terminal event；
- 关闭 HTTP/browser 后重新 GET，SQLite result 仍存在；
- security canary 不出现在 SQLite/HTTP payload。

更窄的单 Worker 手工证据：

```bash
UV_CACHE_DIR=/tmp/zhixing-uv-cache \
uv run pytest -q \
  tests/studio/test_benchmark_execution_worker.py \
  -k 'single_scheduler or independent_core_result_axes or active_cancellation'
```

这组命令使用 fake device，不证明真实 Android。真实 HTTP 复验需要配置一个受信任的
Benchmark Package、已保存 revision 和实际 `AndroidDeviceProfile`；默认
`local-android` 没有 live device handle 时会安全失败，而不是伪造执行成功。

## 已验证证据

2026-07-27 在项目 `unimobile` 环境中完成了以下复验：

- `python -m compileall -q zhixing tests`：通过；
- Worker、Experiment resource、Composer/HTTP、Benchmark Runtime 和 reporting
  专项回归：`100 passed`；
- 完整 Studio 回归：`147 passed`；
- 完整 Benchmark 与 packaging 回归（clean-wheel 单测除外）：`113 passed`；
- `PYTHONPATH=tests uv run pytest -q` 完整后端回归：`531 passed`；
- clean-wheel 隔离安装：`1 passed`；
- `openspec validate implement-studio-benchmark-execution-worker-5-2b --strict`：
  `Change ... is valid`。

验证过程中还观察并如实处理了两类非最终代码失败：

- 完整 Studio 首次为 `145 passed, 2 failed`。一项是 schema migration 预期仍停在
  `[1, 2, 3, 4]`，更新为 schema 5 后修复；另一项是既有普通 Run 终态 cancel
  的 event high-water 时序失败，单测与完整套件复跑均未复现，当前没有把它描述为
  已定位或已修复；
- Benchmark/packaging 在受限网络沙箱首次为 `110 passed, 3 failed`，三项均因隔离
  环境无法下载 `hatchling`、`Pillow` 或 `Pydantic`。允许依赖解析后原命令为
  `113 passed`。

这些自动化结果覆盖 fake-device、服务合同和 packaging 兼容性，不是新的真实
Android trajectory 证据。

## 明确限制

- 只有 1 Agent × 1 Task × 1 repeat；多 Agent/Task/repeat 与统计汇总未接入 Worker；
- 没有启动 recovery/requeue；旧进程 accepted 不自动领取，in-flight 不伪装 resume；
- 没有公共 event page/SSE、heartbeat、backfill 或慢客户端隔离；
- 私有 evidence 已永久保留，但没有 5.2C-2 managed artifact descriptor/download；
- 不发布 report、trajectory、bundle，也不把 TaskRun 注册为 native Replay；
- React Composer 仍没有 create/Monitor 流程；前端消费属于 5.3；
- PostgreSQL 只有 database-neutral seam，没有 adapter；
- 没有 quota、retention、delete 或自动 cleanup；
- 没有真实 Android 验收，不能据 fake-device 结果声明任意 Agent/Benchmark 支持。

## 后续交接顺序

Stage 5.2B 的后续工作不得重新合并为一个超大 durability Change：

1. `implement-studio-benchmark-event-stream-5-2c1`：在现有 durable journal 上增加
   event page、opaque cursor、named SSE、heartbeat、断线 backfill 和慢客户端隔离；
2. `implement-studio-benchmark-publication-replay-5-2c2`：幂等发布正式
   report/trajectory/bundle，建立 managed artifact resolver，并把 terminal TaskRun
   原子提升为 native Replay；
3. `implement-studio-benchmark-startup-recovery-5-2c3`：accepted 安全重新入队、
   不确定 in-flight 收口为 interrupted、finalizing 只重试 publication。

固定依赖顺序是 event stream → publication/Replay → startup recovery。React Monitor
继续属于 5.3；多 Task/repeats/多 Agent、PostgreSQL、retention/delete 和真实 Android
验收不进入这三个 Change。
