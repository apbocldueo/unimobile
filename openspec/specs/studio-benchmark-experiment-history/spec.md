# studio-benchmark-experiment-history Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-history-5-4d1. Update Purpose after archive.
## Requirements
### Requirement: Experiment History 必须拥有独立且可重建的 Benchmark route
Studio frontend SHALL 在 exact `/experiments` route 提供 Benchmark Experiment
History，并 SHALL 保留 `/history` 作为普通 Studio Run/Replay history。History
filter、page limit 和 opaque cursor SHALL 由 URL 与 entity query 拥有；页面刷新
或直接打开 deep link MUST NOT 依赖 Zustand、Monitor SSE session 或先前页面访问。

#### Scenario: 刷新筛选后的 History URL
- **WHEN**用户在 `/experiments` 应用 lifecycle、Benchmark、Agent 或时间筛选后刷新页面
- **THEN**页面从 URL 重建同一 backend history query，而不是只过滤缓存中的当前页

#### Scenario: Benchmark History 与 Run History 分离
- **WHEN**用户打开 `/experiments` 或 `/history`
- **THEN**前者只展示 durable Benchmark Experiments，后者继续展示普通 persisted Run/Replays，二者不混用 resource identity 或筛选状态

#### Scenario: 非法 History URL
- **WHEN**URL 含重复、未知或非法 filter/time/cursor value
- **THEN**页面显示安全的 invalid-query state 和 reset action，不静默纠正为不同查询

### Requirement: Filter 控件必须提交精确后端查询并重置 cursor
History SHALL 支持全部或单一 lifecycle、exact `catalogEntryId`、exact `agentId`
及 accepted half-open time range。Apply、Clear 或改变任一 filter SHALL 删除当前
cursor；TanStack Query identity SHALL 包含规范化 filter、limit 和 cursor。
Current Catalog/Agent list MAY 提供 label 或 autocomplete，但 MUST NOT 成为读取
历史结果的依赖，也 MUST NOT 覆盖 durable identity。

#### Scenario: 改变筛选后重置翻页位置
- **WHEN**用户在后续 cursor page 改变或清除任一 filter
- **THEN**页面删除 cursor、从新 query 的第一页请求，并使用包含新 filter 的独立 cache key

#### Scenario: 当前 Catalog 或 Agent 不存在
- **WHEN**history item 引用的 Catalog Package 或 Agent 已不在当前 registry/autocomplete 中
- **THEN**页面仍显示 durable ID、允许 exact filter，并且 suggestion query 的失败不隐藏或改写 history item

#### Scenario: exact filter 返回空集合
- **WHEN**backend 对合法 filter 返回零个 item
- **THEN**页面显示“当前筛选无结果”的空状态并保留 filter/reset，不把它描述为没有任何历史 Experiment

### Requirement: Keyset navigation 必须保持 opaque cursor 和 truthful page state
History SHALL 跟随 backend `nextCursor` 进行 forward pagination，不解析、改写或从
page number 推导 cursor。Next navigation SHALL push 可重建 URL；客户端 MUST NOT
在没有权威 reverse boundary 时伪造 previous cursor、总页数或 total count。

#### Scenario: 进入下一页并使用浏览器返回
- **WHEN**backend 返回 `nextCursor` 且用户选择下一页
- **THEN**页面将 opaque cursor 写入新 URL 并请求对应 query，浏览器 Back 可返回上一 URL

#### Scenario: 直接打开后续 cursor
- **WHEN**用户直接打开带有效 cursor 的 deep link
- **THEN**页面加载该 backend page，但不声称知道不存在于合同中的页码、总数或 previous cursor

#### Scenario: 后续页请求失败
- **WHEN**新 cursor page 返回 validation、storage 或 network error
- **THEN**页面保留当前 URL/filter、显示安全 retry/reset，并不回退为前一页数据冒充成功结果

### Requirement: History summary 必须保持 durable facts 和独立 availability
每个 History item SHALL 展示 Experiment identity、current service lifecycle 与
terminal reason、immutable Catalog/Package/split、Agent/revision、accepted/
updated/terminal timestamps、planned TaskRun count，以及 outcome、report、Replay、
trajectory、bundle 的独立 availability。页面 MUST NOT 从当前 Catalog title、
Agent name、颜色、单个 component failure 或前端计算替换这些持久事实。

#### Scenario: 部分 publication component 失败
- **WHEN**report、Replay、trajectory 或 bundle 中只有部分 component available
- **THEN**History 分别展示每个 availability，单项失败不把 Experiment 或其他 component 合并成一个通用失败状态

#### Scenario: lifecycle、Agent status 与 Benchmark outcome 不同
- **WHEN**History summary 的 service lifecycle、outcome availability 和 terminal reason 表示不同事实轴
- **THEN**页面分别标注这些事实，不把 service terminal、Agent success 或 Benchmark pass 互相推导

#### Scenario: 时间显示
- **WHEN**页面格式化 accepted/updated/terminal epoch milliseconds
- **THEN**它保留原始排序与筛选值并明确使用浏览器 locale/timezone，不把缺失 terminal time 显示为零或当前时间

### Requirement: History handoff 必须只使用权威 resource links
Monitor action SHALL 使用 strict history `links.self`。Report action SHALL 只在
`reportAvailability=available` 且 strict parser 接受 exact `links.report` 时显示。
Aggregate `replayAvailability` SHALL 只作为事实展示；History MUST NOT 根据
Experiment、TaskRun 或 Replay identity 构造 Replay URL。Artifact viewer、bundle
download 和 export action MUST NOT 在本 Change 中提前实现。

#### Scenario: 返回 Monitor
- **WHEN**用户选择任一合法 History item 的 Monitor action
- **THEN**router 跟随该 item 的 exact same-service `links.self` 打开 durable Experiment Monitor

#### Scenario: Report 不可用
- **WHEN**report availability 不是 `available` 或 strict history item 没有 report link
- **THEN**页面不提供可点击 Report action，但继续展示 availability 和 Monitor

#### Scenario: Replay available 但没有 TaskRun handoff
- **WHEN**Experiment summary 声明 aggregate Replay available
- **THEN**History 只显示 Replay availability，并要求在 Monitor/Report 选择具体 TaskRun 后跟随 `taskRun.links.replay`

#### Scenario: safe-looking 但错误作用域的 link
- **WHEN**History payload 含另一个 Experiment 的 self/report link
- **THEN**entity parser 拒绝 payload，页面不导航或根据 identity 修补 URL

### Requirement: History 页面必须有独立且可恢复的请求状态
History SHALL 分别处理 initial loading、page transition、invalid query、network/
storage failure、unfiltered empty 和 filtered empty。Retry SHALL 重发当前 URL 对应
query；metadata request MUST NOT 启动 worker、连接设备或读取 artifact bytes。

#### Scenario: 首次加载失败后重试
- **WHEN**初始 History metadata query 失败且用户选择 retry
- **THEN**页面重发同一 filter/cursor query，不创建设备 session、Experiment 或 Monitor event connection

#### Scenario: 无筛选且没有 Experiment
- **WHEN**backend 对无筛选第一页返回空集合
- **THEN**页面显示尚无 durable Benchmark Experiment，并提供 Catalog/Composer 入口而不是 mock row

#### Scenario: page transition 保留布局但不冒充完成
- **WHEN**用户进入下一 cursor 且请求尚未完成
- **THEN**页面 MAY 保留上一页布局以避免抖动，但 MUST 标识 loading 并禁止把旧 item 计为新页结果

