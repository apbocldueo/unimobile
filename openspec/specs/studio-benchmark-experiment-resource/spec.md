# studio-benchmark-experiment-resource Specification

## Purpose
定义独立持久 Benchmark Experiment 与 TaskRun 资源、不可变 definition snapshot、生命周期、取消、恢复和可替换 repository 边界。
## Requirements
### Requirement: Benchmark Experiment 必须是独立持久资源
系统 SHALL 将 Benchmark Experiment 建模为独立于普通 `StudioRun` 的 aggregate root。
Experiment MUST 拥有 opaque identity、schema version、immutable definition snapshot、
planned TaskRuns、service lifecycle、cancellation、result/report availability、event
high-water mark 和 timestamps。系统 MUST NOT 把 multi-task/repeat/agent Experiment
压缩为普通 Run 的可选 Benchmark 字段。

#### Scenario: 创建 Benchmark Experiment
- **WHEN**客户端提交有效 preview fingerprint 与 create request
- **THEN**服务返回独立 Experiment identity，普通 Run repository 不产生伪造的父 Run

#### Scenario: 同一 Agent 执行普通任务
- **WHEN**同一 Agent revision 另行创建普通 StudioRun
- **THEN**普通 Run 与 Experiment 拥有独立 lifecycle、identity 和入口，互不覆盖

### Requirement: Experiment definition snapshot 必须不可变且可复核
Create SHALL 原子保存版本化 `ExperimentDefinitionSnapshot`，至少包含有序 Agent
revision/graph identities、Benchmark Catalog entry 与 Package/Plan identities、task
selection、规范化 BenchmarkPlan body 或受控 definition artifact、resource/ground-truth
逻辑 URI 与 digest 清单、规范化 Protocol body/identity、planned schedule、snapshot
fingerprint、device profile identity 和当时的 execution limits。创建后上述定义 MUST
NOT 被后续 Agent revision、Package、默认 Protocol、前端草稿或 profile 配置变化改写。

#### Scenario: 创建后 Agent 又保存 revision
- **WHEN**Experiment accepted 后同一 Agent 保存新 revision
- **THEN**Experiment 继续引用原 revision 与 graph hash，查询明确显示不可变 snapshot

#### Scenario: 创建后 Package 被移动
- **WHEN**本地 Catalog source 后续移动或内容变化
- **THEN**已保存 Experiment 仍保留原 identities/snapshot facts，execution 在设备副作用前报告 resource/definition preflight failure，不把当前同名 Package 冒充为执行定义

### Requirement: Experiment create 必须幂等且先持久化
Create command SHALL 使用 client request identity 与 canonical request fingerprint。
相同 identity 和 fingerprint 的重试 MUST 返回同一 Experiment；相同 identity 与不同
fingerprint MUST 返回 conflict。服务 MUST 在返回 `202 Accepted` 和启动 worker 前原子
提交 Experiment、definition snapshot、planned TaskRuns 与初始 journal event。

#### Scenario: 创建响应丢失后重试
- **WHEN**客户端未收到首次响应并以相同 identity/content 重试
- **THEN**服务返回首次 Experiment 及当前状态，不创建第二个 schedule 或设备执行

#### Scenario: 复用 request identity 改 Agent
- **WHEN**客户端使用相同 request identity 提交不同 Agent revision
- **THEN**服务返回 fingerprint conflict，并保持原 Experiment 不变

### Requirement: Planned TaskRun identity 必须稳定且与 runtime instance 分离
每个 planned schedule entry SHALL 在创建时获得稳定 TaskRun identity，并记录 agent、
task template、repeat、order 和 derived seed description。动态 `TaskInstance` 的具体
identity/parameters MUST 在 Benchmark Core materialization 后附加为运行事实，不得
改写 TaskRun identity。公平复用关系只有在实际 materialization 后才能标记 verified。

#### Scenario: 动态任务被物化
- **WHEN**worker 为一个 planned TaskRun 成功 materialize TaskInstance
- **THEN**TaskRun identity 不变并新增 instance identity、参数摘要和 materialization evidence

#### Scenario: materialization 失败
- **WHEN**动态任务生成器失败
- **THEN**TaskRun 保留 planned identity，记录 materialization failure，不构造虚假 instance identity

