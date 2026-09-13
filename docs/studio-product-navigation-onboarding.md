# Studio 产品导航与首次使用

本文记录 `redesign-studio-product-navigation-onboarding` 实施后已经验证的产品信息架构、
路由兼容、安全边界和验收证据。它描述的是 2026-08-04 的实现事实，不扩大 Agent、
Run、Benchmark 或设备能力声明。

## 用户入口与信息架构

Studio 的稳定全局入口现在按用户对象和研究生命周期组织：

| 全局入口 | 用户问题 | 正式路由 |
| --- | --- | --- |
| 首页 | 我从哪里开始、最近做过什么、运行环境是否可用？ | `/` |
| Agents | 我要创建、导入或继续设计哪个 Agent？ | `/agents` |
| Experiments | 我要怎样建立和查看 Benchmark Experiment？ | `/benchmarks`、`/experiments/*` |
| Runs | 普通 Agent Run 和 Benchmark Experiment 的结果在哪里？ | `/history`、`/experiments` |
| 设置 | Provider、SecretRef identity、安全 Device Profile 和显示偏好是什么状态？ | `/settings` |

路由仍然是资源边界，而不是把不同资源合并成一种 UI 数据模型。普通 Run History
与 Experiment History 使用各自的 DTO、查询、过滤器、游标和状态词；全局 Runs 只提供
两个清楚的入口。Benchmark Catalog、Composer、Monitor、Report 和 Authoring 继续使用
既有资源和正式路由。

打开 Agent 后，`/agents/:agentId/design`、`/agents/:agentId/run` 和
`/agents/:agentId/runs` 共享安全的 Agent 名称和 `设计 / 运行 / 运行记录` 导航，但
Builder draft、当前 Run、History query 和 Replay cursor 仍由原页面所有者管理。
Agent Run 的无查询路由从 Agent 资源解析当前 immutable revision；显式 `revisionId`
和 `runId` 查询仍受互斥校验。Replay 仍是全局、只读的 Run 资源，仅在 snapshot 包含
有效 Agent identity 时显示返回 Agent 的上下文。

## 首次使用与继续工作

首页不再重复完整 Agent 目录。它提供一个主要的“创建 Agent”动作、一个正式示例入口、
可跳过/可恢复的研究闭环提示，以及三个彼此隔离的有界最近工作区域：Agents、可回放的
普通 Runs、Benchmark Experiments。任一区域加载或失败不会阻断其他区域。

引导的步骤是：

```text
选择/创建 Agent → 设计并验证 → 运行任务 → 检查结果 → Replay 与迭代
```

引导只把隐藏/重新打开偏好写入 localStorage。Agent、revision、readiness、task、Run、
Experiment、证据和完成状态均不写入浏览器偏好，也不会由引导伪造。Runtime Readiness
摘要只展示安全的 Provider 数量、SecretRef presence、Device Profile 数量和正式诊断；
不显示 secret 值、ADB serial 或宿主路径。

Agent Library 是唯一完整 Agent 目录。它支持有界读取/搜索、空白创建、后端正式模板、
Schema 2 严格导入和 Schema 1 显式迁移。成功创建后直接进入对象的 Design 路由。正式
Mobile Agent 示例中的 role-bound component 按后端 AgentGraph 合同接受 `role` 或
`contract`，不会为 memory 等角色组件发明服务合同。

截至 2026-08-04，Library 的首用和回访层次进一步收敛为：

- 空目录将“从示例开始”作为唯一主要动作，空白创建和 JSON 导入是次级、可发现动作；
  不在默认画面展示 Schema、模板或迁移细节。
- 有已保存 Agent 时，最新且存在 current revision 的 Agent 以“继续上次工作”突出，
  其余对象保留为紧凑、可搜索的正式目录；搜索时不重复展示该突出卡片。
- 同名 Agent 以安全的更新时间/创建时间辅助区分，raw Agent ID 只在“技术详情”中显示。
- 创建入口由 URL 查询 `create=blank`、`create=example`、`create=choose`、`create=import`
  表示；关闭时只移除该参数并保留其他查询。空白、示例和导入诊断都在明确选择后才展开。
  这些入口只执行既有的 Agent 保存、模板读取或导入预检，不会启动 Run、连接设备、解析
  secret 或调用模型。

## 渐进披露

- Builder 顶层只保留 Validate、Save revision 和满足既有 gate 时的 Run；Save As、
  Import、Export、Load Revision、Reset 和技术身份进入“更多操作”。
- 首页、Agent Library 和 Agent 工作区默认展示安全名称与产品状态；raw Agent/revision
  identity 进入显式“技术详情”。
- Experiments 首页优先展示新建、继续、结果三个任务入口；Benchmark Catalog 和
  Authoring 明确标为高级能力。
- Experiment Composer 的视觉和 DOM 顺序为 Agent → Benchmark/Task →
  Protocol/Profile → Preview/创建；validate、preview、create DTO 和副作用 gate 未改变。

### 2026-08-05：Agent Library 的研究连续性层级

