# executable-mobile-agent Specification

## Purpose
TBD - created by archiving change close-built-in-agentgraph-runtime. Update Purpose after archive.
## Requirements
### Requirement: 统一可执行 Agent 公共入口
系统 SHALL 提供公开的 `compile_agent` 与 `load_agent` 入口，把合法 AgentGraph、成功 CompilationResult 或 graph-native YAML 编译并绑定为 `ExecutableAgent`。该对象 SHALL 暴露其 AgentGraph、canonical hash 和运行方法；编译/加载阶段 MUST NOT 连接设备或开始任务。

#### Scenario: 从 graph-native YAML 加载
- **WHEN** 用户调用 `load_agent` 加载引用受支持内置组件的合法 graph-native YAML
- **THEN** 系统返回持有已验证 AgentGraph 和可执行 plan 的 `ExecutableAgent`，且尚未执行 ADB 或模型调用

#### Scenario: 编译非法图
- **WHEN** 输入图存在端口不兼容、不可达节点或非法循环
- **THEN** 系统在组件实例化、密钥解析和设备连接前返回可定位诊断

### Requirement: Python Builder 直接组合 AgentGraph
系统 SHALL 提供公开的 `AgentGraphBuilder`，允许 Python 用户声明节点、NodeContract/组件绑定、类型化数据边、控制边、Predicate、feedback、Router、Loop 和 Subgraph。Builder 的输出 MUST 是普通 AgentGraph contract 1.1，MUST NOT 要求选择固定 Agent 策略或保存隐藏执行回调。

#### Scenario: SDK 构建 ReAct 风格图
- **WHEN** 用户用 Builder 连接 DeviceObserve、Perception、Reasoning、ActionExecutor 和有界反馈
- **THEN** `.build()` 返回可校验、可 canonicalize 的 AgentGraph，而不是 ModularAgent 或其他策略实例

#### Scenario: SDK 构建多 Reasoning 图
- **WHEN** 用户声明 manager 和 operator 两个 Reasoning 节点以及显式控制关系
- **THEN** Builder 保留两个节点及其逻辑 ID，不把它们压缩进单 reasoning 插槽

### Requirement: YAML 与 SDK 定义等价
graph-native YAML 与 Python Builder SHALL 支持同一 contract、binding、节点、边和控制结构；语义相同且逻辑 ID 相同的定义 MUST 产生相同 canonical hash。source path、声明顺序中的非语义差异、CLI 参数和 presentation 信息 MUST NOT 造成身份差异。

#### Scenario: 等价内置 Agent
- **WHEN** YAML 与 SDK 分别定义同一 screenshot-perception、reasoning、memory 和 action feedback 图
- **THEN** 两个编译结果的 canonical hash 相同

### Requirement: 单次运行配置与 Agent 身份分离
系统 SHALL 使用独立的 `AgentRunConfig` 或等价类型表达 platform、device serial、artifact root、max steps 和 observation 选项，并使用 `TaskInput` 表达本次任务。任务、真实 secret、device serial、run_id 和 artifact root MUST NOT 回写 AgentGraph 或改变 canonical hash。

#### Scenario: 同一 Agent 运行两个任务
- **WHEN** 同一个 ExecutableAgent 先后在不同 run_id 下执行两个 TaskInput
- **THEN** 两次运行共享 AgentGraph hash，但拥有隔离的 RuntimeContext、AgentState、fallback 状态和 artifact namespace

#### Scenario: 更换 Android serial
- **WHEN** 用户只更换 AgentRunConfig 中的 serial
- **THEN** AgentGraph canonical hash 保持不变

### Requirement: 可安装 CLI 支持交互和非交互任务
Python distribution SHALL 安装 `zhixing` console script，并提供 `zhixing run --agent <path>` 子命令。未提供 instruction 时 CLI SHALL 从标准输入读取一个非空任务；提供 `--instruction` 时 SHALL 非交互运行。两种方式 MUST 委托公共 load/compile/run API，而不是复制绑定逻辑或调用旧 AgentFactory。

#### Scenario: 交互输入任务
- **WHEN** 用户运行 graph-native YAML 且未传 `--instruction`
- **THEN** CLI 提示输入任务，并用输入文本启动同一个 ExecutableAgent

#### Scenario: 非交互自动化
- **WHEN** 用户提供 `--instruction "拍一张照片"`、设备 serial 和 artifact root
- **THEN** CLI 运行一次任务、输出终止状态与 manifest/artifact 位置，并以稳定 exit code 表达成功或失败

### Requirement: 可执行结果结构化且可审计
`ExecutableAgent.run()` SHALL 返回 RunResult，并持久化或引用按 run 隔离的 RunEvent、设备观察、动作结果和 manifest。组件失败、模型输出解析失败、设备失败、取消和步数耗尽 MUST 可区分；系统 MUST NOT 仅以日志字符串作为结果。

#### Scenario: Reasoning 输出无法解析
- **WHEN** 内置 Reasoning 在配置的重试后仍无法产生合法 Action
- **THEN** RunResult 与事件包含安全的失败阶段、节点身份和错误类别，且不把任务标为成功

### Requirement: 安装后从仓库外使用
wheel 安装后的公共 SDK、console script、graph-native YAML loader、内置组件资源和 prompt 读取 SHALL 不依赖仓库根目录或当前工作目录。

#### Scenario: 空目录运行
- **WHEN** 用户在仓库外空目录安装 wheel，并通过 SDK 编译 fixture 或调用 CLI 加载绝对路径 YAML
- **THEN** import、组件绑定和包内 prompt 读取成功，运行 artifact 只写入显式配置的位置

### Requirement: 调用者拥有的执行上下文
ExecutableAgent SHALL 提供向后兼容的入口，允许高级编排器传入一个新的、调用者拥有的 `RuntimeContext` 和显式设备会话。该入口 MUST 继续为每次运行重新绑定 run-scoped 组件，并 MUST 使用现有 AndroidGraphRuntime；普通 `run(task, config)` 行为保持不变。

#### Scenario: Benchmark 注入 RuntimeContext
- **WHEN** Benchmark Runtime 为 TaskInstance 创建带 identity、预算、event sink 和 cancellation 的 RuntimeContext
- **THEN** ExecutableAgent 使用该 context 执行 Graph，返回同一 run ID 的 RunResult，且不创建第二个 context

#### Scenario: 普通任务兼容
- **WHEN**现有用户不提供 RuntimeContext 而调用 ExecutableAgent.run
- **THEN**SDK 仍自动创建隔离 context 并保持原有结果合同

### Requirement: 显式共享设备不触发重复发现
调用者提供设备会话时，ExecutableAgent 和 AndroidGraphRuntime MUST 使用该会话，且不得再次枚举 ADB 或创建另一设备连接。设备绑定信息 MUST 保留在运行 provenance 中，不得改变 AgentGraph canonical identity。

#### Scenario: Suite 复用设备
- **WHEN** Benchmark Runtime 在两个任务中传入同一 fake 或真实 Android device
- **THEN**两个 Graph 运行使用同一设备 identity，但保持独立 RuntimeContext 与 artifact namespace

