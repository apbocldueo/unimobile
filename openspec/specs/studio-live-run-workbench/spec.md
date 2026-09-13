# studio-live-run-workbench Specification

## Purpose
定义 Studio 普通 Agent Run 从有效 immutable revision 启动、经 durable journal 实时投影到
三栏工作区，并在 terminal Replay 可用后安全交接的前端合同。
## Requirements
### Requirement: Agent Run 使用稳定路由和持久资源身份
Studio SHALL 通过 `/agents/:agentId/run` 提供普通 Agent Run 工作模式。页面 SHALL 以
URL 中的 agent identity 和可选 run identity 区分 launch/live 状态；accepted Run 的任务、
lifecycle、result 和 evidence MUST 从后端持久资源恢复，不得把它们写入 localStorage 或
仅保存在 React 内存中。

#### Scenario: 打开普通 Run 启动页
- **WHEN** 用户打开存在的 Agent `/agents/:agentId/run` 且 URL 没有 run identity
- **THEN** 页面加载指定或 current immutable revision，并显示普通 task 启动表单

#### Scenario: 刷新正在运行的页面
- **WHEN** 用户刷新带有既有 run identity 的 Agent Run URL
- **THEN** 页面查询同一个 Run、补齐 journal 并继续跟随，不创建或重新执行第二个 Run

#### Scenario: 路由 Agent 与 Run 不一致
- **WHEN** URL agent identity 与查询到的 Run agent identity 不同
- **THEN** 页面显示安全 identity mismatch，不渲染另一 Agent 的 graph 或 artifact

### Requirement: Run 启动必须使用 valid immutable revision
Launch SHALL 只允许选择已经保存且正式 compile status 为 valid 的 immutable revision，
并 SHALL 独立验证当前 Runtime Readiness。客户端 MUST 提交 revision identity、普通 task
text、可选有界 metadata、用户从权威安全目录选择的 device profile identity 和稳定 client
request identity；MUST NOT 提交 Builder draft、BenchmarkTask、raw device serial、secret
或宿主路径。

#### Scenario: 启动有效普通任务
- **WHEN** 用户为 valid、runtime-ready revision 输入非空 task、选择可用安全 Profile 并点击 Run
- **THEN** 客户端以所选 Profile 创建 Run，收到 `202` 后将 URL 绑定到返回的 run identity

#### Scenario: 没有可用 Profile
- **WHEN** exact revision valid 但安全 Device Profile 目录为空
- **THEN** 页面禁用 Run、保留 task 草稿并显示 Settings/服务端配置引导，不发送硬编码 profile identity

#### Scenario: 重试丢失响应的创建请求
- **WHEN** create 请求的响应丢失而用户未修改 task、metadata、agent、revision 或 Profile
- **THEN** 客户端复用原 client request identity 和相同 payload，使后端返回同一 Run

#### Scenario: revision 无效或 canonical identity 不一致
- **WHEN** revision 为 invalid、缺少 graph、或其 canonical hash 与 Run resource 不一致
- **THEN** 页面拒绝启动或停止 graph 投影，显示正式诊断且不按 current revision 猜测

#### Scenario: metadata 包含不安全内容
- **WHEN** metadata 包含 token、password、raw serial、宿主绝对路径或 Benchmark shape
- **THEN** 前后端拒绝创建并使用安全错误 envelope，不在页面日志或 toast 回显原值

### Requirement: Live Run 前端模型和 API 必须严格版本化
前端 SHALL 在 `entities/run` 中定义 versioned Run resource、create response、event page、
event envelope、result 和 lifecycle parser。业务组件 MUST 通过 entity API/query/command
访问 HTTP，MUST NOT 散落直接 `fetch` 或接受 unknown key、非法 lifecycle/result
组合、非有限数值和无界 JSON 为正式事实。

#### Scenario: 解析合法 Run resource
- **WHEN** Stage 3 API 返回 schema 1、稳定 identities、lifecycle、availability 和 high-water mark
- **THEN** entity parser 产生 detached typed resource，并由 TanStack Query 管理服务端缓存

#### Scenario: 响应包含未知或非法字段
- **WHEN** Run/event JSON 包含 unsupported schema、unknown key、未来 cursor 或 terminal without result
- **THEN** parser 返回可观察 contract error，页面不把部分对象当作可信 Run

