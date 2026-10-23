# studio-benchmark-report-view Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-report-view-5-4b. Update Purpose after archive.
## Requirements
### Requirement: Single-Experiment Report 路由必须从持久资源重建
Studio SHALL 提供 `/experiments/:experimentId/report` 路由，并从 route identity、
Experiment detail、TaskRun page、artifact inventory 和显式 report links 重建报告。
页面 SHALL 明确区分 loading、not found、non-terminal、report pending、
not-produced、failed、missing、corrupt 和 available；它 MUST NOT 依赖 Monitor SSE
session、先前页面访问、Zustand 中的资源副本或浏览器构造的 artifact URL。

#### Scenario: 刷新可用报告
- **WHEN**用户刷新一个具有 available report link 的终态 Experiment 报告路由
- **THEN**页面重新查询持久资源和正式 report，并在不依赖 Monitor 内存的情况下恢复报告

#### Scenario: Experiment 尚未终态
- **WHEN**报告路由加载到 accepted、starting、running、cancelling 或 finalizing Experiment
- **THEN**页面展示当前 lifecycle 和返回 Monitor 的动作，不尝试把尚未提交的 report 推断为可用

#### Scenario: Report 已闭合为损坏
- **WHEN**Experiment detail 或重新查询后的 inventory 声明 report missing 或 corrupt
- **THEN**页面保留 Experiment identity 与 publication failure 事实，不展示旧缓存内容或猜测下载地址

### Requirement: Report 必须校验跨资源身份并保持三轴事实独立
Studio SHALL 将正式 Experiment/TaskRun reports 与所选 Experiment、Studio TaskRun
resource 和 immutable definition identities 进行一致性校验。页面 SHALL 分别展示
service lifecycle、Agent status 和 Benchmark outcome；它 MUST NOT 从其中任一轴推导、
覆盖或美化另外两个轴。

#### Scenario: 三轴结果不同
- **WHEN**TaskRun service lifecycle 为 completed、Agent status 为 failed 且 Benchmark outcome 为 invalid
- **THEN**页面分别展示三个原始事实，不合并为单一 success/failure 标签

#### Scenario: Definition identity 冲突
- **WHEN**正式 report 的 Benchmark plan、Experiment protocol、Agent graph 或 task instance identity 与持久资源不一致
- **THEN**对应报告组件失败关闭并显示结构化 integrity/compatibility 状态，不展示冲突的 Evaluation evidence

#### Scenario: Core run 与 Studio TaskRun 无法唯一连接
- **WHEN**run summary 的 Core run identity 没有且仅有一个同 Experiment 的 Studio TaskRun 对应
- **THEN**该 summary 显示不可选择或不一致，页面不按列表位置、文件名或 Agent 名称猜测匹配

### Requirement: TaskRun 导航和选择必须稳定且可深链接
Report SHALL 按服务返回的稳定计划顺序展示复数 TaskRun rail。显式选择 SHALL 使用
Studio TaskRun identity 编码到 URL 查询参数中；默认选择 SHALL 是确定性的，且无效、
越界或跨 Experiment 的选择 MUST 被拒绝或安全回退而不改变权威 report。

#### Scenario: 没有显式选择
- **WHEN**Experiment 具有一个或多个可连接 TaskRun 且 URL 没有选择参数
- **THEN**页面确定地选择稳定顺序中的第一项并展示其事实

#### Scenario: 刷新选中的 TaskRun
- **WHEN**用户选择一个 TaskRun 后刷新或复制报告深链接
- **THEN**页面从 URL 中的 Studio TaskRun identity 恢复同一选择

#### Scenario: 深链接选择属于其他 Experiment
- **WHEN**URL 查询参数引用另一个 Experiment 的 TaskRun
- **THEN**页面不加载该 TaskRun 的 report 或 evidence，并展示安全的无效选择状态或回退

### Requirement: Evaluation Tree 必须递归、可审计且不会冒充自动诊断
Report SHALL 以可展开的层级视图展示完整且已通过有界 parser 的 Evaluation Tree，
保留 node path、name、status、`isPass` 三态、reason、score、duration、
short-circuit、aggregation、evaluator result 和子节点。展开状态 SHALL 使用稳定且
唯一的 node path；页面 MAY 帮助人工定位失败分支，但 MUST NOT 声称自动根因诊断。

#### Scenario: 三态 Evaluation 判断
- **WHEN**同一树中节点的 `isPass` 分别为 true、false 和 null
- **THEN**页面分别显示通过、未通过和未判定，不把 null 转换为失败

#### Scenario: 短路节点
- **WHEN**一个 composite node 声明 short-circuited 且部分子节点为 skipped 或 unverified
- **THEN**页面展示短路事实和子节点原始状态，不伪造未执行节点的 score 或 reason

