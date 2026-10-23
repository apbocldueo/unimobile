# ZhiXing Studio 阶段 0 产品决策

状态：**已接受并已写入阶段 0 OpenSpec Change**  
对齐日期：**2026-07-25**

对应 Change：
[当前已接受的 OpenSpec 合同](../openspec/specs)

本文记录项目负责人对 Studio 阶段 0 的明确产品决策。后续负责 Studio 的 Coding
Agent 在提出 OpenSpec、接口、数据模型、交互或验收方案前，必须先阅读本文和
[Studio 产品与工程路线](studio-roadmap.md)。

本文中的“已接受”表示产品方向已经对齐，不表示功能已经实现。具体 API、DTO、
安全策略和验收用例仍需在对应 OpenSpec Change 中定义并验证。

## 产品定位与第一目标用户

Studio 的第一目标用户是 **Mobile Agent 研究人员**。

ZhiXing 希望为 Agent 研究者提供类似 LangChain 在通用 Agent 领域中的基础设施：

- 研究者可以快速选择和组合 ZhiXing 内置或外部组件，构建不同 Mobile Agent；
- 研究者可以选择已有 Benchmark 测试 Agent；
- 研究者可以开发自己的 Benchmark，优先复用声明式 JSON/Package 和已有
  initializer/evaluator，只集中编写具体 task 或必要的新原子插件；
- 研究者可以比较不同 Agent、组件和配置的结果，并利用结构化运行证据迭代出效果
  更好的 Mobile Agent；
- Studio 服务于研究、实验、调试、比较和复现，而不是只提供面向普通用户的
  “零代码应用生成器”。

上述定位不等于承诺复刻 LangChain、Dify 或 Langflow 的全部功能。ZhiXing 的核心
差异仍是 Mobile Agent 的 AgentGraph、真实设备边界、Benchmark 生命周期和可审计
trajectory。

## 核心研究工作流

Studio 应优先支持以下完整研究循环：

```text
选择/开发组件
  → 拖拽构建 AgentGraph
  → 编译、验证和保存
  → 选择已有 Benchmark 或编写具体 task
  → 在受控 Protocol 下运行
  → 查看 AgentGraph、设备和组件证据
  → 比较结果并修改 Agent
```

Agent Builder 与 Benchmark authoring 是并列能力。Studio 不得把 Benchmark
Evaluator 混入被测 AgentGraph，也不得把 Agent Verifier 当作外部任务判定。

## 页面和路由决策

Design、Run 和 Replay 在逻辑上使用三个路由，在视觉上属于同一个工作台：

```text
/agents/:agentId/design
/agents/:agentId/run
/runs/:runId/replay
```

三个路由共享 Agent 身份、导航、主题和必要的工作区上下文，但拥有独立的页面状态：

- Design 允许编辑、编译和保存 Agent；
- Run 固定本次执行所使用的 AgentGraph identity，避免运行中产生含义不清的修改；
- Replay 只消费持久化结果、trajectory 和 artifact，不连接设备或重新执行组件。

具体 URL 可以在 OpenSpec 中调整，但“逻辑分路由、视觉同工作台”的产品决定保持
稳定。

## Run Workspace 布局

运行工作区使用可拖动宽度的三栏布局：

1. 左侧：AgentGraph 与当前执行路径；
2. 中间：虚拟手机和设备观察；
3. 右侧：组件定义与当前/历史 activation 信息。

初始比例可采用：

```text
AgentGraph 42% / Virtual Phone 25% / Inspector 33%
```

用户调整后的比例应在本地或用户设置中保留。首版优先桌面研究工作区，不要求在
窄屏手机上提供完整三栏编辑体验。

## 自动跟随决策

运行时默认自动跟随当前 activation：

- 节点开始执行时，左侧高亮对应逻辑节点或层级 node path；
- 右侧切换到当前 activation；
- 用户手动选择旧节点或旧 activation 后进入“锁定查看”；
- 锁定时实时运行继续，但 Inspector 不强制跳回当前节点；
- 页面提供“回到当前节点”操作；
- 快速节点可设置 UI 最短高亮时间，但不得修改、延迟或伪造真实事件时间；
- Subgraph 默认可折叠，并允许展开查看内部 node path；
- 失败时自动定位失败 activation，同时保留此前成功和跳过节点状态。

事件到达、UI 动画和 Inspector 选择必须是三个独立状态，避免为了视觉效果改变运行
语义。