#### Scenario: 组件需要创建或取消 Run
- **WHEN** launch 或 live controls 执行 command
- **THEN** feature 调用 entity public API/mutation，并以正式 cache update/refetch 反映结果

### Requirement: Live session 必须先补拉 durable journal 再连接 SSE
页面 SHALL 使用 event query 从最后确认 cursor 连续 backfill 到返回的 high-water mark，
随后使用同一 exclusive cursor 连接 SSE。Journal sequence SHALL 是唯一 live projection
cursor；heartbeat、connection timer 和视觉动画 MUST NOT 推进 cursor。

#### Scenario: 初次进入已有 running Run
- **WHEN** Run journal 已有多个 activation 和 observation
- **THEN** 客户端分页读取所有连续 event，原子恢复最新事实后从 next cursor 连接 SSE

#### Scenario: backfill 期间产生新事件
- **WHEN** Runtime 在客户端读取旧 high-water mark 后继续提交事件
- **THEN** 后续 page 或 SSE 按 exclusive cursor 补齐新 sequence，不遗漏也不重新执行组件

#### Scenario: 收到 heartbeat
- **WHEN** SSE 在空闲期发送 comment heartbeat
- **THEN** connection freshness 更新，但 journal cursor、activation count 和 projection 不改变

### Requirement: SSE 断线恢复和重复处理必须可靠
Live session SHALL 维护 confirmed journal cursor、event identity/fingerprint 和明确的
connecting/open/reconnecting/stale/terminal/integrity-error 状态。连接错误时客户端 MUST
关闭旧 EventSource，并使用最新 cursor 有界重连；MUST NOT 同时发送冲突的旧 `after` 和
浏览器内部 `Last-Event-ID`。

#### Scenario: activation 之后断线
- **WHEN** 客户端已确认 sequence 12 后 SSE 断开
- **THEN** 客户端关闭旧连接、从 12 补拉并显式重建 EventSource，projection 不重复 activation

#### Scenario: 收到完全相同的重复事件
- **WHEN** backfill 和 SSE 边界重复交付同 event identity、sequence 和 fingerprint
- **THEN** adapter 幂等忽略重复内容，不增加 execution count 或 history

#### Scenario: 相同 identity 内容冲突
- **WHEN** 两个事件复用 identity 但 fingerprint 或内容不同
- **THEN** session 进入 integrity error、停止接受未验证尾部并保留最后可信 projection

#### Scenario: sequence 出现无法补齐的缺口
- **WHEN** query 不能从 confirmed cursor 返回连续下一 sequence
- **THEN** 页面显示 partial/integrity 状态，不猜测缺失 activation、observation 或 result

### Requirement: Live 与 Replay 必须共用事实投影合同
Live journal adapter SHALL 将事件转换为 `studio-trajectory-projection` 定义的 normalized
moments、observations 和 actions，并使用同一个无网络、React、timer 和 XYFlow 依赖的纯
reducer。系统 MUST 使用同一次 native Run 的 journal 与 Replay envelope 验证 terminal
projection 等价，不得用两套独立状态机解释运行。

#### Scenario: 同一成功 Run 到达终态
- **WHEN** live adapter 消费完整 journal，Replay adapter 消费该 Run 生成的 native Replay
- **THEN** 两者得到相同 activation history、node aggregate、current observation、actions、RunResult 和 terminal cursor

#### Scenario: feedback 与 bounded loop 实时运行
- **WHEN** journal 包含多次 activation、feedback 和 loop exhausted
- **THEN** live projection 保留每次 activation，并使用与 Replay 相同的 count/badge/iteration 语义

#### Scenario: 未执行节点没有正式 skip
- **WHEN** terminal Run 的某 graph node 从未出现 activation 或 skip evidence
- **THEN** live 与 Replay 均显示 not observed，不推断 branch、cancelled 或 skipped reason

### Requirement: Live 工作区必须提供可调三栏布局
Live mode SHALL 使用 AgentGraph、Virtual Phone 和 Run Inspector 三栏，默认比例为
42% / 25% / 33%，并复用 Replay 的 mode-neutral splitter/layout contract。Pane preference
MAY 本地持久化，但 MUST NOT 改变 StudioFlowDocument、revision、Run snapshot、event 或
canonical identity。

