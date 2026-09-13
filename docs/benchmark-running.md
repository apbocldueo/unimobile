# 运行、比较与检查 Benchmark

## 运行

```bash
zhixing benchmark run benchmarks/android_world \
  --split test \
  --task AndroidWorld_6 \
  --agent candidate=examples/graphs/builtin_android_agent.yaml \
  --serial emulator-5554 \
  --artifact-root temp/benchmark-runs \
  --json
```

真实运行前必须显式选择在线设备，并准备 Agent 所需的 runtime secrets。定义校验、
Agent 绑定和 Protocol 检查在设备副作用之前完成。正常执行顺序为：

```text
materialize → reset → setup → evaluator pre-hook
            → AgentGraph Runtime → evaluation → cleanup → reporting
```

Agent 的 RunStatus 与 Benchmark 的 PASS/FAIL/INVALID/SKIPPED 是不同事实：
Agent 成功结束不自动等于 Benchmark PASS；初始化、评估或清理基础设施失败也不能
伪装成 Agent 失败。

## 输出

默认布局为：

```text
temp/benchmark-runs/<experiment-id>/
  experiment-manifest.json
  experiment-result.json
  experiment-report.json
  runs/<task-run-id>/
    benchmark-result.json
    run-report.json
    trajectory.jsonl
  trajectory-bundle.zip
```

所有公开文件经过同一递归 sanitizer；device serial 使用不可逆摘要，secret、主机
绝对路径和 live object 不得进入报告。manifest 和 bundle 使用内容哈希保护完整性。

```bash
zhixing benchmark report \
  temp/benchmark-runs/<experiment-id>/experiment-report.json --json

zhixing benchmark trajectory \
  temp/benchmark-runs/<experiment-id>/runs/<task-run-id>/trajectory.jsonl --json

zhixing benchmark trajectory \
  temp/benchmark-runs/<experiment-id>/trajectory-bundle.zip --json
```

## 公平比较

同一实验中的 Agent 应共享 BenchmarkPlan、ExperimentProtocol、设备/App 约束、
seed、重复次数、预算和 reset/cleanup 规则。动态 TaskInstance 只有在 Protocol
允许时跨 Agent 复用。报告中：

- PASS/FAIL 构成 success rate 的 eligible denominator；
- INVALID/SKIPPED 单独计数，不转成 Agent loss；
- micro 与 macro success rate 同时保留；
- 方差仅在至少两个样本时提供；
- 只有 TaskInstance 与 Protocol 条件匹配时才标记 paired；
- Wilson interval 是描述性不确定性，不代表统计显著性。

Trajectory 用于人工定位 materialization、环境、Agent、evaluation 或 cleanup 的
失败阶段。当前框架不宣称自动失败诊断。

## Studio 显式 Android Profile

Studio server 不再把 `serial=None` 交给 Runtime，也不根据“唯一在线设备”隐式选取
Android。需要运行 Studio Run 或 Benchmark Experiment 时，部署者必须在受信任的
本地 JSON 中显式配置 exact ADB serial：

```bash
cp examples/device-profiles.example.json /path/to/private-device-profiles.json
# 在私有副本中把 emulator-5554 替换为明确选择的 exact adb serial，且不要提交它。
python -m zhixing.studio serve \
  --device-profile-config /path/to/private-device-profiles.json
```

也可设置 `ZHIXING_STUDIO_DEVICE_PROFILE_CONFIG`；CLI 参数优先。未配置时 profile
directory 是空列表，所有无设备资源仍可读取，新设备执行则 fail closed。浏览器和
公开 API 只能看到安全 `deviceProfileId`、label、platform 与 configured 状态，不能
读取 serial、配置路径、private fingerprint、target key 或 live device。

