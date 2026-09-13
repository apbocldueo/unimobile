# Studio Live Run Workbench

本文记录 Studio Stage 4 已实现的普通 Agent 实时三栏工作区。它把 Stage 1 的
immutable Agent revision、Stage 2 的 Replay 投影与 Stage 3 的 durable Run service
连接为一个可刷新、可取消、可在终态交接到 Replay 的前端闭环。

这不是 Benchmark 入口。页面只接受普通 task；Benchmark Package、Task、
ExperimentProtocol、Evaluation Tree 和报告继续属于独立的 Stage 5 产品线。

## 已实现交互流

```text
Builder clean revision ────────────────┐
                                      ├─→ Run launch
Builder dirty draft → Save & Run ─────┘
  → three-pane launch workspace + bottom Task Run Bar
  → POST ordinary Run
  → /agents/:agentId/run?runId=<run>
  → exact immutable revision + Run resource
  → HTTP journal backfill
  → named SSE journal/heartbeat
  → factual projection
       ├─ read-only AgentGraph highlight
       ├─ causal Virtual Phone screenshot/action
       └─ current or locked activation Inspector
  → cooperative Cancel or natural terminal
  → authoritative Run refetch
  → retain the final Live story
  → explicit “打开完整回放”
  → /runs/:runId/replay when the same native Replay is available
```

Live 与 Replay 使用同一个 transport-independent Run evidence reducer。SSE、React
timer、XYFlow 和 artifact URL 不进入纯事实模型；同一次 native Run 的 journal 与
Replay envelope 通过版本化同源 fixture 验证终态等价。

## 启动

### 生产组合

在仓库根目录启动 Studio 后端：

```bash
conda run -n unimobile python -m zhixing.studio serve \
  --host 127.0.0.1 \
  --port 8765 \
  --database temp/studio.sqlite3 \
  --secrets ./secrets.yaml \
  --device-profile-config ./device-profiles.json
```

另一个终端启动 React/Vite：

```bash
cd studio
npm run dev -- --host 127.0.0.1
```

默认 Vite 地址为 `http://127.0.0.1:5173`。生产组合从服务端读取安全 Device Profile
目录并查询 exact revision readiness；浏览器不会提交 raw serial 或读取 Secret 值，
设备选择与副作用仍由后端 profile、`ObservationProvider` 和 `ActionExecutor` 边界负责。
完整配置见 [Studio Agent Run Readiness](studio-agent-run-readiness.md)。

### 可复现 fake-device 浏览器验收

开发脚本会创建独立 SQLite、保存一个确定性测试 Agent，并用慢 fake device 保留足够
的 live 检查和 Cancel 窗口：

```bash
PYTHONPATH=. uv run python scripts/studio_live_fake_server.py \
  --database temp/studio-live-browser-smoke/studio.sqlite3
```

脚本输出 `agentId`、`revisionId`、`designPath` 和 `launchPath`。它依赖 `tests/`
fixtures、使用 test-only Catalog entries，不进入安装 wheel，也不能作为真实 Android
证据。

## Builder、路由与启动合同

- `/agents/:agentId/design`：编辑 Agent。
- `/agents/:agentId/run?revisionId=<revision>`：为一个 valid immutable revision
  填写普通 task。
- `/agents/:agentId/run?runId=<run>`：恢复并跟随一个持久 Run。
- `/runs/:runId/replay`：读取同一 run identity 的终态 Replay。

Builder clean 且 current revision valid 时显示 `Run`；draft dirty 时显示
`Save & Run`，复用正式 Save mutation。invalid compile、保存失败和 optimistic
conflict 都留在 Builder，不创建假 Run。

Launch 现在不再弹出独立卡片，而是原地展示 exact revision 的只读
AgentGraph、明确的“尚未启动” Virtual Phone、revision readiness 和最底部
Task Run Bar。顶部只显示人类可读的 Agent 名称；Agent/revision/hash 仍是一致性
和授权依据，不会被可变名称替代。