#### Scenario: 打开 running Run
- **WHEN** exact revision graph 和 journal 已验证
- **THEN** 左侧显示只读 graph，中间显示因果设备观察，右侧显示当前 activation

#### Scenario: 调整三栏比例
- **WHEN** 用户拖动 splitter 后在 Live 和 Replay 间切换
- **THEN** 工作区恢复同一安全宽度偏好，而两个模式的事实状态保持不变

#### Scenario: graph snapshot 不可验证
- **WHEN** exact revision 缺失、invalid 或 hash 不一致
- **THEN** Graph pane 明确不可用，Phone、Inspector、events 和 Run result 仍可检查

### Requirement: Graph 高亮必须使用稳定 runtime identity
Graph pane SHALL 使用 immutable capability graph identity、compile projection mapping、journal
node path 和 activation ID，把 exact execution facts 投影为 capability aggregate、relation、
Input/Output boundary、loop/feedback state 和执行次数。它 SHALL 分别建模 factual current、
唯一 visual current、累计完成/失败状态和用户锁定选择；同一时刻 MUST NOT 将多个节点呈现为
当前执行。已完成节点 MAY 保留中性的历史标记和次数，但 MUST NOT 使用与当前执行近似的持续
边框、光晕或动画。前端 MUST NOT 根据显示标题、component class name、数组位置、随机
XYFlow ID 或 generated logical-name convention 猜测。Generated runtime/control nodes MUST NOT
作为可编辑或同级 capability card 出现。

#### Scenario: Generated observation activation
- **WHEN** event 引用 mapping 中归属于 Perception evidence path 的 DeviceObserve node
- **THEN** Graph 将唯一当前标记投影到对应 Perception/relation，Virtual Phone 使用 observation，Inspector 可查看 exact generated activation

#### Scenario: 快速进入下一个 capability
- **WHEN** visual current 从 Perception 前进到 Reasoning
- **THEN** Perception 只保留中性历史状态，Reasoning 成为唯一强当前标记，factual cursor、timestamp 和 Runtime 不受视觉呈现影响

#### Scenario: 同一能力多次执行
- **WHEN** feedback 使 Reasoning capability 对应两个 activation
- **THEN** Graph 只在 Reasoning 当前执行时使用强当前标记，并以紧凑次数/轮次保留两次 exact activation 的累计事实

#### Scenario: 用户锁定历史 activation
- **WHEN** 用户在当前 Action Executor 运行时选择旧 Reasoning activation
- **THEN** Graph 以不同于当前标记的锁定样式表示选择，Action Executor 继续作为唯一当前执行位置

#### Scenario: generated activation 失败
- **WHEN** 正式 failure event 到达且 mapping 指向 capability relation 或 graph policy
- **THEN** Graph 以唯一醒目失败位置替代当前标记并提供图外错误入口，不创建 runtime-glue card或删除此前成功历史

#### Scenario: Run 到达 terminal Output
- **WHEN** authoritative terminal activation 可通过正式 mapping 归属 Output boundary
- **THEN** Output 成为最终唯一位置，Graph 节点和连线不增加 `DONE`、`FAIL` 或其他终态结果文字

#### Scenario: 嵌套 Subgraph activation
- **WHEN** event 包含 hierarchical node path、parent activation 和 loop identity
- **THEN** Graph 使用正式 identity/mapping 定位对应 logical owner，并保留可展开的层级/iteration 信息，不把 generated glue 猜成新 capability

#### Scenario: 同一节点多次执行
- **WHEN** feedback 使 Reasoning node 产生两个 activation
- **THEN** Graph 只保留一个当前执行标记，同时显示累计次数，Inspector 可分别选择两个 exact activation

#### Scenario: activation 失败
- **WHEN** 正式 failure event 到达
- **THEN** 失败位置和 activation 立即以非颜色唯一语义标记，并提供定位入口且不删除此前成功历史