配置加载只做 bounded JSON 校验，不调用 ADB。exact serial readiness、session 构造、
取消检查和 target-level lease 都在真正执行前完成；platform、locale、orientation、
required App 和 Protocol 仍由 Core Runtime 检查。安全停用时移除 CLI/环境变量并
重启服务即可。schema 11 数据库若需要回滚到旧二进制，应恢复升级前备份或换新
workspace，而不是手工删除私有 binding 表。

这套 Studio profile 配置与本页开头 `zhixing benchmark run --serial ...` 的直接 CLI
入口是两个不同边界：直接 CLI 仍要求操作者显式提供 serial；Studio 则用安全公开
profile + 服务端私有 binding 保持 durable Experiment 重启一致性。完整合同、验证
证据和限制见
[Studio Benchmark Android Profile 与证据来源](studio-benchmark-android-profile.md)。

## 真实 Android 验收

仓库提供后端验收脚本 `scripts/run_android_benchmark_acceptance.py`。它接受显式
`serial`、场景、快门坐标、重复次数和 artifact root，不依赖 Studio/frontend，
也不回退到旧 `AgentRunner`。当前场景为：

| 场景 | 验证边界 | 预期结果 |
| --- | --- | --- |
| `builtin-sdk-pass` | SDK 构造的内置 content-verified Agent | Agent SUCCESS、Benchmark PASS、MediaStore `added_count >= 1` |
| `builtin-yaml-pass` | 与 SDK canonical hash 相同的 YAML Agent | Agent SUCCESS、Benchmark PASS、MediaStore `added_count >= 1` |
| `controlled-fail` | 合法提前结束但不拍照的控制 Agent | Agent SUCCESS、Benchmark FAIL、INVALID=0、MediaStore `added_count=0` |
| `paired-comparison` | 两个不同 canonical hash、两个 repeats | 2 PASS、2 FAIL、paired、`matched_count=2`、成功 Agent 两次胜出 |
| `external-component` | 已安装 `zhixing-example-components` 的外部审计节点 | 外部节点 start/complete、任务 PASS、MediaStore 新增 |
| `external-package` | 已安装 `example/photo-smoke@1.0.0` Package | Catalog 发现的外部 Plan 进入统一 Runtime 并 PASS |

在项目根目录、`unimobile` 环境中运行单个场景：

```bash
conda run -n unimobile env PYTHONPATH="$PWD" \
  python scripts/run_android_benchmark_acceptance.py \
  --scenario builtin-sdk-pass \
  --serial emulator-5554 \
  --x 540 \
  --y 2052 \
  --artifact-root temp/benchmark-runs/android-acceptance
```

脚本只有在场景断言全部成立后才返回零，并把安全摘要写入：

```text
temp/benchmark-runs/android-acceptance/<scenario>/<experiment-id>/
  acceptance-summary.json
  experiment-manifest.json
  experiment-result.json
  experiment-report.json
  runs/<task-run-id>/
    benchmark-result.json
    run-report.json
    trajectory.jsonl
  trajectory-bundle.zip
```

`acceptance-summary.json` 应检查 `scenario`、`counts`、`is_expected`、
`identities`、`media_store.added_count`、`artifacts.bundle_verified` 和
`comparisons`。受控 FAIL 不是脚本失败：它的验收通过条件正是 Agent 阶段
`run_status=success`、evaluation `is_pass=false`、最终 `outcome=fail`。

2026-07-25 保存的代表性证据位于
`temp/benchmark-runs/android-acceptance/`。内置 SDK/YAML、外部组件和外部 Package
均各有一条 PASS 摘要；受控负例为 1 FAIL/0 INVALID；paired comparison 为
2 PASS/2 FAIL、`matched_count=2`、`significance_claimed=false`。这些结果只证明
`emulator-5554`、英文 locale、portrait orientation、相机任务、上述 Package/
AgentGraph 和 repeats 的组合，不代表全部 AndroidWorld/AppAgent、任意设备、
任意外部插件或通用模型能力已经通过。

完整的逐步设备观察、报告字段和失败判据见
[真实 Android Benchmark 手工复验](benchmark-android-acceptance.md)。
