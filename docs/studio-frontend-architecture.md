# ZhiXing Studio 前端架构

本文固化 ZhiXing Studio 已接受的前端文件架构、依赖方向、状态所有权、XYFlow
隔离、样式策略、测试位置和增量迁移规则。它是后续 Studio OpenSpec Change 和代码
评审的长期约束，不表示现有前端已经完成迁移。

产品范围、分阶段顺序和运行工作区方向见
[Studio 产品与工程路线](studio-roadmap.md)；Stage 0 的用户与产品决定见
[Studio 阶段 0 产品决策](studio-stage-0-product-decisions.md)。具体阶段仍以对应
OpenSpec Change 的 requirements、design 和 tasks 为实施与验收依据。

## 架构目标

Studio 面向 Mobile Agent 研究人员，需要长期承载四类不同但相互关联的能力：

- AgentGraph 的可视化搭建与版本化；
- 普通任务的运行、事件跟随和虚拟手机；
- trajectory 的离线 Replay 与人工失败定位；
- Benchmark 定义、实验、评估和结果比较。

前端结构必须让这些能力各有所职，并避免把路由、业务状态、XYFlow 数据、后端 DTO、
通用组件和全局样式混在同一目录。采用轻量 Feature-Sliced Architecture
（下文简称 FSD-lite），保留 React 生态的组合方式，同时不过度拆分。

## 接受的技术基线

- React 与 TypeScript 继续作为前端框架和语言；
- Vite 继续承担开发与生产构建；
- XYFlow 只承担图画布交互与渲染，不成为 AgentGraph 的语义模型；
- Zustand 承担复杂、同步、交互密集的客户端编辑状态；
- TanStack Query 承担后端资源、请求生命周期和服务端缓存；
- React Router 承担稳定资源身份、工作模式和可分享导航状态；
- CSS variables 提供设计 token 与深色/浅色主题；
- Tailwind 用于常规布局与间距，CSS Modules 用于复杂组件和 XYFlow 局部样式；
- ESLint 与 TypeScript 配置必须可以自动检查关键分层和 import 边界。

引入 TanStack Query、import boundary lint 或其他依赖属于具体 Change 的实现任务，
不能仅凭本文宣称已经安装。

## 目标目录

```text
studio/
├── public/
├── e2e/
└── src/
    ├── app/
    │   ├── providers/
    │   ├── router/
    │   ├── layouts/
    │   └── styles/
    ├── pages/
    │   ├── studio-home/
    │   ├── agent-design/
    │   ├── agent-run/
    │   ├── run-replay/
    │   ├── benchmark/
    │   └── settings/
    ├── widgets/
    │   ├── studio-shell/
    │   ├── agent-design-workbench/
    │   └── three-pane-workbench/
    ├── features/
    │   ├── agent-builder/
    │   │   ├── model/
    │   │   ├── lib/
    │   │   ├── ui/
    │   │   │   ├── canvas/
    │   │   │   ├── nodes/
    │   │   │   ├── edges/
    │   │   │   ├── palette/
    │   │   │   ├── inspector/
    │   │   │   └── toolbar/
    │   │   └── index.ts
    │   ├── agent-import-export/
    │   ├── agent-revision-history/
    │   ├── run-inspector/
    │   └── virtual-phone/
    ├── entities/
    │   ├── agent/
    │   │   ├── api/
    │   │   ├── model/
    │   │   └── index.ts
    │   ├── agent-revision/
    │   ├── agent-graph/
    │   ├── component-catalog/
    │   ├── run/
    │   ├── artifact/
    │   └── benchmark/
    ├── shared/
    │   ├── api/
    │   ├── config/
    │   ├── lib/
    │   ├── hooks/
    │   ├── ui/
    │   ├── styles/
    │   └── testing/
    └── main.tsx
```

目录树表达长期边界，不要求一次性建立所有空目录。只有出现真实职责时才创建 slice；
不得为了“看起来完整”提前增加空壳。

## 分层职责与依赖方向

唯一允许的宏观依赖方向为：

```text
app → pages → widgets → features → entities → shared
```

上层可以组合下层；下层不得知道上层。

### `app`

应用启动与全局装配层，负责 providers、router、顶层 layout、主题初始化、错误边界和
真正的全局样式。它不实现 Agent Builder、Replay 或 Benchmark 业务。

### `pages`

路由页面层，负责解析路由参数、选择页面级布局并组合 widgets/features。页面不应拥有
复杂业务 store，不应散落直接 `fetch`，也不应承载可复用的领域算法。

“逻辑上多个路由、视觉上同一个工作台”通过 pages 选择模式、widgets 复用工作台实现，
而不是把所有模式塞入一个巨型页面组件。

### `widgets`

