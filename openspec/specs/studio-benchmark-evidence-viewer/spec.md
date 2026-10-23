# studio-benchmark-evidence-viewer Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-evidence-viewer-5-4d2. Update Purpose after archive.
## Requirements
### Requirement: Evaluation evidence 必须通过 causal identity 唯一解析
Studio SHALL 只为当前 Report 中已严格解析的 Evaluation leaf evidence 解析非空
`artifactRef`。解析 SHALL 在已完整、有界收集的 Experiment artifact inventory
中按 `descriptor.causalIdentity` 精确匹配，并 SHALL 同时要求 exact
Experiment identity、exact 当前 Studio TaskRun identity 和恰好一个可见匹配。
Artifact kind、artifact identity、文件名、Core reference 的路径外观或当前
selection 顺序 MUST NOT 代替这些条件。

#### Scenario: 唯一 TaskRun-scoped evidence
- **WHEN**当前 Evaluation leaf 的 `artifactRef` 在 bounded inventory 中恰好对应一个同 Experiment、同当前 TaskRun 的 descriptor
- **THEN**Viewer 将该 descriptor 和它已经严格解析的 content capability 作为唯一候选

#### Scenario: 相同 reference 出现在不同 TaskRun
- **WHEN**相同 causal identity 只存在于另一个 TaskRun，或同时存在于当前与其他 TaskRun
- **THEN**解析只接受当前 TaskRun 中恰好一个匹配，不跨 TaskRun 打开内容

#### Scenario: 重复 causal reference
- **WHEN**当前 Experiment 和 TaskRun 的两个可见 descriptor 声明相同 causal identity
- **THEN**Viewer 显示 ambiguous-reference integrity state，并且不选择任意 artifact 或发起内容请求

#### Scenario: 空或缺失 reference
- **WHEN**leaf evidence 没有 `artifactRef`，或 bounded inventory 中没有可见的 exact match
- **THEN**Viewer 分别显示 inline/no-reference 或 unavailable-reference 状态，不从 evidence value、kind、artifact id 或路径形状猜测

#### Scenario: inventory 无法完整闭合
- **WHEN**inventory 超过成员上限、cursor 不前进、排序不稳定、hidden count 改变或任一 page scope 冲突
- **THEN**Evidence resolution 整体失败关闭，Report 其余已验证事实仍保持可用

### Requirement: Evidence content 必须只跟随 scoped capability
Viewer SHALL 只请求唯一 inventory item 返回且 strict entity parser 已接受的
`links.content`。请求 MUST 通过配置的 Studio API origin 解析该相对 capability，
但 MUST NOT 从 Experiment、TaskRun、artifact identity、kind、filename、
`artifactRef`、storage reference 或 host path 构造或修补 resource path。

#### Scenario: 精确 TaskRun content link
- **WHEN**可读 descriptor 的 exact content link 同时编码 owning Experiment、TaskRun 和 artifact identity
- **THEN**Viewer 只跟随该 link，并让后端 managed resolver 再次执行 scope、availability、size 和 hash 校验

#### Scenario: safe-looking cross-scope link
- **WHEN**inventory payload 的 `/studio/` content link 指向另一个 Experiment、TaskRun 或 artifact
- **THEN**strict inventory parser 拒绝 payload，Viewer 不导航、不请求也不修补该 link

#### Scenario: 不可读 descriptor 带 content link
- **WHEN**pending、not-produced、excluded、missing、corrupt、failed 或 hidden descriptor 试图携带可读 content link
- **THEN**strict parser 或 Viewer contract 失败关闭且不读取 body

#### Scenario: resolver 在读取时闭合 integrity
- **WHEN**内容在 descriptor 提交后变为缺失、大小或 SHA-256 不符，或无法安全打开
- **THEN**Viewer 显示 bounded missing/corrupt/open-failed state，后续 authoritative inventory 可反映闭合后的 availability，且不泄露 storage detail

