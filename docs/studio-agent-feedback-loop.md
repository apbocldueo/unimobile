# Studio Agent 显式反馈闭环

本文记录 `fix-studio-agent-run-feedback-loop` 实现后的普通 Studio Mobile Agent 运行边界。
目标不是在 Runtime 外层补一个不可见循环，而是让 Builder、AgentGraph、Android services、
Live journal 与 Replay 共同表达同一条可审计因果链。

## 已实现执行流

标准 schema-3 能力模板由服务端唯一提供。用户画布只表达：

```text
Input → Memory → Perception → Reasoning → ActionExecutor → Output
          ▲                              │
          └──── bounded interaction ─────┘
```

具体实现、版本、fallback、config 和 dependency 在 Inspector 编辑；LLM 不作为画布节点。
Output 连接只表示“此能力可以结束 Agent”，不承诺输出 payload，连线不显示标签。

后端把该能力图确定性 lowering 为普通 AgentGraph：`DeviceObserve` 是截图和 UI XML 的
唯一来源，runtime `ActionExecutor` 是物理设备副作用的唯一边界；ActionRequest、terminal
predicate、iteration router 与有界 feedback 都是 generated runtime glue，不出现在 Builder
画布。非终止成功动作通过最多 10 次的 feedback 再次观察；terminal action 不额外触发一次
隐藏观察。终态结果只在页面状态、Inspector、Timeline、证据、报告和导出显示，不得出现在
任何图节点、端口、handle、边、badge 或 accessibility name。

Android facade 只注入两个 runtime service 并把调用方输入交给 Kernel。它不检查端口名称
来自动截图，也不在图外创建 interaction。因而截图数量和顺序可以由 DeviceObserve
activation 逐一解释。

## Studio readiness 与旧 revision 边界

通用 AgentGraph compile validity 与 ordinary Studio Android Run eligibility 是两个事实。
Run/Benchmark 共享的 exact-revision eligibility 会无副作用检查：

- schema-3 authoring policy、lowering profile 与 capability hash；
- 当前 Catalog placement/dependency closure；
- 重新 lowering 后的 AgentGraph canonical hash；
- 每个 generated node/edge/path 的 projection ownership；
- 可达的正式 DeviceObserve/runtime ActionExecutor、结构化 terminal predicate 和有界 feedback。

缺少上述结构时，服务返回稳定 topology diagnostic 和可用的 node locator；Builder/Task Run
Bar 引导使用新版模板或手工修复。阻断发生在 Run、journal、artifact、模型调用、截图、
UI dump 和 ADB action 之前，不改变 revision status、canonical hash 或 current pointer。

这是一个有意的 Studio 产品边界：旧 schema-1/2 Studio revision 仍可读取、导出和回放历史
事实，但不自动迁移，也不能再启动新 ordinary Run 或 Benchmark Experiment。用户必须从当前
capability template 明确重建。Python SDK、AgentConfig YAML、
`ModularAgent`、`AgentRunner` 和 `BenchmarkTask` JSON 是独立公共入口，继续保留。

## 启动与手动复验

从仓库根目录运行，路径必须指向真实存在的 regular file：

```bash
conda run -n unimobile --no-capture-output \
  python -m zhixing.studio serve \
  --host 127.0.0.1 \
  --port 8765 \
  --secrets ./secrets.yaml \
  --device-profile-config ./studio/device-profiles.json
```

如果 profile 文件放在仓库根目录，则把最后一个参数改为
`./device-profiles.json`。路径以命令当前目录为基准，不以 Python 模块目录为基准。

手动流程：

1. 从标准能力模板新建 Agent，在 Inspector 配置 implementation 与 LLM dependency/SecretRef，
   Validate 后保存 revision。
2. 在底部 Task Run Bar 输入任务并选择服务端列出的 Device Profile。
3. readiness 应分别显示 graph/history/policy/environment facts；任何 blocked 状态都不应
   产生 History Run。
4. 启动后，第一次 DeviceObserve complete 应让中央手机出现首帧；TAP 完成后旧帧明确为
   stale，下一次 DeviceObserve complete 替换为当前帧。
5. terminal 后进入同一 Run identity 的 native Replay；Live 与 Replay 的 observation、
   action、interaction 和 artifact 顺序应一致，生成节点通过 projection map 聚合到能力图，
   图上不出现终态结果词。

自动化复验：

```bash
conda run -n unimobile --no-capture-output python -m pytest -q \
  tests/studio/test_documents_catalog_compiler.py \
  tests/studio/test_runtime_readiness.py \
  tests/runtime/test_android_graph_runtime.py \
  tests/studio/test_run_execution.py \
  tests/studio/test_run_replay_http.py

cd studio
npm run typecheck
npm run lint
npm test -- --run
npm run build
```

## 预期证据与失败边界

确定性 fake-device acceptance 使用“两次观察，中间一次 TAP，第二次决策结束”的序列：
应得到两个 observation、两个 typed ActionResult、一次确认的物理副作用、terminal success，
并在 HTTP event query、SSE 重连和 native Replay 中保持同一因果顺序。

当前 capability-authoring 合并验证结果为 backend aggregate `254 passed`、Studio
HTTP/SSE/native Replay `11 passed`、schema-3 clean-wheel `1 passed`；前端完整 Vitest
`113 files / 478 tests`，typecheck、lint 和隔离 production build 通过。完整命令与
fake/real-device 声明边界见
[Studio Mobile Agent 能力组件创作](studio-agent-capability-authoring.md)。

terminal failure action 不执行物理动作；模型失败、第二个动作设备失败、feedback 耗尽或 step limit 会
保留边界前已经提交的截图、ActionResult、activation 和 artifact。Virtual Phone 首次观察
前失败时显示“未采集设备证据”；artifact 缺失/损坏时不会沿用上一张并冒充当前画面。

## 已知限制

- 本变更的完整闭环证据来自 deterministic fake device，不是新的真实 Android 证明；
- 本轮没有用户显式提供并授权一个可用 Android profile/device，因此 real-device smoke
  保持 **unverified**；
- readiness 只证明静态依赖和拓扑可启动，不证明模型账户、网络、设备在线或任务成功；
- 旧 schema-1/2 Studio revision 不自动重写，用户必须从当前 capability template 明确重建；
- 当前仍无 pause/checkpoint/resume、自动失败诊断或广泛设备兼容性声明。
