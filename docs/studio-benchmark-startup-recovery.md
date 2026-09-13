# Studio Benchmark Startup Recovery（Stage 5.2C-3）

本文记录已实现并验证的 Stage 5.2C-3。本 Change 在 Stage 5.2A 持久资源、5.2B
单 Worker、5.2C-1 durable event transport 和 5.2C-2 publication/native Replay
之上增加保守的进程启动恢复。规范性需求仍以主 OpenSpec specs 和
[Stage 5 合同](studio-benchmark-experiment-contracts.md)为准。

本文不代表线程/checkpoint resume、分布式调度、React Monitor/reporting UI、
多 Task/多 Agent、PostgreSQL、retention/delete 或真实 Android 验收已经完成。

## 解决的问题

旧进程退出后，SQLite 中的非终态 Experiment 仍带有旧
`process_owner_id`。只生成一个新 owner 并不能证明旧进程已经死亡；同时，
`running` 的最后一个设备动作可能已经发生，盲目重跑会产生第二次点击、输入或
评价污染。

变更前：

```text
process exit
  → accepted / starting / running / cancelling / finalizing 留在旧 owner
  → 新 composition 不领取，也没有明确恢复决定
```

变更后：

```text
build executable composition
  → acquire database-scoped OS ownership
  → page stale nonterminal aggregates
  → commit one conservative lifecycle decision
  → wake scheduler only for committed requeue
  → expose application service
```

## 已实现的决定矩阵

| 持久状态 | 恢复决定 | 执行边界 |
| --- | --- | --- |
| `accepted` | 保持 identity/snapshot/schedule，转移 owner 并回队 | 后续重新执行正常 preflight |
| `starting` | recovery-only reset 到 `accepted`，关闭旧 pending preflight facts | 不解析 profile、lease、Runtime 或设备 |
| `running` | 原子写 `recovery.interrupted`、TaskRun terminal、Experiment terminal | 不调用执行器、Agent 或设备 |
| `cancelling` | 保留 cancellation 与已提交结果/证据，按 uncertain work 中断 | 不用取消覆盖 PASS/FAIL/INVALID |
| `finalizing` + result、无 publication | 记录 publication-only，调用既有 C2 幂等 publisher，再 finalize | 不重跑 Runtime |
| `finalizing` + 已提交 publication | 记录 finalize-only，只补 Experiment terminal | 不重发 artifact、bundle 或 Replay |
| `finalizing` + 无 result | 从 TaskRun reason 推导 failed/cancelled/interrupted 并 finalize | 不构造 result、outcome 或 Replay |
| `terminal` / current owner | no-op | 不转移、不追加事件、不 wake |

`starting → accepted` 只存在于 repository recovery operation，不扩展普通正向状态机。
`claim_experiment` 的 starting/preparing event identity 包含 prior high-water，因此同一
Experiment 在安全回队后可再次 claim，而不会与第一次 preflight 的事件唯一键冲突。

## 实现边界

- `benchmark_experiment_models.py` 提供 versioned candidate、TaskRun projection、
  decision、attempt 和 bounded summary；DTO 不包含 raw owner、数据库/lock 路径或
  device locator。
- `benchmark_experiment_protocols.py` 提供 database-neutral recovery repository
  和 ownership ports；未来 PostgreSQL 可以替换 adapter，不需要把 SQL 暴露给
  orchestrator 或前端。
- `benchmark_experiment_repository.py` 在 schema 6 上实现 deterministic paging、
  owner/lifecycle CAS、requeue reset、interruption 和 finalizing claim。恢复决定、
  TaskRun facts 和 terminal event 位于同一 aggregate transaction；COMMIT 后才通知
  waiter。
- `benchmark_recovery.py` 实现 lifecycle decision table 与本地 ownership。POSIX
  使用 `flock`，Windows 使用 `msvcrt.locking`；不支持的平台明确失败，不用 heartbeat
  猜测进程死亡。
- `benchmark_composition.py` 在 scheduler 构造和 application service 暴露之前获取
  ownership 并完成 recovery；正常关闭、争用、storage/publisher/scheduler 构造失败
  都释放已构造资源。

schema 6 已经保存 lifecycle、owner、TaskResult、publication、Replay mapping 和
journal high-water，能够表达全部恢复事实，因此本 Change 没有新增 schema 版本。
lock marker 是私有 operational state，不进入 Experiment、HTTP 或 event DTO。

## 原子性与崩溃幂等

`running`/`cancelling` interruption 的同一事务顺序固定为：

