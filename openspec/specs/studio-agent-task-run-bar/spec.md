# studio-agent-task-run-bar Specification

## Purpose
为同一个已验证 Agent revision 提供工作台底部的普通 task 输入和重复运行入口，使每个 task 创建可审计的独立 Run，同时保持 AgentGraph、Replay 与 Benchmark 边界不变。
## Requirements
### Requirement: 普通 task 必须在工作台底部持续可用
Studio SHALL 在普通 Agent launch、terminal native Replay 和相应的三栏工作台底部提供 Task Run Bar。Task Run Bar SHALL 将 task 表达为一次 Run 的输入而非 AgentGraph 配置；用户 MUST 能在不返回 Builder、不保存新 revision 的情况下修改 task 并再次提交。

#### Scenario: 从 Builder 打开未运行工作台
- **WHEN** 用户对 valid immutable revision 点击 `Run`，或对已验证的 dirty draft 点击 `Save & Run` 并成功保存
- **THEN** Studio 进入该 exact revision 的三栏 launch 工作台，并在最底部聚焦可编辑的普通 task 输入，而不显示独立全页启动表单

#### Scenario: 同一 revision 连续运行不同 task
- **WHEN** 用户完成 Task A 的 Run 后在底部将输入改为 Task B 并再次提交
- **THEN** Studio 使用同一 agent/revision identity 创建新的 Run B，Run A、其 Replay 和 immutable revision 均保持不变

### Requirement: 每次 task 提交必须创建或恢复一个独立 Run
Task Run Bar SHALL 复用普通 Run create 合同，提交 exact agent identity、revision identity、非空 task text、可选有界 metadata、安全 device profile 和 client request identity。对同一未修改提交的未知结果重试 MUST 复用 request identity；task、metadata 或 launch target 的语义变化 MUST 产生新的 request identity。

#### Scenario: 提交新的普通 task
- **WHEN** eligible launch target 的 task 和 metadata 通过客户端校验且用户点击运行
- **THEN** Studio 创建新的 durable ordinary Run，并将 live URL 绑定到后端返回的 run identity

#### Scenario: 创建响应丢失后重试
- **WHEN** create 请求结果未知且用户未修改 task、metadata、agent 或 revision
- **THEN** Task Run Bar 复用原 client request identity，使后端幂等返回同一个 Run

#### Scenario: 用户修改 task 后再次提交
- **WHEN** 前一次创建已经返回或 task/metadata 的语义内容发生变化
- **THEN** Task Run Bar 使用新的 client request identity，且不得覆盖或恢复为前一次 Run

### Requirement: Task Run Bar 必须呈现真实运行控制状态
Task Run Bar SHALL 区分 idle、invalid、submitting、accepted、starting、running、cancelling、terminal 和 create-error 状态。活动 Run 时 SHALL 显示已持久 task 和真实 lifecycle，并将协作式 Cancel 作为底部运行控制；它 MUST NOT 允许同一控件暗示覆盖当前 Run、强制中断 active call、并行设备执行、Pause 或 node retry。

#### Scenario: Run 正在执行
- **WHEN** 当前 URL 绑定 accepted、starting 或 running Run
- **THEN** 底部显示该 Run 的持久 task、真实状态和可用的协作式 Cancel，而不是可覆盖当前 Run 的空输入框

#### Scenario: Run 正在取消
- **WHEN** cancellation request 已被后端接受但 Run 尚未到达安全终止边界
- **THEN** 底部显示 `cancelling` 并继续跟随，不声称设备、模型或 Python 调用已经停止

#### Scenario: 创建失败
- **WHEN** Run create 返回安全 contract、validation 或 transport error
- **THEN** Task Run Bar 保留 task 草稿、显示可重试错误，并且不导航到伪造的 live Run

### Requirement: Task 草稿必须保持非持久且与服务端事实分离
未提交的 task text、metadata editor、展开状态和 create retry identity SHALL 由运行入口 feature 的有界临时状态拥有。Studio MUST NOT 将 task 草稿、已提交 task、Run evidence、Prompt、模型响应或截图写入 `localStorage`；提交成功后的 task MUST 仅以 authoritative Run resource 恢复。

#### Scenario: 刷新未提交 task
- **WHEN** 用户在 idle Task Run Bar 输入内容但未提交并刷新页面
- **THEN** Studio 可以丢弃该临时草稿，但不得从浏览器持久化中恢复或外泄它

#### Scenario: 刷新活动 Run
- **WHEN** 用户刷新带有 run identity 的 live URL
- **THEN** 底部 task 和 lifecycle 从同一后端 Run resource 恢复，而不是依赖此前 React state

#### Scenario: metadata 包含无效或不安全值
- **WHEN** metadata 不是有界 JSON object，或命中现有 secret、raw serial、宿主路径或 Benchmark shape 拒绝规则
- **THEN** Studio 阻止提交、保留可编辑草稿并使用安全错误，不在日志或 URL 回显原值

### Requirement: Task Run Bar 必须发现并选择安全 Device Profile
Task Run Bar SHALL 从权威 Device Profile API 加载安全 Profile identities，并把当前选择作为
ordinary Run request 的非语义运行配置。一个可用 Profile MAY 自动选择；多个 Profile
MUST 提供明确选择；Profile 偏好 MAY 保存为不含 task/evidence/serial 的本地用户偏好，
但每次提交必须重新验证当前目录。

#### Scenario: 只有一个 Profile
- **WHEN** Device Profile API 返回一个 eligible Android Profile
- **THEN** Task Run Bar 自动选择它、显示安全 label，并以其 identity 创建 Run

#### Scenario: 有多个 Profile
- **WHEN** API 返回多个 eligible Android Profiles
- **THEN** 用户可以在底部 Run 控件选择一个，request 不包含任何 raw serial 或 private target fact

#### Scenario: 之前偏好的 Profile 已删除
- **WHEN** local preference 指向当前目录不存在的 Profile
- **THEN** Task Run Bar 清除或替换无效选择并要求确认，不提交 stale identity

### Requirement: Task Run Bar 必须使用 Readiness Gate
空闲 Task Run Bar SHALL 合并 exact revision compile status、Runtime Readiness 和 selected
Profile 状态决定提交 eligibility。Blocked 状态 MUST 保留临时 task/metadata 草稿、显示
稳定原因和修复入口，并且不创建伪 Run；服务端 create 仍 MUST 重新验证。

#### Scenario: LLM Secret 未配置
- **WHEN** task 有效但 exact revision 的 SecretRef 在当前 Studio 中缺失
- **THEN** Run 按钮禁用，底部显示安全缺失引用和 Settings 指引，不清空 task 草稿

#### Scenario: Readiness 请求暂时失败
- **WHEN**客户端无法读取当前 readiness
- **THEN** Task Run Bar 显示可重试的 unknown 状态，不假定 ready、不发送 Run create

#### Scenario: 所有条件就绪
- **WHEN** revision valid、readiness ready、Profile selected 且 task/metadata 有效
- **THEN** Task Run Bar 允许提交并继续沿用现有 idempotent request identity 语义