### Requirement: 事实跟随、视觉高亮和用户锁定必须分离
Live mode SHALL 立即投影 factual current activation，同时以按 interaction 排序的运行故事
持续保留已经出现的用户可理解步骤。视觉高亮或阅读节奏 MAY 延长呈现，但 MUST NOT 延迟
reducer、修改 timestamp/duration/cursor、阻塞 Runtime，或使 Inspector 把视觉状态当作执行
事实。用户选择历史故事步骤、node 或 activation 后 SHALL 锁定详情，同时 Graph、Phone、
journal 和过程故事继续更新，并 SHALL 提供“回到当前”。

#### Scenario: 极快 activation 完成
- **WHEN** start 与 complete 的实际间隔短于用户能够阅读的时间
- **THEN** factual projection 立即完成，已形成的组件故事步骤继续保留，并以真实 status、duration 和 cursor 呈现

#### Scenario: 锁定旧 activation 后出现新节点
- **WHEN** 用户查看旧 Reasoning activation 且 Runtime 进入 ActionExecutor
- **THEN** Graph、Phone 和过程故事继续接收新事实，组件详情保持锁定并明确提示当前运行仍在继续

#### Scenario: 锁定时发生 failure
- **WHEN** 新 activation failure 到达而 Inspector 已锁定
- **THEN** 页面醒目提示事实 failure 和跳转入口，但不无条件覆盖用户选择或删除此前故事

#### Scenario: 回到当前
- **WHEN** 用户在锁定历史步骤后点击“回到当前”
- **THEN** Inspector 解除锁定并聚焦最新 factual story step，而不修改 journal cursor 或 Runtime

#### Scenario: 断线补拉大量事件
- **WHEN** reconnect backfill 包含多个已完成的快速 activation
- **THEN** 页面从可信前缀确定性重建有界运行故事并定位最新事实，不逐条播放积压动画或制造实时错觉

### Requirement: Virtual Phone 必须只显示因果可见的 live evidence
Virtual Phone SHALL 只读显示已经提交的 observation screenshot、尺寸、observation/
interaction identity、安全 device provenance、最近 Action 和正式 overlay。Live artifact
读取 SHALL 使用 run-scoped opaque identity；新 observation 缺图或读取失败时 MUST 清除
当前画面或明确标记历史/缺失/损坏，不能把上一张冒充当前。共享 Live/Replay journal
projection MUST 按正式 DeviceObserve activation 识别同一 Run 的首张和后续 observation，
不得依赖 Runtime 注入的 input observation 或按截图 artifact 的出现位置猜测来源。

#### Scenario: DeviceObserve complete 到达
- **WHEN** event 引用已登记的 screenshot 和 UI tree artifact
- **THEN** Phone 加载 live artifact URL，并显示对应 observation 与 interaction identity

#### Scenario: Action 后等待新 observation
- **WHEN** Action complete 已到达而下一次 DeviceObserve 尚未完成
- **THEN** Phone 显示最新 Action，旧 screenshot 明确标记为 historical/stale

#### Scenario: screenshot 读取失败
- **WHEN** artifact endpoint 返回 missing、corrupt 或 ownership error
- **THEN** Phone 不保留其为当前画面，展示安全 availability/error 且不尝试其他 Run artifact

#### Scenario: 用户点击 Phone
- **WHEN** 第一版用户在 screenshot 上点击或拖动
- **THEN** 页面不向设备发送命令，也不绕过 ObservationProvider/ActionExecutor

#### Scenario: feedback 产生后续 observation
- **WHEN** 同一 Run 的非终止动作通过 bounded feedback 触发新的 DeviceObserve complete
- **THEN** Live 与 Replay 都将新截图投影为更晚的 causal phone frame，保留此前 observation/action identity，并且不把旧帧继续标为当前

#### Scenario: 首次观察前运行失败
- **WHEN** Run 在任何 DeviceObserve complete 之前因 binding、readiness 或组件错误结束
- **THEN** Phone 显示尚未采集设备证据的事实状态，不复用其他 Run、旧 revision 或兼容输入中的截图

