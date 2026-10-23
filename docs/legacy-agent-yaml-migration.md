# 九个旧 Agent 配置的简洁 YAML 迁移

用户要求按“完成一个、检测一个、再处理下一个”的顺序迁移九项，保留旧配置。
Coding Agent 完成源码核对、逐项构图和差分测试；这里记录本地旧实现的迁移证据，
不新增上游复现、真实模型或设备验收结论。

## 配置对应和顺序

| 顺序 | 本地 Agent | 保留的原文件（examples/） | 新文件（examples/graphs/） | 当前差分场景 |
|---|---|---|---|---:|
| 1 | AppAgent | agent_appagent.yaml | appagent.yaml | 8 |
| 2 | GUICourse | agent_guicourse.yaml | guicourse.yaml | 6 |
| 3 | ShowUI | agent_showui.yaml | showui.yaml | 6 |
| 4 | OS-Genesis | agent_os_genesis.yaml | os_genesis.yaml | 6 |
| 5 | GUI Schema CN | agent_gui_schema_cn.yaml | gui_schema_cn.yaml | 6 |
| 6 | Mobile-Agent | agent_mobileagent.yaml | mobile_agent.yaml | 11 |
| 7 | Mobile-Agent-v2 | agent_mobile_agent_v2.yaml | mobile_agent_v2_migrated.yaml | 11 |
| 8 | MobileUse | agent_mobile_use_multi.yaml | mobile_use.yaml | 7 |
| 9 | UGround | agent_uground.yaml | uground.yaml | 11 |

GUI Schema CN 的 AgentCPM 风格归属仍是提示词/动作 Schema 的来源推断；没有改名
宣称原模型复现。AndroidLab 的原配置尚未确认，不在这九项中。

本地 Mobile-Agent 与 v2 原文件逐字节相同，新图因此语义相同。这不是两种上游
算法差异的证明。原有 `examples/graphs/mobile_agent_v2.yaml` 是通用拍照模板，
本次没有覆盖它；v2 迁移文件使用明确的 `_migrated` 后缀避免冲突。

## 执行关系和取舍

旧入口通过 `agent_type` 选择 Python controller，调用 `reset()/step()`。
新入口为 `kind: agent_graph` 的命名节点简洁 YAML，显式包含：

```text
初始化 → （初始规划/可选设备设置）→ 有界操作循环
  → dispatch → 观察 / 验证 / 感知选择 / 单次感知 / 记忆查询
             / Manager / 推理 / 摘要 / 定位 / 提交 / 执行
  → 路由 → 单支合并 → State 写回 → 下一次操作或终止
```

每个阶段由图路由调度，不把旧 Agent 包装为单节点。共享实现是
`zhixing/plugins/agent/workflow_compat.py`：它重用现有感知、推理、规划、验证、
SlidingWindowMemory 和 UGroundGrounder，仅补单次调用与数据状态之间的适配。
操作类有限制名单，普通 Memory 操作不能选择设备设置操作。

`WorkflowFrame` 只携带任务、计划、原始记忆片段、观察、感知、动作和确认结果；
不保存模型、设备或组件实例。每次调用重建 SlidingWindowMemory 的数据视图，
保持 system/history 分区、原窗口大小、include_raw/include_thought 和原提示组装。
这些选定配置都未声明 knowledge_source，因此真实知识源或经验命中不在本轮证据内。

截图/XML 使用共享 DeviceObserve，动作使用共享 ActionExecutor。UGround 重置的
固定指针显示设置有独立 `workflow_setup` 节点和 device_action 合同，经过现有
Device adapter；编译和构造不执行该设置。重置失败继续执行，与旧 reset 一致。
UGround 原示例 Grounder 的 key 字面值改为 `UGROUND_API_KEY` SecretRef；旧文件
保留，模型名称、参数和本地服务地址继续显式声明。

保留了以下细节：

- AppAgent 的验证降级/成功恢复、解析器切换提示、纠正动作短路，以及感知异常时
  重新经过验证的旧路径；
- Reflection 的反馈文本和来源、A/B/C/D/不明确回复，以及纠正时跳过感知和 Actor；
- MobileUse 的 reset 初始规划、每步 Manager、Critic 纠正短路、Manager 失败沿用
  上一次计划，以及 Operator 错误标签与笔记；
- UGround 的双图摘要、空摘要/摘要异常跳过、显式坐标跳过 Grounder、定位失败
  不提交新 last_action 而等待，以及输入文本后的 Enter 和双击。

显式状态和分支会使 YAML 长于旧版选类配置。这里的“简洁”指现有命名节点/短边
作者格式，不承诺比旧 YAML 更短。离线导出器是
`scripts/export_legacy_workflow_yaml.py`，运行时只读取导出的独立 YAML。
它只接受本轮评审过的策略及 SlidingWindowMemory 布局，不是任意旧配置迁移器。

