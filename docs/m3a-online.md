# M3A 完整在线执行

本次实现由用户授权，Coding Agent 完成源码提取、组件、AgentGraph、YAML、测试和
文档。目标是固定 AndroidWorld 提交
`f8e78c0ab0bb8b5daa681afd0296ed0193a98f1f` 的 M3A 在线逻辑。
官方入口为 `run.py` 的 `m3a_gpt4v`，外层循环为
`android_world/episode_runner.py:run_episode`，单轮为 `agents/m3a.py:M3A.step`。
M3A 与既有 AndroidWorld Benchmark 属于同一个官方 GitHub 来源；新增 Agent 工作流
样本不会增加一个独立仓库，后续论文统计需要保持这一去重边界。

**已完成的是：生产 AgentGraph 在替身模型/环境下执行，以及所覆盖路径与未改动的
官方定义对照。尚未运行真实 AndroidWorld 模拟器或真实模型 API，不宣称真实任务
成功率、任意设备兼容性或形式化的全部输入等价。**

后续 LOC 审计（2026-10-22）：官方在线核心 **841 Python SLOC**，提取新增装配
**28 Python SLOC**，实际执行单文件合计 **869**；精简后的当前 YAML **72 行**
（首次统计为 89 行，原快照保留）。精简仅删除默认字段、复用重复声明及按阶段合写连接，
编译得到的完整 AgentGraph 不变；行数下降不等于删除了对应数量的 Agent 逻辑。
24 组隔离单文件与实际 YAML 对照通过。专用组件、适配和原算法封装另列，72 行
仅表示已有组件且环境依赖已绑定后的图配置量。完整口径、产物和复现命令见
M3A LOC 报告 (not bundled in the core source)及
YAML 精简复验 (not bundled in the core source)。
精简后另跑 M3A、简洁 YAML 合同和干净 wheel 在线验收，合计 67 项通过。

## 组件和文件

| 位置 | 职责与复用 |
| --- | --- |
| `zhixing/m3a.py` | 纯构图工厂；普通 Loop、State、Router 和显式连接 |
| `examples/graphs/m3a_online.yaml` | 可编辑组件与连接；默认图与 Python 工厂具有同一 canonical hash |
| `zhixing/graph/m3a_contracts.py` | 独立调度的类型化阶段合同；不增加图角色 |
| `zhixing/plugins/agent/m3a/perception.py` | 原始 UI 描述、SoM、方向/边界坐标转换和截图副本 |
| `zhixing/plugins/agent/m3a/reasoning.py` | 独立的动作选择与总结节点，各调用模型一次 |
| `zhixing/plugins/agent/m3a/execution.py` | 显式观察、reset、执行和可选环境终止钩子 |
| `zhixing/plugins/agent/m3a/environment.py` | 绑定调用者提供的官方 AsyncEnv，复用其完整动作执行 |
| `zhixing/plugins/agent/m3a/memory.py` | 纯数据适配、分支合并、轮次和结果发布 |
| `agent.memory:sliding_window_memory` | 原样复用；窗口覆盖整个 episode，保存精确 TEXT 总结 |
| `zhixing/plugins/llm/m3a_llm.py` | 惰性复用官方 Gpt4Wrapper，不改其传输、JPEG、采样和重试策略 |
| `zhixing/plugins/agent/m3a/source.py` | 选取官方 UI/标记、提示词、解析和 JSONAction 算法，不包含 Agent 循环 |
| `source-origin.json`、`tests/fixtures/m3a/` | 固定来源、原文件哈希、选取定义及未修改的测试对照源码 |

活跃能力家族为 Perception、Reasoning、Memory、ActionExecutor。原版没有独立
Planner 或结构化 Verifier，图没有增加这些调用。总结保留为 Reasoning 的第二个
操作，输出文本供 Memory 使用，没有引入额外判定、回退或恢复策略。

没有修改执行内核、旧 Agent、BenchmarkTask JSON 或 Benchmark 架构。
现有通用 SoM、通用 Reasoning 和反思 Verifier 的算法规则与原版不同，本实现复用
它们的公共合同/依赖机制，而不是用相近算法替代。官方设备动作、文本输入、App
名称解析由显式 AsyncEnv 边界复用，不重新开发 ADB 原语或借用简化动作映射。

## 在线顺序和停止

1. 外层 setup 执行官方 reset、可选 Home、隐藏自动化坐标；零轮预算跳过 setup。
2. 每轮开始恢复数据 State，将上一轮应入历史的总结写入既有 Memory，再读取完整
   历史。最后额外一次 flush 只写终止/末轮历史，不观察、不调用模型、不执行动作。
