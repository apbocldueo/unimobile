# studio-run-debug-evidence Specification

## Purpose
定义 Studio live Run 调试证据的版本化、安全持久化、敏感内容策略、完整性与资源上限合同。

## Requirements

### Requirement: 调试数据必须使用版本化显式 envelope
系统 SHALL 使用版本化 `DebugPayloadEnvelope` 保存 activation-scoped 调试事实，包括
run/node/activation identity、component definition identity、role-specific task/context、
safe input/output summary、duration、error、usage、typed evidence references 和每个证据
的 availability。每个可读取 evidence reference SHALL 明确 kind、opaque artifact
identity、content type、size/hash、provenance 和 causal identity；系统 MUST NOT 让客户端
根据无类型 `artifactIds` 的数组顺序、文件名或 component class 猜测内容，也 MUST NOT
递归序列化任意 Python 对象或 live component state。

为兼容既有 Run，旧 `artifactIds` MAY 保留，但 typed reference SHALL 是新客户端解析
模型响应和 Debug Payload 的唯一权威；缺少 typed reference 时客户端 MUST 明确显示
unavailable/not_captured，不得 ordinal fallback。

#### Scenario: Planner activation 完成
- **WHEN** Planner 返回可序列化结果
- **THEN** envelope 显示任务、安全输入输出摘要、耗时、正式 component identity 和按 kind 标识的 evidence references

#### Scenario: Perception activation 完成
- **WHEN** Perception 产生识别组件结果和 screenshot evidence
- **THEN** envelope 保存有界识别结果摘要和 typed opaque screenshot reference，不内联图片

#### Scenario: 输出包含 live client
- **WHEN** component output 包含 device、HTTP client 或不可批准对象
- **THEN** serializer 拒绝该字段、标记 excluded 并保留结构化 diagnostic

#### Scenario: 读取旧版无类型 Debug Payload
- **WHEN** 历史 Run 只有 `artifactIds` 且没有 typed evidence reference
- **THEN** Inspector 显示 safe summary 和真实 availability，不按数组位置猜测模型响应或 Prompt

### Requirement: 完整模型响应必须作为受控 artifact 持久化
当所选 component adapter 捕获到完整模型响应时，系统 SHALL 在配置大小上限内将它作为
run-scoped artifact 保存，并在同 activation Debug Payload 中记录
`modelResponse` typed evidence reference，包括 opaque identity、content type、size/hash、
provenance、causal identity 和 availability。Reference MUST 只在 descriptor 已持久化后
进入 journal；默认 Inspector/Run API 可以按该 reference 读取响应。超过限制、未捕获、
损坏、redacted 或 typed reference 缺失 MUST 明确表示，不能以空字符串、safe summary 或
artifact 数组顺序冒充完整内容。

#### Scenario: 捕获完整模型响应
- **WHEN** model-backed component 返回完整 response 且通过安全处理和大小校验
- **THEN** response artifact 原子保存，Debug Payload 的 `modelResponse` typed reference 标记 available 并可通过 run artifact API 读取

#### Scenario: 旧 adapter 没有完整响应
- **WHEN** component 只产生 safe summary
- **THEN** Debug Payload 将 model response 标记为 not_captured，不从 summary 或其他 artifact 反推原文

#### Scenario: 响应超过上限
- **WHEN** 完整响应大于配置的 artifact 限制
- **THEN** 系统按策略拒绝或截断安全副本，typed reference 明确记录 truncated/excluded 与原始大小，不静默丢失

#### Scenario: typed reference 指向其他 Run
- **WHEN** 客户端使用 Run A 的 model response reference 请求 Run B URL
- **THEN** artifact resolver 拒绝读取且不泄露内容、metadata 或宿主路径

