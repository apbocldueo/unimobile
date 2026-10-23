# 九个 Agent YAML 简化：逐项门禁与最终统计

用户要求剩余八项沿用 AppAgent 方案，逐个简化、逐个验证，保留旧版，保持执行
逻辑与流程可编辑。Coding Agent 依次处理 GUICourse、ShowUI、OS-Genesis、GUI
Schema CN、Mobile-Agent、Mobile-Agent-v2、MobileUse、UGround；每项通过后才修改
下一项。AppAgent 本轮保持原来的 80 行和文件字节。

## 设计与执行关系

继续使用现有 `machine` 编译简写，不修改组件、运行适配、编译器或执行内核。
YAML 中的阶段、分支目标、组件参数、模型依赖、设备服务和循环预算可直接编辑；
编译器生成稳定的 State、dispatch、Router、transition 和 merge 胶水。

简化前：完整 YAML 调度节点/边 → AgentGraph → 绑定 → Runtime。
简化后：阶段表 YAML → 既有通用展开规则 → 同一个 AgentGraph → 相同绑定与 Runtime。
没有把整个 Agent.step 藏进一个节点，也没有新增 Agent 名称判断或策略专属工厂。
原生观察/动作边界、run State、500 次操作上限与激活预算不变。

新增可选离线工具 `scripts/simplify_workflow_yaml.py`，每次仅处理一个文件。
它从显式连线恢复阶段内部节点，比较转换前后及实际序列化后的 canonical hash，
一致才写出；不匹配的图拒绝转换，不会默默丢弃未知语义。工具不加载组件、
连接设备或调用模型，运行 YAML 不依赖该工具。其代价单独计入离线工具成本。

## 每项完成后才进入下一项

每项先保存当前展开版，验证其原始字节与图身份，再转换该文件；通过静态校验、
图身份/分支与参数可编辑性检查、对应旧实现差分测试后记录 passed gate。
每次门禁同时检查所有未处理配置与上一项已通过配置的字节，防止提前批量修改。

| 顺序 | Agent | 展开版 → 简化版有效行 | 本项旧实现差分场景 | 结果 |
|---|---|---:|---:|---|
| 1 | GUICourse | 207 → 73 | 6 | 通过；另查两次运行隔离、交互预算 |
| 2 | ShowUI | 206 → 72 | 6 | 通过 |
| 3 | OS-Genesis | 206 → 72 | 6 | 通过 |
| 4 | GUI Schema CN | 206 → 72 | 6 | 通过 |
| 5 | Mobile-Agent | 228 → 78 | 11 | 通过；包含 A/B/C/D/不明确反思反馈 |
| 6 | Mobile-Agent-v2 | 228 → 78 | 11 | 单独通过同类反思检查 |
| 7 | MobileUse | 260 → 88 | 7 | 通过；包含 Manager 失败、Critic 纠正和笔记 |
| 8 | UGround | 257 → 85 | 11 | 通过；包含 Grounder 失败、摘要与重置异常 |

每项还各有一项图身份/可编辑性测试。八项共 64 个有限差分场景，比较真实本地
组件的调用顺序、提示原文、图像字节、动作/设备调用与记忆；AppAgent 的 8 个
原有场景在最终回归中再次通过。MobileUse 的初始规划/每步 Manager/纠正短路、
UGround 的定位失败等待且不提交新 last_action、双图摘要和可选设备设置都保留。

逐项命令、UTC 起止时间、快照、前后字节 hash、未处理文件保护与 passed 状态见
gates.json (not bundled in the core source)。
八份展开版保存在同目录 `before/`；九份原始 `examples/agent_*.yaml` 均与 HEAD
字节相同。AppAgent 的展开快照仍在上一轮专用证据目录中。

## 最终计量

YAML 有效行排除空行、整行注释；保留 AppAgent 的作者格式和 180 列换行宽度，
阶段表使用块结构，不把流程打包成字符串或依靠压缩整张表减少行数。

| Agent | 旧 YAML 有效行 | 最初展开版 | 当前简洁版 |
|---|---:|---:|---:|
| AppAgent（本轮未改） | 37 | 256 | 80 |
| GUICourse | 31 | 207 | 73 |
| ShowUI | 30 | 206 | 72 |
| OS-Genesis | 34 | 206 | 72 |
| GUI Schema CN | 31 | 206 | 72 |
| Mobile-Agent | 47 | 228 | 78 |
| Mobile-Agent-v2 | 47 | 228 | 78 |
| MobileUse | 60 | 260 | 88 |
| UGround | 52 | 257 | 85 |
| 合计 | 369 | 2054 | 698 |