3. 默认等待 1 秒后读取官方 state；`transition_pause=None` 使用原版稳定状态模式。
4. Perception 保留完整 UI 元素顺序和索引，按原版可见性/边界条件生成原图、SoM
   和文字描述。不会以本地 XML、GroundingDINO 或重新编号的元素替代。
5. 使用官方提示词、完整总结历史、原图与 SoM 选择动作，执行原版 Reason/Action
   及 JSON 转换。没有同轮解析重采样。
6. 图 Router 选择终止、固定反馈或执行路径。执行路径直接交给官方 AsyncEnv，
   保留执行前重新取 UI、点击/长按、坐标动作、输入/清空/Enter、区域滚动、App
   启动、answer 缓存和 wait 等行为。
7. 正常执行后默认等 2 秒并重新观察、编码；独立总结节点读取官方前后图、UI
   列表、目标、动作和原因，总结进入历史。
8. 每轮结束后可选调用原版语义的 `termination_fn(env)`，然后按 source status、
   环境终止或轮数预算停止。该钩子不提供 Benchmark 实现或评分。

| 分支 | 模型调用与历史 |
| --- | --- |
| 普通成功执行 | 决策、总结各一次；本轮进入 episode 和历史 |
| answer | 更新原环境交互缓存/展示回答，继续观察与总结，不立即停止 |
| status | 任意 source status 立即停止；complete/infeasible 原文与源字段保留 |
| 格式/JSON 转换/索引上界错误 | 一次决策、零执行、固定反馈进入历史，下一轮继续 |
| 执行异常 | 返回失败步骤给 episode；不观察、不总结，**不加入历史** |
| 决策无有效响应 | 致命错误，不当作普通格式反馈 |
| 总结无有效响应 | 固定错误反馈入历史，继续下一轮 |
| 预算耗尽 | 末轮总结、历史 flush 完成后返回 STEP_LIMIT |

执行异常可能发生在组合动作的中途，例如已经点击文本框但输入失败；保留原版继续
行为不代表设备操作已经回滚，也不代表没有发生部分副作用。

没有擅自修复官方的以下行为：scroll 的 index=0 按全屏处理；输入为负的索引仍按
原版分别经过标记/执行校验；保存的 before 图有 before 标签，而总结模型输入是
未加该文字标签的 before SoM；infeasible 的源 summary 仍使用原版固定文案。
JSONAction 接受的 double_tap/swipe/unknown 等也保留，不将动作收紧为提示词中的
子集。故意调整这些行为应单列变更，不继续宣称该路径与固定源码一致。

## 构图与运行

项目环境中，静态构图不要求安装 AndroidWorld 或模型依赖：

```bash
conda run -n unimobile python -m examples.sdk.m3a_online --dry-run
```

预期返回 graph_hash 和 `execution_evidence: false`。没有模型、设备、密钥读取。
Python/YAML 构图结果一致性由测试验证。

离线替身执行与原版对照：

```bash
conda run -n unimobile python -m pytest tests/runtime/test_m3a_online.py -q
conda run -n unimobile python -m pytest tests/packaging/test_m3a_install.py -q
```

第一条覆盖原始可执行语句的 AST 对照、提示词逐字/图片逐像素对照、动作与时序、
UI 编号空洞、旋转、缺失响应、安全判定、异常与历史、零轮/末轮预算、长历史、
复用隔离、YAML 和模型包装器接口。第二条实际构建 wheel，在无仓库导入路径的
干净虚拟环境中先检查 base-only 构图，再离线复制已安装的声明依赖，执行安装后
YAML 完整流程；不会下载模型或访问网络。

真实执行要求使用上述固定提交的官方 AndroidWorld 环境和其完整依赖，并准备
官方支持的模拟器。安装本项目 `[m3a]` 只提供 NumPy/OpenCV，不替代官方环境安装。
以下命令是运行入口说明，**本轮没有执行真实模型/设备运行**：

```bash
python -m pip install -e '.[m3a]'
# 先按固定提交的官方 README 配置 AndroidWorld、模拟器和 OPENAI_API_KEY。
python -m examples.sdk.m3a_online --task 'Open settings' \
  --max-rounds 30 --console-port 5554 --grpc-port 8554 --adb-path /path/to/adb
```

已经持有官方环境时，可复用现有 SDK，不经过另一种 Agent.step：

