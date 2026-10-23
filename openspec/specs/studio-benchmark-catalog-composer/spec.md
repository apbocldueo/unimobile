# studio-benchmark-catalog-composer Specification

## Purpose
定义 Studio Benchmark Catalog、显式校验、Experiment Composer、不可变 Agent revision 绑定和无副作用 schedule preview 的规范合同。
## Requirements
### Requirement: Studio Benchmark Catalog 必须复用 metadata-only 后端事实源
Studio SHALL 通过版本化 HTTP DTO 暴露现有 Benchmark Catalog 的 Package list、
detail、split 和 task metadata。Catalog adapter MUST 只从后端配置允许的显式本地根、
installed distribution 来源，以及由 Studio release repository 重建的 server-owned
managed publication 来源读取，不得让浏览器扫描 workspace、提交宿主绝对路径或维护
第二套 Package/Task 事实。服务 MAY 在 immutable Catalog snapshot 构建期间解析 task
definitions 以生成 split task count 和 availability index，但 MUST NOT 校验 resource
digest、连接设备、加载插件或因单个无效 entry 阻止其他 entry 可用。Managed publication
在进入 snapshot 前 MUST 已通过其发布边界的完整 frozen closure 校验，普通 Catalog
read MUST NOT 因展示 managed entry 而重新执行 release。

#### Scenario: 查询可用 Benchmark
- **WHEN** Catalog 中存在 AndroidWorld、AppAgent 与一个 durable managed publication
- **THEN** list 返回每个来源的 opaque catalog entry identity、Package identity、标题、版本、来源类型、split、task count 摘要和 availability

#### Scenario: 当前目录存在未配置 Package
- **WHEN** workspace 中出现一个未进入后端 Catalog 配置且未通过 managed publication command 的 Benchmark-like 目录
- **THEN** Studio list 不发现该目录，也不因浏览器当前路径变化而改变

#### Scenario: 一个 Package definition 无效
- **WHEN** 一个配置 entry 的 task definition 无法编译而其他 entry 有效
- **THEN** Catalog 将该 entry 标记为 invalid 并返回安全诊断，其他配置或 managed entry 仍可列出和选择

#### Scenario: 重启后恢复 managed publication
- **WHEN** Studio 重启时 release repository 中存在完整 durable managed publication
- **THEN** Catalog 从 server-owned managed storage 重建同一 entry identity，不读取 owning draft 或原始 source tree

### Requirement: list、detail 与 task metadata 必须无运行副作用
Catalog list/detail/task 操作 MUST NOT 连接设备、解析 device profile、加载或执行
Benchmark 插件、调用模型、执行 initializer/evaluator 或下载资源。Detail MAY 返回
manifest、requirements、resource/ground-truth 摘要和默认 Protocol，但 MUST NOT 返回
secret、raw device serial 或宿主绝对路径。

#### Scenario: 无 Android 设备查看任务
- **WHEN** 服务进程没有可用 ADB 设备且用户打开 Benchmark detail
- **THEN** metadata 请求成功，并且没有设备连接或插件执行

#### Scenario: 外部 Package 路径
- **WHEN** installed distribution 的 manifest 位于宿主 site-packages
- **THEN**响应只包含 opaque source identity 和安全元数据，不包含 site-packages 绝对路径

### Requirement: Catalog entry 歧义必须显式
Studio SHALL 使用服务签发的 opaque catalog entry identity 选择具体来源，并同时保留
Package/Plan canonical identity。多个来源具有相同可读 Package identity 但内容或来源
不同的时候，服务 MUST 返回歧义诊断或多个可显式选择的 entry，不得按发现顺序静默
覆盖。

#### Scenario: 两个来源名称相同
- **WHEN** 本地目录和 installed distribution 都声明同一可读 Package identity 但内容 hash 不同
- **THEN** list/detail 要求客户端使用各自 opaque entry identity，并显示安全的 conflict diagnostic

#### Scenario: 猜测不存在的 entry
- **WHEN** 客户端提交未知或格式非法的 catalog entry identity
- **THEN**服务返回统一 validation/not-found envelope，不泄露配置根和候选路径

