# 知行 ZhiXing

**用于构建与评测 Mobile GUI Agent 的统一框架**

[English](README.md) · [论文 artifact 指南](docs/paper-artifact.md) · [示例](examples) · [文档总览](docs/project-overview.md)

ZhiXing 将 Mobile GUI Agent 的构建与任务评测放在同一个框架中：通过可复用组件、
可组合的 AgentGraph 和共享 Graph Runtime 搭建 Agent 工作流，减少为每种实现单独
编写执行循环的工作。配套的 ZhiXing-Bench 提供声明式任务定义、可复用的初始化与
评估插件，以及自动化的任务结果评估。

一个 Agent 可以接收不同任务，既可以独立运行，也可以由 ZhiXing-Bench 调用。
Agent 配置与 Benchmark 任务定义相互独立，切换任务无需重新构造 Agent 工作流。

## 架构总览

![论文中的 ZhiXing 与 ZhiXing-Bench 工作流：Agent Config 经图构建、检查和组件绑定形成使用 Graph Runtime 的可执行 Agent；独立的 Task Definition 经任务构建、调度、实例化、环境准备、Agent 执行与结果评估，形成报告和 Replay。](docs/assets/zhixing-paper-workflow.png)

整体流程由两部分组成：**ZhiXing 负责构建与执行 Agent**，**ZhiXing-Bench 负责
构建任务与评估任务结果**。Benchmark 执行复用前者构建的可执行 Agent 及其
Graph Runtime。

### Agent 构建与执行

用 Python 或 YAML 组合感知、推理、记忆与动作等组件，构建 AgentGraph。
ZhiXing 负责检查配置、绑定组件并执行工作流，构建的 Agent 既可独立运行，
也可用于 Benchmark。[AgentGraph 指南](docs/agent-graph.md) · [组件扩展](docs/external-components.md)

### 任务构建与评测

用 JSON 定义任务指令、环境初始化和评估规则，复用插件完成任务准备与结果检查。
ZhiXing-Bench 负责调度任务、调用 Agent，并生成报告与回放；任务是否成功由评估
规则判定。[Benchmark 指南](docs/benchmark-architecture.md) · [任务编写](docs/benchmark-authoring.md)

## 快速开始

准备 Python 3.10+、ADB、一台已解锁的 Android 手机或模拟器，以及支持图像输入的
模型 API key。真机需开启 USB 调试并授权电脑连接，详见[设备连接](docs/device_setup.md)。

### 1. 安装

```bash
git clone https://github.com/apbocldueo/unimobile.git
cd unimobile
python -m pip install -e ".[openai]"
cp secrets.example.yaml secrets.local.yaml
```

### 2. 配置模型

编辑 `secrets.local.yaml`，填入自己的 API key 和接口地址：

```yaml
api_key: "YOUR_API_KEY"
base_url: "https://your-model-provider/v1"
```

示例 Agent 的模型名在 [`builtin_android_agent.yaml`](examples/graphs/builtin_android_agent.yaml)
的 `model` 字段中，默认值为 `gpt-4o`；请改为你的接口实际提供、支持图像输入的模型名。

### 3. 连接设备并运行

```bash
adb devices
```

确认设备状态为 `device`。下面以 `emulator-5554` 为例，运行时替换为列表中的设备 ID：

```bash
zhixing run \
  --agent examples/graphs/builtin_android_agent.yaml \
  --instruction "打开相机并拍一张照片，完成后结束任务" \
  --serial emulator-5554 \
  --secrets secrets.local.yaml \
  --artifact-root temp/runs
```

运行时可以在手机上看到 Agent 的操作。结束后，终端会输出运行状态和运行 ID，
截图、动作记录和运行清单保存在 `temp/runs/`。可以替换任务指令尝试其他操作；更多配置见
[Android 运行指南](docs/builtin-agentgraph-runtime.md)。

## 示例与源码入口

| 内容 | 入口 |
| --- | --- |
| AgentGraph 构建 | [Python 示例](examples/agent_graph_no_device.py)、[图定义](examples/agent_graph/) |
| Runtime 调度与反馈 | [无设备执行](examples/agent_graph_runtime_no_device.py)、[更多图模式](examples/generalized_agent_graph_no_device.py) |
| Mobile Agent 工作流 | [图原生 YAML](examples/graphs/)、[Python SDK](examples/sdk/) |
| 外部可复用组件 | [插件示例](examples/external_component_plugin/)、[扩展指南](docs/external-components.md) |
| 任务构建 | [最小 Package](examples/benchmarks/minimal/)、[动态任务](examples/benchmarks/dynamic-task/) |
| 可组合的结果检查 | [Evaluation Tree 示例](examples/benchmarks/composite-evaluation/) |
| 论文机制与复验 | [论文与代码对应表、验证命令](docs/paper-artifact.md) |

核心实现在 [`zhixing/graph/`](zhixing/graph/)、
[`zhixing/components/`](zhixing/components/)、[`zhixing/runtime/`](zhixing/runtime/)、
[`zhixing/benchmark/`](zhixing/benchmark/) 和 [`zhixing/plugins/`](zhixing/plugins/)；
设备实现在 [`zhixing/devices/`](zhixing/devices/)。

## 可选：ZhiXing Studio

Studio 提供 Agent 可视化编写、运行监控、Benchmark 配置、报告与 Replay 工作区。
安装 Python 依赖并准备 Node.js 22.12+ 后：

```bash
npm --prefix studio ci
python run_studio.py
```

启动器打开 `http://127.0.0.1:5173/`，按 Ctrl+C 一并关闭前后端。未配置模型与
设备时可先编写 Agent，执行前需要补齐对应的本地配置。详见
[本地启动说明](docs/studio-local-startup.md)。

## 发布范围与可复现性

当前为论文配套的**核心源码发布**，包含框架、保留的 Agent 示例、教学 Benchmark
Package、测试与 Studio。两份规范 AndroidWorld JSON 共保留 **116 个唯一任务
定义（81 + 35）**。完整任务媒体 Package、App 安装包、模拟器镜像和论文实验的
完整结果台账未随包分发，因此仅凭源码包不足以执行全部 116 个任务或复现论文
报告的实验结果。

按本次确定的范围，Agent-SAMA、AndroidArena、V-Droid 与 MobA 移植代码暂缓分发，
等待核实再分发授权；VisionTasker 的 GPL 源码集成也不进入本次 Apache 核心包。
具体边界见[论文 artifact 指南](docs/paper-artifact.md)与
[第三方版权说明](docs/third-party-notices.md)。

ZhiXing 处于 alpha 阶段，已有离线、fake-device 与有界 Android 验证证据；更广泛
的 Agent 与设备覆盖仍需验证。结构化轨迹用于审计和人工定位失败；第三方 Python
插件在宿主进程中运行。

## 贡献与引用

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)、[SECURITY.md](SECURITY.md) 与
[CITATION.cff](CITATION.cff)。ZhiXing 核心源码使用
[Apache License 2.0](LICENSE)，保留的第三方代码附有各自版权说明。
