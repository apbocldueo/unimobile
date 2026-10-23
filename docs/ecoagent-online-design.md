# EcoAgent 在线流程与六类组件设计

2026-10-22。本文保留实施前设计。**后续已获用户授权并完成选定在线流程的模拟验证，
当前实现与证据见 [EcoAgent 在线实现](ecoagent-online.md)。** 下文“未开始/拟议”等
描述均指调研时状态。
本轮用户同意继续调研；下述文件、组件和验收项是 Coding Agent 的拟议方案，
不是用户已确认的实现细节，也不是完整 AgentGraph 已通过验收的声明。

## 结论与选择范围

建议保留 EcoAgent 为下一候选。完整在线核心可按 Perception、Planner、Reasoning、
Memory、ActionExecutor、Verifier 六类职责拆开，没有发现必须增加第七类能力的需求。
需要策略适配和薄的运行期并发辅助代码，不能仅修改现有组件参数就声称官方逻辑对齐。

[正式论文](https://ojs.aaai.org/index.php/AAAI/article/view/40230)发表于 AAAI 2026。
[作者论文](https://arxiv.org/html/2505.05440v3)直接链接
[官方仓库](https://github.com/Yi-Biao/EcoAgent)。固定代码提交：
`d9b16afb4ccaf3beb59664984dab2aa258b3cccf`。
去重和发表准入证据见先前候选调查 (not bundled in the core source)。

先选官方 CLI 默认 `eco_ui-tars`：云端规划、小模型动作、界面描述、expectation 验证、
失败重规划、投机预测和有界循环均公开。论文主结果表使用 ShowUI/OS-Atlas executor，
不能把本方案说成这些表格/模型配置的复现。代码预测与缓存消费有写死 UI-TARS 的
地方，不能把 name 切换当作四个底座均已正确支持，也不把四变体另算四个 Agent。

## 一次具体执行

例如“输入联系人姓名并保存”：云端先根据初始截图生成步骤和每步 expectation。
计划若先给出 `INPUT [Alice]`，执行器通过 ADB Keyboard 广播输入，等待两秒后截图。
此时官方并发做三件事：描述新界面、比较前后截图与本步 expectation、预测下一步
“点击保存”的具体动作。**第三项只生成动作，不操作手机。**

反馈接受后才执行已预测的保存动作；反馈拒绝时先请求云端重规划。新计划需要 Home
时，旧保存动作必须丢弃；精确回复 `No need to replan.` 时才可继续旧计划/旧预测。
这些分支应在图中可见，不能藏在单个 Reasoning 插件内。

## 官方实际行为

来源为固定版本 `run.py`、`agent/eco.py`、`prompt.py`、`infer.py` 和
`utils/ui_tars_utils.py`。外层循环来自官方，不需要我们补写。

| 项目 | 固定源码事实 | 对齐约束 |
| --- | --- | --- |
| 初始规划 | 一次云端截图请求；Dual-ReACT 在同一 prompt 中引导，提取 step/expectation，thought 不进入后续动作状态 | 不凭名称新增两套 ReACT 模型循环 |
| 计划解析 | steps 与 expectations 分别过滤，保持 dict.values 顺序 | 缺 expectation 可能在动作后 IndexError；成对校验应单列修复 |
| 本地反馈 | before、after 两图及 expectation | 不以执行器布尔返回替代视觉判断 |
| 接受规则 | summary 不含独立单词 `not` 就接受，`No` 也接受 | 原算法保留；通用 Yes/No 判断不是等价替换 |
| 记忆 | 累计 descriptions，保留计划、索引和前后观察；history 属性未使用 | 不增加聊天历史，不用默认滑窗丢弃早期描述 |
| 重规划输入 | original_plan、descriptions、goal 与当前 after 图片 | `.format()` 传了 summary/description，但模板无这两个占位符，summary 没直接进入云端文本 |
| 新剩余计划 | 保留 steps[:step_n+1] 后拼接新步骤，新下一步重新推理 | 即使新旧步骤文本相同，也不复用旧预测 |
| 无需重规划 | 只认精确 `No need to replan.`，尾随换行不匹配 | 不静默 strip 后宣称原协议一致 |
| 并发收束 | context manager 等全部请求结束后进入成功/重规划分支 | 不能旧预测未结束就开始重规划 |
| 预测异常 | 只有 future.result 被消费时传播；新计划丢弃旧预测时不传播 | 无用预测失败不能自动升级为任务失败 |
| 任务停止 | 计划末尾反馈接受，或末尾失败后云端精确回复无需重规划 | decoder finished 返回被 ECO 忽略，不是全局 DONE |
| 默认预算 | 30 个逻辑验证轮次，首轮可能执行两个高层动作 | 物理交互预算不能直接写成 30；已复现两轮三动作 |
| 云端计数 | 仅初始/重规划调用及 tokens | 框架全部模型用量需单独记录 |

论文讲屏幕压缩，实际重规划仍传当前截图。因此不能宣称所有历史/当前画面都不上传，
也不能凭代码存在宣称已实现手机本地模型部署、原论文性能或隐私效果。

## 六类组件的复用边界

| 类别 | 复用既有基础 | 需要的策略适配 |
| --- | --- | --- |
| Perception | ScreenshotPerception 纯截图表示、DeviceObservation、运行产物与显式截图边界 | 原 DESCRIPTION_PROMPT、描述请求提交/收取；不额外把通用截图说明加入模型 prompt |
| Planner | 模型依赖、SecretRef、typed node 合同 | 初始/重规划消息、step/expectation 和前缀拼接；UniversalPlanner 固定任务变量/PlanResult 不足以表达这些状态 |
| Reasoning | 独立模型依赖与 typed invoke | UI-TARS 原 prompt、按步骤决定是否预测、消费/丢弃；UniversalReason 默认解析重试会增加源代码没有的调用 |
| Memory | 通用 RUN State READ/WRITE、Loop/Router、便携数据值 | 初始化、描述追加、索引/观察推进等薄数据操作；直接 State 存完整列表，无需新数据库/记忆算法 |
| ActionExecutor | Action/ActionResult、Android 目标隔离和 tap/swipe/key/shell 能力 | 原 decoder、INPUT 广播、十次 Delete、两秒等待与错误语义；通用 input_text/clear_text 默认不同 |
| Verifier | before/after 图片合同与模型依赖 | SUMARRY_PROMPT 和原 `not` 规则；LLMReflectVerifier 会跳过部分动作并解析 A/B/C/D，换 prompt 不足以等价 |

模型层不能无条件换参数：agent_sama_llm 可保留消息/图片顺序，但插入 image detail、
只返回文本并使用 SDK 重试；m3a_llm 接收像素列表，而这里是 data URL 和不同 tuple。
建议添加薄的请求/回复适配，复用依赖绑定与用量基础，不复制四套 HTTP 客户端。
保留规划/动作/描述/摘要各自 endpoint、模型、temperature、max_tokens 和响应差异。

原 DELETE TEXT 是十次退格，不保证清空任意长文本；INPUT 广播要求外部已安装并选好
ADB Keyboard。不得擅加 IME 切换、清 App 数据或任务 reset。UI-TARS decoder 把整数
当坐标使用，不引入没有来源支持的归一化缩放。

## 并发方案与本轮机制验证

现有 GraphExecutionKernel 同步逐节点激活，独立数据边不会自动产生并发。
本轮实际执行了一个研究小图，验证无需改 Kernel 的路径：

1. Perception、Verifier、Reasoning 分别准备请求，提交到调用者拥有的运行期 I/O helper。
   提交返回字符串 ticket，节点立即结束，模型 I/O 在私有线程中继续。
2. 三次提交完成后，Verifier 收 summary，Perception 收 description，保留 summary
   优先的错误顺序。所有原请求必须已发起，不能失败早退而少发请求。
3. 等本轮所有请求结束，但不因未消费预测的异常失败；Router 再选择继续/重规划/结束。
   继续旧计划时 Reasoning 消费旧 ticket，改计划时丢弃它并重新推理。
4. ActionExecutor 才有设备动作副作用，截屏只走 Perception/观察边界。

helper 仅负责 submit/wait/collect/discard/close，不解释任务、prompt 或重规划，
不注册新 Agent role，不执行一个隐藏 ECO.step。请求组装与结果解释仍各归六类。
Future/线程对象只存私有运行期依赖，不进入 State、YAML、events 或图 identity。

小图通过三工作线程 barrier 证明真实重叠，连续两次使用独立依赖执行成功；输出、
State、events 可 JSON 序列化，绑定时没有线程。它只证明 typed invoke 与显式绑定
能承载该机制，**没有证明完整 EcoAgent、默认 SDK/YAML 自动注入和清理已完成**。

建议沿用 SDK dependencies 或每次运行的新 resolver_factory，用调用者 context
manager 包住一次 run。SDK 当前没有通用依赖自动 close 约定，不能把共享 helper
注入一次后让任务串用。正式实现须验证 run/round 所有权、过期 ticket、重复提交、
异常/取消清理、有限 HTTP timeout、两次运行隔离。正常路径要在重规划前 join，
不能只靠最终退出时 close。并发模型请求不携带设备句柄，也不能自己执行动作。

现有用量通过 ContextVar 记录，线程不会自动继承任务上下文。建议 worker 返回便携
usage，由主线程收取/丢弃完成结果时统一记账，包括丢弃的已完成预测；避免多线程
同时更新同一用量对象。原 cloud-only 指标与框架全模型指标分别保留。

该方案比改全图并发调度范围更小，代价是运行期任务生命周期和两阶段节点事件：
提交完成不等于模型结果返回，收取节点才代表结果可用。没有真实模型延迟证据，
不承诺原论文的加速或成本效果。

## 原版问题与兼容修复边界

正式开发先保存原始源码，为修复保留独立 diff/原因/测试；不能修改冻结快照再称原版。

| 问题 | 已验证证据 | 拟议处理 |
| --- | --- | --- |
| 重名 send_home | 传 serial 触发 TypeError，循环前失败 | 最小入口修复，统一显式目标，不补写 Agent 循环 |
| 小写 json fence | 首次解析失败，后轮 before_image 未初始化 | 解析兼容补丁单列；非法计划明确终止属于错误路径改动 |
| point 标签 | prompt 空格坐标不能被原 decoder 识别，逗号坐标能 | 真实模型接入如需兼容语法，单列补丁，保留原分支，不计官方原始代码 |
| open_app | prompt/论文有，选定 decoder 无实现 | 本阶段不悄补新动作；如支持需独立实现/版本标记，不称官方已有 |
| 裸 adb/固定图片路径 | serial 未传，固定 screen.jpeg | 复用已有目标隔离与每 run 产物路径，说明传输/产物变化 |
| HTTP 非 OK | max_retry=2 仍到第 5 次请求，由替身终止实验 | 有界重试/timeout 单列修复，承认与原无限等待的错误轨迹不同 |
| HTTP 异常耗尽 | 返回 3 元组，调用处解包 4 值 | 统一失败 DTO/元组，单列修复 |
| 缺 expectation/空新计划 | 已复现动作后 IndexError / 重规划 IndexError | 若增加校验，与同补丁版本比较，不写作未修改的错误行为等价 |

建议保留原 `not` 规则、精确无需重规划、十次 Delete、预测异常消费规则；不顺手
优化算法。非法计划和 transport 修复应有开关或清晰版本。官方 requirements.txt
缺失，完整 package import、模型部署与原 CLI 仍待验收。

## 拟开发文件与职责

下述生产路径均尚未创建，正式实施先建立独立 OpenSpec change。

| 文件/位置 | 拟承担职责 |
| --- | --- |
| `zhixing/ecoagent.py` | 初始化、初始执行、有界验证循环、成功/重规划 Router、State 写回 |
| `zhixing/graph/ecoagent_contracts.py` | 便携帧/观察/ticket 端口及副作用合同，不新增 GraphRole |
| `zhixing/plugins/agent/ecoagent/types.py` | EcoFrame、计划、观察引用、反馈、ticket、source 计数；没有 live Future |
| 同目录 `prompts.py`、`protocol.py`、`source-origin.json` 与许可证 | 固定提示/纯 helper、解析与补丁归属；保留 infer.py Apache 来源头和根 MIT 归属 |
| 同目录 `perception.py` | 截图适配、描述提交/收取 |
| 同目录 `planning.py` | 初始/重规划、源提示、解析与前缀拼接 |
| 同目录 `reasoning.py` | 当前步骤推理、下一步预测、按图分支收取/丢弃 |
| 同目录 `memory.py` | 初始化、恢复、追加描述、推进与结果投影等薄数据操作 |
| 同目录 `execution.py`、`environment.py` | 显式设备边界、Home、原 decoder、等待与 acknowledgment |
| 同目录 `verifier.py` | summary 请求/收取、原判定、错误优先级 |
| 同目录 `io_jobs.py` | 惰性、有界、run 隔离的私有 I/O helper，没有 Agent 控制流 |
| `zhixing/plugins/llm/ecoagent_llm.py` | 原消息形状/usage 适配、请求设置与明确记录的 transport 修复 |
| `zhixing/catalog/builtins.py`、`zhixing/graph/contracts.py` | 惰性登记组件/合同，不连接模型/设备 |
| `examples/graphs/ecoagent_online.yaml` | 组件、非默认参数、连接，不能缩成隐藏工作流插件 |
| `examples/sdk/ecoagent_online.py` | 同图 dry-run、明确目标/模型配置、运行依赖 context manager |
| `tests/runtime/test_ecoagent_online.py` 及 fixtures | 与原定义/单列补丁定义差分，不是两份我们重写的逻辑互测 |
| `tests/runtime/test_ecoagent_components.py`、`test_ecoagent_io_jobs.py` | 组件协议、并发、延迟异常、清理、用量与隔离 |
| `tests/graph/test_ecoagent_yaml.py`、`tests/packaging/` | YAML/Python 同图、无副作用、干净安装与资源闭合 |

不计划改 runtime/kernel.py、六类枚举、BenchmarkTask JSON 或 Studio。依赖够用时
不加新包；确认需要额外可选依赖/打包资源才改 pyproject.toml。以后分别统计官方核心、
新增装配、兼容修复、YAML，不能把这些拟开发文件都算成官方源码。

## 分阶段验收

1. **原基线**：固定来源闭合；未修改原定义的正常/重规划/预测丢弃/异常路径；
   入口和模型协议修复分别保留 diff。未公开实现的动作不补作官方能力。
2. **六类图**：相同模型脚本、截图与设备替身，对比原请求文本、图片顺序、计划前缀、
   描述、云端计数、物理动作序列与结果，分支在图中可见。
3. **并发/异常**：三路重叠、无下步不预测、直接动作不调用模型、join 后重规划、
   旧预测不误执行、预测异常消费/丢弃、summary 优先错误、取消/异常清理与隔离。
4. **动作/预算**：首轮双动作、逻辑轮次和独立物理预算、十次 Delete、广播输入、
   decoder 多动作/finished/非法动作原行为；Home 初始化单独记物理证据。
5. **作者入口**：精简 YAML/Python canonical hash 与运行等价、构建无副作用、
   默认 SDK 依赖生命周期及 clean wheel。通过前不称 YAML 完整流程可运行。
6. **真实接入**：部署确定后再验证模型坐标、输入法、真实动作；当前替身不证明真机、
   任务正确率、论文效果或全部模型变体。Benchmark PASS 由独立 evaluator 判断。

如果最小修复后仍不能形成可解释、实际可运行的对应基线，不加入最终 LOC 比较样本。
原代码的可控执行不自动增加真机验收完成数量。

## 本轮实际证据

本轮新增研究脚本、结果和本文，更新旧调查中的精确输入/并发结论；未修改生产插件、
YAML、Kernel 或已有 Agent，没有统计候选 LOC、更新论文实验或宣布新增完整 Agent。

```bash
PYTHONPATH=. conda run -n unimobile python output/research/next-agent-after-androidarena-20261022/source_checks.py
PYTHONPATH=. conda run -n unimobile python output/research/ecoagent-online-design-20261022/design_checks.py
```

第一项重新核对 Git blob/SHA-256、12 来源文件/9 Python 语法与原 3 条闭环分支。
第二项 source_edges、source_transport、graph_io_mechanism 断言均通过，保存于
`output/research/ecoagent-online-design-20261022/design-check-results.json`。
HTTP、截图、ADB 和模型是替身，线程池与 Graph Kernel 是真实执行。
`full_ecoagent_graph_executed=false`、`production_implementation=false`；
默认 SDK/YAML 依赖生命周期不属于本轮已验证证据。

已验证认识：顺序图节点能提交运行期异步 I/O，但须显式依赖和清理，不等于图调度器
已支持并发节点。本轮不更新 interview 的完整 Agent 支持结论或论文效果声明。
