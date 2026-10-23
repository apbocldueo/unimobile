# Studio Builder 用户旅程审查（2026-09-17）

后续：[UX 阶段 1 已实现与验收](studio-builder-editing-phase1.md)覆盖撤销/重做、拒绝连线解释、端口命中区和镜头/校验分离；本文保留修复前的观察，反馈创作等问题仍待后续阶段。

状态：已完成一次 Coding Agent 主导的浏览器走查、定向源码核对与最小 Android 运行尝试；提出修改建议，尚未实施产品修改。不是用户研究统计，也不证明整个前端没有 Bug。

## 结论与范围

当前 Builder 已有拖放、端口连接、配置、校验、版本保存和运行入口，但“能显示 Agent 图”与“用户能独立搭出 Agent”之间仍有缺口。最严重的不是配色：模板的有界反馈关系无法通过普通拖线重建，模型配置仍要求手写依赖 JSON，画布同时暴露数据关系、隐式运行服务与反馈，却没有解释它们的区别。

用户提出了真实体验、重点审查拖拽搭建、参考 Dify/Langflow、允许后续同时调整前后端的要求，并说明模拟器已运行。以下浏览器操作、源码核对、测试和文档由 Coding Agent 执行；修改顺序是建议，尚不是用户接受的实施合同。

本次基线是当前有大量既有未提交修改的工作树，不对应某个干净发布版本。没有修改业务代码、重置已有改动、提交或推送。私有学习计划不进入本报告。

## 实际环境与对象

- 浏览器：Codex 内置浏览器，1280 × 720，现有深色主题。
- 前端：当前 `studio/` Vite 开发服务，`http://127.0.0.1:5173`。
- 后端：正式 `python -m zhixing.studio serve`，端口 8765，独立工作区 `/tmp/zhixing-builder-ux-20260917`。
- 使用已有受信本地 SecretRef 和设备 Profile 文件；未打印或复制凭证值。工作区与原有 Agent 数据隔离。
- 空白测试 Agent：`agent-3e8c031824bf4e80b32053b6738d9d83`，名称 `UX 0917 — 从零搭建`；Revision 2 保留为缺少依赖的无效草稿。
- 模板测试 Agent：`agent-00ace96688b8445691bd1f70bf70b58c`，名称 `UX 0917 — 模板搭建`；有效 Revision 2：`revision-0bab4083cc4345b398e883c10df970d4`。反馈破坏实验未保存，最后恢复了有效版本。
- 实际 Run：`run-f57fb1772f2b425785510b9fe294edf6`。不是 fake device。

## BUX-01 / P1：有界反馈无法用相同拖线操作重建

复现：

1. 从“Mobile Agent 显式闭环（推荐）”创建 Agent，初始 Graph 校验通过。
2. 选择 Action Executor → Memory 的“下一轮”虚线，Inspector 显示 `Kind: feedback`、最大反馈次数 10。
3. 删除这条关系。
4. 从 Action Executor 的 `result` 拖到 Memory 的 `write`，即原来的两个端口。
5. 新边显示 `Kind: data`，没有反馈次数或切换关系类型的控件。
6. Validate 得到普通数据/控制边形成循环的错误；错误包含内部生成节点，且没有精确定位入口。

原始有界反馈 (image not bundled in the core source)

相同端点重连后变成非法普通环 (image not bundled in the core source)

源码证据：`studio/src/features/agent-builder/model/flowAdapter.ts` 的 `validateBuilderConnection` 只生成 `termination`、`activation` 或 `data`；`BuilderInspector.tsx` 的 `RelationInspector` 只能编辑已有 feedback 的次数，没有创建/转换 feedback 的入口。后端拒绝普通环是正确的，问题是前端没有提供与模板语义相符的创作操作。导入完整文档和复用现成模板不等同于用户可以拖拽创作该语义。

建议：正式区分“传递数据”和“进入下一轮”的创作命令。针对合同允许的源/目标，让用户明确选择反馈语义，并配置支持的终止条件、次数和耗尽处理；必要时扩充安全 Catalog/创作元数据。不能把所有画出来的环自动猜成反馈，也不能关闭编译器的环检测。