可独立辨认的大型页面区块，负责跨多个 feature/entity 的组合，例如 Studio Shell、
Agent Design Workbench 和三栏 Run/Replay Workbench。widget 可以安排布局和协作，
但不能成为后端协议或 AgentGraph 语义的事实源。

### `features`

面向用户动作的业务能力，例如搭建 Agent、导入导出、查看 revision、运行 Inspector
和虚拟手机。feature 可以使用 entities 与 shared，并拥有对应交互 store、commands、
selectors 和 UI。

feature 不得深层导入另一个 feature 的内部文件。若多个 feature 必须共同拥有一项
状态或规则，应根据含义提升到 entity、widget 或 shared，而不是形成网状依赖。

### `entities`

稳定业务名词、DTO、解析器、查询与纯领域模型，例如 Agent、AgentRevision、
AgentGraph、ComponentCatalog、Run、Artifact 和 Benchmark。

entities 不依赖 React 页面结构，不导入 XYFlow，也不保存画布组件实例。AgentGraph
实体表达正式语义；Studio presentation 和 XYFlow 坐标只存在于 authoring 文档或
builder 投影边界中。

### `shared`

不带 ZhiXing 业务含义的基础设施和通用 UI，包括 HTTP transport、基础错误、
配置、通用 hooks、设计系统 primitive、纯工具和测试辅助。`shared` 不得出现
Agent、Graph、Run、Benchmark 等业务模型。

## 强制 import 规则

- 只允许按 `app → pages → widgets → features → entities → shared` 向下依赖；
- 跨 slice 引用必须经过对方 slice 的公开 `index.ts`；
- slice 内部可以直接相对引用自己的 `model/`、`lib/`、`ui/`；
- `entities` 不得导入 `@xyflow/react`；
- `shared` 不得导入任何 entity、feature、widget、page 或 app；
- React 组件不得绕过 feature/entity API 直接访问任意全局 store；
- 页面不得直接维护另一份 AgentGraph、Run 或 Catalog 语义状态；
- 一个 feature 不得导入另一个 feature 的内部目录；
- 后端 DTO 解析器不得依赖视图组件、toast 或 router；
- 新代码不得继续写入无所有权的根级 `components/`、`services/`、`stores/`、
  `domain/`、`modules/`、`utils/` 或 `types/` 大桶目录。

这些规则应由 ESLint/import-boundary、TypeScript path alias 和代码评审共同执行。
确有例外时，必须在活动 OpenSpec design 中说明原因和退出方案。

## Slice 公开 API

每个跨 slice 使用的业务 slice 通过根部 `index.ts` 暴露最小公开 API：

```text
entities/agent/index.ts
features/agent-builder/index.ts
widgets/agent-design-workbench/index.ts
```

公开 API 可以导出稳定 DTO、query hooks、selectors、commands 或顶层组件。不得用多层
barrel file 自动导出整个目录，也不得从公开入口泄漏 feature 内部 store 形状、
XYFlow 实例或第三方库对象。

## 状态所有权

状态按其真实生命周期分配，不建立一个包办所有内容的全局 store：

| 状态类型 | 所有者 | 示例 |
|---|---|---|
| 服务端资源与缓存 | TanStack Query | Agent 列表、Component Catalog、revision、compile response |
| 当前编辑会话 | feature Zustand store | canvas draft、selection、dirty、nested graph path、undo/redo commands |
| 稳定导航状态 | URL / Router | agent ID、design/run/replay 模式、可分享筛选条件 |
| 临时视图状态 | React local state | modal、hover、未提交的小型输入 |
| 用户展示偏好 | settings store + localStorage | theme、pane size、工作台展示偏好 |
| 持久业务真相 | 后端 Repository | Agent、不可变 revision、compile snapshot、canonical identity |

Zustand store 不复制 TanStack Query 的完整服务端缓存。编辑开始时可以从严格解析后的
revision 建立 draft；保存成功后由明确 command 更新 query cache 与 server baseline。
Catalog 请求、revision mutation、optimistic conflict 和 compile mutation 由 entity
API/query 层表达，不在组件中散落请求逻辑。

`localStorage` 只保存非语义用户偏好，不保存 Agent revision、运行结果、Prompt、
模型响应、截图或 UI XML。

## StudioFlowDocument、AgentGraph 与 XYFlow

前端必须保留三个不同概念：

```text
StudioCapabilityDocument schema 3
        │
        ├── capability semantic draft
        │          │
        │          └── deterministic lowering ──► AgentGraph 1.1
        │                                             │
        │                                             └── projection map
        └── presentation                              │
                │                                     │
                ▼                                     │
        capability-to-xyflow.ts ◄─────────────────────┘
                │
                ▼
          XYFlow nodes/edges
```

