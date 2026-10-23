# GUI-explorer：六类组件对应与现有实现复用审查

日期：2026-10-22。范围为官方非演示在线任务执行，给定知识库；离线探索和知识挖掘
不在本次接入方案内。固定来源版本 `01338e8ccc1c21d9897642ba197c6ac177e90118`。

后续状态（2026-10-23）：用户已批准并完成在线图实现，实际复用了本页确认的四个
组件和五个 UI 函数；完整图/原始源码对照及安装包验证已通过。下面保留实施前审查的
判断与边界，当前实现和最终验证以 [在线执行文档](guiexplorer-online.md) 为准。

本次是代码审查及隔离兼容性检查，没有新增生产组件、YAML 或 GUI-explorer AgentGraph。
下文区分已经验证的组件操作与尚待集成的设计，不以相同角色或相似类名代替兼容证据。

## 核心结论

可以使用现有六类角色和 AgentGraph，且不需要六类各写一套新实现。

- **原样复用**：`sliding_window_memory`；在沿用现有轮次数据合同的前提下复用
  `m3a_resume`、`m3a_commit`、`m3a_pass`。本次实际执行验证了这些组件操作。
- **函数级复用**：M3A 的五个 UI 描述/过滤/几何处理函数，以及图像读写工具。
  其中四个函数体完全相同，列表函数只有一个已核实相同的调用别名差异。
- **需要来源适配**：GUI-explorer 的感知包装、检索、知识排序、动作选择与总结、
  原始动作分派及设备/模型协议。需要做薄适配，不代表从头写这些算法。
- **不新增**：独立 Planner、独立 Verifier、运行内核分支、训练系统或新的组件角色。

完整现成组件可以直接复用的数量有限；现有框架控制能力和函数的复用范围更大。
不把“框架已有同类接口”“复用源代码函数”“原样引用注册组件”混算成同一种复用。

## 六类角色逐项对应

| 角色 | 官方在线行为 | 现有候选 | 审查结论 |
| --- | --- | --- | --- |
| Perception | 有效 UI 列表、原始索引、SoM、元素裁剪、执行后图片 | `m3a_perception`、`xml_som_perception`、`som_perception`、`coordinate_perception` | 五个 M3A 函数和图像工具可复用；完整感知组件不能只改参数就对齐 |
| Memory | 完整步骤总结历史；按当前 App 和元素裁剪图检索知识 | `sliding_window_memory`、`summary_memory`、`autodroid_memory`、`androidgen_examples` | 历史存储直接复用 SlidingWindowMemory；图片知识检索需新适配；其余检索器不能通过换模型名替代 |
| Reasoning | 知识两两比较排序、带知识动作选择、执行后总结 | `m3a_select`、`m3a_summary`、`universal_reasoning` | 结构参考 M3A，提示、解析、图片及异常协议按官方适配；三种操作可为同角色的多个节点 |
| ActionExecutor | 按 JSONAction 分派点击、输入、滚动等动作 | `legacy_action_executor`、`m3a_execute` | 保留 Action/ActionResult 和显式设备边界；完整原始动作协议需适配，不能直接替换为通用执行器 |
| Planner | 没有独立子目标规划 | `universal_planner`、`ordered_argmax`、SAMA Planner | 不接入；Ranker 排的是知识，并非执行子目标计划；ordered_argmax 也不等价 |
| Verifier | 没有独立成功判定/恢复算法；总结仅作为下轮上下文 | `llm_reflect_verifier`、`screen_diff_verifier`、内容增量验证器 | 不接入；终止及错误由图条件路由，Benchmark 独立评测 |

### Perception：可以多复用一个函数，但绘图确实不同

直接可复用 `zhixing/plugins/agent/m3a/source.py` 中：

1. `_generate_ui_element_description`；
2. `validate_ui_element`；
3. `_logical_to_physical`；
4. `_ui_element_logical_corner`；
5. `_generate_ui_elements_description_list`。

第 5 个函数上轮 AST 原样比较为不同，本次进一步核查发现差异仅为
`m3a_utils.validate_ui_element(...)` 与 `validate_ui_element(...)`。前者实际指向
同一个函数；消除这个已核实别名后，函数体一致。包含隐藏元素的样例也输出相同，
都会过滤隐藏元素并保留原列表索引，不能据先前 AST 标志认定它需要重写。

