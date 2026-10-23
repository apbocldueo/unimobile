# Benchmark Package 开发

本文描述新版 Benchmark 的最短开发路径。长期边界见
`docs/benchmark-architecture.md`。

## 1. 创建教学 Package

```bash
zhixing benchmark init examples/benchmarks/my-benchmark \
  --name my-benchmark \
  --template minimal
```

模板可选 `minimal`、`dynamic-task` 和 `composite-evaluation`。命令默认拒绝写入
非空目录；`--force` 只应在明确确认生成文件可以被替换时使用。

生成目录包含：

```text
benchmark.yaml
tasks/test.json
protocols/default.yaml
assets/
ground_truth/
README.md
```

`benchmark.yaml` 定义 Package 身份、split、资源和逻辑插件要求；任务 JSON
定义 instruction、initializer、environment、evaluator 和 cleanup；Protocol
定义 seed、repeats、预算、设备约束、隔离与失败策略。

## 2. 无副作用检查

```bash
zhixing benchmark validate examples/benchmarks/my-benchmark --no-installed

zhixing benchmark dry-run examples/benchmarks/my-benchmark \
  --agent candidate=examples/graphs/builtin_android_agent.yaml \
  --json
```

预期观察：

- `validate` 返回 Plan 与 Protocol identity；
- `dry-run` 返回 AgentGraph identity、确定性 schedule、预算、公平性提示和预期
  输出布局；
- 动态任务被标记为尚未执行 materialization；
- 两条命令都不连接设备、不执行 initializer/evaluator，也不创建运行产物。

## 3. fake-fixture Contract Test

```bash
zhixing benchmark contract-test examples/benchmarks/my-benchmark --json
```

Contract Test Kit 使用显式 fake fixture 检查 seeded determinism、initializer、
environment/cleanup、Evaluator V2 适配和安全序列化。输出中的
`real_device_evidence` 必须为 `false`；通过它不代表真实插件、App 或设备已经可用。

## 4. 何时需要写插件

已有 initializer/evaluator 足够时，只写声明和资源。Evaluation Tree 可用
AND、OR、SEQUENCE、THRESHOLD 或 WEIGHTED 组合叶子。只有新的初始化、环境操作
或评估语义无法由已有原子能力表达时，才新增插件；作者不应重写 Agent 循环、
设备调度、报告或统计代码。

正式 Package 放入 `benchmarks/`；小型教学内容放入 `examples/benchmarks/`；
原始外部数据和迁移基线保留在 `data/`，不能作为新版隐式运行入口。