验收：用户从空白或删除反馈后的模板出发，仅通过 UI 建立正式有界反馈，保存、刷新、再编译保持语义；fake Runtime 证明多轮和耗尽行为。不得将 UI 测试替代 Runtime 证明。

## BUX-02 / P1：模型配置没有可完成任务的表单

复现：空白 Agent 拖入 Reasoning，参数和依赖都是 `{}`。页面要求补齐 `llm`，但用户只能编辑 `Candidate 1 dependencies` JSON。模板的依赖框包含 namespace、name、version、params、model、SecretRef 等嵌套字段。展开编辑只扩大文本区域，不解释如何选模型。

新节点缺少模型依赖 (image not bundled in the core source)

模型依赖仍是嵌套 JSON (image not bundled in the core source)

建议：先做有正式合同支撑的模型配置控件：Provider、模型、服务端凭证引用、超时/重试高级项。模型目录不可用时允许明确的模型 ID 输入，不虚构可用列表。内置 Memory 等简单参数使用经验证的 schema 表单；未知扩展保留高级 JSON。没有证据表明所有现有 schema 与运行时参数完全一致，不能直接宣称一个通用表单生成器支持任意插件。

涉及前后端：前端表单与原始 JSON 的无损编辑状态；Catalog 的字段说明、默认值、枚举和依赖声明；后端权威校验。凭证值仍留在受信服务端配置中。

验收：不查源码、不手写依赖对象，能给新 Reasoning 配置可用模型；表单和高级 JSON 往返不丢扩展字段；切换实现明确说明将影响什么。

## BUX-03 / P2：不允许的连线静默消失

复现：空白图中 Input.task → Reasoning.task 成功。随后多次将 Reasoning.action 拖到 Output.connection，包含用 DOM 几何核实端点后的尝试，均未产生边，也没有可见拒绝原因。点击式连接同样没有给出可操作解释。

源码解释：Reasoning 未声明正式 termination，拒绝是预期约束。但 `isValidConnection` 仅返回布尔值；警告放在 `onConnect` 中，而无效连接在此前就被过滤，且没有结束连接后的拒绝解释流程。

建议：拖动时突出合法目标，端口旁提供类型/用途说明；释放到不兼容端口时明确解释原因和下一步。提供“从端口添加兼容组件”，减少逐个尝试。端口实测在该空白视图为 8 × 8 CSS 像素；建议扩大交互热区并提供键盘操作，不把本次测量当作完整无障碍认证。

## BUX-04 / P2：查看画布使语义校验看起来失效

复现：有效模板初始显示“当前 revision 已保存 / Graph 已通过”。只点击 Fit View，立刻变成“草稿有未保存修改 / Graph 待校验”，按钮变为 Save & Run。没有改组件、参数或关系。

Fit View 后变成待校验 (image not bundled in the core source)

源码解释：`builder.store.ts` 的 `setViewport` 经 `updateCurrentDocument` 更新 presentation，同时清空 `compileResult`。本次没有发现 canonical identity 被错误改变；问题是语义状态和视图状态在用户反馈中混在一起。

建议：区分语义更改、布局更改与临时视口。纯平移缩放不清空语义校验；如果产品决定将布局存入 revision，也应显示“布局未保存”，避免要求用户重复校验未改变的 Agent。保存并发与 source map 仍需绑定明确的文档快照。

## BUX-05 / P2：推荐模板难以读懂，空白画布也缺少操作引导

实际观察：

- 首次进入模板时 Reasoning 底部超出可视区域。Fit View 可露出完整图，但节点文字仍小。
- 模板按折返方向排列，Reasoning → Action Executor 的连线在卡片后方穿行；不同数据边同色，视线很难追踪。
- Perception 的 `observation *` 没有可见来源但模板合法。它由运行时生成服务供应；UI 未就地解释“系统提供”，用户容易误认为必需输入漏接。
- 节点默认文字如 `reasoning capability`、端口 `control`、组件实现数量，不直接回答该组件做什么、下一步该接谁。
- 空白 Agent 一创建就呈现 Output 不可达错误，而没有“添加感知/决策/执行组件”的渐进指引。
- 1280 × 720 下，上方三层导航/工具区约占 198px，左库约 220px、右栏约 360px；未选择组件时右栏仍占大量空间。可拖动栏宽已有，但无法独自解决阅读顺序问题。

