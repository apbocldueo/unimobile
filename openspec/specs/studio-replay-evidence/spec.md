# studio-replay-evidence Specification

## Purpose
TBD - created by archiving change implement-studio-trajectory-replay-2. Update Purpose after archive.
## Requirements
### Requirement: 版本化 Replay evidence envelope
系统 SHALL 将一次可回放运行表示为版本化 `ReplayEvidenceEnvelope`，关联 replay/run
identity、provenance、不可变 RunSnapshot、RunResult 摘要、ordered events、
observations、actions、可选 Benchmark context、artifact descriptors、evidence
availability 和 integrity diagnostics。前端 MUST NOT 直接依赖 Benchmark 文件目录或
JSONL 行布局作为产品合同。

#### Scenario: 读取 Agent-only Replay
- **WHEN** 导入一个没有 Benchmark context 的正式 RunResult 和 trajectory
- **THEN** envelope 包含 Agent run identity、snapshot、events 和 artifacts，且不构造
  虚假的 Benchmark phase 或 outcome

#### Scenario: 读取 Benchmark Replay
- **WHEN** 导入一个包含 Benchmark lifecycle 和嵌套 AgentGraph events 的 task run
- **THEN** envelope 同时保留 Agent 与 Benchmark identity、状态和 evidence，不把它们
  压缩为一个布尔结果

### Requirement: 显式受信任来源与格式适配
系统 SHALL 支持原生版本化 Replay Package 和显式选择的受信任本地
Benchmark experiment/run 目录。导入 MUST 通过 source adapter 完成，MUST NOT 递归扫描
任意 workspace、根据显示名称发现运行，或让浏览器提交和读取未经授权的宿主路径。

#### Scenario: 显式导入本地 Benchmark 目录
- **WHEN** 本地用户通过受信任 service/CLI boundary 选择一个 experiment/run 目录、
  对应 artifact root 和 graph snapshot
- **THEN** legacy adapter 只读取已声明的 result/report/trajectory/artifact，并生成统一
  Replay envelope

#### Scenario: HTTP 请求包含任意宿主路径
- **WHEN** 浏览器尝试通过 Replay HTTP API 传入一个未授权绝对路径或 workspace 扫描根
- **THEN** 服务拒绝请求，且响应不泄露该路径是否存在

### Requirement: 原子导入与持久 Replay 索引
系统 SHALL 通过版本化 Replay repository 保存导入索引和 artifact metadata，首版
SQLite adapter MUST 仅保存结构化数据，Local Artifact Store MUST 保存截图、XML、
trajectory、响应和 bundle 等大型内容。导入 MUST 在 staging 中完成 schema、路径、
hash、安全和 graph identity 校验，只有全部成功后才提交可查询记录。

#### Scenario: 导入完成后源目录被移动
- **WHEN** 一个 Replay 已成功导入受控存储，随后原始本地目录被移动或删除
- **THEN** 用户仍可通过 run ID 加载 envelope 和已导入 artifact

#### Scenario: 导入中途 artifact 校验失败
- **WHEN** staging 中一个声明的截图 hash 与实际内容不一致
- **THEN** 导入失败、Replay 索引不可见，并且不留下指向半成品内容的有效 metadata

#### Scenario: 未来更换 PostgreSQL adapter
- **WHEN** 未来提供一个通过相同 repository 合同测试的 PostgreSQL adapter
- **THEN** Replay service、HTTP DTO 和前端业务逻辑无需依赖 SQLite row ID 或专有 SQL
  进行修改

### Requirement: 可验证的 AgentGraph snapshot
Replay SHALL 使用 snapshot 中实际保存的 AgentGraph 1.1 body 进行图投影，并 MUST 通过
正式 canonical 算法验证其 hash 与运行身份一致。系统 MUST NOT 根据 `agent_id`、标题、
组件名称或当前 Agent revision 猜测旧运行使用的图。

