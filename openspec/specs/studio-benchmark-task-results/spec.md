# studio-benchmark-task-results Specification

## Purpose
定义 Benchmark TaskRun 结果、Evaluation Tree、正式报告、受控 artifact、可校验 bundle 与 partial/terminal reporting 的事实边界。
## Requirements
### Requirement: TaskRun result 必须保留三类独立事实
TaskRun result DTO SHALL 独立保留 service termination、Agent `RunStatus` 与 Benchmark
`PASS/FAIL/INVALID/SKIPPED`，并包含 AgentGraph、BenchmarkPlan、ExperimentProtocol、
TaskInstance 和 Agent revision identities。任何一类状态 MUST NOT 被另一类推导或覆盖。

#### Scenario: Agent SUCCESS、Benchmark FAIL
- **WHEN**Agent 正常结束但 Evaluator Tree 判定任务未完成
- **THEN**TaskRun 同时显示 Agent SUCCESS 和 Benchmark FAIL，service 可正常 completed

#### Scenario: initializer infrastructure failure
- **WHEN**Protocol 将 initializer failure 归类为 INVALID
- **THEN**TaskRun 保留未运行 Agent 的 availability 和 Benchmark INVALID，不伪造 Agent failure

### Requirement: Benchmark phases 与 Evaluation Tree 必须完整投影
TaskRun detail SHALL 投影 Benchmark Core 的 materialization、reset、setup、
evaluator_pre、agent、evaluation 和 cleanup phase results，以及 Evaluation Result V2
树的节点类型、逻辑路径、状态、通过判断、分数、耗时、短路和 typed evidence。
Studio MUST NOT 从最终布尔值重建或猜测叶子 evaluator。

#### Scenario: AND 中一个叶子失败
- **WHEN**后端报告包含通过与失败两个叶子
- **THEN**TaskRun detail 保留两个叶子、组合决策和各自 evidence

#### Scenario: 未执行 evaluation
- **WHEN**initializer failure 按策略跳过 Agent/evaluation
- **THEN**phase 状态明确为 skipped/not_run，不缺省成 success

### Requirement: Result 与 evidence availability 必须是一等事实
TaskRun/Experiment resource SHALL 分别表达 result、evaluation、report、trajectory、
bundle、Replay 和每个 artifact 的 `pending`、`available`、`not_produced`、`excluded`、
`missing`、`corrupt` 或 `failed` 等适用 availability。系统 MUST NOT 用空对象、旧截图
或临时计数掩盖缺失和失败。

#### Scenario: Replay publication 失败
- **WHEN**TaskResult 已持久化但 Replay finalization 失败
- **THEN**结果保持 available，Replay 标记 failed 并附安全 diagnostic

#### Scenario: Experiment 尚在运行
- **WHEN**客户端请求尚未 final 的 report
- **THEN**服务返回 pending 或明确标记的 partial summary，不把它声明为 final report

### Requirement: Experiment report 必须来自正式 Benchmark reporting
Report API SHALL 投影 Benchmark Core 生成的版本化 task/experiment reports，并保留
source report identity、schema、inputs、计数、分母、micro/macro、usage、timing 和
fairness warnings。Studio frontend MUST NOT 重新计算竞争性的 outcome、统计分母或
aggregation 作为新的事实源。

#### Scenario: PASS/FAIL 与 INVALID/SKIPPED 混合
- **WHEN**正式 report 使用不同统计分母处理四类 outcome
- **THEN**Studio 显示后端分母与 excluded counts，不把 INVALID/SKIPPED 计入错误的 pass rate

#### Scenario: 前端重新加载 report
- **WHEN**浏览器刷新同一 terminal Experiment
- **THEN**展示值来自相同 report identity，不根据当前 TaskRun 排序重新聚合

### Requirement: Paired comparison 必须保留公平性和样本限制
多 Agent report SHALL 显示正式 paired matching、matched count、wins/ties、effect
摘要、公平性 warnings 和 `significanceClaimed`。UI MUST NOT 把描述性小样本结果、
未配对 schedule 或 `significanceClaimed=false` 表述为统计显著性或通用模型优越性。

#### Scenario: 两个 repeats 的配对结果
- **WHEN**report 给出 matched count 2 且 `significanceClaimed=false`
- **THEN**UI 显示 wins/ties 与样本限制，不出现显著性结论

