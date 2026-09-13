# Benchmark 定义层手工验收

以下命令只验证 Package、Plan、Protocol 和 Catalog，不需要 Android 设备。

## 1. 列出首批 Package

```bash
uv run python -m zhixing.cli benchmark list \
  --catalog-root benchmarks \
  --no-installed
```

预期看到：

```text
zhixing/android-world@1.0.0
zhixing/appagent@1.0.0
```

## 2. 查看 Package 信息

```bash
uv run python -m zhixing.cli benchmark info \
  zhixing/android-world@1.0.0 \
  --catalog-root benchmarks \
  --no-installed
```

预期 `task_counts: test=81`、`resources: 11`，并显示 content identity。

## 3. 无设备完整验证

```bash
ANDROID_SERIAL=missing \
uv run python -m zhixing.cli benchmark validate \
  zhixing/appagent@1.0.0 \
  --catalog-root benchmarks \
  --no-installed
```

预期 `valid: true`、Plan/Protocol identity 和
`definition-layer validation only; no task was executed`。命令不会查询
`ANDROID_SERIAL`。

## 4. 验证 Package 搬迁不改变 Plan hash

```bash
tmp_dir="$(mktemp -d)"
cp -R benchmarks/appagent "$tmp_dir/appagent-copy"
uv run python -c '
from zhixing.benchmark import compile_benchmark_package
a = compile_benchmark_package("benchmarks/appagent").plan
b = compile_benchmark_package("'"$tmp_dir"'/appagent-copy").plan
assert a and b
print(a.canonical_hash())
print(b.canonical_hash())
assert a.canonical_hash() == b.canonical_hash()
'
```

预期打印两个完全相同的 `sha256:` identity。

## 5. 验证资源篡改可检测

只在临时副本中操作：

```bash
tmp_dir="$(mktemp -d)"
cp -R benchmarks/appagent "$tmp_dir/appagent-copy"
printf 'tamper' >> "$tmp_dir/appagent-copy/assets/profile.jpg"
uv run python -m zhixing.cli benchmark validate \
  "$tmp_dir/appagent-copy" \
  --no-installed
```

预期非零退出码，并出现 `benchmark.resource.size_mismatch` 和/或
`benchmark.resource.digest_mismatch`。原 Package 不会被修改。

## 6. 确认旧 JSON 仍可编译

```bash
uv run python -c '
from zhixing.benchmark import compile_benchmark_suite
r = compile_benchmark_suite("examples/benchmark_v1/app_agent.json")
assert r.is_success and r.plan
print(len(r.plan.tasks), r.plan.canonical_hash())
'
```

预期任务数为 `45`。原 `load_benchmark_json` 与旧 `BenchmarkPipeline` 仍保留。

## 已知限制

- 上述成功只证明定义、资源和 identity 合同成立；
- 这些 `list/info/validate` 命令本身不执行已经实现的
  `BenchmarkExperimentRuntime`，也不运行 initializer、AgentGraph、evaluator 或
  cleanup；
- 因此本页命令没有产生新的真实 Android trajectory，不能据此报告 Benchmark pass
  rate；Experiment Runtime、报告与已有代表性 Android 证据应分别按
  [Benchmark 运行与比较](benchmark-running.md)和
  [真实 Android Benchmark 手工复验](benchmark-android-acceptance.md)验证；
- Studio Benchmark Experiment API、持久 service 与页面仍属于 Stage 5 规划，合同见
  [Studio Benchmark Experiment 合同](studio-benchmark-experiment-contracts.md)。