### Requirement: Experiment service lifecycle、终止原因和结果必须分离
Experiment service lifecycle SHALL 仅使用 `accepted`、`starting`、`running`、
`cancelling`、`finalizing` 和 `terminal` 的单向状态。Terminal resource MUST 独立保存
`completed`、`cancelled`、`failed` 或 `interrupted` reason，以及正式 result/report
availability。Lifecycle MUST NOT 代替 Agent status、Benchmark outcome 或统计结果。

#### Scenario: Agent 成功但 Benchmark 失败
- **WHEN**所有服务步骤正常收口且 TaskResult 为 Agent SUCCESS、Benchmark FAIL
- **THEN**Experiment lifecycle 为 terminal/completed，同时保留 FAIL outcome

#### Scenario: 服务重启中断
- **WHEN**recovery 发现无法安全恢复的 running Experiment
- **THEN**Experiment 进入 terminal/interrupted，并保留已有 TaskRun 事实而非标记 completed

### Requirement: TaskRun 必须分离 service、phase、Agent 与 Benchmark 状态
TaskRun SHALL 分别表达 service lifecycle、Benchmark phase results、可选 Agent
`RunStatus`、可选 Benchmark `PASS/FAIL/INVALID/SKIPPED`、service termination reason
以及 result/replay availability。尚未由 Benchmark Core 产生正式 outcome 的 TaskRun
MUST 标记 `outcomeAvailability=not_produced`，不得从 service state 推断 outcome。

#### Scenario: 取消尚未启动的 TaskRun
- **WHEN**Experiment 在该 TaskRun 产生设备副作用前被取消
- **THEN**TaskRun terminal reason 为 `cancelled_before_start`，Benchmark outcome 为 not_produced

#### Scenario: cleanup 失败但 evaluation 已完成
- **WHEN**evaluation 产生 PASS，随后 cleanup 失败
- **THEN**TaskRun 同时保留 PASS evaluation、cleanup failure 与 Protocol 决定的最终 outcome

### Requirement: 状态转换必须事务化并抵抗并发终止
Experiment 与 TaskRun lifecycle transition SHALL 通过 transaction 或 compare-and-swap
执行，只允许规范状态机中的前向转换。Cancel、runtime completion、event failure、
finalization 和 recovery 同时竞争时 MUST 产生一个不可变终态，失败的竞争者只能读取
当前事实。

#### Scenario: completion 与 cancel 竞争
- **WHEN**最后一个 TaskRun 完成时 cancel request 同时提交
- **THEN**只有一个合法 transition 序列获胜，Experiment 不出现两个 terminal reason

#### Scenario: terminal 后迟到事件
- **WHEN**旧 worker 在 Experiment terminal 后尝试改写 running
- **THEN**repository 拒绝逆向转换并记录安全 integrity diagnostic

### Requirement: Experiment HTTP 必须提供安全 command/query
Studio HTTP SHALL 提供 create、get、cancel、TaskRun list 和 TaskRun get 接口。查询
MUST 返回 definition/result availability、current lifecycle、event high-water mark 和
显式 resource links；错误 MUST 使用统一安全 envelope。列表 MUST 使用稳定排序和
opaque cursor。

#### Scenario: 创建后立即查询
- **WHEN**客户端收到 `202 Accepted` 后立即 GET Experiment
- **THEN**即使 worker 尚未启动也能读取已提交 snapshot、planned TaskRuns 和初始 cursor

#### Scenario: 查询未知 Experiment
- **WHEN**客户端提交未知或非法 Experiment identity
- **THEN**服务返回 validation/not-found，不泄露数据库、artifact root 或邻近 identity

### Requirement: Cancel 必须幂等且明确为协作式
Cancel command SHALL 先持久化 cancellation request，再通知本进程 cancellation signal。
它 MUST 明确只保证 Benchmark/Graph Runtime 在安全边界观察请求，不得声称强制中断
正在执行的模型、设备或 Python 调用，也不得表示 pause/checkpoint。重复 cancel MUST
返回当前事实且不得产生第二个 request 或 terminal transition。

#### Scenario: accepted 阶段取消
- **WHEN**Experiment 尚未开始任何设备副作用
- **THEN**worker 不启动 TaskRun，Experiment 以 cancelled 收口，scheduled entries 记录 cancelled_before_start

#### Scenario: Agent 调用期间取消
- **WHEN**取消到达时模型或设备调用不可中断
- **THEN**Experiment 显示 cancelling，调用返回后的安全边界停止后续 Agent/TaskRun 调度

