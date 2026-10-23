# AutoDroid 在线执行

当前实现是参考 AutoDroid 在线机制的独立重写，**尚未与固定上游提交达到行为
对齐**。2026-10-19 的核对已发现正常输入、提示/历史、记忆、扫描、恢复和预算等
明确差异，不能把自身执行测试当作原版等价复现。完整来源与 43 个对照探针见
行为核对报告 (not bundled in the core source)。

本实现把 AutoDroid 的在线策略放入已有六类组件契约，由普通 AgentGraph 执行。
新增 Perception、Memory、Reasoning，复用 ActionExecutor、模型客户端、观察服务、
预算和轨迹。Planner、Verifier 在该模板中不启用：额外规划或反思会改变原策略。
BenchmarkTask JSON 仍独立负责初始化和外部评价；Agent 输出 DONE 只代表自行判断完成。

## 代码与执行顺序

| 位置 | 职责 |
| --- | --- |
| `zhixing/autodroid.py` | 无副作用的 SDK 图工厂 |
| `examples/graphs/autodroid_online.yaml` | 77 行组件与连接定义，与默认 SDK 图具有相同 canonical hash |
| `zhixing/plugins/agent/perception/autodroid.py` | XML → HTML 风格选项、控件和滚动容器身份 |
| `zhixing/plugins/agent/memory/autodroid.py` | 接收任务与真实 ActionResult 历史，首次 READ 检索 App Memory |
| `zhixing/knowledge/autodroid.py` | 原始表/规范格式读取、余弦检索、可选 INSTRUCTOR 后端 |
| `zhixing/plugins/agent/reasoning/autodroid.py` | 跨轮扫描、快捷路径、提示注入、模型选择和当前帧定位 |
| `zhixing/plugins/agent/parsers/autodroid_action_parser.py` | 严格解析模型选项，格式错误返回失败 |
| `zhixing/plugins/agent/autodroid_types.py` | 组件内部 DTO 和运行状态，不增加图角色 |

图外层使用现有有界 Loop。每轮 State READ 取上一轮 ActionResult，经 Memory 写入；
DeviceObserve 采集截图/XML，Perception 编码，Reasoning 返回一个 Action，
ActionRequestAssembler 将观察与动作组合交给既有 AndroidActionService。
State WRITE 保存该执行结果，终止结果结束循环。

YAML 采用通用的[简洁图写法](graph-yaml-authoring.md)：节点名作为键，
组件写 `namespace:name`，普通连线写 `source.port -> target.port`。
空参数、`primary: false`、默认生命周期和单候选绑定包装不用写。原先 322 行是
完整 IR 序列化，现已替换；循环边界、跨轮状态、显式控制边和非默认预算仍可编辑。
编译后图指纹保持
`sha256:f6c3b3f89d6b005ce9c99269afa94f84166b286e05c3a8b9b29fbe90f1eb35fd`。

扫描阶段依次滚动到顶、向下收集、恢复到顶。达到 `max_scrolls` 后仅保留有界范围内
已见控件，不声称遍历整页。Reasoning 每次只返回一个 SWIPE，扫描时不调用 LLM；
每次滚动都计入真实交互预算并产生执行记录。选择离屏选项后，逐轮重放滚动前缀，
再在当前观察中按身份匹配目标，重新计算坐标。恢复位置不匹配、身份不唯一或输入
选项不是可编辑控件时明确失败。

余弦相似度达到 `shortcut_threshold` 时尝试一次记忆路径，路径执行后仍由模型
判断是否完成。路径无法匹配当前界面时回退到正常决策；实际设备失败则停止。
明确观察到其他单一应用包时，通过标准 START_APP 恢复目标应用。

本次还修正了通用 Kernel 的一个已有调度缺陷：多值端口收到首个值后，必须等待
其他普通数据来源结束，才能调用组件。否则 Memory 可能漏收较晚到达的动作历史。
修正适用于全部图，没有 AutoDroid 条件分支，并有独立的延迟输入/条件省略测试。

## App Memory 输入

`examples/autodroid/app_memory.json` 是格式示例，包名和界面文案为虚构值，不能用于
证明某个真实应用的任务成功。实际运行需要与设备上的应用版本相匹配的记忆。

规范文件示例：

```json
{
  "schema_version": 1,
  "app_id": "org.example.notes",
  "embedding_model": "hkunlp/instructor-xl",
  "embedding_instruction": "Represent the task for retrieval: ",
  "entries": [{
    "id": "create-note",
    "task": "Create a note",
    "function": "Create and edit a note",
    "path": [{"description": "<button>New note</button>"}]
  }]
}
```

`entries` 必须非空、ID 唯一。可提供 `embedding` 数组，所有缓存向量须使用相同模型、
编码指令和维度；未提供时首次检索生成。检索是稠密向量余弦相似度，没有关键词降级。
`top_k` 默认 3，快捷路径阈值默认 0.95；这些是本实现的可配置策略值。

路径 Target 可以使用当前 Perception 的稳定 `key`，或无临时 id 的 HTML
`description`。支持 `tap`、`input`（附 `text`）、`back` 和 `scroll`；滚动需要明确
容器 key 和逻辑方向。可选 `state_id` 限制目标所在状态。坐标不存入记忆路径。
`equivalent_groups` 可按当前状态 ID 显式声明等价控件 key；只合并类型、交互性和
滚动前缀相同的选项。本次不生成 UTG，也不自动推断功能等价关系。

上游目录需要三个文件：

```text
node_filtered_elements.json  [app][state] = {path: [HTML...], elements: [HTML...]}
element_description.json     [app][state] = [function...]
embedded_elements_desc.json  [app][state] = [[float...], ...]
```

