# AppAgent YAML：将调度胶水收回编译器

用户要求先检查 AppAgent，在保持执行逻辑和流程可编辑的前提下简化、再统计。
Coding Agent 确认上一轮将通用 dispatch、route、transition、merge、State
读写及其连线重复写入 YAML，完成通用编译简写和 AppAgent 配置修改。
其他八个 Agent 的新 YAML、九个旧 YAML、既有运行适配和离线导出器均未改。

## 前后执行关系与取舍

旧 YAML 通过 agent_type 选择既有 Python 策略，流程编辑需要改类实现。上一轮
迁移将调用、分支和状态都展开成可编辑图，但把框架固定胶水也交给作者维护。
这次在 YAML 中保留阶段、22 条分支去向、组件/模型配置、请求/确认设备边界、
State 和循环预算；通用 `machine` 简写只生成固定调度结构。

编译路径为：YAML → 通用 machine 展开 → 普通 AgentGraph → 既有绑定和 Runtime。
运行时仍逐节点调用真实感知、验证、推理和设备服务，未隐藏为整个 Agent.step。
没有新增 AppAgent Python 工厂、策略预设或 Kernel 分支。

保留的流程为：观察 → 验证 → 感知选择 → 单次感知 → 查询记忆 → 推理/缓存
→ 提交 → 执行 → 观察；纠正短路、感知重试重新验证、错误执行路径不变。
500 次操作上限及所有激活预算保留，终止仍取决于确认结果。

选择通用编译展开的成本是增加一层作者格式和对应诊断；好处是策略分支仍由
YAML 控制，完整展开图仍可序列化检查。只调整换行或把整个旧 step 包成单节点
无法同时达到这两个目标。本次也没有进一步合并那些目标相同的 outcome，避免
改变未知 outcome 的行为或现有 canonical graph 身份。

## 重新统计

口径沿用上次：YAML 排除空行/整行注释，Python 排除空行、注释和 AST 文档字符串。
作者格式使用与上一轮一致的组件 flow mapping 和 180 列换行宽度；阶段表使用
普通块结构，没有把图存成字符串或将整个表压成一行。

| AppAgent | YAML 总行 | YAML 有效行 |
|---|---:|---:|
| 保留的旧版 | 44 | 37 |
| 上轮显式展开 | 256 | 256 |
| 当前 machine 写法 | 80 | 80 |

比上轮减少 176 行（68.75%），仍比旧版多 43 个有效行，为旧版的 2.1622 倍。
原因是旧版控制流隐藏在策略类，而当前配置显式表达可编辑分支和预算。
其余八份不变，九项新 YAML 合计从 2054 降到 1878 行；旧版有效行合计仍为 369。
当前 AppAgent 额外必需的专属 Python 组装为 0，新增共享成本另列：

| 共享实现 | Python SLOC | 变化 |
|---|---:|---|
| 运行适配/端口合同/目录接入 | 304 | 上轮涉及代码，完全未改 |
| machine_yaml.py | 124 | 本轮新增通用展开器 |
| 既有编译器及源位置接入 | 33 | 本轮新侧涉及行；替换原代码 12 SLOC |
| 本轮涉及范围 | 157 | 净增加 145 SLOC |

旧离线导出器 185 SLOC 未改，不是运行或逐 Agent 组装的必需成本。完整九项表、
源码哈希、逐行范围、编译器差分和 cloc 复核见
统计报告 (not bundled in the core source) 与
counts.json (not bundled in the core source)。
这不是整个框架代码量，也没有更新论文 LOC 或推断开发时间。

## 验证与复现

简化前后 canonical hash 均为：

```text
sha256:d353781fa1e2caea47157a6da8bcfa032ce0ff8d53424e9a055180b58154597d
```

这证明展开后在既有规范化规则下是同一执行图，包括分支、节点参数、依赖、
端口、State 与预算。20 项新增检查还覆盖两种自定义字段的非 Agent 假组件流程、
复合阶段、分支编辑后真实跳过阶段、两次运行隔离、配置变更影响图身份、错误
位置、冲突/未知字段/越界和全新解释器编译不导入组件/模型/设备。

已有 76 项迁移检查继续通过，其中 AppAgent 的 8 个有限差分场景比较真实组件
调用顺序、提示和图像字节、动作与设备调用、记忆和感知索引。完整相关回归
**583 passed**；新构建 wheel 的九图独立安装及其余资源检查
**8 passed, 1 deselected**。排除的是此前已执行失败的提示词数量断言：固定 16，
工作区实际 27；本轮未改提示词或该断言，不能称全部资源测试通过。

在仓库根目录复现：

```bash
conda run -n unimobile python -m zhixing.cli agent validate examples/graphs/appagent.yaml
conda run -n unimobile python -m pytest tests/graph/test_machine_yaml.py tests/runtime/test_legacy_yaml_migration.py -q
conda run -n unimobile python -m pytest tests/packaging/test_legacy_yaml_migration_install.py -q
python3 output/validation/appagent-authoring-simplification-20261021/count.py
```

预期依次为 valid 和上述 hash、96 项通过、仓库外离线安装后九图 TAP → DONE、
80 行 AppAgent 与共享代码计量结果。旧展开文件保存在
appagent.before.yaml (not bundled in the core source)。
旧迁移 manifest 记录的是上轮 256 行版本，不应继续将其字节 hash 当作当前文件；
本轮新快照和命令结果见同目录 manifest.json/results.json。

## 证据边界

本轮没有真实模型、手机或 Benchmark 测试；这些证据支持本地选定策略的图保持
和有限差分行为，不支持任意输出等价或上游算法成功率。上轮已披露的旧递归
不收敛与 native 有界循环、预算/取消/异常归一化边界继续存在，没有在本轮扩展。
machine 是特定端口约定的可选作者简写，不声称能表达所有 Agent 范式；复杂不匹配
结构仍用完整图。本轮仅检查 AppAgent，不继续修改其他八份 YAML。

## 后续八项已独立完成

以上为 AppAgent 单项轮次记录。用户随后授权将其余八项按同样方式逐个简化、
逐个验证，现已完成；AppAgent 本身保持 80 行和本轮字节 hash。最新九项合计
为 698 行，运行/编译适配增量为 0，新增离线转换工具另计 120 SLOC。
当前文件清单和证据以 [九项简化记录](legacy-agent-yaml-simplification.md) 为准，
不覆盖这里的历史快照。
