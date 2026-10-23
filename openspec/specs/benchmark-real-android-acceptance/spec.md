# Benchmark Real Android Acceptance Specification

## Purpose
Define reproducible evidence requirements for validating built-in and external AgentGraph and Benchmark definitions through the unified Benchmark Runtime on an explicitly selected real Android device.

## Requirements

### Requirement: 显式且可重复的真实 Android 验收
系统 SHALL 提供后端验收入口，以显式 Android serial、Benchmark Package、task ID、ExperimentProtocol、具名 ExecutableAgent 集合和 artifact root 为输入。入口 MUST 在任何设备动作前完成定义编译、组件绑定与设备 preflight，并 MUST NOT 依赖 Studio、隐式默认设备、旧 AgentRunner 或 Graph Kernel 中的任务特判。

#### Scenario: 设备与定义均有效
- **WHEN** 调用者选择在线 Android serial、有效 Package、Protocol 和可绑定 AgentGraph
- **THEN** 验收通过公共 Benchmark Experiment Runtime 执行 reset、setup、evaluator pre-hook、AgentGraph、evaluation 和 cleanup

#### Scenario: 设备不可用
- **WHEN** 显式 serial 不在线或不满足 Protocol 设备约束
- **THEN** 验收在 Agent 动作前失败或产生 INVALID preflight 结果，并保留安全诊断而不选择其他设备

### Requirement: 内置 YAML 与 SDK 定义等价及真实 PASS
系统 SHALL 使用内置组件分别从 YAML 和 Python SDK 构造同一 content-verified Android AgentGraph，并验证二者 canonical hash 相同。两种入口 MUST 均能进入真实 Benchmark Runtime；只有 Agent `RunStatus.SUCCESS`、Benchmark outcome `PASS`、任务 evaluator PASS 和独立 MediaStore 新增照片证据同时成立时，拍照验收才能声明成功。

#### Scenario: YAML 与 SDK canonical identity 相同
- **WHEN** YAML 和 SDK 表达相同节点、边、组件参数与 policies
- **THEN** 编译结果具有相同 canonical hash，且报告不得把二者描述为两个不同算法

#### Scenario: 内置拍照 Agent 成功
- **WHEN** content-verifier Agent 在真实 Android 上执行拍照任务并产生一条新的媒体记录
- **THEN** Agent 状态为 SUCCESS、Benchmark outcome 为 PASS、Evaluator Result V2 为 PASS，独立 MediaStore diff 至少包含一条新增记录

#### Scenario: Agent 声称成功但没有设备证据
- **WHEN** Agent 返回 SUCCESS 但 evaluator 或独立 MediaStore 证据未检测到新增照片
- **THEN** 验收失败且不得把 Agent 自述完成当作任务成功证明

### Requirement: 可解释的受控 Benchmark FAIL
验收 SHALL 包含一个使用公共 AgentGraph/Runtime 合同的受控失败 Agent。该 Agent SHALL 正常结束而不完成拍照任务，使 Graph `RunStatus.SUCCESS` 与 Benchmark `FAIL` 同时存在；失败 MUST NOT 通过破坏 initializer、设备连接、evaluator 或 cleanup 制造。

#### Scenario: 提前结束的 Agent
- **WHEN** 受控 Agent 在不创建照片的情况下执行合法 terminal action
- **THEN** Agent 阶段记录 SUCCESS、evaluation 阶段记录 FAIL、最终 Benchmark outcome 为 FAIL、INVALID 计数为零且 MediaStore 没有新增照片

#### Scenario: 人工定位失败阶段
- **WHEN** 读取受控 FAIL 的 run report 和统一 trajectory
- **THEN** 读者可以区分成功的 Agent 阶段与失败的 evaluation 阶段，并查看各自的安全证据

### Requirement: 真实多 Agent 配对比较
系统 SHALL 在同一个 BenchmarkPlan 和 ExperimentProtocol 下比较至少两个 canonical hash 不同的 AgentGraph。配对运行 MUST 复用同一 repeat 的 TaskInstance，记录相同 seed、预算、设备约束与 verified reset 策略，并执行至少两个 repeats。报告 MUST 按现有公平比较合同区分 matched、unpaired、INVALID 和 SKIPPED。

#### Scenario: 成功 Agent 对受控失败 Agent
- **WHEN** content-verified Agent 和提前结束 Agent 在两个 repeats 中运行同一复用 TaskInstance
- **THEN** experiment report 将比较标记为 paired、matched count 为二，并记录成功 Agent 的两次胜出