平行数组长度必须一致，缺少功能或向量的条目跳过，无有效条目则失败。
`app_state_summary.json` 不参与当前在线读取。上游表可能使用应用简称作为 app key，
与 Android 包名不同；用 `memory_params={"upstream_app": "简称"}` 显式区分。
旧缓存查询保持上游的空指令及 `task: ` 前缀，不混用规范文件的编码指令。
旧 DroidBot 状态 hash 不转换为本实现的 XML 状态 hash。HTML 描述不同或应用改版
会导致路径不匹配，不能宣称原始记忆对任意版本直接可用。

## 使用

在仓库根目录、项目环境中安装需要的可选后端：

```bash
python -m pip install -e '.[openai,autodroid]'
```

INSTRUCTOR 采用其旧版 SentenceTransformers 接口，因此 `autodroid` extra 声明了
配套的版本约束，`all` 包含这些约束。使用不同模型栈的环境应先检查依赖解算。
当前验证覆盖惰性加载接口，尚未安装和实测这一可选模型栈或下载 checkpoint。

先做只校验图的 dry run：

```bash
python -m examples.sdk.autodroid_online \
  --memory examples/autodroid/app_memory.json \
  --app-id org.example.notes --dry-run
```

预期打印图 hash 和 `execution_evidence: false`。该操作不读记忆、不连接设备、
不解析密钥、不加载模型。图 YAML 的相对 memory_path 按运行工作目录解析；
实际使用建议传入绝对路径。

SDK：

```python
import os
from zhixing.autodroid import build_autodroid_graph
from zhixing.sdk import AgentRunConfig, compile_agent

graph = build_autodroid_graph(
    memory_path="/absolute/path/to/app_memory.json",
    app_id="your.android.package",
    max_steps=100,
    memory_params={"top_k": 3, "embedding_device": "cpu"},
    reasoning_params={"max_scrolls": 7, "shortcut_threshold": 0.95},
)
agent = compile_agent(graph, secrets={
    "api_key": os.environ["OPENAI_API_KEY"],
    "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
})
result = agent.run("Your task", AgentRunConfig(
    serial="your-selected-device",
    max_steps=100,
    include_ui_tree=True,
))
```

也可以用 `load_graph_yaml(...)` 或 `load_agent(...)` 读取图 YAML。
必须启用 `include_ui_tree=True`。未提供记忆、嵌入后端不可用或模型出错会显式失败，
不会静默改用另一个 Agent。所有密钥只在运行绑定时传入。

执行命令：

```bash
python -m examples.sdk.autodroid_online \
  --memory /absolute/path/to/app_memory.json --app-id your.android.package \
  --serial your-selected-device --task 'Your task' --max-steps 100
```

预期打印 run ID、执行状态和交互次数，证据默认写入 `temp/autodroid-runs`。
图和运行配置的交互预算分别生效，采用更小者；扫描和应用恢复也消耗预算。
`max_steps` 为 1–998，图循环额外预留一次无设备副作用的终止决策。

## 验证与限制

2026-10-19：专项 37 项通过；runtime/graph/components/资源/依赖与安装检查 221 项
通过（包含专项），共享 Catalog/Studio 后端兼容检查另 48 项通过，共 269 项。
最后一项 HTTP 检查需要沙箱外的本机临时监听权限，单独运行通过。

```bash
conda run -n unimobile python -m pytest \
  tests/runtime/test_autodroid_online.py \
  tests/runtime/test_multiple_input_readiness.py \
  tests/packaging/test_autodroid_install.py -q
```

已验证：五页 fake Android 图运行、全部页选项进入提示、恢复后重放并在第五页当前
坐标点击；测试特意让目标从采集时的 `(50,70)` 移至重访时的 `(50,90)`，执行器
最终使用新坐标。该案例共 29 次确认交互，包含 24 次扫描及 5 次决策路径交互，模型调用
两次。另有快捷路径、格式错误、无效 ID、重复身份、向量维度、原始记忆表、
运行隔离、历史同步、预算和设备失败测试。

wheel 验证使用全新 venv，只从本机解释器复制明确列出的基础依赖发行文件，再以
`pip --no-index` 安装 wheel；不继承开发环境 site-packages。安装后的包在仓库外
执行 TAP → TEXT → BACK → DONE，确认包内提示、默认 SDK/YAML 图 hash 和惰性导入。
这证明安装包的执行闭环，不证明 PyPI 在线解算或 INSTRUCTOR 真模型推理。

本实现依据 [AutoDroid 论文](https://arxiv.org/html/2308.15272v4) 的在线机制及
[官方代码](https://github.com/MobileLLM/AutoDroid/tree/newbranch) 独立重写。
2026-10-19 检出的上游 `newbranch` 提交为
`839b824774173d8e6373b48fc7b82f55f3bf77ae`。该提交的滚动扫描逻辑是启用的，
三引号只是扫描前后的独立说明字符串；此前把它们描述为禁用块是不准确的，现予更正。
TaskPolicy 默认关闭 memory。本实现不声称与该入口逐行或逐轨迹等价；提示模板、
稳定身份和失败策略也有明确工程取舍。

本次未验证真实 Android、真实嵌入/LLM 效果、原论文 benchmark 成功率、离线探索、
任务合成或微调。不支持无可用 XML 的纯视觉/WebView 控件；嵌套滚动和动态布局可能
导致恢复失败；跨屏重复且同身份的控件无法可靠区分；多包 XML 无法唯一确定前台
应用时不作包名恢复；TEXT 沿用现有执行器，未证明清空原文本、Unicode/IME 等价。
没有新增 Studio 专用编辑界面、旧 AgentConfig 编译策略或 Benchmark 评价契约。
