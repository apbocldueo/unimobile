# GUI-explorer 完整在线执行

用户确认六类角色对应和复用方案后，Coding Agent 实现了本页所述在线图、组件适配、
来源对照测试和安装包验证。来源为 [GUI-explorer 官方仓库](https://github.com/iLearn-Lab/ACL25-GUI-explorer)，
固定提交 `01338e8ccc1c21d9897642ba197c6ac177e90118`，论文为
[ACL 2025 主会长文](https://aclanthology.org/2025.acl-long.282/)。

**已实现并验证的是：生产 AgentGraph 在模拟设备、模型和检索边界下运行，所覆盖的
在线路径与未改写的官方循环对照，以及从隔离 wheel 执行实际 YAML。尚未进行真实
模型、知识库加载/向量检索或 Android 设备验收，不宣称论文成功率或全部输入等价。**
在线实现阶段没有进行 LOC 统计，也没有修改 Studio、执行内核、既有 M3A 组件或 Benchmark。
后续独立统计已完成：官方在线核心 1,116 SLOC，提取装配 15，实际核心单文件 1,131；
现有 YAML 71 行。53 组隔离对照、范围、外部服务和额外实现成本见
LOC 报告 (not bundled in the core source)。

2026-10-23 最终验证：本功能专项 73 项通过，GUI-explorer 隔离 wheel 验证 1 项通过；
合并 `tests/runtime`、`tests/graph`、`tests/contracts` 和 GUI-explorer/M3A 两个 wheel
测试后共 **996 项通过、2 项跳过**。跳过的是原有 AndroidArena 显式真实 tokenizer
检查和 AndroidGen 可选模型适配检查，不是本功能测试。原环境缺少的 AndroidArena
对照依赖只安装在临时目录，没有修改用户 conda 环境；最终测试命令/版本记录见
`output/validation/guiexplorer-online/report.json`，逐项结果见同目录 `final-validation.xml`。

## 执行与复用

官方 Python 类内部调度的任务循环现在由 Graph 的 Loop/State/Router 表达：

1. 复用 `m3a_resume` 恢复通用游标，判断终止或轮数上限。
2. 通过薄的来源标记适配，将前一步允许提交的总结写入现有
   `sliding_window_memory`；窗口覆盖整个任务，而不是压缩或截断历史。
3. 观察原始 UI、方向、屏幕/画框和截图，保留全列表索引，构造官方 SoM 与元素裁剪。
4. Memory 节点调用官方图像检索服务；按包名、top-k、阈值取得知识，不替换成文本 RAG。
5. Reasoning 排序节点运行官方两两比较和完整归并排序，保留全部知识。
6. 动作选择节点用官方提示、知识、全部历史、原图与 SoM 调用模型一次，交给图路由。
7. ActionExecutor 通过显式原始 Device 边界执行；成功后重新观察并用前后图总结。
8. 复用 `m3a_commit` 提交步骤，按官方规则决定是否进入历史，并在每个非终止轮后
   额外等界面稳定。末尾多一次图迭代仅用于历史 flush，不增加模型或设备调用。

活跃家族是 Perception、Memory、Reasoning、ActionExecutor；原在线方法没有独立
Planner 或结构化 Verifier，因此没有添加这两类算法。总结属于 Reasoning，不能视作
独立任务成功证明；BenchmarkTask JSON 继续独立定义初始化与评测。

原样复用的注册组件：`sliding_window_memory`、`m3a_resume`、`m3a_commit`、
`m3a_pass`。实际沿用 M3AFrame 游标与合同，GUIExplorerStep/View 扩展便携数据，
不是把无关类型仅改名成 M3A。五个 UI 描述/过滤/几何函数通过 import 复用现有定义，
图像读写也直接复用。原组件、公共标识和执行行为未改动。

| 位置 | 本次职责 |
| --- | --- |
| `zhixing/guiexplorer.py` | 无副作用 SDK 构图工厂 |
| `examples/graphs/guiexplorer_online.yaml` | 与默认 SDK 图完全相同的组件、连接及预算 |
| `zhixing/plugins/agent/guiexplorer/` | 来源感知、检索/历史、排序/选择/总结、设备/执行及便携数据 |
| `zhixing/knowledge/guiexplorer.py` | 调用作者已有检索服务的薄客户端 |
| `zhixing/plugins/llm/guiexplorer_llm.py` | WEBP 请求、响应存在性、比较模型及 token 记录 |
| `zhixing/graph/guiexplorer_contracts.py` | 来源节点合同；不添加组件角色或内核调度分支 |
| `source-origin.json`、`LICENSE`、`NOTICE` | 原文件哈希、选取定义、兼容差异及许可证 |
| `tests/fixtures/guiexplorer/` | 未修改官方文件，作为独立测试对照 |

## 分支与兼容边界

| 官方分支 | 本实现 |
| --- | --- |
| 格式、JSON、动作参数/上界索引错误 | 固定错误总结入历史，进入下一轮，不在节点内重采样 |
| 动作执行异常 | 保留原错误记录，跳过总结且不追加历史；仍执行 run 的轮末稳定等待 |
| 动作模型没有响应 | 原始 RuntimeError 对应 Run failure |
| 总结没有响应 | 固定错误总结入历史；成功空文本与无响应分开处理 |
| status complete / infeasible | 都停止；独立暴露 Agent 状态和 goal_status，不写成 Benchmark PASS |
| status 缺失/其他 goal_status | 保留官方 permissive 停止行为，原值保留在 evidence |
| answer / wait / unknown | 按官方分派后继续；answer 展示及原始空操作语义保留 |
| 预算为 0 / 耗尽 | 零轮无设备/模型/RAG 调用；耗尽前最后一个非终止轮仍有原始稳定等待 |

显式列出的兼容改动：

- 官方动作 HTTP 非成功响应分支可能无限重试；本实现让其消耗五次重试预算。
  原始请求设置和退避序列保留，失败响应内容不会进入公开错误。
- Pillow 10+ 的 `Image.Resampling.LANCZOS` 替代旧常量拼写；插值规则不变。
- 可选库延迟导入，模型/RAG/时钟成为明确依赖。已有异步宿主中，局部比较通过独立
  事件循环和复制的 usage context 执行，避免修改全局事件循环；组件接口保持同步。
- 源码私有 HTTP 对象和压缩 pickle 输出改为 response-presence 布尔值、JSON/PNG
  及框架轨迹。图片输入副本、提示、历史和索引规则保持来源语义。
- 范围固定为非演示在线分支，不连接作者演示消息服务器，也不启用演示模式的排序跳过。

离线探索、生成新 App 知识和训练不在本次实现中。在线依赖作者已有知识库和官方
SigLIP/FAISS 服务；服务失败会暴露失败，不用空知识冒充成功。预建知识库 Release
元数据已核实存在，文件内容和真实检索效果仍未验收。

## 手动复核

无需设备/模型即可检查完整构图：

```bash
PYTHONPATH=. /opt/miniconda3/envs/unimobile/bin/python examples/sdk/guiexplorer_online.py --dry-run
```

预期返回 `graph_hash` 和 `execution_evidence: false`，不创建运行 artifacts。

执行新功能及其来源对照测试：

```bash
/opt/miniconda3/envs/unimobile/bin/python -m pytest tests/runtime/test_guiexplorer_online.py tests/runtime/test_guiexplorer_services.py tests/graph/test_guiexplorer_yaml.py -q
/opt/miniconda3/envs/unimobile/bin/python -m pytest tests/packaging/test_guiexplorer_install.py -q
```

第二条在新 venv 离线安装当前 wheel，将所需已有依赖复制进去，从仓库外执行实际
YAML。它证明分发资源和模拟边界可运行，不证明真实环境安装/设备/模型质量。

真实执行前需要安装 `.[guiexplorer]`，并在作者要求的 Python 3.12 环境准备官方
SigLIP 编码与检索服务；ZhiXing 的在线适配仍兼容 Python 3.10。官方服务启动入口为
`python -m utils.embedding_pipeline` 和 `python -m utils.retrieval`，后者需要
`KNOWLEDGE_BASE_ABSOLUTE_ROOT_PATH` 指向已准备好的知识库目录。

运行环境提供 `OPENAI_API_KEY`、`OPENAI_API_MODEL`，可选 `OPENAI_BASE_URL`、
`RAG_SERVER_ENDPOINT`、`RAG_TOP_K`、`RAG_THRESHOLD`、`LOW_RESOLUTION`；
YAML 中的凭据只能使用 SecretRef，不填明文。真实执行入口示例：

```bash
PYTHONPATH=. /opt/miniconda3/envs/unimobile/bin/python examples/sdk/guiexplorer_online.py --serial emulator-5554 --task '打开设置并找到蓝牙入口'
```

此命令会真正操作指定设备和调用外部服务，本次未执行。应观察检索、排序、动作与总结
阶段及 `guiexplorer-episode.json`，最后由独立 Benchmark 或人工状态检查判断任务正确性。

更多设计依据见 [复用审查](guiexplorer-component-reuse.md)；面试说明见
GUI-explorer 在线工程记录 (not bundled in the core source)。