#### Scenario: terminal 后重复取消
- **WHEN**客户端取消一个 terminal Experiment
- **THEN**服务幂等返回既有终态，不改写结果或新增 terminal event

### Requirement: Cancel 不得丢弃 evaluation、cleanup 与 finalization 事实
取消在 evaluation、cleanup 或 finalizing 阶段到达时，服务 SHALL 保留已经产生的
Evaluation Result、artifact 和 phase evidence，并按 Protocol 完成必须的 cleanup 或
幂等 publication；取消 MUST 阻止新的 TaskRun 调度，但 MUST NOT 用 CANCELLED 覆盖已
提交的 PASS/FAIL/INVALID 事实。

#### Scenario: evaluation 完成后取消
- **WHEN**正式 evaluation 已提交而 cleanup 尚未结束时收到 cancel
- **THEN**evaluation 保留，cleanup 按 Protocol 收口，Experiment terminal 同时表达 cancellation 与已完成结果

#### Scenario: report publication 时取消
- **WHEN**所有 TaskRuns 已结束且 report 正在原子发布
- **THEN**finalizer 可以完成或安全失败，已有 TaskResults 不被删除或改写

### Requirement: Startup recovery 不得伪造 in-flight resume
可执行 Benchmark Studio composition SHALL 在对外提供 application service 或唤醒
scheduler 前扫描由旧进程拥有的非终态 Experiment，并以 typed repository transaction
持久化 recovery decision。`accepted` Experiment SHALL 使用原 identity、snapshot 和
schedule 转移给当前 owner 并重新入队；仅完成无设备副作用 preflight 的 `starting`
Experiment SHALL 通过显式 recovery-only transition 重置为 `accepted` 后重新验证与
入队。`running` 或 `cancelling` Experiment MUST NOT 自动重跑不确定的 Agent/设备
动作，而 SHALL 保存已确认 journal/evidence、以 `interrupted` 收口当前及未开始
TaskRun。`finalizing` Experiment SHALL 只依据已提交 TaskRun/TaskResult/publication
事实完成 publication-only 或 finalize-only recovery。Terminal Experiment MUST 保持
不可变且不产生 recovery side effect。

#### Scenario: accepted Experiment 后进程退出
- **WHEN** recovery 发现旧 owner 的 `accepted` Experiment
- **THEN** Experiment 使用原 identity、snapshot 和 schedule 转移给当前 owner 并入队一次，不创建第二个 schedule

#### Scenario: starting preflight 后进程退出
- **WHEN** recovery 发现旧 owner 的 `starting` Experiment 且执行边界保证该阶段尚未解析设备、获取 device lease 或调用 Agent
- **THEN** repository 原子关闭旧 preflight attempt、重置为 `accepted` 并按同一 identity 重新执行 preflight

#### Scenario: running TaskRun 后进程退出
- **WHEN** recovery 无法证明最后一个设备动作是否完成
- **THEN** 服务不重跑 Agent 或设备，保存 interrupted 前缀并将 TaskRun/Experiment 以 `interrupted` 收口

#### Scenario: cancelling TaskRun 后进程退出
- **WHEN** recovery 发现旧 owner 的 `cancelling` Experiment
- **THEN** 服务保留 cancellation request、已提交 result/outcome/evidence，并按不确定 in-flight work 的规则以 `interrupted` 收口

#### Scenario: finalizing 且结果完整
- **WHEN** 所有需要 publication 的 immutable TaskResult 已落盘而 publication transaction 尚未提交
- **THEN** recovery 仅按 immutable publication identity 幂等重试 publication，不调用 execution adapter、Agent 或设备

#### Scenario: finalizing 时进程退出
- **WHEN** 所有 TaskResult 已落盘但 Replay/report publication 或 Experiment terminal 尚未完成
- **THEN** recovery 仅按 immutable identity 幂等完成 publication 或 finalization，不重新执行 Agent

#### Scenario: finalizing 但没有 TaskResult
- **WHEN** TaskRun 已以 failed、cancelled 或 interrupted 终止且 Experiment 在无结果 finalization 后崩溃
- **THEN** recovery 从已提交 TaskRun terminal reason 完成 Experiment finalization，不发布结果、bundle 或 Replay

#### Scenario: terminal Experiment 被扫描
- **WHEN** recovery query 遇到已提交 terminal Experiment
- **THEN** repository 返回或跳过既有不可变事实，不转移 owner、不追加 recovery event 且不唤醒 scheduler

