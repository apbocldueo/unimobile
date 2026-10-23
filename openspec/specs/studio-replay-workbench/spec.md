# studio-replay-workbench Specification

## Purpose
TBD - created by archiving change implement-studio-trajectory-replay-2. Update Purpose after archive.
## Requirements
### Requirement: History 使用真实 Replay 索引
`/history` SHALL 从 Replay repository 分页加载真实记录，并展示 run/Agent identity、
Agent status、可选 Benchmark outcome、时间、provenance、evidence completeness 和
Replay 入口。页面 MUST NOT 使用 hard-coded mock rows、假导出或通过浏览器扫描 `temp/`。

#### Scenario: History 有已导入运行
- **WHEN** repository 包含可读取和部分证据两种 Replay
- **THEN** History 按稳定顺序展示各自状态和完整度，并允许进入对应
  `/runs/:runId/replay`

#### Scenario: History 为空
- **WHEN** repository 没有已导入 Replay
- **THEN** 页面展示真实空态和本地导入指引，不生成示例成功记录冒充用户运行

#### Scenario: History 请求失败
- **WHEN** 列表 API 返回安全错误
- **THEN** 页面保留筛选/导航状态，展示重试入口且不回退到 mock 数据

### Requirement: Replay 路由提供只读三栏工作台
`/runs/:runId/replay` SHALL 加载一个持久 Replay resource，并以 AgentGraph、Virtual
Phone 和 contextual Inspector 呈现。默认工作区 MUST 优先分配可读空间给 AgentGraph，
其次为当前设备证据，最后为 Inspector：存在 causally visible screenshot 时默认目标
比例为 50% / 30% / 20%；没有当前可读截图时，页面 MUST 压缩 Virtual Phone 空态并将
释放空间分配给 Graph 和 run overview。用户 SHALL 能拖动可见分栏，宽度偏好 MUST NOT
写入 AgentGraph、revision 或 canonical identity。正在查看 Replay 时，History module 的
完整二级导航 MUST 默认收起为可访问的紧凑入口，以免与三栏工作区争夺主视图宽度。

#### Scenario: 打开有效 Replay URL
- **WHEN** 用户访问一个存在的 run identity
- **THEN** 页面加载 envelope、图、当前 evidence 和时间轴，明确标记 Replay 为只读，
  并在首屏提供 run overview 而不是未选择节点的 Inspector 字段 dump

#### Scenario: 当前截图不可用
- **WHEN** 当前 cursor 没有 causally visible、完整性可读的 screenshot
- **THEN** Virtual Phone 使用紧凑且明确的 unavailable state，不用固定空设备占据主要
  工作区空间，Graph 和 run overview 获得相应可读空间

#### Scenario: 调整面板宽度
- **WHEN** 用户拖动两个 splitter 后刷新页面
- **THEN** 用户偏好恢复，运行 snapshot、graph hash 和 Replay evidence 不发生变化

#### Scenario: Run 不存在或已损坏
- **WHEN** route identity 不存在或 envelope 无法通过 schema/integrity 校验
- **THEN** 页面展示区分 not found 与 corrupt 的安全错误，不渲染其他 Run 的缓存内容

### Requirement: Replay Graph 使用稳定身份和确定性布局
Graph pane SHALL 使用 RunSnapshot AgentGraph identity、可用的 immutable capability document
和 compile projection mapping，按当前 Replay cursor 的 node path/activation identity 投影只读
能力状态。对于可信 capability revision，Replay SHALL 使用与 Live 相同、独立于 Builder saved
coordinates 的 deterministic vertical-first 执行布局；Builder presentation 只提供安全标签等
非位置提示，不决定 Replay 坐标。默认“运行路径” SHALL 突出当前 cursor 唯一位置、已发生
能力和可信关系子集，并降低不帮助理解当前执行的静态关系；“关系全图” SHALL 按需呈现完整
immutable capability topology。factual current、visual current、累计状态和用户锁定 MUST 分离，
已完成节点不得与当前节点使用近似的持续高亮。Replay focus、布局和关系披露 MUST NOT 改写
canonical graph、Builder revision、trajectory 或 evidence，也 MUST NOT 推断 execution fact。
节点、ports、edges、edge labels、badges 和 canvas accessibility names MUST NOT 显示 `DONE`、
`FAIL` 或其他终态结果词汇。

