# 简洁的 AgentGraph YAML

用户编写组件配置和连接，编译器负责展开 IR 的固定包装。需要自定义连接、状态、
Router 或 Loop 时使用这里的 schema-1 写法；标准 mobile_vlm 的 schema-2 入口
继续保留。六大角色、设备边界、BenchmarkTask JSON 和执行内核均未改变。

## 组件与连接

```yaml
kind: agent_graph
schema_version: 1
nodes:
  input: {kind: input}
  observe:
    component: zhixing.runtime:device_observe
    contract: {id: zhixing.service.device_observe, version: '2.0'}
  perception:
    component: agent.perception:screenshot_perception
  output: {kind: output}
edges:
  - input.value -> observe.request
  - observe.observation -> perception.observation
  - perception.perception -> output.result
```

这是观察和感知子图，不是完成手机任务的 Agent。完整在线例子见
[`autodroid_online.yaml`](../examples/graphs/autodroid_online.yaml)：它显式组合
Perception、Memory、Reasoning 与共享观察/动作服务，并保留 Loop 和跨轮 State。
Planner、Verifier 不参与这一在线策略，无需为凑齐六类而声明空节点。

组件参数直接写 `params`，依赖直接写 `dependencies`，可选组件版本写 `version`。
`component: agent.reasoning:autodroid_reasoning` 只展开为一个普通候选，不会调用
专用 Agent 工厂。第三方组件同样可以使用完整命名空间，并显式指定 `role` 或
`contract`。多候选 fallback 仍使用原来的完整 `component: {policy, candidates}`。

## 可以省略哪些字段

| 字段 | 简洁写法的默认值 |
| --- | --- |
| 节点 `id` | `nodes` 中的键 |
| `kind` | 有且仅有 component/router/state/loop/subgraph 之一时取对应类型 |
| `contract_version` | 命名节点图为 `1.1`；旧节点数组格式保留原来的默认值 |
| `role` | 未显式指定 role/contract 时，从六种准确的 `agent.<role>` 命名空间推导 |
| `lifecycle` | input 为 on_run_start，output 为 terminal，state 为 stateful，其余为 per_step |
| 绑定 `policy` | single；组件字符串自动包装为单个候选 |
| 空 params/dependencies/metadata | 空对象 |
| `primary` | false；主动作执行节点需要显式写 true |
| 普通连线 `kind` | data；control/feedback 必须显式声明 |
| GraphPolicies | 沿用现有默认值：15 次交互、10 次 feedback、1000 次激活、8 层嵌套 |

Memory 组件若采用 stateful 生命周期，仍须显式声明；角色不改变生命周期。
LLM 模型与连接参数也不由编译器猜测。AutoDroid 的 request_timeout=45 和
max_retries=0 是显式策略选择，保留在依赖配置中。

Loop/Subgraph 的端口映射、终止 Predicate、次数和非默认激活预算继续按现有
AgentGraph 合同声明；不从连线猜测循环，也不加入 AutoDroid 专属默认值。
可以用标准 YAML anchor 复用重复预算、端口映射或 State 配置。

## 复用状态机调度胶水

图作用域可以用 `machine` 替代该作用域的 `nodes` 和 `edges`。它是编译期
简写，展开后仍是普通 State、Router、Component 和连线；不会增加执行内核分支，
也不选择某个 Agent 预设。可运行例子见 [`appagent.yaml`](../examples/graphs/appagent.yaml)，
其简化前后 canonical hash 完全相同。其余八份迁移配置随后也已逐项简化、逐项
验证，复用相同编译器而未增加运行适配；见 [九项简化记录](legacy-agent-yaml-simplification.md)。

`machine` 必须显式声明：

| 字段 | 含义 |
|---|---|
| `state` | `key`、`data_type`、`scope`；生成匹配的 read/write，采用既有 replace 策略、初值 null |
| `selector` | 从 frame 中选择当前阶段的字段；也作为 transition 的目标参数名 |
| `outcome` | 阶段结果中的分支字段 |
| `resume`、`transition`、`merge` | 完整的组件节点声明；可以绑定调用者自己的适配组件和合同 |
| `stages` | 阶段与分支去向；键为稳定阶段名，`next` 映射 outcome → 阶段名或显式退出值 |

可选 `exits` 默认 `[]`，声明至多128个非空、互异且不与阶段名重叠的退出值。
例如 `exits: [finish]` 允许分支写 `next: {complete: finish}`，转移后返回该 frame；
**退出仍由父级 Loop 的显式终止条件决定**，不会生成一个隐藏的 finish 操作。
可选 `transition_prefix` 默认空字符串，用于保留已有转移节点名称，例如 `go_`。
它不改变端口约定；生成后的名字冲突仍会被拒绝。Agent-SAMA 的
当前配置 (not bundled in the core source) 使用这两个字段，
从407有效行简化至157，canonical graph与旧配置完全相同。
后续通过既有YAML anchor/merge共享重复参数，当前为138有效行；编译器不再改动。
参数保留理由与验证见Agent-SAMA参数核查 (not bundled in the core source)。