#### Scenario: recovery 再次崩溃
- **WHEN** 新进程在 recovery transaction、scheduler wake、publication 或 finalization 之间再次退出
- **THEN** 下一次启动从最后一个原子提交点重复决策，不重复执行、发布、schedule 或 terminal transition

### Requirement: 持久化必须通过可替换 typed repository port
Experiment、TaskRun、request、snapshot、lifecycle、cancellation、result availability
和 recovery query SHALL 通过 typed repository protocols 访问。首版 SQLite adapter
MUST 使用版本化 schema，但 domain、HTTP DTO、application service 与 React MUST NOT
依赖 SQLite row ID、SQL、数据库路径或专有时间语义。

#### Scenario: SQLite 服务重启
- **WHEN**服务使用同一 workspace database 重启
- **THEN**已提交 Experiment、TaskRuns、snapshot、cancel state 和 cursor 仍可查询

#### Scenario: 未来 PostgreSQL adapter
- **WHEN**PostgreSQL adapter 通过同一 repository contract suite
- **THEN**HTTP resource identity、application service 和前端不需因存储实现而修改

### Requirement: 第一版持久数据不得自动清理
首版服务 SHALL 持久保存 Experiment、TaskRun、events、results 和 managed artifact
metadata，除非未来经独立版本化 retention/delete 合同执行显式操作。服务 MUST NOT
因为进程重启、浏览器关闭、Experiment 失败或临时 quota heuristic 自动删除可审计
证据。

#### Scenario: 浏览器关闭后重新访问
- **WHEN**用户在 Experiment terminal 后关闭浏览器并稍后重新打开
- **THEN**Experiment、TaskRuns、results 和已保留 artifact 仍可查询

#### Scenario: 磁盘接近预警
- **WHEN**preflight 检测到无法保证 evidence 持久化的存储条件
- **THEN**新 Experiment 在设备副作用前失败或拒绝启动，不删除旧 Experiment 腾空间

### Requirement: Device binding 必须使用安全 profile
Experiment create SHALL 只接受可信本地配置允许的 opaque device profile identity，并
保存公共 profile identity 与 Protocol constraints，同时在同一 atomic create boundary
中保存 server-private binding fingerprint。Metadata/preview MUST NOT runtime-resolve、
发现或连接真实设备；create MAY 读取无副作用的静态 binding authority，但公共 snapshot、
event、result、report、Replay 和 export MUST NOT 保存 raw serial、private fingerprint、
凭据、ADB 参数、配置路径或 live handle。相同成功 command 的幂等重试 SHALL 先返回原
持久 aggregate 和原 binding authority，不因当前 profile 漂移改写已接受事实。

#### Scenario: 选择合法 profile
- **WHEN**用户为执行选择可信配置中的 Android fake/real profile
- **THEN**公共 snapshot 只保存 opaque profile identity，private binding fingerprint 与完整 aggregate 原子提交

#### Scenario: 客户端提交 raw serial
- **WHEN**create payload 包含 `emulator-5554` 等直接 serial、binding fingerprint 或 ADB 参数
- **THEN**服务拒绝请求，不尝试连接或持久化该设备信息

#### Scenario: 成功重试时 profile 已漂移
- **WHEN**相同 `clientRequestId` 的 Experiment 已成功创建，随后本地 profile 被重新绑定并再次提交相同请求
- **THEN**服务返回原 Experiment 和原 private authority，不用当前配置改写成功 command 的事实

#### Scenario: binding persistence 失败
- **WHEN**创建 aggregate 与 private binding authority 的 transaction 被注入失败
- **THEN**Experiment、TaskRun、accepted event 和 binding record 全部不可见

### Requirement: Stage 5.2A create 必须提交完整定义而非身份占位符
`StudioBenchmarkExperimentCreateRequestV1` SHALL 包含 `schemaVersion`、
`clientRequestId`、`previewFingerprint` 和完整的 versioned preview definition。
Definition MUST 包含有序 Agent revision references、Catalog entry、split、task
selection、正式 Protocol body 和安全 `deviceProfileId`。服务 MUST 解析完整定义并重算
所有 canonical identities；客户端提交的 hash、Plan body、AgentGraph body、raw device
serial 或 storage locator MUST NOT 成为事实源。