#### Scenario: TaskInstance 未跨 Agent 复用
- **WHEN**Protocol 明确关闭 reuse 并产生 fairness warning
- **THEN**comparison 显示不可默认配对的警告，不隐藏或自行修复匹配

### Requirement: Report 和 artifact HTTP 必须使用显式 resource link
Studio HTTP SHALL 提供 Experiment report、TaskRun detail、opaque artifact 和完整
bundle 的只读 resource link。客户端 MUST 从 Experiment/TaskRun response 读取 link，
不得根据文件名、output root、TaskRun ID 或标题构造宿主路径。未知或非法 identity
MUST 返回统一安全错误。既有 Experiment report、bundle、Experiment artifact 与
TaskRun artifact content routes SHALL 同时支持 GET 与 HEAD；HEAD MUST 调用与 GET
相同的 scoped managed resolver 和 read-time size/hash 校验，关闭已打开 stream，
返回与后续 GET 相同的 exact `Content-Type`、`Content-Length`、attachment
`Content-Disposition`、private no-store 与 nosniff 合同，但 MUST NOT 返回 body。
允许跨配置 Studio API origin 使用这些 links 时，CORS SHALL 允许 HEAD 并暴露
`Content-Disposition`，且 MUST NOT 暴露 storage reference 或宿主路径。

#### Scenario: 读取 available screenshot
- **WHEN**客户端跟随 TaskRun typed evidence 中的 artifact link
- **THEN**resolver 返回正确 content type/hash 对应内容，不暴露存储路径

#### Scenario: 猜测 report 文件路径
- **WHEN**浏览器提交任意绝对路径或 `../` 读取 report
- **THEN**服务拒绝请求，不泄露路径是否存在

#### Scenario: HEAD 准备合法 artifact
- **WHEN**客户端对后端给出的 exact scoped report、bundle 或 artifact link 发起 HEAD
- **THEN**服务执行相同 scope、availability、size 和 hash 校验，返回无 body 的 exact 下载 headers

#### Scenario: HEAD 发现内容已损坏
- **WHEN**descriptor 提交后 managed 文件缺失、大小变化或 SHA-256 不匹配
- **THEN**HEAD 不返回内容，resolver 将权威 availability 收口为 missing 或 corrupt，后续 inventory 不再给出可读 link

#### Scenario: HEAD 跨 scope
- **WHEN**客户端把 Experiment A 的 artifact identity 用于 Experiment B 或其他 TaskRun 的 URL
- **THEN**HEAD 与 GET 一样安全失败且不泄露该 artifact 是否存在

#### Scenario: 浏览器读取下载响应头
- **WHEN**前端使用配置的跨 origin Studio API 准备 report、trajectory 或 bundle
- **THEN**CORS preflight/response 允许 HEAD 并让客户端读取 content disposition、type 和 length，而不暴露内部存储 metadata

### Requirement: Managed artifact 必须 scoped、可验证且安全
每个 artifact SHALL 使用 Experiment/TaskRun-scoped opaque identity，并记录 content
type、size、hash、schema/provenance 和 availability。Resolver MUST 拒绝 path
traversal、absolute path、symlink escape、目录、未知 content type、跨 Experiment
引用和 integrity mismatch。大型内容 MUST 保存在 managed artifact store，repository
和 event 只保存有界 descriptor。

#### Scenario: 跨 Experiment artifact identity
- **WHEN**客户端在 Experiment A URL 使用只属于 Experiment B 的 artifact identity
- **THEN**resolver 不返回内容或 metadata，也不泄露其存在

#### Scenario: hash 不匹配
- **WHEN**artifact 内容与已提交 digest 不一致
- **THEN**读取失败并标记 corrupt，错误响应不返回损坏内容

### Requirement: 敏感 evidence 必须沿用统一 capture/export 策略
TaskRun events、reports、artifact metadata、Replay 和 bundle MUST NOT 保存或返回 raw
API key、token、password、authorization header、raw device serial、未经批准的宿主
绝对路径或 live object。完整模型响应在已捕获且通过安全处理时 MAY 作为受控 artifact
读取；完整 Prompt SHALL 按既有策略持久化为 hidden evidence，普通 API/Inspector/
export MUST NOT 返回其内容。