### Requirement: Studio validate 必须显式且无设备副作用
Studio SHALL 提供显式 Benchmark validate command，调用现有 compiler/validator 检查
manifest、task、cross-reference、resource digest、ground truth、split、identity 和
Protocol，并返回有界结构化 diagnostics、Package identity、Plan identity 与 Protocol
identity。Validate MUST NOT 连接设备、运行插件、调用模型或启动 Experiment。

#### Scenario: 校验有效 Package
- **WHEN** 用户对一个完整 Package 执行 validate
- **THEN**响应包含 success、canonical identities 和空 error diagnostics，且未创建 Experiment

#### Scenario: 多个定义错误
- **WHEN** Package 同时包含重复 task ID、resource digest 错误和非法 Protocol budget
- **THEN**响应聚合所有可独立发现的 diagnostics，并使用安全 source pointer 定位，不返回绝对路径

### Requirement: Composer 必须绑定不可变有效 Agent revision
Experiment preview/create SHALL 接受一个有序 `agentRevisions` 列表，每项使用稳定
Agent identity 与 immutable revision identity。服务 MUST 通过现有 Agent revision
repository 加载并重新验证相应 AgentGraph snapshot/canonical hash，不得使用未保存
draft、当前 mutable revision、显示名称或前端提交的任意 graph body 代替。

#### Scenario: 选择有效 revision
- **WHEN** 用户选择一个 immutable valid revision
- **THEN**preview 返回 agent/revision/canonical graph identity，并使用该 snapshot 规划 schedule

#### Scenario: revision 已失效或不存在
- **WHEN** 请求引用未知、invalid 或 canonical 校验失败的 revision
- **THEN**preview/create 在任何设备副作用前失败，并返回定位该 agent reference 的结构化 diagnostic

### Requirement: Protocol Composer 必须保留正式 ExperimentProtocol 语义
Composer SHALL 使用正式 `ExperimentProtocol` schema 表达 seed、repeats、order、
TaskInstance reuse、budget、device/App constraints、isolation 和 failure policy。前端
MUST NOT 定义竞争性的默认值或省略影响 Protocol identity 的字段；规范化与 identity
必须由后端合同产生。

#### Scenario: 编辑 repeats 与 budget
- **WHEN** 用户提交合法 repeats、step limit 和 timeout
- **THEN**preview 返回规范化 Protocol body、Protocol identity 和所有采用的显式/default 字段

#### Scenario: 未知策略值
- **WHEN** 客户端提交未知 order 或 failure policy
- **THEN**preview 返回字段级 validation error，不回退到前端或服务隐式默认行为

### Requirement: Schedule preview 必须确定、可解释且无执行副作用
Preview SHALL 根据已验证 Agent revisions、BenchmarkPlan、task selector 和
ExperimentProtocol 生成有序 planned schedule。每个 entry MUST 包含稳定 planned entry
identity、agent/revision、task template、repeat、order 和 derived seed description。
相同规范化输入 MUST 产生相同 snapshot fingerprint 与 schedule；preview MUST NOT
materialize 动态任务参数、连接设备、执行 Agent 或持久化 Experiment。

#### Scenario: 重复相同 preview
- **WHEN**客户端两次提交语义相同但 JSON 字段顺序不同的请求
- **THEN**两次返回相同 Plan/Protocol identity、snapshot fingerprint、entry identity 和顺序

#### Scenario: 动态 Task
- **WHEN**选定 task 需要在运行时 materialize 动态参数
- **THEN**preview 只展示 template、repeat 和 seed 派生描述，并将 instance 标记为 pending materialization，不伪造目标参数

### Requirement: Preview 与 create 必须防止定义漂移
Preview response SHALL 包含可供 create 回传的 snapshot fingerprint。Create request
MUST 同时提交该 fingerprint 和完整 versioned preview definition，包括 Agent
revisions、Catalog entry、split、task selection、正式 Protocol body 和安全
`deviceProfileId`。当 `clientRequestId` 尚无 durable record 时，Create MUST 重新解析
并验证 Agent revision、Catalog entry、Plan、task selection、Protocol 与 profile
metadata；若当前 canonical 结果与提交 fingerprint 不同，MUST 返回 definition
conflict，不得创建 Experiment 或产生运行副作用。当相同 request identity/content
已经持久创建时，重试 MUST 优先返回该 durable Experiment，不得让创建后的 Package、
revision 或配置漂移否定已提交事实。

