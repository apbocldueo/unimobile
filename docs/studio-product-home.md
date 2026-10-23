# 知行产品首页与工作台

日期：2026-09-28。Change：`introduce-studio-product-home`。

> 后续入口调整：现行首页按钮为“进入知行”，直接到 `/agents`；`/workspace` 已兼容跳转到我的 Agents。下文保留首轮实现记录，当前行为见 [个人使用入口](studio-personal-entry.md)。

## 需求与本轮实现

用户指出原首页更像日常控制台，希望首页成为介绍产品的门面，并确认了首页／工作台
分离、真实产品展示、构建→运行→评测和首次使用流程的方向。Coding Agent 完成本轮
页面、路由、样式、回归测试和浏览器验收；没有新增设备执行或 Benchmark 能力。

- `/`：独立品牌导航、产品主张、可切换的大幅 Builder / Replay / Benchmark 截图、
  三项能力介绍、四步使用流程、研究开发入口、常见问题和工作台入口。
- `/workspace`：原 `StudioHomePage`，保留运行准备、最近 Agent、任务结果、实验和
  首次使用引导。工作区导航第一项改为“工作台”；Studio 标识返回产品首页。
- Agent、Run、Replay、Benchmark、Experiment、Settings、Help 的既有地址保持有效。
- `App` 只在进入工作区路由后加载 `StudioApplication`，后者持有原查询 Provider、
  registry bootstrap 和工作区路由。新首页本身不启动这些资源查询。
- 产品预览选择保存在组件局部状态；切换图文不运行任务、不创建资源、不连接设备。
  CSS Modules 只影响首页，兼容既有浅色／深色偏好；没有自动播放或动效依赖。

新 slice 为 `studio/src/pages/product-home/`，页面不依赖 entity、feature 或运行状态。
没有用新的数据模型替代 AgentGraph，也没有合并 Agent 与 Benchmark 定义。

## 图片来源与事实边界

三张 PNG 均从已经存在的仓库证据原样复制到页面 assets，由构建工具输出带 hash 的资源：

| 首页资源 | 原始来源 | 页面上的事实解释 |
| --- | --- | --- |
| `builder.png` | `docs/assets/studio-builder-canvas-20260928/arranged.png` | 已整理的 Builder 示例画布 |
| `replay.png` | `docs/assets/studio-journey-20260928/replay-copy-task.png` | 历史任务未完成，展示失败排查入口 |
| `benchmark.png` | `docs/assets/studio-usability-review-20260928/13-composer-preview.png` | 执行前配置预览，不代表评测已通过 |

这些截图不是实时设备、当前配置或当前用户的运行结果。没有添加虚构客户、成功率、
设备数量、多设备调度、任意 Android 任务兼容或自动失败诊断的宣传。

## 本轮验证

- `npm test`：143 files / 670 tests passed。新增公共首页不调用 fetch/bootstrap、
  预览与事实说明同步、进入／返回工作台和直接访问工作台的集成测试。
- `npm run typecheck`、`npm run lint`、生产 build 通过。
- 完整并发测试首次发现 lazy 工作区转换超过测试默认 1 秒等待；保留真实模块加载，
  将集成测试等待放宽至 10 秒后，完整套件通过。不是关闭或替换真实工作区模块。
- 实际浏览器检查：浅色／深色页面、390 px 窄屏、鼠标／Enter 切换预览、帮助入口、
  首页→工作台→标识返回首页，以及 `/workspace` 刷新。窄屏 DOM clientWidth 与
  scrollWidth 均为 375 px（390 px viewport 含滚动条），图片加载成功。
- 浏览器工作台读取现有本地服务；本轮没有创建 Agent、Run 或 Experiment，也没有
  调用模型或操作设备。预览域名的主题设置已恢复浅色，viewport override 已重置。
- 页面截图保存在 `docs/assets/studio-product-home-20260928/`。

构建命令（在 `studio/` 下）：

```bash
npm run typecheck
npm run lint
npm test
npm run build -- --outDir /tmp/zhixing-product-home-dist
```

## 手动复验

已运行开发服务时直接刷新根地址。否则在项目根目录使用既有启动器：

```bash
conda activate unimobile
python run_studio.py
```

1. 打开启动器显示的前端根地址：应看到品牌导航、大标题与产品展示，没有运行准备告警。
2. 切换三项展示：图片、介绍、说明和大图链接同步变化；用 Tab / Enter 也可操作。
3. 点击“使用流程”定位到四步说明；点击文档进入既有本地帮助页面。
4. 点击“进入工作台”：地址为 `/workspace`，应看到原先的任务与最近记录；刷新仍可打开。
5. 点击工作区左上标识返回首页；在设置切换主题后首页随之适配。

## 取舍与限制

选择独立产品路由和原工作台复用，避免把展示文案与运行准备逻辑放在同一首屏。
静态截图保证无需设备也能介绍产品，代价是不能代表实时状态，未来 UI 更新后需手动更新。
进入工作台仍依赖正常后端与已有运行配置。既有工作区应用 chunk 约 734 kB（压缩前），
构建仍提示超过 700 kB；本轮只是延后该模块加载，未完成全工作区 bundle 优化。
没有新增 SSR、独立公网发布、演示视频或搜索引擎收录验证。新增前端证据不扩大既有
Android / 模型 / Benchmark 能力结论。