#### Scenario: 使用完整 preview 定义创建
- **WHEN**客户端提交与成功 preview 相同的完整 definition 和 fingerprint
- **THEN**服务从已验证后端事实构造 Experiment snapshot，而不是从 client identity 猜测定义

#### Scenario: 只提交 Protocol identity
- **WHEN**create request 只有 `protocolIdentity` 或遗漏完整 Protocol body
- **THEN**服务返回字段级 validation error，不读取进程内 preview cache 补全请求

### Requirement: Stage 5.2A 必须原子创建完整 accepted aggregate
首次 create SHALL 在单一 repository transaction 内保存 Experiment、canonical request
record、不可变 definition snapshot、全部 planned TaskRuns、初始 accepted journal event
和 event high-water mark。事务任一步失败 MUST 不留下任何可查询的 Experiment、
TaskRun 或 event。服务 MUST 只在提交成功后返回 `202 Accepted`。Stage 5.2B MAY 在
该 durable commit 后通知 dispatcher，但 scheduler、profile resolve、设备、插件、
模型、initializer 或 evaluator 副作用 MUST NOT 进入 create transaction；相同内容
retry 的通知 MUST 依赖 worker claim CAS 防止重复执行。

#### Scenario: 初始 event 写入失败
- **WHEN**SQLite adapter 在 Experiment 与 TaskRun insert 后无法写入 accepted event
- **THEN**整个 transaction 回滚，create 返回安全 storage failure，所有资源均不可查询且 dispatcher 不被通知

#### Scenario: 原子提交成功
- **WHEN**definition、snapshot 和 schedule 均有效且所有 insert 成功
- **THEN**首次 GET 同时看到 accepted Experiment、完整 planned TaskRuns 和从 1 开始的 high-water mark，随后才允许 worker claim

#### Scenario: create 重试通知 dispatcher
- **WHEN**相同 request identity/content 的重试返回仍为 accepted 的原 Experiment
- **THEN**服务可以再次唤醒 dispatcher，但 repository 保证最多一个 worker owner 和一次 Benchmark 执行

### Requirement: Stage 5.2A 幂等重试必须先读取持久事实
Create SHALL 在严格解析请求并计算 canonical request fingerprint 后，先按
`clientRequestId` 查询 durable request record。若已有记录且 fingerprint 相同，服务
MUST 立即返回原 Experiment，不重新解析当前 Catalog Package 或重新验证当前 Agent
revision；若 fingerprint 不同，MUST 返回 idempotency conflict。只有不存在 durable
记录时，服务才 SHALL 重建当前 definition、检查 preview drift 并尝试原子创建。
Repository MUST 通过唯一约束和 race-safe create 使并发相同请求只产生一个 aggregate
和一个 accepted event。

#### Scenario: 成功后 Package 漂移再重试
- **WHEN**首次 create 已提交但响应丢失，随后 Package 内容变化，客户端以相同 identity/content 重试
- **THEN**服务返回首次 Experiment，不因当前 Package 漂移拒绝已存在的 durable fact

#### Scenario: Package 漂移后的首次 create
- **WHEN**不存在 durable request record 且当前 Package 与提交 preview fingerprint 不同
- **THEN**服务返回 definition conflict，不写入 Experiment、TaskRun 或 event

#### Scenario: 两个相同首次请求并发
- **WHEN**两个调用并发使用相同 client request identity 和 content
- **THEN**二者获得同一 Experiment，数据库只有一个 schedule 和一个 accepted event

#### Scenario: request identity 内容冲突
- **WHEN**已有 request identity 被用于不同 canonical content
- **THEN**服务返回 idempotency conflict，原 snapshot 和 lifecycle 保持不变

### Requirement: V1 definition snapshot 必须完整、有界且安全
Stage 5.2A SHALL 在 SQLite 中内联保存 canonical
`ExperimentDefinitionSnapshotV1`，包含完整已验证 AgentGraph snapshots、完整规范化
BenchmarkPlan 和 ExperimentProtocol bodies、安全 Catalog/Package/content/Plan/
Protocol/revision/graph identities、task selection、resource 与 ground-truth 逻辑 URI
及 digest、planned schedule、preview fingerprint、device profile identity 和当时的
capability/execution limits。Canonical UTF-8 JSON MUST NOT 超过 2,097,152 bytes。
Snapshot MUST NOT 包含 Package asset bytes、宿主绝对路径、secret、raw device serial、
live handle、插件/模型实例或数据库 locator。