#### Scenario: Preview 后 Package 内容变化
- **WHEN**用户 preview 后、首次 create 前所选本地 Package 的 Plan identity 发生变化
- **THEN**使用旧 fingerprint create 返回 conflict，且不创建 Experiment 或连接设备

#### Scenario: Preview 后没有变化
- **WHEN**所有 canonical input 与 preview 一致且不存在 durable request record
- **THEN**create 使用完全相同的 snapshot fingerprint 保存 Experiment definition snapshot

#### Scenario: Create 成功后的相同重试遇到漂移
- **WHEN**Experiment 已提交后 Package 或 Agent 当前状态变化，客户端以相同 request identity/content 重试
- **THEN**服务返回原 Experiment，不重新校验当前来源或创建第二个 Experiment

#### Scenario: Create body 缺少完整定义
- **WHEN**客户端只回传 snapshot fingerprint 或 canonical identity 而没有完整 preview definition
- **THEN**服务返回 validation error，不使用前端状态或临时 cache 猜测定义

### Requirement: 服务必须显式发布执行 cardinality 限制
Preview metadata SHALL 返回当前实现支持的 `maxAgents`、`maxSelectedTasks`、
`maxRepeats` 和相关 capability flags。请求 DTO MUST 保留复数 Agent 与正式 Protocol
结构；当前实现不能执行某组合时 MUST 返回 `unsupported_cardinality`，不得截断、
串改 Protocol 或只运行第一项。

#### Scenario: 第一条纵向切片
- **WHEN**服务声明限制为一个 Agent、一个 selected Task、一个 repeat
- **THEN**符合限制的 preview/create 可继续，并以相同复数 DTO 表达

#### Scenario: 请求两个 Agent 但尚未支持
- **WHEN**客户端在 `maxAgents=1` 的服务提交两个 Agent revisions
- **THEN**服务拒绝整个请求并返回 capability diagnostic，不创建部分 Experiment

### Requirement: Benchmark Composer 路由必须使用正式 typed domain
Studio SHALL 以 `/benchmarks`、`/benchmarks/:benchmarkId` 和 `/experiments/new`
提供 Catalog/detail/composer。新前端代码 MUST 遵循 FSD-lite 依赖方向，并使用
Benchmark/Experiment typed DTO；它 MUST NOT 扩展旧 `pipeline: unknown[]`、扫描本地
文件或导入 Builder feature 私有 store。

#### Scenario: 打开旧 Benchmark 入口
- **WHEN**用户访问旧 `/benchmark`
- **THEN**应用重定向到正式 `/benchmarks`，不渲染 hard-coded mock Pipeline

#### Scenario: Builder 与 Composer 同时构建
- **WHEN**前端 import-boundary 检查覆盖两个 route
- **THEN**Composer 只依赖允许的 entities/shared 与自身 features，不依赖 Builder 私有 Zustand 状态

### Requirement: Catalog 来源必须由服务端命名配置
Studio SHALL 使用带稳定安全 `sourceId` 的服务端配置声明 local Package、Catalog root
与 installed discovery，并 SHALL 为 durable managed publications 使用固定的 server-owned
managed source identity。默认服务 MAY 注册存在的 workspace `benchmarks/`，但 MUST
NOT 隐式扫描 `data/`、递归扫描任意 workspace 目录、把 managed storage 当作普通目录
扫描，或接受浏览器提交的 filesystem path。每个 `catalogEntryId` MUST 由安全 source
identity、source-relative package key、Package identity 与防止不同内容静默碰撞所需的
稳定 semantic facts 确定地产生，不得包含或返回宿主绝对路径。

#### Scenario: 默认 workspace 有正式 Packages
- **WHEN** Studio 以一个包含 `benchmarks/android_world` 和 `benchmarks/appagent` 的 workspace 启动
- **THEN** Catalog 使用命名的 workspace Benchmark source 暴露两个 entry，不扫描同级 `data/`

#### Scenario: 显式外部 Catalog root
- **WHEN** 操作者通过服务端配置增加一个外部 Catalog root
- **THEN**其中有效 Package 使用该配置的安全 source ID 进入 Catalog，HTTP payload 不包含 root 绝对路径