- StudioCapabilityDocument 是当前 authoring state；schema-1/2 只作为有界历史输入；
- AgentGraph 是后端执行语义和 canonical identity；
- XYFlow nodes/edges 是可重建的交互投影；
- presentation 变化可以产生新的文档 revision，但不得改变 capability hash 或 AgentGraph
  canonical hash；
- XYFlow 随机 ID、handle、组件实例、viewport 对象不得进入 AgentGraph；
- capability logical ID、generated graph ID、contract port ID、runtime node path 与 projection
  owner 必须分别建模；
- document ↔ XYFlow 适配器属于 `features/agent-builder`，不是 `entities/agent-graph`。

后续 Run/Replay 的高亮通过稳定身份链路投影到 XYFlow，不改变 AgentGraph 实体：

```text
Studio capability logicalId / relationId
  ← persisted projection map ← generated AgentGraph node/edge id
  ← RunEvent node_path / activation_id
  → Live/Replay factual aggregation
  → XYFlow visual state
```

Live/Replay 不从事件名称或端口文案猜能力归属。Studio snapshot 缺少完整 projection 时显示
truthful unavailable；generic Python/YAML Replay 可以继续显示低层拓扑。两者的画布文本都必须
经过共享策略，禁止在节点、端口、handle、边、badge 或 accessibility name 中暴露终态结果词。

capability-authored Run/Replay 还会在 `features/trajectory-replay` 内经过一个纯前端
execution-map presenter。它从同一 immutable snapshot 同时派生纵向“运行路径”和按需
“关系全图”，不读取 Builder x/y 作为运行坐标，也不修改 route、state、loop、composite、
lowering 或 AgentGraph identity。factual current、唯一 visual current、累计历史、正式失败和
用户锁定分别建模；XYFlow 只负责呈现该 view model。

## API 组织

网络访问分成三层：

```text
shared/api/httpClient.ts
        ↓
entities/<entity>/api/*.api.ts
        ↓
feature commands / query hooks
        ↓
React UI
```

- `shared/api` 只处理通用 transport、超时、取消、安全错误 envelope 和 JSON；
- `entities/*/api` 定义版本化业务 DTO、endpoint 与严格 response parsing；
- feature 组合“加载、编辑、验证、保存”等用户用例；
- React 组件只消费 query/mutation/command，不散落 `fetch`；
- 任何 DTO 都不得包含 raw secret、live component、device handle 或宿主绝对路径；
- API client 不通过字符串名称猜测 NodeContract、组件或 port 语义。

## 样式、主题与布局

采用混合策略：

- CSS variables 定义颜色、字体、圆角、阴影、层级、间距语义和深浅主题；
- Tailwind 处理常规 flex/grid、尺寸、间距、响应式和简单状态；
- CSS Modules 处理 XYFlow node/edge/handle、复杂动画和 feature 私有样式；
- `app/styles` 只保存 reset、字体、tokens、theme 和真正全局的布局基础；
- 不新增巨型 feature-global CSS；
- 运行坐标、动态 panel size 等运行时值可以使用有限 inline style，静态视觉规则不应
  依赖大量动态 style object；
- 三栏工作台使用可调整分栏，宽度偏好可持久化，但不得影响语义文档；
- 深色和浅色主题均为正式要求，设置页负责用户选择。

旧的全局 CSS 可以在功能迁移时逐步拆分，不要求为目录调整进行无关视觉重写。

## 命名和文件粒度

- React 组件：`PascalCase.tsx`；
- hook：`useSomething.ts`；
- Zustand store：`builder.store.ts`；
- selectors：`builder.selectors.ts`；
- API：`agent.api.ts`；
- parser/schema：`agent.schema.ts`；
- 纯模型：`agent.model.ts`；
- 测试：与被测代码同目录的 `*.test.ts` / `*.test.tsx`；
- CSS Module：`Component.module.css`；
- 一个主要 React 组件一个文件；
- 文件与目录按业务职责命名，避免 `utils.ts`、`helpers.ts`、`common.ts`、
  `types.ts`、`constants.ts`、`service.ts` 等不断膨胀的模糊文件；
- 只有需要跨 slice 使用时才增加 `index.ts`，不建立层层 barrel。

当一个文件同时承担 DTO、业务规则、远程请求、store、React 渲染和样式时，必须按职责
拆分。文件行数不是唯一标准，但巨型文件通常说明职责边界已经丢失。

## 错误、加载与可观察性