#### Scenario: Replay capability revision
- **WHEN** RunSnapshot 包含 capability document、projection mapping 和横向 Builder presentation
- **THEN** Graph pane 使用 Input/Output 与 capability cards 的稳定纵向执行布局，通过 mapping 高亮当前唯一位置，不连接 Builder edit store或显示 generated glue cards

#### Scenario: Replay Studio revision
- **WHEN** RunSnapshot 包含 graph body 和 legacy Studio presentation，但没有可信 schema-3 capability mapping
- **THEN** Graph pane 使用只读 compatibility projection 与稳定 identity 保留可验证拓扑，不连接 Builder edit store，也不把 capability 纵向隐藏规则套到无法验证的 graph 上

#### Scenario: cursor 前进到下一 capability
- **WHEN** Replay cursor 从 Perception activation 前进到 Reasoning activation
- **THEN** Reasoning 成为唯一强当前标记，Perception 仅保留中性已发生状态，用户锁定选择保持独立

#### Scenario: cursor 后退
- **WHEN** 用户把 Replay cursor 移到更早 interaction
- **THEN** 运行路径只显示截至该 cursor 可验证的节点/关系状态和唯一当前位置，不泄露未来完成、失败或 Output 状态

#### Scenario: Replay legacy Studio revision
- **WHEN** 历史 snapshot 使用已知旧 schema-2 glue-heavy graph
- **THEN** Replay 使用只读 compatibility projection保留能力与 Input/Output，exact旧 graph/evidence 可在图外审计且不被改写

#### Scenario: Replay YAML 来源
- **WHEN** graph body 有效但没有 Studio capability mapping
- **THEN** Graph pane 使用可复现 generic layout或明确 mapping unavailable，刷新后结果稳定且不通过 capability 规则省略 exact topology

#### Scenario: 聚焦失败路径
- **WHEN** projection 有正式 failure target 且用户选择聚焦该路径
- **THEN** Graph 以唯一醒目失败位置定位映射能力、淡化不相关能力并保留完整关系/evidence 入口，没有正式 target 的能力不得被标为失败

#### Scenario: 检查关系全图
- **WHEN** 用户从默认运行路径切换到“关系全图”
- **THEN** 页面显示 snapshot 中完整 capability relations、relation kinds 和当前 cursor 状态，并可无损返回默认执行视图

#### Scenario: Graph snapshot 缺失
- **WHEN** evidence availability 表明 graph body 未采集
- **THEN** Graph pane 显示明确不可用状态，run overview、时间轴、状态和 artifact 仍可检查，不绘制猜测图

### Requirement: 双轨时间轴和 activation 级播放控制
Replay SHALL 提供播放/暂停、上一 activation、下一 activation、0.5×/1×/2×和跳转失败。
正常导航 SHALL 优先显示 activation start/terminal、observation、action、feedback、
loop/router control、failure 和可用 Benchmark phase 等语义 milestones，而不是把每一个
低层 causal moment 作为同等视觉元素。用户 MUST 能按需进入 exact causal-moment detail；
存在 Benchmark context 时才显示独立 Benchmark phase lane。播放 SHALL 保留真实
timestamp/sequence/duration 展示，但 MAY 使用有界视觉间隔避免长时间无响应。

#### Scenario: 播放包含 Benchmark 和 Agent events 的运行
- **WHEN** 用户从头播放一个 Benchmark Replay
- **THEN** Agent milestone lane 和 Benchmark phase lane 按因果顺序推进，不把
  Benchmark phase 渲染为 AgentGraph node

#### Scenario: 单步到下一 activation
- **WHEN** 当前 activation 中间包含多个 audit/control moments，用户点击 Next
- **THEN** cursor 跳到下一个 activation 或重要 milestone，同时用户仍可访问被跨过的
  原始 moments

#### Scenario: 只有 Agent 运行
- **WHEN** Replay 没有 Benchmark context
- **THEN** 时间轴只展示 Agent milestones，不保留空 Benchmark lane 或 `not attached`
  占位内容

#### Scenario: 跳转失败
- **WHEN** Agent 成功但 Benchmark evaluation 失败
- **THEN** “Jump to failure”跳到 evaluation phase，并保持 Agent SUCCESS 的图状态