#### Scenario: 发布到 managed source
- **WHEN** 一个 frozen Package revision 通过显式 publication command 成功发布
- **THEN**它使用固定 managed source identity 进入 Catalog，而不是要求浏览器或操作者配置其 storage path

#### Scenario: 重启后解析相同来源
- **WHEN** source ID、relative package key、Package identity 与 semantic content facts 未变化
- **THEN**服务在重启后为该具体来源产生相同 catalog entry identity

### Requirement: Catalog snapshot 与分页必须确定
Studio SHALL 在 process composition 中维护一个可原子替换的当前 immutable Catalog
snapshot，并以稳定 entry、split 和 task 排序签发有界 opaque cursor。普通 list 请求
MUST NOT 重新扫描 filesystem；每个 list/detail/task/Composer 请求 MUST 捕获一个
snapshot 并在该请求期间只使用该版本。成功 managed publication MAY 在完整 next
snapshot 预构建后原子替换 current snapshot，但 MUST NOT 就地修改已有 snapshot。
未知、过期、属于被替换 snapshot 或与当前 filter 不匹配的 cursor MUST 返回安全
validation error，不得跳项、重复项或暴露 cursor 内部 source locator。

#### Scenario: 分页期间 filesystem 变化
- **WHEN** Catalog snapshot 建立后有人在配置 root 中增加 Package
- **THEN**当前 snapshot 的分页结果保持不变，新 Package 仅在显式 snapshot rebuild 或服务重启后出现

#### Scenario: 发布与读取并发
- **WHEN** managed publication 在一个 Catalog 请求执行期间原子替换 current snapshot
- **THEN**该请求完整使用旧 snapshot，随后开始的请求完整使用新 snapshot，任何响应都不混合两者

#### Scenario: 使用旧 snapshot cursor
- **WHEN**客户端在 snapshot 替换后继续提交旧 snapshot 签发的 cursor
- **THEN**服务返回安全 stale-cursor validation error，而不是在新 snapshot 中猜测 continuation 位置

#### Scenario: 任务跨页读取
- **WHEN** 用户在同一 snapshot 中按稳定 split 与 task ID 顺序读取连续 task pages
- **THEN**每个 task 恰好出现一次，next cursor 不包含 task 内容或宿主路径

### Requirement: Composer 必须通过安全目录选择 device profile
Studio SHALL 提供只读 safe device profile metadata，使 Composer 使用
`deviceProfileId` 选择后端通过可信本地配置显式绑定的 profile。目录响应 MUST 只包含
profile identity、label、platform 和静态 configured 状态，不得返回 serial、private
binding fingerprint、device handle、secret、宿主配置或实时连接信息。未配置 profile
时目录 SHALL 为空，不得生成未绑定的 `local-android` 默认项。列举 profile 和 preview
MUST NOT 调用 profile runtime resolve、ADB discovery 或连接设备。

#### Scenario: 查看本地 Android profile
- **WHEN** 服务显式配置 `local-android` 的私有 target 且没有 ADB 设备在线
- **THEN**目录仍返回安全 configured metadata，并且没有 ADB 调用或实时 availability 推断

#### Scenario: 服务没有 profile 配置
- **WHEN** 服务在 no-device 模式启动且没有可信 Android profile 配置
- **THEN**目录返回空 items，Catalog、History、authoring 和 reporting 查询仍可使用

#### Scenario: 提交未知 profile
- **WHEN** preview 引用不在安全目录中的 device profile ID
- **THEN**请求在 schedule 生成和任何设备副作用前返回字段级 validation diagnostic

### Requirement: Stage 5.1 preview 必须保持非持久化边界
Stage 5.1 Studio SHALL 只提供 definition validation 与 deterministic preview。
Preview response MUST 明确自身为 preview-only，且 MUST NOT 创建 Experiment/TaskRun
identity、写入 Experiment repository、调用 scheduler、发布运行事件或注册 Replay。
页面 MUST NOT 把 preview success 表述为 Experiment 已创建或任务已运行。

#### Scenario: Preview 成功
- **WHEN**用户提交一个有效 Agent revision、一个 task、一个 repeat 和安全 profile
- **THEN**响应返回 identities、limits、schedule、fingerprint 和 `previewOnly` 事实，不返回 Experiment ID

