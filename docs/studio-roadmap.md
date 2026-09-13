# ZhiXing Studio 产品与工程路线

本文固化 ZhiXing Studio 的长期产品方向、后端边界和分阶段交付顺序。它记录的是
已对齐的规划，不表示相关能力已经完成。每个实施阶段都必须先建立对应 OpenSpec
Change，并以代码、自动化测试和适当的运行证据作为完成依据。

## 产品目标

Studio 应成为 Mobile Agent 的可视化构建、运行调试和轨迹复盘环境，而不只是
Agent YAML 的表单编辑器。目标工作流为：

```text
拖拽组件与控制节点
        ↓
编译、验证并保存 AgentGraph
        ↓
运行普通任务或进入 Benchmark
        ↓
AgentGraph 高亮 ↔ 虚拟手机 ↔ 组件运行信息
        ↓
加载 trajectory 复盘与人工定位失败阶段
```

Studio 不定义独立的 Agent 执行语义。画布文档、图原生 YAML 和 Python SDK 必须
编译为同一种 AgentGraph；Runtime、Benchmark 和设备副作用继续服从现有后端合同。

## 已验证的产品导航

`redesign-studio-product-navigation-onboarding` 已实现按用户对象和研究生命周期组织的
`首页 / Agents / Experiments / Runs / 设置` 全局导航、唯一 Agent Library、Agent
对象级 `设计 / 运行 / 运行记录`、有界最近工作、真实 Runtime Readiness、可跳过的首次
使用引导、渐进披露和兼容路由。实现没有合并 ordinary Run 与 Benchmark Experiment
合同，也没有改变 AgentGraph identity、Run/Experiment lifecycle 或设备副作用 gate。
具体路由、最小 Replay `agentId` 过滤、自动化/浏览器证据和限制见
[Studio 产品导航与首次使用](studio-product-navigation-onboarding.md)。

截至 2026-08-04，`refine-agent-library-first-use` 将该 Library 的首用/回访层次收敛为
示例优先、空白/导入次级、最新可继续 Agent 突出、其余对象紧凑搜索，以及 URL 兼容的
渐进创建/导入 surface。此改动只调整前端信息架构与既有 Agent API 的使用方式；不改变
AgentGraph、revision、Run、设备或 secret 的合同。

## 三种工作模式

### Agent Builder

Builder 提供类似 Langflow、Dify 的节点式编排体验：

- 左侧组件目录支持分类、搜索和拖拽；
- 中间画布编辑节点、类型化端口、普通边、控制边和反馈边；
- 右侧检查节点定义、组件选择、参数、NodeContract 和端口；
- 顶部提供保存、加载、编译验证、运行、导入和导出；
- 后端编译诊断必须定位到画布节点、端口或边；
- Studio presentation 与 AgentGraph semantic identity 必须分离。

Builder 当前采用单画布能力层级，而不是“简化视图 + 精确视图”：六类核心角色与
Grounder、Tool、外部插件等独立能力使用完整卡片；正式模板的 DeviceObserve、
ActionRequest、Iteration、Terminal 使用保留真实 identity/port/diagnostic 的紧凑操作符，
Input/Output 使用边界锚点。普通控制节点与未知组件默认仍是完整卡片，避免根据名称猜测
运行胶水。可选 `presentation.nodes.*.renderMode` 不进入 canonical identity，也不改变
Runtime readiness 或执行顺序。

长期可编辑节点至少包括 Input、Output、六类核心 Agent 角色、
DeviceObserve、ActionExecutor、Condition、Router、State、Loop、Subgraph 和显式
feedback。组件目录必须来自后端 Catalog/Contract，不得让前端维护一套竞争性的
端口或组件事实源。

### Run Workspace

运行工作区采用三栏布局：

```text
┌──────────────────────┬──────────────────┬──────────────────────┐
│ AgentGraph           │ Virtual Phone    │ Component Inspector  │
│ 当前节点与路径高亮    │ 当前设备观察       │ Definition           │
│ 完成/失败/跳过状态    │ 最近动作可视化      │ Input / Output       │
│ Loop/Feedback 进度    │ Interaction 状态   │ Duration / Error     │
│                      │                  │ Activation History    │
└──────────────────────┴──────────────────┴──────────────────────┘
```