```text
recovery.interrupted
  → task_run.terminal
  → experiment.terminal（唯一且最后）
```

requeue commit 发生在 scheduler wake 前。若进程在 commit 后、wake 前再次退出，下个
owner 重新转移同一 Experiment，而不会创建第二个 Experiment 或 planned TaskRun。

publication-only decision 与 publication transaction 可以分开提交。若 decision 后
崩溃，下次启动复用原 decision 的 journal high-water 作为 C2 immutable input；若
publication/Replay 已提交但 Experiment terminal 尚未提交，下次只 finalize，不创建
第二个 managed artifact、Replay row、Replay moment 或 terminal event。已提交的
partial/failed publication 同样保持不可变。

## 验证证据

- C3 专项覆盖 lifecycle、CAS、rollback、SSE、crash window、publication/Replay、
  ownership、composition cleanup 和安全 canary，`27 passed`；
- 5.2A–C3 focused resource/worker/event/publication/recovery 回归为
  `108 passed`；
- `tests/benchmark` 94 项通过；
- 完整 Studio 回归为 `208 passed, 1 failed`；唯一失败是既有普通 Studio Run
  terminal/high-water 时序用例；
  该竞态发生在普通 Run 先标 terminal、随后追加 `run.terminal` 的旧流程，不经过
  Benchmark recovery，本文不把它描述为已修复；
- wheel 已构建并安装到仓库外虚拟环境，从安装包成功构造 schema 6 executable
  composition、获取/release ownership、运行空 startup scan，并导入 event、
  publication 和 native Replay 边界；
- 所有新增/修改函数 docstring 已做 AST 检查；恢复 DTO、event 与 SSE canary 未暴露
  raw owner、数据库/lock 路径或 serial。

这些是 no-device、fake-device、HTTP/SSE、SQLite 和 clean-wheel 证据，不是新的真实
Android trajectory。

## 手工复验

在仓库根目录运行：

```bash
uv run pytest -q tests/studio/test_benchmark_startup_recovery.py

uv run pytest -q \
  tests/studio/test_benchmark_experiment_resource.py \
  tests/studio/test_benchmark_execution_worker.py \
  tests/studio/test_benchmark_event_stream.py \
  tests/studio/test_benchmark_publication_replay.py \
  tests/studio/test_benchmark_startup_recovery.py

uv run pytest -q tests/benchmark

<local-openspec-bin> validate \
  implement-studio-benchmark-startup-recovery-5-2c3 --strict

<local-openspec-bin> validate --specs --strict
```

预期观察：

- accepted/starting 保持 Experiment 和 TaskRun identity，并各自在 commit 后回队；
- running/cancelling 的恢复 suffix 为 recovery decision、TaskRun terminal、
  Experiment terminal，SSE 从旧 cursor 连续回放；
- result-bearing finalizing 只产生 publication/finalization，no-result finalizing
  保持 `not_produced`/`failed`；
- 第二个 executable composition 在同一数据库上明确 contention；第一个关闭或异常
  退出后可重新获取 ownership；
- terminal/current-owner 再次扫描 summary 为零且 journal 不增长。

## 已知限制与下一步

- 不恢复 Python thread、Agent node 或设备 action checkpoint；无法证明的 in-flight
  work 必须 interrupted。
- 第一条 Worker 仍是一个 Agent × 一个 Task × 一个 repeat。
- SQLite 是唯一实现 adapter；PostgreSQL 只有 typed port。
- 不实现跨主机 ownership、broker、distributed scheduler 或多设备并行。
- 不实现 retention、delete、quota、orphan-file cleanup 或 publication component
  升级重试。
- 不增加 recovery HTTP route；React Monitor 读取既有 Experiment/TaskRun/event/
  publication/Replay facts。
- 没有新增真实 Android 验收，不声明任意设备或任务可恢复。

Stage 5.2 durability 至此完成。下一步是
`implement-studio-benchmark-monitor-5-3`，由 React Monitor 消费现有 query/SSE 和
Replay links，不在前端重建 recovery 状态机。

## 规范与历史来源

- [Stage 5 产品路线](studio-benchmark-experiment-roadmap.md)
- [Stage 5 合同](studio-benchmark-experiment-contracts.md)
- [Stage 5.2B Worker](studio-benchmark-execution-worker.md)
- [Stage 5.2C-1 Event Stream](studio-benchmark-event-stream.md)
- [Stage 5.2C-2 Publication/Replay](studio-benchmark-publication-replay.md)
- [当前已接受的 OpenSpec 合同](../openspec/specs)（5.2C-3 历史变更不随公开源码发行）