## 虚拟手机决策

第一版虚拟手机是 **只读截图视图**：

- 根据 DeviceObservation/trajectory artifact 显示当前截图；
- 显示屏幕尺寸、interaction step、最近动作和安全设备信息；
- 可在截图上叠加最近点击位置、滑动轨迹或识别框；
- 截图缺失或读取失败必须有明确状态，不能继续显示旧图并冒充当前观察。

首版不能把实现写成只能只读的死路。接口和组件边界应允许后续增加：

1. 暂停、重试、取消等运行控制；
2. 用户点击虚拟手机控制真实设备。

后续人工设备控制必须单独设计坐标映射、权限、Agent/人工动作竞争、trajectory
归属和恢复策略。Studio 不得绕过 ActionExecutor 直接执行未审计设备动作。

## 视觉与主题决策

- Studio 同时提供深色和浅色主题；
- 用户可以在 Settings 中选择，并持久化偏好；
- 第一版视觉参考 Dify 和 Langflow 的节点编排体验；
- 产品气质优先为“研究工具”，而不是偏营销或普通用户的低代码平台；
- 三栏宽度可拖动；
- 视觉系统应允许后续形成 ZhiXing 自己的品牌和交互风格，不把参考产品的布局写死
  为不可替换实现。

视觉设计不能改变 AgentGraph semantic identity。节点颜色、位置、折叠状态、主题
和面板宽度均属于 presentation/user preference。

## Inspector 总体原则

右侧 Inspector 只展示对理解当前组件和本次 activation 有意义的信息，不以“把
所有 Python 对象完整 dump 出来”为目标。

Inspector 至少区分：

- Definition：组件身份、版本、Contract、参数和来源；
- Current Activation：本次输入、输出、状态和耗时；
- Activation History：同一节点的历史执行；
- Runtime Identity：run、node path、activation、interaction 和 loop identity；
- Error/Evidence：安全错误、证据和 artifact references。

首版不要求展示完整 Prompt。完整 Prompt 不进入默认 Inspector；是否作为隐藏的
审计/导出 artifact 持久化，仍是阶段 0 OpenSpec 必须明确的未决项。

## 组件级首版展示要求

以下是首版 Inspector 的产品语义，具体 DTO 字段由 OpenSpec 定义。

### Perception

应优先展示：

- 使用的 observation/screenshot；
- 识别出的 UI 元素或区域；
- 文本、类别、边界框/坐标和可用置信度；
- 结构化 perception result；
- 标注叠加图或相关 artifact。

如果某个 Perception 只返回整体描述而不返回元素列表，Inspector 应如实展示其正式
输出，不得伪造检测框。

### Planner

应优先展示：

- 当前任务；
- 生成的计划或子任务；
- 当前计划步骤和进度；
- replan 原因和新旧计划关系（若存在）；
- 相关模型响应和耗时。

### Reasoning

应优先展示：

- 当前任务；
- 当前 observation/perception、plan step 和必要 Memory 摘要；
- 选择的决策、Action 或 Tool；
- 解析结果和失败重试；
- **完整模型响应**；
- 耗时和可观测 usage。

### Memory

应优先展示：

- 本次 read/write/reset 操作；
- 读取到的相关上下文；
- 新增或更新的 fragment；
- Memory scope 和本次运行内的状态变化；
- 不展示 live Memory 实例或未授权的跨运行内部状态。

### ActionExecutor

应优先展示：

- 请求执行的 Action；
- 参数和目标坐标/应用；
- ActionResult；
- 是否确认产生物理副作用；
- terminal status、设备错误和动作 artifact。

### Verifier

应优先展示：

- 被验证的任务和动作；
- 验证前后 observation/evidence；
- success、feedback 和终止/反馈决定；
- content、visual 或其他外部证据引用。

### Runtime Service 与扩展组件

DeviceObserve 应展示 observation identity、截图、UI XML、尺寸和安全设备信息。
自定义 Tool/组件根据 NodeContract 和正式 Debug Payload 展示，不允许前端按未知
组件名称硬编码任意字段。

## 持久化和导出决策

以下内容必须作为可审计运行证据默认持久化，并允许导出：

- 完整组装 Prompt，作为默认不可见的审计 artifact；
- 完整模型响应；
- screenshot；
- UI XML；
- 与组件理解相关的结构化 input/output Debug Payload；
- RunEvent、RunResult、trajectory、错误和 artifact references。