#### Scenario: Graph body 与运行 hash 一致
- **WHEN** 导入的 AgentGraph body 计算结果与 trajectory 的 `agent_graph` identity 一致
- **THEN** Replay 标记 graph snapshot 为 verified，并允许前端渲染该不可变图

#### Scenario: Graph body 与运行 hash 不一致
- **WHEN** 提供的 AgentGraph body canonical hash 与运行证据中的 identity 不同
- **THEN** 导入以结构化 graph identity diagnostic 失败，不使用该图进行 Replay

#### Scenario: 旧运行只有 graph hash
- **WHEN** 运行证据只有 canonical hash 而没有 graph body
- **THEN** Replay 保留事件、结果和 artifact，并将 graph availability 标记为
  `not_captured`，而不是按 Agent 名称加载另一张图

### Requirement: 证据可用性是正式数据
每类可选 evidence SHALL 使用 `available`、`not_captured`、`excluded`、`missing`、
`corrupt` 或 `redacted` 等结构化 availability 状态。系统 MUST 区分“本次运行未采集”
与“声明存在但读取失败”，不得用空字符串或虚构内容掩盖差异。

#### Scenario: 旧 Android 运行没有 UI XML 和模型响应
- **WHEN** 导入的 trajectory 只有 screenshot references 和有界 RunEvent payload
- **THEN** screenshot 可标记为 available，而 UI XML、完整模型响应和 Prompt 分别标记
  为真实的 not_captured/excluded 状态

#### Scenario: Manifest 声明截图但文件缺失
- **WHEN** manifest 声明一个 screenshot artifact 而内容不存在
- **THEN** Replay 标记该 artifact 为 missing、保留运行其余证据，并向界面提供可读
  diagnostic

#### Scenario: 内容经过 secret redaction
- **WHEN** 一个模型响应 artifact 的部分字段被安全策略替换
- **THEN** availability/provenance 记录 redacted 状态，原始 secret 不进入 envelope、
  metadata 或导出

### Requirement: Opaque artifact identity 与安全解析
每个 artifact SHALL 具有 replay-scoped opaque identity、content type、size、hash、
schema/provenance 和安全相对来源。HTTP artifact 读取 MUST 以 run identity 和 artifact
identity 查询受控 resolver，并 MUST 拒绝绝对路径、路径穿越、symlink escape、目录、
未知 content type、跨 Run 引用和完整性不匹配。

#### Scenario: 加载有效截图
- **WHEN** 客户端请求属于该 Run 且 hash 有效的 PNG artifact identity
- **THEN** resolver 从受控根返回正确 content type 和内容，不暴露宿主存储路径

#### Scenario: 路径穿越引用
- **WHEN** 导入包或请求尝试使用 `..`、绝对路径或逃逸受控根的 symlink
- **THEN** 系统拒绝导入或读取，并返回不包含真实宿主路径的安全错误

#### Scenario: 跨 Run 猜测 artifact identity
- **WHEN** 客户端使用 Run A 的 URL 请求只属于 Run B 的 artifact identity
- **THEN** resolver 不返回该 artifact，也不泄露其 metadata

### Requirement: Replay 查询和导出 API
Studio HTTP SHALL 提供可分页 Replay 列表、按 run identity 获取 envelope、按 opaque
identity 获取 artifact 以及下载版本化 Replay bundle 的只读接口。响应 SHALL 使用统一
安全错误 envelope，列表 MUST 使用稳定排序和 opaque cursor。

#### Scenario: 分页查询 Replay
- **WHEN** 客户端使用上一页 opaque cursor 请求下一页
- **THEN** 服务按稳定 `(imported_at, run_id)` 顺序返回无重复、无遗漏的已导入记录

#### Scenario: 导出 Replay bundle
- **WHEN** 用户下载一个已导入 Replay
- **THEN** bundle 使用安全相对成员、schema、size/hash 和 manifest，可由公共 verifier
  验证且不包含宿主绝对路径

