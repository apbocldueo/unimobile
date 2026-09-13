# Studio Trajectory Replay

本文记录 Studio Stage 2 已实现并经过验证的离线 Replay 纵向切片。Replay 用于审计和
人工定位失败阶段，不连接设备、不启动 Agent，也不宣称自动失败诊断。

## 已实现范围

```text
显式本地导入
  ├─ native Replay package
  └─ legacy Benchmark result + trajectory + artifact + optional graph snapshot
                         │
                         ▼
ReplayEvidenceEnvelope V1
  ├─ SQLite：身份、状态、索引、结构化 envelope
  └─ Local Artifact Store：截图、XML、响应和导出包
                         │
                         ▼
History → /runs/:runId/replay
          Graph │ Virtual Phone │ Inspector
                 Agent / Benchmark 双轨时间轴
```

后端只接受显式、caller 已授权的来源，不递归扫描 workspace 或 `temp/`。导入先在
staging namespace 校验 schema、路径、大小与 SHA-256，再复制到受控存储并事务提交
SQLite 索引。源目录随后移动或删除，不影响已经成功导入的 Replay。

浏览器只使用 `runId + artifactId` 的 opaque identity。HTTP 不接受或返回宿主绝对路径；
resolver 拒绝绝对路径、`..`、symlink escape、目录、未知 media type、hash 不一致和
隐藏 artifact。默认 Bundle 排除 Prompt，并在 manifest 中记录排除事实。

## 本地运行和导入

在仓库根目录启动后端：

```bash
uv run python -m zhixing.studio serve \
  --host 127.0.0.1 \
  --port 8765 \
  --database temp/studio.sqlite3
```

在 `studio/` 启动 React 前端：

```bash
npm install
npm run dev
```

显式导入原生 Replay package：

```bash
uv run python -m zhixing.studio replay-import \
  --package /absolute/path/to/replay.zip \
  --database temp/studio.sqlite3
```

显式组合旧 Benchmark 证据：

```bash
uv run python -m zhixing.studio replay-import \
  --legacy-run /absolute/path/to/runtime-run \
  --benchmark-result /absolute/path/to/benchmark-result.json \
  --artifact-root /absolute/path/to/experiment-artifacts \
  --graph-snapshot /absolute/path/to/agent-graph.json \
  --database temp/studio.sqlite3
```

`--benchmark-result`、`--artifact-root` 和 `--graph-snapshot` 是可选的独立来源；未提供的
内容必须显示为 `not_captured` 或 `missing`，导入器不会根据 Agent 名称或当前 revision
猜测旧运行的图。`temp/` 只适合本地验证，产品持久性来自导入后的 SQLite 与受控
Artifact Store，而不是原始 `temp/` 目录。

## HTTP 与存储合同

前端使用以下只读接口；服务同时接受 `/studio/...` 与开发代理使用的
`/api/studio/...` 路径：

```text
GET /api/studio/replays?limit=<n>&cursor=<opaque>
GET /api/studio/replays/{runId}
GET /api/studio/replays/{runId}/artifacts/{artifactId}
GET /api/studio/replays/{runId}/bundle
```

列表使用稳定的 `(imported_at, run_id)` 排序和 opaque cursor。SQLite adapter 位于
repository protocol 后；未来 PostgreSQL adapter 应复用 import/list/get/artifact/bundle
合同测试，而不是让 service、HTTP 或 React 依赖 SQLite row ID。Stage 2 没有实现
PostgreSQL adapter。

大型内容不写入 SQLite BLOB。默认数据库旁的 `artifacts/` 是 Local Artifact Store，
包含 run-scoped 内容和导出包。当前没有产品级 quota、自动清理或删除 API；导入内容会
持续保留，直到未来独立的保留/删除 Change 定义并实现安全语义。

## Replay 投影语义

Adapter 将 Benchmark lifecycle 和 AgentGraph events 标准化为带全局 causal index、
source-local sequence、activation、node path、interaction 与 artifact correlation 的
moment。纯 reducer：

- 对相同 moment 幂等；
- 拒绝 identity 冲突、倒序、重复 source sequence 和缺少 start 的 terminal event；
- 对 source sequence gap 停在已验证前缀并标记 `partial`；
- 只在 observation 的因果时刻到达后显示截图，不泄漏未来证据；
- 分离 node aggregate 与每次 activation history；
- 独立保留 Agent terminal status 和 Benchmark outcome；
- 没有正式 skip event 时只显示 `not observed`，不伪造 skip reason。

