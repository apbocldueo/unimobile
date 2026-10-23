# studio-benchmark-experiment-monitor Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-monitor-5-3. Update Purpose after archive.
## Requirements
### Requirement: Benchmark Experiment Monitor 必须以 durable resource 为权威事实
Studio SHALL 提供 `/experiments/:experimentId` 路由，并通过版本化、严格解析的
Experiment 与 TaskRun HTTP DTO 展示 lifecycle、progress、timing、outcome、
availability、diagnostics 和 links。浏览器 MUST NOT 根据已收到的 event 自行推导
recovery、evaluation、terminal outcome 或持久资源状态；event 只能触发权威资源刷新。
路由 MUST 明确展示 loading、not-found、partial availability、recovering、
interrupted、terminal 和安全错误状态。

#### Scenario: 刷新运行中的 Experiment
- **WHEN**用户在 Experiment 执行期间刷新 `/experiments/:experimentId`
- **THEN**页面从 durable Experiment、TaskRun 与 event cursor 重建视图，而不是依赖刷新前的 React 内存

#### Scenario: event 先于资源刷新到达
- **WHEN**浏览器收到一个 phase-complete event 但 TaskRun resource 尚未完成下一次查询
- **THEN**页面保留已确认 event 事实并刷新 TaskRun，且不自行把 TaskRun 推导为 terminal

#### Scenario: Experiment 不存在
- **WHEN**路由参数对应的 Experiment 无法找到
- **THEN**页面展示稳定 not-found 状态，不启动无界重试或构造占位 Experiment

### Requirement: Monitor 必须提供可扩展的 TaskRun 导航和选择边界
Monitor SHALL 在三栏工作台之外提供可折叠 TaskRun rail，按服务返回的稳定计划顺序展示
TaskRun identity、Agent、Task、repeat、lifecycle、outcome 和可用性摘要。URL 中的
Experiment identity MUST 保持稳定；当前 TaskRun selection 与 follow/lock 状态 MUST
属于客户端交互状态，不得覆盖 TanStack Query 中的服务端资源。当前单 Task slice
仍 MUST 使用复数结构，不得假定永远只有一个 TaskRun。

#### Scenario: 默认选择第一项
- **WHEN**Experiment 包含 TaskRuns 且用户尚未作出选择
- **THEN**Monitor 确定地选择稳定顺序中的第一项并展示其事实

#### Scenario: 用户锁定旧 TaskRun
- **WHEN**用户选择一个较早 TaskRun 后新的 TaskRun event 到达
- **THEN**资源与 event cursor 继续更新，但选择保持锁定并提供回到当前项的动作

#### Scenario: TaskRun 暂时不可用
- **WHEN**Experiment resource 已加载但 TaskRun query 暂时失败
- **THEN**Experiment summary 与连接状态仍可见，rail 显示可重试的局部错误而不让整个页面崩溃

### Requirement: Monitor live session 必须保持连续性和完整性
Benchmark live session SHALL 先通过有界 HTTP event page 补齐到查询所得 high-water，
再连接 named SSE，并使用最后确认的 Experiment-local sequence 恢复。它 MUST 接受
identity、sequence 与 canonical content 均相同的精确重复，MUST 对 gap 执行 HTTP
backfill，MUST 保持 unknown versioned kind 可审计并继续推进 cursor。若同一位置或
identity 出现内容冲突、连续性无法恢复或服务报告 journal integrity failure，session
MUST 冻结在最后已验证前缀并显示不可忽略的完整性错误，不得自动跳过。

#### Scenario: 首次打开存在历史 events
- **WHEN**Monitor 打开时 Experiment journal 已有多页 events
- **THEN**客户端连续分页到固定 high-water 后才进入 live wait，并按 sequence 只投影一次

#### Scenario: SSE 中出现 sequence gap
- **WHEN**客户端最后确认 sequence 8 而下一 SSE journal frame 为 sequence 11
- **THEN**session 使用 HTTP 查询补齐 9 和 10，验证连续后再接受 11

#### Scenario: 收到精确重复
- **WHEN**重连后再次收到与已确认 sequence、event identity 和 canonical content 相同的 frame
- **THEN**session 忽略重复投影并保持 cursor 不回退

#### Scenario: 收到完整性冲突
- **WHEN**相同 sequence 或 event identity 携带不同 canonical content
- **THEN**session 关闭 live 接收、冻结最后已验证事实，并要求用户显式重试或刷新

#### Scenario: 收到未知 event kind
- **WHEN**服务发送 envelope 有效但当前前端尚未识别的 versioned kind
- **THEN**session 保留安全 envelope 摘要、推进连续 cursor，且 Monitor 不崩溃或猜测其业务含义

### Requirement: Monitor 必须区分事实状态、传输状态和用户视图状态
Studio SHALL 分别维护由 HTTP/SSE 提供的 authoritative facts、连接阶段与 cursor、
以及 TaskRun selection、pane size 和 follow/lock 等用户视图状态。断线、heartbeat、
reconnecting 和 terminal drain MUST 只改变传输展示；pane size MAY 作为非语义偏好
持久化，但 Experiment、TaskRun、event、截图、UI XML、Prompt 和 Replay evidence
MUST NOT 写入 `localStorage`。

#### Scenario: SSE 暂时断线
- **WHEN**网络中断但 durable Experiment 仍在运行
- **THEN**Monitor 显示 reconnecting，保留最后已验证事实和用户选择，并从确认 cursor 恢复