#### Scenario: 默认导出遇到隐藏 Prompt
- **WHEN** Replay metadata 记录存在隐藏 Prompt evidence，用户使用默认导出
- **THEN** bundle 排除 Prompt 内容并在 manifest 明确记录 excluded，不通过其他日志成员
  间接泄露

### Requirement: Evidence 安全 canary
Replay 导入、repository、HTTP DTO、artifact metadata 和导出 MUST NOT 保存或返回 raw
API key、token、password、authorization header、原始 Android serial、未经批准的宿主
绝对路径或 live runtime object。拒绝或 redaction MUST 保留结构化、安全的 provenance。

#### Scenario: 导入包含多类安全 canary
- **WHEN** fixture 同时包含已知 secret、raw serial、绝对路径和不可序列化 live object
- **THEN** 持久化目录、SQLite、HTTP 响应和导出扫描均找不到原始 canary，同时能看到
  对应拒绝或 redaction diagnostic

### Requirement: 终止 live Run 必须直接注册为原生 Replay
Studio Run finalizer SHALL 从 run-owned snapshot、durable journal、RunResult 和 managed
artifact inventory 原子建立原生 `ReplayEvidenceEnvelope`。该路径 MUST NOT 伪装成
legacy Benchmark 导入，不得重新扫描 `temp/` 或要求用户手工导入刚完成的 Run。

#### Scenario: live Run 成功结束
- **WHEN** RunResult、journal 和 artifact inventory 已完成安全校验
- **THEN** finalizer 直接创建同 run identity 的原生 Replay，History 可立即查询

#### Scenario: live Run 没有 Benchmark context
- **WHEN**普通 Agent Run 终止
- **THEN** Replay provenance 标记 native Studio Run，Benchmark context 保持 absent

### Requirement: 失败和中断 Run 必须保留可验证前缀
当 execution、cancel、device、evidence 或 service restart 导致非成功终止时，Replay
SHALL 保存截至 journal high-water mark 的 snapshot、events、artifacts、availability、
integrity diagnostics 和正式 RunResult。Finalizer MUST NOT 为缺失尾部、未执行节点或
未捕获证据构造虚假成功事实。

#### Scenario: activation 中途设备失败
- **WHEN** device failure 前已经提交 observation、activation 和 action evidence
- **THEN** Replay 包含已验证前缀及 DEVICE_FAILURE，后续 evidence 标记真实 availability

#### Scenario: 服务重启收口
- **WHEN** recovery 将旧进程的 Run 标记为 service-restarted failure
- **THEN** Replay 保留旧 high-water mark 和 interruption diagnostic，不重放旧 activation

### Requirement: live evidence 提升必须保持 artifact identity 与默认敏感策略
运行期间已分配的 opaque artifact identity、hash、causal identity 和 availability SHALL
在 Replay 注册后保持稳定。提升过程 MUST 原子发布 Replay metadata；默认 Replay API 和
export MUST 继续排除 hidden Prompt，并允许读取符合策略的 screenshot、UI XML 和完整模型
响应。

#### Scenario: Run 页面转入 Replay
- **WHEN**客户端已加载一个 screenshot artifact，随后 Run terminal 并注册 Replay
- **THEN**同一 run/artifact identity 继续解析到同一验证内容，无需复制为新身份

#### Scenario: Replay 注册中断
- **WHEN**finalizer 在提交 Replay metadata 前失败
- **THEN**半成品 Replay 不对 History 可见，Run 保留 evidence-finalization failure 供恢复

### Requirement: Terminal Benchmark TaskRun 必须原子注册为 native Replay
Benchmark Experiment finalizer SHALL 使用已持久的 Experiment definition snapshot、
TaskRun journal slice、Agent RunResult、Benchmark phase/evaluation results 和 managed
artifact inventory 构建 `ReplayEvidenceEnvelope`，并通过显式 publisher 原子注册
具有独立 native Benchmark provenance 的 Replay。Publisher MUST 为相同不可变
publication 输入返回相同稳定 Replay identity，但 TaskRun resource MUST 显式保存并
返回该 identity、availability 和 resource link；客户端 MUST NOT 从 TaskRun ID、
文件名、标题或本地目录推断 Replay identity。Replay metadata、Replay artifact index、
TaskRun Replay mapping、publication availability 和对应 journal facts MUST 在同一
持久 transaction 中变为可见。

