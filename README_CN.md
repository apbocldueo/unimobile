# 知行 ZhiXing

**一个面向 Mobile Agent 组合、运行与评测的后端优先框架。**

[项目总览](docs/project-overview.md) · [AgentGraph](docs/agent-graph.md) ·
[Benchmark 架构](docs/benchmark-architecture.md) · [English](README.md)

知行通过显式契约连接 Agent 编写、图运行时、设备副作用和 Benchmark 评测。
Python API、图原生 YAML 与 Studio 编写面最终编译为 AgentGraph；旧版
AgentConfig YAML 继续作为兼容路径；BenchmarkTask JSON 始终是独立的任务初始化与
评测契约。

当前项目处于 alpha 阶段。仓库拥有代表性的 fake-device 和有界真实 Android 验证，
但不宣称支持任意 Agent 范式、任意 Android 任务、广泛设备兼容、自动失败诊断，
也不宣称能够安全隔离任意第三方插件。

## 安装

需要 Python 3.10 或更高版本：

```bash
python -m pip install -e ".[dev]"
python -c "import zhixing; print(zhixing.__version__)"
```

按需安装模型、视觉、HarmonyOS 或 Benchmark 依赖。当前仓库不声称 `0.1.0` 已发布到
PyPI。

## 无设备快速验证

```bash
python examples/agent_graph_runtime_no_device.py
python examples/generalized_agent_graph_no_device.py
```

这两条命令不会连接手机，也不会解析模型密钥。

## Android 运行

```bash
cp secrets.example.yaml secrets.local.yaml
adb devices
zhixing run \
  --agent examples/graphs/builtin_android_agent.yaml \
  --serial emulator-5554 \
  --secrets secrets.local.yaml
```

请只在本地填写 `secrets.local.yaml`，不要提交密钥和真实设备配置。详细说明见
[设备连接](docs/device_setup.md)与
[内置 Android Graph Runtime](docs/builtin-agentgraph-runtime.md)。

## Studio

```bash
python -m zhixing.studio
```

另开终端：

```bash
cd studio
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173/`。当前 Studio 已包含 Agent 编写、持久 Run、Replay
以及 Stage 5 Benchmark 工作流。已验证能力和限制以
[Studio 路线文档](docs/studio-roadmap.md)为准。

## 核心边界

- AgentGraph 是与展示位置无关的语义表示。
- AgentConfig YAML 和 BenchmarkTask JSON 是两套独立契约。
- 设备副作用必须经过 ObservationProvider、ActionExecutor 等显式边界。
- `zhixing/engine` 仍是被入口和测试使用的兼容层，不能在行为等价验证前删除。
- 结构化轨迹支持审计和人工定位失败，不等于自动根因诊断。

## 验证

```bash
python -m pytest tests -q \
  -m "not real_android_acceptance" \
  --ignore=tests/packaging

cd studio
npm ci
npm test
npm run typecheck
npm run lint
npm run build
```

真实 Android 验收必须显式选择设备、任务和凭据。fake-device 或浏览器 fixture
不能被描述为真实设备证据。

## 正式开源发布

开发仓库不会整体复制到正式仓库。发布工具仅从 Git 已跟踪文件中选择白名单内容，
拒绝危险路径、常见凭据特征和非空目标目录，并生成 SHA-256 清单：

```bash
python scripts/build_public_release.py
python scripts/build_public_release.py --destination ../unimobile-public
```

详细流程见 [正式开源发布指南](docs/public-release.md)。

## 贡献、安全与许可证

贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请按照
[SECURITY.md](SECURITY.md) 私下报告，不要在公开 Issue 中提交密钥、设备标识或漏洞细节。

项目源代码使用 [Apache License 2.0](LICENSE)。Benchmark 数据集和媒体可能受独立的
上游条款约束，在完成再分发来源审核前不会进入默认公开导出。