模板首次打开 (image not bundled in the core source)

建议：三栏框架可以保留，但默认让画布主流程按“输入任务 → 理解屏幕 → 判断 → 执行动作”阅读，记忆关系作为辅助，反馈沿外侧返回；这种布局是表达现有依赖，不额外规定 Runtime 的执行顺序。使用中文主标签配准确技术副标签、稳定的类型视觉区分、选中高亮上下游、常用端口优先与系统输入标识。保留完整关系的检查入口。自动整理布局应可撤销；不能静默改写语义或每次添加就把全图缩小。

## BUX-06 / P2：缺少普通图编辑的撤销/重做

本次删除反馈、重建、校验后，在非文本输入状态按 Cmd+Z，错误的数据关系仍保留。工具栏“更多操作”只有 Save As、Import、Export、Load revision、Reset draft，未见普通图编辑 Undo/Redo。源码仅找到特定批量 LLM 操作的撤销状态，不是全局图编辑历史。

建议：为新增、删除、移动、连线、配置提交提供有界会话历史；一笔拖动算一次操作。文本框使用文本撤销，避免与画布撤销冲突。Reset draft 是回到已存版本，不是撤销上一步。此能力直接影响用户是否敢试错。

## RUN-01：真实运行未成功，失败展示仍可更清楚

从 Builder 的 Run 进入正式启动页，提交：

> 仅打开 Android 系统设置首页，看到设置首页后立即结束。不要修改任何设置，不要登录，不要打开个人文件。

浏览器实际显示 Memory、Perception、Reasoning、Action Executor 进展和真实设备截图，`start_app` 动作显示成功。下一轮观察失败，后台资源确认：

```text
lifecycle: terminal
result.status: device_failure
result.kernelStatus: failure
result.errorCode: runtime.device_failure
stepCount: 1
activationCount: 11
interactionCount: 1
error: observe: ui_dump failed (exit_code=-1, timed_out=False):
       ERROR: null root node returned by UiTestAutomationBridge.
event page: 45 items, highWaterMark 45, terminal true
```

真实设备运行失败 (image not bundled in the core source)

Live 终态与 Replay 入口工作，点击后可打开此 Run 的只读回放；回放初始位置如实显示尚无截图。未逐事件核验全部 Replay。

需要改善：失败结论应优先说明“第二轮读取设备界面失败”，展示重试/回到设计的明确路径。观察失败后，手机仍显示此前桌面截图并标“当前截图”；建议标“最后成功观察，后续读取失败”，并说明时间/交互归属。动作区域的“设备效果已确认”不能让用户误解成整个任务目标已被验证。

本次不能证明 Android 失败原因一定是界面切换竞态，也不能宣称任务已到达设置首页。没有通过本轮修复设备采集或实施重试。后续如增加等待/重试，应仅针对明确的可重试观察错误，不盲目重新执行有副作用的动作；需独立验收。

## 本次确认已有改善

- 鼠标将 Reasoning 从左库拖入画布成功，节点可见并被选中。
- Input.task → Reasoning.task 的合法端口连接成功。
- 无效 JSON `{` 使全局显示配置输入错误，并禁用保存/运行。
- 带无效 JSON 点击 Settings 出现离开保护，“保存并离开”不可用；选择继续编辑保留原文。
- 修复 JSON 后可保存为明确标记的 invalid draft，未冒称图有效。
- 模板可保存有效 revision，重新进入 Design 后保持有效和反馈线。
- 实际启动、Live 状态变化、终态失败以及进入 Replay 可用。

## Dify / Langflow 参考：借鉴机制而非照搬领域模型

本次参考官方文档，没有登录并亲测这两个产品的当前 UI。

