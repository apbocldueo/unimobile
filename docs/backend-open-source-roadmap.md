# Backend 开源整理与优化路线

这份文档记录 ZhiXing 后端在开源前的结构审计结果和分阶段改造顺序。它只记录已经检查到的事实与可复现的验证，不把规划中的重构写成已完成能力。

## 审计范围与基线

本次检查覆盖 `zhixing/` 下的 Graph、Runtime、Components、Devices、Benchmark、Studio、CLI、插件发现与打包边界，同时检查了 `tests/`、CI、`pyproject.toml`、公共发布脚本和安全文档。

当前可复现基线：

- `conda run -n unimobile python -m pytest tests -q -m "not real_android_acceptance" --ignore=tests/packaging`：964 项通过。
- `conda run -n unimobile python -m compileall -q zhixing`：通过。
- `conda run -n unimobile python -m build --wheel --no-isolation`：构建 `zhixing-0.1.0-py3-none-any.whl` 通过。
- 项目已有 backend、frontend、package 和 public-release CI；真实 Android 测试通过 marker 单独隔离。

当前后端已经具备清晰的产品边界：AgentConfig YAML、AgentGraph、BenchmarkTask/Package、ExperimentProtocol、设备副作用和 Studio 持久化并行存在；`Graph Runtime` 不再依赖旧 `AgentRunner` 执行核心；第三方组件的宿主进程信任边界也已经在公开文档中声明。

## 已发现的结构问题

### P0：公共发布前必须处理

1. 当前 Git 树仍包含约 4,078 个 `studio/node_modules` 跟踪文件和一个 `studio/dist` 文件。公共发布脚本会排除它们，但仓库本身仍然会被这些生成物膨胀。应在独立发布清理变更中从 Git 跟踪中移除，并以 `npm ci` 和构建验证替代提交依赖目录。
2. 当前工作树中的公共发布准备文件尚未全部进入 Git 跟踪，`build_public_release.py --allow-dirty` 因 required release paths 未跟踪而拒绝生成发布树。发布前必须先完成一份干净、可复现的 release commit，再运行 allowlist、secret scan、wheel 和 frontend checks。
3. 审计时发现 Harmony 设备旧适配器把多处命令拼成字符串传给 `_execute_command`，该函数对字符串使用 `shell=True`。本轮已完成 Harmony 内部调用的 argv 迁移；剩余工作是统一 Android/Harmony 的 `DeviceCommand` 协议，并继续限制旧 `shell(str)` 兼容入口的使用范围。

### P1：优先提升维护性

1. `zhixing/studio/httpd.py` 约 3,600 行，集中包含 HTTP 路由、请求解析、SSE、artifact 读取和多条 Stage service dispatch；`runtime/kernel.py` 约 1,900 行；`benchmark_service.py`、`database.py`、`cli.py` 也分别超过 1,200 行。它们目前有较好的回归保护，但新贡献者难以定位改动边界。
2. Runtime、旧 `engine/agent`、Components 兼容适配器和新版 Graph API 同时存在，这是有意保留的兼容层，不能直接删除；需要通过 `legacy/compatibility` 标识、文档入口和 parity 测试让维护者知道哪些路径是稳定 API、哪些只是迁移桥。
3. Python CI 已覆盖测试和打包，但没有统一的静态质量门槛或覆盖率趋势门槛。加入工具时应先以现有全量测试为基线，再按包设置逐步收紧，避免一次性把历史代码风格问题混成运行时回归。
4. 设备发现和旧 registry 曾经直接写 stdout。此次已改为标准 logging，库调用不会再污染调用方的输出流；后续应继续统一设备、插件和 CLI 的日志字段与敏感信息过滤。

## 已完成的低风险整理

- `zhixing/devices/manager.py`：Android/Harmony 发现失败和设备初始化改为模块级 logging。
- `zhixing/utils/registry.py`：重复注册告警改为 logging，并补充注册装饰器的契约文档。
- `zhixing/devices/harmony.py`：保留旧 `shell(str)` 兼容入口，但通过 argv 调用 HDC；内部设备发现、应用查询和文本清理改为结构化参数。
- `tests/devices/test_harmony_device_runtime.py`：覆盖 Harmony 命令不会被展平成宿主 shell 字符串，以及内部参数边界保持分离。
- `scripts/build_public_release.py --check-hygiene`：新增只读仓库卫生检查，列出已跟踪的生成物和缺失的发布必需路径，不会修改工作树。
- 原有设备选择、异常类型和兼容返回值保持不变。
- 聚焦设备/registry/Harmony 测试 15 项通过；发布契约测试 14 项通过；完整后端基线保持 964 项通过。

## 建议的实施顺序

### 阶段 A：发布边界清理

先处理 tracked generated files、release manifest 和 secrets 示例的干净提交。验收条件是：新 clone 只通过 Python/Node 安装即可重建；public release builder、wheel、frontend build、secret scan 均通过；发布树不含本地数据库、设备配置、模型响应、轨迹和依赖目录。

### 阶段 B：设备命令安全边界

Android 已经使用 argv 执行主要操作，Harmony 内部命令也已完成第一步迁移。后续仍应把这套约束收敛为统一的 `DeviceCommand`/argv 执行协议，保留旧 `shell(str)` 兼容入口但在文档中明确其 trusted boundary；串命令只在设备端明确需要时经过受控转义。继续补充 serial 特殊字符、超时、stderr 截断和失败诊断测试。

### 阶段 C：按职责拆分大模块

保持公共导入和 HTTP 行为不变，分三次拆分：

1. `studio/httpd.py` 拆为 request primitives、route modules、SSE transport 和 application composition；每次只迁移一组 route，并保留现有 HTTP 合同测试。
2. `runtime/kernel.py` 拆为 budget/activation、port propagation、component invocation、feedback scheduling 和 result events；先提取无状态纯函数，再移动 session 状态。
3. `cli.py` 拆为 parser、component commands、benchmark commands、run commands；入口仍由 `zhixing.cli:main` 提供。

每次拆分都必须满足：canonical identity 不变、AgentConfig/BenchmarkTask 兼容测试通过、Graph trace parity 通过、import side-effect 测试通过。

### 阶段 D：开发者质量门槛

在现有测试基线稳定后，再加入 Python lint/type checks、最小覆盖率趋势和 pre-commit 规则。规则应先针对新增/修改文件启用，避免把一次开源整理变成无法审阅的全仓格式化。

## 不应在本轮做的事情

- 不删除旧 `ModularAgent`、`AgentRunner` 或 AgentConfig/BenchmarkTask 路径。
- 不把第三方 Python 组件描述成进程沙箱。
- 不把 fake-device 结果写成任意 Android 设备支持。
- 不为了“文件变小”改变 Graph canonical hash、插件 identifier、HTTP DTO 或 SQLite revision 合同。
