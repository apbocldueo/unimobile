# agent-graph-runtime Specification

## Purpose
TBD - created by archiving change implement-agent-graph-runtime. Update Purpose after archive.
## Requirements
### Requirement: 单一 AgentGraph 执行入口
系统 SHALL 提供单一 Graph Runtime 执行入口，接收通过校验和绑定的 AgentGraph、TaskInput、RuntimeContext 及运行服务，并返回 RunResult。Python、图原生 YAML、Studio FlowDocument 或兼容 AgentConfig 只要编译为语义相同的 AgentGraph，MUST 由同一入口执行而不是分叉成不同调度器。

#### Scenario: 三种 authoring surface 执行同一图
- **WHEN** Python、图原生 YAML 和 Studio FlowDocument 编译出 canonical hash 相同的 AgentGraph 并绑定同一组 fake components
- **THEN** Graph Runtime 产生相同的节点执行顺序、条件选择和终止状态

#### Scenario: Runtime 只接收已绑定图
- **WHEN** 调用方尝试执行仅完成解析但尚未校验或绑定的对象
- **THEN** 执行入口拒绝启动并返回明确的阶段错误

### Requirement: 确定性生命周期调度
GraphExecutionKernel SHALL 按显式 execution policy、data readiness、control activation、State scope、Loop 和 Subgraph 结构确定性调度节点，并使用稳定 logical path 解决同优先级顺序。contract 1.0 的 `on_run_start`、`per_step`、`post_action`、`stateful` 和 `terminal` 生命周期 SHALL 由 compatibility facade 转换为等价 execution plan；Kernel MUST NOT 根据 Planner、Perception、Reasoning、Verifier 等角色硬编码调用阶段。

#### Scenario: Planner 仅运行一次
- **WHEN** 一个 contract 1.0 图包含 `on_run_start` Planner 并执行多个 interaction step
- **THEN** compatibility facade 保持 Planner 只执行一次且 PlanResult 可复用

#### Scenario: 可选节点缺省
- **WHEN**旧合法图不包含 Planner、Memory 和 Verifier
- **THEN** compatibility facade 仍能执行最小链且缺省可选输入不阻塞节点

#### Scenario: 新图两个 Reasoning 节点
- **WHEN** contract 1.1 图的 manager 和 operator Reasoning 同时满足各自输入与 control
- **THEN** Kernel 按 logical path 和显式依赖执行二者，不将 role 当作唯一槽位

#### Scenario: 已存在节点失败
- **WHEN**任意已激活组件节点失败且没有显式恢复策略
- **THEN** Kernel 将节点或父结构标记为失败而不是因其 contract 可选而静默跳过

#### Scenario: 已存在的可选节点失败
- **WHEN** 图中存在的 Verifier 调用失败且没有显式恢复策略
- **THEN** compatibility facade 将运行标记为失败而不是因为 Verifier 角色可选就跳过异常

### Requirement: 类型化值存储与节点就绪
Graph Runtime SHALL 维护按运行、步骤、逻辑节点和端口寻址的类型化 ValueStore。节点仅在全部必需 data 输入可用、可选 data 输入已确定为有值或缺省、且存在 incoming control edge 时至少一条控制边被激活后才可执行；同优先级就绪节点 MUST 使用稳定逻辑顺序执行。

#### Scenario: 必需输入未到达
- **WHEN** Reasoning 的必需 perception 输入尚未产生
- **THEN** Runtime 不调用 Reasoning，并在图无法继续推进时报告 deadlock 诊断而不是传入空字典

#### Scenario: 未激活条件分支
- **WHEN** Condition 仅激活 true control edge
- **THEN** false 分支节点不会执行且不会阻塞 true 分支后的合法终止

#### Scenario: 稳定执行次序
- **WHEN** 多个无依赖的同生命周期节点同时就绪
- **THEN** Runtime 按图中稳定逻辑身份规则产生可复现的执行顺序

