# AgentGraph V1

AgentGraph 是 ZhiXing 的后端执行语义中间表示。Python 模型、图原生 YAML、Studio FlowDocument，以及受支持的旧 AgentConfig V1 都先编译为同一种图；BenchmarkTask JSON 仍独立描述任务初始化和评估，不进入 AgentGraph。

## 六类核心角色与 Studio 能力层

`perception`、`planner`、`reasoning`、`memory`、`action_executor`、`verifier` 是面向 Agent 架构的六类角色。LLM、Grounder 是组件依赖，Device 是未来 Runtime 服务，Initializer/Evaluator 属于 Benchmark 生命周期。`Action` 是数据，`ActionExecutor` 才是执行动作的组件。

Studio schema 3 不把完整 AgentGraph 原语直接暴露给作者。它只展示系统提供的 Input、
Output、六类核心能力，以及 Catalog 批准的 Grounder/Tool 扩展；具体实现、版本、fallback、
config 和 dependency 在 Inspector 编辑。DeviceObserve、ActionRequest、runtime
ActionExecutor、terminal predicate、Router/State/Loop/Subgraph 等执行胶水由后端按
`studio.mobile-agent-lowering@1` 确定性生成，并用 projection map 投影回能力节点。
这是一层 Studio 产品策略，不收窄 Python/YAML 的低层 AgentGraph 合同。

稳定数据类型为 `task_input`、`device_observation`、`plan_result`、`perception_result`、`memory_context`、`action`、`action_result`、`verifier_result`、`control` 和 `run_result`。后端 `zhixing.graph.port_catalog_payload()` 是端口契约的唯一来源。

## Python 与 YAML

Python 可以直接构造 `AgentGraph`，然后调用 `validate_graph()`、`canonical_mapping()`、`canonical_json()` 和 `canonical_hash()`：

```python
from zhixing.graph import load_graph_yaml

result = load_graph_yaml("examples/agent_graph_v1.yaml")
if not result.is_success:
    raise ValueError(result.to_safe_dict())

graph = result.graph
print(graph.canonical_hash())
```

图原生 YAML 使用独立 envelope：`kind: agent_graph`、`schema_version: 1`、`contract_version: "1.0"`。旧 Agent YAML 仍由 `load_agent_yaml()` 返回 `AgentConfig`；`compile_agent_config()` 只是新增的兼容编译边界，不改变旧 factory/runner 输入。

## 节点、条件与反馈

V1 支持 `component`、`input`、`condition`、`output` 节点，以及 `data`、`control`、`feedback` 边。条件必须是结构化 Predicate，不接受表达式或脚本。普通 data/control 子图必须无环；反馈只能由显式 feedback edge 表达，必须声明 1..10 次上限和耗尽策略。V1 拒绝嵌套或重叠反馈环。

节点逻辑 ID、组件候选及顺序、生命周期、边、条件、反馈和 policies 进入 canonical hash。Studio canvas ID、坐标、图标、标题和时间不进入 hash；相同 Agent 的 Python、YAML、Studio 定义因此产生相同 `sha256:<hex>`。

## 当前边界

AgentGraph 1.1 已用于通用 Graph Runtime、Studio 普通 Run 和 Studio Benchmark 执行路径；
旧 `ModularAgent`、`AgentRunner`、AgentConfig YAML 与独立 BenchmarkTask JSON 入口继续保留。
Studio schema 3 的能力编译已用 deterministic fake device 验证标准显式
observe→reason→act→feedback 闭环，但这不证明任意范式、任意 Android 任务或广泛设备兼容性。
复杂范式只有在代表性低层图无需 Kernel 范式分支并成功执行后，才可声明受支持。