#### Scenario: 观察持久化与运行边界
- **WHEN**测试对 Experiment repository、scheduler、device、plugin 和模型调用安装 fail-fast spies 后执行 preview
- **THEN**preview 成功且所有副作用 spy 均未被调用

### Requirement: Composer 必须覆盖完整浏览器状态
`/benchmarks`、`/benchmarks/:benchmarkId` 与 `/experiments/new` SHALL 使用正式 typed
DTO 展示 loading、empty、invalid entry、ambiguity、validation failure、unsupported
cardinality、preview stale 和 success 状态。Catalog server state MUST 由 query cache
持有，未提交 Composer 表单 MUST 由 feature-local memory state 持有，不得写入
`localStorage` 或旧 `pipeline: unknown[]` store。

#### Scenario: 从 Catalog 完成 preview
- **WHEN**用户依次选择 Benchmark、split、task、有效 Agent revision、Protocol 和 device profile 并显式点击 preview
- **THEN**页面展示后端返回的 normalized Protocol、diagnostics、execution limits 与 ordered schedule

#### Scenario: 修改已 preview 的表单
- **WHEN**用户在 preview success 后修改任何语义字段
- **THEN**旧 preview 被标记 stale 且不得继续显示为当前定义的有效计划，直到用户重新 preview

#### Scenario: 访问旧路由
- **WHEN**用户或旧书签打开 `/benchmark`
- **THEN**Router 重定向到 `/benchmarks`，不挂载占位 page 或旧 Benchmark draft store

### Requirement: Preview 与首次 create 必须复用单一 prepared definition
后端 SHALL 通过一个 side-effect-free prepared-definition contract 完成 Agent revision
验证、Catalog Package 编译、task selection、Protocol 规范化、安全 device profile
metadata 校验、cardinality 检查、schedule 生成与 preview fingerprint 计算。Preview
与不存在 durable idempotency record 的首次 create MUST 消费同一 canonical 结果；
首次 create MUST NOT 为同一请求再次独立编译 Plan 或采用另一套默认值。Preparation
MUST NOT resolve runtime device profile、连接设备、materialize TaskInstance、加载
运行插件、调用模型或写入 Experiment。

#### Scenario: Preview 与首次 create 输入相同
- **WHEN**Catalog、Agent revision、Protocol 和 profile metadata 在两次请求间未变化
- **THEN**preview 与 create 得到完全相同的 identities、schedule 和 fingerprint

#### Scenario: 观察 preparation 副作用
- **WHEN**测试为 device resolve、scheduler、plugin、model 和 Experiment repository 安装 fail-fast spy
- **THEN**prepared definition 成功且所有 runtime spy 均未调用

### Requirement: Composer 必须只提交当前有效 preview 创建 Experiment
`/experiments/new` SHALL 在当前 preview 成功且未 stale 时提供显式 Create Experiment
command。客户端 MUST 使用该 preview 对应的完整 versioned definition 与 snapshot
fingerprint，并为一次用户创建意图生成稳定 `clientRequestId`；在结果未知的安全重试中
MUST 复用相同 request identity 与相同 canonical content。任一语义输入变化 MUST
使 preview stale、禁用 create，并要求重新 preview。创建成功 SHALL 导航到服务返回的
`/experiments/:experimentId`；validation、definition conflict 或网络错误 MUST 保留
Composer 输入和诊断，不得伪造 Experiment identity。

#### Scenario: 从当前 preview 创建
- **WHEN**用户确认一个未 stale 的成功 preview
- **THEN**客户端提交完整 definition、对应 fingerprint 和新的稳定 client request identity，并导航到返回的 durable Experiment

#### Scenario: 结果未知后安全重试
- **WHEN**create 请求发送后连接中断且客户端无法确认服务是否已提交
- **THEN**重试复用相同 client request identity 与相同内容，使服务返回原 Experiment 或完成唯一创建

#### Scenario: preview 后修改定义
- **WHEN**用户在 preview success 后修改 Agent revision、task、Protocol 或 device profile
- **THEN**create 立即不可用，直到新定义完成新的 preview

#### Scenario: create 返回 definition conflict
- **WHEN**首次 create 发现 Package、Agent revision 或规范化定义已相对 preview 漂移
- **THEN**Composer 保留用户输入、标记 preview stale 并展示结构化 conflict，不导航或自动重新 preview

