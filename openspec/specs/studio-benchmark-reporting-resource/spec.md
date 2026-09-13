# studio-benchmark-reporting-resource Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-reporting-resource-5-4a. Update Purpose after archive.
## Requirements
### Requirement: Experiment history 必须是有界稳定的持久资源
Studio SHALL 提供只读的 Benchmark Experiment history page，使用
`(acceptedAt DESC, experimentId DESC)` 的确定性顺序和 opaque continuation
cursor。服务 SHALL 对完整持久 history 支持可选的单 lifecycle、exact
`catalogEntryId`、exact scheduled `agentId`、inclusive `acceptedFrom` 和
exclusive `acceptedBefore` 筛选；筛选 SHALL 在 keyset pagination 之前由
repository 执行，而不是由客户端过滤当前页。每个 summary SHALL 只投影持久的
Experiment identity、service lifecycle、terminal reason、Catalog/Package/split
identity、Agent/revision identities、planned TaskRun count、component
availability、timestamps 和已经实现的 resource links；它 MUST NOT 返回完整
AgentGraph、BenchmarkPlan、Protocol、设备绑定或当前 Catalog 推断出的可变标题。

所有新 continuation cursor SHALL 绑定规范化 filter identity 与 exclusive
boundary。旧版无筛选 cursor MAY 继续用于无筛选 query，但 MUST NOT 用于任一筛选
query。Lifecycle filter 表示每次请求时的 current durable lifecycle，不构成跨请求
历史快照；Catalog、scheduled Agent membership 与 accepted time 筛选 SHALL 来自
immutable snapshot/schedule facts。

#### Scenario: 多页读取时存在相同 acceptedAt
- **WHEN**多个 Experiment 具有相同 `acceptedAt` 且客户端以同一筛选连续读取多个 history page
- **THEN**服务以 `experimentId` 作为稳定 tie-breaker，所有匹配条目最多返回一次且不会因 timestamp tie 跳过

#### Scenario: 新 Experiment 在翻页期间创建
- **WHEN**客户端读取第一页后又有更新的 Experiment 被创建
- **THEN**既有 cursor 继续从原 exclusive boundary 向旧记录翻页，不重复第一页条目

#### Scenario: 单项和组合筛选作用于全部历史
- **WHEN**客户端提交 lifecycle、`catalogEntryId`、scheduled `agentId` 或 accepted time range 的任意合法组合
- **THEN**repository 在分页前对全部 durable Experiment 执行 AND 语义精确筛选，并保持相同 newest-first order

#### Scenario: accepted time 使用半开区间
- **WHEN**客户端提交 `acceptedFrom=A` 与 `acceptedBefore=B`
- **THEN**服务只返回满足 `A <= acceptedAt < B` 的 Experiment，并拒绝不安全整数、负值或 `A >= B`

#### Scenario: 非法 filter query
- **WHEN**客户端提交 unknown、重复、空 filter、未知 lifecycle、非法 identity 或非法时间
- **THEN**服务返回稳定 validation error，且不执行宽松匹配、当前页过滤或部分 query

#### Scenario: filter-bound cursor 被跨查询复用
- **WHEN**客户端在签发 cursor 后改变任一 filter，或把 filtered cursor 用于另一组 filter
- **THEN**服务拒绝 cursor/query identity 冲突，不返回另一筛选集合的数据

#### Scenario: 旧无筛选 cursor 兼容
- **WHEN**客户端将既有版本的有效 history cursor 用于无筛选 list
- **THEN**服务继续从原 exclusive boundary 返回条目；若同一 cursor 与任一 filter 同时提交则拒绝

#### Scenario: 非法 cursor 或 limit
- **WHEN**客户端提交损坏、越界或不受支持版本的 cursor，或提交不在 1 到 100 内的 limit
- **THEN**服务返回稳定 validation error，且不泄露 SQL、数据库路径、filter fingerprint 或邻近 identity