#### Scenario: Benchmark TaskRun 正常终止
- **WHEN**TaskResult、journal 和 artifact inventory 已完成安全与 integrity 校验
- **THEN**finalizer 原子注册同时保留 Agent 与 Benchmark context 的 native Replay，TaskRun 查询返回显式 Replay identity 与 link

#### Scenario: Replay 注册中途失败
- **WHEN**publisher 在统一 metadata transaction 提交前失败
- **THEN**半成品 Replay 不进入 History，TaskRun result 保持可读且 Replay availability 标记 failed

#### Scenario: 相同 publication 重试
- **WHEN**publisher 以相同 Experiment、TaskRun、result fingerprint、journal high-water mark 和 artifact inventory 重试
- **THEN**服务返回同一 Replay identity 且不创建第二个 History 条目、artifact identity 或 terminal event

#### Scenario: Replay identity 冲突
- **WHEN**既有 Replay identity 对应不同 provenance 或不同不可变 publication fingerprint
- **THEN**publisher 拒绝注册并记录安全 conflict diagnostic，不覆盖既有 Replay 或 TaskResult

### Requirement: Benchmark native Replay 必须保留失败或中断前缀
无论 TaskRun PASS、FAIL、INVALID、SKIPPED、cancel、device/evidence failure 或 service
interruption，Replay finalization SHALL 保留截至 task journal high-water mark 的已确认
snapshot、events、Benchmark phases、Agent status、Benchmark outcome（若正式产生）、
artifacts、availability 和 diagnostics。系统 MUST NOT 为未执行 phase、缺失尾部或取消
前未产生的 outcome 构造虚假事实。

#### Scenario: Agent 期间设备失败
- **WHEN**失败前已提交 observation、action 和 Benchmark setup evidence
- **THEN**Replay 包含这些 verified facts、Agent DEVICE_FAILURE 和真实的后续 availability

#### Scenario: TaskRun 启动前取消
- **WHEN**TaskRun 没有 Agent RunResult 或 Benchmark outcome
- **THEN**若系统为审计创建 Replay，则 envelope 明确标记 not_produced；否则 TaskRun 标记 Replay not_produced，不伪造空成功运行

### Requirement: Experiment TaskRun 提升必须保持 artifact 与安全 identity
从 live Experiment evidence 首次纳入 managed storage 时，系统 SHALL 为每个允许的
artifact 分配 Experiment/TaskRun-scoped opaque identity，并记录 hash、causal
identity、Benchmark/Agent identity 和 availability。Report、TaskRun、bundle 与
native Replay MUST 复用该已提交 identity 和同一验证内容；普通 Replay API 与 export
MUST 继续排除 hidden Prompt，并仅允许读取策略允许且实际捕获的 screenshot、UI XML
和完整模型响应。提升 MUST NOT 为 Replay 复制 artifact 为竞争性新身份，也 MUST NOT
重新扫描 `temp/benchmark-runs`、workspace 或未声明目录。

#### Scenario: TaskRun artifact 提升后打开 Replay
- **WHEN**TaskRun publication 已为 screenshot 提交 opaque artifact identity，随后 native Replay 注册
- **THEN**TaskRun、bundle manifest 与 Replay descriptor 引用相同 identity、hash 和内容，不产生第二份竞争性 artifact

#### Scenario: Monitor 已加载 screenshot
- **WHEN**TaskRun terminal 后用户从 Monitor 进入 Replay
- **THEN**同一 artifact identity 解析到相同 hash/content，且 Replay 新增持久 envelope 而非复制文件身份