播放、速度、cursor、自动跟随、Inspector 锁定和三栏宽度是前端交互状态，不进入
Replay 事实或 AgentGraph canonical identity。三栏宽度只保存为 localStorage 展示偏好。

## Focus-first 信息层级

Replay 工作台现在以“先理解 Agent，再排查组件”为固定优先级：

1. 顶部首先并列展示 Agent 运行结果与可选的 Benchmark 结果，两者不合并；同时展示
   已记录的失败/当前位置、正式原因和跳转入口。来源、完整性和设备证据降为可展开标签。
2. 左侧 AgentGraph 是主视图。没有不可变 Studio presentation 时只在 Replay 内使用
   自上而下的确定性布局；“聚焦执行”只框选并弱化一跳以外节点，“查看全图”恢复完整
   拓扑，二者都不删除节点、不修改 cursor、不写回 canonical graph。
3. 中间 Virtual Phone 只在当前因果时刻有可读截图时显示手机画面；否则缩成明确的
   `pending`、`not_captured`、`missing` 或 `corrupt` 证据状态，为流程图释放空间。
4. 右侧 Inspector 在没有选中 activation 时展示结果、正式位置、计数、关键证据和最多
   六个语义里程碑；选中后按 perception、planner/reasoning、ActionExecutor、verifier、
   observation provider 或外部组件角色展示关键输入/输出和动作结果。
5. 组件定义、完整 activation 历史、运行身份、Debug Payload、模型响应和证据清单放在
   次级 disclosure 中。Prompt 字段即使出现在历史 payload 里也会被递归隐藏。
6. 底部默认只显示 start、terminal、observation、action、feedback/router/loop 和正式
   Benchmark lifecycle 里程碑；完整 causal journal 仍可从“精确事件”展开。没有正式
   Benchmark context 时不渲染空 Benchmark 轨道。

Replay 工作区的顶部现在只显示 Agent 名称。Agent/Benchmark outcome、失败原因、
计数、provenance 和 integrity 仍在右侧默认 overview 可见，Run/revision/hash 则
放在可展开的技术详情中。名称来自当前 Agent metadata，只是可变展示文本，
不是历史 Replay 证据或 identity。

Replay timeline 保留在底部 dock 上层。仅当 provenance 为 `native_studio_run`、
不带 Benchmark context，且 exact local Agent/revision/canonical hash 仍全部匹配时，
最底部才显示可编辑 Task Run Bar。提交会创建新 Run 并 push-navigate 到
Live；Replay cursor、当前选择、旧 envelope 和 artifacts 不变。任何 imported、
Benchmark、legacy、fixture、缺失或不匹配条件均保守降级为只读原因，不查询
current revision 作为替代。

默认 Replay 比例为 Graph 50%、Virtual Phone 30%、Inspector 20%；无当前可读截图时
动态使用 58%/12%/30%。用户拖拽后的展示偏好会迁移到有边界的新版本 key，刷新保持，
“重置布局”只清除展示偏好，不删除或改写 Replay evidence。

本次重构没有新增或修改 Replay HTTP、SQLite、Artifact Store、设备调用或运行时语义。
数据仍只来自既有 `ReplayEvidenceEnvelope`、纯投影 reducer 和 scoped artifact resolver。

## 证据可用性

Replay 明确区分 `available`、`not_captured`、`excluded`、`missing`、`corrupt` 和
`redacted`：

- `available`：内容存在且 hash/size 已验证；
- `not_captured`：源运行没有采集该类证据；
- `excluded`：安全或产品策略明确不展示，例如默认 Prompt；
- `missing`：源记录声明过内容，但导入时无法取得；
- `corrupt`：内容或结构未通过验证；
- `redacted`：可读取的是安全处理后的内容。

完整模型响应只有 availability 为 `available` 时才按已采集 payload 展示；Prompt
始终不进入默认 Inspector 或 Bundle。Virtual Phone 的 `尚未到达截图证据` 与
`未采集截图` 也是两个不同状态，避免把尚未播放到 observation 的时刻误报为源未采集。

## 已验证证据

### 真实 Android 摘录

手工导入了当前 acceptance 运行
`d97fd96e0e15dac78a11c0fbd8f32e70`：

- 67 个 causal moments、4 个 observations、7 个受控 artifacts；
- Agent `success`，Benchmark `pass`；
- screenshot 可用并能按 observation 因果时刻显示；
- canonical hash 有记录，但 graph body/presentation 未被该旧运行采集，因此 Graph
  pane 如实显示 `graph_snapshot_unavailable`；
- UI XML、完整模型响应和 Debug Payload 未采集；Prompt 默认排除。