#### Scenario: lifecycle 在翻页期间改变
- **WHEN**一个既有 Experiment 在两次 lifecycle-filtered page 请求之间转换 lifecycle
- **THEN**后续请求依据当前 durable lifecycle 评估 membership，服务和客户端均不把 cursor 描述为历史 snapshot

#### Scenario: history summary 不依赖当前 Catalog
- **WHEN**原 Benchmark Package 或 Agent registry entry 已移动、删除或更名
- **THEN**history 仍从不可变 Experiment snapshot/schedule 返回原 Catalog/Package/Agent identities，而不读取当前 registry 补写历史事实

#### Scenario: filtered history 仍是 metadata-only
- **WHEN**客户端读取任一筛选的 history page
- **THEN**服务不连接设备、不构造 plugin/model、不读取 artifact body，也不改变 Experiment 或 publication availability

### Requirement: Experiment artifact inventory 必须分页且只暴露安全 metadata
Studio SHALL 提供 Experiment-scoped artifact inventory page，使用稳定
`artifactId ASC` 顺序、1 到 100 的 bounded limit 和绑定该 Experiment 的 opaque
cursor。Inventory SHALL 从 managed publication metadata 投影 kind、availability、
Experiment/TaskRun scope、content type、size、hash、provenance、causal identity 与
显式 content link；它 MUST NOT 返回 storage reference、宿主路径、bundle member
路径或 artifact body。

#### Scenario: 可读 artifact
- **WHEN**一个 artifact 的 availability 为 `available`、`redacted` 或 `truncated` 且 metadata 完整
- **THEN**inventory 返回校验后的 content type、size、hash 和当前 Experiment 作用域内的 opaque content link

#### Scenario: 不可读 artifact
- **WHEN**artifact 为 `pending`、`not_produced`、`excluded`、`missing`、`corrupt` 或 `failed`
- **THEN**inventory 保留其 availability 与安全 metadata，但不返回可跟随的 content link

#### Scenario: hidden artifact
- **WHEN**Experiment metadata 包含一个或多个 `hidden` artifact
- **THEN**普通 inventory 不返回其 artifact identity、causal identity 或 content link，只返回不含 identity 的 aggregate hidden count

#### Scenario: 跨 Experiment cursor 或 artifact
- **WHEN**客户端把 Experiment A 的 inventory cursor 或 artifact identity 用于 Experiment B
- **THEN**服务拒绝请求或返回 scoped not-found，且不泄露该 cursor 或 artifact 是否属于其他 Experiment

#### Scenario: metadata-only inventory
- **WHEN**客户端分页读取 artifact inventory
- **THEN**repository 只读取已提交 descriptor metadata，不打开、校验或反序列化任何 artifact body

### Requirement: Resource link 必须与 scope 和 availability 一致
History、Experiment detail 和 artifact inventory 中的 reporting link SHALL 是
same-service safe path，并与对应 Experiment、TaskRun、artifact identity 以及
availability 一致。客户端 MUST 跟随返回的 link；它 MUST NOT 从 Core
`report_ref`、`trajectory_ref`、artifact kind、文件名或宿主目录构造内容 URL。

#### Scenario: report 尚不可用
- **WHEN**Experiment report availability 不是 `available`
- **THEN**history/detail resource 不返回 report link

#### Scenario: integrity closure 后重新查询
- **WHEN**一次 artifact read 将 report 从 available 闭合为 missing 或 corrupt
- **THEN**后续 resource 与 inventory 查询保留失败事实并移除该 artifact 的可读 link

#### Scenario: safe 但错误的 link
- **WHEN**payload 中的 link 是 `/studio/` 路径但嵌入了不同 Experiment、TaskRun 或 artifact identity
- **THEN**严格客户端 parser 拒绝整个 resource，而不是跟随该 link