### Requirement: 自动跟随、历史锁定和回到当前
播放开始时过程视图 SHALL 随 factual cursor 增量呈现截至当前时刻的组件级运行故事，已出现的
步骤 SHALL 保持可见。用户选择历史故事步骤、node、activation 或 moment 后 SHALL 锁定组件
详情；播放、Graph cursor、Phone 和过程故事继续更新但不得强制改变详情选择，并 SHALL 提供
“回到当前”。

#### Scenario: 锁定后继续播放
- **WHEN** 用户正在查看旧 Reasoning activation 且播放器进入新的 ActionExecutor
- **THEN** Graph 和 Phone 跟随新的 factual current，过程增加动作步骤，组件详情仍显示旧 activation 并提示已锁定

#### Scenario: 锁定时出现失败
- **WHEN** 播放到新 activation failure 而组件详情已锁定
- **THEN** 页面显示醒目失败提示和跳转入口，不无条件覆盖选择或删除此前故事

#### Scenario: 回到当前
- **WHEN** 用户点击“回到当前”
- **THEN** Inspector 解除锁定并选择当前 cursor 对应的最新用户可理解故事步骤和正式 evidence

#### Scenario: 用户后退 Replay cursor
- **WHEN** 用户把 cursor 移到更早的 causal moment
- **THEN** 过程视图只显示截至该 cursor 已发生的故事事实，不泄露未来动作或结果

### Requirement: Virtual Phone 绑定 causally visible observation
Virtual Phone SHALL 只读展示当前或选中 cursor 可见的 screenshot、尺寸、observation
identity、interaction step、最近 action 和安全 device provenance。可选 overlay 只能
来自正式 evidence；组件 MUST NOT 连接设备、发送 ADB 命令或伪造识别框。

#### Scenario: 切换到含截图的 Observation
- **WHEN** cursor 到达一个通过完整性验证的 DeviceObservation complete
- **THEN** 手机区域加载对应 opaque artifact，并显示 observation/interaction identity

#### Scenario: 当前截图缺失
- **WHEN** 当前 observation 声明的截图为 missing 或 corrupt
- **THEN** 手机区域清除当前画面或将旧画面标为历史，展示缺失/损坏原因和 artifact
  metadata

#### Scenario: Perception 没有 overlay
- **WHEN** perception evidence 只有整体文本描述而没有正式 bounding boxes
- **THEN** Virtual Phone 不生成或猜测检测框

### Requirement: Inspector 分离定义、activation 和 evidence
Inspector SHALL 采用“过程 / 组件详情 / 技术详情”的渐进披露层级。“过程” SHALL 是默认
状态，并按 interaction 将正式 activation 聚合为用户可理解的观察、计划/判断、记忆变化、
动作、验证、反馈轮次与结果；generated runtime/control activation 只有在正式 projection
mapping 支持时才能聚合到 capability owner 或 relation。选择故事步骤后，“组件详情” SHALL
明确区分该次 activation 的输入与输出、状态、耗时、错误和直接相关 evidence。“技术详情”
SHALL 保留 Definition、Activation History、Runtime Identity、完整模型响应、raw Debug
Payload、evidence inventory、ID、hash 和 provenance，并默认折叠。所有内容 MUST 来自当前
cursor 可见的 immutable Replay facts，不得 dump 任意对象或按名称猜测语义。

#### Scenario: 打开有效 Replay
- **WHEN** Replay 已有一个或多个用户可理解的组件 activation
- **THEN** Inspector 首屏显示按因果顺序组织的运行故事，而不是内部 event 尾部、ID 列表或原始 payload dump

#### Scenario: Perception 故事步骤
- **WHEN** 用户选择带 observation 和识别结果的 Perception 步骤
- **THEN** 组件详情分别显示输入截图/Observation 与输出元素或整体描述，并如实标记未采集字段

#### Scenario: 同一节点有多次 activation
- **WHEN** feedback 使 Reasoning capability 执行多次
- **THEN** 过程按 interaction 保留多次决策，组件详情只显示选中 activation，并允许在历史中切换

#### Scenario: Action Executor activation
- **WHEN** 用户选择一个 Action Executor 步骤
- **THEN** 组件详情优先显示 Action、目标/参数、安全 ActionResult、effect、terminal status 与设备错误，而非 contract hash