`/agents` 仍是唯一的完整 Agent 目录；本次只收敛已保存 Agent 场景的呈现，不改变
Agent API、搜索、创建、导入、路由或 immutable revision 语义。页面以“继续上次工作”为
首要任务：最新的可继续 Agent 通过克制的蓝色左侧连续性标记和浅蓝背景提示，并把
“继续设计”设为唯一实心操作。“新建 Agent”降为标题区的描边操作，完整目录则保留为
安静、可搜索的索引。

目录仍包含最近 Agent，搜索只过滤目录而不隐藏继续工作的入口。默认卡片只显示名称和
更新时间（同名时保留安全的创建时间区分）；运行状态、组件数量、技术身份和“技术详情”
不进入首屏。卡片整体及继续按钮都进入既有 Design 路由。空目录、读取失败、无结果和
创建/导入 dialog 仍使用原有状态与 URL-owned `create` 参数。

视觉使用页面范围内的白色画布、既有浅色/深色语义 token、#339CFF 强调色以及全局
Times New Roman / 微软雅黑字体映射；不新增营销式统计卡、状态标签或动画。窄屏时标题
操作纵向堆叠、目录退为单列，并保留可见键盘焦点与 reduced-motion 行为。

## API 结论与最小后端改动

既有 typed Agent、Experiment History 和 Runtime Readiness API 已足以支持有界首页。
普通最近工作使用已经持久化且可回放的 Replay summary，因此不会把尚未形成 Replay 的
活动 Run 描述为可检查结果。

唯一实际缺口是 Agent-scoped ordinary history。`GET /api/studio/replays` 新增可选、精确、
有界的 `agentId` 查询；HTTP、应用服务、Repository protocol 和 SQLite 查询共同保持
新到旧排序及原 cursor 语义。Agent identity 必须匹配稳定标识符规则，SQL 使用参数绑定。
没有新增数据库列、迁移、聚合 truth 或写操作。

## 兼容路由

- `/builder?...` 确定性替换为 `/agents?...`，保留查询，不选择任意 Agent。
- `/benchmark?...` 确定性替换为 `/benchmarks?...`，保留查询。
- `/history`、`/experiments` 及所有 Agent、Run/Replay、Benchmark、Experiment 深链保持
  可直接加载、刷新和复制。
- 未知地址显示安全 404 和返回首页动作；资源身份不匹配仍由对应 typed 页面处理。

## 验证证据

自动化验证：

```bash
cd studio
npm run lint
npm test
npm run build

cd ..
conda run -n unimobile --no-capture-output \
  pytest -q tests/studio/test_replay_backend.py \
  tests/studio/test_runtime_readiness.py tests/studio/test_http_api.py
```

结果为 ESLint 通过、111 个 Vitest 文件共 480 个测试通过、TypeScript 与 Vite 生产构建
通过，以及 24 个后端/HTTP 测试通过。Agent Library 的 focused 测试覆盖空目录、回访
继续、同名安全区分、无结果搜索、读取/创建失败、导入迁移披露、直接 URL、Escape/
focus-return 与无 Run/设备/secret 副作用。`test_runtime_readiness.py` 包含不构造组件或设备、
旧拓扑无副作用阻断、unready Run 在持久副作用前拒绝和安全 HTTP 投影 canary。

真实浏览器验收覆盖：已保存 Agent 的继续入口、创建选择层、`create=blank` 与
`create=import` 深链、无结果搜索，以及浅色/深色主题；空目录状态由无设备 DOM fixture
覆盖。此前的浏览器验收还覆盖：无设备首次首页、正式示例入口、返回用户 Agent Library、
Agent Design → current-revision Run、unready 拦截、普通/Experiment History 切换与 Back
查询恢复、兼容路由查询保留、未知路由、深层 Authoring 当前域、Experiment Composer
顺序、浅色/深色主题，以及仓库 no-device fixture 的 Experiment History → Monitor →
Report 只读链路。fixture 明确显示没有实时设备证据，不以历史截图冒充当前证据。

2026-08-05 的 Agent Library 收敛额外通过了 focused Library 测试（6 个）、完整 Studio
Vitest、TypeScript typecheck、ESLint 和生产构建；无设备浏览器验收覆盖有 Agent 的继续/
目录、无结果搜索、浅色与深色主题，以及 390px 窄屏布局。验证只读取现有列表资源，不会
创建 Agent、启动 Run、连接设备、解析 secret 或调用模型。

## 仍然存在的边界

- 首页普通 Runs 只列已经进入 Replay index 的结果，不承担活动 Run 监控。
- 引导不会自动推断所有步骤“已完成”；它避免建立第二套生命周期真相。
- Agent 名称不是唯一 identity；重复名称仍以独立资源存在，raw ID 仅在技术详情显示。
- Library 不会自动选择、修改或运行 Agent；“继续上次工作”仅在 current revision 存在时
  出现，并始终进入 Design。导入仍取决于既有 Schema 2/Schema 1 后端合同与文件选择。
- 本变更没有增加多 Agent/多 Task Worker cardinality、设备兼容范围、实时视频、账户系统、
  自动失败诊断、跨资源联合游标或统计显著性声明。
- 设置中的快捷键、账户和关于区域仍有历史占位内容；它们现在可发现，但不代表对应后端
  能力已经实现。