### Requirement: 观察—决策—动作—再观察闭环
contract 1.0 compatibility facade SHALL 保持每个 interaction step 的动作前观察、Perception/Reasoning、ActionExecutor 和按需动作后观察语义。contract 1.1 图 SHALL 通过显式 DeviceObserve/Mobile service 节点和 ActionExecutor contract 决定观察与设备动作顺序；GraphExecutionKernel MUST NOT 自动观察设备、直接映射 Action 或要求每次 local iteration 都执行物理动作。

#### Scenario: fake device 顺序执行
- **WHEN** contract 1.0 顺序图在 fake ObservationProvider 和 fake ActionExecutor 上运行一步
- **THEN** compatibility facade 保持动作前观察、Perception、Reasoning、ActionExecutor 的调用顺序

#### Scenario: ReAct 动作前工具循环
- **WHEN** contract 1.1 ReAct 图在产生 Action 前执行多个 Tool activation
- **THEN** Kernel 不在每个 Tool iteration 之间自动观察设备或推进 interaction step

#### Scenario: UGround 显式链
- **WHEN** graph 连接 DeviceObserve、Perception、Reasoning、Grounder 和 ActionExecutor
- **THEN** 服务与组件只按数据/control readiness 执行，Kernel 不包含 UGround 特判

#### Scenario: ActionExecutor 是唯一动作边界
- **WHEN** contract 1.0 或 1.1 图执行 click、type、swipe 或 finish Action
- **THEN** 设备副作用只经当前绑定的 ActionExecutor 发生，Runtime 和 Kernel 均不按动作类型直接调用设备 API

#### Scenario: Verifier 使用两次观察
- **WHEN** contract 1.0 图包含 post_action Verifier
- **THEN** compatibility facade 在动作后再次观察，并向 Verifier 提供同一步不同的 before/after Observation

### Requirement: RuntimeContext 贯穿实际执行链
一次运行 MUST 创建或接收一个 RuntimeContext 实例，并把同一实例传入该运行内的组件调用、ActionExecutor、fallback 状态和事件产生过程。Runtime SHALL 在进入新步骤前更新 context 的 step，并 SHALL 将节点产生的 AgentState 变化保持到运行结束。

#### Scenario: 同一 Context 实例
- **WHEN** 一个图依次调用 Perception、Reasoning、ActionExecutor 和 Verifier
- **THEN** 所有组件收到对象身份相同的 RuntimeContext 且 run_id 一致

#### Scenario: 步骤更新
- **WHEN** 图执行第二个交互步骤
- **THEN** 第二步组件看到更新后的 step，而第一步保存的历史和策略状态仍可访问

### Requirement: 结构化条件只激活一个控制分支
Condition 节点 SHALL 使用 AgentGraph 定义的结构化 Predicate 对已存在的端口值求值，并只激活 `true` 或 `false` 对应的 control edge。Runtime MUST NOT 使用 `eval` 或执行来自配置的代码。

#### Scenario: Verifier 失败分支
- **WHEN** Condition 对 VerifierResult.is_success 执行 `eq false` 且结果为真
- **THEN** Runtime 只激活 true control edge 并保持业务值由独立 data edge 传递

#### Scenario: 字段路径不存在
- **WHEN** Predicate 读取不存在的字段且操作符不是存在性检查
- **THEN** Condition 节点失败并产生可定位错误，而不是把缺失字段任意解释为 false

### Requirement: 反馈边是有界的跨步骤反馈
feedback edge SHALL 在源谓词命中时把类型化反馈值锁存到下一交互步骤，而不是在当前步骤内直接重新调用目标节点。下一步骤 MUST 重新执行动作前观察和该目标之前的必要感知链；每条反馈边 SHALL 独立计数并遵循 `max_iterations` 与 `on_exhausted`。

#### Scenario: 验证失败触发下一步重试
- **WHEN** 第一步 Verifier 失败并命中返回 Reasoning 的 feedback edge
- **THEN** Runtime 锁存 VerifierResult，开始下一步骤，重新观察和感知后再把反馈提供给 Reasoning

#### Scenario: 反馈未命中
- **WHEN** feedback predicate 为 false
- **THEN** Runtime 不增加该边计数并继续其普通激活路径

#### Scenario: 反馈耗尽并失败
- **WHEN** feedback 已达到 max_iterations 且 `on_exhausted` 为 `fail`
- **THEN** Runtime 以 FAILURE 终止并保留最后一次反馈与动作结果

