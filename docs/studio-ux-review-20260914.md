# Studio 用户体验评审：2026-09-14

状态：原始公开版本评审保留；UX-01/UX-02 已在开发工作区完成第一批编辑可靠性修复与定向验收，尚未公开发布。其他意见仍未在本批实施。不是完整功能验收或“无 Bug”证明。

修复后的行为、截图、真实服务保存/刷新/失败重试证据及人工检查限制见 [Builder 编辑会话说明](studio-builder-edit-session.md)。下文“实际结果”描述原始 release-v2 的评审基线，不应误读为当前开发候选版本仍有相同表现。

## 评审对象与方法

- 对象：公开分支 `release-v2`，commit `1c999b0d719d92be30c48d6a730d30a9a112655c`。
- 运行副本：`/private/tmp/zhixing-publish-20260913.sSheXp/remote-final3`。
- 实际浏览器访问前端 `127.0.0.1:5173`，连接后端 `127.0.0.1:8876`。
- 隔离数据库：`/private/tmp/zhixing-docs-demo/studio.sqlite3`。没有配置设备、模型凭证或 Benchmark Package，关闭 installed benchmark discovery。
- 主要按桌面视口检查，含 1280×800、1024×768；截图也包含浏览器默认尺寸。不据此宣称全断点兼容。
- Coding Agent 实际点击、输入错误配置、导航返回、保存、刷新并截图；这是启发式体验评审，不是招募真实研究者完成的可用性研究。
- 本地开发工作区存在大量未提交变更，本报告不把其内容混作公开版本的已验证行为。
- 未修改业务代码，未推送本报告，未调用模型或执行真实设备任务。测试偏好已恢复为深色、标准字号，临时视口覆盖已撤销。

测试创建的两个对象保留在隔离数据库中，便于复测：

- `UX audit — blank`：`agent-3812b4b2ecc249dbb564104843002817`。
- `UX audit — example`：`agent-9254dfa9f0bf4772bc13f0613b035bbb`。

## 结论

已有可工作的创建、配置、保存、刷新恢复和页面导航基础，但还不能把当前版本视为让新用户放心自助使用的成熟工作台。
最先应修复的是编辑可靠性和状态真实性，而不是全面换皮。三栏编辑器的基本结构可以保留，需改善添加节点的可见性、配置层次及运行前的引导。

## 已复现的功能问题

### UX-01 / P1：站内导航会无提示丢失未保存编辑

复现步骤：

1. 首页点击“创建 Agent”，建立空白 Agent。
2. 在能力库点击 Memory；页面显示“草稿有未保存修改”。
3. 不保存，点击“运行环境未就绪 · 查看 Settings”。
4. 在设置页使用浏览器返回。

实际结果：没有离开确认；Memory 消失，页面恢复到初始 Input/Output，并显示“当前 revision 已保存”。
另一路径也复现：添加 Reasoning → 点击全局 Agents → 继续设计，新增节点消失。
这是未保存编辑丢失，不是已经提交的 revision 丢失。

导航前：有未保存编辑 (image not bundled in the core source)

导航返回：新增节点消失 (image not bundled in the core source)

对应公开版本代码：`studio/src/widgets/agent-builder-workbench/AgentBuilderWorkbench.tsx:42–56`。
已有 `beforeunload` 防护，但组件卸载会 `clear()`；浏览器文档卸载与站内路由切换不是同一件事。

建议：统一保护所有离开编辑会话的入口，提供“保存并离开 / 放弃修改 / 继续编辑”；保存失败时保持原页和草稿。
输入框中尚未解析成功的文本也必须参与离开保护。不要把含敏感内容的业务草稿直接塞进 localStorage。

验收：导航菜单、Settings 提示按钮、设计/运行标签、浏览器后退都不会静默丢稿；取消离开保留原文；只有明确放弃后才丢弃。

### UX-02 / P1：配置框 JSON 无效，但全局仍报告“已保存、校验通过”

复现步骤：

