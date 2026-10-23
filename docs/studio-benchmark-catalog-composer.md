# Studio Benchmark Catalog 与 Experiment Composer（Stage 5.1）

## 状态与目的

状态：**Stage 5.1 已实现；仅定义与预览，不执行 Experiment**
适用 Change：`implement-studio-benchmark-catalog-composer-5-1`
最后核对：2026-07-27

本阶段把现有 Benchmark definition/compiler/schedule 能力接入 Studio，让 Mobile
Agent 研究人员可以完成：

```text
Catalog → Package detail → split/task → immutable Agent revision
        → ExperimentProtocol → validate → deterministic preview
```

结果是一个可解释、可重复计算的 preview fingerprint 和计划 schedule。它不是
Experiment，也没有 Experiment ID、TaskRun、设备连接、运行事件或报告。

## 已实现边界

后端新增一个 definition-only Studio application boundary：

```text
named Package/Catalog/installed sources
                    │
                    ▼
      immutable Catalog snapshot
                    │
      ┌─────────────┼─────────────┐
      ▼             ▼             ▼
 list/detail      validate       preview
                                    │
                ┌───────────────────┼──────────────────┐
                ▼                   ▼                  ▼
       formal compiler    immutable revision    safe profile ID
                │                   │                  │
                └────────── build_schedule() ──────────┘
                                    │
                                    ▼
                    fingerprint + planned entries
```

实现的 HTTP 路由：

```text
GET  /studio/benchmarks
GET  /studio/benchmarks/{catalogEntryId}
GET  /studio/benchmarks/{catalogEntryId}/tasks
POST /studio/benchmarks/{catalogEntryId}/validate
GET  /studio/device-profiles
POST /studio/benchmark-experiments/preview
```

React 路由：

```text
/benchmarks
/benchmarks/:benchmarkId
/experiments/new
```

旧 `/benchmark` 只做兼容重定向。Stage 2–4 的 Replay Benchmark result projection
仍由原 `entities/benchmark` 负责；Stage 5.1 的 Catalog 和 preview 使用新的
`entities/benchmark-catalog` 与 `entities/experiment-preview`，不复用旧
`pipeline: unknown[]` 草稿作为领域事实。

## Catalog 来源与稳定身份

默认只在 `<workspace>/benchmarks` 存在时注册 `workspace-benchmarks`，并允许
installed distribution metadata discovery。不会隐式扫描 `data/`、workspace 任意
目录或浏览器提交的宿主路径。

显式来源可以通过 CLI 重复配置：

```bash
python -m zhixing.studio serve \
  --benchmark-package /trusted/package \
  --benchmark-catalog-root /trusted/catalog
```

也可以使用 `os.pathsep` 分隔的环境变量：

```text
ZHIXING_STUDIO_BENCHMARK_PACKAGES
ZHIXING_STUDIO_BENCHMARK_CATALOG_ROOTS
```

`--no-installed-benchmarks` 关闭 installed metadata discovery。路径只存在于后端
composition，浏览器只看到安全 `sourceKind` 和 opaque `catalogEntryId`。

Catalog 在服务启动时冻结 snapshot，普通 list/detail/tasks 请求不重新扫描目录。
新增或修改 Package 后需要重启 Studio 才会刷新。`catalogEntryId` 绑定命名来源、
source-relative package key 和 Package identity；内容漂移由 Package/Plan identity
和 preview fingerprint 检测。同一 Package identity 的等价或分歧来源均保留为独立
entry，并返回显式 diagnostic。

## Preview 合同

第一版明确限制：

```text
maxAgents = 1
maxSelectedTasks = 1
maxRepeats = 1
multiAgentComparison = false
```

请求仍使用 `agentRevisions[]` 和正式 `ExperimentProtocol`。超过限制会整体拒绝，
不会静默截断。Preview 会：

1. 严格解析 camelCase DTO，拒绝未知字段；
2. 按 `catalogEntryId` 解析具体来源并编译 selected split；
3. 检查 exact task；
4. 读取保存的 immutable Agent revision，重建 AgentGraph 并复核 canonical hash；
5. 检查安全 device profile ID 是否已配置，但不调用 runtime `resolve()`；
6. 复用正式 `build_schedule()` 计算顺序与 derived seed；
7. 对 source、Package/Plan、revision/graph、task、Protocol、profile 和 capability
   contract 计算 preview fingerprint。

