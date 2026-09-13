# ZhiXing Benchmark 长期架构原则

本文保存 Benchmark 主线的稳定产品目标和架构边界。具体里程碑、验收步骤与实现
任务属于 `docs/roadmap.md` 和 OpenSpec Change，不写入本文。

## 定位

Benchmark 是与 AgentGraph 并列的一等产品能力，而不是 Agent 执行结束后的附属
评分器。ZhiXing 的目标是让用户在同一工具中：

1. 直接使用已有 Mobile Agent Benchmark；
2. 在统一、可审计的协议下公平比较不同 Agent；
3. 以声明式任务为主开发新 Benchmark，避免重写运行框架；
4. 为不同任务组合确定性、视觉、文本和轨迹等评估方法。

目标架构包含三个独立对象：

```text
Agent YAML / SDK       Benchmark JSON / Package       Experiment settings
        |                         |                            |
        v                         v                            v
    AgentGraph               BenchmarkPlan             ExperimentProtocol
        \_________________________|___________________________/
                                  |
                                  v
                         Experiment Runtime
                                  |
                                  v
                 RunResult + Evaluation + Report
```

## 稳定边界

- `AgentGraph` 定义 Agent 如何感知、推理和行动。
- `BenchmarkPlan` 定义任务、资源、初始化、ground truth、评估与清理。
- `ExperimentProtocol` 定义设备与应用要求、seed、重复次数、顺序、预算和失败策略。
- 三者必须保持独立身份；Benchmark 内容不得改变 AgentGraph canonical hash。
- 同一 AgentGraph 应可运行普通任务和不同 BenchmarkPlan；同一 BenchmarkPlan
  应可比较不同 AgentGraph。
- Benchmark Runtime 可以编排 Graph Runtime，但不得在 Kernel 中加入
  Benchmark、数据集或 Agent 范式特判。
- AgentGraph 中的 `Verifier` 控制 Agent 是否继续、反馈或结束；Benchmark
  `Evaluator` 作为外部考官判定任务结果。两者不得混为一体。
- 现有 Benchmark JSON、插件和旧 Pipeline 在新路径通过行为等价验证前必须保留。

## 目标文件架构

下列目录是 Benchmark 后端的长期目标，不代表所有目录当前均已建立。新增能力应
向该结构收敛；迁移现有模块时必须保持公共导入、配置合同、canonical identity
和已验证运行行为兼容。

