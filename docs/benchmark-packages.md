# Benchmark Package 与公平实验协议

ZhiXing 的 Benchmark 定义层与 AgentGraph 并列：

```text
Agent YAML / SDK       Benchmark JSON / Package       Experiment settings
        |                         |                            |
        v                         v                            v
    AgentGraph               BenchmarkPlan             ExperimentProtocol
```

当前版本既支持 Benchmark 的无设备编译、查询和验证，也支持把
`BenchmarkPlan + ExperimentProtocol + ExecutableAgent` 交给 Experiment Runtime。
`benchmark validate` 仍只证明定义正确；只有 `benchmark run` 的结构化结果与
真实设备证据才能证明某个任务运行成功。

## 五个对象

- `BenchmarkPackage`：可复制或独立安装的内容单元，包含 manifest、任务、
  assets、ground truth、依赖与默认协议。
- `BenchmarkTask`：保留的 V1 JSON 任务模板，负责 instruction、initializer、
  环境声明和 Evaluator Tree。
- `BenchmarkPlan`：Package 或独立 JSON 编译出的纯语义 IR，不包含设备、插件
  实例、secret、绝对路径或随机生成结果。
- `TaskInstance`：运行前按派生 seed 物化的具体任务，包含生成参数、最终
  instruction、reset/setup/cleanup 与绑定后的 ground truth；默认同一 repeat
  跨 Agent 复用。
- `ExperimentProtocol`：公平实验策略，负责 seed、repeats、顺序、预算、设备与
  App 约束、reset、cleanup 和分阶段失败处理。

## Package 目录

```text
my_benchmark/
  benchmark.yaml
  tasks/
    test.json
  assets/
  ground_truth/
  protocols/
    default.yaml
  README.md
```

最小 manifest：

```yaml
schema_version: "1.0"
identity:
  publisher: acme
  name: camera-tasks
  version: 1.0.0
title: Camera Tasks
platforms: [android]
splits:
  test:
    files: [tasks/test.json]
resources: []
ground_truth: {}
apps:
  - id: camera
    platform: android
    package_id: com.android.camera2
    requires_login: false
plugins: []
default_protocol: protocols/default.yaml
```

任务文件仍使用现有 `BenchmarkTask` JSON 数组，不引入第二套 task schema。

## Assets 与 ground truth

Package 中的宿主资源必须在 manifest 声明：

```yaml
resources:
  - id: target-image
    kind: asset
    path: assets/target.png
    media_type: image/png
    sha256: sha256:<64-lowercase-hex>
    size: 12345
```

任务参数使用 `asset://target-image`，不得继续写
`data/AndroidWorld/...`、绝对路径或 `..`。共享 ground truth 使用
`groundtruth://<id>`；较小的 JSON-compatible ground truth 可以 inline。

编译器会阻止绝对路径、路径穿越和符号链接逃逸。完整验证会检查 size 与
SHA-256，但 `benchmark list` 不读取大型资源内容。

## ExperimentProtocol

可从 [default_protocol.yaml](../examples/benchmarks/default_protocol.yaml)
开始：

```yaml
schema_version: "1.0"
seed: 42
repeats: 1
task_order: {strategy: fixed}
task_materialization: {reuse_across_agents: true}
device:
  platform: android
  locale: en-US
  orientation: portrait
  version_policy: compatible
budget:
  max_interactions: 15
  max_activations: 200
  timeout_seconds: 600
isolation:
  reset: before_each_agent
  cleanup: after_each_run
  require_verified_reset: true
```

公平比较默认要求：同一 repeat 的动态任务先物化一次，再向所有待比较 Agent
复用相同 `TaskInstance`。关闭 `reuse_across_agents` 是允许的，但会产生
`benchmark.protocol.unpaired_materialization` 警告。

实际设备 serial、登录凭据、输出目录不属于 Protocol；它们由运行时绑定和
provenance 记录。当前 Runtime 已通过运行时配置执行这些约束；token 使用量不可观测
时会记录
UNVERIFIED，严格协议可以把结果判为 INVALID，而不是把缺失值当作零。

## CLI

源码仓库中的两个首批 Package 需要显式提供 Catalog 根：

```bash
zhixing benchmark list \
  --catalog-root benchmarks \
  --no-installed

zhixing benchmark info zhixing/android-world@1.0.0 \
  --catalog-root benchmarks \
  --no-installed

zhixing benchmark validate zhixing/appagent@1.0.0 \
  --catalog-root benchmarks \
  --no-installed
```

也可以直接验证 Package 目录：