Task Run Bar 要求非空 task，可选 metadata 的 JSON 根必须是对象且不超过
16 KiB。安全目录只有一个 Profile 时自动选择，多个时必须显式选择，空目录或 stale
偏好会阻止提交。同一语义表单的网络重试复用一个
`clientRequestId`；task、metadata 或 target 改变后才生成新 identity。accepted 后 URL
只保存 opaque `runId`，task 和 evidence 从后端资源恢复，不进入
localStorage。Live 期间底部改为持久 task、authoritative lifecycle 和协作式
Cancel，不显示第二个可编辑输入，也不暗示并行或覆盖运行中任务。

native ordinary Replay 只在 provenance 为 `native_studio_run`、没有 Benchmark
context，且 exact local Agent/revision/canonical identity 均可重新验证时恢复可编辑
Task Run Bar。新 task 使用 push navigation 创建新 Run，因此浏览器返回仍是
旧 Replay。Benchmark、imported、legacy、fixture、缺失 revision 或 hash 不匹配的
Replay 均 fail closed，只显示明确的只读原因，绝不回退到 current revision。

## 实时恢复与完整性

首次进入和断线后都从 exclusive cursor 连续查询：

```text
GET events?after=<confirmed>&limit=<bounded>
  → 验证每页 schema/sequence/fingerprint/highWaterMark
  → 直到 confirmed cursor 到达该页 high-water mark
  → EventSource(.../events/stream?after=<confirmed>)
```

后端固定发送两类 named SSE frame：

- `event: journal`：包含版本化 durable journal envelope；
- `event: heartbeat`：仅表示连接活性，不推进 cursor 或事实。

浏览器不依赖原生 EventSource 的自动恢复。发生 error 时会关闭旧 source，从最后确认
cursor 做 HTTP backfill，再以有界退避显式新建 EventSource。完全相同的重复事件幂等
忽略；identity/fingerprint 冲突、倒退 sequence 或无法补齐的 gap 会进入 integrity
error，并冻结最后一个已验证事实前缀。刷新 live URL 会恢复同一个 Run，不会重新执行。

极快 activation 的最短高亮只是有界 presentation queue；事实 reducer、timestamp、
duration 和 cursor 都立即更新。用户锁定历史 activation 后，Inspector 保持选择，
Graph、Phone 和 SSE 继续跟随，并可“回到当前节点”。

## 三栏证据

- **AgentGraph**：读取 Run 绑定的 exact revision，并验证 agent/revision/canonical
  identity；按 `node_path` 和 `activation_id` 显示当前路径、执行次数、feedback/loop
  badge、成功和失败，不按标题或组件名猜测节点。
- **Virtual Phone**：只读加载 run-scoped opaque screenshot/UI XML reference，显示
  observation/interaction identity、安全设备来源和最近 Action。新交互尚无截图时旧图
  标为 historical/stale；缺失或损坏时不把旧图冒充当前画面。
- **Run Inspector**：默认以按交互累积的因果故事显示 Memory、Perception、Reasoning、
  Action Executor 等正式 capability owner；已完成步骤不会被下一条内部事件覆盖。
  “组件详情”分开显示安全输入与输出；Run/activation ID、hash、node path、generated
  glue、Debug Payload、provenance 和完整模型响应只在默认折叠的“技术详情”中按需查看。
  presenter 只使用 immutable snapshot、projection map 和 typed Debug Payload，不按
  Python class 或事件标题猜 capability。

完整 Prompt 在后端 capture 能力存在时经 redaction 后永久保存为 hidden artifact；
前端只显示 hidden availability，不读取、预取或导出 Prompt 内容。旧 Run 缺少 typed
reference 时显示 `not_captured`，不按 `artifactIds` 数组位置猜测。

### capability execution map

schema-3 capability Run/Replay 的左栏现在使用独立于 Builder presentation 的稳定纵向布局：
Input 在上、Output 在下，并行上下文能力保持紧凑分组。默认“运行路径”省略不帮助定位当前
步骤的静态/feedback 长线；“关系全图”恢复 immutable document 中的全部正式 relations。
当前节点使用唯一高对比 rail/pointer 与“当前执行”文字，已完成节点只保留中性“已经过”，
用户锁定和正式失败使用不同语义。切换关系视图、锁定 Inspector 或回退 Replay cursor 都不会
改写 projection、Builder 坐标或 AgentGraph；画布不显示终态结果词。

## Cancel 与终态交接

