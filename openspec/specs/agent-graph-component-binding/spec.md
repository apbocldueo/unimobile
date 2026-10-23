# agent-graph-component-binding Specification

## Purpose
TBD - created by archiving change implement-agent-graph-runtime. Update Purpose after archive.
## Requirements
### Requirement: 校验先于运行时绑定
系统 SHALL 只对已经通过 AgentGraph 结构、profile 和语义校验的图执行组件绑定。绑定阶段 MUST 与 source compiler 分离，且 source compiler MUST 继续保持无组件实例化、无设备连接和无真实密钥解析的副作用边界。

#### Scenario: 非法图不触发组件解析
- **WHEN** AgentGraph 包含不兼容端口、缺失必需节点或非法循环
- **THEN** 系统在调用组件 resolver、secret provider 或设备 provider 之前返回图诊断

#### Scenario: 编译与绑定阶段分离
- **WHEN** 调用方仅把 Python、YAML 或 FlowDocument 编译为 AgentGraph
- **THEN** 系统不会创建组件实例或连接 fake/真实设备

### Requirement: 可注入的组件解析边界
系统 SHALL 通过可注入的 `ComponentResolver` 按组件绑定中的 namespace、name、version、params、dependency refs 和 secret refs 解析组件实例，并 SHALL 生成保持原始逻辑节点 ID 的绑定图。解析出的真实密钥 MUST 仅存在于运行时依赖边界，MUST NOT 回写 AgentGraph 或诊断文本。

#### Scenario: 解析内置组件
- **WHEN** 合法组件节点引用当前 registry 中已注册且角色兼容的组件
- **THEN** resolver 返回绑定到该逻辑节点的组件实例并保留其节点 ID

#### Scenario: 组件不存在
- **WHEN** 组件绑定引用无法解析的 namespace、name 或 version
- **THEN** 绑定失败并返回包含逻辑节点 ID 和非敏感组件标识的结构化错误，且运行尚未开始

#### Scenario: 解析 secret reference
- **WHEN** 组件参数包含 secret reference
- **THEN** resolver 向组件提供解析值，但绑定图、RunEvent 和错误信息均不包含真实 secret

### Requirement: 角色协议检查与调用适配
系统 SHALL 在绑定时检查组件角色、NodeContract 与统一组件协议是否兼容，并 SHALL 通过按 Contract 注册的 Input/Output Adapter 把图端口值转换为现有协议 DTO、把组件返回值规范化为图端口值。携带 ComponentSpec 的新式组件 MUST 通过正式定义预检；显式本地结构化对象 MAY 使用 Protocol 路径；旧组件 SHALL 仅通过已声明 Legacy Adapter 路径接入。系统 MUST NOT 把未类型化的任意字典直接作为所有角色的统一输入，也 MUST NOT 在新式定义失败时回退到宽松路径。

#### Scenario: Reasoning 缺少可选 Planner
- **WHEN** 图中不存在 Planner 且 Reasoning 的 plan 端口未连接
- **THEN** Reasoning assembler 生成稳定的空计划语义并以合法 `ReasoningInput` 调用组件

#### Scenario: Verifier 获取动作前后状态
- **WHEN** post_action Verifier 被调度
- **THEN** Verifier assembler 使用同一步中动作前 Observation、动作后 Observation、Action 和可选 ActionResult 生成输入

#### Scenario: Memory 接收多种写入值
- **WHEN** Memory 的 write 端口接收 TaskInput、PlanResult、Action、ActionResult 或 VerifierResult
- **THEN** Memory assembler 按稳定映射将值包装为合法 Memory 操作，而不要求各上游组件了解 Memory 的内部 DTO

#### Scenario: 角色与协议不兼容
- **WHEN** Perception 节点解析到不满足 Perception 调用协议的对象
- **THEN** 绑定阶段返回该节点的 role/protocol mismatch 且不进入执行循环

#### Scenario: 新式角色与 Contract 不兼容
- **WHEN** Perception 节点解析到声明 Reasoning ComponentSpec 的实现
- **THEN** 绑定阶段返回该节点的 role/contract mismatch 且不进入执行循环

#### Scenario: 本地结构化组件
- **WHEN** SDK 显式注入未声明 ComponentSpec 但具有兼容 typed invoke 的本地对象
- **THEN** binder 可通过 Protocol 路径使用该对象，同时不把它加入可发现组件 catalog

#### Scenario: 新式定义不得降级绕过
- **WHEN** ComponentSpec 的签名、配置或运行时类型声明不合法
- **THEN** binder 返回定义错误而不是把实现重新解释为普通鸭子类型或旧组件

### Requirement: 有序 fallback 的运行级选择
声明 fallback 策略的组件节点 SHALL 按 AgentGraph 中的候选顺序尝试候选。候选在一次运行中成功后 SHALL 作为该节点的运行级选择被复用；候选失败、切换和最终耗尽 MUST 可观察且不得改变 canonical AgentGraph。

