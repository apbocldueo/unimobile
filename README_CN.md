# 知行 ZhiXing

**用可复用 AgentGraph 构建、运行和评测 Mobile Agent，并保留可审计的实验依据。**

[English](README.md) · [文档总览](docs/project-overview.md) · [示例](examples) · [Studio](docs/studio-roadmap.md)

论文对应的代码入口、无设备复验、任务数据边界与暂缓分发的上游适配，见
[论文 artifact 指南](docs/paper-artifact.md)。当前发布的是核心源码，不是已完整
复现论文实验结果的数据包；第三方来源见[版权与分发说明](docs/third-party-notices.md)。

ZhiXing 将通常被硬编码在一起的三件事分开：Agent 如何工作、任务意味着什么，以及在
什么条件下进行评测。它们可被独立定义、组合运行，并保留检查结果所需的证据。

## 快速开始

ZhiXing 需要 Python 3.10+。

```bash
git clone https://github.com/apbocldueo/unimobile.git
cd unimobile
python -m pip install -e ".[openai,dev]"

# 无需设备或 API key。
python examples/agent_graph_runtime_no_device.py
```

这个无设备示例会验证图构建与确定性 Runtime 行为，不会连接手机或解析模型密钥。

## 你可以做什么

- **构建 Agent：** 用 Python、图原生 YAML 或 ZhiXing Studio；所有编写方式都会编译为
  `AgentGraph`。
- **运行可控 Benchmark：** 将 AgentGraph 与 `BenchmarkPlan`、`ExperimentProtocol`
  组合执行。
- **检查证据：** 独立记录 Agent 状态与 Benchmark 结果，并保留 report、结构化
  trajectory、Replay 与可校验 bundle。

## 工作原理

![ZhiXing 四阶段架构：创作 AgentGraph，绑定独立的 Benchmark 与 Protocol 定义，经显式设备边界执行，并保留结果和产物。](docs/assets/zhixing-architecture-overview.png)

1. **编写：** 使用 Python SDK、图原生 YAML 或 Studio 创建 `AgentGraph`。
2. **绑定：** 将它与独立的 BenchmarkPlan、ExperimentProtocol 组合。
3. **执行：** 经 `ObservationProvider`、`ActionExecutor` 等显式设备边界运行。
4. **检查：** 查看 Agent 状态、外部任务 verdict 和保留的产物。

`AgentGraph` 定义 Agent 行为；`BenchmarkPlan` 定义任务 setup 与 evaluation；
`ExperimentProtocol` 固定 seed、repeats、预算和设备约束。修改其中之一不会静默改写另外两者。

## 接下来

| 我想要… | 从这里开始 |
| --- | --- |
| 理解核心架构 | [项目总览](docs/project-overview.md) |
| 编写 AgentGraph | [AgentGraph 指南](docs/agent-graph.md) |
| 连接 Android 设备 | [设备连接](docs/device_setup.md) |
| 运行内置 Android 图 | [Android Runtime 指南](docs/builtin-agentgraph-runtime.md) |
| 创建或运行 Benchmark | [Benchmark 架构](docs/benchmark-architecture.md) |
| 使用可视化工作区 | [Studio 路线图](docs/studio-roadmap.md) |
| 整理后端并准备开源 | [后端开源整理路线](docs/backend-open-source-roadmap.md) |
| 查看可运行定义 | [示例](examples) |

### 启动 Studio

```bash
# 首次安装前端依赖（需要 Node.js 22.12+）
npm --prefix studio ci

# 日常启动：在项目根目录、已安装依赖的 Python 环境中运行
python run_studio.py
```

自动启动前后端并打开 `http://127.0.0.1:5173/`，按一次 Ctrl+C 一起关闭。
自动加载 `secrets.local.yaml`（优先）或 `secrets.yaml`，以及
`studio/device-profiles.json`。未配置时仍可编辑 Agent，实际运行前需补齐配置。
可用 `--check` 只检查启动条件，或 `--no-browser` 禁用自动打开浏览器。
原来的 `python -m zhixing.studio` 独立后端入口保持可用。
配置覆盖、端口冲突和首次安装见[本地启动说明](docs/studio-local-startup.md)。

### 运行 Android 示例

```bash
cp secrets.example.yaml secrets.local.yaml
adb devices
zhixing run \
  --agent examples/graphs/builtin_android_agent.yaml \
  --serial emulator-5554 \
  --secrets secrets.local.yaml
```

请在本地替换示例 serial 和密钥；不要提交凭据或真实设备配置。

## 当前范围

ZhiXing 是 alpha 阶段的研究与工程框架，拥有 fake-device 和有界 Android 验证证据。
它不宣称支持任意 Agent 范式、任意 Android 任务、广泛设备兼容、自动失败诊断，或对
任意第三方插件的安全沙箱隔离。

完整的验证命令、打包、正式开源发布、贡献、安全和引用说明请见
[文档总览](docs/project-overview.md)、[CONTRIBUTING.md](CONTRIBUTING.md)、
[SECURITY.md](SECURITY.md) 与 [CITATION.cff](CITATION.cff)。

ZhiXing 源代码使用 [Apache License 2.0](LICENSE)。
