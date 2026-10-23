# Studio Mobile Agent 能力组件创作

Studio 新建和修改 Mobile Agent 时使用 `StudioCapabilityDocument` schema 3。它把用户看到的
“能力组件”与执行时必须存在的 AgentGraph 节点分开：用户编辑能力，后端确定性生成运行胶水。
通用 Python/YAML AgentGraph 仍可直接使用底层控制原语。

## 最终组件清单

| 类别 | 画布状态 | 语义 |
|---|---|---|
| Input | 保留、自动创建 | Agent 任务入口；没有实现，不计入能力数 |
| Output | 保留、自动创建 | 连接到它的能力可以结束 Agent；不承诺 payload |
| Perception | 保留 | 核心能力，可有多个实例 |
| Planner | 保留 | 核心能力，可有多个实例 |
| Reasoning | 保留 | 核心能力，可有多个实例 |
| Memory | 保留 | 核心能力，可有多个实例 |
| ActionExecutor | 保留 | 核心能力；Studio 只提供一个框架能力 |
| Verifier | 保留 | 核心能力，可有多个实例 |
| Grounder | 保留 | 批准的功能扩展 |
| Tool | 保留（无实现时禁用） | 仅 Catalog 有合规实现时可添加 |

具体 implementation、exact version、ordered fallback、config 和 dependency 在 Inspector
编辑。LLM 是 dependency，不是画布节点。

以下对象仍可存在于 lowered AgentGraph 或 Benchmark/runtime 合同，但不能由 Builder 直接
添加、复制、导入或连线：

- DeviceObserve、ActionRequest、runtime ActionExecutor；
- terminal Condition、iteration Router；
- raw Condition、Router、State、Loop、Subgraph；
- LLM/provider、Device、parser；
- Benchmark initializer、environment、evaluator；
- `legacy_action_executor` 和未知 external component 的通用卡片回退。

节点标题、端口、handle、边、badge、兼容 presentation 文本和 accessibility name 都不得显示
`DONE`、`FAIL` 或等价终态结果词。结果、错误、生成身份和终止原因仍在画布之外的状态、
Inspector、Timeline、证据、报告和导出中保留。Output 连线在画布上始终无标签。

## 编译与身份闭包

```text
schema-3 capability document
  │  policy = studio.capability-authoring@1
  │  profile = studio.mobile-agent-lowering@1
  ▼
Catalog placement / family / dependency validation
  ▼
deterministic lowering
  ├─ DeviceObserve service nodes
  ├─ ActionRequest + runtime ActionExecutor
  ├─ structured terminal predicate + executable Output
  └─ bounded feedback/control primitives
  ▼
ordinary AgentGraph 1.1 validator + canonicalizer
```

新 valid revision 原子保存 authoring policy、lowering profile、capability semantic hash、
AgentGraph canonical hash、source map 和每个生成 node/edge 的 projection map。presentation、
revision 时间和 runtime 状态不进入 capability hash。

Run/Benchmark 准入会重新解析 capability document、重算 capability hash、按当前 Catalog
重新 lowering，并核对 graph hash 与 projection map。校验不构造 component、不解析 secret、
不发现或连接设备、不获取 lease、不调用模型、不创建 Run/Experiment 或 artifact。

## Live、Replay 与历史

Live/Replay 保留精确 runtime event、activation、failure target、Virtual Phone 因果和证据，
但 Graph 通过持久化 projection map 聚合到能力节点。缺失映射时显示 truthful unavailable，
不根据事件名猜 Studio 能力。没有 Studio authoring/source-map 证据的 generic Replay 可继续
显示低层拓扑，但所有画布文本仍经过同一结果词过滤器。

- schema 1/2 revision 和已完成 Run/Experiment/Replay 不删除、不改 current pointer，继续
  可读和可导出。
- schema 1/2 或 closure 不完整的 revision 不允许创建新 Run/Experiment；用户须从当前
  capability template 明确重建。
- 不提供静默迁移或自动替换。旧 JSON 导入会给出重建提示。
- SQLite schema 12 只增加 nullable closure/projection 列；schema 11 行保持原值。
- 回滚应用代码不会删除新列或历史数据，但旧版本不能运行 schema-3 revision。

## 验证与声明边界

测试覆盖 strict schema/hash、Catalog placement、确定性 lowering、多个 Perception、SQLite
restart、旧 revision 零 Run/event 持久化、普通 Run/Benchmark policy gate、Live/Replay 投影、
generic Graph/YAML 回归和完整 Studio 前端。标准模板的 fake-device 测试仍证明显式观察、一次
物理 tap、再次观察和 terminal RunResult，且没有 Kernel 模板分支。

可复现命令：

```bash
/opt/miniconda3/envs/unimobile/bin/python -m pytest -q \
  tests/studio/test_capability_authoring.py \
  tests/studio/test_documents_catalog_compiler.py \
  tests/studio/test_repository_service.py \
  tests/studio/test_runtime_readiness.py \
  tests/studio/test_benchmark_composer.py \
  tests/studio/test_run_execution.py \
  tests/studio/test_run_replay_http.py \
  tests/studio/test_benchmark_execution_worker.py \
  tests/studio/test_benchmark_startup_recovery.py \
  tests/studio/test_benchmark_experiment_resource.py \
  tests/graph tests/catalog tests/components

/opt/miniconda3/envs/unimobile/bin/python -m pytest -q \
  tests/packaging/test_isolated_install.py::test_wheel_from_unrelated_cwd

cd studio
npm run typecheck
npm run lint
npm test -- --run --reporter=dot
npm exec vite build -- --outDir /private/tmp/zhixing-studio-capability-build --emptyOutDir
```

本次实际结果为 backend aggregate `256 passed`、clean-wheel `1 passed`、frontend
`113 files / 480 tests passed`，typecheck、ESLint、隔离 production build 与 strict OpenSpec
validation 均通过。实际后端浏览器旅程从正式模板创建 schema-3 Agent、进入 Builder、Validate、
重载并检查 Palette、Input/Output、Inspector、画布可见文本和所有 `aria-label`；没有发现
forbidden Palette 项或终态结果词。旅程还验证 schema-2 Agent 的只读兼容图、新 Run 禁用、
Benchmark Preview 策略拒绝，以及 Replay 只在图外保留正式结果。该旅程发现并修复了 template
API 内嵌 feedback policy 曾输出 snake_case 的 wire bug，现由 camel-case round-trip contract
覆盖。

策略校验和 Benchmark preview/create 的已知错误会在 Run/Experiment/event/artifact、component、
secret、profile、lease、model 和 device 边界之前失败。SQLite 12 是 additive migration；回滚时
可先停止新 schema-3 写入并运行旧应用读取历史，但不要删除新增 nullable 列，也不要把新
schema-3 revision 降级为旧执行资格。

本变更没有收到 exact Android profile/task 授权，因此没有执行新的真实 Android 验收，也不
扩大设备兼容性、模型质量或 arbitrary Agent paradigm 声明。

当前 schema 3 只声明并 lowering 有界 feedback；它尚未定义 route、state、loop 或 approved
composite 的公开能力语法。Generic AgentGraph 的这些原语仍完整可用，但是否把新声明合同加入
schema 3 需要单独的 OpenSpec 设计决定。因此任务 4.6 保持未完成，不能把当前 feedback-only
lowering 描述成上述全部语义已经支持。