### Requirement: Preview loader 必须在读取过程中保持有界
Viewer SHALL 使用不进入 Zustand 或长期 TanStack Query cache 的短生命周期 loader。
Loader SHALL 在分配完整内容前比较 descriptor size 与媒体预览上限，在响应后验证
HTTP status、exact normalized content type、声明 Content-Length，并通过流式读取在
实际 byte count 超限时取消。文本类 preview 上限 SHALL 为 2 MiB；PNG preview
上限 SHALL 为 8 MiB、宽高各不超过 4096 pixels 且总像素不超过 16,777,216。
响应实际 byte count MUST 等于 descriptor size。

#### Scenario: descriptor 已声明 oversized
- **WHEN**文本 descriptor 超过 2 MiB 或 PNG descriptor 超过 8 MiB
- **THEN**Viewer 在 fetch 前显示 oversized state，不把内容载入 JavaScript 内存

#### Scenario: 响应声明大小冲突
- **WHEN**Content-Length 缺失、非法或不等于 descriptor size
- **THEN**Viewer 显示 size-mismatch state 并停止预览，不把响应解释为受验证 evidence

#### Scenario: 流式读取超过边界
- **WHEN**响应实际 bytes 超过媒体上限或 descriptor size，即使 header 声称更小
- **THEN**loader 取消 reader、丢弃已收集 bytes 并显示 oversized 或 size-mismatch state

#### Scenario: obsolete request
- **WHEN**用户在证据请求完成前关闭 Viewer、切换 TaskRun 或选择另一条 evidence
- **THEN**旧请求通过 AbortSignal 取消，迟到结果不能覆盖当前 selection

### Requirement: Preview 必须按允许的 content type 安全展示
Viewer SHALL 对 `application/json`、`application/x-ndjson`、`application/xml`、
`text/plain` 和 `image/png` 使用显式 preview adapter。HTTP content type MUST 与
descriptor 的 normalized content type 精确一致。JSON、NDJSON、XML 和纯文本 MUST
作为转义文本渲染，不得作为 HTML、SVG、脚本或可执行 markup 注入。ZIP 与其他后端
allowlist 中不可预览的类型 SHALL 只提供权威 capability 的 download-only 浏览器
handoff，并 MUST NOT 在 Viewer 中解压、执行或解释。

#### Scenario: JSON evidence
- **WHEN**bounded JSON body 的 MIME 与 descriptor 一致且 JSON 语法有效
- **THEN**Viewer 显示转义后的结构化文本，不执行字符串中的 HTML 或 script

#### Scenario: malformed JSON 或 NDJSON
- **WHEN**JSON 无法解析，或 NDJSON 任一非空行不是合法 JSON value
- **THEN**Viewer 显示 content-validation state，并且不把部分内容冒充完整结构化 evidence

#### Scenario: XML evidence
- **WHEN**bounded XML body 包含 element、CDATA、entity-looking text 或 script-looking text
- **THEN**Viewer 只显示转义源码，不使用 `innerHTML`、DOMParser 结果或嵌入式文档执行它

#### Scenario: PNG evidence
- **WHEN**response MIME、PNG signature、IHDR dimensions、descriptor size 和 preview ceilings 全部合法
- **THEN**Viewer 以临时 object URL 显示图片，并保留 kind、availability、size、hash、provenance 与 causal identity metadata

#### Scenario: PNG dimensions 超限或签名非法
- **WHEN**PNG header 非法、宽高超过 4096 或总像素超过 16,777,216
- **THEN**Viewer 拒绝创建可显示 image state，并显示 invalid-image 或 oversized state

#### Scenario: ZIP 或 non-previewable allowed content
- **WHEN**descriptor content type 为 ZIP 或后端允许但 Viewer 没有 preview adapter 的类型
- **THEN**Viewer 标记 download-only，并只把 exact content capability 交给浏览器，不声称下载完成、完整性验证完成或正式 Export 成功

#### Scenario: MIME mismatch
- **WHEN**HTTP Content-Type 与 descriptor content type 不一致或不在 Viewer allowlist
- **THEN**Viewer 显示 content-type-mismatch state，不嗅探并降级为其他 renderer