`Cancel` 调用 Stage 3 的幂等 command，并明确说明它是协作式取消。活动中的模型、设备或
Python 调用不会被宣称为已强制中断；页面持续跟随 `cancelling`，直到下一个安全
activation boundary 产生 terminal 事实。

收到唯一 `run.terminal` 后，页面关闭 SSE，重新查询 authoritative Run，并验证
lifecycle、result 和 terminal event 一致。Live 页面保留最终 Graph、Phone、Inspector
故事和失败事实，不再自动跳转。只有 `replayAvailability=available` 才显示
“打开完整回放”；用户点击后复用同一 identity-verifying handoff decision，进入同一
`runId` 的 Replay。Replay pending/missing/corrupt/not-captured 时保留可检查的 Live
terminal 页面、已验证 journal prefix 和明确的重新检查状态。

## 浏览器 smoke 步骤与预期观察

1. 用 fake server 输出的 `designPath` 打开 Builder，修改节点 lifecycle。
2. 预期 Builder 变为 dirty，按钮显示 `Save & Run`。
3. 点击后预期保存新 immutable revision，并进入含新 `revisionId` 的 launch route。
4. 输入普通 task 并启动，预期 URL 绑定一个 `runId`。
5. live 页面预期同时显示 `LIVE RUN · open`、只读图、有效 PNG、Inspector 和一致
   cursor；活动节点为 `build_action`。
6. 在 Run 未终止时刷新，预期同一 `runId` 经 HTTP backfill + SSE 恢复，不创建第二个
   Run。
7. 确认 Cancel，预期 lifecycle 显示 `cancelling`、按钮显示 `Cancelling…`，页面仍可
   检查 graph、phone 和 Inspector。
8. 到达安全边界后，预期仍停留在 Live 并保留最终故事；只有在同 Run Replay 可用时
   显示“打开完整回放”。点击后 Replay 显示 `cancelled`、`native_studio_run`、时间轴和
   相同 run/artifact identity。
9. 浏览器控制台不应出现应用异常或 XYFlow missing-handle/edge 警告。
10. 在终态 native ordinary Replay 底部输入不同 task 并运行，预期使用
    同一 exact revision 创建不同 `runId`，Live 显示新 task 和真实 lifecycle。
11. 第二次运行交接到 Replay 后执行浏览器返回，预期回到第一个
    Replay URL，旧 envelope、timeline、artifact 和 Run identity 不变。

截至 2026-07-26，本流程已在真实浏览器和确定性 fake device 上执行通过，包括
Save & Run、live 三栏、刷新恢复、Cancel 和 Replay 交接。它没有连接真实 Android。

截至 2026-08-03，持久 Task Run Bar 增量验收使用同一 fake Agent/revision
验证了 Builder `Run` 入口、三栏 launch、底部 task 提交、Live 中的持久
task/Cancel/cancelling、failure 结果、Replay playback、Replay 二次提交以及返回旧
Replay。两个持久 Run 分别是
`run-063f8970455d47c48972ac8d0b92fb3d` 和
`run-c63d7b6282124cafbe4f3aa39efb47c3`。该路线中图上操作保持为 clean revision，
因此 Builder 显示 `Run`；dirty draft 的 `Save & Run` 使用同一 save command
和 launch route，已由 Builder route 测试验证。这是明确的 no-device/fake 证据，
不是真实 Android 成功运行证据。

截至 2026-08-10，`refine-studio-run-story-inspector` 的真实浏览器验收使用
`Studio Capability Test Agent`。既有成功 Run
`run-16d40c51369d46bba0e2ef8d4a846a7a` 验证了两轮交互的累计故事、1-based 交互编号、
Perception 安全设备观察与截图输入、Reasoning 缺失摘要的诚实空态、ActionResult/effect、
历史步骤锁定、Replay 前缀和终态时机、按需技术 identity/provenance，以及 Graph 节点和
边上没有 `DONE`/`FAIL` 文本。新建 Run
`run-23d7bcbd719749b88f23455f80105300` 因本机没有已连接 Android target 终止；页面保留了
`Selected Android device target is unavailable`，没有自动跳转，并在用户显式点击后进入
同一 Run Replay。该负向结果证明终态展示和 handoff，不证明新的真实 Android 成功运行。

## 可复现自动化验证

