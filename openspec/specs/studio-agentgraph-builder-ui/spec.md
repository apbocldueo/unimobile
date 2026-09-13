# studio-agentgraph-builder-ui Specification

## Purpose
TBD - created by archiving change implement-studio-agentgraph-1-1-builder. Update Purpose after archive.
## Requirements
### Requirement: 前端分层与依赖边界
Stage 1 Studio frontend SHALL 使用
`app → pages → widgets → features → entities → shared` 的向下依赖方向。AgentGraph、
AgentRevision 和 ComponentCatalog entity MUST NOT 导入 XYFlow 或 feature UI；跨 slice
使用 SHALL 经过 slice 的最小公开 API。新业务代码 MUST NOT 继续写入无所有权的根级
`domain`、`modules`、`services`、`stores` 或通用业务 `components` 大桶。

#### Scenario: 逆向依赖进入提交
- **WHEN** entity 导入 feature、shared 导入业务 entity 或 AgentGraph entity 导入
  `@xyflow/react`
- **THEN** import-boundary lint 失败并阻止该结构被视为 Stage 1 完成

#### Scenario: 增量迁移旧页面
- **WHEN** Stage 1 只修改 Builder 依赖的旧模块
- **THEN** 修改的职责迁入正式 slice，未触及的 Benchmark、History、Run 和 Replay
  可以暂时保留且行为不被无关重写

### Requirement: 前端状态按生命周期归属
后端 Agent、Catalog、revision 和 compile request cache SHALL 由 server-state query
层管理；当前 document draft、selection、dirty、nested path 和编辑 command SHALL
由 Builder client store 管理；agent identity SHALL 由 URL 管理；短暂视图状态 SHALL
留在组件；theme、pane size 等非语义偏好 MAY 写入 localStorage。任何 store MUST NOT
建立与这些所有者竞争的第二份完整真相。

#### Scenario: 保存一个编辑草稿
- **WHEN** 用户从 query result 建立 draft、编辑并成功保存 revision
- **THEN** Builder 明确更新 server baseline 和 query cache，dirty 变为 false，且不把
  Agent document 写入 localStorage

#### Scenario: Revision conflict
- **WHEN** save mutation 返回 optimistic conflict
- **THEN** query cache 保留服务端 current revision，Builder store 保留本地 draft，
  用户可以显式 reload 或另存

### Requirement: XYFlow 仅是 authoring 投影
StudioFlowDocument schema 2 SHALL 是当前 authoring state，XYFlow nodes、edges、handles
和 viewport SHALL 由显式 adapter 投影并可重建。`entities/agent-graph` MUST NOT 包含
XYFlow 类型或实例，presentation 修改 MUST NOT 改变编译所得 AgentGraph canonical
identity。

#### Scenario: 仅移动节点
- **WHEN** 用户只改变节点坐标或 viewport
- **THEN** Studio 可以保存新的 document revision，但重新编译的 canonical hash 与原
  semantic graph 相同

#### Scenario: 重新构建画布
- **WHEN** 相同 StudioFlowDocument 被关闭后重新打开
- **THEN** adapter 确定性重建 nodes、edges 和 handles，不依赖先前内存中的 XYFlow
  component instance

### Requirement: 样式与主题具有明确边界
Studio SHALL 使用 CSS variables 表达 design tokens 和深浅主题，Tailwind 处理常规
布局，CSS Modules 处理复杂 feature/XYFlow 私有样式。全局样式 SHALL 只包含 reset、
字体、tokens、theme 和真正全局规则；Stage 1 MUST NOT 把新 Builder 样式继续累积到
巨型 feature-global CSS。

#### Scenario: 新增 Builder node 视觉
- **WHEN** 开发者增加一种控制节点的复杂 handle 和状态样式
- **THEN** 样式位于该 Builder UI slice 的 CSS Module，颜色使用主题 token，且不会
  污染其他页面

### Requirement: Agent Design 身份路由
Studio SHALL 通过 `/agents/:agentId/design` 打开一个稳定 Agent identity 的 Builder。
现有 `/builder` SHALL 保留兼容入口并导航到明确的现有 Agent 或创建/选择流程，不得用
浏览器随机 ID 假装后端已保存 Agent。

#### Scenario: 直接打开 Agent Design
- **WHEN** 用户打开一个存在的 `/agents/:agentId/design`
- **THEN** Builder 从后端加载 Agent current revision、document 和 compile snapshot