#### Scenario: 默认导出包含 hidden Prompt 的 Experiment
- **WHEN**用户下载完整 Experiment bundle
- **THEN**bundle 排除 Prompt 内容并在 manifest 记录 excluded，不从日志或 report 间接泄漏

#### Scenario: 多层 payload 包含安全 canary
- **WHEN**Runtime result/evidence 包含 secret、raw serial、绝对路径和 live client
- **THEN**SQLite、artifact、HTTP、SSE、Replay 和 export 均找不到原值，并保留 redaction/rejection fact

### Requirement: Experiment bundle 必须版本化且可校验
Terminal Experiment SHALL 能导出版本化 bundle，包含 manifest、definition snapshot、
TaskRun results、Experiment report、trajectory 和允许导出的 artifacts，并为每个成员
记录安全相对路径、size 与 hash。Bundle MUST 可由公共 verifier 校验，且不包含数据库、
宿主路径或未授权敏感内容。

#### Scenario: 下载完整 terminal bundle
- **WHEN**Experiment result/report finalization 成功
- **THEN**bundle verifier 确认 manifest、成员 hash、identities 和允许的 evidence 完整

#### Scenario: bundle 成员被修改
- **WHEN**下载后一个 report/artifact 内容被篡改
- **THEN**verifier 报告具体 integrity failure，不把 bundle 标记为有效

### Requirement: 运行中只能显示明确的 partial facts
Experiment monitor MAY 展示已经持久化的 completed TaskRun counts、正式 outcomes 和
phase evidence，但 MUST 将其标记为 partial，并同时显示 planned/completed/terminal
数量与 journal high-water mark。它 MUST NOT 提前生成最终 paired comparison、Wilson
interval 或 final report identity。

#### Scenario: 多 Task Experiment 完成一项
- **WHEN**一个 planned TaskRun terminal 而其他仍 scheduled/running
- **THEN**monitor 显示该 TaskRun 正式结果和 Experiment partial 标记，不显示 final report

#### Scenario: partial 后 Experiment interrupted
- **WHEN**后续服务重启使 Experiment interrupted
- **THEN**已完成 TaskRun 保留，未完成项与 final report availability 真实标记

### Requirement: Reporting route 必须展示 loading、partial、terminal 与失败状态
Studio SHALL 以 `/experiments/:experimentId/report` 展示正式 report resource，并对
loading、pending/partial、terminal available、not found、integrity failure 和 retryable
publication failure 提供可区分状态。深浅主题和 presentation MUST NOT 改变统计事实或
canonical identity。

#### Scenario: report 仍在 finalizing
- **WHEN**用户直接打开 terminal 前的 report URL
- **THEN**页面显示 pending/partial 与当前 lifecycle，不渲染 mock chart

#### Scenario: 切换主题
- **WHEN**用户在 report 页面切换深浅主题
- **THEN**所有 result、warning、sample count 与 identity 保持不变

### Requirement: Stage 5.2B 必须持久化有界 TaskRun result projection
Worker SHALL 将正式 `BenchmarkTaskResult` 投影为 versioned、database-neutral、可查询的
Studio TaskRun result。Projection MUST 包含 planned/Core/AgentGraph/Agent revision/
BenchmarkPlan/ExperimentProtocol/TaskInstance identities、service termination、
Benchmark phases、可选 Agent `RunStatus`、可选 Benchmark outcome、Evaluation Tree
摘要、usage、公平性 warning 和安全 diagnostics。它 MUST 使用统一 sanitizer、显式
depth/item/string/serialized-size limits，并 MUST NOT 在 SQLite 中保存 live objects、
raw serial、secret、宿主路径或重复的完整 runtime event history。

#### Scenario: Agent SUCCESS 与 Benchmark FAIL
- **WHEN**Core 返回 Agent SUCCESS、Evaluation false 和 Benchmark FAIL
- **THEN**TaskRun GET 从持久 result 同时返回两类事实，刷新后不重新计算或覆盖

#### Scenario: 大型嵌套 evidence
- **WHEN**Core result 包含超过 inline 限制的 collection、文本或 event history
- **THEN**SQLite 只保存有界 typed summary/truncation diagnostic，大型内容不进入 result JSON