```bash
zhixing benchmark validate benchmarks/android_world --no-installed
```

`list` 是 metadata-only；`info` 读取 manifest 和任务定义；`validate` 进行资源
摘要与完整引用检查。这些命令都不会连接 ADB、执行 initializer/evaluator、导入
Benchmark 插件或调用模型。

运行 Package：

```bash
zhixing benchmark run benchmarks/android_world \
  --split test \
  --task AndroidWorld_6 \
  --agent candidate=examples/graphs/android_content_verified_agent.yaml \
  --serial emulator-5554 \
  --artifact-root temp/benchmarks/androidworld-6 \
  --no-installed \
  --json
```

该 YAML 使用真实模型依赖，需要通过 `--secrets` 提供对应配置。无需模型的项目
验收脚本使用同一个普通 AgentGraph，只把 Reasoning 依赖替换为确定性脚本：

```bash
uv run env PYTHONPATH=. python \
  scripts/run_android_benchmark_acceptance.py \
  --serial emulator-5554 \
  --artifact-root temp/benchmark-android-acceptance
```

预期同时看到 suite `pass=1`、Agent `status=success`、Evaluator `is_pass=true`
和 `independent_media_evidence.added_count=1`。若 preflight INVALID，先检查
`adb devices`、`getprop ro.product.locale`、相机包和设备方向；若 Agent SUCCESS
但 Benchmark FAIL，检查任务 evaluator 的真实 Android 存储语义，不要在 Runtime
按 task ID 硬编码成功。

## Python API

```python
from zhixing.benchmark import (
    BenchmarkCatalog,
    BenchmarkValidationLevel,
    compile_benchmark_package,
    compile_benchmark_suite,
    discover_benchmark_candidates,
)

# 旧 BenchmarkTask JSON 仍可直接进入同一 Plan IR。
standalone = compile_benchmark_suite("examples/benchmark_v1/app_agent.json")
assert standalone.is_success

# Package 编译。
compiled = compile_benchmark_package(
    "benchmarks/android_world",
    split="test",
    validation_level=BenchmarkValidationLevel.RESOURCES,
)
assert compiled.is_success
print(compiled.plan.canonical_hash())

# 显式 Catalog。
candidates = discover_benchmark_candidates(
    catalog_roots=["benchmarks"],
    include_installed=False,
)
catalog = BenchmarkCatalog(candidates)
print(catalog.info("zhixing/appagent@1.0.0"))
```

## 独立分发包

开发期间不要求先构建 wheel。克隆一个仓库后，可以把 Package 目录显式传给
`--package` 或 Python Catalog。

需要安装分发时，使用标准 Python Entry Point：

```toml
[project.entry-points."zhixing.benchmarks"]
camera-tasks = "acme_camera_benchmark.package"
```

`acme_camera_benchmark/package/` 必须作为 package data 包含
`benchmark.yaml` 及其任务和资源。Catalog 通过 Entry Point 元数据与
`Distribution.files` 定位 manifest，不调用 `EntryPoint.load()`，也不导入目标
module。

Git、editable 和 wheel 只要安装到当前 Python 环境，就使用相同元数据协议。
ZhiXing 不会自动下载 Git URL。

## 当前内置 Package

- `zhixing/android-world@1.0.0`：81 个唯一任务。旧源有 82 个数组项，
  `AndroidWorld_72` 完全重复；处理证据位于
  `benchmarks/android_world/migration-report.json`。
- `zhixing/appagent@1.0.0`：45 个任务；源内容核对位于
  `benchmarks/appagent/migration-report.json`。

两个 Package 的 assets 不进入 ZhiXing 核心 wheel。`data/` 和
`examples/benchmark_v1/` 仍保留为旧 Pipeline 与迁移基线。

## 当前边界

当前已实现版本化 task/experiment report、统一 JSONL trajectory、可校验 bundle、
micro/macro 指标、Wilson interval 和 paired comparison；使用与证据边界见
[Benchmark 运行与比较](benchmark-running.md)。这些统计是描述性结果，不自动支持
显著性结论。

仍未完成：

- Studio Benchmark Catalog/Composer、持久 Experiment service、monitor 和 report
  产品闭环；规划合同见
  [Studio Benchmark Experiment 合同](studio-benchmark-experiment-contracts.md)；
- 全部 AndroidWorld/AppAgent 任务的真实 Android 复现；
- 广泛的外部 Benchmark Package/设备/App 版本兼容矩阵；
- 远程 registry、自动下载、签名与进程隔离执行。