### Requirement: Experiment report 必须作为严格的 Core 文档消费
Studio frontend SHALL 以有界 loader 和 strict versioned parser 消费现有
`benchmark_experiment_report` schema `1.0` 文档。Parser SHALL 将 Core
`snake_case` 适配为内部 typed model，并验证 Experiment scope、exact outcome
counts、run summaries、Agent metrics、comparisons、fairness warnings 与
`significance_claimed`；它 MUST NOT 重算或替换正式 outcome、micro/macro、
Wilson interval、paired matching、aggregation 或 significance。

#### Scenario: 支持的正式 report
- **WHEN**客户端通过 available report link 读取 schema `1.0` 且 kind 为 `benchmark_experiment_report` 的有界文档
- **THEN**客户端返回 typed Experiment report，并保留 Core 提供的全部 counts、denominators、metrics、comparison 和 warning facts

#### Scenario: 不支持的版本或 kind
- **WHEN**report 使用未知 schema version、错误 kind 或未知顶层字段
- **THEN**parser 返回明确 compatibility/validation failure，不静默忽略字段或展示部分统计

#### Scenario: outcome denominator 冲突
- **WHEN**Agent metric 的 `eligible_count` 不等于该 Agent 的 PASS 加 FAIL，或 outcome count 为负数或非整数
- **THEN**parser 拒绝 report，不把 INVALID/SKIPPED 合并到成功率分母

#### Scenario: rate 或 interval 越界
- **WHEN**success rate、Wilson bound 不在零到一之间，或 interval 下界大于上界
- **THEN**parser 拒绝 report，而不是 clamp、默认成零或重新计算替代值

#### Scenario: comparison cardinality 冲突
- **WHEN**comparison 的 matched count 不等于 left wins、right wins 与 ties 之和，或 Agent pair/数量非法
- **THEN**parser 拒绝 report；schema `1.0` 也不得接受没有声明方法却声称 significance 的文档

#### Scenario: 大型 report
- **WHEN**响应声明或实际超过 frontend 配置的 2 MiB report limit
- **THEN**loader 在解析前失败，不把大型 report 长期缓存到浏览器状态

### Requirement: TaskRun report 与 Evaluation Tree 必须严格且有界
Studio frontend SHALL 通过 Experiment inventory 中 `task_report` 的显式 content
link 读取 `benchmark_run_report` schema `1.0`。Parser SHALL 保留 Core run identity、
Agent/task/repeat/outcome、canonical identities、stages、usage 与完整 Evaluation
Tree 节点事实，并 SHALL 对递归深度、总节点数、数组成员和文本大小实施显式界限。
Experiment report 的 `task_run_id` 和 TaskRun report 的 `task_run_id` SHALL 被解释为
Core run identity，而 Studio TaskRun resource identity SHALL 保持独立并通过持久
`coreTaskRunId` 显式连接。Experiment report 的 `report_ref` MAY 只作为 safe causal
identity 与同一 Studio TaskRun scope 的 inventory item 匹配，MUST NOT 作为 URL 或
文件路径。安全导出的 Evaluation `token` SHALL 只接受 finite number、null 或精确的
`"<redacted>"` 表示，并 MUST NOT 用于推导 score、pass、outcome 或视觉状态。

#### Scenario: 选择一个 TaskRun report
- **WHEN**Experiment run summary 的 Core run identity 与 Studio TaskRun 的 `coreTaskRunId` 相同，且 safe `report_ref` 与同一 Experiment/Studio TaskRun inventory item 的 causal identity 匹配
- **THEN**客户端跟随 inventory content link 并解析对应 Core TaskRun report，同时保留两个独立 identity

#### Scenario: report reference 没有 inventory match
- **WHEN**run summary 声明 report reference 但 inventory 没有同 Experiment 和 Studio TaskRun scope 的可读 `task_report`
- **THEN**客户端显示明确 unavailable/inconsistent fact，不猜测 `runs/<id>/run-report.json` 的 HTTP 地址