#### Scenario: 反馈耗尽并继续
- **WHEN** feedback 已达到 max_iterations 且 `on_exhausted` 为 `continue`
- **THEN** Runtime 不再激活反馈目标，并允许源节点的普通下游路径继续

#### Scenario: 反馈耗尽并终止
- **WHEN** feedback 已达到 max_iterations 且 `on_exhausted` 为 `terminate`
- **THEN** Runtime 终止执行并保留当时可用的最终结果，不再开始新步骤

### Requirement: 反馈、终止与输出具有固定优先级
同一节点求值同时使反馈和普通输出/terminal 路径可用时，命中的且未耗尽的 feedback edge SHALL 优先，普通 terminal 激活 SHALL 延迟到反馈不再触发或耗尽策略允许继续。ActionResult data edge 写入 output 节点 SHALL 仅表示结果可收集，MUST NOT 自身绕过反馈策略立即宣告成功。

#### Scenario: ActionResult 已产生但 Verifier 要求反馈
- **WHEN** ActionResult 已进入 output 节点且随后 Verifier 失败并命中未耗尽 feedback edge
- **THEN** Runtime 保存 ActionResult 但开始下一步骤，不以成功提前终止

#### Scenario: Agent 显式完成
- **WHEN** Action 或 ActionResult 表示受支持的 DONE/FINISH 终止且没有更高优先级反馈
- **THEN** Runtime 结束循环并把状态映射为 SUCCESS

#### Scenario: Agent 显式失败
- **WHEN** Action 或 ActionResult 表示受支持的 FAIL 终止
- **THEN** Runtime 结束循环并把状态映射为 FAILURE

### Requirement: 运行边界与旧路径兼容
Graph Runtime SHALL 支持正常成功、组件失败、设备失败、步数上限和取消，并 SHALL 映射为稳定 RunStatus。现有 `ModularAgent` 和 `AgentRunner` MUST 继续可按原入口运行；兼容保留不要求 Graph Runtime 在本 change 内替换所有旧架构。

#### Scenario: 达到步数上限
- **WHEN** 图既未成功也未失败且达到 RuntimeContext.max_steps
- **THEN** Runtime 停止调度并返回 STEP_LIMIT

#### Scenario: 设备观察失败
- **WHEN** ObservationProvider 报告设备不可用
- **THEN** Runtime 不继续调用后续 Agent 节点并返回 DEVICE_FAILURE

#### Scenario: 运行被取消
- **WHEN** 取消信号在两个节点之间被观察到
- **THEN** Runtime 不启动新节点并返回 CANCELLED

#### Scenario: 旧 ModularAgent 回归
- **WHEN** 调用方继续使用现有 AgentFactory、ModularAgent 和 AgentRunner 入口
- **THEN** 旧路径仍能按既有测试运行且不被强制构造 AgentGraph Runtime

### Requirement: 通用 GraphExecutionKernel 不依赖 Agent 范式
系统 SHALL 提供只依赖 Bound execution plan、NodeContract invocation、Value/State stores、control structures 和 runtime services 的 GraphExecutionKernel。Kernel 源码和注册选择 MUST NOT 根据 Modular、Reflection、ReAct、Planner-and-Execute、UGround 或 Multi-Agent 名称分叉。

#### Scenario: 六种模板使用同一 Kernel
- **WHEN** 六种代表性 template 绑定 fake components/services
- **THEN** 它们通过同一个 Kernel public entry 执行并由图结构决定不同调用顺序

### Requirement: Compatibility facade 委托 Kernel
现有 GraphRuntime 公共入口 SHALL 保持签名与已验证结果语义，并 SHALL 通过适配 execution plan 委托 GraphExecutionKernel。实现 MUST NOT 长期复制一套独立旧 scheduler；旧 ModularAgent/AgentRunner 路径继续单独保留。

#### Scenario: 现有 Runtime 回归
- **WHEN** 当前 GraphRuntime 顺序、条件和 feedback 测试运行
- **THEN** 结果、事件关键字段和状态保持兼容且执行经过 Kernel

