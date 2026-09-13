# studio-runtime-readiness Specification

## Purpose
定义普通 Studio Agent Run 所需的可信本地 Secret、模型依赖和设备配置，以及浏览器可读取但不泄露运行权限的版本化就绪状态。
## Requirements
### Requirement: Studio 运行权限必须由服务端可信配置提供
Studio 服务 SHALL 从显式本地配置加载 SecretRef 值和 Android Device Profile 私有绑定，
并把它们作为进程级、运行时依赖注入普通 Agent Run。浏览器、FlowDocument、AgentGraph、
revision、Run request、event、Replay、diagnostic、toast、URL 和浏览器存储 MUST NOT 接收
实际 secret、raw ADB serial、private target key、live model client 或宿主绝对路径。

#### Scenario: 使用显式配置启动 Studio
- **WHEN** 操作者在 `unimobile` conda 环境中使用合法 secret mapping 和 device-profile 配置启动 Studio
- **THEN** 服务加载运行权限，公开接口只暴露稳定 SecretRef/Profile identity 和安全状态

#### Scenario: 配置文件包含无效结构
- **WHEN** secret 或 device-profile 配置超过有界大小、不是普通文件、结构非法或包含不受支持值
- **THEN** 服务在监听 HTTP 或接受 Run 前以安全配置错误退出，且不打印原始 secret、serial 或绝对路径

### Requirement: Runtime Readiness 必须是版本化且安全的事实投影
系统 SHALL 提供版本化 Runtime Readiness 资源，能够报告 Catalog 中所需组件/可选依赖、
已配置 SecretRef identities 和安全 Device Profile 列表。它 MUST 只返回可用性布尔值、
稳定 identity、能力类别和安全 diagnostic code/message，不得返回配置值或私有绑定。

#### Scenario: 查询已就绪环境
- **WHEN** LLM implementation、被引用 SecretRef 和至少一个安全 Device Profile 均已配置
- **THEN** Readiness 返回对应能力为 ready，并保持 secret value 和 raw serial 不可观察

#### Scenario: SecretRef 未配置
- **WHEN** AgentGraph 引用 `openai_api_key` 但服务端 Secret Provider 没有该 identity
- **THEN** Readiness 返回稳定 missing-secret diagnostic 和该引用 identity，不返回任何相邻配置内容

### Requirement: Exact Revision Run Readiness 必须无副作用
系统 SHALL 能针对 exact immutable Agent revision 和所选安全 Device Profile 计算 ordinary
Run readiness。检查 SHALL 覆盖 graph/hash 完整性、组件与依赖引用可用性、SecretRef
闭包和 Profile 静态存在性，但 MUST NOT 构造组件、连接设备、获取设备租约、调用模型、
执行 Agent、创建 Run 或写 evidence。

#### Scenario: Revision 和环境都可运行
- **WHEN** exact valid revision 的所有必需 dependency/SecretRef 均可解析且所选 Profile 存在
- **THEN** Readiness 返回 ready，并给出可用于 Run Bar 的安全 revision/profile identity

#### Scenario: 设备当前状态在预检后变化
- **WHEN** 静态 Readiness 返回 ready 后设备变为 offline 或 busy
- **THEN** 正式执行边界仍重新检查动态设备事实并产生准确 device failure，Readiness 不声称已证明真实执行

### Requirement: Settings 必须呈现安全运行环境状态
Studio Settings SHALL 显示可用 LLM provider、已配置/缺失的 SecretRef identities 和安全
Device Profile identities，并提供不含私有配置的启动修复指引。Settings MUST NOT 提供
把 raw API key、token、password 或 ADB serial 写入 localStorage/SQLite 的控件。

#### Scenario: 环境未配置
- **WHEN** Runtime Readiness 表明没有 Secret 或 Device Profile
- **THEN** Settings 显示缺失项和服务端配置指引，而不是要求用户把原值保存在浏览器

#### Scenario: 配置完成后重启服务
- **WHEN** 操作者补充可信配置并重启 Studio
- **THEN** Settings 重新查询权威 Readiness 并显示 ready，不依赖先前页面内存或本地伪状态