```text
unimobile/
├── zhixing/
│   ├── benchmark/                    # 新版 Benchmark 框架核心
│   │   ├── __init__.py               # 稳定公共 API
│   │   ├── contracts/                # 无副作用的数据契约
│   │   │   ├── package.py            # Package manifest 与资源声明
│   │   │   ├── task.py               # BenchmarkTask / BenchmarkSuite
│   │   │   ├── plan.py               # BenchmarkPlan / TaskInstance
│   │   │   ├── experiment.py         # ExperimentProtocol
│   │   │   └── result.py             # Task/Suite/Experiment 结果 DTO
│   │   ├── compiler/                 # JSON/Package → BenchmarkPlan
│   │   │   ├── loader.py
│   │   │   ├── validator.py
│   │   │   ├── compiler.py
│   │   │   └── identity.py           # canonical identity
│   │   ├── catalog/                  # Benchmark 发现和选择
│   │   │   ├── catalog.py
│   │   │   ├── discovery.py
│   │   │   └── resolver.py
│   │   ├── runtime/                  # Benchmark 生命周期编排
│   │   │   ├── context.py
│   │   │   ├── lifecycle.py
│   │   │   ├── materializer.py
│   │   │   ├── executor.py
│   │   │   ├── resources.py
│   │   │   └── suite.py
│   │   ├── evaluation/               # 单任务 Evaluation Tree
│   │   │   ├── tree.py
│   │   │   ├── evidence.py
│   │   │   └── aggregation.py
│   │   ├── reporting/                # 跨任务/实验报告和轨迹
│   │   │   ├── report.py
│   │   │   ├── metrics.py
│   │   │   ├── trajectory.py
│   │   │   ├── safety.py
│   │   │   └── writer.py
│   │   ├── authoring/                # 脚手架与无设备开发检查
│   │   │   ├── templates.py
│   │   │   ├── scaffold.py
│   │   │   ├── dry_run.py
│   │   │   └── testing.py
│   │   ├── compatibility/            # 旧 Pipeline 兼容边界
│   │   │   └── legacy.py
│   │   └── cli.py                    # authoring/report/trajectory 子命令
│   └── plugins/benchmark/            # 内置、可复用原子插件
│       ├── task/                      # 动态任务参数生成
│       ├── environment/               # reset/injection/setting
│       └── evaluator/                 # system/visual/text/trajectory
├── benchmarks/                        # 可直接使用的 Benchmark Package
│   ├── android_world/
│   │   ├── benchmark.yaml
│   │   ├── tasks/
│   │   ├── assets/
│   │   ├── ground_truth/
│   │   ├── protocols/
│   │   └── README.md
│   └── appagent/
│       ├── benchmark.yaml
│       ├── tasks/
│       ├── assets/
│       ├── ground_truth/
│       ├── protocols/
│       └── README.md
├── data/                              # 旧来源与迁移基线，不是新版运行入口
├── examples/
│   ├── benchmark_v1/                  # 旧 JSON 路径兼容示例
│   └── benchmarks/                    # 新版教学示例
│       ├── minimal/
│       ├── dynamic-task/
│       └── composite-evaluation/
├── tests/benchmark/
│   ├── contracts/
│   ├── compiler/
│   ├── catalog/
│   ├── runtime/
│   ├── evaluation/
│   ├── reporting/
│   └── authoring/
├── docs/
│   ├── benchmark-architecture.md
│   ├── benchmark-authoring.md
│   └── benchmark-running.md
├── tools/benchmark_import/            # 外部数据到标准 Package 的迁移工具
└── temp/benchmark-runs/               # 运行产物，永远不是输入
```

各层职责必须保持单向清晰：

- `contracts` 只描述不可变语义和安全结果，不连接设备或实例化插件；
- `compiler` 只负责加载、验证、编译和 identity，不产生运行副作用；
- `catalog` 只发现、解析和选择 Package，不执行任务；
- `runtime` 消费 Plan、Protocol 和 ExecutableAgent，编排真实生命周期；
- `evaluation` 组合单个任务的 Evaluator Tree，不负责跨实验统计；
- `reporting` 从已发生的 Task/Suite Result 生成统计、比较和统一 Trajectory，
  不修改原始执行事实；
- `authoring` 生成小型 Package、编译定义、规划调度和运行显式 fake fixture；
  默认不得加载真实插件、连接设备或执行 Agent；
- `compatibility` 隔离旧 Pipeline adapter，不把旧概念重新引入 Runtime Kernel；
- `plugins/benchmark` 提供可组合的原子任务、环境和评估能力；
- `benchmarks` 保存正式 Package 内容，`examples` 保存教学样例，`data` 只保存
  原始来源和迁移基线；
- `temp/benchmark-runs` 只保存可删除的运行产物，不参与任何 canonical identity。

物理迁移遵守以下约束：

1. 先建立新模块和兼容 re-export，再迁移内部调用；不得静默破坏
   `zhixing.benchmark` 公共导入。
2. `contracts/task.py` 复用现有 `BenchmarkTask`/`BenchmarkSuite` 合同，不复制出
   第二套含义相近但行为不同的模型。
3. Benchmark `runtime/context.py` 只保存实验绑定并复用 Agent Graph
   `RuntimeContext`，不得定义竞争性的设备或执行上下文。
4. `evaluation/aggregation.py` 只处理 AND/OR/SEQUENCE 等任务内组合；pass rate、
   置信区间和多 Agent 配对比较属于 `reporting/metrics.py`。
5. `zhixing/cli.py` 可以保留顶层命令分派，但 Benchmark 子命令实现应逐步收敛到
   `zhixing/benchmark/cli.py`。
6. 旧 `zhixing/engine/benchmark/`、Benchmark JSON 和 Pipeline 在行为等价验证
   完成前不得删除；目录整理本身不能作为完成或兼容证明。
