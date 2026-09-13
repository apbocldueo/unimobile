# 通用 Agent 控制流后端验收

本阶段只验收后端控制流，不涉及 Studio、真实 Android、Benchmark、外部 wheel 插件发现或自动失败诊断。核心目标是：范式不再由新的 `Agent.step()` 子类或 Runtime 分支定义，而由同一个 AgentGraph 1.1 和 GraphExecutionKernel 表达。

## 1. 查看六种范式

```bash
python - <<'PY'
from zhixing.graph import PARADIGM_TEMPLATES

for name, template in PARADIGM_TEMPLATES.items():
    graph = template.build()
    print(name, graph.validate_graph().is_valid, graph.canonical_hash())
PY
```

预期看到六个 `True`：`modular`、`reflection`、`react`、`planner_and_execute`、`uground`、`multi_agent`。每个模板都是普通 AgentGraph；Kernel 不读取这些名称。

## 2. 直观看 Router、State、Loop、Subgraph

```bash
python -m examples.generalized_agent_graph_no_device
```

预期：

- ReAct 在同一个 run 中执行两次 local tool iteration，`interaction_steps` 仍为 0；
- Planner-and-Execute 写入显式 plan state，执行两次子图迭代，再由 action service 产生 1 个 interaction step；
- 输出中能看到 `plan_iterator/execute_step` 等层级 node path。

可直接查看 YAML 结构：

```bash
python - <<'PY'
from zhixing.graph import load_graph_yaml

result = load_graph_yaml("examples/agent_graph/react_loop_v11.yaml")
print(result.is_success)
print(result.graph.canonical_hash())
PY
```

## 3. 验证组件替换不改变拓扑

调用 `bind_execution_plan(graph, components)` 时，`components` 是显式的候选名到实例/工厂的映射。把某一候选替换为另一个实现，再运行相同 `graph.canonical_hash()`；图身份不因运行时实例改变。若需要改变组件参数或候选声明，应修改 `ComponentBinding`，此时 canonical hash 会变化。

扩展契约通过显式 `NodeContractCatalog` 和 `InvocationAdapterRegistry` 注入。当前阶段不会扫描 entry point；安装后自动发现属于外部插件里程碑。

## 4. 查看层级事件

```bash
python - <<'PY'
from examples.generalized_agent_graph_no_device import run_planner_execute

print(run_planner_execute()["event_paths"])
PY
```

每个真正执行的节点都会产生 `start` 与 `complete` 或 `fail`；事件包含：

- 兼容字段：`node_id`、`step`；
- 新字段：`node_path`、`activation_id`、`parent_activation_id`；
- 循环字段：`loop_path`、`loop_iteration`；
- 设备动作语义：`interaction_step`。

Router 额外产生 `router_selected`，State 产生 `state_transition`，Loop 产生 `loop_enter`、`loop_iteration`、`loop_exit` 或 `loop_exhausted`。事件只保存结构摘要，不把组件、服务或 secret 对象序列化进去。

## 5. 验证旧 V1 不回归

```bash
python - <<'PY'
from tests.graph.helpers import make_golden_graph

graph = make_golden_graph()
print(graph.canonical_hash())
print(graph.model_dump(mode="json")["policies"])
PY
```

预期 hash 固定为：

```text
sha256:3cadf8a4ec2a556bcfe025cb1649e3f24ae7e03eed36f399133bfca8f8638e83
```

旧 `GraphRuntime.run(...)`、`ModularAgent` 和 `AgentRunner` 仍可用。`GraphRuntime` 现在是兼容 facade，经 GraphExecutionKernel 的 compatibility plan 边界执行原有 mobile scheduler。

## 6. 确认旧策略编译边界

`modular_agent` 的旧 AgentConfig 编译路径已经有 V1 行为回归，因此继续启用。`reflection_agent`、`uground_agent` 和 `multi_agent` 的旧策略包含各自的历史状态/摘要/缓存细节，目前仍返回稳定 `graph.compile.unsupported` 并继续走旧 AgentFactory/Runner；不能把“新的 fake 范式模板可运行”冒充为“旧策略已完成行为等价迁移”。

## 7. 运行自动化验收

```bash
python -m pytest -q tests/graph tests/runtime
python -m pytest -q tests
python -m compileall -q zhixing examples/generalized_agent_graph_no_device.py
```

本阶段完成时的真实记录：

- Graph + Runtime 定向测试：`81 passed`；
- 正式 `tests/`：`190 passed`；
- wheel/sdist 构建和仓库外隔离安装包含 AgentGraph 1.1 与顺序 Multi-Agent fake 执行，已通过。

## 当前边界

- 六种模板证明的是控制语义和组合能力，不证明真实 Mobile Agent 成功率。
- 尚未连接真实 Android Observation/Action services。
- 尚未让 BenchmarkTask 使用新 Kernel。
- 尚未实现外部插件自动发现、Contract Test Kit 或 Studio。
- Multi-Agent 当前仅为确定性顺序 Manager/Operator/Critic，不支持并行、分布式或多个设备动作竞争。
- 旧 Reflection/UGround/MultiAgent 仍走旧执行路径；它们的模板迁移必须先完成真实 typed component parity。