#### Scenario: 旧 Builder 入口
- **WHEN** 用户访问 `/builder`
- **THEN** Studio 进入 Agent 选择/创建或明确最近 Agent，不丢失旧入口可达性

### Requirement: Schema 2 文档状态为画布真相
前端 SHALL 使用严格解析的 StudioFlowDocument schema 2 作为 authoring state，并区分
server document、current editable document、revision、dirty、loading、saving 和
compile state。XYFlow nodes/edges SHALL 是该文档的交互投影，不得成为另一份不可重建的
持久化真相。

#### Scenario: 加载后不修改保存
- **WHEN** 用户加载一个 revision 并未改变文档
- **THEN** Builder 显示 clean state，重新序列化保留稳定 canvas/logical/edge identity

#### Scenario: 离开未保存页面
- **WHEN** current document 与 server revision 不同且用户导航离开
- **THEN** Studio 明确提示未保存修改，不静默丢失

### Requirement: Catalog 驱动组件面板
Palette、组件版本、NodeContract ports、config form 和 connection validation SHALL
从后端 Catalog 派生。前端内置 definition MAY 提供图标或专用安全 renderer，但 MUST
NOT 覆盖 Catalog 的正式 port/type/config 语义。

#### Scenario: 新外部组件出现
- **WHEN** Catalog 返回未知名称但合同有效的外部组件
- **THEN** Palette 使用通用卡片展示并允许按正式 ports 拖入连接

#### Scenario: Catalog 不可用
- **WHEN** 已保存 document 可加载但 Catalog 请求失败
- **THEN** Builder 可只读展示已有结构，禁用依赖未知语义的新建、重连和正式 Validate

### Requirement: AgentGraph 1.1 节点编辑
Builder SHALL 支持 component、input、output、condition、router、state、loop 和
subgraph 节点，以及 structured predicate、GraphInterface、GraphPolicies、typed
data/control edge 和 bounded feedback。UI MUST NOT 接受任意 Python/JavaScript 表达式
作为控制语义。

#### Scenario: 编辑 Router
- **WHEN** 用户为 Router 添加有序 predicates 和 default branch
- **THEN** document 保存 structured cases，画布端口使用稳定 case ID

#### Scenario: 编辑 State
- **WHEN** 用户配置 state key/type/scope/operation/merge
- **THEN** document 保存正式 StateSpec 字段并由后端 validator 验证

#### Scenario: 编辑 Loop body
- **WHEN** 用户打开 Loop 或 inline Subgraph
- **THEN** Builder 使用 breadcrumb nested canvas 编辑 child document，并保留父子
  canvas path

### Requirement: Typed connection 与 stable handles
XYFlow handle SHALL 从 stable canvas ID、direction 和 NodeContract port ID 确定性派生。
连接 UI SHALL 使用 type、direction、required 和 cardinality 提供即时提示，但后端
compile result SHALL 是最终权威。

#### Scenario: 重新加载文档
- **WHEN** 用户保存、关闭并重新打开同一 revision
- **THEN** node、port、edge identity 保持稳定，source map 仍能定位原对象

#### Scenario: 不兼容类型连线
- **WHEN** 用户尝试连接不兼容 data types
- **THEN** 前端拒绝或标记连线，并且后端 Validate 对伪造请求仍返回正式诊断

### Requirement: Component binding 与 SecretRef 表单
Inspector SHALL 支持 exact component version、single/fallback candidates、params、
dependencies、execution policy 和 SecretRef。它 MUST NOT 把 raw secret 存入
StudioFlowDocument、localStorage、toast 或 diagnostics。

#### Scenario: 配置 fallback
- **WHEN** 用户为一个幂等组件选择有序 fallback candidates
- **THEN** document 保留候选顺序，后端根据 side-effect/idempotency contract 验证

#### Scenario: 输入 API key
- **WHEN** config schema 标记字段为 secret
- **THEN** UI 只允许选择/输入 secret reference identity，不把实际值写入 document

### Requirement: Validate 与定位诊断
Builder SHALL 提供显式 Validate，调用后端 side-effect-free compile API，并展示
valid/invalid、canonical hash、warnings 和 errors。每个具有 source locator 的
diagnostic SHALL 能高亮或导航到对应 nested canvas/node/edge/port/property。

#### Scenario: 重复 logical ID
- **WHEN** 两个同 scope 节点使用相同 logical ID
- **THEN** Validate 显示稳定 diagnostic code 并高亮两个冲突节点，不生成 hash