7. 不为目录外观创建无行为的空模块；每个目标目录应随对应能力和测试一起落地。

## 当前已验证状态

当前已经实现并测试：

- 现有 `BenchmarkSuite` JSON 与 `BenchmarkPackage` 均可无设备副作用地编译为
  `BenchmarkPlan`；
- Package、Plan、TaskInstance 与 ExperimentProtocol 拥有分离的 canonical
  identity；
- Package asset 与 ground truth 使用逻辑 URI、Package-relative 路径和内容摘要；
- `ExperimentProtocol` 固定 seed、repeats、顺序、预算、隔离与失败策略；
- 显式本地目录和已安装 distribution 可进入 metadata-only Catalog；
- `benchmark list/info/validate` 不连接设备、不执行插件和任务；
- AndroidWorld 81 个唯一任务与 AppAgent 45 个任务已迁移为首批 Package。
- `BenchmarkPlan + ExperimentProtocol + ExecutableAgent` 进入同一个
  `BenchmarkExperimentRuntime`，不调用旧 `AgentRunner`；
- TaskInstance 按派生 seed 确定性物化，并可在同一 repeat 的多个 Agent 间复用；
- initializer、reset/setup、Evaluator Tree、Graph Runtime 和 cleanup 复用同一
  显式设备会话，每个 Agent × TaskInstance 使用独立 RuntimeContext；
- 生命周期产生结构化阶段、事件、错误和 artifact 引用；Agent RunStatus 与
  Benchmark PASS/FAIL/INVALID/SKIPPED 分开表达；
- `zhixing benchmark run` 可以选择 Package、split、task、一个或多个具名
  graph-native Agent、Protocol、serial 与 artifact root；
- fake device 已覆盖多任务、多 Agent、repeats、公平复用、失败、预算和隔离策略；
- Evaluator 输出已升级为 V2，并支持保持旧语义的 AND/OR/SEQUENCE 以及显式
  THRESHOLD/WEIGHTED 组合；
- 每次实验可生成版本化 Task/Experiment Report、因果顺序 JSONL Trajectory、
  内容哈希和可校验 bundle；PASS/FAIL 与 INVALID/SKIPPED 使用不同统计分母；
- `benchmark init/dry-run/contract-test/report/trajectory` 已提供无设备 authoring
  和产物检查入口；
- 真实 Android 验收已在 `emulator-5554`、`en-US`、portrait orientation 上重新
  采集 V2 报告与统一 Trajectory：内置 SDK/YAML Agent 各完成一次
  AndroidWorld_6 PASS，二者 canonical hash 相同且每次 MediaStore 各新增一张照片；
- 合法提前结束的控制 Agent 已产生 Agent `RunStatus.SUCCESS`、Benchmark FAIL、
  INVALID=0 和 MediaStore 无新增的受控负例，证明 Agent 结束状态与外部任务判定
  保持分离；
- 两个 canonical hash 不同的 AgentGraph 已在同一 Plan/Protocol 下各运行两个
  repeats，报告为 2 PASS/2 FAIL、paired `matched_count=2`，成功 Agent 两次胜出，
  且 `significance_claimed=false`；
- 已安装的独立外部组件 distribution 已有节点 start/complete、共享 run identity、
  AndroidWorld_6 PASS 和 MediaStore 新增证据；设备动作仍经过内置
  ActionExecutor；
- 已安装的独立外部 Benchmark Package `example/photo-smoke@1.0.0` 已从 Catalog
  解析，以自己的 Plan identity 运行 PhotoSmoke_1，并生成 PASS、MediaStore 新增、
  V2 report、统一 trajectory 和通过完整性检查的 bundle。

这些证据不等于全部 AndroidWorld/AppAgent 任务已经复现，也不等于任意
AgentGraph、外部组件、外部 Package、Android 设备或 App 版本均已通过。验收使用
确定性脚本 Reasoning 来隔离 Runtime 行为，因此不构成通用 VLM 自主能力或算法
质量证据；两个 repeats 也只验证配对 plumbing 和描述性指标，不支持统计显著性
结论。Studio/frontend 未参与本轮验收。

