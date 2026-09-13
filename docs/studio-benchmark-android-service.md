# Studio Benchmark 真实 Android 服务验收（Stage 5.6C-1）

本文记录 2026-08-02 完成的 Stage 5.6C-1 有界真实 Android 服务验收。它证明
既有 Studio Benchmark durable service 能在一个明确选择的 Android 虚拟设备上，
通过生产 repository、Worker、Core Runtime、managed publication 和 Replay 边界完成
一个代表性正例与一个受控失败例。它不是 AndroidWorld 全量通过率、任意设备兼容性
或模型质量证明。

## 有界矩阵

| 维度 | 固定选择 |
|---|---|
| safe profile | `stage-5-6-acceptance` |
| platform / locale / orientation | Android / `en-US` / portrait |
| Package | `zhixing/android-world@1.0.0` |
| split / task | `test` / `AndroidWorld_6`（Take one photo） |
| Protocol | seed `42`，一个 repeat，预算与失败策略来自 immutable snapshot |
| Studio cardinality | 每个 Experiment 为 1 Agent × 1 Task × 1 repeat |
| Agent revisions | 一个执行拍照动作的 positive revision；一个正常结束但不拍照的 controlled-negative revision |

原始设备 serial、配置路径、private fingerprint、target key 和 live device authority
只在临时可信配置与进程内存在；公共资源、受管产物和本文只保留 safe profile 与
有界设备事实。验收结束后，服务被关闭，临时私有配置被删除。

## 执行流与前后差异

验收前，Stage 5.6A/5.6B 已证明 profile/provenance 合同和无设备分层链路，但所有
新证据仍为 fake/no-device，不能证明 Studio service 的真实 Android 行为。C-1 没有
新增另一套 Runtime，而是从真实产品入口闭合下列链路：

```text
explicit confirmation + trusted safe profile
        ↓ fail-closed preflight / exact target lease
Studio create → SQLite Experiment/TaskRun → single Worker
        ↓
Core Benchmark Runtime → initializer → AgentGraph → Android executor
        ↓
evaluator → cleanup → durable journal → terminal publication
        ↓
report / trajectory / manifest / bundle / native Replay / exact GET+HEAD
        ↓
stop service → reopen same durable workspace → reconstruct without source replay
```

验收后，正例和受控失败例都具有独立的 service lifecycle、Agent status、Benchmark
outcome、evaluator 与设备状态事实；终态重启从持久资源重建，不重放 initializer、
Agent、evaluator 或 Android action。

## 实际结果

| 场景 | service / Agent | Benchmark / evaluator | 独立设备观察 | 结论 |
|---|---|---|---|---|
| `real_android_positive` | Experiment 与 TaskRun `terminal/completed`；Agent `success` | `pass` / `true`；`INVALID=0` | MediaStore 新增 1 个目标图片，动作证据非空 | 通过 |
| `real_android_controlled_fail` | Experiment 与 TaskRun `terminal/completed`；Agent `success` | `fail` / `false`；`INVALID=0` | 未出现目标图片增量，未用基础设施错误替代失败 | 通过 |

两个 source TaskResult 都是
`fresh_execution / real_android / realDeviceEvidence=true`；对应 native Replay 是
`replay_projection / real_android / realDeviceEvidence=false`。Replay 继承真实来源环境，
但它是历史投影，不是一次新的真机执行。

## 因果证据与 managed closure

每个场景从 Experiment ID 显式连接 planned TaskRun、Core TaskRun/Agent run、immutable
Agent revision、TaskResult、publication、artifact inventory 与 Replay ID。验收逐项复核
正式 Experiment report、Task report、TaskResult、NDJSON trajectory、definition/runtime/
publication manifests、action/screenshot evidence、Experiment bundle 和 Core trajectory
bundle。所有必需成员均通过 exact Experiment/TaskRun scope、GET/HEAD、content type、
size 与 SHA-256 验证；没有通过文件名、标题或相邻列表项拼接证据。

正例重启前后 source-effect count 均为 `15`，受控失败例均为 `13`；两者 event
high-water、资源身份与唯一 terminal transition 均保持不变，重启新增目标媒体数为
`0`。因此该证明只支持 terminal reconstruction/non-replay，不支持 checkpoint resume。

## 安全与失败边界

- 验收 summary schema 为 `studio-benchmark-android-service-5.6c1-v1`，两场景均为
  `verification=passed`、`realDeviceEvidence=true`；
- 数据库公开字段、event、report、trajectory、Replay、manifest、bundle、export
  metadata 与 summary 均经过私有 authority canary 扫描，`privateValuesFound=0`；
- safe device reference 进入 observation/action evidence 前由公共 redaction helper
  归一化；原始 device identity 不再通过 `repr()` 泄漏；
- preflight、setup、cleanup、timeout、cancel、authority drift 或 infrastructure failure
  都不能被计作 controlled-negative；
- 本地可选插件导入仍提示缺少 `cv2`、`torch`、`pyperclip`、`openai` 与 Harmony
  driver。这些插件不属于所选相机任务路径，未阻断本次验收，但不是“完整可选依赖已安装”
  的证明。

## 复验命令

真实设备运行必须由操作者明确确认，并提供不会提交到仓库的可信 profile 配置：

```bash
uv run python scripts/studio_benchmark_android_service_acceptance.py run \
  --confirm-real-android \
  --device-profile-id stage-5-6-acceptance \
  --device-profile-config <trusted-profile-config> \
  --workspace-root <disposable-campaign-root> \
  --x 540 --y 2052 --timeout-seconds 900

uv run python scripts/studio_benchmark_android_service_acceptance.py validate \
  <campaign-root>/acceptance-summary.json
```

本轮 retained summary 位于 disposable `temp/` campaign 下；验证输出为 schema 1、
scenario count 2、`realDeviceEvidence=true`、`verification=passed`。相关 focused backend
回归为 `77 passed`。永久文档保留复验方法和有界事实，不复制 raw target authority。

## 设计取舍与限制

选择 acceptance-only harness 而不是为验收添加产品 API，可复用真实 composition 并
避免把一次性设备控制变成公共能力；代价是操作者仍需准备可信本地 profile 和恢复任务
前置状态。选择独立设备 MediaStore probe，而不是只信 evaluator，避免把 evaluator
实现错误升级成真机成功；代价是任务矩阵固定在可独立观察的相机任务。选择终态重启
non-replay，而不是线程/checkpoint resume，因为当前产品只对已提交 terminal 资源具有
足够确定性。

本证据不支持：宽泛 Android/Harmony 兼容、AndroidWorld/AppAgent 全量成功率、任意
Agent revision、模型质量、统计显著性、自动失败诊断、跨进程设备租约、Studio
multi-Task/repeats/multi-Agent Worker、PostgreSQL、object storage 或 retention/delete。