#### Scenario: 有效 document
- **WHEN** backend compile 成功
- **THEN** Builder 显示 AgentGraph contract version 和 canonical hash，且明确该 hash
  属于语义图而非 document revision

### Requirement: 保存与有效性分离
Builder SHALL 允许把严格结构有效但 compile invalid 的 document 保存为 revision，并
分别显示 saved/dirty 和 valid/invalid。只有 valid immutable revision SHALL 显示
canonical hash 并允许进入普通 Agent Run。`Save & Run` MUST 先完成正式 revision 保存和
compile validation；invalid、保存失败或 optimistic conflict MUST 保留本地 draft 且不得
创建 Run。

#### Scenario: 保存 invalid draft
- **WHEN** 用户保存尚未完成的图
- **THEN** Save 成功创建 invalid revision，UI 保留 diagnostics、不显示“可运行”，Run action 不创建 Run

#### Scenario: Revision conflict
- **WHEN** Save 或 Save & Run 返回 base revision conflict
- **THEN** UI 保留当前本地修改、显示 current server revision，并要求用户显式重新加载或另存，不自动覆盖或运行 stale revision

#### Scenario: clean valid revision 进入 Run
- **WHEN** Builder 当前 revision 已保存、compile status 为 valid 且 draft clean
- **THEN** Run action 使用该 revision identity 导航到 `/agents/:agentId/run`，不提交可变 FlowDocument

#### Scenario: dirty valid draft 执行 Save & Run
- **WHEN** 用户修改 Builder draft 后点击 Save & Run
- **THEN** Builder 先保存新 immutable revision，只有返回 compile status valid 时才导航到该 revision 的 Run 页面

### Requirement: JSON Import/Export 与 schema 1 migration
Builder SHALL 导入/导出 StudioFlowDocument schema 2。导入 schema 1 / contract 1.0 时
SHALL 运行显式 migrator并展示 migration diagnostics；无法安全迁移时 MUST 保留原始
输入且不得部分覆盖当前画布。

#### Scenario: 导入 legacy modular flow
- **WHEN** schema 1 文档具有可无歧义映射的 role、plugin 和 typed ports
- **THEN** importer 生成 schema 2 draft，并要求用户 Validate 后再保存

#### Scenario: 导入 legacy wildcard
- **WHEN** schema 1 文档含 VerifiedPlan 或 wildcard 语义
- **THEN** importer 返回定位 migration diagnostic，当前 document 不变

### Requirement: 阶段 1 不模拟运行
Stage 1 保留的“不模拟运行”约束 SHALL 在 Stage 4 继续成立：Builder Run action 现在可以
导航到正式 `/agents/:agentId/run` 并通过 Stage 3 API 创建真实持久 Run，但 MUST NOT 使用
timer、toast、占位数据或前端本地状态伪造 running、success、history、device frame 或
activation。没有 valid immutable revision 时 Run action SHALL 禁用或引导 Save &
Validate，而不是执行草稿。

#### Scenario: 点击有效 revision 的 Run
- **WHEN** 用户在 clean valid revision 点击 Run
- **THEN** Studio 打开正式 Run launch 页面，只有后端接受请求后才显示 accepted/running 状态

#### Scenario: 点击 invalid revision 的 Run
- **WHEN** 当前 revision compile status 为 invalid
- **THEN** Studio 显示正式 diagnostics 或 Save/Validate 引导，不连接设备、不创建 Run 且不显示虚构成功

#### Scenario: Run 后端不可达
- **WHEN** create Run 请求失败或本地服务不可用
- **THEN** 页面显示安全错误并允许使用同 client request identity 重试，不回退到 mock execution

### Requirement: Builder 必须提供 Catalog 驱动的 LLM Dependency Editor
当 selected component 声明 `llm` dependency slot 时，Inspector SHALL 提供 exact LLM
component/version、Catalog config、SecretRef 和可用性编辑，而不是要求用户只能手写任意
Dependencies JSON。提交结果 MUST 是普通 candidate `dependencies.llm` 语义；UI MUST NOT
引入只有 Studio Runtime 才能理解的隐藏 default 或保存 raw secret。

#### Scenario: 为 Planner 选择 OpenAI LLM
- **WHEN** 用户在 Universal Planner Inspector 选择 Catalog 中可用 OpenAI LLM、model 和 SecretRef identity
- **THEN** Builder 把显式 LLM component ref 写入该 Planner candidate dependency，并把 draft 标记为 dirty

