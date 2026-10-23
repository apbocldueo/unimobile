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

### Requirement: 准备清单必须区分上下文与证据层级
Studio SHALL 根据用户当前意图展示缺失项、状态和受约束的下一步操作，区分进程配置概览、指定已保存 revision 的 readiness 与真实执行证据。配置可用 MUST NOT 被表述为设备在线、模型调用成功或任务可完成；过期、请求失败、加载中和不适用 MUST 与缺失分开。清单 MUST NOT 绕过正式运行前检查或自动触发设备、模型、安装和执行。

#### Scenario: 有效图缺少服务端凭证
- **WHEN** 指定 revision 编译有效但 readiness 报告 SecretRef 未配置
- **THEN** 保留 Graph valid 和 canonical identity，清单解释服务端配置及重新检查步骤，不将密钥写进图或浏览器存储

#### Scenario: 设备 profile 已配置
- **WHEN** 进程概览确认 profile 存在但没有真实连接证据
- **THEN** 清单只说明 profile 已配置，不标记设备已在线或 Android 任务已验证

#### Scenario: 草稿与已检查 revision 不同
- **WHEN** 用户继续编辑后旧 revision 的 readiness 仍在缓存中
- **THEN** 清单明确检查对象并引导完成编辑和保存，不把旧结果当成新草稿可以运行的证明

#### Scenario: 查询失败或状态过期
- **WHEN** readiness 查询失败、尚未完成或结果已不适用于当前对象
- **THEN** 显示相应状态与精确重试或重新检查动作，不用缺少配置或 ready 替代未知事实

### Requirement: 普通运行和 Benchmark 准备必须保持独立
普通 Run 的准备清单 MUST NOT 要求 Benchmark。Benchmark 入口 SHALL 根据已有正式资源展示适用的 Package、Agent revision、profile 和预览前提，区分真实空目录、筛选无匹配、查询失败与未发布草稿。引导 MUST NOT 自动发布、执行或扩张既有 Worker 接受范围。

#### Scenario: 普通 Run 没有 Benchmark
- **WHEN** 普通 Run 的既有前提满足但工作区没有 Benchmark
- **THEN** Benchmark 不成为 Run 阻断项，仍由原有正式启动检查决定是否接受运行

#### Scenario: Catalog 没有可选 Benchmark
- **WHEN** Catalog 查询成功且没有资源
- **THEN** 提供了解或创建 Benchmark 的明确入口，说明作者草稿和可选发布资源的区别，不伪造可运行示例

#### Scenario: 筛选为空或查询失败
- **WHEN** Catalog 的筛选结果为空或查询失败
- **THEN** 分别提供清除筛选或重试，不混同于需要创建 Benchmark

#### Scenario: 准备提示不能执行修复
- **WHEN** 用户阅读清单或打开其帮助入口
- **THEN** 不发布 Package、不创建 Run/Experiment、不连接设备或调用模型，也不绕过现有基数和执行资格限制