1. 从“Mobile Agent 显式闭环（推荐）”创建 Agent。
2. 选择画布上的 Reasoning。
3. 将 Candidate 1 config 改为单个 `{`，点击 Validate。

实际结果：字段内显示 JSON 语法错误，顶部仍显示“当前 revision 已保存 / Graph 已通过”，并出现“校验通过”通知；Save revision 不可点击。

无效配置与通过状态同时出现 (image not bundled in the core source)

对应公开版本代码：`BuilderInspector.tsx:17–54` 的 JsonField 将原始文本与错误保存在局部 state，只在解析成功后调用 onCommit；`BuilderToolbar.tsx:82–85` 校验 store 中的 document。
因此校验通过的是此前的合法文档，不是用户此时看见的配置。没有证据表明后端接受了无效 JSON；问题在前端状态和用户反馈没有对齐。

建议：把编辑会话的 raw buffer、解析错误、未提交状态纳入全局编辑状态汇总；有无效字段时阻止 Validate/Save/Run 对当前编辑内容作成功承诺，并提供定位字段的入口。保留原文，不能自动回退后声称已保存。

验收：输入 `{` 后全局明确提示“配置格式错误，尚未验证”；修复后验证确实针对最新内容；跨节点切换也不能把无效原文静默吞掉。

### UX-03 / P2：点击能力库新增节点，节点可能落在当前画布之外

复现：新建空白 Agent → 点击 Reasoning。右侧出现 Inspector，但新节点在画布右边缘之外，主要内容不可见；Fit View 后才找到。

新增节点在画布可视区外 (image not bundled in the core source)

公开版本 `BuilderPalette.tsx` 使用 `nextNodePosition(count)`；`flowAdapter.ts:282–283` 根据数量生成固定坐标，没有按当前 viewport 放置。这与观察到的现象一致。

建议：点击添加落在当前可见画布附近并选中；避免覆盖已有节点。拖放继续尊重用户落点。必要时轻量平移，不应每次强制 Fit View 导致整图突然缩小。

验收：不同缩放、平移和桌面尺寸下，点击添加的新节点都能立即辨认、选择并编辑。

## 设计与引导问题（不是全部都属于程序 Bug）

### UX-04 / P2：空白创建缺少下一步引导

首页“创建 Agent”进入空白图，创建成功即出现 `graph.reachability.unreachable_node`，且归属显示为 document。
空白图不完整本身是正常的，但这不应让新用户误以为自己刚创建就弄坏了系统。

空白创建后的底层错误 (image not bundled in the core source)

建议：首用主入口突出“从示例开始”，保留空白创建给熟悉用户；空白画布给可执行的搭建说明。
诊断默认用“Output 还没有连接到任务流程”等用户语言，附原因和定位操作；底层 code/identity 放入技术详情。不能靠隐藏诊断把无效图改称有效。

### UX-05 / P2：运行准备流程尚未形成闭环

当前路径是 Run 禁用 → Settings → 只读 Provider/SecretRef/Profile 信息和一行服务端启动命令。
诊断真实，但新用户仍需要知道配置文件格式、文件放哪里、如何验证、配置好后如何回到原 Agent。
点击帮助进入的是明确标为占位的帮助页，未连接已经建立的文档站。

建议：增加分项准备清单：模型配置、设备配置、当前 Agent 校验；每项提供具体文档或安全配置示例入口、刷新验证、返回原 Agent。
仍由服务端保管真实凭证，不要求把密钥输入图文档，也不需要为了体验绕过 readiness gate。

### UX-06 / P2：Inspector 默认展示过多实现细节，编辑空间不足

选择 Reasoning 后，右栏首先展示 Family、Logical ID、exact implementation、single binding policy、完整组件标识，实际配置在较下方；依赖需要在右栏滚动后再操作 JSON 文本框。
普通参数、服务依赖与技术身份之间没有足够清晰的任务层次。

浅色、大字号下的 Inspector 布局 (image not bundled in the core source)