#### Scenario: 重复 node path
- **WHEN**一个已解析的 Evaluation Tree 包含两个相同 path
- **THEN**视图投影拒绝该树或对应组件，不使用数组索引制造不稳定的展开身份

#### Scenario: 大型但合法的树
- **WHEN**Evaluation Tree 在既定深度和节点上限内但包含大量折叠后代
- **THEN**页面只挂载当前展开的可见分支，同时保留用户继续展开全部已验证节点的能力

### Requirement: Evidence 描述和 Replay handoff 必须使用权威作用域
Report SHALL 对 leaf evaluator evidence 展示 bounded descriptor、availability、
safe value summary 和 causal artifact reference，并仅在同作用域持久 TaskRun resource
声明 native Replay available 时提供显式 Replay 动作。5.4B MUST NOT 打开任意 artifact
body、构造宿主路径、实现下载/导出或把 live event buffer 当作 Replay。

#### Scenario: Leaf evidence 可描述但不可读取
- **WHEN**evaluator result 包含 evidence descriptor 但对应 artifact 不可读或本阶段不提供 viewer
- **THEN**页面展示 kind、availability 和安全摘要，不提供失效内容链接或把缺失证据判为 Benchmark failure

#### Scenario: Replay 可用
- **WHEN**所选 Studio TaskRun resource 提供可用 native Replay identity 或 safe link
- **THEN**用户可显式进入既有 Replay route，由该 route 独立重新加载持久 evidence

#### Scenario: Replay 不可用
- **WHEN**Core report 声明 trajectory reference 但 Studio TaskRun 没有权威 Replay capability
- **THEN**页面展示 Replay unavailable，不从 Core reference 构造 Replay URL

### Requirement: 局部失败不能抹去其余已验证事实
Report SHALL 为 Experiment resource、TaskRun list、artifact inventory、Experiment
report、Experiment-level metrics/comparisons、选中 TaskRun report、Evaluation Tree
和 Replay capability 维护独立的组件状态。一个下游组件失败 SHALL 只阻断依赖它的
事实，同时保留其余已经通过作用域和完整性校验的事实以及显式重试路径。Experiment
metrics/comparisons SHALL 只依赖正式 Experiment report，不得随 TaskRun 选择变化或
因选中 TaskRun detail、Evaluation、inventory content 或 Replay 的局部失败而消失。

#### Scenario: TaskRun report 不可用
- **WHEN**Experiment report 有效但所选 TaskRun 的 task_report 缺失、失败或 causal reference 不一致
- **THEN**页面继续展示 Experiment identity、publication、run summaries 和 Experiment metrics/comparisons，只让所选详情组件显示局部错误

#### Scenario: TaskRun query 暂时失败
- **WHEN**Experiment report 可读但 TaskRun resource query 暂时失败
- **THEN**页面保留正式 report summaries、Experiment metrics/comparisons 和 Evaluation-independent facts，同时禁用需要权威 Studio TaskRun 的 Replay 与三轴对应项

#### Scenario: Evaluation 为空
- **WHEN**一个合法 TaskRun report 的 Evaluation 为 null
- **THEN**页面展示 Evaluation unavailable，并保留 Experiment metrics/comparisons、stages、outcome、identity 和 Replay facts

#### Scenario: 切换选中 TaskRun
- **WHEN**用户在同一 Experiment Report 中切换 URL-owned Studio TaskRun selection
- **THEN**Experiment outcome、metrics、comparisons、fairness 和 significance boundary 保持不变，只更新选中 TaskRun 的 detail、Evaluation 和 Replay

#### Scenario: Experiment report 不可用
- **WHEN**正式 Experiment report 为 pending、failed、missing、corrupt、compatibility 或 integrity state
- **THEN**Experiment metrics/comparisons 显示对应不可用状态且不消费旧数据，同时页面保留不依赖正式 report 的 Experiment resource facts

### Requirement: Report 前端必须遵守 FSD-lite 和安全展示边界
Report page、workbench、interaction feature 与 reporting/experiment entities SHALL
遵守 `app → pages → widgets → features → entities → shared` 依赖方向并通过公开入口
导入。服务端资源 SHALL 由 TanStack Query 管理，URL SHALL 拥有稳定选择，局部展开状态
SHALL 留在组件或 feature；report、Evaluation、evidence、secret、device handle 和宿主
路径 MUST NOT 写入 localStorage 或未清理日志。

#### Scenario: Import boundary 检查
- **WHEN**TypeScript 与 ESLint 检查新的 Report slices
- **THEN**跨 slice import 只沿允许方向并经过公开 API

#### Scenario: 安全错误展示
- **WHEN**report loader 或 parser 返回 compatibility、integrity 或 availability failure
- **THEN**页面只展示结构化安全消息和允许的 identity，不渲染原始响应、绝对路径、secret 或异常堆栈

