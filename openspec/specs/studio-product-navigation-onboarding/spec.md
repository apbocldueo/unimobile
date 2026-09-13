# studio-product-navigation-onboarding Specification

## Purpose
定义 ZhiXing Studio 面向首次使用者与持续研究工作的全局信息架构，使 Agent、Experiment 和运行记录能够按对象与生命周期被发现，同时通过渐进披露保留研究级技术细节和既有正式资源边界。
## Requirements
### Requirement: Studio 必须使用对象与研究生命周期组织全局导航
Studio SHALL 提供稳定且全局一致的首页、Agents、Experiments、Runs 和设置入口。顶层导航 MUST 使用用户能够理解的对象或生命周期名称，不得把“Agent 构建”“试车场”“Catalog”“Composer”等实现模块同时作为相互竞争的全局主入口；当前入口 SHALL 在所有普通页面和工作区中可辨认。

#### Scenario: 首次从首页进入 Agent 工作
- **WHEN** 首次用户希望创建或打开一个 Agent
- **THEN** 用户可以从首页或 Agents 入口直接到达唯一 Agent Library，而无需先判断“流程”“Agent 构建”或其他内部模块的区别

#### Scenario: 在深层页面辨认当前位置
- **WHEN** 用户直接打开 Agent Design、Experiment Monitor、Report 或 Replay deep link
- **THEN** Studio 显示对应全局对象域和本地上下文，不错误高亮无关模块，也不要求返回首页才能切换到其他全局入口

### Requirement: 首页必须同时服务首次开始和继续工作
首页 SHALL 以一个清晰的 Mobile Agent 研究价值主张、一个主要创建 Agent 动作、一个从受支持示例开始的次级动作、最近工作和环境准备摘要组成。首页 MUST NOT 再展示重复的完整 Agent 目录或要求用户先“选择模块”；最近工作项 MUST 使用权威持久资源并链接到其正式上下文。

#### Scenario: 全新工作区没有用户资源
- **WHEN** Agent、Run 和 Experiment 都为空
- **THEN** 首页显示创建 Agent 与从示例开始的明确动作、简短的后续流程说明和真实环境准备状态，而不显示空白模块网格或伪造最近记录

#### Scenario: 返回用户继续工作
- **WHEN** 用户已有 Agent、普通 Run 或 Experiment
- **THEN** 首页以有界最近工作显示名称、类型、状态、更新时间和权威链接，且同一个 Agent 不同时作为侧栏目录、最近卡片和第二个 Builder 目录重复出现

#### Scenario: 最近工作部分加载失败
- **WHEN** 一个最近资源查询失败但其他首页事实可用
- **THEN** 首页隔离该部分的错误并提供精确重试，继续保留创建、示例和其他可用入口，不以 mock 内容填充失败区域

### Requirement: Agent Library 必须是 Agent 发现和创建的唯一目录
Studio SHALL 提供一个权威 Agent Library，负责列出、搜索、创建、从正式模板创建、导入和打开 Agent。Library MUST 根据权威 Agent 列表的空/非空状态建立任务层级：没有任何 Agent 时，正式示例 SHALL 是主要开始动作，空白创建 SHALL 是次级动作，导入 SHALL 作为明确但次级的方式；已有 Agent 时，最近更新且可继续设计的 Agent SHALL 成为主要继续工作入口，创建 SHALL 保持单一可发现动作。最近工作入口 MUST 只是同一权威 Agent 的快捷入口，完整可搜索目录 MUST 继续包含该 Agent。模板选择、名称输入、Schema 迁移说明和 immutable revision 的技术解释 MUST 只在用户明确进入相应创建或导入流程后显示；目录卡片 MUST NOT 显示 raw identity 或无行动价值的技术详情。其他页面 MAY 展示有界最近 Agent 或上下文引用，但 MUST NOT 再维护与 Library 竞争的完整 Agent 列表或第二套创建流程。

#### Scenario: 首次用户从正式示例开始
- **WHEN** Agent 查询成功且工作区没有任何 Agent
- **THEN** Library 优先显示“从示例开始”、可见的空白创建入口和次级导入入口，不默认显示模板选择器、Schema 迁移细节、raw identity 或无关的完整目录说明

#### Scenario: 返回用户继续最近 Agent
- **WHEN** Agent 查询成功且至少一个 Agent 存在
- **THEN** Library 显示一个由权威安全元数据确定的最近可继续设计 Agent 作为主要工作入口，并在其下提供包含该 Agent 在内的完整、紧凑、可搜索 Agent 列表与单一新建动作