#### Scenario: 首选候选成功
- **WHEN** fallback 节点的第一个候选成功解析并完成首次调用
- **THEN** 同一次运行后续调用继续使用该候选且不重新排序

#### Scenario: 首选候选调用失败
- **WHEN** fallback 节点的当前候选在调用时失败且仍有后续候选
- **THEN** Runtime 记录非敏感候选失败事件，按声明顺序尝试下一候选并把成功选择保持到本次运行结束

#### Scenario: 候选全部失败
- **WHEN** fallback 节点的所有候选均无法解析或调用
- **THEN** 该节点失败并遵循普通节点失败语义，Runtime 不静默跳过该节点

### Requirement: 旧组件通过 adapter 兼容
系统 SHALL 允许现有 `BasePerception.perceive()`、`BaseReason.think()` 等旧组件通过显式 adapter 参与 Graph Runtime，且 MUST 保持现有协议 DTO 的身份兼容。adapter MUST 位于组件边界，Graph Runtime 核心不得为某个具体旧插件硬编码分支。

#### Scenario: 绑定旧 Reasoning 实现
- **WHEN** registry 返回仅实现旧 `think()` 接口的已支持 Reasoning 插件
- **THEN** resolver 使用 Reasoning adapter 将统一 invoke 调用转发到旧接口并返回规范化 Action

#### Scenario: 不支持的旧组件
- **WHEN** 旧组件无法被已声明 adapter 安全转换
- **THEN** 绑定失败并给出可定位诊断，而不是猜测参数或吞掉异常

### Requirement: Binding 由 NodeContract 驱动而非固定 role 分支
绑定阶段 SHALL 先解析节点的 NodeContract，再通过该 contract 的 invocation adapter 检查组件实现、组装 typed input 并规范化 typed output。GraphExecutionKernel MUST 只调用 BoundNode invocation boundary，不得包含固定六类 role assembler 分支。

#### Scenario: 绑定 Grounder
- **WHEN** Grounder 节点引用合法 contract 和兼容组件
- **THEN** binder 生成接受 GroundingInput、返回 GroundingResult 的 BoundNode且无需修改 Kernel

#### Scenario: 输出类型错误
- **WHEN** 扩展 Tool 实现返回不符合 contract output port 的对象
- **THEN** invocation 失败并产生包含 node path、contract ID 和实际类型的安全错误

### Requirement: Built-in 与 extension catalog 合并确定且显式
Binder SHALL 接收内置 catalog 和零个或多个显式 extension catalog，并按稳定优先级解析 contract。重复 contract ID/version 但定义不同 MUST 被拒绝；本能力 MUST NOT 自动扫描安装环境。

#### Scenario: 冲突契约定义
- **WHEN** 两个 extension catalog 为同一 ID/version 声明不同端口
- **THEN** binding 在组件解析前失败且不任意选择一个定义

### Requirement: 子图 binding 保留层级身份和隔离
Binder SHALL 递归绑定通过校验的 Subgraph，并为每个节点保留完整 logical path、局部 binding、fallback 状态和 state scope。兄弟子图使用同一组件候选时 MAY 共享显式声明的依赖服务，但 MUST NOT 隐式共享 sticky fallback 选择或私有组件状态。

#### Scenario: 两个 Agent 子图使用同名 Reasoning
- **WHEN** Manager 和 Critic 子图都绑定 `reasoning/default`
- **THEN** BoundNode path 和运行级选择独立，除非 contract/binding 明确声明安全共享实例

### Requirement: 有副作用节点的恢复策略受 contract 限制
NodeContract SHALL 标记副作用分类。ActionExecutor、Device 或其他非幂等节点发生调用失败后，binder/runtime MUST NOT 自动切换 fallback 或重试，除非 contract 与 graph policy 显式声明幂等或补偿语义。

#### Scenario: Tool 是只读幂等调用
- **WHEN** 只读 Tool contract 声明可重试且首选候选在调用前失败
- **THEN** runtime 可按声明策略切换候选并记录事件

#### Scenario: 设备动作结果不确定
- **WHEN** ActionExecutor 调用后失败且副作用是否发生未知
- **THEN** runtime 不自动调用下一候选

### Requirement: 内置组件使用确定性 catalog 绑定
系统 SHALL 提供显式且版本化的内置组件 catalog/bootstrap，覆盖本闭环所需的 Perception、Reasoning、Memory、Planner、Verifier、Grounder 和 LLM 实现。生产 binder SHALL 按 namespace、name、version、params 和 dependencies 解析所选组件；未被图引用的可选组件或可选依赖失败 MUST NOT 阻止基础包导入。

#### Scenario: 绑定最小截图 Agent
- **WHEN** 图引用 `screenshot_perception`、`universal_reasoning`、`sliding_window_memory` 及受支持 LLM
- **THEN** binder 通过内置 catalog 构造所有 Agent 组件，并保持声明节点 ID 和依赖关系

#### Scenario: 未安装视觉 extra
- **WHEN** 环境未安装重型视觉依赖且图只使用 screenshot perception
- **THEN** 内置绑定成功，不因未选择的 OmniParser 或其他视觉组件不可用而失败