适配端口约定为：resume 接收 `initial`/`previous`，transition 接收 `value`，
merge 接收多值 `values`，三者均输出 `result`，并支持可选 `control`。transition
根据显式的 selector 参数生成新 frame；merge 必须处理所选分支，不能隐藏下一步
调度。AppAgent 复用既有 workflow_state 操作；编译器不导入其实现。

普通阶段包含 `node` 和 `next`：单节点接收 `value`，以 `control` 门控，输出
`result`。例如 AppAgent 的验证阶段直接声明
`next: {continue: select, correction: execute}`，修改去向会改变执行图。

复合阶段声明 `nodes`、`inputs`、`entry`、`output`、`edges` 和 `next`。
`inputs` 列出共享 frame 的接收端，`entry` 指定控制入口，`output` 指定结果端。
其内部 `edges` 使用阶段内的 `node.port -> node.port` 数据边。AppAgent 的观察和
执行阶段保留独立原生设备服务与请求/确认连线，设备副作用仍经过 Runtime 边界。
不适合这个端口约定的流程可以继续使用完整命名节点图；没有强制迁移其他图。

编译器生成 input/output、read/write、resume、dispatch、每阶段 Router、每分支
transition 和 merge，拒绝名字冲突、未知字段、缺失阶段、跨阶段内部连线和歧义
端点。生成节点/边保留指向原阶段或分支的 SourceMap；端口和类型继续由 IR 校验。
支持 1–128 阶段、每阶段 1–128 outcome；复合阶段至多 128 节点和 1024 条内部边。
未知 outcome 走 `unrouted`，不自动选择某个分支。

`machine` 只表达一次阶段调用与转移，不隐式创建循环。父级 Loop 的终止条件、
次数、端口映射和激活预算仍显式声明。AppAgent 的 500 次操作上限、run State、
22 条分支、LLM 依赖与所有 native 设备边界均保留。

本次 AppAgent 从 256 行减少到 80 行；旧版选类配置仍为 37 个有效行。新增共享
展开器为 124 Python SLOC，既有编译器改动涉及 33 SLOC；本轮净增加 145 SLOC，
并不把通用代码计作零成本。完整口径与验证见 [AppAgent 记录](appagent-yaml-simplification.md)。
后续八项复用这些既有代码，无运行/编译适配增量；新增可选离线折叠工具为 120
SLOC。九份简洁 YAML 当前合计 698 有效行，最新计量见九项简化记录。

以上代码量是九项简化时的快照。随后Agent-SAMA补充通用退出值/名称前缀，展开器
124→133 SLOC，离线折叠工具120→132；其他九份配置和执行内核均未改。
具体增量、源码快照和验证见 Agent-SAMA简化记录 (not bundled in the core source)。

## 条件与校验

普通连接用字符串；有条件或控制类型的边用对象：

```yaml
- {source: begin.ready, target: previous.control, kind: control}
- source: previous.value
  target: memory.write
  condition: {field: status, operator: exists}
```

节点名和端口名都允许点号。若 `a` 与 `a.b` 同时存在，`a.b.value` 有歧义，必须
写完整地址：`source: {node: a.b, port: value}`。编译器不会凭顺序选择。
未知字段、错误端口、错误类型和明文密钥仍由既有严格合同拒绝。

```bash
conda run -n unimobile python -m zhixing.cli agent validate examples/graphs/autodroid_online.yaml
conda run -n unimobile python -m pytest tests/graph/test_compact_yaml.py tests/runtime/test_autodroid_online.py tests/packaging/test_autodroid_install.py -q
```

预期校验成功，图 hash 与 SDK 一致；测试用确定性模型和 fake Android 执行。
编译只展开和校验图，不读 App Memory、不加载组件或模型、不连接设备。
安装验收从仓库外读取简洁 YAML，再执行 TAP → TEXT → BACK → DONE。
这些证据不代表真实模型、真实设备或原论文任务成功率。

## 代码量口径

旧的 322 行快照保留在 `output/loc/autodroid-20261019/final/`。
新 YAML 为 77 行；这是实际作者格式变化，不是将多行文本存成字符串或调用
AutoDroid 预设。新增的通用展开器单独计量，不能因为组件可复用就声称其没有成本。
Agent 专属 Python、外置提示词、YAML 与通用框架成本应分列报告。

本轮快照 `output/loc/autodroid-20261019/concise-yaml-1/` 中，Agent 专属 Python
仍为 654 SLOC，YAML 为 77 行，外置提示词为 16 个非空行；混合材料合计 747 行。
通用展开器另计 140 Python SLOC，公共 YAML 入口的增量另以 diff 留存。
本轮 178 项相关检查通过，覆盖图合同、运行回归、包资源和安装后 YAML 执行。