#### Scenario: YAML 与 SDK 等价表示
- **WHEN** 两个具名输入拥有相同 AgentGraph canonical hash
- **THEN** 验收把它们作为 authoring parity 证据，而不把它们计为两个独立算法的公平比较

#### Scenario: 样本量不足
- **WHEN** 真实比较只有验收所需的小样本 repeats
- **THEN** 报告仅提供描述性 paired metrics，且不声称统计显著性或普遍性能优势

### Requirement: 外部组件参与真实 Android AgentGraph
系统 SHALL 从已安装的独立 distribution 通过 `zhixing.components` Entry Point 发现外部组件，并将其组合进真实 Android AgentGraph。验收 MUST 证明外部节点实际执行、接收当前运行的 RuntimeContext 并产生 start/complete 事件；Android 设备副作用仍 MUST 通过显式 ObservationProvider/ActionExecutor 边界。

#### Scenario: 外部节点与拍照主链共同完成
- **WHEN** 已安装外部组件作为有消费方的审计或扩展分支参与 content-verified AgentGraph
- **THEN** 统一运行结果和 trajectory 包含该外部节点的 start/complete 事件、当前 run identity 和安全输出，同时拍照任务得到 PASS

#### Scenario: 外部 provider 未安装
- **WHEN** 当前 Python 环境不存在 AgentGraph 引用的 provider
- **THEN** 绑定在连接设备前失败并指出安全的 provider/component identity，不回退为内置组件

### Requirement: 外部 Benchmark Package 真实执行
仓库 SHALL 提供一个可独立构建和安装的最小 Benchmark Package 验收 fixture。该 distribution MUST 通过 `zhixing.benchmarks` Entry Point 暴露 package resource，且其 Package/Plan identity、Catalog、验证和运行语义 MUST 与显式本地目录来源一致，不得修改 ZhiXing 核心注册表。

#### Scenario: 已安装外部 Package 被发现
- **WHEN** 最小 Benchmark distribution 从 wheel 安装到验收环境
- **THEN** `benchmark list/info/validate` 通过 metadata-only Catalog 发现并验证它，且核心 wheel 不包含该 Package 内容

#### Scenario: 外部 Package 在真实 Android 运行
- **WHEN** 调用者使用外部 Package 的拍照任务、显式 serial 和 content-verified AgentGraph
- **THEN** 统一 Experiment Runtime 产生真实 PASS、设备证据、报告和 trajectory，而不使用外部 Package 专属执行分支

### Requirement: V2 报告、统一轨迹和安全产物验收
每个真实 PASS、受控 FAIL、比较和外部运行 SHALL 写入独立实验目录，并生成可加载的 task result、run report、trajectory、experiment result、experiment report、manifest 和 integrity-checked bundle。验收 MUST 使用公共读取/校验入口重新检查这些产物，并对 secret、原始 serial、非安全绝对路径和 live runtime 对象进行有界扫描。

#### Scenario: PASS 产物完整
- **WHEN** 真实 PASS suite 完成且 writer 成功
- **THEN** 所有规定产物存在、schema 可加载、bundle hash 校验成功且 artifact references 为安全相对路径

#### Scenario: FAIL 产物保留因果证据
- **WHEN** 受控 FAIL suite 完成
- **THEN** 报告和 trajectory 同时保留 Agent SUCCESS、evaluation FAIL、Evaluator Result V2 和独立设备证据，不把失败压缩为一个布尔值

#### Scenario: 敏感字段扫描
- **WHEN** 验收扫描全部 JSON、JSONL、manifest 和 bundle 成员
- **THEN** 产物不包含 API key、token、password、原始 Android serial、live component/device repr 或不允许的宿主绝对路径

### Requirement: 无真机回归与真实性边界
真实 Android 验收编排 SHALL 具有 fake-device 或 contract-level 回归，覆盖 PASS、受控 FAIL、外部节点事件、paired schedule 和 artifact 校验，而不要求普通自动化测试连接设备。只有实际真机命令成功产生对应证据时，文档才可记录真实 Android 支持事实。

#### Scenario: 自动化环境没有 Android
- **WHEN** 常规测试环境没有在线设备
- **THEN** fake/contract 测试仍验证验收逻辑，并明确跳过真实设备步骤而不伪造 PASS

#### Scenario: 真实设备实验完成
- **WHEN** 验收人员在显式设备上完成规定矩阵并保存报告
- **THEN** 项目文档只声明该设备、Package、任务、AgentGraph 和 repeats 范围内的验证结果，并保留其他任务、设备和 Agent 范式限制
