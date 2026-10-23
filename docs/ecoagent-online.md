# EcoAgent 在线 AgentGraph

2026-10-22。用户在完成源码设计调研后授权开发；本变更实现官方默认
`eco_ui-tars` 在线流程。**已通过模拟设备/模型下的官方差分、完整图、YAML 和安装包
执行检查；尚未做真实模型、真机或 Benchmark 正确率验收。**

## 范围与来源

论文：[EcoAgent, AAAI 2026](https://ojs.aaai.org/index.php/AAAI/article/view/40230)。
官方：[Yi-Biao/EcoAgent](https://github.com/Yi-Biao/EcoAgent)，固定提交
`d9b16afb4ccaf3beb59664984dab2aa258b3cccf`。
论文主表使用 ShowUI/OS-Atlas，当前实现选择官方 CLI 默认 UI-TARS 分支，不能将本次
验收说成论文表格复现，其他底座不在本次已验证范围。

原项目的完整 CLI、ECO.step、外层循环、模型封装、提示和动作 decoder 均已公开。
冻结 12 个原文件于 `tests/fixtures/ecoagent/official/`，SHA-256 清单另存于
`tests/fixtures/ecoagent/source-origin.json`；没有修改这些原始文件。
兼容修复为旁置 `compatibility.patch`，只应用到临时副本。

生产路径中的 prompts.py 为原提示常量；_decoder.py 保留原纯解析算法，扩充文档。
测试在忽略 docstring 后比较 AST，验证没有改算法语句。source-origin.json、
compatibility.json、LICENSE 和 NOTICE 随包发布，保留原 MIT 归属及 infer.py
继承的 AndroidWorld Apache 来源说明。

## 运行前后与六类职责

此前只有来源调查与小型并发机制实验。现在完整流程经 SDK/YAML 进入普通 AgentGraph：

```text
初始化 → Home → 截图 → 初始规划 → 首步推理/直接指令 → 执行 → 等待 → 截图
  → 有界验证轮次：
      提交界面描述 → 提交前后图摘要 → 可选提交下一步预测
      → 收摘要 → 收描述 → 记录描述并等待全部请求结束
      → Router：接受则继续旧计划；否则云端重规划
      → Router：到计划末尾则结束；否则选定动作 → 执行 → 等待 → 截图
      → 推进逻辑索引 → State 写回
  → 原完成条件成功，或逻辑预算耗尽
```

六类节点与文件：

| 类别 | 实现职责 | 复用边界 |
| --- | --- | --- |
| Perception | 显式截图、原界面描述请求提交/收取 | DeviceObservation、运行产物、既有 Android screenshot |
| Planner | 初始计划、expectations、失败重规划、前缀拼接 | 模型依赖、SecretRef、typed invoke |
| Reasoning | 当前动作推理、下一步预测及按分支消费 | 独立模型服务与便携回复，不直接碰设备 |
| Memory | 初始化、恢复、描述累计、join、索引推进、结果投影 | 普通 RUN State/Loop/Router，无新记忆数据库 |
| ActionExecutor | Home、原直接动作/decoder、两秒等待、ack | 既有 AndroidDevice.shell、目标 serial 和 ActionResult |
| Verifier | 两图+expectation 摘要，原 not-word 判定 | 图片合同、显式模型依赖 |

没有添加第七类 Agent role，没有编辑 runtime/kernel.py 或六类枚举，没有改 Studio
和 BenchmarkTask JSON。现有组件仅改参数不足以保留原规划协议、判定规则及预测消费，
因此添加六类内部的薄策略适配。设备与模型基建沿用既有边界。

## 并发、状态与错误

图节点仍顺序激活；提交节点立即返回字符串 ticket，实际 I/O 在调用者拥有的
InferenceJobs 中并发。下一节点不会等待上一个请求完成。Perception/Verifier/Reasoning
分别组装和解释自己的请求，helper 不理解 Agent 任务或重规划，也不藏一个 ECO.step。

使用 `with EcoEnvironment(device) as boundary` 包住一次 run。该对象持有选定设备和
私有、惰性的 I/O helper，进入时不连接设备/创建线程；首个 submit 才建池。每个
helper 只能被一个 run_id 认领，ticket 限定 round，退出时等待并关闭全部工作。
SDK 不会自动关闭任意注入依赖，这里由显式 context manager 保证生命周期。
同一边界可先退出后再次进入，下一次会得到新的 helper。

验证摘要先收，描述再收，然后 join 所有已提交工作才允许重规划。summary 失败时
仍等已提交的描述和预测结束；description 失败同理。被新计划丢弃的预测即使失败，
也不升级成 Agent 失败；继续旧计划而消费它时才传播安全错误。取消发生在节点边界，
退出会等在途 HTTP 返回或 timeout，不能声称即时取消模型计算。

Future、模型客户端、设备句柄只在运行边界中，State 与输出不包含它们。工作线程
返回 usage，主调用线程统一记账，包含丢弃的成功预测，避免 ContextVar 在线程中
丢失或共享计数竞争。source llm_calls/total_tokens 只统计云端规划，保持与官方一致。

## 保留规则与单列修复

保留官方行为：

- summary 中没有独立单词 `not` 就接受，包括 `No`；不换成通用 Yes/No 或 A/B/C/D。
- 仅精确 `No need to replan.` 继续原计划，尾随换行不被接受。
- 重规划保留已执行前缀，新剩余步骤重新推理，即使文本与旧预测步骤相同。
- 重规划模板没有 summary 占位符，不擅自添加。它收到完整 descriptions 和当前截图。
- INPUT 走 ADB Keyboard 广播；DELETE TEXT 是十次退格，不保证清空任意长文本。
- decoder 允许一个回复含多个动作；未知动作跳过，finished 只结束当前 decoder 块，
  不直接结束 Agent。open_app 仍没有被悄悄补成官方能力。

独立记录的修复/适配：

| 变更 | 处理及比较界限 |
| --- | --- |
| CLI send_home 重名 | 临时官方副本重命名无参旧函数；框架用显式设备 Home |
| 小写 JSON fence、空格 point 标签 | 默认修复，可由 build_ecoagent_graph(fix_protocol=False) 关闭；不缩放坐标 |
| 模型错误无限重试、3/4 tuple 不一致 | 临时官方副本补有限计数/timeout/失败元组；生产使用单个标准库 HTTP 适配和 EcoReply |
| 非法/空/缺 expectation 计划 | 图明确失败，不继续访问未初始化截图或越界索引；这是错误路径改动，不能宣称原版完全等价 |
| serial 和共享截图路径 | 走已有选定 AndroidDevice 与每 run 观察产物；不保留裸 adb/共享 screen.jpeg |
| 设备错误 | 保存部分执行证据，映射框架 DEVICE_FAILURE，不泄漏底层错误内容 |

原始有效输入与未修复原循环差分；协议修复与旁置补丁后的临时原循环差分。
异常策略改动单测并披露，避免把框架修复算成原始官方代码。

## 预算与精简 YAML

官方默认 30 个逻辑验证轮次。初始首步在循环前执行，首个验证轮次可能又执行下一步。
加启动 Home，最坏有 32 个高层执行 acknowledgment；Kernel 在达到物理上限时停止，
因此图保留 33 的物理阈值。解码回复的多条 ADB 指令属于同一高层动作 ack，不能把
interaction_count 解释为原始 ADB 调用次数。两轮验证、三条任务动作的边界已覆盖。

`examples/graphs/ecoagent_online.yaml` 当前 **59 个物理文本行**，不是 Python SLOC。
默认参数省略，锚点复用合同与模型绑定，循环、分支、State 和连接仍完整展开；没有
通过单个工作流预设插件隐藏 Agent 控制流。YAML/Python 图对象与 canonical hash 相同：

`sha256:a0e982a758d4b9856d204fb7e6433c2479ee1c4248c02f89d708037a39bcba5e`。

后续已完成 LOC 审计：官方核心 455 Python SLOC，提取装配 15，兼容替换 7 行净增 0，
可运行文件 470，YAML 59 行；29 组隔离单文件/实际 YAML 对照通过。通用模型传输
115、配置加载 25 和框架额外组件成本另列，见
完整统计报告 (not bundled in the core source)。

## 已执行验证

- 专项 **58 passed**：原定义/原外循环差分、旁置修复差分、完整官方 CLI 实际导入与
  受控执行、源文件哈希、模型请求/图片顺序、直接动作、重规划、丢弃/消费异常、
  并发 barrier、join 时序、主线程用量、取消、运行隔离、设备失败及 YAML/构建检查。
- 安装 **1 passed**：当前 wheel 在仓库外新建 venv，离线安装并只复制基础依赖，
  dry-run 不导入模型/设备可选包，安装后的 YAML 执行失败反馈→丢弃失败预测→重规划→完成。
- 相关运行时/既有 Agent 组合回归 **229 passed, 2 skipped**；两个 skip 分别为
  AndroidArena 真实 tokenizer 的显式开关、AndroidGen 未安装的可选 backoff。
- graph/components/catalog 回归 **182 passed**。上述分组有重叠，不直接相加。

当前 conda unimobile 没有 AndroidArena 参考所需 xmltodict/tiktoken；组合回归按
该 Agent 既有文档复用了 `/private/tmp/zhixing-androidarena-deps`。未使用该参考目录的
首次组合运行出现依赖不可用失败；未为此改动 AndroidArena 代码。EcoAgent 自身专项
和安装验证不依赖该目录，不添加新必需包。

复核：

```bash
PYTHONPATH=. conda run -n unimobile python -m pytest tests/runtime/test_ecoagent_online.py tests/runtime/test_ecoagent_components.py tests/runtime/test_ecoagent_io_jobs.py tests/graph/test_ecoagent_yaml.py -q
PYTHONPATH=. conda run -n unimobile python -m pytest tests/packaging/test_ecoagent_install.py -q
PYTHONPATH=. conda run -n unimobile python examples/sdk/ecoagent_online.py --dry-run
```

预期分别为 58 passed、1 passed，以及上述 graph_hash 和 execution_evidence=false；
dry-run 不创建运行目录、解析凭证、连接设备或启动线程。

## 实际接入入口与未验证条件

先部署云端 planner、UI-TARS executor 与 observer 的兼容接口，确认其 model alias。
原 DEVICE_OBSERVER 是配置占位符，代码不替用户下载/部署模型。手机需已授权 ADB、
可用 ADB Keyboard；未在本次自动配置设备、输入法或任务初态。

```bash
PYTHONPATH=. conda run -n unimobile python examples/sdk/ecoagent_online.py \
  --serial YOUR_SERIAL --task 'YOUR_TASK' \
  --executor-model YOUR_EXECUTOR_ALIAS --observer-model YOUR_OBSERVER_ALIAS
```

云端凭证由运行时 OPENAI_API_KEY 提供，不写 YAML。自定义完整 chat-completions URL
使用 --planner-url、--executor-url、--description-url、--summary-url。图/CLI 默认
wait 两秒、max_rounds 30；实际 SDK run 需令 AgentRunConfig.max_steps 使用图的物理
预算，不用 SDK 默认 15 截断原流程。

加载 YAML 可使用 `load_agent(path, secrets={...}, discover_external=False)`；一次运行
仍须包在显式 EcoEnvironment 上下文中，并传入 device=boundary。直接改六类组件或
模型参数不需要修改 Kernel，但更换成论文其他模型分支不自动获得原策略对齐证明。

目前没有真实模型定位、坐标尺度、输入法、实际手机任务、Benchmark evaluator 或
论文延迟/成功率证据；本次不能据此增加“真机完成”的数量或写论文性能提升结论。
原 decoder 的引号/Unicode escape 限制仍保留，Android shell 也保留既有单行约束；
不宣称任意文本输出均可输入。模型直接 INPUT 广播与 decoder 的 type 路径应分别验证。
上述 LOC 审计保留来源与修复边界，不改变这些真实接入和效果证据限制。