静态任务只返回 `template_only`；动态任务返回 `pending_materialization`，不会执行
generator。Preview 不写 Agent、Run、Replay 或 Experiment 表，不调用 scheduler、
event publisher、模型、插件 runtime、ADB、device manager 或 lease。

## 前端状态所有权

- TanStack Query 保存 Catalog、detail、tasks、Agent、profile 等服务端事实；
- `features/experiment-composer` 的 Zustand store 只保存未提交表单；
- preview mutation 的响应不写 localStorage；
- 每次语义字段变化都会增加 form version，使旧 validation/preview 立即变为 stale；
- stale 或失败的 preview 不显示为“可以执行”；
- light/dark 继续由全局 theme token 控制。

前端目录遵循 FSD-lite：

```text
entities/benchmark-catalog/
entities/experiment-preview/
features/experiment-composer/
pages/benchmarks/
pages/benchmark-detail/
pages/experiment-create/
```

## 手工验证

准备至少一个 `<workspace>/benchmarks/<package>/benchmark.yaml` 和一个已保存且
compile status 为 valid 的 Agent revision，然后：

```bash
uv run --extra dev python -m zhixing.studio serve \
  --workspace . \
  --no-installed-benchmarks

cd studio
npm run dev
```

浏览器访问 `http://127.0.0.1:5173/benchmarks`，预期：

1. Catalog 只显示配置来源；
2. detail 可选择 split/task，并能显式 validate；
3. Composer 可选择 Agent current revision 和安全 device profile；
4. preview 显示 fingerprint、canonical identities、Protocol、schedule 与 derived seed；
5. 修改 seed/budget/task 后旧 preview 显示“已过期”；
6. SQLite 中不会新增 Experiment、Run 或 Replay，设备不会收到请求。

自动化复核：

```bash
PYTHONPATH=tests UV_CACHE_DIR=/tmp/zhixing-uv-cache \
  uv run --extra dev python -m pytest -q

cd studio
npm run lint
node node_modules/typescript/bin/tsc -b
npm test -- --run
node node_modules/vite/bin/vite.js build
```

## 已验证证据与限制

2026-07-27 的针对性证据：

- side-effect-free Composer/Run boundary：`38 passed`；
- real loopback Benchmark HTTP：`3 passed`；
- 完整后端回归：`481 passed in 93.86s`；
- 前端：`22` 个 test files、`77 passed`；
- TypeScript、ESLint 和 Vite production build 通过；
- 实际 Studio backend + Vite 的 in-app browser smoke 覆盖 Catalog、detail、
  Composer deep link/刷新、validate、preview、空结果、非法 cursor 错误和 stale；
- 浏览器 smoke 暴露并修复了一个真实合同差异：HTTP 的 `exclude_none` 会省略未
  materialize 的 `identity/parameters`，strict parser 现在同时接受字段省略或
  `null`，并统一归一化为 `null`，仍拒绝任何非空 materialized 值；
- smoke 前后 SQLite 均为 `1 Agent / 1 revision / 0 Run / 0 event / 0 Replay`；
  页面也没有 Experiment ID、TaskRun ID 或运行入口；
- 生产构建仍有大于 500 kB 的 chunk 警告，本 Change 没有引入 route-level
  code splitting。

本阶段没有：

- 创建、保存、调度、取消或恢复 Experiment；
- materialize 动态任务；
- 连接 Android/HarmonyOS 或验证真实 profile 在线；
- 执行 initializer、Agent、模型、evaluator 或 cleanup；
- Experiment event/SSE、TaskRun、Replay promotion、report、trajectory 或 bundle；
- 多 Agent、多 task 或 repeats 大于一；
- PostgreSQL adapter；
- 新的真实 Android 证据。

因此，Stage 5.1 只能声明“定义选择、校验和确定性预览已产品化”，不能声明
Benchmark 已从 Studio 执行或产生新的通过率。