### Requirement: Kernel 执行边界与预算
Kernel SHALL 在 run、interaction、subgraph 和 loop 层维护独立有限预算，并在节点边界观察取消。预算或取消命中后 MUST 停止启动该作用域的新 activation，并返回可定位到层级 path 的状态。

#### Scenario: Local Loop 达到预算
- **WHEN** Loop iteration 未超过自身 max_iterations 但父 Subgraph activation budget 已耗尽
- **THEN** Kernel 停止子图并报告父预算耗尽，不继续启动 loop body

### Requirement: 真实设备图仍由显式控制流驱动
GraphExecutionKernel SHALL 以与 fake services 相同的方式调用真实 DeviceObserve 和 ActionExecutor services。Android facade MUST 只装配设备、RuntimeContext、artifacts 和 services，MUST NOT 插入隐藏观察、动作、反馈或终止步骤。

#### Scenario: 图决定重新观察
- **WHEN** AgentGraph 在 ActionExecutor 后连接第二个 DeviceObserve 节点
- **THEN** Kernel 在动作完成后按图执行重新观察

#### Scenario: 图不请求重新观察
- **WHEN** AgentGraph 在动作后直接终止且没有 DeviceObserve activation
- **THEN** Android facade 不额外采集观察

#### Scenario: 图内局部工具循环
- **WHEN** ReAct 子图在一次 interaction 内执行多个 Tool activation 后才产生 Action
- **THEN** Android Runtime 不在工具循环之间隐式调用设备或推进 interaction

### Requirement: Kernel 调度状态与 Agent outcome 分离
Android 图运行结果 SHALL 分别表达 Kernel 调度状态与 Agent outcome。成功完成 execution plan 不得自动等同于 Agent 任务成功；DONE、FAIL、STEP_LIMIT、CANCELLED、DEVICE_FAILURE 和无明确终止的完成状态 MUST 通过稳定规则映射到 RunResult。

#### Scenario: Kernel 完成且 Agent DONE
- **WHEN** execution plan 正常结束且类型化 ActionResult 表示 DONE
- **THEN** KernelStatus 为成功并且 Agent outcome/RunStatus 为 SUCCESS

#### Scenario: Kernel 完成但 Agent FAIL
- **WHEN** ActionExecutor 正常返回类型化 FAIL 终止
- **THEN** KernelStatus 可保持成功调度，但 Agent outcome/RunStatus 为 FAILURE

#### Scenario: Android service 失败
- **WHEN** DeviceObserve 或 ActionExecutor 报告设备断开
- **THEN** Kernel 停止无恢复策略的后续节点，RunStatus 映射为 DEVICE_FAILURE

#### Scenario: 无终止输出
- **WHEN** execution plan 已无可运行节点且未产生支持的终止结果
- **THEN** RunResult 明确报告非成功终止原因，不得猜测任务成功

### Requirement: 物理 interaction 由执行结果确认
Runtime SHALL 分别维护 node activation、Agent decision/step 与物理 device interaction 计数。只有 ActionExecutor 成功返回确认已执行的设备 effect 时才增加物理 interaction；contract 静态副作用标签本身不足以证明动作发生。

#### Scenario: 点击成功计数
- **WHEN** TAP 的 ActionResult 为成功且 effect_performed 为 true
- **THEN** 物理 interaction 计数增加一次

#### Scenario: 点击命令失败
- **WHEN** TAP 已激活但底层 ADB 命令失败且 effect 未确认
- **THEN** activation 被记录但物理 interaction 计数不增加

#### Scenario: DONE 不计物理动作
- **WHEN** DONE 结束运行
- **THEN** Agent decision/activation 可增加，但物理 interaction 计数不增加

### Requirement: 同一 RuntimeContext 贯穿 Android service 链
Android run facade SHALL 把同一个 RuntimeContext 实例传入 Kernel、DeviceObserve、Agent components、ActionExecutor、event sink 和 artifact store。设备 identity 与 artifact namespace SHALL 绑定本次 run，反馈或 loop activation 不得创建不相关的新 run context。

#### Scenario: 观察与动作共享上下文
- **WHEN** 图依次执行 DeviceObserve、Perception、Reasoning 和 ActionExecutor
- **THEN** 所有调用观察到相同 RuntimeContext 对象身份、run_id 和目标 device identity