建议：默认先回答“这个组件做什么 / 使用哪个实现 / 必须配置什么”，提供参数、依赖、技术详情分区；有正式 schema 的字段使用有说明的控件，无 schema 的扩展保留明确 JSON 编辑入口。
提供展开编辑器或可调整宽度，不能通过猜字段名生成有误的表单。

### UX-07 / P2：缺少资源的 Experiment Composer 是操作死路

本次隔离环境主动未配置 Benchmark Package 和 Device Profile，因此 Catalog 为空是预期结果，不是发现机制失效。
但“新建 Experiment”仍进入完整表单：Benchmark/Profile 只有占位选项、验证按钮禁用、右侧要求“完成左侧选择”，没有就地解释如何取得缺少的资源。

缺少前置资源时的 Composer (image not bundled in the core source)

建议：表单顶部列明阻断项，并给“添加 Benchmark 的说明 / 配置设备 / 返回 Catalog”入口；区分未配置、搜索无匹配和加载失败。
Agent 下拉应让用户看得出当前 revision 是否可用，避免用户选择后才发现问题。此点是建议，本轮没有执行有资源的 Composer 全链路。

### UX-08 / P3：工作台有较多重复标题和面向开发者的文案

Run 页在对象栏显示 Agent 名称后，又单独占一行重复名称；Inspector 默认强调 contract、节点数等技术数据，真正待办是底部的设备配置问题。
多个页面使用 `immutable revision`、`exact task`、`canonical identity`、`Stage 5.3 · durable create` 等词。对研究人员这些并非都无用，但不应成为完成基本动作前必须理解的门槛。

运行准备页面的布局 (image not bundled in the core source)

建议：保留对象级导航，减少重复标题；运行前优先展示准备清单和启动条件，开始运行后才突出设备与执行证据；内部阶段编号移到版本/开发说明。
中英文用词制定统一规则，关键状态与操作优先统一，技术标识保留准确原文。
本轮未做正式对比度或无障碍合规测量，不据截图断言 WCAG 不合格。

## 已通过与未覆盖

已实际通过：

- 从空白和官方模板创建独立 Agent。
- 查看组件参数及依赖。
- 将模板 Reasoning 的 `parse_max_retries` 改为 3，验证、保存 Revision 2，刷新并再次查看，值仍为 3。
- 无 Device Profile 时阻止执行，并如实显示尚未开始，没有伪造设备截图或运行结果。
- 访问普通 Runs 空状态和 Experiment Composer 缺资源状态。
- 深浅主题和字号选择刷新后保留；检查后恢复原偏好。
- 相关 Builder 自动化测试 4 个文件、11 项全部通过：

```bash
cd studio
npm run test -- \
  src/features/agent-builder/ui/BuilderInspector.test.tsx \
  src/features/agent-builder/ui/BuilderToolbar.test.tsx \
  src/features/agent-builder/model/builder.store.test.ts \
  src/features/agent-builder/ui/BuilderCanvas.test.tsx
```

测试通过与 UX-01/02 的浏览器复现同时成立，说明需要补跨组件、跨路由的验收场景。

未覆盖：真实 Android、付费模型请求、运行中的 SSE/取消/恢复、带真实结果的 Replay、Benchmark Report/Evidence/Export、第三方插件、多窗口冲突、超大图、长时性能、全部键盘和读屏体验。不得把这轮结果推广成整个前端无 Bug。

## 建议分三轮实施

1. **编辑可靠性**：UX-01、UX-02。先补能复现失败的测试，再修状态汇总与离开防护；不改运行语义。
2. **从创建到可运行**：UX-03、UX-04、UX-05、UX-07。实现可见的添加反馈、示例优先、可操作的诊断、文档与配置入口。
3. **桌面编辑效率**：UX-06、UX-08。整理 Inspector、工具栏与字号层次，在深浅主题及常见桌面宽度下复核。

上述是待用户确认的修改建议，尚未建立新的实施 Change。建议先批准第一轮，不要把修复编辑丢失与全面视觉重设计打包为一个大改动。