#### Scenario: Package 后续被修改
- **WHEN**Experiment 创建后 Catalog Package 或 Agent 当前 revision 变化
- **THEN**GET 仍返回创建时的安全 snapshot facts 和 identities，不用当前内容改写历史

#### Scenario: Snapshot 超过限制
- **WHEN**canonical snapshot JSON 大于 2,097,152 bytes
- **THEN**create 在 transaction 和任何运行副作用前返回 typed size error，数据库不产生部分记录

#### Scenario: 公共查询 snapshot
- **WHEN**客户端 GET 已创建 Experiment
- **THEN**响应投影可复核定义且不包含 host path、SQLite filename、raw serial 或 secret

### Requirement: Stage 5.2A SQLite migration 必须由共享边界统一管理
Studio SHALL 由一个共享 SQLite database migration boundary 管理单调 schema history。
Schema version 4 SHALL 添加 Experiment、TaskRun 和 Experiment event tables、唯一约束
及查询 indexes；现有 Agent-document、StudioRun 与 Replay repositories MUST 复用该
boundary，并保持原 public imports、constructors 和 schema 1–3 行为。任一 repository
在 version 4 database 上启动 MUST NOT 把合法数据库误判为未知新版本。

#### Scenario: 从 schema 3 升级
- **WHEN**已有 Agent、Run 与 Replay 数据库首次由新版本打开
- **THEN**migration 原子增加 version 4 结构，旧数据和旧 repository 查询结果保持不变

#### Scenario: 不同 repository 重复打开
- **WHEN**Agent、Run、Replay 和 Experiment adapters 并发或依次打开同一 version 4 database
- **THEN**migration 可重入且只有一条 version 4 记录，不发生 newer-schema rejection

#### Scenario: 未来替换存储 adapter
- **WHEN**非 SQLite adapter 通过相同 typed aggregate repository contract suite
- **THEN**application service 与 HTTP DTO 不依赖 SQL row ID、database path 或 SQLite 时间语义

### Requirement: Stage 5.2A accepted cancel 必须直接原子终止
若 cancel 的 repository transaction 成功 claim 一个尚未产生任何执行副作用的
`accepted` Experiment，它 SHALL 原子保存 cancellation request、将所有 `scheduled`
TaskRuns 终止为 `cancelled_before_start`、保持 Benchmark
`outcomeAvailability=not_produced`、将 Experiment 终止为 `cancelled`，并按确定顺序
追加 cancellation、TaskRun terminal 和唯一 Experiment terminal events。若 worker
已 claim `starting/running/cancelling/finalizing`，Stage 5.2B cancel SHALL 改为先持久
请求并通知本进程 cooperative signal；不得把 active Experiment 冒充
cancelled-before-start。对已终态 Experiment 重复 cancel MUST 返回现有事实且不追加
event。

#### Scenario: accepted Experiment 被取消
- **WHEN**cancel CAS 先于 worker claim 获得尚无副作用的 accepted Experiment
- **THEN**Experiment 与全部 TaskRuns 在同一次提交中按 cancelled/cancelled_before_start 收口

#### Scenario: active Experiment 被取消
- **WHEN**worker 已 claim 且 Experiment 处于 starting、running 或 cancelling
- **THEN**request 先持久化、lifecycle 前向进入或保持 cancelling、active signal 被通知，并在安全边界收口

#### Scenario: finalizing 时取消
- **WHEN**TaskResult 已提交且 Experiment 正在 finalizing
- **THEN**cancel request 可幂等记录但 lifecycle 不逆转，已有 Agent status、Benchmark outcome 和 cleanup facts 不被覆盖

#### Scenario: cancel transaction 失败
- **WHEN**取消过程中任一 lifecycle 或 event 写入失败
- **THEN**整个 transaction 回滚，Experiment、TaskRuns、cancellation 和 high-water mark 保持上一个已提交事实

#### Scenario: 重复取消
- **WHEN**客户端再次取消 cancelling 或已 terminal Experiment
- **THEN**服务返回当前事实，不增加第二个 cancellation request 或 terminal event