#### Scenario: 选择缺少依赖的组件
- **WHEN** 图显式选择需要未安装 extra 的组件
- **THEN** 绑定在运行前返回包含组件标识和所需 extra 的结构化错误

### Requirement: 内置 LLM 作为显式依赖解析
需要模型的内置组件 SHALL 通过 component dependency 声明获取 LLM 实例。Resolver MUST 支持嵌套 LLM component reference、SecretRef 和显式 dependency provider，并把依赖映射到旧构造函数所需的参数名；真实 secret MUST 只存在于绑定期对象中。

#### Scenario: UniversalReason 绑定 OpenAI LLM
- **WHEN** Reasoning binding 声明一个带 SecretRef 的内置 OpenAI LLM dependency
- **THEN** resolver 构造 LLM 后通过 adapter/constructor mapping 注入 UniversalReason，AgentGraph 和事件不包含真实 key

### Requirement: 内置旧组件通过统一 adapter 执行
当前只实现 `perceive()`、`think()`、`add()/get_working_context()`、`make_plan()`、`verify()` 或 `ground()` 的内置组件 SHALL 通过现有统一 adapter 接入 BoundNode。adapter SHALL 完成 contract DTO 与旧协议 DTO 的确定性转换；GraphExecutionKernel MUST NOT 根据组件类名或插件名称增加分支。

#### Scenario: 旧 screenshot perception
- **WHEN** contract 1.1 Perception 节点解析到现有 ScreenshotPerception
- **THEN** adapter 将 DeviceObservation 转换为旧 PerceptionInput，并把结果规范化为公共 PerceptionResult

#### Scenario: 旧 reasoning 返回 action 和 raw response
- **WHEN** UniversalReason 返回旧式 `(Action, raw_response)`
- **THEN** adapter 返回规范化 Action，并以安全 metadata/事件保留可审计原始响应引用

### Requirement: 内置绑定与运行 service 分离
DeviceObserve 和 ActionExecutor SHALL 由 Android runtime 作为 run-scoped services 注入，内置 Agent component resolver MUST NOT 在编译或组件绑定阶段创建 AndroidDevice。用于组装 ActionExecutionInput 的框架 transform MAY 作为无设备状态的内置组件绑定。

#### Scenario: 编译并绑定但不运行
- **WHEN** 用户在无 ADB 环境 compile_agent 一个合法 Android AgentGraph
- **THEN** Agent 组件完成绑定，但 AndroidDevice、DeviceObserve 和 ActionExecutor service 尚未创建

### Requirement: 有状态内置组件按运行隔离
Memory、Planner 或其他具有瞬态状态的内置组件 MUST 按 run 创建或在运行开始时确定性重置。连续调用同一 ExecutableAgent 不得隐式继承上一次任务的运行状态，除非图显式引用持久化 Memory service。

#### Scenario: 连续运行两个任务
- **WHEN** 同一 ExecutableAgent 连续运行任务 A 与任务 B
- **THEN** 任务 B 的 SlidingWindowMemory 不包含任务 A 的动作历史

### Requirement: ComponentSpec 预检先于组件构造和设备分配
Binder SHALL 在构造新式外部组件前验证 ComponentSpec 身份、ZhiXing 兼容范围、精确 NodeContract、作者基类或装饰器签名、配置模型和运行时类型绑定。仅当预检与配置解析成功后，resolver 才可构造组件；该过程 MUST 发生在 AndroidDevice、模型调用和运行循环开始之前。

#### Scenario: 配置字段错误
- **WHEN** AgentGraph 为外部组件提供不符合其配置模型的参数
- **THEN** binding 返回包含安全字段路径的 component-config-invalid，且组件构造函数未执行

#### Scenario: 版本不兼容
- **WHEN** ComponentSpec 的 ZhiXing 兼容范围不包含当前框架版本
- **THEN** binding 返回 component-version-incompatible，且不解析 secret 或依赖

#### Scenario: 预检成功后构造
- **WHEN** ComponentSpec、Contract、配置和运行时类型均合法
- **THEN** resolver 使用验证后的参数与显式依赖创建 run-scoped 实例并保留原始组件身份

### Requirement: 实际返回值在 NodeContract 边界校验
静态标注和定义预检 MUST NOT 被当作组件运行正确的证明。每次新式组件调用完成后，Runtime SHALL 根据 NodeContract 输出端口和运行时类型绑定校验实际结果；不兼容结果 MUST 产生安全的节点失败，并 MUST NOT 流入后续组件或被宣称为成功。

#### Scenario: 标注正确但返回错误
- **WHEN** 外部 Verifier 标注返回 `VerifierResult` 但实际返回字符串
- **THEN** Verifier 节点以 runtime-output-type 失败，后续成功分支不被执行

#### Scenario: 多输出映射缺失
- **WHEN** 自定义 Contract 声明多个输出端口但实现返回非 Mapping 单值
- **THEN** Runtime 返回 output-mapping-required 并标识安全节点路径与 Contract