#### Scenario: 收到 heartbeat
- **WHEN**SSE 发送 heartbeat 而没有 journal frame
- **THEN**连接健康时间更新，但 factual projection 与 journal cursor 不改变

#### Scenario: terminal drain 完成
- **WHEN**唯一 terminal event 已处理且客户端追平最终 high-water
- **THEN**session 进入 terminal-complete 连接状态并停止重连，权威 terminal 展示仍来自资源查询

### Requirement: 三栏 Benchmark workbench 必须诚实表达证据可用性
Monitor SHALL 复用 mode-neutral 三栏布局，并从 immutable Agent snapshot 渲染只读
Graph、Virtual Phone 和 Inspector。Stage 5.3 运行中若 committed facts 不包含 nested
Agent node activation、screenshot 或 UI XML，Graph MUST 保持静态且不得高亮推测节点，
Virtual Phone MUST 显示 live evidence unavailable，Inspector MUST 只展示已提交的
Benchmark phase、lifecycle、diagnostic 和 availability 事实。任何缺失证据 MUST 以
不可用状态表达，而不是用 mock、timer 或普通 Run telemetry 填充。

#### Scenario: TaskRun 正在 action phase
- **WHEN**event journal 只声明 Benchmark action phase start 而没有 nested Agent node activation
- **THEN**Inspector 展示 action phase，Graph 不高亮任意节点，Virtual Phone 不伪造 frame

#### Scenario: terminal TaskRun 缺少 screenshot
- **WHEN**TaskRun 已 terminal 但其 availability 声明没有 live screenshot
- **THEN**Virtual Phone 展示明确不可用原因，并保留进入持久 Replay 的独立动作

#### Scenario: 普通 Run 与 Benchmark 同时存在
- **WHEN**前端同时构建普通 Run workbench 与 Benchmark Monitor
- **THEN**Benchmark 使用自己的 DTO 和 live session，不把 `StudioRunResource` 或普通 Run journal 强制转换为 Benchmark 类型

### Requirement: Cancel 必须是显式且受 lifecycle 约束的协作命令
Monitor SHALL 只在服务资源声明 Experiment 可取消时提供确认后的 Cancel command，
调用既有 accepted-only cancel API，并在 mutation 期间防止重复提交。Cancel 成功
MUST 触发 Experiment 与 TaskRun 资源刷新；客户端 MUST NOT 因关闭页面、SSE 断开或
本地按钮状态直接标记 Experiment cancelled。

#### Scenario: 用户确认取消 accepted Experiment
- **WHEN**Experiment 可取消且用户确认 Cancel
- **THEN**客户端提交一次 cancel command、刷新权威资源并展示后端接受后的 lifecycle

#### Scenario: terminal 竞争先完成
- **WHEN**Cancel 请求到达前 Experiment 已进入 terminal
- **THEN**Monitor 展示服务返回的 immutable terminal fact，不覆盖为 cancelled

#### Scenario: 用户关闭 Monitor
- **WHEN**用户导航离开运行中的 Experiment
- **THEN**浏览器只释放 query 与 SSE consumer，不向后端发送 cancel

### Requirement: terminal TaskRun Replay 必须由用户显式打开持久证据
当 TaskRun resource 声明 native Replay available 且提供安全 link 或 replay identity
时，Monitor SHALL 提供显式“打开 Replay”动作，导航到既有 Replay route 并由该 route
重新加载持久 evidence envelope。Monitor MUST NOT 自动跳转、把 live SSE buffer
冒充 Replay，或在 Replay unavailable 时构造临时 trajectory。

#### Scenario: 用户打开可用 Replay
- **WHEN**terminal TaskRun 的 resource 声明 replay available 且用户点击打开
- **THEN**应用导航到持久 Replay identity，由 Replay route 独立请求 evidence

#### Scenario: Replay 尚未发布
- **WHEN**TaskRun terminal 但 resource 声明 Replay unavailable 或 publication 未完成
- **THEN**Monitor 展示 availability 状态并允许资源刷新，不显示失效的 Replay 链接

#### Scenario: 多个 TaskRun 未来可用
- **WHEN**一个 Experiment 最终包含多个 terminal TaskRuns
- **THEN**每个 rail item 各自提供显式 Replay 动作，Monitor 不自动选择或跳转到任意一个

### Requirement: Monitor 前端实现必须遵守 FSD-lite 和安全展示边界
Benchmark Experiment DTO、parser、query 与 mutation SHALL 属于 entity 层；live
session、selection、cancel 和 Monitor 交互 SHALL 属于 feature 层；三栏组合 SHALL
属于 widget 层；路由参数与页面级边界 SHALL 属于 page/app 层。跨 slice import MUST
经过公开 API。错误、diagnostic、event 与 availability 展示 MUST 使用结构化安全字段，
不得记录或渲染 secret、raw device serial、device handle、宿主绝对路径或未清理异常。

#### Scenario: import boundary 检查
- **WHEN**ESLint 与 TypeScript 检查新的 Benchmark Monitor slices
- **THEN**依赖只沿 app → pages → widgets → features → entities → shared 方向并经过公开入口

#### Scenario: 后端返回安全 diagnostic
- **WHEN**Monitor 收到带 code、message 和安全 locator 的结构化 diagnostic
- **THEN**页面展示允许字段，且不从异常文本解析身份、路径或 lifecycle

