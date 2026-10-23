# external-component-plugin-discovery Specification

## Purpose
TBD - created by archiving change discover-external-component-plugins. Update Purpose after archive.
## Requirements
### Requirement: 已安装 distribution 通过标准 Entry Point 声明组件 provider
系统 SHALL 使用固定 Entry Point group `zhixing.components` 发现外部组件 provider。PyPI、wheel、Git 和本地 editable 来源 MUST 在安装到当前 Python 环境后走同一发现协议；系统 MUST NOT 要求插件复制到 ZhiXing 源码树、修改核心注册表或依赖当前工作目录。

#### Scenario: 发现 editable 插件
- **WHEN** 一个本地 Python 项目以 editable 模式安装并声明 `zhixing.components` Entry Point
- **THEN** 系统把它枚举为外部组件 provider，且无需修改 ZhiXing 或 `sys.path`

#### Scenario: 发现 Git 或 wheel 插件
- **WHEN** 同一个插件 distribution 从 Git URL 或 wheel 安装并暴露相同 Entry Point
- **THEN** 系统通过相同 provider 协议发现它，Runtime 不根据安装来源增加分支

#### Scenario: 仅有 GitHub URL
- **WHEN** 用户提供一个尚未安装到当前 Python 环境的 GitHub 仓库 URL
- **THEN** discovery 不下载或执行该仓库，并报告当前环境中没有对应已安装 provider

### Requirement: 元数据枚举与 provider 代码加载分离
系统 SHALL 能只读取 Entry Point 和 distribution 元数据生成不可变 `PluginCandidate`，且该操作 MUST NOT 调用 Entry Point load、导入 provider 模块或构造组件。provider 代码只可在调用方显式请求 discovery/bootstrap 加载阶段执行。

#### Scenario: 只枚举候选
- **WHEN** 调用方请求列出当前环境中的组件 provider
- **THEN** 系统返回 provider ID、distribution 名称、distribution 版本和 Entry Point 目标等安全元数据，且 provider 模块尚未导入

#### Scenario: 显式加载候选
- **WHEN** 调用方显式加载一个已枚举并启用的 provider
- **THEN** 系统才调用对应 Entry Point load 并把返回对象交给 ComponentBundle 校验

#### Scenario: 导入基础包
- **WHEN** 进程仅执行 `import zhixing` 或 `import zhixing.components`
- **THEN** 系统不枚举 Entry Point、不加载 provider 且不改变旧全局 PluginRegistry

### Requirement: provider 选择策略明确且可复现
discovery/bootstrap SHALL 支持按稳定 provider ID 配置 allowlist 和 denylist。默认 bootstrap SHALL 加载当前环境中所有未禁用 provider；候选排序、加载顺序和报告顺序 MUST 确定且不依赖底层 metadata 返回顺序。

#### Scenario: allowlist 选择
- **WHEN** 当前环境安装了多个 provider 且调用方只允许 `acme-mobile`
- **THEN** 系统只加载该 provider，其他候选记录为未选择且不导入其模块

#### Scenario: denylist 禁用
- **WHEN** provider ID 位于 denylist
- **THEN** 系统保留其安全候选信息但不加载其代码

#### Scenario: provider ID 重复
- **WHEN** 两个已安装 distribution 在同一 Entry Point group 声明相同 provider ID
- **THEN** 系统返回确定性的 provider identity conflict，而不是依赖枚举顺序选择其中一个

### Requirement: provider 加载失败隔离并产生安全报告
系统 SHALL 为每个 Entry Point 独立记录加载状态。一个 provider 的导入错误、缺少可选依赖、返回类型错误或 Bundle 校验失败 MUST 产生结构化 `PluginLoadFailure`，且不得阻止无关 provider 被加载；错误不得包含 secret、凭据 URL、任意插件对象 repr 或无界 traceback。

#### Scenario: 一个 provider 缺少依赖
- **WHEN** provider A 因缺少可选 Python 依赖加载失败而 provider B 合法
- **THEN** DiscoveryReport 记录 A 的稳定错误类型并成功加载 B

#### Scenario: 被引用组件来自失败 provider
- **WHEN** AgentGraph 引用的组件只能由加载失败的 provider 提供
- **THEN** binding 返回可定位到 provider 和安全组件身份的错误，且不把它误报为普通 unknown component

#### Scenario: 错误包含敏感 URL
- **WHEN** provider 异常文本包含 token、password 或带用户信息的 URL
- **THEN** DiscoveryReport 对敏感片段脱敏并限制错误内容长度

### Requirement: 安装来源只作为安全 provenance
系统 SHALL 在可用时读取 distribution 安装来源信息，并把经过清理的来源类型、VCS 类型、requested revision 和 commit ID 作为非语义 provenance。真实凭据、URL userinfo、secret query、设备句柄和无关绝对路径 MUST NOT 出现在公共 discovery 数据中。

#### Scenario: Git commit 来源
- **WHEN** provider distribution 包含合法 `direct_url.json` 和 Git commit 信息
- **THEN** DiscoveryReport 可以记录经清理的 VCS 类型与 commit ID，但 AgentGraph 内容不发生变化

#### Scenario: 来源包含凭据
- **WHEN** direct URL 包含用户名、token 或 password
- **THEN** 公共来源描述移除凭据且不把原始 URL写入日志、事件或报告