#### Scenario: generated activation 可映射
- **WHEN** exact DeviceObserve、ActionRequest、Router、feedback 或 terminal activation 有正式 capability projection mapping
- **THEN** 过程显示其用户意义而不将它作为同级业务组件卡片，技术详情保留 exact activation 审计入口

#### Scenario: 外部组件没有专用 profile
- **WHEN** 外部组件只有 NodeContract 和通用安全 payload
- **THEN** 组件详情使用 typed inputs/outputs、safe identity、status、duration 和 artifact references，且不按 Python 类名失败

#### Scenario: 旧运行证据不完整
- **WHEN** 旧 Replay 缺少完整模型响应、typed summary 或 capability mapping
- **THEN** Inspector 使用可验证的有界事实和明确 unavailable 状态，不虚构内容、不猜测 owner，并保留原始审计入口

### Requirement: 证据 provenance 与真实性标记
History、Replay overview 和 evidence 区域 SHALL 展示正式 provenance，至少区分真实
Android 摘录、fake contract fixture 和普通导入来源。overview 可以压缩其默认视觉占用，
但用户 MUST 能访问 acquisition、environment、real-device-evidence 和 integrity 的
独立事实及安全解释。界面和文档 MUST NOT 用 fake Debug Payload 或 committed excerpt
证明 Runtime 已实现完整实时采集。

#### Scenario: 打开 fake 完整证据 fixture
- **WHEN** fixture 包含模型响应、UI XML 和 bounded loop
- **THEN** 页面完整演示相应 UI，同时以紧凑且明确的 label 标记
  `fake_contract_fixture`，并允许展开查看正式来源事实

#### Scenario: 打开真实 Android failure 摘录
- **WHEN** fixture 来源于已验证真实 Android trajectory，但完整响应和 XML 未采集
- **THEN** 页面标记真实来源、展示真实失败/截图事实，并如实显示缺失 evidence；它不将
  历史摘录表达为 fresh real-Android execution

### Requirement: 前端分层与只读状态所有权
Stage 2 前端 SHALL 遵守 `app → pages → widgets → features → entities → shared` 依赖方向。
Replay page/widget MUST NOT 导入 Builder feature 内部 store、editable XYFlow handles 或
保存命令；server resources、事实 projection、播放交互、临时选择和用户偏好 SHALL 按
前端架构文档分别拥有。

#### Scenario: Replay 图与 Builder 同时存在
- **WHEN** 工程构建同时包含 Agent Design 和 Run Replay 路由
- **THEN** import-boundary 检查证明 Replay 不依赖 Builder 内部实现，修改 Replay cursor
  不会污染 Builder draft

### Requirement: 深浅主题和可观察页面状态
Replay/History SHALL 支持现有深色与浅色主题，并明确呈现 loading、empty、partial、
not found、corrupt、artifact error 和 retry 状态。主题与 presentation MUST NOT 改变
Replay facts 或 AgentGraph identity。

#### Scenario: 切换主题后继续 Replay
- **WHEN** 用户在锁定某个 activation 时切换深浅主题
- **THEN** 三栏视觉更新，但 cursor、锁定选择、activation history 和 canonical hash
  保持不变

### Requirement: Replay 首屏优先解释一次 Agent 执行
Replay SHALL 在无需选择节点或展开技术详情的首屏，以组件级因果故事解释截至当前 cursor
的 Agent 执行，并紧凑保留独立的 Agent terminal status、仅在存在 Benchmark context 时
显示的 Benchmark outcome、最高优先级 failure target、安全原因摘要和 evidence
provenance/integrity。默认首屏 MUST NOT 由 activation 数量、内部 event 尾部、identity 或
hash 主导。所有内容 MUST 基于已持久化 Replay facts；它 MUST NOT 合并 Agent/Benchmark
outcome、推断根因、编造缺失节点，或将历史 Replay 标记为新的真实设备执行。

#### Scenario: 成功 ordinary Replay
- **WHEN** Replay 包含可验证的观察、决策、动作和成功结果
- **THEN** 首屏按 causal order 呈现这些核心步骤和成功结论，技术计数与 identity 保持可展开而不主导默认视图

