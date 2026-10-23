# ZhiXing Studio（前端）

与仓库根目录下的 `zhixing/` **平行** 的 Vite + React + TypeScript 工作台，用于 **兵工厂（Agent 构建）** 与 **试车场（Benchmark）** 等 1.0 能力。

## 目录结构（摘要）

```text
studio/
├── src/
│   ├── app/                 # 壳与路由
│   ├── features/            # 按业务竖切：agent-builder、benchmark-suite…
│   ├── stores/              # agentBuilderStore / benchmarkStore 隔离
│   ├── domain/              # 模板、序列化、类型（不含 UI）
│   ├── api/                 # 后端契约（占位）
│   ├── components/ui/       # 通用 UI 片段
│   └── lib/                 # 工具函数
├── package.json
└── vite.config.ts
```

## 本地运行

推荐在项目根目录、已安装 Python 依赖的环境中执行 `python run_studio.py`，
一次启动前后端并自动加载现有本地配置；按 Ctrl+C 一起关闭。
首次仍需运行下方的 `npm ci`。详细说明见 [本地启动](../docs/studio-local-startup.md)。
下面保留仅启动前端的开发方式，它需要另行启动后端。

需要本机已安装 **Node.js 22.12+**。Vite 7 和 Vitest 5 的工具链不再支持旧的
Node.js 版本。

```bash
cd studio
npm ci
npm audit --audit-level=moderate
npm run dev
```

浏览器打开终端里提示的地址（一般为 `http://127.0.0.1:5173`）。

- 侧边栏可切换「兵工厂 / 试车场 / 运行历史 / 全局设置」。
- 兵工厂画布为 **Modular 只读链** 占位；点击槽位上 **「+ 挂载插件」** 打开右侧抽屉（插件橱窗 → 选卡片进入配置占位），画布槽位状态会随 Store 更新。

## 环境变量

复制 `.env.example` 为 `.env`，后续填写 `VITE_API_BASE_URL` 等。

## 构建

```bash
npm run build
npm run preview
```

依赖升级后，提交前应重新运行 `npm ci`、`npm audit --audit-level=moderate`、
`npm test`、`npm run typecheck`、`npm run lint` 和 `npm run build`。