### Requirement: Live Inspector 必须分离定义、activation 和证据
Inspector SHALL 默认以“过程”视图按 interaction 展示组件级因果故事，优先呈现任务相关的
观察、判断、动作与结果。每个故事步骤 SHALL 从共享 projection、typed Debug Payload、
Observation、Action、artifact reference 和正式 capability projection mapping 派生；已经显示的
步骤 SHALL 在后续事实到达后继续可见。Inspector SHALL 提供按需“组件详情”，明确区分该次
activation 的输入与输出；Runtime Identity、Definition、完整模型响应、raw Debug Payload、
evidence inventory、ID、hash 和 node path SHALL 作为默认折叠的“技术详情”继续可访问。
Inspector MUST NOT dump 任意运行对象、显示完整 Prompt，或按未知组件类名猜测字段。

#### Scenario: Perception activation 完成
- **WHEN** Perception 有正式 observation、safe input summary、output summary 和可选 screenshot reference
- **THEN** 过程视图说明该组件观察了什么，组件详情分别呈现输入 Observation/截图与输出识别结果，并且不伪造缺失元素或检测框

#### Scenario: Reasoning activation 完成
- **WHEN** Reasoning evidence 包含 task、上下文摘要、决策、Action 和可用模型响应 reference
- **THEN** 过程视图显示人类可读决策，组件详情区分输入上下文和输出动作，完整模型响应仅在技术详情中按正式 reference 懒加载

#### Scenario: Memory 与 Action Executor 完成
- **WHEN** Memory 和 Action Executor 产生正式 Debug Payload 或 ActionResult
- **THEN** Memory 优先显示本次 read/write 变化，Action Executor 优先显示动作、参数、结果、effect、状态与错误，而不是 ID 或 contract hash

#### Scenario: generated runtime activation 到达
- **WHEN** DeviceObserve、ActionRequest、Router、feedback 或 terminal glue 可通过正式 mapping 归属 capability 或 relation
- **THEN** 默认过程聚合其用户意义到 owner capability 或“进入下一轮/运行完成”，且技术详情仍可访问 exact generated activation

#### Scenario: generated runtime activation 无法正式归属
- **WHEN** exact activation 没有可信 projection mapping
- **THEN** Inspector 不按名称猜测归属，在技术详情中标为未映射运行事实并保持默认故事真实

#### Scenario: Prompt 已捕获
- **WHEN** Debug Payload 将 Prompt 标记 hidden
- **THEN** Inspector 只显示 hidden availability，普通浏览器路径不读取、预取或导出 Prompt 内容

#### Scenario: 外部组件只有通用合同
- **WHEN** activation role 没有内置专用 presenter
- **THEN** Inspector 使用 NodeContract、safe typed input/output summaries、duration、status、error 和 artifact references 的通用视图

#### Scenario: 用户打开技术详情
- **WHEN** 用户主动展开某一步的技术详情
- **THEN** 页面显示与该 exact activation 对应的 runtime identity、definition、availability 和审计入口，不混入其他 activation 的 payload

### Requirement: Live Run 只提供真实协作式取消
对于 accepted、starting、running 或 cancelling Run，页面 SHALL 提供调用 Stage 3 幂等
cancel command 的控制，并显示 cancellation requested/cancelling/terminal 的真实状态。
UI MUST NOT 声称强制中断活动模型、设备或 Python 调用，也不得显示无后端合同的 Pause、
checkpoint 或 node retry 控制。

#### Scenario: 取消 running Run
- **WHEN** 用户确认 Cancel
- **THEN** 页面发送一次正式 cancel command、显示协作式取消提示并继续跟随直到 terminal

#### Scenario: 重复点击或刷新后再次取消
- **WHEN** cancellation 已持久化
- **THEN**幂等 command 返回同一 Run，页面不生成第二个 terminal event 或假结果

#### Scenario: active call 尚未返回
- **WHEN** Run lifecycle 为 cancelling 但模型或设备调用仍在进行
- **THEN** 页面保持 cancelling，不显示已停止或允许启动危险的组件级 retry

### Requirement: Terminal Run 必须保留完成态并由用户打开 Replay
收到 `run.terminal` 后，Live session SHALL 关闭 SSE、重新读取持久 Run resource，并保留
terminal Graph、Phone 和完整运行故事。页面 MUST NOT 因 Replay 可用而自动离开 Live 页面。
当 lifecycle、RunResult 与同 identity native Replay 均权威可用时，页面 SHALL 显示明确的
“打开完整回放”操作；只有用户触发后才进入 `/runs/:runId/replay`。Replay missing、corrupt
或 finalization failure SHALL 留在可检查的 Live 完成态并提供重新检查，不得构造假 Replay。