- query loading、empty、stale、error 和 retry 状态由 feature/page 明确展示；
- mutation error 必须保留用户 draft，特别是 revision conflict；
- 后端 diagnostic code 和 source locator 作为稳定数据处理，不通过错误文本解析；
- Error Boundary 用于隔离不可恢复的 React 渲染错误，不代替正常 API 错误状态；
- 前端日志不得记录 secret、完整凭据、设备 serial 或未经安全处理的运行 payload；
- Stage 1 不用 timer、toast 或假数据模拟运行成功。

## 测试位置与层次

- `entities/*`：DTO parser、schema、纯模型和 API contract mapping 单元测试；
- `features/*`：store、selector、command、document/XYFlow adapter 和交互组件测试；
- `widgets/*`：跨 feature 组合与工作台状态投影测试；
- `pages/*`：路由参数、loading/error boundary 和关键页面组合测试；
- `studio/e2e/`：真实前后端关键用户路径；
- import-boundary lint、TypeScript typecheck 和 production build 属于每个前端阶段的
  基础验收。

测试不得把本地 mock 定义变成正式 Catalog 或 AgentGraph 语义事实源。需要业务合同时，
优先使用后端正式 fixture 或版本化 DTO fixture。

## 旧目录到目标结构的迁移

当前前端包含历史原型目录。迁移采用映射而不是简单改名：

| 当前职责 | 目标位置 |
|---|---|
| `features/agent-studio/` | `features/agent-builder/` |
| `modules/flow-graph/` 的纯语义 | `entities/agent-graph/` |
| `modules/flow-graph/` 的 XYFlow adapter | `features/agent-builder/lib/` |
| `components/flow-studio-cards/` | `features/agent-builder/ui/nodes/` |
| `services/studioRegistryClient.ts` 的 transport | `shared/api/` |
| `services/studioRegistryClient.ts` 的业务 endpoint | 相应 `entities/*/api/` |
| 根级 `stores/*` | 拥有该状态的 `features/*/model/` 或 entity query |
| `domain/agent/` | `entities/agent/`、`entities/agent-graph/` |
| `app/shell/` | `app/layouts/` 或 `widgets/studio-shell/` |
| route page component | `pages/*/` |
| 真正通用的 `components/ui/` | `shared/ui/` |
| `styles/globals.css` | `app/styles/`，仅保留真正全局内容 |

迁移时必须先判断文件职责；如果一个旧文件混合多种职责，应拆到多个目标 slice。

## 增量迁移策略

不进行一次性“大爆炸”重构：

1. 在当前实施阶段建立必要的 `app/pages/widgets/features/entities/shared` 边界、
   alias、公开 API 和 import lint；
2. Stage 1 Builder 的所有新代码直接遵守本文；
3. Stage 1 只迁移 Builder 依赖到的应用基础、Agent、AgentGraph、Catalog 和 revision
   代码；
4. Benchmark、History、Settings、Run 和 Replay 的旧代码在各自阶段触及时迁移；
5. 迁移期间允许新旧目录暂时共存，但禁止向旧的无所有权大桶目录增加新业务代码；
6. 每次迁移保持路由和用户行为可验证，空目录与无引用兼容文件最后删除；
7. 不因目录重构顺便改变 AgentGraph contract、后端 API 或旧导入行为。

这种策略比一次性重写稍有过渡成本，但能控制回归范围，并让 Builder 1.1 的交付证据
与纯目录移动分开。

## 代码评审检查表

涉及 `studio/` 的 Change 或 PR 至少检查：

- 新文件是否位于真正拥有该职责的 layer/slice；
- import 是否只向下且通过 slice public API；
- 是否把服务端资源、编辑会话、URL、临时 UI 与偏好状态放到正确所有者；
- entity 或正式 DTO 是否意外依赖 XYFlow/React；
- presentation 是否影响 AgentGraph canonical identity；
- Catalog/NodeContract 是否仍来自后端正式合同；
- 组件中是否出现散落 `fetch`、重复 DTO 或重复业务真相；
- 是否向旧根级大桶目录或巨型全局 CSS 添加了新代码；
- secret、运行 artifact 和模型响应是否经过明确的安全与持久化合同；
- 单元测试、typecheck、boundary lint、production build 和相应 e2e 是否覆盖风险；
- 文档描述的是已验证事实还是尚未完成的目标。

## 当前事实

本文建立时的 React/XYFlow 原型已逐步迁移到 entity/feature/widget 边界，TanStack Query、
immutable revision、Live/Replay 与 Benchmark 工作台已有已验证纵向切片。当前 Agent Builder
使用 schema-3 capability document 和 feature-local draft store；Catalog/revision/compile 仍由
entity query/API 层拥有，XYFlow 仍只是可重建投影。旧根级目录可能继续存在，但新代码不得
深化这些无所有权大桶。

本文仍是长期架构合同；每个新增迁移或能力只有在对应代码、测试、构建和浏览器证据完成后，
才能描述为已实现。