```bash
# Stage 4 focused backend
uv run pytest -q \
  tests/studio/test_run_models_repository.py \
  tests/studio/test_run_artifacts_debug.py \
  tests/studio/test_run_execution.py \
  tests/studio/test_run_replay_http.py \
  tests/studio/test_run_event_performance.py \
  tests/runtime/test_android_graph_runtime.py

# Stage 1/2/3 Studio 与 Runtime
PYTHONPATH=tests uv run pytest -q tests/studio tests/runtime

# clean wheel / public package boundary
uv run --extra dev python -m pytest -q \
  tests/packaging/test_artifacts.py \
  tests/packaging/test_isolated_install.py \
  tests/packaging/test_public_import.py \
  tests/packaging/test_resources.py \
  tests/packaging/test_benchmark_package_boundary.py

# 前端
cd studio
node node_modules/typescript/bin/tsc -b
node node_modules/eslint/bin/eslint.js src
node node_modules/vitest/vitest.mjs run
node node_modules/typescript/bin/tsc -b
node node_modules/vite/bin/vite.js build

# OpenSpec
/Users/maczhen/.npm/_npx/abab5bd700860149/node_modules/.bin/openspec \
  validate implement-studio-live-run-workbench-4 --strict
```

本次已记录的独立结果为：focused backend `61 passed`、Studio/Runtime
`157 passed`、clean-wheel/package boundary `15 passed`、前端 `68 passed`，并且
typecheck、lint 与 production build 通过。Vitest 仍输出 React Router v7 migration
future-flag 提示，Vite 仍输出大 chunk advisory；前者是依赖升级提醒，后者是后续性能
工作，两者都没有被当成测试或构建成功的替代证据。

持久 Task Run Bar 增量验证的独立结果为：11 个 focused 前端文件
`33 passed`，完整前端 98 个文件 `424 passed`，typecheck、ESLint 和
production build 通过；未改动的 ordinary Run repository/execution/Replay HTTP
合同 `37 passed`。后端合并首次运行曾在协作式 Cancel 时观察到一次
`eventHighWaterMark` 的异步时序差异；单项重跑与完整合并重跑均通过，
本 Change 没有修改后端时序或契约。

Run Story Inspector 增量验证结果：`npm test -- --run` 为 115 个文件、495 个测试通过；
`npm run typecheck`、`npm run lint` 和 `npm run build` 通过。浏览器还验证了 1050 px
窄宽右栏没有水平内容溢出；CSS 只在 `prefers-reduced-motion: no-preference` 下启用
短过渡，并保留 focus-visible 与非颜色状态文本。该 Change 没有修改后端、API、DTO、
Runtime、AgentGraph 或 persistence。

Execution Map 增量验证结果：完整前端 117 个文件、505 个测试通过；typecheck、ESLint 与
production build 通过。真实浏览器使用既有成功 `Studio Capability Test Agent` Replay 验证了
纵向布局、Input → Memory 的唯一 current 切换、历史节点中性化、关系模式无损切换、Output
终点、cursor 回退清除未来 Output 状态和画布无 `DONE`/`FAIL`；控制台无错误。本增量没有新建
Run、调用设备或修改后端/API/DTO/Runtime/Builder/AgentGraph。

## 已知限制

- 当前是本地单用户、单进程、默认单 worker 与单安全 device profile；
- Task Run Bar 不是 queue；活动 Run 不提供第二 task，也不支持并行运行；
- Stage 4 真实 Android UI smoke 因用户没有明确选择 profile/device/task 而保持
  **未验证**；fake device 不替代真机证据；
- 2026-08-10 本机 `adb devices -l` 返回空设备列表，因此本轮只能复验已有成功 Android
  Run，并对新 Run 保留设备不可用失败事实；没有把历史 Replay 当成新的设备执行；
- Virtual Phone 第一版只有 artifact snapshot，没有实时视频或点击/拖动控制设备；
- 无 pause、checkpoint、resume、节点级 retry 或强制中断 active call；
- 普通 Run 不创建 Benchmark outcome、Evaluation Tree、报告或 paired comparison；
- model adapter 未捕获完整响应时只能显示 safe summary 与 `not_captured`；
- revision 删除、PostgreSQL、对象存储、配额、自动清理和删除/回收站属于后续 Change；
- Replay 用于审计与人工定位失败阶段，不提供自动根因诊断。
