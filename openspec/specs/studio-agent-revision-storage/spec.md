# studio-agent-revision-storage Specification

## Purpose
TBD - created by archiving change implement-studio-agentgraph-1-1-builder. Update Purpose after archive.
## Requirements
### Requirement: 可替换 AgentDocumentRepository
系统 SHALL 定义独立于数据库实现的 `AgentDocumentRepository` 合同，管理 Agent metadata
和不可变 Agent revision。Repository 方法、DTO、pagination、identity、conflict 和
transaction outcome MUST NOT 暴露 SQLite rowid、PRAGMA、dialect-specific JSON operator
或数据库连接对象。

#### Scenario: 使用 SQLite 默认实现
- **WHEN** 本地 Studio 按默认配置启动
- **THEN** AgentDocumentService 通过 Repository 合同使用 SQLite，而不在 HTTP 或
  compiler 层执行 SQL

#### Scenario: 未来替换 PostgreSQL
- **WHEN** 未来实现通过相同 contract tests 的 PostgreSQL adapter
- **THEN** application service 和前端 API DTO 无需改变

### Requirement: 版本化 SQLite schema
首版 SHALL 在操作系统用户数据目录中按 workspace identity 创建 SQLite 数据库，并
通过版本化 migration 管理 schema。数据库至少 SHALL 保存 Agent、immutable revision
和 migration metadata。默认位置 SHALL 可配置，测试 MUST 能使用显式临时目录。

#### Scenario: 首次启动
- **WHEN** workspace 尚无 Studio 数据库
- **THEN** migration runner 原子创建当前 schema，且不在 Git 工作区写数据库

#### Scenario: 服务重启
- **WHEN** 用户保存 revision 后重启 Studio 服务
- **THEN** 同一 workspace identity 能重新加载 Agent、current revision 和 compile
  snapshot

### Requirement: Agent 与 Revision 身份分离
Agent SHALL 具有稳定 agent ID、名称、创建/更新时间和 current revision pointer。
Revision SHALL 具有稳定 revision ID、agent ID、ordinal、parent/base revision、
immutable StudioFlowDocument 和创建时间。一经提交的 revision MUST NOT 被原地修改。

#### Scenario: 修改名称
- **WHEN** 用户重命名 Agent
- **THEN** Agent metadata 更新，但既有 revision document 和 canonical hash 不变

#### Scenario: 保存新 revision
- **WHEN** 用户基于 current revision 保存修改后的 document
- **THEN** Repository 新增 immutable revision 并原子更新 Agent current pointer

### Requirement: Optimistic revision conflict
保存 revision SHALL 要求调用者提供 `baseRevisionId`。若它与 Agent current revision
不一致，系统 MUST 返回结构化 conflict，并 MUST NOT 覆盖 current pointer 或保存成
伪线性历史。

#### Scenario: 两个页面同时保存
- **WHEN** 页面 A 先基于 revision 1 保存 revision 2，页面 B 随后仍基于 revision 1 保存
- **THEN** 页面 B 收到 conflict，revision 2 保持 current，系统不执行 last-write-wins

### Requirement: 无效草稿可保存
每个 revision SHALL 保存 compiler snapshot，包括 `valid` 或 `invalid` status、
diagnostics 和 source map。只有 valid revision SHALL 保存 canonical AgentGraph JSON
和 canonical hash；invalid revision MUST NOT 伪造 hash 或被标记为可运行。

#### Scenario: 保存未连接完成的草稿
- **WHEN** StudioFlowDocument 严格结构有效但 AgentGraph compile 返回 diagnostics
- **THEN** 系统保存 invalid revision、完整 authoring document 和 diagnostics，且不
  保存 AgentGraph/hash

#### Scenario: 保存有效图
- **WHEN** compile 产生有效 AgentGraph 1.1
- **THEN** revision 保存与该 document 对应的 immutable graph JSON 和 canonical hash

### Requirement: Presentation revision 与 semantic identity 分离
只修改 presentation SHALL 可以产生新 document revision，但 valid compile snapshot
的 canonical hash SHALL 与前一语义相同 revision 相同。系统 MUST NOT 以 canonical
hash 代替 revision ID。

#### Scenario: 移动画布节点后保存
- **WHEN** 用户只移动节点并保存
- **THEN** 创建新 revision ID，两个 revision 的 AgentGraph canonical hash 相同

### Requirement: Agent 列表与 Revision 读取
系统 SHALL 支持稳定排序和有界 pagination 的 Agent list、按 agent ID 读取 current
metadata、按 revision ID 读取 immutable document/compile snapshot。响应 MUST NOT
包含 SQLite 路径、数据库连接信息或 live object。

#### Scenario: 直接打开旧 revision
- **WHEN** 用户请求属于该 Agent 的历史 revision
- **THEN** 系统返回该 revision 的文档与 compile snapshot，且不改变 current pointer

### Requirement: 持久化安全
Agent document、revision、diagnostics 和 compile snapshot MUST NOT 保存 raw API key、
token、password、authorization header、live component/model/device object、原始
Android serial 或未经批准的宿主绝对路径。Component secret SHALL 使用 SecretRef 或
批准 placeholder。

#### Scenario: raw secret 写入
- **WHEN** document params 尝试包含 raw secret 字段
- **THEN** DTO/compiler/save service 在 transaction 前拒绝或转换为显式安全诊断，原始
  secret 不进入 SQLite

### Requirement: Agent Revision HTTP contract
系统 SHALL 提供 Agent list/create/get/rename、revision get/save 的版本化 HTTP DTO。
Malformed request SHALL 返回 400，缺失 Agent/Revision 返回 404，revision conflict
返回 409，内部失败返回不泄露路径或 secret 的稳定 500 error envelope。

#### Scenario: 创建 Agent
- **WHEN** 用户提交合法名称和可选初始 schema 2 document
- **THEN** API 返回稳定 agent ID 和初始 current revision/compile status

#### Scenario: 保存 conflict
- **WHEN** save request 的 base revision 已过期
- **THEN** API 返回 409、current revision identity 和安全 conflict code，不覆盖数据

