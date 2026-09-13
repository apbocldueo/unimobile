# android-graph-runtime Specification

## Purpose
TBD - created by archiving change implement-android-graph-runtime. Update Purpose after archive.
## Requirements
### Requirement: 显式目标设备的 Android 图运行入口
系统 SHALL 提供接收已绑定 AgentGraph、TaskInput、RuntimeContext 或其构造参数、Android device serial 和 artifact root 的 Android 图运行入口。该入口 MUST 校验设备可达性、注入 Android runtime services 并委托通用 GraphExecutionKernel，MUST NOT 根据 Agent 范式创建固定观察—决策—动作循环。

#### Scenario: 指定在线 emulator
- **WHEN** 调用方以 `emulator-5554` 和合法 Bound AgentGraph 启动运行且该设备状态为 `device`
- **THEN** 系统只为该 serial 创建 Android 会话并由通用 Kernel 执行图

#### Scenario: 指定设备不可用
- **WHEN** 指定 serial 不存在、离线或未授权
- **THEN** 系统在启动 Agent 节点前返回结构化 DEVICE_FAILURE 且不回退到其他设备

#### Scenario: 多设备但未指定 serial
- **WHEN** 环境存在多个可用 Android 设备且调用方未指定 serial
- **THEN** 系统拒绝猜测目标并返回包含候选设备安全标识的配置错误

### Requirement: Android observation service 产生可携带的设备观察
Android DeviceObserve service SHALL 从绑定设备采集截图、屏幕尺寸和按请求启用的 UI XML，并返回不包含 live device handle 的 DeviceObservation。成功结果引用的每个 artifact MUST 已实际写入本次 run 的 artifact store。

#### Scenario: 采集截图与 UI XML
- **WHEN** 图激活 DeviceObserve 节点并请求 screenshot 与 UI tree
- **THEN** service 返回同一 observation sequence 的图像和 XML artifact 引用、设备 serial、platform、尺寸及采集时间

#### Scenario: 截图命令失败
- **WHEN** ADB 截图命令非零退出、超时或产生空文件
- **THEN** service 返回结构化设备失败且后续依赖该 observation 的节点不执行

#### Scenario: 只请求截图
- **WHEN** observation request 明确关闭 UI tree
- **THEN** service 不执行 UI dump，并返回 UI artifact 为空的合法 DeviceObservation

### Requirement: Android action service 是唯一设备副作用边界
Android ActionExecutor service SHALL 校验类型化 ActionExecutionInput，并只通过绑定的 AndroidDevice 执行支持的动作。Runtime facade 和 GraphExecutionKernel MUST NOT 按 action type 直接调用设备 API。

#### Scenario: 执行点击并确认副作用
- **WHEN** ActionExecutor 收到坐标合法的 TAP 且底层命令成功
- **THEN** 返回成功 ActionResult，标记已产生物理设备副作用并记录安全设备元数据

#### Scenario: 非法动作参数
- **WHEN** TAP 坐标越界、SWIPE 参数不完整或 action type 不受支持
- **THEN** service 在执行设备命令前返回失败 ActionResult 且标记未产生物理副作用

#### Scenario: 终止动作
- **WHEN** ActionExecutor 收到 DONE 或 FAIL
- **THEN** service 返回对应终止语义且不调用 AndroidDevice、不标记物理副作用

#### Scenario: 底层命令失败
- **WHEN** AndroidDevice 动作命令非零退出、超时或报告设备断开
- **THEN** ActionResult 为失败、包含安全诊断并且不得报告动作成功

### Requirement: Android 命令失败可观察且参数安全
AndroidDevice 用于图运行的关键命令 SHALL 检查 exit code、timeout、stderr 和必要输出。用户或配置提供的 serial、应用标识、文本和路径 MUST 经过结构化参数传递或明确验证，MUST NOT 作为未验证字符串直接拼接到 shell 命令。

#### Scenario: ADB 非零退出
- **WHEN** ADB 返回非零 exit code
- **THEN** 调用方获得包含操作类别和安全 stderr 摘要的设备异常

#### Scenario: 命令超时
- **WHEN** screenshot、UI dump 或 action 超过配置的有限 timeout
- **THEN** 系统终止该命令、返回 timeout 诊断并停止依赖节点

