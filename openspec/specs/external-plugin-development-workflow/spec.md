# external-plugin-development-workflow Specification

## Purpose
定义外部组件插件从独立开发、标准安装、自动发现、Contract 验证到 AgentGraph 执行的可复现开发闭环。

## Requirements
### Requirement: 框架提供可独立分发的正式插件示例
系统 SHALL 提供一个使用独立 `pyproject.toml` 和 `src` 布局的外部组件示例项目。该项目 MUST 只导入 ZhiXing 公共作者 API，MUST 通过 `zhixing.components` Entry Point 导出版本化 `ComponentBundle`，并 MUST 能在不修改 ZhiXing 源码、核心 Registry 或 `sys.path` 的情况下独立构建 wheel。

#### Scenario: 将示例复制为独立仓库
- **WHEN** 开发者把示例插件目录复制到 ZhiXing 仓库之外并构建项目
- **THEN** 构建产生可安装 wheel，且源码不依赖 ZhiXing 仓库内路径或私有模块

#### Scenario: 示例组件通过插件侧测试
- **WHEN** 开发者在示例插件项目中运行其 pytest
- **THEN** 测试通过公共 Contract Test Kit 验证 Bundle 中的正式组件，而不连接网络、模型或真实设备

### Requirement: 标准安装来源共享同一开发流程
示例插件 SHALL 支持 wheel、editable 和固定 Git commit 三种标准 Python 安装来源。三种来源 MUST 通过相同 Entry Point、provider ID、ComponentBundle 和 Catalog 解析语义接入框架；安装来源 provenance MUST NOT 改变组件身份或 AgentGraph canonical hash。

#### Scenario: wheel 与 editable 安装
- **WHEN** 两个干净环境分别从插件 wheel 和 editable 源码安装同一版本
- **THEN** ZhiXing 发现相同 provider 与组件身份，并为等价 AgentGraph 计算相同 canonical hash

#### Scenario: 固定 Git commit 安装
- **WHEN** 干净环境从本地或远程 Git 仓库的固定 commit 安装示例插件
- **THEN** 插件通过同一 Entry Point 被发现，commit 只出现在安全 provenance 而不进入 AgentGraph 语义

### Requirement: YAML 与 Python SDK 执行同一已安装外部组件
系统 SHALL 允许 YAML 和 Python SDK AgentGraph 按相同 namespace、name、version 与参数引用已安装插件组件。两条作者路径 MUST 编译为相同 canonical AgentGraph，并 MUST 通过普通 Catalog resolver、binder 和 Graph Runtime 执行，不得在 Kernel 中增加 provider、distribution 或插件名称分支。

#### Scenario: YAML 执行已安装组件
- **WHEN** 高层 YAML 入口加载引用示例插件组件的 AgentGraph，且 provider 已安装并被允许
- **THEN** 系统从发现 Catalog 解析并构造该组件，节点执行产生 start 和 complete RunEvent

#### Scenario: SDK 执行同一组件
- **WHEN** Python SDK 使用相同组件引用和图语义构建 AgentGraph
- **THEN** SDK 图与 YAML 图具有相同 canonical hash，并通过相同 binding 和 invocation boundary 得到等价结果

#### Scenario: 插件未安装
- **WHEN** YAML 或 SDK 图引用示例插件组件，但当前环境没有对应 provider
- **THEN** 系统在设备分配和 Kernel 启动前返回结构化 missing component 或 provider failure 诊断

### Requirement: 干净环境验收贯穿完整插件链路
项目 SHALL 提供仓库外干净虚拟环境验收，依次安装 ZhiXing wheel 和外部插件 distribution，再通过真实 installed metadata 完成发现、健康检查、YAML/SDK 编译、组件绑定和 fake Runtime 执行。验收 MUST 移除仓库 `PYTHONPATH` 和用户 site 影响，且 MUST 不以进程内手工 Catalog 代替 Entry Point 发现。

#### Scenario: 完整成功闭环
- **WHEN** 验收环境安装两个 wheel 并执行示例工作流
- **THEN** provider 可列举、Bundle 健康检查通过、两种图定义身份一致、外部节点执行成功且事件可断言

#### Scenario: 仓库外工作目录
- **WHEN** 验收从不包含 ZhiXing 或插件源码的空目录运行
- **THEN** 所有导入、资源、Entry Point 和 AgentGraph 文件均来自已安装 distribution 或显式示例输入，不依赖当前工作目录

### Requirement: 开发者 Quickstart 对应可执行事实
项目 SHALL 提供从组件实现、ComponentSpec、Bundle、Entry Point、Contract 测试、安装、doctor 到 YAML/SDK 使用的短路径文档。文档中的核心命令和示例 MUST 由自动化测试或可重复人工验收覆盖，不得把计划能力、PyPI 发布、自动 Git 下载、沙箱或真实 Android 结果描述为已完成。

#### Scenario: 新开发者按 Quickstart 操作
- **WHEN** 熟悉 Python 的开发者在干净环境按文档执行示例命令
- **THEN** 开发者能够构建并安装插件、查看健康状态并运行引用外部组件的示例 AgentGraph

#### Scenario: 查看已知限制
- **WHEN** 开发者阅读插件信任与能力边界
- **THEN** 文档明确说明 provider 在当前 Python 进程执行、doctor 不是安全沙箱、fake Runtime 不证明真实 Android 行为
