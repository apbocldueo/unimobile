# Studio AgentGraph 1.1 Builder

本文说明当前已经实现并验证的 Stage 1.1 authoring vertical slice。它覆盖 Agent
创建、Catalog 驱动的图编辑、后端验证、不可变 revision、加载、JSON 迁移与导出；
不覆盖 Agent 运行、Replay、虚拟手机、SSE 或 Benchmark 编辑。

## 启动

先在仓库根目录启动本地后端：

```bash
uv run python -m zhixing.studio
```

后端默认只监听 `127.0.0.1:8765`。再开一个终端启动 React/Vite：

```bash
cd studio
npm run dev
```

访问 `http://127.0.0.1:5173/builder`。`/builder` 是兼容创建/选择入口；正式编辑
地址是 `/agents/:agentId/design`。

## 核心工作流

1. 输入 Agent 名称，选择空白图、schema 2 模板或 legacy migration fixture。
2. 从左侧 Catalog 点击或拖拽组件/控制节点到画布。后端 Catalog 是组件版本、
   NodeContract、端口、配置 schema 与 availability 的事实源。
3. 在右侧编辑 exact contract、single/fallback binding、参数、SecretRef、依赖和
   Input、Output、Condition、Router、State、Subgraph、Loop、Feedback 属性。
4. 点击 **Validate**。后端无副作用地编译 schema 2 文档，返回 authoritative
   diagnostics、nested source map、AgentGraph 1.1 和 canonical hash。
5. 点击 **Save revision**。每次保存追加一个 immutable revision；invalid draft
   也可以保存，但只有 valid revision 才保存 AgentGraph 与 canonical hash。
6. **Load revision** 可按 revision ID 打开历史版本；**Reload remote** 在冲突时
   丢弃本地草稿并加载远端 current revision。系统不会自动覆盖冲突 revision。
7. **Export** 下载 schema 2 JSON；**Import** 导入 schema 2，或显式迁移 schema 1。
   迁移返回 diagnostics，且不会修改原始文件。

`saved/dirty` 与 `valid/invalid` 是两组独立状态。只移动节点会产生新的文档 revision，
但不会改变 canonical hash；修改节点、binding、参数或边等 semantic 内容通常会改变
hash。

## 单画布能力层级

Builder 只展示一张可编辑 AgentGraph，不提供“Agent 视图/完整执行图”切换，也不生成
代表节点或第二套边。每个 semantic node、edge 和 typed port 都仍使用原始 canvas
identity；点击任何形态的节点都会进入同一个 Inspector。

- Perception、Planner、Reasoning、Memory、ActionExecutor、Verifier 是六类主要能力。
  当前 Agent 只展示实际存在的实例，不补造缺失角色。
- Grounder、Tool、外部插件与用户自定义 Subgraph 等独立能力默认使用完整卡片。
- 正式模板中的 DeviceObserve、ActionRequest、Iteration 和 Terminal 是可审计的运行胶水，
  以紧凑操作符显示；Input/Output 以边界锚点显示。它们没有从图中删除，端口和诊断也
  没有合并到其他节点。
- 普通 Router、Condition、Loop、Subgraph 和未知组件保守地使用完整卡片。只有明确的
  presentation `renderMode` 能把某个模板节点显示为 `inline`；Input/Output 可按节点 kind
  默认成为 `boundary`。

`renderMode: card | inline | boundary` 只属于 schema 2 的 `presentation.nodes`，会随文档
保存和导出，但不进入 canonical AgentGraph。旧 revision 不会被静默重写，因此没有该字段
的旧运行胶水仍可能显示为完整卡片；创建新的正式示例即可看到新的层级。

## 数据位置与替换边界

默认 SQLite 位于操作系统用户数据目录，并使用 workspace 路径的 SHA-256 摘要隔离：

- macOS：`~/Library/Application Support/ZhiXing/studio/workspaces/<digest>/studio.sqlite3`
- Linux：`${XDG_DATA_HOME:-~/.local/share}/ZhiXing/studio/workspaces/<digest>/studio.sqlite3`
- Windows：`%LOCALAPPDATA%\ZhiXing\studio\workspaces\<digest>\studio.sqlite3`

数据库不会保存 workspace 绝对路径。`AgentDocumentRepository` 是存储协议，
`SQLiteAgentDocumentRepository` 只是默认 adapter；未来 PostgreSQL 实现应保持
Agent/revision identity、分页、optimistic conflict 和 transaction 语义，不让上层
依赖 SQLite rowid、PRAGMA 或方言 JSON 操作。

可用以下命令打印当前 workspace 的实际路径：

```bash
uv run python -c "from pathlib import Path; from zhixing.studio import default_studio_database_path; print(default_studio_database_path(Path.cwd()))"
```

## 手工验收

自动检查：

```bash
cd studio
npm run typecheck
npm run lint
npm run test
npm run build

cd ..
uv run python -c 'import sys; sys.path.insert(0, "tests"); import pytest; raise SystemExit(pytest.main(["-q"]))'
```

浏览器验收：

1. 创建空白 Agent，加入 Input 与 Output，并连接 `value → result`。
2. Validate 后应显示 `valid` 和 `sha256:...` canonical hash。
3. 保存、刷新页面，应仍看到相同节点、边和 hash。
4. 仅移动节点，重新 Validate/Save；应产生新 revision，但 hash 不变。
5. 修改语义参数或连线；重新 Validate 后 hash 应改变，或得到可定位诊断。
6. 导出 JSON；根字段应为 `schemaVersion: 2`、`contractVersion: "1.1"`。
7. 用两个页面基于同一 revision 保存；后提交者应得到 409 conflict，而不是覆盖前者。
8. 从正式示例创建 Agent；应只出现一张画布，四个实际核心能力为完整卡片，四个运行
   胶水为紧凑节点，Input/Output 为边界锚点；点击“设备证据”后 Inspector 应显示真实
   `tpl_observe`。
9. 加入 Grounder 或 Tool；它应作为完整扩展卡片出现。切换浅色/深色主题后，标题、正文、
   端口、选择与诊断状态都应可读。

需要查看数据库时，可在停止写入后使用 `sqlite3 <path>` 检查
`studio_agents`、`studio_agent_revisions` 和 `studio_schema_migrations`。业务代码与
工具不得依赖 SQLite 内部 rowid。

## 已知限制

- **Run · Stage 2** 明确禁用；当前 UI 没有启动 Graph Runtime。
- 没有 Replay、实时事件、虚拟手机、截图/UI XML 或运行 Inspector。
- 外部组件仍在宿主 Python 进程中；Catalog availability 不等于进程沙箱或权限许可。
- 缺失可选依赖的组件会显示为不可用；安装依赖与 provider 审批不由 Builder 自动完成。
- `Load revision` 首版需要输入 revision ID，尚无可视化 revision timeline。
- production bundle 当前约 541 kB，Vite 会提示大于 500 kB；功能正确，但后续应做路由
  与重型画布代码拆包。
- 本 Change 已使用项目本地 OpenSpec 1.6.0 通过 strict validation。