节点状态至少区分 idle、waiting、running、success、failure、skipped、
feedback、exhausted 和 cancelled。右侧必须区分组件静态定义与某次运行
activation；同一节点多次执行时，应能选择当前和历史 activation。

运行高亮使用稳定身份链路：

```text
Studio logicalId
  → AgentGraph node.id
  → RunEvent node_path / activation_id
  → canvas node state + inspector selection
```

不得根据显示标题、组件名称或随机画布 ID 猜测当前节点。Loop、Subgraph 和反馈
运行必须保留层级 node path、parent activation、interaction step 和 iteration
信息。

### Replay / History

Replay 使用已经落盘的 result、report、trajectory 和 artifact，不需要连接设备：

- 按生命周期因果顺序播放或单步执行；
- 图节点随事件高亮；
- 虚拟手机切换到相应 DeviceObservation；
- 右侧显示当时的 activation、输入输出摘要、耗时和错误；
- 支持暂停、前进、后退和跳转失败阶段；
- 区分 Agent 运行状态与 Benchmark PASS/FAIL/INVALID/SKIPPED。

Trajectory 只支持审计和人工定位，不得把 Replay 描述为自动失败诊断。

## 虚拟手机演进

虚拟手机按风险由低到高演进：

1. **Artifact snapshot**：收到 observation 事件时加载对应截图，并显示尺寸、
   interaction step、最近动作和安全设备信息；
2. **Near-live refresh**：通过运行事件或有界轮询刷新最新截图；
3. **Live streaming/control**：有明确需求和独立安全设计后，再评估
   scrcpy、WebRTC 或其他实时画面与输入方案。

第一阶段不要求实时视频。真实设备输入和动作仍必须经过显式设备边界，Studio
不得绕过 ObservationProvider 或 ActionExecutor 直接拼接 ADB 命令。

## 后端接口方向

Studio 后端应逐步提供以下独立接口边界：

- metadata：组件 Catalog、NodeContract、端口和模板；
- document：创建、读取、更新和版本化 Studio FlowDocument；
- compile：FlowDocument → AgentGraph、source map、diagnostics 和 canonical hash；
- run：创建、取消和查询一次 AgentGraph run；
- event stream：推送 run-scoped lifecycle 和 RunEvent；
- artifact：读取经过授权和安全处理的截图、UI tree、报告与轨迹；
- replay：加载持久化 RunResult 或 Benchmark trajectory。

实时运行首版优先使用普通 HTTP 加 SSE：创建、取消和查询使用 HTTP，服务端事件
使用单向 SSE。只有出现明确的双向低延迟设备控制需求时，才升级 WebSocket。

## 运行信息与安全边界

Studio 不能通过递归序列化任意 Python 对象获得组件详情。运行时调试信息应使用
显式、安全、版本化的 Debug Payload：

- 默认输出有界的 input/output summary；
- 二进制和图片只使用 artifact reference；
- 长文本、Prompt 和模型响应具有大小上限；
- secret、token、password、原始设备 serial 和宿主绝对路径必须清理；
- live component、Device、client 和其他运行对象必须拒绝导出；
- Stage 3 默认持久化已捕获的完整模型响应；完整 Prompt 经 redaction 后以 hidden
  artifact 持久化，普通 API/export 不返回内容。未来可增加更严格的 capture policy；
- production 与 debug 数据保留策略应明确分离。

组件 Inspector 至少保留 definition、current activation、activation history、
runtime identity 和 error/evidence 五类信息，具体字段以阶段 0 的产品合同为准。

## 分阶段路线

### 阶段 0：产品与合同对齐

建立 Studio OpenSpec Change，定义 FlowDocument 1.1、编译接口、事件 envelope、
节点状态机、artifact 读取、Debug Payload、安全策略和代表性验收场景。此阶段
不以大规模改 UI 为完成标准。