#### Scenario: 恶意应用标识
- **WHEN** 应用标识包含不符合允许格式的 shell 控制字符
- **THEN** 系统在启动命令前拒绝该参数

### Requirement: Android run artifacts 按运行和交互隔离
每次 Android 图运行 SHALL 使用独立 run artifact namespace，并按 interaction 与 observation/action sequence 分配稳定引用。系统 MUST NOT 依赖调用方当前工作目录决定 artifact 位置，也 MUST NOT 在事件中嵌入截图二进制或 live device object。

#### Scenario: 从任意目录启动
- **WHEN** 安装后的调用方从空项目目录传入 artifact root 并启动运行
- **THEN** 所有观察与动作证据写入该 root 下的 run namespace，路径不依赖 `os.getcwd()`

#### Scenario: 连续两次运行
- **WHEN** 同一设备连续执行两个 run
- **THEN** 两次运行具有不同 namespace，且 observation/action sequence 各自从稳定初值开始

#### Scenario: artifact 写入失败
- **WHEN** 目标目录不可写或写入后文件校验失败
- **THEN** 运行返回可定位错误且结果中不产生指向不存在文件的成功引用

### Requirement: 真实 Android smoke test 形成可审计证据
系统 SHALL 提供无需外部模型密钥的确定性 Android AgentGraph smoke test。该测试 MUST 在显式指定的在线设备上完成至少一次观察、一次安全可恢复的真实动作、一次动作后观察和显式终止，并保存 RunResult、RunEvent 与 observation artifacts。

#### Scenario: emulator smoke test 成功
- **WHEN** `emulator-5554` 在线且测试图完成预检、观察、安全动作、重观察和 DONE
- **THEN** 测试证据显示同一 run_id、正确节点顺序、至少一个已确认物理副作用及成功 Agent outcome

#### Scenario: 真实设备不可用
- **WHEN** smoke test 启动时目标设备不可达
- **THEN** 测试明确报告 skip 或 DEVICE_FAILURE，且项目不得把 fake 测试结果作为真实 Android 里程碑完成证据

#### Scenario: smoke 动作中途失败
- **WHEN** 真实动作或动作后观察失败
- **THEN** 运行保存截至失败点的事件和 artifacts，并返回 DEVICE_FAILURE 而不是成功

### Requirement: 旧 Android Runner 保持兼容
新增 Android Graph Runtime SHALL 与旧 AgentRunner、ModularAgent 和 AgentFactory 入口并存。现有 AgentConfig YAML 和 BenchmarkTask JSON MUST NOT 因使用新入口而被删除或合并。

#### Scenario: 旧 Runner 回归
- **WHEN** 调用方按原入口构造 ModularAgent 并通过 AgentRunner 操作 fake 或真实设备
- **THEN** 既有公共调用方式仍可运行且不要求调用方先构造 AgentGraph 1.1

#### Scenario: 新旧入口选择
- **WHEN** 调用方提供 Bound AgentGraph 1.1
- **THEN** Android Graph Runtime 使用新 service-injection 路径，且不会先包装为旧策略 Agent

### Requirement: ExecutableAgent 委托真实 Android Runtime
当 AgentRunConfig 指定 Android 时，`ExecutableAgent.run()` SHALL 为本次 run 选择显式设备、创建 RuntimeContext 和 artifact store、注入 DeviceObserve/ActionExecutor services，并把已绑定 contract 1.1 plan 交给 AndroidGraphRuntime。该门面 MUST NOT改变图拓扑或自行执行设备动作。

#### Scenario: SDK 运行在线 emulator
- **WHEN** SDK 构建并编译的 Agent 在 `emulator-5554` 上执行 TaskInput
- **THEN** 系统使用该 AgentGraph hash 和该 serial 启动 AndroidGraphRuntime，并返回同一 run_id 下的结构化结果

#### Scenario: YAML 与 SDK 使用同一设备入口
- **WHEN** canonical hash 相同的 YAML 与 SDK Agent 使用相同 RunConfig 分别运行
- **THEN** 两者经过同一 Android runtime facade 和 service contracts，而不是按 authoring surface 选择不同 Runner

