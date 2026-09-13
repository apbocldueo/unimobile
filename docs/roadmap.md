# ZhiXing 后端路线图

本文件只记录稳定方向和已经有测试证据的里程碑状态。具体需求、设计和任务以
对应 OpenSpec Change 为准。

## 产品目标

ZhiXing 的目标是让外部开发者使用 Python SDK 或 YAML 组合 AgentGraph，在同一
Runtime 中运行 Mobile Agent，并使用独立 BenchmarkTask 完成初始化与评估。框架
应允许增加组件和 Agent 范式而不修改 Runtime Kernel。

## 已验证的后端基础

- AgentGraph 作为 Python/YAML 的统一语义表示，具备 canonical identity 和静态
  验证。
- Graph Runtime 支持有界控制流、RuntimeContext、RunEvent 和旧 ModularAgent
  兼容路径。
- Android device side effect 通过 ObservationProvider 与 ActionExecutor 边界接入。
- 内置组件能够经 YAML/SDK 编译、绑定并运行 AgentGraph。
- 外部组件具备正式作者 API、ComponentSpec、Contract Test Kit、Entry Point
  发现、Catalog 解析和运行期绑定。
- 独立示例插件已在干净环境验证 wheel、editable 和固定本地 Git commit 三种
  安装来源，并验证 YAML/SDK canonical hash 等价以及两条定义分别完成 Catalog
  绑定与 fake Runtime 节点执行。
- Benchmark 已具有与 AgentGraph 并列的定义层：旧 `BenchmarkTask` JSON 和
  `BenchmarkPackage` 可编译为 `BenchmarkPlan`，公平策略由独立
  `ExperimentProtocol` 表达；Package 资源不依赖当前工作目录。
- Metadata-only Benchmark Catalog 与 `benchmark list/info/validate` 已覆盖显式
  本地目录和已安装 distribution，且不连接设备、导入 Benchmark 插件或执行任务。
- AndroidWorld 81 个唯一任务和 AppAgent 45 个任务已迁移为首批可验证 Package，
  并保留源数据差异报告。
- Benchmark Experiment Runtime 已按 Protocol 物化 TaskInstance，使用同一设备
  编排 initializer、Graph Runtime、Evaluator Tree 与 cleanup，并产生独立
  RuntimeContext、生命周期事件和结构化 Task/Suite Result；新路径不调用
  AgentRunner。
- fake device 已验证两个任务、两个 repeats、两个 AgentGraph、公平复用、失败与
  预算语义；AndroidWorld_6 已在 emulator 上取得 TaskResult PASS、Agent SUCCESS
  和独立 MediaStore 新增照片证据。该证据仅覆盖这一任务与这一图。

外部 provider 当前是宿主进程中的可信 Python 代码，没有进程沙箱。默认
`components doctor` 只报告结构、构造和已获授权的 Contract 检查；被跳过的
invocation 会显示为 `structural-only`，不代表组件行为或算法正确。

以上状态不等于“任意 Agent 范式”或“任意 Android 任务”已完成；每一种范式和
真实设备能力仍需代表性图与真实 trajectory 证明。

## 后续已完成的演进与当前优先级

以上为早期后端基础的历史记录。此后已增加报告、trajectory/bundle、有限 Android
配对与外部组件证据，以及 Studio Builder、Run、Replay 和 Stage 5 Benchmark
工作流。具体证据和限制以 [当前项目总览](project-overview.md)、
[Studio 路线图](studio-roadmap.md) 和各阶段验收文档为准；历史测试数量不代表
当前工作区回归结果。

当前优先完成 [开源发布准备](public-release.md)：公开源码依赖闭包、干净安装、
自动化测试和文档一致性。后续 Worker 多任务/多 Agent/repeats 扩展、更多 Android
设备与任务验收均需独立变更。Core 多基数证据不能用于声明 Studio Worker 已支持
同样的执行规模。

## 当前明确不属于已完成项

- 插件 marketplace、框架自动下载 Git URL 或自动安装依赖；
- 第三方插件的进程沙箱、签名验证和权限隔离；
- 全部内置 Benchmark 任务的真实设备通过率；
- 自动失败诊断。Trajectory 目前用于审计和人工定位失败阶段。
