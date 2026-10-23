# Builder UX 阶段 1：可恢复的基础编辑

2026-09-17，用户明确要求先落地 UX 阶段 1。Coding Agent 实现、测试并操作真实浏览器验收。
对应 OpenSpec：`improve-studio-builder-editing-reliability`。这里的“阶段 1”是本次 UX 修复顺序，
不是重新定义 Studio 历史里程碑。代码已在当前开发工作区实现，未发布或提交。

## 用户现在可以做什么

- 工具栏提供撤销/重做；支持 Cmd/Ctrl+Z、Cmd/Ctrl+Shift+Z、Ctrl+Y。
  删除一个节点和它的关联连线是一笔操作；删除后焦点消失也能用快捷键恢复。
- 节点添加、删除、移动、连线及配置修改进入当前会话历史。配置原文（包括未完成的 `{`）
  可以恢复。文本框保留浏览器自己的文本撤销，不把一次文本撤销当成删除节点。
- 缩放、平移和 Fit View 只是查看画布，不产生未保存内容、不清空 Graph 校验。
  移动节点仍可保存位置，显示“布局有未保存修改”，同时保留语义校验。
- 错误拖线、点选连接、重连会解释类型/方向/输入容量/结束能力等原因；错误重连保留原关系。
  在空白处放开只取消手势。规则仍由现有 Catalog 校验器判断。
- 端口命中区域由 8px（边界 10px）扩大到 24×24 CSS px，保留小圆点和类型提示，
  增加焦点/连接高亮。也可以聚焦端口，按 Enter 或空格点选连接。

连线失败的明确原因 (image not bundled in the core source)

移动节点保留校验结果 (image not bundled in the core source)

## 涉及的层与选择

仅修改 `studio/src/features/agent-builder/` 的编辑状态、命令、画布、节点呈现和测试。
后端 API、AgentGraph、AgentConfig YAML、BenchmarkTask JSON、运行内核与设备边界未修改。

| 原先 | 本次 |
| --- | --- |
| 没有普通编辑历史，误删需手动重建 | feature-local store 保存可恢复的文档、raw buffer 和选择状态 |
| Fit View 写入文档并清空校验 | 镜头属于临时会话；位置属于 presentation；语义修改才清空语义校验 |
| 非法连接在 `isValidConnection` 被挡住，`onConnect` 收不到错误 | 在连接结束处读取尝试的端口，复用同一校验规则说明原因 |
| 删除焦点节点后快捷键无目标 | 记住最后一次工作区交互归属，点击工作区外即放弃接管 |

历史不含服务端 revision/CAS 权威。保存只推进 baseline；保存后撤销是相对新 baseline 的未保存修改。
Undo/Redo 推进编辑代次，迟到响应不能覆盖新内容。校验响应可跨纯 presentation 更改生效，
前提是仍属于相同 session 且当前有效配置语义等同该快照。此比较不替代后端 canonical hash。

每个历史方向最多 50 个检查点、约 4 MiB 序列化 UTF-16 内容；这是近似内容预算，不是 JS 堆总量保证。
超大检查点会清空该方向可回溯历史。连续同字段输入合并，失焦或显式命令结束分组。
重载、导入、Reset、切换编辑会话清空历史；不会把 raw configuration 放进 localStorage。
相比持久化事件日志，这个选择改动较小，也不承诺崩溃恢复或跨设备撤销。

## 验收证据

最终全前端回归：**134 files / 626 tests passed**。`typecheck`、`lint`、独立目录生产构建通过。
本批新增历史、端口尝试、快捷键测试；扩大镜头/连接结束/异步命令用例，覆盖保存中编辑或撤销、
CAS 基线不倒退、冲突保留、无效原文、原子删除、分组、上限、旧会话、迟到校验和焦点删除。

实际浏览器使用真实 Studio 后端与隔离工作区 `/tmp/zhixing-builder-ux-20260917`。
先检查开发页面，最终关键流程在生产构建上完成，使用后端既有允许的 `127.0.0.1:5173` 来源。
曾尝试 5174 预览；GET 可读，但写命令被后端来源限制拒绝，随后改用既有 5173，未放宽来源配置。
测试 Agent：`agent-00ace96688b8445691bd1f70bf70b58c`（UX 0917 — 模板搭建）。