### Requirement: 真实 Mobile Agent 多步闭环
真实 Android 运行 SHALL 支持内置组件产生的动态 Action，而不是只支持 smoke test 的 FixedAction。每次非终止物理动作完成后，后续观察是否发生及进入哪个组件 MUST 由 AgentGraph 的控制流决定；DONE/FAIL SHALL 通过类型化 ActionResult 终止。

#### Scenario: 动态点击相机快门
- **WHEN** Reasoning 根据当前截图产生合法 TAP 且图把动作连接到 ActionExecutor
- **THEN** Android Action service 执行该动态动作、记录已确认 effect，并按图进入后续观察

#### Scenario: 模型产生非法坐标
- **WHEN** Reasoning 产生超出屏幕边界的 TAP
- **THEN** ActionExecutor 在设备调用前拒绝动作，RunResult 不声称产生物理副作用

### Requirement: 拍照任务使用独立设备证据验收
项目 SHALL 提供一条显式真实 Android acceptance，使用内置组件 AgentGraph 执行“拍一张照片”。验收 MUST 在运行前后采集配置化的媒体状态，并且只有检测到属于本次运行的新照片时才报告设备任务成功；Agent 的 DONE 文本或 Kernel 成功本身不足以证明拍照成功。

#### Scenario: 新照片产生
- **WHEN** 在线 Android 设备完成 AgentGraph 运行且运行后媒体状态比运行前增加一张符合条件的照片
- **THEN** acceptance 记录 AgentGraph hash、RunResult、事件、artifacts 和媒体差分，并判定闭环通过

#### Scenario: Agent 返回 DONE 但无照片
- **WHEN** Agent 明确 DONE 但媒体状态没有新增照片
- **THEN** 框架运行结果可保留 Agent SUCCESS，外部 acceptance/evaluation 判定任务未通过并保存证据

#### Scenario: 无在线设备或模型凭据
- **WHEN** acceptance 环境缺少指定设备或模型配置
- **THEN** 测试明确 skip 或报告前置条件失败，不得用 fake 结果替代真实 Android 证据

### Requirement: 真实失败保留截至失败点的轨迹
设备断开、截图失败、模型失败、Action 解析失败或媒体断言失败时，系统 SHALL 保留已经产生的 RunEvent、observation/action artifacts 和安全错误信息，便于人工定位失败层。系统 MUST NOT 宣传或输出未经实现验证的自动失败诊断结论。

#### Scenario: 第二次观察失败
- **WHEN** 物理动作成功后设备在 post-action observation 期间断开
- **THEN** 结果为 DEVICE_FAILURE，并保留动作前观察、已确认动作和失败节点事件

### Requirement: Android Runtime 不得代替 AgentGraph 声明 observation
Android Runtime SHALL 只向已绑定 DeviceObserve 与 ActionExecutor service contract 注入设备实现，并把调用方提供的边界输入原样交给通用 Kernel。它 MUST NOT 因 input 节点暴露 `observation` port、下游组件等待 observation 或图来自 Studio 而主动截图、补写边界输入、增加 interaction 或改变控制流。

#### Scenario: 显式 DeviceObserve 采集首帧
- **WHEN** 图声明可达的 DeviceObserve 节点并由控制流激活它
- **THEN** Android Runtime 通过该 service activation 采集一次首帧并记录正式节点事件和 artifact，不在 Kernel 启动前额外采集

#### Scenario: 旧线性图缺少显式观察节点
- **WHEN** 图仅从 input 的 `observation` port 连接 Perception，而调用方没有提供 observation
- **THEN** Android Runtime 不访问设备补齐该值，依赖节点不以伪造输入执行，结果保留结构化图执行失败或调用方在 Run 前得到 topology-readiness 阻断

#### Scenario: 多轮观察由 feedback 控制
- **WHEN** 非终止 ActionResult 触发图声明的 bounded feedback 并重新到达 DeviceObserve
- **THEN** 每次后续截图对应一个新的图 activation 与 interaction evidence，Android Runtime 不在 feedback 之外增加隐藏观察

#### Scenario: 旧 Runner 兼容路径仍然独立
- **WHEN** 调用者使用既有 ModularAgent 或 AgentRunner 而不是 Bound AgentGraph Android Runtime
- **THEN** 本要求不移除该旧公共入口，也不把其内部循环伪装成 AgentGraph 节点事件