## Benchmark 开发体验

Benchmark 应采用 declarative-first，而不是不真实的“任何任务都只需 JSON”承诺：

- 现有原子 initializer/evaluator 足够时，作者只需任务 JSON、资源和 ground truth；
- 复杂条件应优先通过 Evaluation Tree 组合已有原子 Evaluator；
- 只有出现新的初始化或评估语义时，作者才需要编写小型插件；
- 作者不应重写设备循环、Agent 调度、结果聚合或报告代码。

Benchmark Package 应能稳定描述身份、版本、任务、资源、依赖和评估协议，并允许
Catalog 完成发现、检查和选择。资源解析不得依赖当前工作目录。

## 公平性与评估

“经过同一个 Pipeline”不是充分的公平证据。可比较实验必须记录并约束至少：

- AgentGraph、BenchmarkPlan 和 ExperimentProtocol 身份；
- 设备、系统、应用和相关插件版本；
- 初始化与清理结果、seed、顺序、重复次数和执行预算；
- 模型配置与使用量的安全摘要；
- 每个生命周期阶段的状态、错误和 artifact 引用。

Evaluation Tree 应保留叶子 Evaluator 的结构化结果和证据，而不只输出最终布尔值。
组合逻辑可以演进，但不得自动猜测 evaluator 或 ground truth。确定性检查应优先于
模型判断；使用 VLM/LLM 评估时必须记录其配置、成本和限制。

## 完成判据

当前 Build–Run–Evaluate 基础闭环的完成判据为：

- Benchmark 定义可以无设备副作用地校验和编译；
- initializer、环境准备、AgentGraph、Evaluator 与 cleanup 按统一生命周期运行；
- 新路径执行 `ExecutableAgent`/Graph Runtime，而不是暗中回退到旧 AgentRunner；
- 多个 Agent 可以在相同 BenchmarkPlan 和 ExperimentProtocol 下比较；
- 每个任务产生结构化结果，失败阶段可区分且已有证据不会丢失；
- suite 结果、任务 artifact 与环境 provenance 可安全导出。

更广泛的产品验证仍要求更多真实任务成功/失败样本、外部 Benchmark Package、
不同设备/App 版本和足够样本量的多 Agent 实验。

Trajectory 用于审计和人工定位失败阶段。除非未来存在独立且经过验证的能力，
不得宣传自动失败诊断。

## Studio 集成

Benchmark Studio 不是新的 Benchmark Runtime，也不是普通 Agent Run 的可选评分字段。
Stage 5 的产品目标、实施顺序和当前后端/前端边界见
[Studio Stage 5 Benchmark Experiment 路线](studio-benchmark-experiment-roadmap.md)；
资源、DTO、状态机、事件、持久化、Replay、安全和分层验收要求见
[Studio Benchmark Experiment 合同](studio-benchmark-experiment-contracts.md)。

Stage 5.1 的 Catalog/Composer 之后，durable Experiment、single Worker、events/SSE、
startup recovery、managed publication/Replay、Monitor、Report/History/Evidence/Export、
authoring/freeze/release/migration 和 explicit device authority 已按独立 change 落地。
definition preview、validation、Contract Test、freeze 或 publication 本身仍不表示
Benchmark 已从 Studio 执行。

截至 2026-08-02，Stage 5.6B 已用 production fake Studio composition 和 14 场景的
bounded proof ledger 连接 durable service、Core Runtime、publication、Replay、actual-
backend browser 与 installed external Package。Core `2 Agents × 2 Tasks × 2 repeats`
的运行能力和 Studio Worker `1 Agent × 1 Task × 1 repeat` 的 fail-closed 产品限制被
分别验证；所有执行均为 `contract_fixture/fake_device`，六个 ADB/real-device/network/
model/secret/source-fallback canary 为 0，`realDeviceEvidence=false`。这不替代新的真实
Android 证据；下一步仍需
`validate-studio-benchmark-android-service-5-6c1`。完整命令与限制见
[Studio Benchmark 分层无设备验收](studio-benchmark-layered-acceptance.md)。