#### Scenario: 用户明确创建 Agent
- **WHEN** 用户选择空白创建、正式示例或新建动作
- **THEN** Library 在明确的创建上下文中显示名称和与该意图相关的模板选项，完成既有持久 Agent 创建流程后打开该 Agent 的 Design 上下文，不在另一个模块页要求用户再次选择同一 Agent

#### Scenario: 用户导入 Agent 文档
- **WHEN** 用户明确选择导入 JSON
- **THEN** Library 在导入上下文中说明 Schema 2 校验和 Schema 1 显式迁移的结果，保留原文件，且仅在导入解析成功后创建持久 Agent 并打开其 Design 上下文

#### Scenario: Agent 名称相同
- **WHEN** 多个 Agent 具有相同显示名称
- **THEN** Library 使用安全的创建/更新时间帮助区分并跟随各自权威 identity，且目录不显示“技术详情”或完整 raw ID

### Requirement: Agent 工作区必须保持稳定的对象级上下文
打开一个 Agent 后，Studio SHALL 在共享对象头部提供 Agent 名称和设计、运行、运行记录三个本地工作模式。Design、Run 和 Replay/History MUST 继续使用各自正式路由、状态所有者和 immutable identity；切换模式 MUST NOT 把可编辑 draft 当作已保存 revision、把历史 Replay 当作新运行或隐式创建 Run。

#### Scenario: 从设计进入运行
- **WHEN** 当前 Agent 具有 clean、valid、runtime-ready immutable revision 且用户选择运行
- **THEN** Studio 跟随该 Agent 的正式 Run 路由并保留 Agent 上下文，不弹出一个脱离对象工作区的第二套 Agent 选择流程

#### Scenario: 从运行记录打开 Replay
- **WHEN** 用户在该 Agent 的运行记录中选择一个具有 Replay 的普通 Run
- **THEN** Studio 跟随权威 Replay link、保持只读标识并允许回到同一 Agent 的设计或运行记录，不将 Replay 连接设备或重放副作用

#### Scenario: Agent 尚无运行记录
- **WHEN** 用户打开某 Agent 的运行记录但该 Agent 没有普通 Run
- **THEN** 页面显示该 Agent 范围内的真实空状态和“运行此 Agent”动作，不混入其他 Agent 或 Benchmark Experiment

### Requirement: Experiments 入口必须按研究任务渐进展开 Benchmark 能力
Experiments SHALL 首先提供开始新实验、继续活动实验和访问结果的任务导向入口。选择 Benchmark、Agent revision、Task、Protocol 和 Device Profile SHALL 在创建实验流程中按依赖顺序呈现；Benchmark Catalog、Benchmark Authoring、Contract Tests、Release 等专业能力 MUST 保留，但 SHALL 作为上下文或明确的高级入口出现，而不是与“新建实验”同等竞争首次注意力。

#### Scenario: 新建 Benchmark Experiment
- **WHEN** 用户选择新建实验
- **THEN** Studio 引导其依次选择 Agent、Benchmark/Task、Protocol/Profile 并确认 schedule，继续使用既有 validate/preview/create 合同且不连接设备直到正式创建执行要求发生

#### Scenario: 研究者编写 Benchmark
- **WHEN** 用户明确进入 Benchmark 高级能力
- **THEN** Studio 提供现有 Authoring、Validation、Contract Test、Freeze、Release 和 Migration deep links，不隐藏这些研究功能或把它们改造成 AgentGraph 节点

#### Scenario: Experiment 创建能力受限
- **WHEN** 服务声明单 Agent、单 Task 或单 repeat 等 cardinality 限制
- **THEN** 创建流程在相关选择步骤展示正式限制并阻止不支持的组合，不截断用户选择或把限制藏到最终运行错误

### Requirement: Runs 入口必须统一发现而不合并资源语义
Runs SHALL 为普通 Agent Runs 与 Benchmark Experiments 提供一致的历史发现入口和清晰的类型切换。两类记录 MUST 继续使用独立 typed query、resource identity、状态轴、筛选和权威 deep links；Studio MUST NOT 从普通 Agent success 推导 Benchmark pass，也不得用一个伪统一 DTO 丢失 Experiment/TaskRun 事实。

#### Scenario: 查看普通 Run 历史
- **WHEN** 用户在 Runs 中选择普通 Agent Runs
- **THEN** 页面只查询和显示 durable ordinary Run/Replay 记录，并使用其正式 Run、Agent 和 Replay identity

#### Scenario: 查看 Benchmark Experiment 历史
- **WHEN** 用户切换到 Benchmark Experiments
- **THEN** 页面进入或组合现有 Experiment History，保留 lifecycle、outcome、report、TaskRun、evidence 与 Replay availability 的独立事实