### Requirement: Availability 和失败事实必须保持独立且真实
Viewer SHALL 分别投影 readable `available`、`redacted`、`truncated`，以及
`pending`、`not_produced`、`excluded`、`missing`、`corrupt`、`failed` 等持久
availability。`oversized`、size mismatch、content-type mismatch、invalid content、
request failure、absent reference 和 ambiguous reference SHALL 作为 Viewer-local
state 表达，而不是写回或替换后端 availability。Hidden evidence SHALL 只使用
inventory 的匿名 aggregate `hiddenCount` 表达。

#### Scenario: redacted 或 truncated evidence
- **WHEN**descriptor availability 为 redacted 或 truncated 且 content capability 可读
- **THEN**Viewer 允许有界预览并始终显示对应限制 badge，不把内容描述为完整原始 evidence

#### Scenario: 一个 artifact corrupt
- **WHEN**当前 evidence 打开时发生 corrupt closure
- **THEN**该 Viewer 显示 corrupt，Report、Evaluation Tree、metrics、comparison、Replay、trajectory 和 bundle 的独立已验证状态不被覆盖

#### Scenario: hidden aggregate 存在但 reference 没有匹配
- **WHEN**`hiddenCount` 大于零且当前 `artifactRef` 没有可见匹配
- **THEN**页面只说明 Experiment 存在匿名 hidden artifacts 和当前 reference 不可解析，不声称某个 hidden artifact 就是该 leaf 的 evidence

#### Scenario: retry
- **WHEN**可重试 network 或 resolver failure 后用户选择 Retry
- **THEN**Viewer 使用当前唯一 scoped capability 发起新的短生命周期请求，不重新执行 Experiment、连接设备或扫描文件目录

### Requirement: Viewer 生命周期必须释放内容和保持页面可恢复
Evidence selection SHALL 是 Report workbench 的临时视图状态，而不是持久业务事实。
关闭 Viewer、切换 evidence、切换 TaskRun、Report scope 改变或组件卸载 SHALL
取消进行中请求、丢弃 text/byte buffers 并 revoke 已创建的 image object URL。
Report route 刷新 SHALL 从 Experiment、TaskRun、report 和 inventory resource
重建事实，但 MUST NOT 自动恢复或预取先前打开的 evidence body。

#### Scenario: 关闭 PNG Viewer
- **WHEN**用户关闭一个已显示 PNG 的 Viewer
- **THEN**object URL 被 revoke，图片 bytes 不保留在全局 store 或 server cache

#### Scenario: TaskRun 切换
- **WHEN**用户在 Viewer 打开时选择另一个 TaskRun
- **THEN**旧 Viewer selection 和 content 被释放，新 TaskRun evidence 必须重新按新 scope 解析

#### Scenario: 刷新 Report deep link
- **WHEN**用户刷新带稳定 TaskRun selection 的 Report route
- **THEN**页面可重新取得 Report 与 inventory metadata，但不会在没有显式用户动作时加载任一 leaf artifact body

### Requirement: Evidence Viewer 必须保持安全与副作用边界
Viewer、fixture、错误 state 和日志 MUST NOT 显示或记录 Prompt、secret、token、
raw device serial、storage reference、host absolute path、后端原始异常、hidden
artifact identity 或未转义 artifact markup。Evidence query MUST NOT 启动 worker、
连接设备、构造 plugin/model、加入 Monitor SSE session、重算 Evaluation 或统计，
也 MUST NOT 被描述为自动失败诊断。

#### Scenario: 安全 canary 出现在 payload 或错误
- **WHEN**content、metadata、diagnostic 或 transport error 中出现 Prompt、secret、raw serial、storage ref 或 host-path-shaped canary
- **THEN**普通 Viewer、状态文案和日志不显示原值，并使用稳定安全 error/state 表达失败

#### Scenario: 人工失败定位
- **WHEN**用户从 Evaluation leaf 打开一条合法 evidence
- **THEN**UI 将其描述为可审阅证据和人工定位材料，不从内容自动推导 root cause、Benchmark outcome 或统计结论

#### Scenario: no-device 审阅
- **WHEN**持久 Report、inventory 和 managed artifacts 可用但没有设备、worker、plugin 或 model 配置
- **THEN**用户仍可完成 Report 到 Evidence Viewer 的受控审阅流程且没有运行副作用