阶段 0 已接受的用户定位、路由、自动跟随、虚拟手机、Inspector、持久化、导出和
视觉决策见
[Studio 阶段 0 产品决策](studio-stage-0-product-decisions.md)。OpenSpec 必须以
该决策为产品输入，并明确其中列出的未决事项。

### 阶段 1：AgentGraph 1.1 Builder

在现有 React、TypeScript、XYFlow 和 Zustand 基础上升级编辑器，接入后端
Catalog、Contract 和 compile diagnostics，支持 1.1 控制节点、保存/加载及
canonical identity。代表性 Studio/Python/YAML 定义必须取得相同 canonical hash。

阶段 1 的实施范围、技术设计和验收任务见
[当前 Builder 合同](../openspec/specs/studio-agentgraph-builder-ui/spec.md)。
阶段 1 及后续 Studio 前端代码必须遵循
[Studio 前端架构](studio-frontend-architecture.md)，采用约定的分层、状态所有权、
XYFlow 隔离和增量迁移方式。
该 Change 未完成前，不得把 Builder 1.1、SQLite revision 或正式 Catalog API 描述为
已实现。

截至 2026-07-26，Stage 1.1 的生产代码、自动化测试、真实浏览器 smoke、前端
production build 和 clean wheel 安装已完成：当时 Builder 以 schema 2/AgentGraph 1.1
工作，Catalog、compile、SQLite revision、optimistic conflict、迁移与导出链路均有
验证证据。schema 2 现在只保留历史读取/导出，不再是新建和修改 Agent 的 authoring
合同。历史使用方式和限制见
[Studio AgentGraph 1.1 Builder](studio-agentgraph-builder.md)。Change 已使用项目本地
OpenSpec 1.6.0 通过 strict validation；Run、Replay、虚拟手机、SSE 和 Benchmark UI
仍属于后续阶段。

### 阶段 2：Trajectory Replay

先用已有真实和 fake trajectory 完成事件时间轴、节点高亮、手机截图、Inspector
和失败阶段跳转，验证三栏交互模型，不依赖实时设备。

截至 2026-07-26，Stage 2 的离线纵向切片已经完成并通过验证：后端提供版本化
Replay envelope、SQLite 索引、受控 Local Artifact Store、legacy/native 显式导入、
安全 artifact/bundle 读取；前端提供真实 History、`/runs/:runId/replay`、确定性
AgentGraph 投影、因果截图、Inspector、双轨时间轴与三栏拖动。真实 Android 摘录和
fake 完整合同证据必须继续分开描述。使用方式、证据边界和已知限制见
[Studio Trajectory Replay](studio-trajectory-replay.md)。

### 阶段 3：实时运行服务

提供 run HTTP API、取消与状态查询、SSE 事件、artifact 获取和最终 RunResult。
确保事件顺序、断线恢复、重复事件处理和终止状态有自动化测试。

截至 2026-07-26，Stage 3 后端纵向切片已完成：普通 Agent task 绑定 immutable valid
revision，使用 SQLite repositories、managed artifact store、单 worker scheduler、
安全 device profile、AndroidGraphRuntime、协作取消和 startup recovery；HTTP 提供
create/get/cancel、cursor event query、SSE 和 live artifact，terminal Run 自动成为同
identity 的 native Replay。fake Android 已覆盖成功与主要失败/取消/中断路径；真实
Android Stage 3 smoke 因未明确选择 profile/serial 而保持未验证。使用方式和限制见
[Studio Run Service](studio-run-service.md)。

### 阶段 4：实时三栏工作区

将 Replay 的状态投影复用于实时事件，实现运行节点高亮、虚拟手机刷新和当前
activation Inspector；运行结束后自动转入可回放状态。