这里的“永久保存”定义为：**默认持久化，直到用户显式删除，或未来由用户选择的
数据保留策略执行清理**。不得使用进程内临时状态代替，也不得在页面刷新或服务
重启后丢失。

导出应使用版本化 manifest、相对 artifact references 和内容完整性信息。大响应、
图片和 XML 应保存为 artifact，事件只保存有界摘要和引用，避免把整个运行复制进
每条事件。

“完整”不取消安全边界。以下内容即使用户要求持久化和导出，也不得以原始明文进入
产物：

- API key、token、password、authorization header 和 secret；
- live Device、component、client、model 或进程对象；
- 未经允许的宿主绝对路径；
- 原始 Android serial；应使用批准的安全设备 provenance；
- 无界二进制 payload。

模型响应可能包含任务数据或设备屏幕中的敏感内容。OpenSpec 必须定义本地存储、
删除、保留和导出警告，但首版不能因为安全设计尚未完成就静默丢弃研究证据。

首版持久化采用以下已接受方案：

- SQLite 保存 Agent revision、Run、event、activation 和 artifact metadata 等结构化
  索引；
- 本地 Artifact Store 保存 Prompt、模型响应、截图、UI XML、trajectory 和导出包；
- 上层通过 Repository/Storage 合同访问，未来可以增加 PostgreSQL adapter；首版不
  要求实际交付 PostgreSQL；
- 默认存储位于操作系统用户数据目录，并按 workspace/project identity 隔离，允许
  用户配置其他位置；
- 首版不设置硬配额、不自动清理 Run；达到默认 20GB 可配置阈值时警告；
- 无法保证完整证据写入时阻止新 Run，不得静默丢弃某类证据；
- 用户删除后进入 7 天回收站，也可以立即永久清除；共享 artifact 仍被引用时不得
  误删；
- 导出为包含版本化 manifest、相对引用和成员 hash 的 bundle。完整 Prompt 默认不
  加入导出，用户确认敏感内容警告后可显式包含。

## Benchmark 研究体验

Studio 应让研究者：

- 浏览、选择和验证已有 Benchmark Package；
- 选择 split、task、Agent 和 ExperimentProtocol；
- 对声明式 Benchmark 主要编写具体 task JSON；
- 在确有新初始化/评估语义时开发小型插件；
- 运行一个或多个 AgentGraph；
- 查看 PASS、FAIL、INVALID、SKIPPED、Evaluation Tree 和证据；
- 进行满足公平合同的 paired comparison；
- 导出报告、trajectory 和完整性 bundle。

Studio 不得承诺“任意 Benchmark 只写 JSON 即可”。声明式已有能力应复用，新的
初始化或 evaluator 语义仍需要正式插件和 Contract Test。

## 阶段 0 默认技术方向

以下技术方向由 Coding Agent提出，产品负责人已接受其作为当前默认方案，仍需在
OpenSpec 中细化：

- 保留 React、TypeScript、XYFlow 和 Zustand；
- Studio authoring 升级到 AgentGraph contract 1.1；
- 严格按 AgentGraph 1.1 Builder → Trajectory Replay → 实时运行服务 → 实时三栏
  工作区的路线实施；
- 首版实时推送优先使用 HTTP + SSE；
- 组件定义信息与 activation 运行信息分离；
- logical ID/node path 是高亮依据；
- 所有详细运行信息通过显式、安全、版本化 Debug Payload；
- Agent Builder 与 Benchmark authoring 保持独立产品边界。

## 阶段 0 补充确认

- 完整 Prompt 默认落盘为不可见审计 artifact，不进入默认 Inspector，导出默认排除；
- 首版重试创建从头执行的 child run，组件级/checkpoint retry 另立 Change；
- 外部组件首版使用通用 NodeContract + Debug Payload Inspector；受限 UI schema
  后续扩展，不允许注入任意前端代码；
- 首版为本地单用户、单服务实例；HTTP + SSE 仍必须支持 sequence cursor、重复事件
  幂等、断线补拉和最终 RunResult 查询；
- 第一批正式验收 fixture 由阶段 0 OpenSpec 定义，具体代码与证据在对应实现阶段完成。

阶段 0 已无阻塞后续实施顺序的产品未决项。schema 字段、migration、压缩/去重、
Subgraph 交互和远程部署属于对应阶段的工程设计；不得由前端临时实现悄悄改变本文中
的已接受产品方向。
