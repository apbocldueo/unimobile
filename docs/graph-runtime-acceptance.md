# AgentGraph Runtime 阶段验收指南

本指南只验收里程碑 B：Graph Runtime。它不需要 Android 设备、模型或 API key，也不代表 Studio 实时界面、Benchmark Runtime 或真实 Android 端到端已经完成。

## 1. 运行无设备完整示例

在仓库根目录执行：

```bash
python -m examples.agent_graph_runtime_no_device
```

预期现象：

1. 首先打印 AgentGraph 的 `canonical_hash`。
2. `planner` 只在运行开始执行一次。
3. step 0 依次出现 perception、reasoning、action_executor、verifier。
4. 第一次 verifier 失败后出现 `feedback_latched`，目标步骤为 step 1。
5. step 1 重新执行 perception，说明 Runtime 重新观察和感知，而不是在旧截图上原地循环。
6. 最终 `run_result.status` 为 `success`。

## 2. 观察节点事件配对

检查示例输出中的每个实际节点调用：

```text
start → complete
```

失败节点应为：

```text
start → fail
```

事件中应能看到 `step`、`node_id` 和严格递增的 `sequence`。未激活控制分支只产生可选的 `node_skipped`，不会伪造 start/complete。

## 3. 分别验证四种图语义

```bash
python -m pytest -q \
  tests/runtime/test_graph_runtime.py \
  tests/runtime/test_runtime_contract.py
```

重点对应关系：

- 顺序图：`test_minimal_graph_reobserves_until_explicit_done_and_preserves_context_identity`
- 可选节点：最小图不包含 Planner、Memory 和 Verifier，仍可执行
- 条件节点：`test_condition_false_without_feedback_returns_failure`
- 反馈边：`test_feedback_is_cross_step_reobserves_and_has_priority_over_output`
- 反馈上限：`test_feedback_exhausted_policies_are_normalized`
- 非激活分支与 deadlock：`test_inactive_control_branch_emits_skip_without_fake_start_event`

## 4. 验证 ActionExecutor 设备边界

```bash
python -m pytest -q \
  tests/runtime/test_graph_runtime.py::test_observation_and_action_device_failures_have_distinct_status \
  tests/runtime/test_runtime_contract.py::test_graph_runtime_source_never_calls_legacy_runner_mapping
```

预期结果：Graph Runtime 只把 Action 交给图中绑定的 ActionExecutor，不调用 `AgentRunner._execute_on_device`。ObservationProvider 失败映射为 `DEVICE_FAILURE`。

## 5. 验证三种定义进入同一 Runtime

```bash
python -m pytest -q \
  tests/runtime/test_runtime_contract.py::test_python_yaml_and_studio_graphs_use_the_same_runtime_trace
```

该测试会将 Python、Graph YAML 和 Studio FlowDocument 编译为 canonical hash 相同的 AgentGraph，然后断言节点顺序、条件选择与 RunStatus 相同。

## 6. 验证旧 ModularAgent 兼容路径

```bash
python -m pytest -q tests/runtime/test_legacy_regression.py
```

预期结果：旧 `ModularAgent.reset()/step()` 和 `AgentRunner.run()` 均继续工作。当前阶段采用新旧旁路共存，不强制迁移未支持的旧 Agent。

## 7. 当前阶段的明确边界

- 已完成：fake device 上的 Graph Runtime 语义、RuntimeContext、ActionExecutor 边界、RunEvent、RunResult、旧路径兼容。
- 尚未完成：真实 Android provider/executor 验收、Studio 实时运行和节点高亮、BenchmarkTask 迁移、完整 RunReport/Trajectory 下载。
- 不提供：自动失败诊断。当前结构化事件和运行结果仅提供可审计证据，失败仍由用户人工定位。
