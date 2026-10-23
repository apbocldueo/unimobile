# AndroidGen 完整在线执行

用户授权 Coding Agent 在现有六类组件和 AgentGraph 中实现 AndroidGen，尽量复用并
对齐官方在线逻辑。本轮实现对象为 [THUDM/AndroidGen](https://github.com/THUDM/AndroidGen)
提交 `3f511cff18a842e6583ac7e7d9cabd217c5d3b1b` 的 **`run.py` 单任务在线流程**。
设计调查见 [开发前方案](androidgen-online-design.md)。

当前证据是生产 SDK/YAML/组件在假设备和脚本模型下实际执行，以及与冻结官方源码
的对照。真实 AndroidWorld 模拟器、真实模型 API、Contriever 权重下载/模型质量和
Benchmark 任务正确性尚未验收。StepCritic 经验库自更新不属于本轮 `run.py` 范围。

2026-10-22 后续LOC审计：对应官方在线核心 **734 Python SLOC**，单文件新增
装配 **27 SLOC**；tooltip修复为 **1行替换、净增0**，实际可运行单文件 **761 SLOC**。
首次YAML **74行**；后续压缩为 **59行**，完整AgentGraph不变。精简后83项测试和
22组单文件/实际YAML对照通过，原未修复版正常运行及tooltip缺陷复现分别保留。
精简证据见 复验报告 (not bundled in the core source)。
计数/范围与完整新增成本见
LOC报告 (not bundled in the core source)。

## 原流程与现在的图

原版由 `run.py` 循环调用 `Env.get_current_state → Agent.__call__ → Env.interact`，
再更新 Agent 和 Recorder。现在这些步骤分别由标准 Graph 节点调度：

```text
Task → ActionExecutor:setup → Memory/Knowledge:一次 ExpSearch
  → 外层 Loop
      State 恢复 → Memory 写上一轮两个片段并读完整历史 → Router
        结束：纯历史 flush → State 提交
        继续：显式观察 → Perception:UI 文本/SoM
          → Planner:初次生成 / 更新（空更新由嵌套 Loop 重试）
          → Verifier:上一轮 fail 的 AutoCheck 反馈
          → Reasoning:原角色消息和一次动作决策/代码块提取
          → ActionExecutor:原 Python 协议、检查和实际动作
          → Memory:原记录、待写消息、轮次及 exit → State 提交
  → Memory:发布源结果和轨迹
```

六类角色均实际参与。没有新建 Agent.step 子类，没有为 AndroidGen 修改 Kernel、
通用编译器、已有 Agent 或独立 BenchmarkTask JSON。额外阶段端口使用既有合同
扩展机制，不改核心 Planner/Verifier DTO。

| 组件家族 | 文件/职责 | 复用与必要适配 |
| --- | --- | --- |
| Perception | `plugins/agent/androidgen/perception.py` | 直接复用 M3A 的 UI 转换、像素读写与 SoM 标记；新增官方 `<element>` 格式和过滤 |
| Planner | `plugins/agent/androidgen/planning.py` | ReflectPlan 原提示、正则和生成/更新分支；每次激活只调用一次模型 |
| Reasoning | `plugins/agent/androidgen/reasoning.py` | 原 system/history/current 协议和第一段 Python 代码块；没有解析重采样 |
| Memory | `plugins/agent/androidgen/memory.py` | **原样复用 sliding_window_memory，窗口 62**；新增 Recorder 片段/提交薄适配 |
| Verifier | 同一 `reasoning.py` 的 `androidgen_feedback` | 规划后整理上一轮 fail 原文，无额外模型、截图或立即重试 |
| ActionExecutor | `execution.py`、`environment.py`、`source.py` | 原动作方法和校验顺序；外部 AsyncEnv/ADB 经显式、按实例绑定的边界执行 |

表内生产文件均位于 `zhixing/` 下。其他入口：

- `zhixing/androidgen.py`：纯构图 API，支持独立规划/动作模型与 text/image 配置。
- `examples/graphs/androidgen_online.yaml`：显式组件、端口和连接，默认与 SDK 图身份一致。
- `zhixing/graph/androidgen_contracts.py`：数据端口和副作用声明。
- `zhixing/knowledge/androidgen.py`：惰性经验库/Contriever 适配，不增加第七个核心角色。
- `zhixing/plugins/llm/androidgen_llm.py`：惰性原 GPT 消息/传输协议。
- `source-origin.json`、`LICENSE`、`tests/fixtures/androidgen/manifest.json`：来源、许可、
  原文件哈希及单列兼容差异；原始夹具没有修补。

不能仅换参数复用通用 Planner/Reasoning/Verifier：它们的历史、计划更新、动作解析或
反思重试策略不同。AutoDroid 的索引也不能替代原 Contriever 未归一化点积检索。

## 必须保留的源行为

- ExpSearch 在启动时只查询一次，按 `complete` 和 `env` 过滤。App/init_state 过滤
  在源代码已注释；同任务示例默认允许。无匹配/关闭时使用原 default_example。
- Contriever 使用 attention-mask 均值、原始向量点积和 `torch.topk`；没有查询前缀
  或余弦归一化。checkpoint 编码器通过外部依赖注入或在首次真实检索时加载。
- Planner 读取此前**全部 assistant 响应**；actor 只取最近 **20 条消息**，再加固定
  两条任务开头。历史是 Recorder 原始响应，不是通用 Action 的文本归一化结果。
- 首次计划解析为空仍进入本轮动作；已有计划更新为空时，使用同一观察和同一提示
  重试。计划全部 Done 不会停止 Agent，原 `exit` 才是停止声明。
- AutoCheck 关闭只影响错误消息注入。原动作检查始终保留：空文本输入先点击，再
  返回失败；Swipe 转成相反方向 Scroll；清空文本的 ADB 顺序和逐字符输入保留。
- `quote` 和失败都消耗逻辑轮。代码块内多条 Python 调用仍按原协议执行，最后的
  `current_return` 为该轮结果。没有替换成单条 JSON 动作，也没有第三方代码沙箱。
- 缺代码块在 interact 外致命失败；代码执行 Exception 转成原 fail 并在下轮反馈。
  不产生结果的代码返回 None，先保存该轮记录，随后按原停止检查失败，不自动重采样。
- 原独立循环从 0 开始且 `<=30`，默认 **31 逻辑轮**。最后再做一次纯 Memory flush，
  不观察、不调用模型、不操作设备。两个记忆片段有显式顺序依赖，保证 user 在前。

## 明确差异与限制

1. **兼容修复**：原 `_format_element` 的非空 tooltip 分支引用未赋值局部变量；仅改为
   `ui_element.tooltip`。测试保留原 UnboundLocalError，并检查修复后的文本及索引。
2. **有界更新重试**：原更新计划可无限重试；Graph 默认最多 3 次，可设 1–20。
   耗尽返回 `runtime.loop_exhausted` 运行失败，不能当作原 fail 反馈或正常任务完成。
3. **模型配置与密钥**：提供原 GPT transport 的惰性适配，默认
   `gpt-4o-2024-08-06`，独立于源仓库默认 human 演示配置。去除导入时 `.token`
   加载，运行时原 constructor 从 `OPENAI_TOKEN` 读取。Human/Vllm 可通过显式
   generate 协议自行注入，本适配不提供它们的原生选择器。原 GPT 退避可能持续重试，
   没有擅自增加传输次数限制；旧模型当前可用性尚未验证。
4. **产物与生命周期**：源目录可变 cache/时间戳 JSONL 改为运行服务的不可变图片、
   `androidgen-records.json`（`records` 列表）和 `androidgen-episode.json`。观察 I/O
   与编码分离，原图先入库以保留失败证据；成功输入文本/图片通过对照。环境由调用者
   创建和关闭；示例 finally 在致命异常时也清理，较原正常路径 close 更明确。
5. **依赖边界**：UI/SoM 使用当前已固定的 M3A/AndroidWorld helpers，提交
   `f8e78c0ab0bb8b5daa681afd0296ed0193a98f1f`。上游 AndroidGen 没有固定所有
   AndroidWorld 版本，本轮对照依赖是这一明确版本，不推出任意第三方版本等价。
6. **停止与计数**：源 `exit` 映射 Agent SUCCESS，预算结束映射 STEP_LIMIT；
   `benchmark_evaluated=false` 始终单列。SUCCESS 只表示声明退出，不是任务 PASS。
   框架交互数按产生作用的**代码块**加一，多个底层调用记录在 acknowledgment；
   不应解释为原始 ADB 命令数。quote/exit 无物理输入时不递增。失败调用可能已产生
   部分作用，元数据保留未知标志，不能推断回滚。
7. **后续范围**：StepCritic 不被普通 run.py 调用；不包含跨任务经验库更新、真机
   验收、任意 Agent 范式、真实模型成功率或统计显著性。实现时未统计LOC，后续审计见本文开头链接。

Data-only Frame/State 存计划、原响应、记录和资源路径；模型、编码器和环境实例
留在依赖/边界中。已去除未被算法读取的 UIElement.metadata；不将 API 客户端或
密钥写入证据。源可信 Python 的任意调用仍需由使用方控制其运行环境。

## 验证与人工复现

构图不会连接设备、读经验库/密钥、加载模型或导入重型可选模块：

```bash
conda run -n unimobile python -m examples.sdk.androidgen_online --dry-run
```

预期 `execution_evidence=false`，默认图指纹为
`sha256:4da70e4db2b0848035b21c9ed4c3d9a05f690b1d207cf216b97192389cf55729`。

具备测试依赖时可执行：

```bash
python -m pip install -e '.[androidgen,androidgen-retrieval,dev]'
python -m pytest tests/runtime/test_androidgen_online.py -q
python -m pytest tests/packaging/test_androidgen_install.py -q
```

专项测试当前 70 项：原 Agent/Plan/Env/Recorder 完整在线对照；四种规划/动作
text/image 组合；原图片逐像素、提示/消息/历史/作用顺序；全部动作和异常；空计划
分支；31 轮与最终 flush；同一 SDK recipe 跨运行隔离；库过滤、真实张量池化/点积；
实际 GPT wrapper 与原 wrapper 在替身 SDK 下生成同一消息/图片/sampling 请求；
原可执行 AST 与提示常量对照。没有从 mock 的 return 值推断真实服务已经可用。

本轮 `unimobile` 缺 backoff，验证时仅将其 2.2.1 官方 wheel 解压到临时测试目录，
通过 PYTHONPATH 使用，没有修改用户 conda 环境。上述安装声明 extra 的方式也可
复现。未安装 backoff 时，单个 transport 测试会明确 skip，其余边界测试仍可执行。

安装验收实际构建 wheel，在与仓库无关的干净 venv 中先做 base-only 编译，确认
不导入 NumPy/OpenCV/Torch/Transformers/AndroidWorld/OpenAI/backoff；再离线复制
已安装的声明视觉依赖，执行完整 YAML：2 个逻辑轮、2 次动作模型调用、3 次规划
调用（含空更新重试），真实读取测试经验库，保留 4 条历史。只替换外部模型、ADB、
AsyncEnv 和 checkpoint ranker；没有真实 checkpoint 或网络模型调用。

2026-10-22 最终验证：专项 **70 项**通过；Graph/SDK/Catalog 与既有 Agent 回归
**434 项**通过；AndroidGen/M3A 两项独立安装验收与依赖/资源 11 项检查通过。
最后一批包含 70+2+11，共 **83 passed、0 skipped**；两批合计 517 项。
现有 M3A YAML 字节哈希及默认图身份保持不变；新函数 docstring 检查通过。
没有声称全仓测试或真实设备验收。

本轮完整命令（标准安装声明 extra 后无需临时 PYTHONPATH）：

```bash
python -m pytest tests/runtime/test_androidgen_online.py \
  tests/packaging/test_androidgen_install.py tests/packaging/test_m3a_install.py \
  tests/packaging/test_dependency_profiles.py tests/packaging/test_resources.py -q
python -m pytest tests/graph tests/sdk tests/catalog \
  tests/runtime/test_builtin_catalog.py tests/runtime/test_graph_runtime.py \
  tests/runtime/test_android_graph_runtime.py tests/runtime/test_m3a_online.py \
  tests/runtime/test_autodroid_online.py tests/runtime/test_seeclick_online.py \
  tests/runtime/test_agent_sama_online.py tests/runtime/test_agent_sama_official.py \
  tests/runtime/test_vdroid_selection.py -q
```

第一条预期 83 项；第二条预期 434 项。安装测试为避免网络安装依赖干扰，复制当前
解释器中已安装的声明依赖进入干净 venv，再以 `--no-index --no-deps` 安装新 wheel；
不等于已验证在任意新机器上从 PyPI 解析所有 extras。

## 真实执行入口（尚未运行）

先按选定 AndroidWorld 版本安装完整官方依赖、模拟器和 App；`[androidgen]` 不会
替代它。准备实际 JSON 经验库、本地 Contriever checkpoint 和 `OPENAI_TOKEN`。
以下是运行说明，**不是本轮已执行的真实实验**：

```bash
python -m examples.sdk.androidgen_online --task 'Open settings' \
  --database /path/to/experience.json --checkpoint /path/to/contriever \
  --console-port 5554 --grpc-port 8554 --adb-path /path/to/adb \
  --serial emulator-5554
```

默认 YAML 的经验库路径为 `data/androidgen/experience.json`，checkpoint 为
`facebook/contriever-msmarco`；必须提供实际资源或通过参数/依赖替换。仓库没有假装
附带官方完整经验库。命令行要求显式传入 database/checkpoint，避免误把占位配置当
成可运行资源。`--no-expsearch` 只用于原配置消融，不作为完整配置的验证证据。

SDK 直接持有官方环境时：

```python
from zhixing.androidgen import build_androidgen_graph
from zhixing.plugins.agent.androidgen.environment import AndroidGenEnvironment, AndroidGenAdb
from zhixing.sdk import compile_agent, AgentRunConfig

agent = compile_agent(build_androidgen_graph(example_params={
    'database_path': '/path/to/experience.json',
    'retriever_ckpt_path': '/path/to/contriever',
}))
try:
    result = agent.run('Open settings', AgentRunConfig(max_steps=32),
        device=AndroidGenEnvironment(official_async_env,
            adb=AndroidGenAdb('/path/to/adb', 'emulator-5554')))
finally:
    official_async_env.close()
```

注入已创建的 AsyncEnv 默认不额外 reset，与原注入路径一致；需要原内部创建环境的
Home 准备时设 `reset_on_setup=True`。准备阶段仍保留禁用 Google 输入法/TTS 的原
命令。`AgentRunConfig.max_steps` 应留出源末轮提交空间（默认 32），较低预算会提前
中断。独立 BenchmarkTask 的初始化、真实任务评估仍由 Benchmark 产品线承担。