#### Scenario: 反馈推进 interaction
- **WHEN** Verifier 触发到下一 interaction 的 feedback
- **THEN** context 保留 run identity 和 AgentState，同时更新 interaction position 并分配新的 artifact sequence

### Requirement: Android Graph Runtime 不破坏旧执行入口
新 Android 图路径 SHALL 增量接入通用 Kernel；旧 GraphRuntime compatibility facade、ModularAgent 和 AgentRunner SHALL 继续按既有测试语义运行。实现 MUST NOT 把旧 Runner 的动作 switch 复制到新 Kernel。

#### Scenario: 新旧回归并存
- **WHEN** 测试分别运行 Bound AgentGraph Android path 与旧 ModularAgent fake-device path
- **THEN** 两条入口均通过各自契约，且新 Kernel 源码不包含 Android action-type dispatch

### Requirement: 内置组件形成多步 Mobile Agent 执行链
GraphExecutionKernel SHALL 能通过 BoundExecutionPlan 执行由内置 DeviceObserve、Perception、可选 Planner、Memory、Reasoning、可选 Grounder/Verifier、Action 组装 transform 和 ActionExecutor 构成的多步 Mobile Agent 图。节点调用顺序、可选路径、终止与重试 MUST 由显式图结构决定，不得由 ExecutableAgent 或 Kernel 隐藏插入固定策略循环。

#### Scenario: 最小 ReAct 风格 Android 图
- **WHEN** 图把观察、截图感知、记忆读取、推理、动作组装和 ActionExecutor 连成有界循环
- **THEN** Kernel 重复执行图声明的交互链，直到 DONE、FAIL、设备失败、取消或预算耗尽

#### Scenario: 增加 Planner
- **WHEN** 用户在同一图中加入一次性 Planner 并把 plan 连接到 Reasoning
- **THEN** Kernel 按连接执行 Planner，不要求切换为 PlannerAgent 策略类

#### Scenario: 增加 Verifier 反馈
- **WHEN** 用户加入 post-action observation、Verifier 和失败 feedback
- **THEN** Kernel 在验证失败时按 feedback 上限进入下一交互，而不是由旧 ModularAgent 控制重试

### Requirement: 新闭环不得委托旧策略执行循环
`ExecutableAgent.run()` 和新 CLI 的 graph-native 路径 SHALL 直接委托 GraphExecutionKernel/AndroidGraphRuntime。它们 MUST NOT 构造 AgentFactory、ModularAgent、ReflectionAgent、AgentRunner 或按 agent_type 选择旧执行策略。

#### Scenario: 新 YAML 运行
- **WHEN** graph-native YAML 通过新 CLI 执行
- **THEN** spy/集成测试观察到新 binder 与 GraphExecutionKernel 被调用，旧 AgentFactory 和 AgentRunner 未被调用

### Requirement: 每个内置节点调用产生结构化事件
每个被激活的内置组件和 runtime service 节点 SHALL 产生可排序的 start 以及 complete 或 fail RunEvent。事件 MUST 包含 run、node path、contract/role、interaction、activation 和耗时身份，并提供有界安全的输入输出摘要。

#### Scenario: 一次物理点击
- **WHEN** 图依次执行 DeviceObserve、Perception、Reasoning 和 ActionExecutor
- **THEN** 四个节点均有匹配的 start/complete 事件，且 ActionExecutor 摘要能表明动作类型与确认的 effect 而不包含截图二进制或 secret

### Requirement: fake device 复现生产拓扑
自动化测试 SHALL 使用 fake Android service 和 scripted LLM/组件执行与真实示例相同的 AgentGraph 拓扑，覆盖至少两次观察、一次物理动作、一次反馈或循环推进和显式 DONE。测试 MUST 断言调用次序、共享 RuntimeContext、状态隔离和 RunResult。

#### Scenario: deterministic 拍照控制流
- **WHEN** scripted Reasoning 先返回启动/点击动作并最终返回 DONE
- **THEN** fake 运行按预期次数观察和执行，产生成功结果且不需要网络或真实设备