```python
from zhixing.m3a import build_m3a_graph
from zhixing.plugins.agent.m3a.environment import M3AEnvironment
from zhixing.sdk import AgentRunConfig, compile_agent

rounds = 30
agent = compile_agent(build_m3a_graph(max_rounds=rounds))
result = agent.run(
    'Open settings',
    AgentRunConfig(max_steps=rounds + 1, artifact_root='temp/m3a-runs'),
    device=M3AEnvironment(official_async_env),
)
```

环境由调用者创建/关闭；图执行 reset 但不会安装 App、初始化 Benchmark 任务或
冻结日期。使用 YAML 时，将 `load_graph_yaml(...)` 的结果传给 `compile_agent`。
默认模型是固定源码工厂的旧 GPT 型号，是否仍可用没有验证；修改型号需明确记录。
官方 Gpt4Wrapper 在部分 HTTP 非成功响应上可能持续重试，本适配没有擅自改变它。

## 预算、证据与限制

`max_rounds` 统计完整决策轮，包括格式错误、answer 和 wait；与物理交互数不同。
图物理预算为 `max_rounds + 1`，SDK `AgentRunConfig.max_steps` 也需显式给出这一值。
SDK 默认 15 的额外上限若更低，会在动作后提前中断，不能据此声称完成官方末轮。
本项目配置限制轮数为 0–999、显式等待为 0–60 秒；不宣称接受任意原版配置范围。

每次观察保存不可变 PNG 与完整 source UI JSON。标记图和选择目标图是独立副本。
`m3a-episode.json` 保留每个 episode 步骤和 source history、源停止事实及原动作字段。
HTTP 原始响应只保留存在性；不保存客户端、环境、响应对象、请求头或密钥。
未被 M3A 算法读取的 UIElement.metadata 被去除，避免携带环境内部对象或秘密。

`episode_done`、`agent_done`、`environment_done`、`goal_status` 分开记录。
complete 映射 Agent SUCCESS；infeasible/缺失或其他 status 映射 FAILURE；无停止信号
而轮数耗尽映射 STEP_LIMIT。可选环境钩子终止映射正常运行结束，并保留 agent_done
及 goal_status 原值。这些映射都不等于 Benchmark PASS，记录明确标注未进行评分。

后续真实验收仍需核对固定 AndroidWorld 安装、模型接口与凭据、设备/App 版本，
并保存真实轨迹。现有证据覆盖明确的替身行为与源算法，不能推导真实任务成功率。

## 本轮实际验证记录（2026-10-22）

- M3A 专项：54 项通过，包括生产图的完整在线替身执行及固定源码对照。
- 扩大回归：578 项通过，包含上述 54 项；其余覆盖 Graph、Catalog、通用 Kernel、
  绑定、已有 AutoDroid/SeeClick/Aguvis/V-Droid/Agent-SAMA 和资源/依赖边界。
- 干净 wheel 验收：另 1 项通过；base-only 编译没有导入 NumPy、OpenCV、AndroidWorld
  或 OpenAI；安装声明视觉依赖后，安装版 YAML 执行两轮、三次模型调用并保留历史。
- SDK dry run 与 YAML/Python 默认图身份一致：
  `sha256:deac69ea6d1b90bf7cd79b892b2aba5b805516a866a70c93f3bfcf27c6e33cdd`。
- 新函数均有 docstring，修改文件 whitespace 检查通过；Kernel 没有 M3A 分支。
- 回归中修正已有资源测试的过时固定计数：仓库当前有 27 个 Markdown 提示词，原
  断言仍要求 16。改为来源与包资源清单一致性，并继续读取每一个提示词。

扩大回归的可复现命令：

```bash
conda run -n unimobile python -m pytest \
  tests/runtime/test_m3a_online.py tests/runtime/test_generalized_kernel.py \
  tests/runtime/test_builtin_catalog.py tests/runtime/test_formal_component_binding.py \
  tests/runtime/test_external_catalog_binding.py tests/graph tests/catalog \
  tests/runtime/test_binding_and_assemblers.py tests/runtime/test_graph_runtime.py \
  tests/runtime/test_runtime_contract.py tests/runtime/test_multiple_input_readiness.py \
  tests/runtime/test_autodroid_online.py tests/runtime/test_seeclick_online.py \
  tests/runtime/test_aguvis_online.py tests/runtime/test_vdroid_selection.py \
  tests/runtime/test_agent_sama_online.py tests/runtime/test_agent_sama_components.py \
  tests/runtime/test_agent_sama_official.py tests/runtime/test_agent_sama_recovery_gate.py \
  tests/packaging/test_dependency_profiles.py tests/packaging/test_resources.py -q
```

隔离安装命令见前文。以上数量记录本轮实际检查，不代表全仓全部测试。