### Requirement: Stage 5.2A HTTP 必须只发布真实可用资源
Studio HTTP SHALL 保留 `POST /studio/benchmark-experiments`、
`GET /studio/benchmark-experiments/{experimentId}`、
`POST /studio/benchmark-experiments/{experimentId}/cancel`、
`GET /studio/benchmark-experiments/{experimentId}/task-runs` 和
`GET /studio/benchmark-experiments/{experimentId}/task-runs/{taskRunId}`。
Create response SHALL 使用 versioned wrapper 返回 `created` 和 resource；新建与
same-content retry 均返回 `202`。TaskRun list MUST 按 `(order, taskRunId)` 稳定排序并
使用有界 limit 与 opaque cursor。Stage 5.2B resource SHALL 发布 `executes=true`、
cooperative cancel guarantee 以及已实现的 lifecycle/result availability，但 links
MUST 继续只包含真实 route，不得发布 Stage 5.2C 的 event query/SSE、report、bundle、
artifact、Replay、recovery、retry 或 runtime-control 失效链接。

#### Scenario: 重启后查询
- **WHEN**服务使用同一 SQLite database 重启后 GET Experiment 与 TaskRuns
- **THEN**resource、snapshot、已提交 lifecycle/result、high-water mark、稳定排序和 cursor 均由持久事实恢复，但本 Change 不声称自动恢复执行

#### Scenario: TaskRun 不属于 Experiment
- **WHEN**客户端在一个 Experiment-scoped route 中查询另一 Experiment 的 TaskRun identity
- **THEN**服务返回安全 not-found，不泄露所属 Experiment 或邻近 identity

#### Scenario: 查询非法 cursor
- **WHEN**TaskRun list 收到未知、篡改或与当前 Experiment 不匹配的 cursor
- **THEN**服务返回安全 invalid-cursor，不跳项、重复项或暴露 cursor 内部结构

#### Scenario: 读取 capability links
- **WHEN**客户端读取 Experiment resource
- **THEN**响应只包含可用的 self/cancel/TaskRun links，capability facts 按实际 composition 区分 execution-enabled 与 definition-only 服务，不发布未实现 route

#### Scenario: 读取 Stage 5.2B capability facts
- **WHEN**客户端 GET 一个由 execution worker 管理的 Experiment
- **THEN**响应真实声明 executes 与 cooperative cancel 可用，同时 eventStream、replay 和 reports 仍为 false 且无对应链接

### Requirement: Stage 5.2C-1 Experiment resource 必须如实开放 event transport
当且仅当进程已经组合 durable Benchmark Experiment repository、event query service
与 SSE transport 时，Experiment resource MUST 将 `capabilities.eventStream` 设为
true，并提供 Experiment-scoped `links.events` 和 `links.eventStream`。当且仅当
Stage 5.2C-2 managed publication、safe resolver 和 native Replay publisher 已完整组合
时，resource MUST 将 `capabilities.reports` 与 `capabilities.replay` 设为 true，并按
对应 availability 提供 report、bundle 和 TaskRun Replay typed links。Definition-only
或缺少任一完整边界的组合 MUST 保持对应 capability false 且省略失效 links。

#### Scenario: 可执行组合开放真实 event links
- **WHEN**客户端读取已组合 Stage 5.2C-1 event transport 的 Experiment
- **THEN**resource 声明 `eventStream=true`，并返回可成功访问同一 Experiment 的 events 与 eventStream links

#### Scenario: publication 组合开放真实能力
- **WHEN**客户端读取由 Stage 5.2C-2 publication service 管理的 Experiment
- **THEN**resource 声明 `reports=true` 与 `replay=true`，available publication 返回可访问的显式 typed links

#### Scenario: publication 尚在 finalizing
- **WHEN**Experiment 已有 available TaskResult但 report、bundle 或 Replay 尚未提交
- **THEN**resource 保留 pending availability 且不返回对应 content link，不把 TaskResult 推断为 publication available

#### Scenario: publication 失败
- **WHEN**report、bundle 或 Replay publication 独立失败
- **THEN**resource 返回对应 failed availability 和安全 diagnostic，省略失效 link，已提交 result 与其他 available links 保持不变

#### Scenario: Replay 与 reports 仍未开放
- **WHEN**客户端读取只组合 Stage 5.2C-1 event transport、但没有 Stage 5.2C-2 publication service 的 Experiment resource
- **THEN**resource 继续声明 `replay=false`、`reports=false`，且不包含 Replay、report 或 bundle link

#### Scenario: Definition-only 组合不伪造能力
- **WHEN**进程没有 durable event transport、managed publication 或 Replay publisher
- **THEN**resource 分别保持对应 capability false 且不包含其 links