#### Scenario: 成功 Run 完成并发布 Replay
- **WHEN** terminal event 与 GET Run 均确认 native Replay available
- **THEN** 页面保留最后运行故事和成功结论，并显示由用户触发的同 identity Replay 入口

#### Scenario: 用户打开完整回放
- **WHEN** 用户在 authoritative Replay available 后点击“打开完整回放”
- **THEN** 页面导航到同 run identity Replay，已持久 evidence、result 和 causal order 保持不变

#### Scenario: failure 或 cancelled Run 发布 Replay
- **WHEN** 非成功 Run 终止且 native Replay available
- **THEN** 页面先保留正式 failure/cancelled 完成态与可信 journal 前缀，并允许用户主动打开 Replay

#### Scenario: Replay finalization 尚未完成或失败
- **WHEN** terminal Run 的 replay availability 不是 available
- **THEN** 页面显示真实 availability、保留 terminal 故事并允许重新检查，不禁用技术审计或循环导航

### Requirement: Live 工作区必须有明确页面状态和安全日志边界
页面 SHALL 明确呈现 loading、launch validation、accepted、starting、running、
cancelling、reconnecting、stale、terminal、not found、contract error、integrity error、
artifact error 和 retry 状态，并支持现有深浅主题。前端日志、toast、query key 和
localStorage MUST NOT 包含完整 Prompt、模型响应、task evidence、raw serial、secret、
宿主路径或未经清理的 event payload。

#### Scenario: Studio backend 不可达
- **WHEN** Run query 或 SSE 无法连接本地服务
- **THEN** 页面保留 run identity 和最后可信 projection，显示重试状态且不回退到 mock success

#### Scenario: 切换深浅主题
- **WHEN** 用户在 live activation 锁定期间切换主题
- **THEN** 三栏视觉更新，run cursor、selection、projection 和 canonical hash 保持不变

#### Scenario: 检查浏览器持久化
- **WHEN** Run 已显示完整响应、screenshot 和 Debug Payload
- **THEN** localStorage/session logs 不包含这些 evidence 内容，仅后端受控存储保存正式证据

### Requirement: Launch 必须使用三栏工作台而非独立全页表单
普通 Agent launch 状态 SHALL 读取 exact valid immutable revision，并使用与 Live/Replay 一致的三栏工作台骨架展示只读 AgentGraph、明确的设备未启动状态和运行准备摘要。Task 输入和提交控制 SHALL 位于工作台最底部；页面 MUST NOT 在 Builder 与 Live Run 之间插入占据主内容区的独立 launch card。

#### Scenario: valid revision 等待 task
- **WHEN** `/agents/:agentId/run` 绑定 valid revision 且尚无 run identity
- **THEN** 页面在三栏 launch 工作台底部显示 Task Run Bar，Graph 可读，Phone 明确尚未启动，右侧显示 revision readiness

#### Scenario: revision 无效或身份不匹配
- **WHEN** launch revision invalid、缺失、属于另一 Agent 或 canonical identity 无法验证
- **THEN** 工作台拒绝创建 Run并显示正式诊断，不用 current revision 或 Builder draft 替代 exact target

### Requirement: Live 顶部必须只承担 Agent 名称识别
普通 Live 工作台顶部 SHALL 使用可用的 Studio Agent metadata 显示一个人类可读 Agent 名称，并保持紧凑；它 MUST NOT 重复展示 run ID、计数、lifecycle 卡片、connection 卡片、failure summary 或 evidence card。运行状态、失败、计数和 evidence SHALL 在右侧 Run Overview/Inspector、Graph 或底部运行 dock 保持首屏可访问，技术 identity SHALL 保留为主动展开的详情。

#### Scenario: Agent metadata 可用
- **WHEN** Studio 能读取 Run 所属 Agent 的当前安全 metadata
- **THEN** 顶部只显示其人类可读名称，名称不参与 revision、Run 或 canonical identity