#### Scenario: 从旧 History deep link 进入
- **WHEN** 用户打开既有普通 `/history` 或 Experiment History deep link 及其合法筛选参数
- **THEN** Studio 保留原查询语义并在新的 Runs 导航中显示正确类型，不丢弃 cursor、filter 或资源 scope

### Requirement: 页面必须采用渐进披露和稳定的操作层级
Studio 首屏 SHALL 优先显示对象名称、用户目标、当前状态、阻塞原因摘要和唯一下一步。常用主操作 MUST 与破坏性、迁移、导入导出、版本和审计操作在视觉及交互上区分；raw identity、revision、canonical hash、contract、provenance、完整 diagnostics 和 payload MUST 保留为可访问的详情，但不得在无上下文时主导首页、目录或工作区头部。

#### Scenario: 打开 Agent Design
- **WHEN** 用户打开一个 Agent 的 Design 工作区
- **THEN** 默认操作层级突出 Validate、Save 和 Run，Save As、Import、Export、Load Revision 与 Reset 位于明确的次级区域，且其安全确认与既有语义不变

#### Scenario: 运行环境未准备好
- **WHEN** AgentGraph valid 但 SecretRef 或 Device Profile 未配置
- **THEN** 页面显示简明阻塞摘要与前往设置的动作，并允许展开查看正式 readiness diagnostics；它不把 graph 标记为 invalid，也不在头部持续展示完整技术 dump

#### Scenario: 用户需要审计身份
- **WHEN** 用户主动展开技术详情或 Inspector
- **THEN** Studio 提供已有 revision、canonical identity、contract、provenance、integrity 与安全 diagnostics，不因默认简化而删除、改写或猜测这些事实

### Requirement: 首次使用引导必须可跳过、可恢复且基于事实
Studio SHALL 为首次用户提供短小的黄金路径，引导其从正式示例或 Agent 创建进入设计、验证、运行、结果与 Replay。引导状态 MAY 作为非语义用户偏好持久化，但资源完成状态、环境 readiness 和运行结果 MUST 来自权威服务；引导 MUST 可跳过、可重新打开，并且不得阻止熟悉用户直接使用 deep link 或高级功能。

#### Scenario: 使用正式示例完成首次路径
- **WHEN** 新用户选择“从示例开始”
- **THEN** Studio 先说明示例目标与真实前置条件，再使用正式模板或已有示例资源进入 Agent Design，并在每个阶段只提示当前可执行的下一步

#### Scenario: 用户跳过引导
- **WHEN** 用户关闭首次使用引导
- **THEN** Studio 立即恢复完整产品导航，将跳过状态仅作为展示偏好保存，并提供可重新打开的帮助入口

#### Scenario: 示例所需环境不可用
- **WHEN** 模型 SecretRef 或安全 Device Profile 未配置
- **THEN** 引导显示真实阻塞状态和配置路径、保留已创建资源，不宣称示例可运行、不生成 fake Run，也不暴露 secret、raw serial 或宿主路径

### Requirement: 兼容入口和页面状态必须安全迁移
既有 `/builder`、`/benchmark`、`/benchmarks`、`/experiments/new`、`/experiments`、`/history`、Agent Design/Run 和 Replay deep links SHALL 保持可达或通过确定性兼容导航到等价正式上下文。Loading、empty、invalid URL、not found、permission/configuration 和 network failure MUST 在其所属页面被区分；兼容迁移 MUST NOT 静默选择错误 Agent、Run、Experiment 或 revision。

#### Scenario: 打开无 Agent identity 的旧 Builder 入口
- **WHEN** 用户访问 `/builder` 且没有明确的最近 Agent 选择依据
- **THEN** Studio 导航到唯一 Agent Library 或创建流程，不随机打开某个 Agent，也不生成浏览器临时 identity 冒充持久资源

#### Scenario: 打开不存在的资源 deep link
- **WHEN** URL 引用不存在或 scope 不匹配的 Agent、Run、Experiment、Report 或 Replay
- **THEN** Studio 显示安全 not-found/identity-mismatch 状态和返回所属 Library/History 的动作，不渲染其他资源的缓存内容

#### Scenario: 前端刷新后恢复上下文
- **WHEN** 用户在 Agent 工作区、筛选后的 Runs 或 Experiment 详情页刷新浏览器
- **THEN** Studio 从 URL 和权威 query 重建同一对象、模式和合法筛选，不依赖先前内存中的导航或 onboarding 状态