#### Scenario: 未捕获完整模型响应
- **WHEN**Runtime 没有产生经过安全处理的完整模型响应 artifact
- **THEN**Replay 与 export 标记 not_produced，不从 event summary 或日志猜测并构造响应内容

#### Scenario: Legacy 与 native 路径并存
- **WHEN**系统同时存在旧本地 Benchmark import 和新 native TaskRun Replay
- **THEN**二者使用显式 provenance/adapter 区分，native 路径不伪装成 legacy import

### Requirement: Startup recovery 必须保持 Benchmark Replay 身份与缺失事实
Startup recovery SHALL 复用 Stage 5.2C-2 已提交的 native Benchmark Replay mapping、
publication fingerprint 和 managed artifact identities。若 coordinated publication
尚未提交，publication-only recovery MAY 以相同 immutable input 调用 publisher；若
Replay mapping 已提交，recovery MUST NOT 重新注册、复制 artifact 或创建第二个 History
entry。没有 immutable TaskResult 或可验证执行前缀的 TaskRun MUST 保持 Replay
`not_produced`，不得为 recovery 审计构造空成功 Replay。

#### Scenario: Replay 已提交但 Experiment 未终结
- **WHEN** 进程在 Replay mapping/publication transaction 后、Experiment terminal transition 前退出
- **THEN** recovery 复用既有 Replay identity/link 并仅完成 Experiment finalization

#### Scenario: publication-only recovery 注册 Replay
- **WHEN** immutable TaskResult 与 publication input 已提交而 Replay mapping 尚未提交
- **THEN** publisher 返回由相同 fingerprint 导出的稳定 Replay identity，TaskRun、History 与 artifact index 只出现一次

#### Scenario: running Experiment 被 interruption 收口
- **WHEN** recovery 无法证明 in-flight Agent/设备动作的完成边界
- **THEN** 已有 committed Replay/evidence prefix 保持可读，系统不重放 activation、不补造缺失尾部或第二个 Replay

#### Scenario: finalizing 没有 TaskResult
- **WHEN** recovery 依据 no-result TaskRun terminal facts 完成 Experiment
- **THEN** TaskRun Replay availability 保持 `not_produced` 或既有明确 failure，不创建 History entry

#### Scenario: 已提交 Replay 输入冲突
- **WHEN** recovery 输入与既有 Replay provenance 或 immutable publication fingerprint 不同
- **THEN** publisher 拒绝覆盖并记录安全 conflict diagnostic，既有 Replay、artifact 与 TaskResult 保持不变

### Requirement: Replay acquisition 与 source environment provenance 必须分离
Replay evidence SHALL separately identify how the Replay was acquired and the execution
environment evidenced by its source facts. Native projection, native package import, legacy
import, explicit real-Android excerpt, and fake contract fixture MUST NOT overwrite whether the
source environment was real Android, fake device, or unverified. When source environment facts
are absent, Replay MUST report `unverified` rather than infer from artifact appearance, profile
identity, title, URL, or import option.

#### Scenario: Native projection of fake Benchmark TaskRun
- **WHEN**a fake-device Studio Benchmark TaskRun is promoted to native Replay
- **THEN**Replay records projection acquisition and preserves fake-device source environment

#### Scenario: Native projection of future real Android TaskRun
- **WHEN**a TaskRun with verified real-Android source facts is promoted to native Replay
- **THEN**Replay records projection acquisition and preserves real-Android source environment without claiming a new fresh execution

#### Scenario: Historical evidence has no environment fact
- **WHEN**a legacy or native import contains no verified execution-environment provenance
- **THEN**Replay records its truthful import acquisition and `unverified` source environment

#### Scenario: Replay DTO is scanned for private target data
- **WHEN**a Replay envelope, list item, artifact inventory, or export is serialized
- **THEN**it contains no raw serial, private binding fingerprint, ADB argument, trusted configuration path, or live device handle