#### Scenario: Studio 和 Core TaskRun identity 被混用
- **WHEN**客户端收到 Studio `task-run-...` resource identity 与裸 Core run identity
- **THEN**它只通过持久 `coreTaskRunId` 建立连接，不要求两者字符串相等也不把其中一个改写成另一个

#### Scenario: 安全导出的 token
- **WHEN**正式 TaskRun report 的 Evaluation node 将 token 表示为 `"<redacted>"`
- **THEN**parser 保留明确 redacted 状态，页面不拒绝 report、恢复原值或从 token 推导任何评估结论

#### Scenario: 非法 token 表示
- **WHEN**Evaluation token 是非有限数字、任意字符串、object 或 array
- **THEN**parser 拒绝该 report，不把未知值展示为 score 或安全 redaction

#### Scenario: Evaluation Tree 保留三态判断
- **WHEN**一个 Evaluation node 的 `is_pass` 为 `true`、`false` 或 `null`
- **THEN**typed model 保留原值和 status，不把 unavailable/not-run 判断转换为失败

#### Scenario: 递归结构超限
- **WHEN**Evaluation Tree 超过 32 层、2000 个节点或任一有界成员限制
- **THEN**parser 拒绝文档，不递归到浏览器资源耗尽或截断后冒充完整 evidence

#### Scenario: TaskRun scope 冲突
- **WHEN**task report 的 Experiment、Core run、Agent、task 或 repeat identity 与选中的 run summary 和 Studio TaskRun scope 不一致
- **THEN**客户端拒绝该 report，并且不展示其 Evaluation Tree 或 evidence

### Requirement: Artifact descriptor 必须使用完整 availability 合同
Frontend reporting entity SHALL 严格解析 managed Benchmark artifact availability
词汇，包括 `pending`、`not_produced`、`available`、`excluded`、`hidden`、
`missing`、`corrupt`、`failed`、`redacted` 和 `truncated`。Readable、unreadable
和 hidden metadata shape SHALL 与 backend managed artifact contract 一致；任意
未知 availability MUST 失败关闭。

#### Scenario: readable metadata 不完整
- **WHEN**available/redacted/truncated descriptor 缺少 content type 或 hash
- **THEN**parser 拒绝 descriptor，不生成 content link

#### Scenario: hidden descriptor 暴露 readable metadata
- **WHEN**hidden descriptor 同时携带 content type、非零 size、hash 或可读 link
- **THEN**backend projection 或 frontend parser 拒绝该 shape

#### Scenario: 未知 availability
- **WHEN**服务返回客户端未支持的 artifact availability
- **THEN**parser 返回 compatibility failure，而不是把它当作 available 或普通字符串

### Requirement: Reporting query 必须无运行副作用且可重建
History、inventory 和 report entity query SHALL 与 Benchmark worker、device
profile resolution、plugin/model construction、scheduler 和 Monitor event session
分离。Metadata query MUST NOT 触发 execution 或 artifact body read；report body
只在客户端显式跟随 available report/content link 时读取。所有 query SHALL 能从
route identity、resource link 和 opaque cursor 重建，不依赖 Zustand 草稿、内存
Experiment handle 或先前页面访问。

#### Scenario: 无设备配置读取 history
- **WHEN**服务拥有持久 Experiment metadata 但没有可用设备、plugin 或 model
- **THEN**history 和 inventory 仍可查询，且没有设备或 Runtime 调用

#### Scenario: 浏览器刷新后加载 report
- **WHEN**用户刷新未来的 `/experiments/:experimentId/report` 页面
- **THEN**entity queries 可从 Experiment identity 重新取得 detail、inventory 和正式 report，不依赖 5.3 Monitor 的 SSE session

#### Scenario: 仅列 metadata
- **WHEN**客户端只读取 history 或 inventory
- **THEN**服务不打开 report、trajectory、bundle 或 evidence 内容，也不改变其 integrity availability

