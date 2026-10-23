# Studio Builder 阶段 3：用表单配置组件

这一阶段把“拖入一个能力节点”推进到“这个能力具体用什么实现、参数是什么”。原来的
Inspector 主要依赖 JSON 输入，用户需要自己理解 `params` 和 `dependencies` 的结构。
现在常用组件参数会根据后端 Catalog 提供的 `configSchema` 自动生成表单。

## 用户流程

```text
选择画布节点
→ 选择具体实现/版本
→ 在组件参数表单填写常用字段
→ 查看依赖是否已配置
→ Validate
→ Save revision
```

支持的常用参数类型包括字符串、整数、数字、布尔值和枚举。Catalog 的默认值只作为提示
显示，用户真正修改字段后才写入 Agent 文档。数组、嵌套对象和扩展字段继续通过高级 JSON
编辑器处理，避免丢失组件扩展能力。

模型依赖也有一条专用的表单路径。对 Catalog 声明的 `llm` 依赖，用户先选择可用的
dependency-only 提供方，再填写模型 ID、API 凭证 SecretRef、可选服务地址和常用运行参数。
SecretRef 输入只会写入 `{secret_ref: "..."}` 引用，不接受 API Key 原文；原始依赖 JSON 仍
保留在“高级依赖 JSON”中处理扩展字段和未知结构。

表单编辑和高级 JSON 编辑共用同一份 feature-local 草稿状态。表单修改会清理当前候选组件
对应的旧 JSON 原文缓冲，防止保存时旧原文覆盖新表单值；其他候选组件的原文输入不受影响。
Undo/Redo、Validate、Save revision 和现有 SecretRef 安全规则继续生效。

## 涉及的层

| 层 | 变更 |
| --- | --- |
| Catalog | 复用后端 `configSchema`，前端不维护第二套组件字段定义 |
| Builder Inspector | 增加 `ComponentConfigForm`、`LlmDependencyForm`、实现选择说明、依赖状态和高级 JSON 提示 |
| Builder store | 增加带原文缓冲同步的候选组件字段更新命令 |
| 后端/运行时 | 无 API、AgentGraph、运行内核或设备边界变化 |

## 验收证据

真实浏览器中选中 `Reasoning` 节点，看到 `Preset`、`Prompt File`、`Parser Name`、`Input Mode`、
`Parse Max Retries` 表单字段；把 `Parse Max Retries` 从 2 改为 4 后，右侧高级 JSON 同步显示
`"parse_max_retries": 4`，工具栏显示草稿未保存。点击撤销后恢复为 2，且 revision 没有被保存修改。

自动化覆盖：组件表单类型转换、复杂字段提示、表单与原文缓冲同步、模型依赖表单和 Inspector 集成。
真实浏览器还在缺少 `llm` 的 Reasoning 节点上选择 OpenAI LLM、填写 `gpt-4.1-mini` 和
`openai_api_key` SecretRef；Validate 后原来的缺少依赖错误消失，只留下该 fixture 自身的
缺少输入端口和不可达 Output 诊断。完整前端回归为 **138 files / 643 tests passed**，
typecheck、lint 和 production build 通过。

## 验证命令

```sh
cd studio
npm test -- --run
npm run typecheck
npm run lint
npm run build
```

本阶段验证的是组件定义编辑闭环，不包含模型调用、Android 设备执行或组件运行质量评估。

## 限制

- 当前表单覆盖 Catalog 中常见标量字段；数组和嵌套对象仍需高级 JSON 编辑。
- 目前专用表单覆盖 `llm` 依赖；其他依赖类型和无法由 Catalog 描述的复杂结构继续在高级 JSON 中编辑。
- 表单不会在前端保存真实凭证；SecretRef 只是服务端凭证的名字。
- 表单显示字段名来自 Catalog 的属性名或 title，Catalog 若没有 title，会把下划线转换为空格并首字母大写。