#### Scenario: 没有 direct URL
- **WHEN** provider 由普通 index wheel 安装且没有 `direct_url.json`
- **THEN** discovery 仍以 distribution 名称和版本工作，不把来源缺失视为组件失败

### Requirement: discovery 阶段不获得运行时能力
框架在枚举和加载 provider 时 MUST NOT 向第三方代码传入 RuntimeContext、Device、ActionExecutor、LLM、Secret provider 或 Benchmark runtime，不得由 discovery 自身连接设备、访问网络、创建运行目录或执行组件。

#### Scenario: 加载合法 Bundle
- **WHEN** provider Entry Point 返回合法 ComponentBundle
- **THEN** 系统只验证静态 Bundle 和 ComponentSpec 定义，不实例化组件或访问 Android

#### Scenario: provider 需要运行时参数
- **WHEN** Entry Point 目标要求 Device、Secret 或其他调用参数才能返回声明
- **THEN** provider contract 校验失败，discovery 不尝试从运行环境注入这些对象

### Requirement: CLI 可检查已安装组件详情
系统 SHALL 提供面向单个外部组件的 inspect 命令。inspect MUST 在用户显式调用后按现有 allowlist、denylist 和 Catalog 版本解析规则加载 provider，并输出组件安全身份、provider ID、角色或类别、NodeContract、配置 schema 与清理后的 provenance；输出不得包含组件实例、factory、secret 或原始安装 URL。

#### Scenario: 检查精确版本组件
- **WHEN** 用户 inspect `acme:camera_verifier@1.0.0` 且允许的 Catalog 存在该身份
- **THEN** CLI 以人工文本或稳定 JSON 输出对应 ComponentSpec 的安全 metadata

#### Scenario: 省略版本但存在多个版本
- **WHEN** 用户 inspect 未固定版本的组件且 Catalog 存在多个匹配版本
- **THEN** CLI 返回非零退出码和 component-version-ambiguous，并列出安全版本集合

### Requirement: CLI 可诊断 provider 健康状态
系统 SHALL 提供 doctor 命令，显式枚举并加载选中的 provider，组合 DiscoveryReport、Catalog 建立结果和 Bundle Contract 聚合结果。doctor MUST 区分未选择、加载失败、Catalog 冲突、Contract 失败和健康 provider，并 MUST 同时支持有界人工文本与稳定 JSON。

#### Scenario: provider 健康
- **WHEN** 用户对合法示例 provider 运行 doctor
- **THEN** CLI 报告 provider、Bundle 和全部安全 Contract 检查通过并返回成功退出码

#### Scenario: provider 缺少依赖
- **WHEN** provider 导入因缺少可选依赖失败
- **THEN** doctor 返回 discovery/load 阶段的稳定错误码和 provider ID，不尝试运行其组件且不影响其他 provider 的诊断

#### Scenario: 组件 Contract 失败
- **WHEN** provider 成功加载但 Bundle 中组件违反运行时输出 Contract
- **THEN** doctor 返回区别于 discovery 错误的健康检查失败退出码，并定位组件与失败阶段

### Requirement: 组件诊断命令保持显式加载、受信任代码边界和安全输出
`components list` 默认 metadata-only 行为 SHALL 保持不变；inspect 和 doctor MAY 在用户显式调用后加载并构造已安装的第三方 provider。框架自身 MUST NOT 自动安装包、修改 `sys.path`、主动连接设备或网络，也 MUST NOT 向 provider 注入真实 `RuntimeContext`、Device、ActionExecutor、LLM、网络客户端或其他运行时能力。已安装 provider 的模块导入、Bundle factory 和组件构造函数属于当前 Python 进程中的受信任第三方代码，系统 MUST 明确说明这些阶段不受沙箱保护，因而不能保证第三方代码自身没有副作用。所有失败输出 MUST 使用统一脱敏边界并限制字符串、集合大小和递归深度。

#### Scenario: 仅执行 list
- **WHEN** 用户运行不带 load 的 `components list`
- **THEN** 系统不导入 provider，也不运行 Bundle Contract 检查

#### Scenario: doctor 遇到带凭据异常
- **WHEN** provider 异常包含用户名、password、token 或带 userinfo 的 URL
- **THEN** 文本和 JSON 输出均移除敏感内容且不包含原始 traceback

#### Scenario: doctor 检查敏感角色
- **WHEN** 已安装 provider 声明 Device、ActionExecutor 或 LLM 等敏感角色，且用户没有提供插件侧受控 fixture
- **THEN** doctor 可以验证定义、构造和实例隔离，但跳过 invocation、公开 skipped 状态，且框架不注入任何真实运行时能力

#### Scenario: provider 自身在导入阶段产生副作用
- **WHEN** 已安装 provider 的模块导入或构造函数自行访问网络、设备或宿主环境
- **THEN** 系统把该 provider 视为受信任宿主进程代码，不宣称 doctor 能阻止此行为，并在开发者文档中提示安装和诊断第三方包的信任边界

#### Scenario: 传入 GitHub URL
- **WHEN** 用户把未安装 GitHub URL 当作 inspect 或 doctor 目标
- **THEN** CLI 不下载或执行仓库，并提示先通过标准 Python 工具安装 distribution