#### Scenario: 安全 canary
- **WHEN**result/evidence 嵌套包含 token、raw serial、绝对路径和 live client
- **THEN**持久 result 与 HTTP payload 找不到原值并保留 redacted/rejected/truncated 事实

### Requirement: TaskInstance、phase、Agent 与 outcome availability 必须独立提交
TaskRun SHALL 独立表达 TaskInstance、phase results、Agent status、Benchmark outcome、
result、evaluation 和 Replay availability。Worker MUST 在事实产生时使用
`pending`、`available`、`not_produced` 或 `failed` 等明确状态；它 MUST NOT 从 service
lifecycle 推导 Agent status/outcome，也 MUST NOT 在 Stage 5.2B 把尚未注册的 Replay、
report、trajectory 或 bundle 标记 available。

#### Scenario: materialization 失败
- **WHEN**Core 不能产生正式 TaskInstance
- **THEN**TaskInstance availability 为 failed 或 not_produced，Agent status 为 not_produced，并保留 Core 决定的正式 INVALID（若产生）

#### Scenario: accepted 阶段取消
- **WHEN**TaskRun 在 worker claim 前被 cancelled_before_start
- **THEN**Agent、TaskInstance、evaluation 和 Benchmark outcome 均为 not_produced，不伪造 SKIPPED

#### Scenario: result 已提交但 Replay 未发布
- **WHEN**Stage 5.2B terminal TaskRun 已有 available result
- **THEN**Replay/report/bundle availability 仍真实为 pending 或 not_produced，且没有失效 resource link

### Requirement: Result commit 必须抵抗终态和 cancellation 竞争
Repository SHALL 在一个 transaction/CAS boundary 内提交 TaskRun 的最后 phase、
bounded result、Agent status、Benchmark outcome、availability、terminal lifecycle 和
对应 result/TaskRun journal facts，或者保持上一个已提交状态。Cancel 或旧 worker MUST
NOT 用 cancelled/failed 空结果覆盖已经提交的 PASS、FAIL 或 INVALID。

#### Scenario: evaluation 后 cancel
- **WHEN**正式 FAIL result 已提交且 cancellation 在 cleanup/finalization 到达
- **THEN**FAIL 与 evaluation 保持 available，cancel 只影响允许的 service terminal facts

#### Scenario: result transaction 注入失败
- **WHEN**写入 outcome 后、terminal lifecycle/event 前发生 storage failure
- **THEN**整个 result transaction 回滚，不暴露 outcome available 与缺失 result 的矛盾组合

#### Scenario: terminal 后重复 worker finalization
- **WHEN**迟到 callback 再次提交不同 terminal result
- **THEN**repository 拒绝改写并返回当前 immutable TaskRun fact

### Requirement: Stage 5.2B evidence namespace 必须受控但不冒充 publication
Worker SHALL 在设备副作用前分配 Experiment/TaskRun-scoped 的私有受控 evidence
namespace，并验证可写性和容量。Core/Agent 运行产生的允许 evidence MUST 保留在该
namespace，不得使用自动清理的临时目录；Stage 5.2B 只在 result 中保存安全逻辑引用
或 availability，不得公开宿主路径或声称 5.2C managed artifact、report、bundle 或
Replay publication 已完成。

#### Scenario: 浏览器关闭
- **WHEN**运行中或 terminal Experiment 的浏览器页面关闭
- **THEN**SQLite result 与已有受控 evidence 不被删除，worker 生命周期不受连接影响

#### Scenario: Core 默认 report finalizer 被延后
- **WHEN**Studio 以 defer-publication 模式调用 Benchmark Runtime
- **THEN**TaskResult 仍可持久化，但 Experiment report/bundle/Replay 不被生成公开 link 或标记 available

### Requirement: Stage 5.2C-2 必须从完整 Core 结果准备正式 publication
Studio Benchmark execution SHALL 在完整 `BenchmarkSuiteResult` 仍可用时调用现有
Benchmark Core reporting boundary，将版本化 task/experiment report、trajectory、
result 和 manifest 写入 Experiment 私有受控 staging。准备失败 MUST 作为独立
publication diagnostic 持久化，且 MUST NOT 阻止或改写有界 TaskResult 的事务提交。
Studio MUST NOT 从有界 HTTP DTO、TaskRun 排序或前端状态重新计算竞争性的正式报告。

