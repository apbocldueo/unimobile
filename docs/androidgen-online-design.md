# AndroidGen：官方在线流程与六类组件映射（开发前）

2026-10-22 开发前记录。用户当时要求先拆官方流程、核对复用能力、暂不改代码；
下文的“尚未实现”保留这一调查时点。用户随后已授权开发，当前组件、图、YAML、
对照验证与限制见 [AndroidGen 在线执行](androidgen-online.md)，不以本历史方案
代替当前实现证据。

来源固定为 [THUDM/AndroidGen](https://github.com/THUDM/AndroidGen) 提交
`3f511cff18a842e6583ac7e7d9cabd217c5d3b1b`，论文为
[ACL 2025 长文](https://aclanthology.org/2025.acl-long.138/)。已有来源筛选、配置和错误
记录见 候选选择记录 (not bundled in the core source)。

## 1. 本次复现对象与入口

主线采用官方 `run.py:run` 的单任务在线流程。其完整调用顺序如下。

| 时机 | 官方实现 | 必须保留的行为 |
| --- | --- | --- |
| 初始化 | `environment/android/env.py:Env.__init__`、`Agent.__init__` | 绑定/准备设备、取得初始 App 信息；决策模型与规划模型独立配置 |
| 初始经验 | `model/example_retrieval/__init__.py`、`retriever.py` | 开启 ExpSearch 时读取经验库并检索一次；将示例放入系统提示 |
| 每轮观察 | `Env.get_current_state` | 等待稳定状态，读取官方 UIElement；构造文本、原图及编号图，并取得 App/方向/边界 |
| 每轮规划 | `model/planning/__init__.py:Plan` | 无计划时生成；已有计划时结合当前界面和历史 assistant 响应更新 Done/Todo |
| 错误反馈 | `Agent.__call__` | 规划后读取上轮执行结果；autocheck 开启且 operation=fail 时，将原错误加入当前输入 |
| 动作决策 | `Agent.__call__`、`model/llms/gpt.py` | 系统提示＋固定任务开头＋最近 20 条历史消息＋当前状态/计划/反馈；一次动作模型调用 |
| 提取与执行 | `run.py:get_code_snippet`、`Env.interact` 及各动作方法 | 提取第一段代码块，按原函数调用协议执行；保留源校验、异常和执行结果 |
| 提交历史 | `Agent.update`、`recorder.py:Recorder.update/format_history` | 保存原始响应、输入时错误反馈和执行结果；重建 user/assistant 历史 |
| 停止 | `run.py` | operation=exit 时退出，否则按轮数继续；保存轨迹并结束环境生命周期 |

官方独立入口使用 `recorder.turn_number <= 30`，计数从 0 开始，默认最多 **31 轮**。
`quote`、失败操作等也会消耗逻辑轮，不能将预算替换成“31 次成功点击”。
`exit` 由 Agent 主动声明结束，不等于 Benchmark 的真实任务 PASS。

## 2. 不能从论文名称直接推断的细节

### ExpSearch

官方编码器是 Contriever，池化为 attention-mask 均值，使用未归一化向量点积及
`torch.topk` 选 top-1。当前在线默认 `allow_same=True`；按 complete 与 env 过滤，
App/init_state 限制在代码里已注释。不得自行补上 App 过滤或排除同任务示例。
没有匹配项、或显式关闭检索时，`prompt_provider` 使用原默认示例，而不是完全没有示例。

### ReflectPlan

第一次生成时，仅解析合法计划行；全部解析失败可以留下空计划，仍进入当前动作决策。
已有计划的更新若没有解析到任何合法行，会用同一提示继续调用规划模型，期间不重新
观察设备。计划全部 Done 不会自动替代 `exit`。规划输入保留此前全部 assistant 响应，
并不沿用动作模型最近 20 条消息的截断规则。

### AutoCheck

源码的检查分散在 `do`、open_app、quote、方向检查及实际执行接口里；随后由
`Agent.__call__` 决定是否把上一轮 fail 的 message 提供给模型。它没有额外的截图
反思模型。`autocheck=false` 关闭的是该错误提示注入，并不会关闭环境方法本身的检查。

不能把全部检查统一搬到执行前。例如 `input_text('', id)` 会先点击目标，再检查
文本为空并返回 fail。完整等价需要保留这一副作用顺序。

### 解析与错误边界

没有匹配代码块时，异常发生在 `Env.interact` 外，独立入口会中止；代码执行内部
异常由 interact 转为原 fail 反馈。不能统一替换成“自动重试解析三次”或把两种错误
都直接映射为正常下一轮。没有结果的代码、未知操作等边界也应纳入后续对照。

## 3. 六类组件怎样承载

这里六类表示能力职责，可以有多个阶段节点；角色不强制固定排列。观察、执行仍走
显式设备边界。以下新增名称均是**拟议名称，尚未注册或实现**。

| 组件家族 | 在 AndroidGen 中负责什么 | 现有复用与拟新增内容 |
| --- | --- | --- |
| Perception | 从官方 UIElement 构造原格式文本和 SoM | 复用 M3A 已保留的 UI 数据转换、像素读写与原 SoM 绘制纯函数；新增 `androidgen_perception` 格式/过滤适配 |
| Planner | ReflectPlan 初始生成、状态更新和解析 | 新增 `androidgen_reflect_plan`，封装原算法；一个调用节点只作一次模型尝试，空更新重试由 Graph 控制 |
| Reasoning | 原系统提示、历史、状态、计划/反馈组合与动作代码块 | 新增 `androidgen_reasoning`，保留角色消息及原解析边界，不混入通用 JSON 动作重试 |
| Memory | 完整对话历史、计划状态、上轮结果、初始检索示例 | **直接复用 `sliding_window_memory`，设置足够窗口**；新增原 Recorder 历史转换/提交薄适配；ExpSearch 作为该家族的知识依赖，新增 Contriever/库格式适配 |
| Verifier | AutoCheck 的原始执行反馈判定 | 新增轻量 `androidgen_feedback`：读取上一轮结果和配置，保留原 message；不调用模型，不额外观察，不擅自立即重试当前动作 |
| ActionExecutor | 原函数协议执行、原检查及设备副作用 | 新增 `androidgen_execute` 与显式环境桥接，复用官方 AsyncEnv/ADB 服务；检查与动作的源顺序留在执行边界内部 |

Verifier 在当前轮 Planner 后、Reasoning 前消费**上一轮**结果，与官方顺序一致。
它只组织 AutoCheck 的反馈；执行器内部的真实检查不会被重复执行或全数前移。
这不是新增一种模型评审算法，也不增加第七类核心组件。

Memory 可存每轮两个 TEXT 片段（user 的环境省略/反馈文本、assistant 的原始响应），
默认窗口至少覆盖 31×2=62 条消息。Planner 读取全部片段，Reasoning 再按原代码截取
最后 20 条并添加固定任务开头。片段携带轮次/消息序号，避免相同输出被运行时去重。
检索示例单独存入运行数据，避免被错误地当作历史 assistant 或每轮重复检索。

为复用同一个 stateful Memory 节点，建议沿用 M3A 的时序：每轮开始写入上一轮待写
片段，再读取上下文；每轮结束只将新记录及待写片段提交到 Frame/State。终止或
第 31 轮完成后，再执行一次不观察、不调用模型、不操作设备的收尾，将最后片段写入
同一 Memory 节点。因此外层最多 32 次迭代，其中最多 31 次实际决策。
不能声明两个独立 Memory 节点，再默认认为它们共享同一缓冲区。

标准核心 Planner DTO 只包含任务和截图；标准 Verifier DTO 面向前后观察。
它们不足以直接表达本流程。建议沿用现有 NodeContract 扩展方式，声明当前状态、
旧计划、完整历史和原执行结果等类型化端口，而不修改既有公共 DTO、合同或 Kernel。
六类角色仍保留；额外端口属于已有扩展机制。

## 4. 现有插件逐项复用结论

| 已有能力 | 判断 | 源码依据与理由 |
| --- | --- | --- |
| Graph Builder、Loop/Router/State、条件、运行隔离、产物服务 | 直接使用 | 已有图基础设施可以描述阶段和分支；AndroidGen 代表图仍需实际执行验收 |
| `agent.memory:sliding_window_memory` | **调参数直接复用** | TEXT 片段保留内容和角色；本轮已验证窗口 62 完整保留 62 条消息 |
| `zhixing.memory.fragments:1.0` | 直接使用 | 已有片段写入合同支持多条 fragment；无需把历史转成通用 Action 文本 |
| M3A 的 `portable_ui/source_ui`、`load_pixels/save_pixels`、原标记函数 | 复用纯函数 | AndroidGen 本来就调用官方 m3a_utils 绘制；UI 编号仍取原列表索引 |
| `m3a_perception` 整个组件 | 需要新格式适配 | M3A 的描述字段和 AndroidGen 的 `<element ...>` 格式、tooltip/resource/键盘元素过滤不同 |
| `xml_som_perception`、`autodroid_perception` | 无法仅靠参数等价 | 前者从 UIAutomator XML 筛选、合并、重新编号；后者合并后代语义，改变原 UI 顺序/文本 |
| `universal_planner` | 无法仅靠换提示词等价 | `PlanInput` 无完整历史/旧计划/当前文本状态；现有 make_plan 没有源更新和空计划分支 |
| `universal_reasoning` | 无法仅靠现有参数等价 | 通用输入为拼接文本、动作空间和 Action 解析；原版是角色化对话＋Python 代码；关闭解析重试只能消除一项差异 |
| AutoDroid 的 `AppMemoryIndex` | 不直接替换 ExpSearch | 固定语义包含余弦归一化、查询前缀和不同库结构；换 checkpoint 或 top_k 不能得到原点积检索 |
| `llm_reflect_verifier`、`screen_diff_verifier` | 不使用于原 AutoCheck | 前者多调用模型，后者新增截图变化/重试判断，都会改变原策略 |
| `llm:openai_llm`、`llm:m3a_llm` | 复用 SDK/依赖机制，新增消息协议薄适配 | 前者主要构造一个 user 消息，后者是 M3A predict_mm；均不能仅改参数保留原 system/history/current 顺序 |
| `M3AEnvironment` 整个包装 | 不直接复用 | reset/等待、metadata 与动作语义为 M3A 专用；AndroidGen 还有清空文本、逐字符 ADB、相反 Swipe 等行为 |

新增 LLM 适配建议惰性委托原 `OpenaiEngine` 或相同消息协议的显式后端，规划/动作
模型分别绑定。模型、设备和编码器实例留在依赖/运行服务里；图 State 只存可序列化
数据与资源引用，不能把原 `Agent`、`Plan` 或 `ExampleRetriever` 实例塞入状态。

## 5. 建议 AgentGraph

下图为设计草图，不是已存在或可直接运行的配置。

```text
Task → 环境准备 → Memory/Knowledge：一次 ExpSearch → 初始 State
  ↓
有界任务 Loop（最多 31 个决策轮＋1 次收尾）
  State 恢复 → Memory 写入上轮片段并读取 → Router
    收尾：发布历史/结果
    继续：显式观察 → Perception
  → Planner：无计划生成 / 已有计划更新（空更新进入重试子图）
  → Verifier：整理上一轮 AutoCheck 反馈
  → Reasoning：原始消息与一次动作决策
  → ActionExecutor：代码块、原检查与原设备执行
  → Memory 家族：原历史/执行结果及待写片段提交 → State 写回
  → Router：exit 结束 / 下一轮 / 逻辑轮数耗尽
  ↓
轨迹与运行结果；可选任务后经验更新另行启用
```

普通轮次通常是规划一次、动作决策一次；规划更新格式无效可能增加规划调用。
没有 M3A 的动作后截图总结模型，也不为适配现有 Verifier 补一个额外观察阶段。
本轮观察保存原图和 SoM 不等于它们都会作为模型输入；规划/动作的 text/image
配置分别控制实际消息图片。

31 逻辑轮应由图状态及 Loop 管理。物理交互预算必须留出末轮历史提交的空间，
不能让内核在最后一次设备作用后立即中断。精确预算和最后一轮保存需用图执行验证。

源 Plan 更新可无限重试，而现有 Graph 要求有界 Loop。建议增加显式规划尝试预算，
超限单独报告预算耗尽，不冒充原 `fail` 或任务完成。这是运行保护差异，不能声称
与源无限重试在全部输入上等价。官方模型包装器的退避也可能持续等待；若另加传输
重试上限，同样应显式配置和披露，而不是悄悄改变原模型调用。

源接口使用 Python 代码执行；建议原协议留在显式 ActionExecutor/环境边界。
不能直接替换成现有 JSON parser；如后续选择限制可接受语法，也要明确范围和差异。
本轮没有决定或实现第三方代码沙箱。

## 6. StepCritic 支路：已查全源码，边界另列

完整 tracked tree 中存在 `model/judge/judge.py` 与 `judge_prompt.py`，本轮已补读。
普通 `run.py` 不调用它；`evaluate/androidworld/androidgen.py:step` 的 exit 分支
会另外启动该脚本。

该支路读取已保存轨迹，以任务、全部响应和最后一条记录的文本状态调用判定模型，
最多尝试三次，解析子目标/完成步骤，再写入检索数据库及成功子目标前缀示例。
这里最后状态来自原记录，不能自加一次终止后观察后称为原输入。

若复现固定经验库下的官方 `run.py` 在线 Agent，StepCritic 不在每轮主图内；
不能因此宣称已覆盖跨任务经验自更新。若目标包含这一能力，则应另加显式任务后
支路：**Verifier：StepCritic → Memory/Knowledge：按原规则更新库**，并将相应核心
源码计入那一配置的 LOC。它的模型判断不替代 BenchmarkTask 的独立真实任务评测。

## 7. 拟涉及文件（尚未创建）

- `zhixing/plugins/agent/androidgen/`：类型、原编码/提示/解析来源、Perception、
  Planner、Reasoning、反馈 Verifier、Memory 薄适配、执行与环境边界。
- `zhixing/knowledge/androidgen.py`：原经验库与 Contriever 的惰性运行适配。
- `zhixing/plugins/llm/androidgen_llm.py`：原角色消息协议与模型依赖。
- `zhixing/graph/androidgen_contracts.py`、Catalog/合同注册：显式新端口与阶段合同。
- `zhixing/androidgen.py`、`examples/graphs/androidgen_online.yaml`：SDK/YAML 显式装配。
- 官方源码夹具及 provenance、组件/图/差分测试、干净 wheel 测试和可选依赖声明。

现有内核、通用编译器、六类角色、既有 Agent 和独立 BenchmarkTask 契约均无需为
此设计增加 AndroidGen 专属分支。是否成立须由后续代表图运行证明。

## 8. 开发前门槛与未来验证清单

先保留已复现的 tooltip 原错误、非法依赖声明和默认 human/占位资源配置；必要修复
应有独立 diff、配置和测试记录。原行为、兼容修复、新装配及运行保护成本要分列。
不能关闭 ReflectPlan/AutoCheck/ExpSearch 后宣称完整配置已通过。

后续至少验证：

1. 原始/复现两端完整 system、角色消息、20 条截断、规划完整历史、原图/SoM 输入。
2. 首次空计划不立即重试、更新空计划同提示重试、合法部分行、全 Done 不自动退出。
3. 经验库 complete/env 过滤、top-1 点积、无匹配默认示例、运行时只初始化检索一次。
4. 全部官方动作、quote/exit、失败反馈、autocheck 开关、空文本点击后失败及 Swipe 方向。
5. 缺代码块致命失败、执行代码异常可恢复失败、逻辑轮数与物理作用计数、末轮历史保存。
6. 独立运行不串计划/记忆、编译不连接设备或加载模型、wheel 安装后的实际 YAML 执行。
7. 若启用 StepCritic 更新，另测三次尝试、无法解析、原数据库跳过、子目标前缀及后续检索。

本轮已运行的只有局部探针：固定源码哈希；提取未改动的 Plan/Agent 方法并注入脚本
模型，验证完整历史与 20 条截断、空更新重试和错误反馈；现有滑动记忆保存 62 条；
原 input_text 空文本先点击再失败；缺代码块异常与 interact 失败边界。
探针替换模型服务及部分常量/状态，不是整套原版执行，更不是 Graph 差分验收。
结果在 `output/research/androidgen-flow-20261022/probe-results.json`。没有真机、真实
模型/Contriever 权重调用或新增 LOC 结论。
