# Studio 中英文界面

实现变更：`add-studio-bilingual-interface`，验证日期：2026-10-17。

## 使用

打开 **设置 / Settings**。页面顶部有 **中文** 与 **English** 两个按钮；所有设置分区均可看到。点击后立即切换，无需刷新，选择保存在当前浏览器、当前 origin 的 localStorage。新环境沿用中文默认；刷新会恢复已经选择的语言。

当前开发服务的验证地址为 `http://127.0.0.1:5274/settings`。其他启动端口属于不同 origin，浏览器显示偏好不跨 origin 同步。

## 实现边界

- `studio/src/shared/i18n/locale.ts`：严格的 `zh-CN` / `en` 偏好、React 订阅、静态文案与插值消息、document language/title。
- `studio/src/shared/i18n/messages.ts`：1,217 条静态 UI 文案的英文对应；包含重复用途或辅助文案，不是独立功能数。
- `SettingsPage` 提供显式按钮；localStorage 只新增 `zx-studio-language-v1` 的 allowlisted 字符串，不保存业务内容。
- React 组件订阅语言状态，纯展示 helper 读取同一状态；静态展示词表在读取时选择语言，避免模块初始化时固定住语言。
- Builder、Inspector 与 Replay 的 memoized 展示投影包含语言依赖；不通过 remount、DOM 替换或远程翻译实现切换。
- 覆盖当前路由可达的导航、首页、Agent Library、Builder、普通 Run、History / Replay、Benchmark Catalog / Composer / Authoring / Monitor / Report、Settings。旧版未路由页面不在此次迁移范围。
- 帮助页已有完整双语内容；没有显式 `lang` 参数时跟随全局偏好，合法 URL 语言参数仍可选定文章语言。帮助页语言选择也会更新全局显示偏好。
- 内置模板通过可信模板 ID 本地化显示名称；外部模板名称、用户命名的 Agent / 节点、参数、Prompt、任务内容与证据保留原文。
- 英文首页使用重新从实际界面捕获的 `builder.en.png`、`replay.en.png`、`benchmark.en.png`；中文保留已有配图。两组均为历史截图，Composer 截图仅为 preview。

语言切换不修改 AgentGraph、BenchmarkTask、Protocol 或运行结果，不创建 Run / Experiment，不连接设备或调用模型。未知外部消息和历史数据可能仍使用源语言；不应为界面英文而翻译证据。

## 验证

执行命令：

```bash
npm --prefix studio run typecheck
npm --prefix studio run lint
npm --prefix studio test -- --reporter=dot
npm --prefix studio run build -- --outDir ../temp/studio-i18n-20261017/dist
```

本次完整前端回归为 **145 files / 681 tests passed**，类型检查、lint 与生产构建通过。构建使用独立临时输出目录，未覆盖已有 `studio/dist`。已有 React `fetchPriority` 测试警告和生产 chunk-size 提示不构成本次检查失败。

重点覆盖：

1. 挂载状态下切换；输入含中文、`<script>` 和占位符样式文本时保留原值，React 仍按普通文本转义。
2. localStorage 持久化与模块重载恢复；非法语言回退；存储被拒绝时仍可内存切换。
3. 所有翻译模板的占位符集合一致。
4. Settings 保留选中分区，切换不产生请求。
5. 真实 Builder store 的未保存 document、baseline、非法 JSON raw buffer、session、generation 在语言变化后保持原引用 / 原值。

浏览器实际验证：中文 → English → 刷新仍为 English → 中文 → English；英文 Builder 能静态校验；英文 Replay 显示既有 Agent Completed / Benchmark Passed；英文 Composer 验证与确定性 preview；英文首页选择 `.en.png`，帮助页跟随英文。

Composer 在中英文界面的同一配置 preview fingerprint 均为
`sha256:a91c60d85ba16cee8a0ce6ea4070717d388e97b4da16ea53b664b53cc679ae74`。
这次仅进行静态验证和证据读取，没有发起新的 Android / 模型执行。

为拍摄首页示例，另对本次独立彩排数据库中的 `ICSE Demo Rehearsal` 使用了既有 Auto arrange 并保存布局。该操作产生展示 revision 2，不是语言切换的副作用。revision 1 / 2 的 AgentGraph identity 均为
`sha256:8448a9a42cb802f625b6692f641609663ec89b9647d5084100c2cb1531e81524`，移除 presentation 后的文档内容完全一致。

本地截图与原始翻译接入清单位于 `temp/studio-i18n-20261017/`；不可据此宣称任意设备 / 模型或所有历史版本已验收。

## 手工复核

进入 Settings，点击 English，检查导航和设置标题；刷新后应仍为 English。打开一个已有 Agent，应看到 Validate / Save / Try Run 等控件。查看已有 Replay，其控制和状态标签应为英文，任务原文与截图不变。回到 Settings 点击中文，当前界面恢复中文。