还导入了 controlled-fail 运行 `bfb785f2c75d8237b6f200931bdf5468`：

- 30 个 causal moments、2 个 observations、2 个 actions、4 个 artifacts；
- Agent `success`，Benchmark `fail`，证明两种结果没有被错误合并；
- canonical hash 为
  `sha256:81103632516524782361502bd150b0e22f503b9436f3f278bf81c3763f5ed206`，
  但旧运行没有 graph body，Graph pane 必须降级；
- screenshot 可用；UI XML、完整模型响应和 Debug Payload 未采集；Prompt 排除。

这些证据只证明指定 Android acceptance 摘录可导入和复盘，不证明任意 Android
trajectory、任意 AgentGraph 或实时设备控制。

### Fake 完整合同证据

浏览器 smoke 使用明确标记为 `fake_contract_fixture` 的完整 envelope，验证：

- AgentGraph body/hash、确定性 Dagre 布局、节点状态和 feedback badge；
- 因果 screenshot、UI XML、完整模型响应和 Debug Payload；
- Agent `success` 与 Benchmark `fail` 同时成立；
- 播放/暂停、0.5×/1×/2×、里程碑、末尾重播、双轨 phase、失败跳转；
- 点击节点锁定历史 activation，再回到当前 activation；
- History 深链接、浏览器 back/forward 和 Bundle 下载。

Fake 证据用于验证合同和界面，不是实际模型或真实设备能力。

### Focus-first 浏览器证据

本次界面重构额外在浅色和深色主题下验证了两个只读场景：

- 本地有限证据 Replay `run-80428d6ea8c9491ca85ea9fff53772e3`：可用 Graph、未采集
  screenshot、Agent 初始化失败、无 Benchmark；验证纵向全图、紧凑手机、正式失败
  跳转、来源 disclosure、精确事件、拖拽后刷新保持和布局重置。
- `benchmark-monitor-smoke-fixture.mjs` 的无设备 fixture：Agent `success`、Benchmark
  `pass`、1 个 observation-provider activation、无 screenshot；验证独立双结果、关键
  里程碑、activation drill-down、角色化 Inspector 和次级 disclosure。

浏览器控制台没有新增错误；只观察到项目既有的 React Router v7 future-flag 警告。
视觉检查期间发现并修复了“重置布局”与 Inspector 只读标签重叠的问题。

## 可复现验证

```bash
# Replay 后端合同、存储、安全与 HTTP
PYTHONPATH=.:tests uv run pytest -q tests/studio/test_replay_backend.py

# 完整后端回归
PYTHONPATH=tests uv run pytest -q

# 前端
cd studio
npm run typecheck
npm run lint
npm test
npm run build

# 可选：在默认 8765 被其他 Studio 服务占用时启动隔离 fixture
ZHIXING_STUDIO_FIXTURE_PORT=8766 npm run smoke:benchmark-monitor
ZHIXING_STUDIO_PROXY_TARGET=http://127.0.0.1:8766 npm run dev -- --port 5174

# OpenSpec
/Users/maczhen/.npm/_npx/abab5bd700860149/node_modules/.bin/openspec \
  validate implement-studio-trajectory-replay-2 --strict
```

原 Stage 2 里程碑记录的后端证据为 415 项通过。本次 focus-first 重构没有重跑或扩大
后端能力声明；前端完整回归为 93 个测试文件、412 项测试通过，typecheck、ESLint 和
production build 通过。浏览器验收使用上述本地有限证据 Replay 和显式 fake fixture。

## 已知限制

- Replay 本身仍是不可变的离线证据；可选 Task Run Bar 只是从已验证的
  native ordinary snapshot 创建新 Run，不会重试、改写或实时跟随旧 Run；
- Virtual Phone 只显示证据，不控制真实 Android/Harmony 设备；
- 旧 trajectory 缺失的 graph、XML、模型响应、Prompt 或 skip reason不能补造；
- 当前只提供 SQLite + Local Artifact Store，没有 PostgreSQL、远程对象存储、多用户
  授权、quota、清理或删除 API；
- 自动布局只影响 Replay presentation，不写回 AgentGraph；
- failure target 是基于正式事件和 terminal facts 的稳定跳转，不是根因诊断；
- 聚焦视图只支持一个正式 activation/failure 节点及其一跳邻域，不是自动执行路径摘要；
- 当前 pane 偏好是浏览器本地展示状态，不跨浏览器或用户同步；
- 窄屏仍以桌面研究工作台为基础，本次没有新增移动端专用布局；
- production build 仍有单个较大的 JavaScript chunk，后续可做路由级拆包。