`m3a.perception.load_pixels/save_pixels` 不绑定 UI 算法，可以复用。
但 `M3APerception` 目前固定使用 `metadata['m3a']`、M3A UI 重建和绘图函数，
没有参数可切换到 GUI-explorer 的全套规则。两种 SoM 函数处理相同样例产生 606 个
不同像素；M3A 还有额外缩放处理。`mark_target/label_before` 也调用 M3A 绘图，不能
因为能读写同一文件就宣布可直接使用。

其他感知组件的差异也无法靠现有参数全部消除：XmlSom 合并 clickable/focusable、
去近邻并从 1 编号；SoM 使用目标检测模型；Coordinate 重新组织文本与编号。
这些变化会改变知识检索的图片和动作索引，不能当作官方等价输入。

**建议**：新增薄的 GUI-explorer 感知包装，引用五个共享函数和图像工具，保留官方
UI 数据结构、绘图/标签和裁剪逻辑。无需为了本次接入先重构所有已有感知插件。

### Memory：历史直接复用，图片知识检索单独适配

`SlidingWindowMemory` 对 TEXT fragment 原样保留，因此每个官方历史条目写成一个
TEXT fragment 即可。默认最大 30 轮时配置 `window_size: 30`，不额外向这个历史节点
写入任务、知识或其他 fragment。未来增加轮数时，窗口必须同步覆盖全部历史。
图中的 Memory 保持按 Run 独立实例及 `stateful` 生命周期。

本次把官方循环产生的 30 条历史逐条写入现有 Memory，经现有 canonical adapter
读取，文本、顺序和 metadata 均保留；清空及新实例空历史检查通过。
`SummaryMemory` 的长期压缩与官方逐步视觉总结是两回事，不能互相替代。

检索不能复用 AutoDroid/AndroidGen 的算法：AutoDroid 是任务文本查询及任务路径知识，
并缓存一次 Guide；AndroidGen 是任务开始时用 Contriever 检索一条经验示例。
GUI-explorer 则每步对元素裁剪图做 SigLIP 检索，使用 App 分库、融合库回退、相似度
阈值及 top-k。现有 `BaseKnowledgeSource.search_docs(query: str)` 也不能直接表达
整批图片查询；`RETRIEVE_EXPERIENCE` 的返回 Action 与本方法的知识列表不同。

**建议**：历史仍用已有 Memory；新增 Memory 角色内的图片知识读取节点，调用作者
已有检索服务。无需重写 SigLIP/FAISS，也无需添加全局 MemoryOperation 或第七类角色。
服务是 Memory 的运行依赖，类似现有模型依赖；检索结果通过明确的 typed port 输出。

### Reasoning：新增的是官方协议，不是重新设计算法

`M3ASelect` 绑定 M3A 提示、`Reason:` 解析及安全分类协议；GUI-explorer 的提示含知识、
输出 `Reasoning:`，没有该安全分类分支。直接使用 M3A parser 会解析不到 reasoning。
`M3ASummary` 的提示和失败总结文字也与官方不同，不能只换模型名。

`UniversalReason` 支持换提示和 parser，但历史格式固定，并在解析失败时原地重采样；
即使设置 `parse_max_retries: 0`，失败结果仍是 FAIL，不能自动变成官方的“记下反馈，
进入下一轮”。目前也没有现成的知识端口、完整来源步骤记录及终止协议适配。

`ordered_argmax` 输入已有数值分数并输出一个最高分候选；官方 Ranker 调模型做两两
比较并返回全部知识的顺序。保留一条最高分知识会改变方法。SAMA 的候选生成/打分及
恢复规划、AndroidArena 的跨试次反思也属于不同算法，不能因都调用 LLM 就直接替代。

**建议**：Reasoning 下分别安排 rank/select/summary 三种明确操作，使用官方原函数与
提示。排序内的归并递归是有界局部算法，任务循环仍由 AgentGraph 调度。

模型可复用 `BaseLLM`、密钥绑定、usage 和证据设施，完整现有模型插件不能照搬：
`m3a_llm` 依赖 AndroidWorld Gpt4Wrapper；通用 `openai_llm` 的图片 MIME/detail、
返回值和异常规则与官方 WEBP 请求及 response-presence 区分不同。需来源模型适配层，
保留成功空文本与没有 HTTP 响应的区别。官方无限重试隐患如做有限化修复，应单独记录。

### ActionExecutor 与设备边界

已有通用执行器能够完成若干同类动作，但不具备完整等价协议。官方输入文字会先聚焦，
再调用 `input_text(..., smart_enter=True, clear_first=True)`；通用执行器没有这些
选项。官方原生 double-click、滚动端点和时序、App 启动匹配及 answer 展示也需保留。