### Requirement: 完整 Prompt 必须保存但默认隐藏
当 model adapter 能在调用边界获得完整 Prompt 时，系统 SHALL 在 secret redaction 后将其
保存为分类 `sensitive_prompt` 的受控 artifact。Debug Payload typed evidence SHALL 仅
暴露 `prompt` 的 hidden availability 和安全 metadata，不得提供普通客户端可读取的内容
reference。普通 Run/Replay envelope、默认 Inspector、普通 artifact endpoint 和默认
export MUST 排除其内容；Stage 4 MUST NOT 提供绕过此策略的浏览器路径。

#### Scenario: 模型调用捕获 Prompt
- **WHEN** adapter 在调用前获得 Prompt 且安全处理成功
- **THEN** Prompt 进入受控隐藏 artifact，Debug Payload 只返回 hidden availability 而非可读取内容

#### Scenario: 猜测 Prompt artifact identity
- **WHEN** 浏览器通过普通 artifact endpoint 请求隐藏 Prompt
- **THEN** resolver 不返回内容，也不泄露宿主路径或相邻敏感 artifact

#### Scenario: 默认导出 live Replay
- **WHEN** 用户导出包含 hidden Prompt metadata 的 Replay
- **THEN** bundle 排除 Prompt 内容，并在 manifest 记录 excluded/hidden

#### Scenario: Live Inspector 查看 activation
- **WHEN** activation evidence 表明 Prompt 已捕获
- **THEN** Inspector 显示 hidden 状态和安全说明，不渲染、预取或记录 Prompt 文本

### Requirement: 所有调试与 artifact 内容必须先安全处理
Debug serializer、event payload、SQLite metadata、artifact、HTTP 和 export SHALL 共享
版本化安全策略，移除或替换 API key、token、password、authorization、raw device serial、
宿主绝对路径和未批准 header。redaction MUST 在数据写盘前发生，diagnostic 不得回显原值。

#### Scenario: 多层 payload 包含安全 canary
- **WHEN** input、model response、exception 和 metadata 中嵌套同一个 secret canary
- **THEN** SQLite、artifact root、HTTP、SSE 和 export 扫描均找不到原值，并保留 redaction 事实

#### Scenario: error 包含绝对路径和 serial
- **WHEN** device 或 filesystem exception 含宿主路径和 raw serial
- **THEN** Run error 和 Debug Payload 只保存安全 code/message 与配置的 device profile identity

### Requirement: evidence availability 与完整性必须是一等事实
每类 evidence SHALL 使用统一 availability vocabulary，至少区分 `available`、
`not_captured`、`excluded`、`hidden`、`missing`、`corrupt`、`redacted` 和 `truncated`。
Artifact metadata MUST 保存 size、hash、schema、capture source 和 causal identity；
读取时 MUST 验证 run ownership 和 integrity。

#### Scenario: screenshot 声明存在但文件丢失
- **WHEN** metadata 存在且受控内容缺失
- **THEN** artifact 读取失败并将 evidence 标为 missing，不返回上一张或其他 Run 内容

#### Scenario: artifact hash 不匹配
- **WHEN**受控文件内容与保存的 hash 不一致
- **THEN** resolver 返回 integrity error、标记 corrupt 并阻止内容进入 Inspector/Replay

### Requirement: 调试证据必须有有界序列化与资源策略
系统 SHALL 对 inline depth、member count、string length、event size、artifact size 和
每 Run 总量使用显式可配置上限。超限处理 MUST 是确定性的，并保存 truncated/excluded
diagnostic；任何单个调试 payload MUST NOT 导致无限内存、SQLite row 或 SSE frame。

#### Scenario: 深度嵌套 component output
- **WHEN**输出超过允许的深度或成员数
- **THEN** serializer 产生有界摘要和结构化 truncation marker，服务保持可用

#### Scenario: 大型图片或 XML
- **WHEN** observation evidence 超过 inline 限制但仍在 artifact 限制内
- **THEN**内容只进入 artifact store，event 和 SQLite 仅保存有界 descriptor