## 差分检查与复现

`tests/runtime/test_legacy_yaml_migration.py` 运行真实旧 controller 的 reset/step，
用原 YAML 指定的真实组件；新侧通过正常 SDK 执行完整 YAML。只替换外部模型和
设备，对异常场景另注入明确的边界失败。两侧比较提示原文、图像文件字节摘要、
动作及其元数据、设备调用、感知顺序、system/history 记忆、感知索引；UGround
另检查摘要 pending 与上次 raw response。

目前为 72 个有限差分场景，另有显式结构、角色/类型限制、两次运行隔离、native
交互预算四项检查。实际阶段门禁保存在
`gates.json` (not bundled in the core source)；
后补的目录文本和记忆窗口场景在全部逐项门禁后作为统一加固执行。

在仓库根目录执行：

```bash
conda run -n unimobile python -m zhixing.cli agent validate examples/graphs/appagent.yaml
conda run -n unimobile python -m pytest tests/runtime/test_legacy_yaml_migration.py -q
conda run -n unimobile python -m pytest tests/packaging/test_legacy_yaml_migration_install.py -q
```

预期第一条返回 valid 和 canonical hash；第二条 76 项通过；第三条离线安装到
新 venv，在仓库外仅使用复制的九张图执行 TAP → DONE。安装探针阻断网络连接和
进程启动，并检查编译不导入组件、模型或设备；这不是第三方代码沙箱证明。
测试无需真实密钥、ADB 或模型权重。逐文件 SHA 与最终回归记录见
`manifest.json` (not bundled in the core source) 和
`results.json` (not bundled in the core source)。

最终相关回归 563 项通过；新构建 wheel 的九图验收和其余资源检查 8 项通过、
1 项明确排除。排除项 `test_all_builtin_prompts_are_packaged_and_readable` 已实际
执行并失败：测试写死 16 份，工作区实际为 27 份。本轮未新增或修改提示词，也未
改动这个现有断言；不能把这项结果描述为全部资源测试通过。

## 不能推广的结论

对照目标是当前本地实现的 reset/step 和选定配置，不是上游固定提交，亦未覆盖
完整 AgentRunner 的 reset/cleanup、外部插件、自定义 Memory 或所有异常输入。
有限脚本模型对照不等于任意模型输出的数学等价、真实 Android 成功或 Benchmark PASS。

新版使用 native Runtime 的物理交互预算、取消、错误归一化和独立激活预算。
YAML 的操作循环最多 500 次；这是操作次数，不是 500 次手机动作。旧 Modular
在持续主感知异常和“验证成功恢复主感知”的组合下可能递归不收敛；本轮探针曾
触及该旧问题，新版受有界循环保护。这是公开的边界差异，不能称所有失败行为完全等价。
初始规划/验证中向外抛出的异常也由 native SDK 归一化为失败结果，不能拿该状态
枚举当成旧 Runner 状态的逐项等价。原 Python controller/旧 YAML 均未改变。

本轮未更新论文 LOC 或旧成功率。若重新统计已有组件上的组装成本，应统计新 YAML
与额外装配；本次新增适配实现的规模/准备投入另列，不由此推断开发时间减少。

## AppAgent 后续简化（2026-10-21）

用户随后要求先审查 AppAgent 的重复胶水。已将通用调度结构收回编译器，保留
YAML 中的阶段和分支；AppAgent 从 256 行降到 80 行，展开后的 canonical hash
完全不变，其他八项配置不变。新增 20 项通用编译/执行/诊断检查，相关回归为
583 项通过；安装与其余资源检查为 8 项通过、1 项保留排除。

上面的旧 manifest 和 LOC 快照属于第一轮迁移；当前 AppAgent 文件的字节 hash
以 [后续简化记录](appagent-yaml-simplification.md) 及其新证据目录为准。共享运行
适配 304 SLOC 完全未改；本轮另增加通用编译代码，成本独立列出，不能说简化
没有实现成本。原离线导出器仍导出完整图，不自动改写其他八项。

## 剩余八项后续简化（2026-10-21）

用户随后授权八项依次简化。已按 GUICourse → ShowUI → OS-Genesis → GUI Schema
CN → Mobile-Agent → Mobile-Agent-v2 → MobileUse → UGround 的顺序逐项通过图身份、
可编辑性与各自旧实现差分门禁，再进入下一项。九项当前 YAML 共 698 有效行；
运行适配与编译器均未改，新增可选离线工具 120 SLOC 单独计量。
旧文件和每项展开快照全部保留。最终相关回归 594 项通过，安装及其余资源检查
8 项通过、1 项继续明确排除。最新清单、计量和命令见
[九项简化记录](legacy-agent-yaml-simplification.md)，不再用上轮展开版字节 hash
代表当前简洁 YAML。