#### Scenario: 完整 Core result 成功准备
- **WHEN**Benchmark Runtime 返回包含完整 TaskRun、Agent 和 Evaluation 事实的 SuiteResult
- **THEN**Studio 从该 SuiteResult 准备版本化正式 publication 输入，后续 managed publication 不重新计算统计事实

#### Scenario: report staging 写入失败
- **WHEN**Core 执行已产生正式 TaskResult但私有 report staging 写入失败
- **THEN**TaskResult 仍原子提交为 available，report/trajectory/bundle 标记 failed 并记录安全 diagnostic

#### Scenario: publication 重试
- **WHEN**相同 Experiment/TaskRun identity 的 publication 在 staging 已验证后重复执行
- **THEN**服务返回相同 report、artifact、bundle 和 Replay identities，不生成竞争性正式结果

### Requirement: Stage 5.2C-2 publication 必须按组件独立收口
Experiment finalizer SHALL 分别提交 report、trajectory、bundle、managed artifact 和
Replay availability，并保留不可变 TaskResult。一个 publication 组件的失败 MUST NOT
覆盖其他已经提交的 available 组件、Agent status、Benchmark outcome 或 Evaluation；
每个失败 MUST 使用有界安全 diagnostic 表达，并允许后续 5.2C-3 仅重试 publication。

#### Scenario: Replay 失败但 report 成功
- **WHEN**正式 report、trajectory 和 bundle 已发布，而 Replay metadata commit 失败
- **THEN**report/trajectory/bundle 保持 available、TaskResult 保持不变，Replay 标记 failed 且 History 不出现半成品

#### Scenario: artifact integrity 失败
- **WHEN**一个准备发布的 runtime artifact 与声明 digest 不一致
- **THEN**该 artifact 标记 corrupt 且内容不可下载，其他已验证 publication facts 可继续提交

#### Scenario: 启动前取消
- **WHEN**TaskRun 在 Agent、Benchmark outcome 和可验证运行前缀产生前取消
- **THEN**TaskResult 与 Replay 保持 not_produced，系统不发布空成功 trajectory 或 Replay

### Requirement: Managed Experiment bundle 必须使用正式与受控证据
Stage 5.2C-2 SHALL 生成版本化 Experiment bundle，包含不可变 definition snapshot、
正式 Core reports、TaskRun results、trajectory、publication manifest 和策略允许的
managed artifacts。Manifest MUST 为每个成员记录安全相对路径、content type、size、
digest、scope、availability 和排除原因；bundle verifier MUST 能在不访问 SQLite、
私有 evidence root 或宿主路径的条件下验证完整性。

#### Scenario: 下载 terminal Experiment bundle
- **WHEN**terminal Experiment 的正式 publication 成功
- **THEN**typed bundle link 返回可由公共 verifier 验证的 bundle，成员 identities 与 Experiment/TaskRun scope 一致

#### Scenario: 默认 bundle 包含 hidden Prompt metadata
- **WHEN**受控 evidence inventory 声明 hidden Prompt
- **THEN**bundle manifest 记录 excluded/hidden fact 但不包含 Prompt 内容或可读取 artifact identity

#### Scenario: bundle 成员被篡改
- **WHEN**下载后的任一成员内容与 manifest digest 不一致
- **THEN**verifier 返回具体 integrity failure，不把 bundle 标记为有效

### Requirement: Finalizing recovery 必须只使用已提交执行事实
Startup recovery SHALL 将 `finalizing` Experiment 分为 immutable TaskResult
publication-only、publication-already-committed 和 no-result finalize-only 三类。
Recovery MUST NOT 从 bounded DTO 重新计算正式结果，不得重新调用 Benchmark Runtime、
Agent 或设备。只有 publication metadata 尚未提交且其输入 identity 可由已提交
TaskResult 与受控 staging 验证时，系统 SHALL 调用 Stage 5.2C-2 idempotent publisher；
已经提交的 partial/failed publication SHALL 作为不可变 publication attempt 保留，
不得由 startup recovery 覆盖或升级。