#### Scenario: Agent 名称不可用
- **WHEN** Agent 已删除、metadata 查询失败或 Replay 来源不提供本地 Agent resource
- **THEN** 顶部显示明确的不可用名称或安全缩短的 agent identity，页面其他 Run 事实仍可检查

#### Scenario: Live Run 失败
- **WHEN** 正式 activation failure 到达
- **THEN** Graph 和右侧 Run Overview 显示失败位置与安全原因，底部显示运行状态，而顶部仍只承担 Agent 名称识别

### Requirement: Run Workspace 必须呈现事实性的准备与设备证据状态
Launch、Live 和 terminal Replay 的中间设备栏 SHALL 使用稳定状态区分 not-started、
runtime-not-configured、preparing-agent、waiting-for-device、waiting-for-first-observation、
screenshot-available、early-binding-failure、device-offline、device-unauthorized、
artifact-missing 和 artifact-corrupt。Phone shell MAY 保持稳定以维护空间连续性，但状态
标签 MUST 来自 readiness/lifecycle/result/evidence 事实，不能由缺图推断设备离线。

#### Scenario: 尚未提交 Task
- **WHEN** valid launch workspace 尚未创建 Run
- **THEN** Phone 显示“运行后将在这里显示设备截图”或对应 readiness block，不显示 `OFFLINE`

#### Scenario: Agent binding 早期失败
- **WHEN** accepted Run 在连接设备之前发生结构化 binding failure 且没有 screenshot artifact
- **THEN** Phone 显示“Agent 尚未连接设备/未采集截图”，右侧显示 binding failure，不把状态标为 device offline

#### Scenario: 后端确认设备离线
- **WHEN** execution result/evidence 包含权威 device-offline code
- **THEN** Phone 可以显示 `OFFLINE`，并且该标签与未配置、未启动和未采集截图可区分

#### Scenario: 已有截图证据
- **WHEN** 当前 causal observation 引用完整且可读取的 screenshot artifact
- **THEN** Phone 显示截图、observation/interaction identity 和最近动作，覆盖层不伪造实时视频

### Requirement: Live Graph 必须默认呈现纵向运行执行图
对于具有可信 capability document 与 projection mapping 的 Live Run，Graph pane SHALL 使用
独立于 Builder saved coordinates 的稳定 vertical-first 执行布局。默认“运行路径” SHALL
保留 Input、Output 与 capability cards，突出唯一当前 capability 和可信已发生路径；它 MAY
降低或省略不帮助定位当前执行的静态 data relations，并 SHALL 将 feedback/iteration 表达为
紧凑轮次提示而不是支配画布的长回环。用户 SHALL 能切换到“关系全图”检查完整 capability
topology 和 relation kinds。两种视图 MUST 使用同一 immutable snapshot，不得修改 Builder
presentation、AgentGraph、canonical identity、trajectory 或 evidence。

#### Scenario: 打开 capability-authored running Run
- **WHEN** snapshot 包含 schema-3 capability document、完整 projection mapping 和横向 Builder presentation
- **THEN** Live Graph 使用稳定纵向执行布局并保持节点标签，且不改写或复用 Builder 坐标作为运行布局

#### Scenario: 默认运行路径包含上下文依赖
- **WHEN** Memory、Perception 与 Input 的多个 data relations 汇入 Reasoning
- **THEN** 默认视图只强调当前可信执行走廊，并以安静边线或节点依赖摘要表达其余关系，不让交叉线遮挡节点和当前标记

#### Scenario: feedback 进入下一轮
- **WHEN** Action Executor 的正式 feedback relation 开始新的 interaction
- **THEN** Graph 显示当前轮次与唯一当前 capability，不持续动画整条回环线或把 generated router 显示为组件

#### Scenario: 用户检查关系全图
- **WHEN** 用户切换到“关系全图”
- **THEN** 页面显示 snapshot 中全部 capability relations 及可区分的 relation kinds，并保留返回“运行路径”的动作和当前位置

#### Scenario: capability mapping 不可验证
- **WHEN** snapshot 缺少可信 capability mapping 或完整性失败
- **THEN** Graph 显示明确 unavailable/compatible generic 状态，不通过名称猜测纵向执行路径或隐藏可能改变含义的 exact topology