`m3a_execute` 要求 `M3AEnvironment`，其底层是 AndroidWorld AsyncEnv；GUI-explorer
使用 uiautomator2。现有 `AndroidDevice` 的 ADB 输入法、滑动及 UI 采集也不同。
AndroidArena 虽同样用 uiautomator2，但有不同 reset、XML 处理及固定等待规则。

**建议**：复用设备/Artifact/ActionResult 的现有服务边界，薄包装官方 Device 和动作
分派，不修改 Runtime。读取和动作必须显式发生在观察/执行阶段，不能藏进 Reasoning。
设备服务和模型服务是依赖，不是额外的 Agent 能力角色。

## 轮次组件可以真正原样复用

| 注册组件 | 已核实行为 | 使用条件 |
| --- | --- | --- |
| `agent.memory:sliding_window_memory` | 原样保留 TEXT、顺序及元信息 | 窗口覆盖完整历史；每 Run 独立实例 |
| `agent.memory:m3a_resume` | 创建游标、恢复前轮、判定终止或轮数上限 | 沿用 `M3AFrame` 公共字段；不启用 M3A environment_done 钩子 |
| `agent.memory:m3a_commit` | 提交一步、增加轮数、选择是否追加历史、末次 flush | 复用现有游标字段，GUI-explorer 步骤类型可以扩展 M3AStep |
| `agent.memory:m3a_pass` | 原样透传或等待 Memory 读完成 | 保留现有端口合同，不伪造类型等价 |

这些组件名字带 M3A，但上述操作不调用 M3A 的模型、设备或提示。本次直接调用原组件
验证了初始化、正常提交、执行异常不追加历史、扩展步骤字段保留、透传、终止 flush 和
预算。沿用现有 `m3a_frame` 合同，使实际 Python 类型与声明一致；不单纯把任意新类型
的合同名字改成 M3A。尚未把它们接成 GUI-explorer 完整图，集成证明仍在后续。

`m3a_history` 的提取逻辑可以经薄包装复用，但 source tag 固定为 `m3a.summary`，
应改由包装层标记为 GUI-explorer。`m3a_finish` 固定写 M3A commit、文件名及 evidence
结构，不应复用后冒充 GUI-explorer 来源。无需为复用先全局改名这些公共标识。

## 建议的图及文件范围

图中顺序为：resume → 上轮历史写入/读出 → before 观察与感知 → 知识检索 → 知识排序
→ 动作选择 → 条件路由 → 执行 → after 观察与感知 → 总结 → commit → 下轮。
终止、解析失败和执行失败分支按官方跳过相应阶段；最后一轮需 flush，但不能多调用模型。
官方 run 在每个非终止 step 后还会额外等稳定，不能只保留动作之后的观察。

复用现有 State、Router、Loop、有界预算、合同校验及 Runtime；Planner/Verifier 留空。
下面仅为待实施文件范围，不是本次已经创建的实现：

| 范围 | 作用 |
| --- | --- |
| `zhixing/plugins/agent/guiexplorer/types.py` | 在现有游标/步骤基础上承载来源字段、UI 与知识查询/结果 |
| `.../perception.py` | 引用共享 UI 函数及像素工具；保留原始绘图、标签、裁剪 |
| `.../memory.py` | 图片知识检索、历史 source-tag 薄包装、真实来源的终态 evidence |
| `.../reasoning.py` | 官方 rank/select/summary 协议，图外不新建任务循环 |
| `.../environment.py`、`.../execution.py` | 原始 uiautomator2 设备与动作边界、等待顺序及 ActionResult |
| `.../source.py`、来源清单/许可证 | 仅保留需适配的官方定义；已能引用的共享函数不再次复制 |
| 模型适配、Catalog 和 Graph 合同 | 新来源的依赖/typed ports；不改内核调度逻辑 |
| 示例和相关测试 | 简洁 YAML、显式运行入口及逐分支来源对齐 |

## 本次验证与可复核边界

```bash
/opt/miniconda3/envs/unimobile/bin/python output/research/next-agent-after-mobilerl-20261022/probe_component_reuse.py
```

预期 `{"status": "passed", "checks": 9}`；明细在同目录的
`component-reuse-probe.json`。9 组检查涵盖 Memory、共享轮次组件、共享 UI 函数，以及
SoM、解析、排序和输入文字执行的具体差异。检查依赖均为本地源代码和模拟外部 I/O，
未连接设备、调用模型或访问检索服务。上轮的官方流程探针为 10 场景，两者不要相加
宣称为完整 GUI-explorer AgentGraph 测试。真实知识库加载、向量检索、图集成及真机
语义对齐仍未完成。
