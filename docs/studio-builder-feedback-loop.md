# Studio Builder 阶段 2：可搭建的下一轮反馈

2026-09-18，Coding Agent 按用户要求继续修复 Agent 拖拽搭建闭环。本阶段只处理
“删除或新建反馈关系后还能不能继续搭建”的问题，不改变 AgentGraph、运行内核、后端
持久化或设备边界。

## 解决的问题

模板中原本能看到一条虚线反馈边，但用户从画布重新连线时，前端只会创建普通 data 或
activation 关系。于是用户删除反馈后无法重建；即使看见“下一轮”标签，也无法知道它的
触发条件和耗尽行为。这个阶段把关系创作拆成两个明确模式：普通连线仍是默认模式，
“下一轮反馈”是用户主动选择的模式。

反馈创建要求：

- 两端都必须是能力节点，不能连接 Input 或 Output；
- 端口类型必须兼容；
- 目标节点必须能沿普通 data/activation 关系回到来源节点，避免把普通无界环误写成反馈；
- 新关系自动带现有 schema-3 的安全起始策略：`terminal_status` + `falsy`、最多 3 轮、
  `fail`。

反馈边继续使用虚线和“下一轮反馈”标签。重连时根据原关系恢复普通/反馈类型，反馈策略
也会保留；不合法重连不改变原关系。

## Inspector 编辑

选中反馈边后，Inspector 提供条件字段、判断方式、JSON 条件值、最多反馈轮数和达到上限
后的行为（`fail`、`continue`、`terminate`）。字段编辑仍走现有 feature-local store、
Undo/Redo、Validate、Save revision 和服务端 CAS 流程。前端只做端点和回路的即时提示；
谓词字段/值是否适合运行时仍由后端编译器最终判断。

## 涉及的层

| 层 | 变更 |
| --- | --- |
| 画布交互 | 增加临时普通/反馈模式选择，反馈创建和重连使用同一套 Catalog 校验 |
| flow adapter | 增加普通回路可达性检查、默认反馈策略和反馈语义标签 |
| Inspector | 编辑 feedback predicate、maxIterations、onExhausted |
| 状态与后端 | 不新增 API、字段或运行时 edge kind；继续使用已有 `StudioCapabilityRelation` |

## 验收证据

完整前端回归：**134 files / 629 tests passed**；`npm run typecheck`、`npm run lint` 和
`npm run build` 通过。

真实 Studio 后端（隔离工作区 `/tmp/zhixing-builder-ux-20260917`）和浏览器页面
`/agents/agent-00ace96688b8445691bd1f70bf70b58c/design` 完成以下流程：

1. 选中模板反馈边并删除，确认图进入未校验草稿；
2. 选择“下一轮反馈”，从 Action Executor.result 拖到 Memory.write，反馈边重新出现；
3. 在 Inspector 把条件改为 `score == 1`、耗尽行为 `terminate`、最多 4 轮；
4. Validate 显示 `Graph 已通过`，保存 revision，刷新页面；
5. 重新选中关系，仍显示 `score`、`4` 和 `terminate`；
6. 将测试策略恢复为原模板的 `terminal_status`、`falsy`、`10`、`fail` 并再次 Validate/Save。

这证明的是 Builder 编辑、保存和重新加载闭环，不是模型质量或 Android 设备执行证明。

## 复查命令

```sh
cd studio
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

## 限制

- 新建反馈的默认最大轮数是 3，模板历史值仍可保留为 10；最终上限和谓词语义由后端编译器约束。
- 目前没有在画布上直接绘制条件文本；策略集中在选中边后的 Inspector，避免把运行时内部字段塞进节点图。
- 浏览器证据使用 1280×720 深色桌面；尚未验证触屏、读屏、浅色主题和超大图布局。
- 本阶段没有新增运行时重试、设备调用或 Backend API；若后端未来扩展谓词类型，前端选项需同步更新。