| 真实操作 | 观察到的结果 |
| --- | --- |
| Fit View、Zoom In、Zoom Out | 保留“当前 revision 已保存 / Graph 已通过”，Save disabled |
| 拖动 Reasoning | “布局有未保存修改”，Graph 仍通过；Cmd+Z 恢复，Cmd+Shift+Z 重做 |
| 删除 Reasoning → Cmd+Z → 重做 | 节点/线数 6/7 → 5/3 → 6/7；重做再次删除节点 |
| 配置输入 `{` → 工具栏撤销 → 重做 | 合法配置恢复；重做恢复精确 `{` 与错误状态，不能保存 |
| 无效原文中键入空格 → 文本 Cmd+Z | 只撤销空格，仍保留 `{`，没有跳回合法图快照 |
| 参数 2→3 → 保存 → 撤销 → 再保存 | revision 4 保存 3；撤销后为未保存 2；revision 5 保存 2，未回退 CAS |
| 重载已保存页面 | valid revision 与原参数恢复；历史为空 |
| Reasoning.action → Output（拖拽和点选） | 明确提示该能力不能直接结束 Agent，不新增关系 |
| 删除 Input.task→Reasoning.task，再用 Enter 点选端口重建 | 普通关系恢复，后端 Validate 通过 |
| 撤销重建，再鼠标拖拽重建同一普通关系 | 后端 Validate 通过，canonical hash 与原图相同 |
| 把该关系重连到 Perception.observation | 提示 `task_input → device_observation` 不兼容；原关系仍指向 Reasoning |

浏览器首次发现“删除后焦点落到 body，Cmd+Z 无效”，实现修复并增补回归后再次实测通过。
这说明仅测试 store 命令不足以证明完整交互。

最终保留 revision 5：`revision-b003216352c5493e9d71875c3d2df214`，状态 valid，参数
`parse_max_retries=2`，后端只读 API 独立核对。canonical hash：
`sha256:8448a9a42cb802f625b6692f641609663ec89b9647d5084100c2cb1531e81524`。
测试性连线修改已撤销；验收后恢复原来的 Vite 开发服务（5173），临时预览服务已停止。截图同时记录原文重做 (not bundled in the core source)、
重建通过 (not bundled in the core source)和最终已保存页面 (not bundled in the core source)。

## 可复查步骤

在现有本地服务的测试 Agent 设计页：

1. Fit View、缩放，再拖一个节点：前两者不产生修改；拖动仅提示布局修改。
2. 选中 Reasoning，Backspace 删除，Cmd/Ctrl+Z 恢复，Shift+Cmd/Ctrl+Z 重做。
3. 将配置改成 `{`，点击撤销/重做，检查原文和禁用的 Save 状态。
4. 尝试 Reasoning.action→Output，检查错误原因；不要为测试点击 Run。
5. 在独立测试 Agent 上改参数、保存、撤销、再次保存、刷新，核对内容与新版本。

```sh
cd studio
npm test
npm run typecheck
npm run lint
VITE_STUDIO_API_BASE=/zhixing-studio npx vite build --outDir /tmp/zhixing-studio-builder-phase1-dist
```

运行构建预览时先释放自己启动的 5173 服务，再运行：

```sh
npx vite preview --host 127.0.0.1 --port 5173 --strictPort --outDir /tmp/zhixing-studio-builder-phase1-dist
```

预期为上述测试全部通过、构建成功；后端启动方式见[原始 UX 审查](studio-builder-ux-review-20260917.md)。
本轮没有运行模型、Android 任务或 Benchmark；编译通过不是设备执行证据。

## 剩余限制与后续阶段

- 阶段 2 仍需实现反馈连线创作；删除反馈再当普通数据线重建的问题尚未修复。
  现阶段可用 Undo 恢复被误删的完整反馈关系，不能把这当成已支持反馈创建。
- 本轮观察到普通线与反馈线重叠，点击线的包围盒可能选中另一条；模板布局/连线辨识仍属于后续工作。
- 原生 `window.confirm` 在内置浏览器自动化中曾阻塞，需要用户手动取消。
  “带未完成原文的删除确认→恢复”组合由确定性 store 测试覆盖，本轮未完成真实确认后的组合流程。
- 真实视觉检查为 1280×720 深色桌面；未验证浅色、触屏、读屏或大图性能。
  24px 是图内 CSS 命中区，随画布缩放，并非所有缩放下都保持 24 屏幕像素。
- Undo 语义修改后须重新 Validate；历史不跨刷新。模型表单、整体布局与 Android 读取失败留在后续阶段。
- OpenSpec 文件已按 requirement/scenario 结构人工核对；本机没有可用 OpenSpec CLI，未声称 CLI 校验通过。

工程面试说明见阶段 1 工程记录 (not bundled in the core source)。