### Requirement: Stage 5.2C-2 HTTP 必须通过 scoped typed links 发布证据
Studio HTTP SHALL 提供 Experiment report、Experiment bundle 和
Experiment/TaskRun-scoped opaque artifact 的只读 route，并使 TaskRun resource 在
Replay available 时返回显式 Replay identity 与既有 Replay API link。Handler MUST
只接受经过语法验证的 opaque Experiment、TaskRun 和 artifact identities，并通过
repository scope 查找；它 MUST NOT 接受宿主路径、relative path、storage locator 或
由客户端拼装的文件名。未知、非法、跨 scope、missing 或 corrupt 内容 MUST 使用统一
安全错误且不泄露相邻 metadata。

#### Scenario: 跟随 available report link
- **WHEN**客户端从 terminal Experiment resource 跟随 `links.report`
- **THEN**服务返回与已提交 report identity、content type 和 digest 对应的正式 Core report

#### Scenario: 跟随 TaskRun Replay link
- **WHEN**terminal TaskRun 的 Replay availability 为 available
- **THEN**TaskRun 返回显式 Replay identity 与既有 `/studio/replays/{replayId}` link，客户端无需推断 identity

#### Scenario: 跨 Experiment artifact 请求
- **WHEN**客户端在 Experiment A 的 artifact route 使用只属于 Experiment B 的 opaque artifact identity
- **THEN**服务返回安全 not-found，不泄露该 artifact 是否存在或属于哪个 Experiment

#### Scenario: artifact 被篡改
- **WHEN**resolver 读取的 artifact 内容与已提交 digest 不一致
- **THEN**服务不返回内容、将 availability 收口为 corrupt，并返回不含宿主路径的 integrity error

### Requirement: 可执行 composition 必须拥有唯一 recovery owner
每个 workspace Benchmark repository SHALL 通过 typed recovery ownership port 保证
同一时刻至多一个可执行 Studio composition 可以执行 startup recovery 和本地
scheduling。首版 SQLite composition MUST 使用随进程退出自动释放的 workspace/database
级独占 ownership；definition-only Catalog/Composer composition MUST NOT 获取该
ownership。Domain、application service 和 HTTP DTO MUST NOT 依赖 lock 文件路径、
SQLite row identity 或平台专有 owner 表达。

#### Scenario: 两个本地服务同时启动
- **WHEN** 第二个可执行 composition 尝试为同一 workspace database 获取 recovery ownership
- **THEN** 第二个 composition 在 recovery 和 scheduler 启动前明确失败，不能把第一个活跃进程的工作误判为 stale

#### Scenario: 旧进程异常退出
- **WHEN** 持有 ownership 的进程崩溃且操作系统释放独占 ownership
- **THEN** 新 composition 可以获取 ownership、扫描旧 owner records 并执行规范 recovery

#### Scenario: 只读 authoring composition
- **WHEN** Studio 只构造 Catalog/Composer 而不提供 Benchmark execution
- **THEN** composition 不获取 recovery ownership，也不扫描或改写 Experiment

### Requirement: Recovery repository 操作必须保持 aggregate 原子性
Recovery query、owner transfer、requeue reset、in-flight interruption、finalizing
claim 和 finalize-only transition SHALL 通过 database-neutral typed repository
protocols 表达。SQLite adapter MUST 使用 transaction/CAS 同时验证旧 lifecycle 与
owner、更新 Experiment/TaskRun facts、追加 recovery journal facts，并仅在 commit 后
通知 scheduler 或 event waiter。Storage failure MUST 回滚整个 decision。

#### Scenario: recovery transaction 写入失败
- **WHEN** repository 在更新 TaskRun 后、提交 recovery 或 Experiment event 前发生 storage failure
- **THEN** 整个 transaction 回滚，query/SSE 不暴露半个 decision，scheduler 不执行该 Experiment

#### Scenario: 旧 worker 迟到写入
- **WHEN** recovery 已经转移或终结 Experiment 后旧 owner 尝试提交 lifecycle/result
- **THEN** owner-scoped CAS 拒绝迟到写入并保留当前 recovery 事实

#### Scenario: 未来 PostgreSQL adapter
- **WHEN** PostgreSQL implementation 通过相同 recovery repository 与 ownership contract suite
- **THEN** recovery orchestrator、HTTP resources 和 frontend 无需改用 SQL、row ID 或数据库路径