#### Scenario: Agent activation 失败
- **WHEN** projection 有正式 activation failure target
- **THEN** 首屏在故事中保留失败前的已完成步骤、标识正式失败位置并提供跳转，同时保留独立 Agent status 和安全错误摘要

#### Scenario: Agent 成功但 Benchmark 失败
- **WHEN** Agent result 为 success 且 Benchmark evaluation 为 fail
- **THEN** 首屏同时显示 Agent success 与 Benchmark fail，并将 evaluation 作为独立失败位置而不伪造 AgentGraph node failure

#### Scenario: 没有 Benchmark context
- **WHEN** Replay resource 没有附加 Benchmark context
- **THEN** 首屏不渲染空 Benchmark 卡片或 timeline lane，且不把 `not attached` 表达为 Agent 失败

### Requirement: Replay 首屏的证据状态必须紧凑且可展开
Replay SHALL 以一个紧凑、可见的 evidence label 表达正式 acquisition、environment、
real-device-evidence 和 integrity 的组合状态。用户 MUST 能按需展开或访问该 label
以检查各个原始字段及其安全解释；页面 MUST NOT 仅因紧凑呈现而隐藏、弱化或推断这些
真实性边界。

#### Scenario: 历史 real-Android Replay
- **WHEN** resource 记录 `replay_projection / real_android / realDeviceEvidence=false`
- **THEN** 默认 label 明确其为历史投影而非 fresh execution，展开信息保留这三个独立
  的正式字段

#### Scenario: Fake contract fixture
- **WHEN** resource 记录 fake-device contract fixture
- **THEN** 默认 label 明确其为非真实设备证据，页面不依靠截图、手机外观或成功状态
  升级其来源

### Requirement: Replay 顶部必须压缩为 Agent 名称
Replay 工作台顶部 SHALL 仅显示一个人类可读 Agent 名称或安全 fallback，并为 Graph、Virtual Phone 和 Run Overview 释放垂直空间。Agent terminal status、可选 Benchmark outcome、failure target、原因摘要、计数、provenance/integrity 和技术 identity MUST 继续按既有 Replay 合同在右侧首屏、Graph、时间轴或可展开详情中可访问；压缩顶部 MUST NOT 删除、合并或推断这些事实。

#### Scenario: ordinary native Replay 有失败事实
- **WHEN** ordinary native Replay 包含 Agent failure、正式 failure target 和完整 evidence origin
- **THEN** 顶部只显示 Agent 名称，右侧首屏仍显示独立 status、failure location、安全原因和紧凑 evidence 状态

#### Scenario: Benchmark Replay
- **WHEN** Replay 带有 Benchmark context
- **THEN** 顶部保持名称简洁，右侧和时间轴继续独立显示 Agent status 与 Benchmark outcome，且不出现普通 task 再运行入口

### Requirement: Replay 底部必须组合播放与新 task 入口
ordinary native Replay SHALL 在最底部显示 Task Run Bar，并将现有 Replay playback/timeline 作为其上方的独立只读层。提交新 task SHALL 创建新的 ordinary Run 并导航到新 live identity；当前 Replay cursor、envelope、artifact、result 和 evidence MUST NOT 被修改或重解释。

#### Scenario: 从 eligible Replay 提交新 task
- **WHEN** Replay provenance 为 `native_studio_run`，snapshot 含本地 exact revision，Agent/revision/canonical identity 验证成功且用户提交新 task
- **THEN** Studio 创建新的 Run、进入其 live URL，并允许浏览器返回原 Replay

#### Scenario: 返回原 Replay
- **WHEN** 用户从新 Run 或其 terminal Replay 返回先前页面
- **THEN** 原 run identity、Replay facts 和持久 evidence 与提交前一致

#### Scenario: Replay 不具备 ordinary rerun 条件
- **WHEN** Replay 来自 Benchmark、导入、legacy/fake fixture，或本地 revision 缺失、invalid、identity/hash 不匹配
- **THEN** Replay 保持只读，底部明确说明不能基于该证据启动普通 Run，且不回退到 current revision 猜测

#### Scenario: Task Bar 与时间轴共存
- **WHEN** 用户播放、单步或锁定 Replay activation
- **THEN** 上层播放控制只改变 Replay cursor/selection，下层 task 草稿只影响潜在的新 Run，两者互不覆盖且均不写入 Replay identity