截至 2026-07-26，Stage 4 前端纵向切片已完成：Builder 提供 `Run`/`Save & Run`，
`/agents/:agentId/run` 支持普通 task launch 与持久 live Run 恢复；客户端使用 HTTP
backfill + named SSE、共享 Live/Replay reducer 和独立 factual/visual/selected 状态驱动
只读 AgentGraph、Virtual Phone 与 Inspector。typed evidence 支持懒加载完整模型响应并
保持 Prompt hidden；Cancel 沿用 Stage 3 幂等协作合同；terminal 仅在 authoritative
Replay available 后交接。自动化和真实浏览器 fake-device smoke 已覆盖刷新、重连、
取消和 Replay handoff；真实 Android Stage 4 UI smoke 因未选择 profile/device/task 而
保持未验证。使用方式、证据和限制见
[Studio Live Run Workbench](studio-live-run-workbench.md)。

截至 2026-08-03，普通 Run readiness 增量已补齐 required LLM dependency authoring、
server-side SecretRef/Profile authority、process/exact readiness、pre-accept no-side-effect
gate、Profile selection 和 factual Virtual Phone 状态。历史 revision 保持 immutable，
配置变化不进入 AgentGraph canonical identity；详见
[Studio Agent Run Readiness](studio-agent-run-readiness.md)。

同日，标准 Studio Mobile Agent 的 lowered AgentGraph 已从依赖 Runtime 首帧兼容注入的
单次线性图升级为显式 DeviceObserve、ActionRequest、runtime ActionExecutor、terminal
predicate 和有界 feedback 闭环。当前 schema-3 Builder 不再把这些执行胶水暴露给用户，
而是由能力文档确定性生成；ordinary Run/Benchmark policy gate 会阻断 schema-1/2 和闭包
不完整 revision，但不改写 immutable 历史，也不删除 SDK/YAML/ModularAgent/AgentRunner
入口。Live 与 Replay 通过持久 projection map 将这些 activation 投影到能力节点。确定性
fake-device 已验证两次观察、一次物理 TAP 和 terminal RunResult；画布不显示终态结果词，
本轮没有新增真实 Android 证据。
详见 [Studio Agent 显式反馈闭环](studio-agent-feedback-loop.md)。

截至 2026-08-10，新建和修改 Agent 使用
`StudioCapabilityDocument` schema 3：画布只保留 Input、Output、六个核心能力以及批准的
Grounder/Tool 扩展，implementation/dependency 在 Inspector 编辑。Catalog placement、
lowering profile、capability hash、graph hash 和完整 projection map 构成新 revision 的
执行身份闭包；旧 schema-1/2 revision 与已完成证据继续可读/导出，但不能创建新 Run 或
Experiment。详见
[Studio Mobile Agent 能力组件创作](studio-agent-capability-authoring.md)。

同日，capability-authored Live/Replay 左栏从 Builder 拓扑缩略图收敛为纯前端纵向
execution map：唯一 current 与历史/失败/锁定分离，默认只显示可信运行路径，完整 relations
按需展开。该呈现不修改 Builder、route/state/loop/composite authoring、lowering、Runtime 或
AgentGraph identity；generic/legacy Replay 保留兼容路径。详见
[Studio Live Run Workbench](studio-live-run-workbench.md)。

### 阶段 5：Benchmark 与历史产品

接入 Benchmark Package、Task、ExperimentProtocol、Evaluation Tree、报告、
paired comparison 和 bundle 下载。Benchmark 定义继续与 AgentGraph 保持独立。

阶段 5 已对齐的目标、现有后端基础、Studio 缺口、目标路由、服务边界、
5.0–5.6 实施顺序、第一条执行切片和默认决策见
[Studio Stage 5：Benchmark Experiment 产品路线](studio-benchmark-experiment-roadmap.md)。
该路线是后续 OpenSpec Change 的输入，不表示 Benchmark Studio 产品闭环已经实现。
Stage 5.0 的版本化 DTO、资源关系、状态机、event/SSE、SQLite/PostgreSQL 边界、
cancel/recovery、Replay、安全和验收合同见
[Studio Benchmark Experiment 合同](studio-benchmark-experiment-contracts.md)。

### 阶段 6：视觉、性能与高级设备体验

