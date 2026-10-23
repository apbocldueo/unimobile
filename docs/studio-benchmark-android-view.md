# Studio Benchmark 真实 Android 浏览器验收（Stage 5.6C-2）

本文记录 2026-08-02 完成的 Stage 5.6C-2 真实浏览器验收。C-2 先严格消费已通过的
5.6C-1 summary，再用实际浏览器连接真实 Studio backend，分别创建正例与受控失败
Experiment，并完成 Catalog → Composer → Monitor → Report/Evidence → Replay → Export
闭环。它验证事实呈现和资源连续性，没有改变 Runtime/Worker 语义。

## 前置条件与有界矩阵

C-2 prerequisite receipt 绑定 C-1 canonical summary digest，并要求两个场景、managed
closure、terminal restart non-replay 与 redaction 全部通过后，才允许解析可信 profile、
启动服务或触碰设备。本轮沿用：

- safe profile `stage-5-6-acceptance`；Android、`en-US`、portrait、Camera 可用；
- `zhixing/android-world@1.0.0` / `test` / `AndroidWorld_6`；
- Protocol seed `42`、一个 repeat；
- C-1 同一 positive 与 controlled-negative immutable Agent revisions；
- 每个 Studio Experiment 仍为 1 Agent × 1 Task × 1 repeat。

## 浏览器闭环

```text
C-1 strict receipt
   ↓
Catalog → Composer preview/create → durable Experiment
   ↓                     ↘ immutable Agent revision + safe profile
Monitor (SSE/backfill/refresh) → terminal TaskRun
   ↓
Report + exact Evidence → native Replay reload
   ↓
Export refresh + HEAD preparation → ordinary browser handoff
```

实际浏览器先发现一个有界产品缺口：Composer 只请求 Catalog 前 50 个 task，按稳定排序
位于后一页的 `AndroidWorld_6` 无法被 deep-link 选中。修复将请求提升到后端既有最大
页大小 `100`，没有改变 Catalog DTO、排序、筛选或执行语义，并增加 route test 固定
该合同。随后 Composer 可见 81 个 AndroidWorld task，并按 URL/authoritative ID 选择
目标 task。

## 两条真实浏览器旅程

| 场景 | Monitor / Report | Evaluation | Replay | Export |
|---|---|---|---|---|
| positive | terminal/completed；Agent success；Benchmark PASS | evaluator pass，`INVALID=0` | reload 后仍为 `replay_projection / real_android / false`，read-only | report metadata refresh + exact HEAD 成功；只声称 handoff |
| controlled-negative | terminal/completed；Agent success；Benchmark FAIL | evaluator fail，原因是没有新状态/行；`INVALID=0` | reload 后仍为历史真实来源投影且保持 FAIL | 同样准备 exact report capability；不声称下载完成 |

两条 Report 都执行了显式 `Refresh report`，仍保留独立 service/Agent/Benchmark 轴与
fresh source provenance。Evidence/manifest 只通过 selected Experiment/TaskRun 的 exact
capability 展示；正例包含 report、trajectory、runtime/action/screenshot evidence 与
bundle，受控失败例保留它自己的较小闭包，不从正例借用内容。

## SSE、刷新与非重复执行

两个 Experiment 的 event sequence 均为连续 `1..19`，终态 cursor/high-water 均为
`19/19`。正例在 committed cursor `11` 时刷新并重连，随后 terminal drain 到 `19`；
受控失败例在终态 route reload 后仍重建同一 TaskRun 和 `19/19`。两场景各只有一个
initializer、Agent、evaluator 和 Worker source execution；持久 core event count 在
刷新前后均为 `12`。Monitor、Report 与 Replay 的重新加载没有新增 source/device effect。

## 三类 provenance

UI 使用权威 TaskResult/Replay resource 的三轴事实，而不是从标题、URL、profile、
截图或 artifact 字符串推断：

| 当前资源 | acquisition | environment | realDeviceEvidence |
|---|---|---|---|
| 两个 fresh TaskResult | `fresh_execution` | `real_android` | `true` |
| 对应 native Replay | `replay_projection` | `real_android` | `false` |
| 支持性无设备 fixture | `contract_fixture` | `fake_device` | `false` |

因此“来源环境是真 Android”和“当前页面正在进行新鲜真机执行”是两个独立命题。

## Export 与安全边界

Export drawer 刷新 closed inventory，并对选中的 Experiment report 完成 exact HEAD
准备。页面出现普通浏览器 handoff capability，但本轮没有把“链接已交给浏览器”写成
“下载已完成”、本地持久化、GET 后摘要复核、bundle 复核或新 execution evidence。

最终 ledger 为 `studio-benchmark-android-view-5.6c2-v1`。它保留 7 个 required surfaces、
causal IDs、两条 outcome、cursor、provenance、prepared artifact metadata、console/network
metadata 与固定 claim limits，不保留 raw DOM、response body 或 live object。对 campaign
文件、managed archive 成员和数据库公开文档共扫描 `236` 项，
`privateValuesFound=0`。仅观察到外部 telemetry timeout；Studio 产品请求和页面没有
意外应用错误。服务关闭后临时可信 profile 配置已删除。

## 验证命令与结果

```bash
uv run python scripts/studio_benchmark_android_view_acceptance.py \
  validate <campaign-root>/acceptance-summary.json

npm test -- --run src/pages/benchmarks/benchmarkRoutes.test.tsx

cd studio
npm run typecheck
npm run lint
npm test -- --run
npm run build

PYTHONPATH=.:tests uv run python -m pytest -q
```

账本校验输出为 schema 1、scenario count 2、`realDeviceEvidence=true`、
`verification=passed`。Catalog/Composer focused regression 为 `5 passed`；完整前端为
`89 files / 399 tests`，并通过 typecheck、lint 与 production build；按仓库既有
`PYTHONPATH=.:tests` 约定运行的完整后端为 `921 passed`。

## 设计取舍、失败情况与限制

- 复用 production-composed acceptance server，而不是为验收增加公共 backend mode；
  好处是路径真实，代价是 harness 仍是本地 opt-in 工具；
- 让 URL + Query/resource identity 拥有页面重建事实，而不是浏览器 local buffer；
  好处是刷新可复核，代价是需要严格 stale/cross-owner gate；
- Export 只验证 metadata refresh、HEAD 和 handoff authority，不自动下载大 bundle；
  这样不越过浏览器安全边界，但不证明用户磁盘上的最终文件；
- controlled-negative 必须 Agent 正常完成且 evaluator 明确失败；任何设备/服务错误、
  timeout、cancel、invalid 或证据缺失都不能替代它；
- optional plugin import warning 说明本环境没有安装全部可选插件，不影响所选相机链路，
  也不能被表述为任意 Package 都可运行。

本轮只证明一个明确 Android 虚拟设备、一个 locale/orientation、一个相机 task、两个
Agent revisions 与一次 repeat 的产品闭环；不证明 broad Android compatibility、任意
任务成功、模型质量、自动失败诊断、统计显著性或 Studio Worker 扩容。