#### Scenario: TaskResult 已提交但 publication 未提交
- **WHEN** recovery 读取到 immutable TaskResult、可验证 staging 和缺失的 coordinated publication record
- **THEN** 系统使用原 publication identity 调用 publisher 一次，并保持 Agent status、Benchmark outcome 与 Evaluation 不变

#### Scenario: publication transaction 已提交
- **WHEN** recovery 发现 publication metadata 已存在但 Experiment 尚未 terminal
- **THEN** 系统不再发布 artifact、report、bundle 或 Replay，只依据既有 availability 完成 Experiment finalization

#### Scenario: 已提交 partial 或 failed publication
- **WHEN** coordinated publication record 已提交且一个或多个 component 为 partial、failed 或 corrupt
- **THEN** recovery 保留该 attempt 与 diagnostic 并 finalize，不覆盖 component、不生成竞争性 identity

#### Scenario: staging 缺失或验证失败
- **WHEN** publication record 尚未提交但受控 staging 缺失、损坏或 identity 不匹配
- **THEN** idempotent publisher 提交有界 failed availability/diagnostic，TaskResult 保持不可变且 Experiment 可以真实收口

#### Scenario: finalizing 没有 TaskResult
- **WHEN** TaskRun 已因 preflight、cancel 或 interruption 终止且 result availability 为 not_produced 或 failed
- **THEN** recovery 使用 TaskRun service terminal reason 完成 failed、cancelled 或 interrupted Experiment，不构造 Benchmark outcome、report、bundle 或 Replay

#### Scenario: cancellation facts 已提交
- **WHEN** finalizing recovery 读取到 cancellation request 与已经提交的 PASS、FAIL 或 INVALID TaskResult
- **THEN** 系统保留两类事实并按既有 terminal reason contract 收口，不用取消覆盖 result

### Requirement: Publication-only recovery 必须跨崩溃保持幂等
Publication-only recovery SHALL 使用稳定 Experiment、TaskRun、result fingerprint、
journal high-water 和 artifact inventory identity。Recovery decision、publication
metadata 与 Experiment terminal transition MAY 位于多个可恢复 transaction，但每个
边界 MUST 可由下一次 startup 判定，且重复启动 MUST NOT 创建第二个 report、artifact、
bundle、Replay mapping 或 Experiment terminal event。

#### Scenario: decision 后 publication 前崩溃
- **WHEN** recovery decision 已提交但 publisher 尚未提交时进程退出
- **THEN** 下一次 startup 可重新领取 finalizing work 并以同一 immutable input 重试 publisher

#### Scenario: publication 后 terminal 前崩溃
- **WHEN** coordinated publication 已提交但 Experiment finalization 尚未提交时进程退出
- **THEN** 下一次 startup 检测既有 publication，只提交缺失的 finalization

#### Scenario: 重复 composition startup
- **WHEN** 同一数据库连续构造可执行 composition
- **THEN** 已完成 publication 与 terminal TaskResult identities 保持不变，publisher 和 execution adapter 不被再次调用

### Requirement: TaskResult 必须独立保存安全执行证据来源
Studio TaskResult SHALL 使用有界 typed facts 分别保存 evidence acquisition 和 source
execution environment。Acquisition MUST 区分 fresh execution、Replay projection、
explicit import 与 contract fixture；environment MUST 区分 real Android、fake device
与 unverified。Projection MUST 保留 Core device preflight 的安全 check outcomes，但
MUST NOT 保存 raw serial、private binding fingerprint、ADB 参数、配置路径或 live handle。
Profile configured、preview success、Agent SUCCESS、Benchmark PASS 或截图存在均 MUST NOT
单独推导 `real_android`。

#### Scenario: fake fixture 产生 PASS
- **WHEN**fake-device contract execution 返回 Agent SUCCESS 和 Benchmark PASS
- **THEN**TaskResult 标记 contract-fixture acquisition 与 fake-device environment，且 real-device evidence 仍为 false

#### Scenario: exact target context preflight 失败
- **WHEN**Core 对 exact target 返回 locale、orientation、platform 或 required-App mismatch
- **THEN**TaskResult 保留安全 check outcomes 和 INVALID，同时不泄露 target identity

#### Scenario: 只有 profile configuration
- **WHEN**Experiment 尚未产生正式 TaskResult
- **THEN**resource 不根据 selected profile 补造 execution provenance 或 real-device evidence

