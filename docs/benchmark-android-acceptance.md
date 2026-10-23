# 真实 Android Benchmark 手工复验

本清单复验后端 Build–Run–Evaluate 与报告链路。它会操作显式 Android 设备、
启动相机并在 PASS 场景拍照；不使用 Studio/frontend。只在可删除的测试设备上
执行，并为每次复验使用新的 artifact root，避免覆盖既有证据。

## 1. 准备环境

在仓库根目录确认解释器、设备和验收参数：

```bash
conda run -n unimobile python --version
adb devices -l
conda run -n unimobile env PYTHONPATH="$PWD" \
  python scripts/run_android_benchmark_acceptance.py --help
```

失败判据：

- `emulator-5554` 未显示为 `device`，或出现 `offline`/`unauthorized`；
- 帮助中缺少六个场景之一；
- 设备不是 Android、不是 `en-US` 或不能切到 portrait；Runtime preflight 会在
  Agent 动作前失败或产生 INVALID；
- 当前相机 UI 的快门中心不是验收命令传入的坐标。仓库保存的成功证据使用
  `--x 540 --y 2052`，坐标不是 Runtime 的通用默认能力。

## 2. 准备外部 distributions

只有 `external-component` 和 `external-package` 场景需要以下安装。先构建并安装
仓库内的独立示例 wheel：

```bash
conda run -n unimobile python -m build --wheel examples/external_component_plugin
conda run -n unimobile python -m pip install \
  examples/external_component_plugin/dist/zhixing_example_components-1.0.0-py3-none-any.whl

conda run -n unimobile python -m build --wheel examples/external_benchmark_plugin
conda run -n unimobile python -m pip install \
  examples/external_benchmark_plugin/dist/zhixing_photo_smoke_benchmark-1.0.0-py3-none-any.whl
```

然后检查 metadata：

```bash
conda run -n unimobile env PYTHONPATH="$PWD" \
  python -m zhixing.cli components doctor \
  --plugin-provider zhixing-example --json

conda run -n unimobile env PYTHONPATH="$PWD" \
  python -m zhixing.cli benchmark info \
  example/photo-smoke@1.0.0 --json

conda run -n unimobile env PYTHONPATH="$PWD" \
  python -m zhixing.cli benchmark validate \
  example/photo-smoke@1.0.0 --json
```

预期：

- doctor 的 provider 为 `zhixing-example`，`passed=true`；
- Benchmark `source_kind=installed`、distribution 为
  `zhixing-photo-smoke-benchmark`、task 为 `PhotoSmoke_1`；
- validate 的 `is_success=true`，Plan 与 Protocol identity 均存在。

任一 provider/package 未发现、合同失败或 identity 缺失时，不要开始真机动作。

## 3. 依次运行六个场景

为本次复验选择新目录：

```bash
export ZHIXING_ANDROID_ACCEPTANCE_ROOT="temp/benchmark-runs/manual-android-acceptance"
```

对下列每个 `<scenario>` 分别运行同一命令：

```bash
conda run -n unimobile env PYTHONPATH="$PWD" \
  python scripts/run_android_benchmark_acceptance.py \
  --scenario <scenario> \
  --serial emulator-5554 \
  --x 540 \
  --y 2052 \
  --artifact-root "$ZHIXING_ANDROID_ACCEPTANCE_ROOT"
```

场景顺序与设备上应观察到的行为：

1. `builtin-sdk-pass`：相机启动、等待预览、点击快门，新增一张照片。
2. `builtin-yaml-pass`：行为同上；摘要中的 Agent hash 应与 SDK 场景相同。
3. `controlled-fail`：Agent 合法返回主屏幕/结束，不点击快门，不新增照片。
4. `paired-comparison`：两个 repeats；verified Agent 各拍一张，控制 Agent 各不拍。
5. `external-component`：设备行为仍是内置拍照链；外部审计节点没有隐式设备能力。
6. `external-package`：Catalog 选择 `PhotoSmoke_1`，相机启动并新增一张照片。

不要只凭相机动画判断成功。每条命令必须退出为零并打印
`"is_expected": true`；否则保留该实验目录并按失败处理。

## 4. 检查摘要和报告

在每个
`<root>/<scenario>/<experiment-id>/acceptance-summary.json` 中检查：

- `counts`：PASS 场景为 1/0/0/0，受控负例为 0/1/0/0，paired 为
  2 PASS/2 FAIL/0 INVALID/0 SKIPPED；
- `identities.agents`：YAML 与 SDK hash 相同；paired 两个 Agent hash 不同；
- `media_store.added_count`：单个 PASS 至少 1，受控 FAIL 为 0，paired 至少 2；
- `artifacts.bundle_verified=true`，且 report/run refs 都是相对路径；
- paired 的 `paired=true`、`matched_count=2`、成功 Agent wins=2、
  `significance_claimed=false`。

读取实验报告、单 run trajectory 和 bundle：

```bash
conda run -n unimobile env PYTHONPATH="$PWD" \
  python -m zhixing.cli benchmark report \
  <experiment-root>/experiment-report.json --json

conda run -n unimobile env PYTHONPATH="$PWD" \
  python -m zhixing.cli benchmark trajectory \
  <experiment-root>/runs/<task-run-id>/trajectory.jsonl --json

conda run -n unimobile env PYTHONPATH="$PWD" \
  python -m zhixing.cli benchmark trajectory \
  <experiment-root>/trajectory-bundle.zip --json
```

报告必须保留 `benchmark_plan_identity`、`experiment_protocol_identity`、
`counts`、`agent_metrics`、`run_summaries`、`comparisons`、
`fairness_warnings` 和 `significance_claimed`。单 run report 必须保留
`task_run_id`、`task_id`、`agent_id`、四类 identity、`outcome`、`stages`、
EvaluationResult V2 和 usage availability。

trajectory 应返回七个阶段：

```text
materialization → reset → setup → evaluator_pre
                → agent → evaluation → cleanup
```

受控 FAIL 的关键判据是 run report 中 agent stage 的
`run_status=success`，同时 evaluation 的 `is_pass=false`、最终
`outcome=fail`；任何 reset/setup/evaluator/cleanup 错误或 INVALID 都不是预期负例。
外部组件 trajectory 还必须包含 `external_audit` 节点的 start/complete，role 为
`example.external.task_run_labeler`，其 run ID 与 task run ID 相同。

## 5. 安全与范围检查

公开 JSON/JSONL 不应包含原始 `emulator-5554`、API key/token/password、live
device/component repr 或宿主绝对 artifact 路径；设备应显示为
`device-sha256:...`。bundle 校验失败、缺少 manifest 成员、绝对引用、原始 serial
或 secret 泄漏均使验收失败。

本矩阵只证明指定 emulator、locale/orientation、相机坐标、AndroidWorld_6、
PhotoSmoke_1、两个已安装示例 distributions 和最多两个 repeats。它不证明全部
Benchmark、真实手机、任意第三方插件、并行设备调度、通用模型能力或统计显著性。