本轮八份从 1798 降到 618 行，减少 1180 行（65.63%）。九份从本轮开始的 1878
降到 698 行；相对最初 2054 行展开版，共减少 1356 行（66.02%，包含此前 AppAgent
已减少的 176 行）。当前仍比旧版 369 行多，因为旧版把控制流放在 Python 类里。

组件已存在的前提下，每项额外必需 Python 组装为 0；共享代码和可选工具另列。
Python SLOC 排除空行、注释和 AST 文档字符串，经 tokenize 与 cloc 2.06 复核：

| 共享实现/工具 | Python SLOC | 本轮状态 |
|---|---:|---|
| 既有运行适配、端口合同与目录接入 | 304 | 完全未改；原迁移涉及范围 |
| 既有 machine 展开器 | 124 | 完全未改 |
| 既有编译入口/源位置接入改动范围 | 33 | 完全未改；此前编译适配涉及 157，净增加 145 |
| 本轮新增运行/编译适配 | 0 | 八项直接复用 |
| 本轮新增可选离线折叠工具 | 120 | 仅作者转换时使用，运行不依赖 |
| 原可选离线导出器 | 185 | 完全未改，运行不依赖 |

不把共享成本按九个 Agent 重复相加，不将 YAML 与 Python 混称纯 Python SLOC。
测试、门禁、文档和统计工具排除；未修改论文指标，也不由代码量推断开发时间。
完整物理行、有效行、源码范围、hash 和复核见
统计报告 (not bundled in the core source) 与
counts.json (not bundled in the core source)。

## 最终验证与手动复现

- 逐项门禁全部通过，所有图 canonical hash 与各自展开版相同。
- 完整相关回归 **594 passed**：其中既有迁移 76 项、新增逐图/离线工具 11 项，
  通用 machine 20 项，其他为相邻图、组件、目录、Runtime、CLI 和 Benchmark 编译检查。
- 新构建 wheel 的九图仓库外独立安装及其余资源检查 **8 passed, 1 deselected**。
  保留排除的是此前已执行失败的提示词数量断言（固定 16，工作区实际 27）；
  本轮未改提示词或该断言，不能称全部资源测试通过。
- 所有旧 YAML 与 HEAD 字节相同，AppAgent 和共享运行/编译代码与本轮基线相同。

在仓库根目录执行：

```bash
conda run -n unimobile python -m zhixing.cli agent validate examples/graphs/uground.yaml
conda run -n unimobile python -m pytest tests/runtime/test_legacy_yaml_migration.py tests/graph/test_simplified_legacy_workflows.py -q
conda run -n unimobile python -m pytest tests/packaging/test_legacy_yaml_migration_install.py -q
python3 output/validation/eight-workflow-simplification-20261021/count.py
```

预期依次是 valid 和原 UGround 图身份、87 项通过、九图独立安装后 TAP → DONE、
九份 698 有效行和本轮适配 0/离线工具 120 SLOC。门禁与历史统计快照不覆盖；
新的当前文件字节清单及完整结果在本轮证据目录 `manifest.json` / `results.json`。
如需重新导出展开版，可在副本上执行旧导出器，再用离线折叠工具逐文件转换；
不要运行已完成的门禁去重写历史证据。

## 已知边界

证据针对本地选定策略和有限脚本输入，不是任意模型输出等价、真实模型/设备
成功率、Benchmark PASS 或上游算法复现。本轮未执行真实模型或设备。旧 Modular
持续异常可能递归不收敛，新图有 500 次操作上限；native 预算、取消与异常归一化
相对旧 Runner 的已知差异继续存在，本轮没有改动这些边界。

Mobile-Agent/v2 本地配置原本相同，不是独立架构证据；GUI Schema CN 的 AgentCPM
风格归属仍是推断，AndroidLab 未纳入。machine 是明确端口约定的可选简写，
复杂不匹配结构仍可使用完整命名节点图，不能据此宣称任意 Agent 范式都已验证。