#### Scenario: 将同一 LLM 应用于兼容节点
- **WHEN** 用户选择“应用到所有需要 LLM 的组件”且图中 Planner、Reasoning 都声明兼容 slot
- **THEN** Builder 通过一个可撤销 authoring command 把显式 dependency 展开到每个兼容 candidate，不改变不兼容节点

#### Scenario: 外部组件声明未知依赖类型
- **WHEN** Catalog 返回前端没有专用控件但 schema 可安全表达的 dependency slot
- **THEN** Inspector 使用通用安全 schema editor；无法安全表达时显示 unsupported diagnostic 而不删除已有值

### Requirement: Builder 必须区分 Graph Validity 和 Runtime Readiness
Builder SHALL 继续以 side-effect-free compile result 决定 valid/invalid 和 canonical hash，
并把当前环境 Runtime Readiness 作为独立状态显示。Run/Save & Run eligibility MUST 同时
满足 exact saved valid revision 与 ready environment，但 temporary unready MUST NOT 改写
revision compile status 或 canonical identity。

#### Scenario: 图有效但 Secret 缺失
- **WHEN** revision 的 LLM dependency/SecretRef 结构有效，而当前 Studio 没有该 SecretRef 值
- **THEN** Builder 显示 `Graph valid` 与 `Run blocked: secret not configured`，保留 canonical hash

#### Scenario: 修复环境而不修改图
- **WHEN** 操作者补充服务端 Secret 并重启，revision document 未改变
- **THEN** Builder readiness 变为 ready，revision identity、document 和 canonical hash 不变

### Requirement: 新建 LLM 组件不得生成已知不可绑定的空 dependency
当模板或 Palette command 创建一个声明必需 LLM slot 的 component candidate 时，Builder
SHALL 要求用户选择合法 dependency，或把 draft 保持为明确 compile-invalid 状态。默认
模板 MUST NOT 把 Universal Planner/Reasoning 的空 `dependencies` 表述为 valid runnable
Agent。

#### Scenario: 从标准模板创建 Agent
- **WHEN** 用户使用标准 Modular AgentGraph 模板
- **THEN** Planner/Reasoning 获得明确可编辑的 LLM dependency，或 Validate 返回定位到节点的配置缺失，而不是运行时 `llm_client` TypeError

### Requirement: 标准 Studio Mobile Agent 模板必须形成显式运行闭环
Studio SHALL 让标准新建 Mobile Agent 模板编译为显式观察、感知、推理、类型化动作请求、设备动作、终止判断和有界反馈组成的 AgentGraph。普通非终止 ActionResult MUST 通过图声明的 bounded feedback 进入下一 interaction，只有明确的 DONE/FAIL、结构化执行失败或图策略上限才能结束运行；模板 MUST NOT 依赖 Runtime 注入未声明的 observation。

#### Scenario: 从标准模板创建新版 Agent
- **WHEN** 用户从 Studio 标准模板创建并 Validate 一个 Mobile Agent
- **THEN** 保存的 schema 2 document 包含可达的 DeviceObserve 和 ActionExecutor service、明确的 terminal condition、非终止结果的 bounded feedback 以及有限的 step/feedback policy

#### Scenario: 非终止设备动作进入下一轮
- **WHEN** 标准模板 Agent 的 Reasoning 产生合法 TAP 且 ActionExecutor 返回无 terminal status 的成功结果
- **THEN** 图通过 feedback 激活下一 interaction 的 DeviceObserve，而不是把该 ActionResult 直接视为 Run 成功或失败的最终 Output

#### Scenario: 明确终止进入 Output
- **WHEN** 标准模板 Agent 的 ActionExecutor 返回 DONE 或 FAIL terminal status
- **THEN** terminal branch 激活 Output，feedback branch 不再激活，Run 保留对应的 Agent outcome

#### Scenario: 打开旧线性 Studio revision
- **WHEN** 既有 Studio revision 依赖 `input.observation`、legacy action executor 或非终止 ActionResult 直达 Output，且不满足新版普通 Android Run topology readiness
- **THEN** Studio 保持 immutable revision 和历史读取能力，但以稳定可定位诊断阻止普通 Run，并引导用户基于新版模板重建或手工补齐闭环，不静默改写 revision

#### Scenario: 框架公共入口不受 Studio 模板淘汰影响
- **WHEN** 调用者通过既有 Python SDK、AgentConfig YAML、ModularAgent、AgentRunner 或独立 BenchmarkTask JSON 使用框架
- **THEN** Studio 标准模板升级不删除或改写这些公共入口的合同