| 官方依据 | 值得采用的机制 | ZhiXing 的边界 |
| --- | --- | --- |
| [Langflow Components](https://docs.langflow.org/concepts-components) | 默认展示常用/必需选项；类型端口、悬浮说明、兼容组件检索 | 类型必须来自正式 Catalog，系统观察不能伪装成用户必须手接的变量 |
| [Langflow Build flows](https://docs.langflow.org/concepts-flows) | 以模板开始，连接与配置后进入试用 | 模板必须能通过正式可视化操作表达与修改 |
| [Dify Hotkeys](https://docs.dify.ai/en/cloud/use-dify/build/shortcut-key) | 撤销/重做、自动整理、选择与平移模式、连接高亮 | 首要是操作可发现，不能仅在快捷键文档中提供 |
| [Dify Orchestration Logic](https://docs.dify.ai/en/cloud/use-dify/build/orchestrate-node) | 显式表达循环/迭代，说明顺序与并行关系 | 当前 schema 3 的有界 feedback 与通用 Loop 不等价，不承诺新支持任意控制图 |
| [Dify Single Node](https://docs.dify.ai/en/cloud/use-dify/debug/step-run) | 节点级输入、输出、耗时与错误检查 | Mobile Agent 状态/设备动作有副作用；离线样例检查和真实设备试运行需要明确分开 |

不建议这一轮增加大量节点种类、自动生成任意 Agent 或全面重写 Runtime。优先补齐现有能力从创建到修改再到运行的路径。

## 建议实施顺序（待逐轮确定 OpenSpec）

1. **完整、可恢复的连线编辑**：反馈创建/编辑、非法连接解释、Undo/Redo；纯视图操作不使语义校验失效。第一验收目标是用户能删除并重建推荐模板的闭环，不查源码也不改 JSON。
2. **看得懂、配得出**：模板布局和空白引导、清楚的节点/端口用途、模型配置表单、内置组件参数表单。按合同扩充后端元数据，保留高级 JSON 和准确的失败诊断。以首次使用者完成一个最小 Agent 为验收任务。
3. **运行后的解释与恢复**：运行前显示实际模型/设备/预算，明确设备观察失败、最后截图与任务结果的区别；独立修查本次 Android 读取失败。增加真实设备任务矩阵，不把一次小任务通过推广为普遍可靠。

每一轮均先定义可复现用户操作与预期，再做定向实现、合同回归和真实浏览器回归。示意流程应服务于能力语义，不能通过隐藏真实限制获得“看起来能运行”的界面。

## 复查命令和证据限制

本次定向前端测试：**6 files / 38 tests passed**；这些通过与上述浏览器缺陷同时成立。

```sh
cd studio
npm test -- --run \
  src/features/agent-builder/ui/BuilderCanvas.test.tsx \
  src/features/agent-builder/ui/BuilderCamera.test.tsx \
  src/features/agent-builder/ui/BuilderEditCommands.test.tsx \
  src/features/agent-builder/ui/BuilderLeaveGuard.test.tsx \
  src/features/agent-builder/ui/BuilderToolbar.test.tsx \
  src/features/agent-builder/model/flowAdapter.test.ts --reporter=dot
```

从仓库根目录重启本次隔离后端（端口空闲时；本地配置必须仍有效）：

```sh
conda run -n unimobile python -m zhixing.studio serve \
  --host 127.0.0.1 --port 8765 \
  --workspace /tmp/zhixing-builder-ux-20260917 \
  --secrets secrets.yaml \
  --device-profile-config studio/device-profiles.json \
  --no-installed-benchmarks
```

另一个终端：`cd studio && npm run dev -- --host 127.0.0.1`。用上述测试 Agent 复查 BUX-01，不保存破坏实验；离开时明确放弃当前测试编辑。临时目录可能被系统清理，截图和复现步骤则随本报告保留。

没有执行整个前端的全部测试、全部浏览器/尺寸/主题、触屏/读屏、复杂多节点图、任意插件、Benchmark、新用户招募实验或长时性能验收。本轮真实 Android 只有一次失败运行，未达到成功执行验收。没有把历史报告和自动化测试数量当作本轮实际用户成功率。