在核心合同稳定后完善响应式布局、快捷键、无障碍、超大图性能、主题、实时视频、
授权远程控制和团队协作。插件 marketplace、签名和进程沙箱属于独立产品/安全
里程碑，不因 Studio 展示组件而自动获得。

## 各阶段共同完成标准

- 先有 OpenSpec requirement、设计、任务和验收场景；
- 不静默修改 AgentGraph canonical identity、组件 identifier 或旧配置合同；
- Studio 不成为端口、组件或 Runtime 语义的独立事实源；
- presentation 修改不影响语义 hash；
- 编译与只读元数据接口不得连接设备、解析 secret 或加载未选择的外部代码；
- fake 证据、Replay 证据和真实 Android 证据必须明确区分；
- 运行失败保留截至失败点的安全事件和 artifact；
- 前端生产构建、关键交互测试和后端合同测试必须可复现；
- 未实现的实时视频、自动诊断、任意 Agent 范式或设备兼容不得写成已完成。

## 当前事实与限制

当前事实：

- Studio Builder 已使用 schema 3 capability contract、AgentGraph contract 1.1、正式
  Catalog placement、typed relation、后端 deterministic lowering/diagnostics 和 immutable
  revision；Input/Output、六个核心能力与批准扩展是唯一可直接组装的画布对象；
- 旧 schema 1/2 通过有界 parser/export/replay 保留，不再作为新 Builder 的编译真相，
  也不具备创建新 Run/Experiment 的 current-policy eligibility；
- Agent create/list/load、Validate、Save/Save As、revision load、conflict、import/export
  已形成 Stage 1 authoring 闭环；
- History 与离线 Replay 已形成 Stage 2 只读闭环，包括持久索引、三栏工作台、
  因果 Virtual Phone、运行 Inspector、Agent/Benchmark 双轨和 bundle 导出；
- 普通 Agent Run 后端、实时 durable event/SSE、协作取消、artifact 和 native Replay
  已形成 Stage 3 后端闭环；Builder 启动、实时三栏、刷新恢复、协作 Cancel 和 terminal
  Replay handoff 已形成 Stage 4 前端闭环；暂停/checkpoint、节点重试、真实设备控制和
  完整 Benchmark 产品仍未形成产品闭环；
- Stage 5 Benchmark Experiment 的产品路线和 5.0–5.6 切分已经对齐并文档化；
  Catalog/Composer、持久 Experiment service、execution/durability、Monitor、
  Reporting/History/Evidence/Export、5.5A durable authoring resource 与 5.5B-1/2/3
  definition/managed-content/resource editor 已实现并分别验证。原
  5.5B editor 已永久细分为 5.5B-1 definition editor、5.5B-2 managed-content
  backend、5.5B-3 resource editor、5.5C-1/2 validation/dry-run 与 5.5D Contract
  Tests 与 5.5E-1 validated freeze 已实现。E-1 对 exact current revision 的全部
  declared split 做 definition-only revalidation，以 schema 9 原子持久化独立
  attestation 与 closed immutable Package revision，不修改 source revision 或授予
  runtime/publication evidence。原 5.5E 已拆为 5.5E-1 validated freeze、5.5E-2
  publication/export 与 5.5E-3 legacy migration，三项和 Stage 5.5 均已完成。
  5.6A explicit profile/provenance 与 5.6B layered no-device acceptance 也已完成；
  5.6B 用 production fake composition、14 场景 proof ledger、actual-backend 浏览器
  和 external-Package clean wheel 闭合 Studio 因果链，同时分别证明 Core `2×2×2`
  与 Studio `1×1×1` fail-closed 边界。它没有执行真实 Android。当前下一步固定为
  `validate-studio-benchmark-android-service-5-6c1`，随后是 5.6C-2 浏览器真机验收；
- 后端已有 RunEvent、observation artifact、结构化 RunResult 和 Benchmark
  trajectory，可作为 Replay 与实时 UI 的基础；
- Stage 1.1、Stage 2 与 Stage 3 Change 已归档；Stage 4 的实现、验证与 strict
  validation 证据见对应 OpenSpec Change。
