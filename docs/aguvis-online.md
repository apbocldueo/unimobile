# Aguvis-7B：CLI 协议的 Android 在线适配

> 2026-10-22：本实现保留为 ZhiXing 自补在线适配实验，**暂不计入官方完整 Mobile
> Agent LOC 对比或有效样本数**。新找到的官方 OSWorld 桌面闭环与本实现不同；
> 不能用 163 行单步核心或包含自补逻辑的 388 行基线作为官方完整流程。见
> [官方来源复核与决定](aguvis-official-source-audit.md)。

2026-10-21。用户选择 Aguvis 并授权按调研方案开发。Coding Agent 完成模型协议、
动作转换、AgentGraph、示例、测试和安装验收；本记录不把这些工作描述为用户手写。

## 已实现的执行链

任务 → 共享 ObservationProvider 截图 → 既有 screenshot_perception → 既有
sliding_window_memory 的 TEXT 历史 → Aguvis 单次推理 → 解析完整命令批 →
图上逐原子执行 → 成功后写入低层指令历史 → 下一轮观察。

此前只有 Aguvis 的调研及官方单步推理入口。本次新增的是 ZhiXing 拥有的在线装配。
每次预测仍遵守官方提交 `178c4187069d8aa028aaf00f209139824c00a76f` 的消息、
模板、模式前缀、processor 调用、输入 token 切片和解码；单步返回没有包含的前缀
不由解析器凭空当作模型重新生成的内容。

主要入口：

- SDK：`zhixing/aguvis.py:build_aguvis_graph`。
- 可编辑 YAML：`examples/graphs/aguvis_online.yaml`，显式列出组件、连接和两个循环。
- 命令行示例：`examples/sdk/aguvis_online.py`。
- 来源和开发前的边界：调研快照 (not bundled in the core source)。

## 六种职责的实际使用与复用

| 职责 | 本次实现 |
| --- | --- |
| Perception | 直接使用已有 screenshot_perception；不将它的通用说明额外加入模型提示 |
| Memory | 直接使用已有 sliding_window_memory，窗口覆盖 max_decisions；只保存 Step i 的 TEXT |
| Reasoning | 新增 AguvisReasoning，只做一次 typed 模型调用和结果规范化 |
| Planner | 无独立规划节点；单模型模式由 Aguvis 自身规划/定位 |
| Verifier | 无独立反思节点；回答/结束声明与 Benchmark 判定分离 |
| ActionExecutor | 直接使用共享 action_executor；命令批在普通有界子图中依次提交 |

`aguvis_adapters.py` 中的准备、游标恢复、确认、回答、分支合并和历史转换节点是
纯装配/控制转换，不是六种新的 Memory 算法。它们没有设备句柄或模型调用。

为传递精确 TEXT，增加显式 `zhixing.memory.fragments:1.0` 合同；共享角色 assembler
允许原样传递 MemoryFragment。旧 `zhixing.core.memory:1.0` 的端口、默认映射和
哈希语义没有改动。其余扩展合同位于 `zhixing/graph/aguvis_contracts.py`。
**没有修改 GraphExecutionKernel，也没有添加 Aguvis 专属调度分支。**

## 模型和命令合同

`AguvisLLM` 仅在实际预测时加载可选运行库与模型。默认 checkpoint revision 为
`6dd54127b5b84b9ee89172a5065ab6be576f0db9`，默认 local_files_only=True。
source 里与推理有关的五组常量以 JSON 资源保存；来源文件及哈希在
`tests/fixtures/aguvis/`，差异测试执行固定官方函数的 AST，mock 外部模型/tensor。

- 支持 self-plan、force-plan、grounding，以及优先于 mode 前缀的低层指令。
  配置层拒绝非法 mode，不复刻官方“非法 mode 但提供低层指令可绕过校验”的漏洞。
- 使用原图和发布 processor；不固定缩放为 UGround 尺寸，不要求 XML/OCR/SoM。
- 每决策一次推理；模型或解析失败显式 FAIL，不重新采样。
- 整批命令先解析，再执行；AST 只接受允许函数的字面量调用，不 eval/exec 模型代码。
- 支持点击、写入、有限 Android 按键、长按、明确端点 swipe、page scroll、Home、
  Back、等待、打开应用、回答和终止。未覆盖的桌面 API 明确拒绝。
- 文本输入不隐含点击或 Enter；Backspace 映射单个 KEYCODE_DEL，不使用共享 del
  别名的清空全文行为。
- answer 只产生回答事件/批结果数据，不自动成功或退出；后续 terminate 才给出
  Agent 结束声明。回答事件保留在 RunResult.events 与 trajectory 中。

### 明确属于本次适配的规则

原仓库没有 Android 执行器，因此以下规则不是官方 runner 的恢复结果：

1. 点/端点坐标采用原始截图上的 0–1 归一化转换，1 映射最后一个像素；拒绝越界和
   0–1000 猜测。采用此合同有官方移动数据小数坐标证据，但没有原执行器可做像素级对照。
2. `scroll(page=...)` 按对应截图轴长度计算位移、以屏幕中心生成手势。正垂直滚动
   对应手指向下，正水平滚动对应手指向左；小屏幕端点收敛到边界。默认 swipe
   400ms、long_press 1000ms，可调。默认拒绝 wheel clicks 单位；只有明确设置
   scroll_pixels_per_click 才转换。page 绝对值最大 0.8。
3. WAIT 只接受 0.5–30 秒，使共享执行器无需静默裁剪。未实现命令间的隐式 settle
   等待；需要等待时由明确的 mobile.wait 或图节点表达。
4. 应用显示名由已有 Android start_app 的注册别名/包名边界解析。未注册名称明确
   失败，不猜 package，不自动操作启动器。设备配置需提供实际所需的别名。
5. 同一回复允许有限个顺序调用；先遇到失败/终止就停止。终止后仍有命令的整批
   回复在执行前拒绝。保留失败之前已经确认的原子动作；不在原子动作之间增加推理。
6. 历史只追加完整成功的非终止决策。有 Action 描述时用该低层指令，否则使用
   原命令文本作为已披露的 fallback；不将失败动作编成“已成功”历史。
7. 提供 terminate/mobile.terminate 与 answer/mobile.answer 的显式移动适配别名；
   默认无参 terminate 表示 success，未知状态拒绝。它们不增加 Benchmark 评测证据。

## 验证与可复跑命令

当前证据分三层：

- Aguvis focused：61 项检查，覆盖固定来源函数对照、parser、SDK/YAML 实际图执行、
  历史/多动作顺序/回答、部分失败、独立预算、跨 Run 隔离、惰性模型加载和边界。
- 相关回归与安装验收合计 **383 passed**：Graph、绑定/assembler、Kernel、Catalog、
  AutoDroid、SeeClick、V-Droid、Agent-SAMA、Aguvis 和独立 wheel 测试；结果见
  `output/validation/aguvis-online-20261021/regression.xml`。
- 独立 base-wheel：禁止 Torch/Transformers/Qwen/OpenAI/CV2/NetworkX 导入，离开
  checkout 编译 YAML、对照资源、执行多命令图及 SDK dry-run 通过。
- 另保留 SDK/YAML 各一条 fake 轨迹，均为四次模型决策、五次物理交互，图身份、
  历史和动作序列一致。索引见 `output/validation/aguvis-online-20261021/ledger.json`。

```bash
conda run -n unimobile python -m pytest tests/runtime/test_aguvis_online.py -q
conda run -n unimobile python -m pytest tests/packaging/test_aguvis_install.py -q
conda run -n unimobile python examples/sdk/aguvis_online.py --dry-run
```

预期 focused 显示 61 passed；安装测试显示 1 passed；dry-run 输出 graph_hash 和
execution_evidence=false，不连接设备或下载模型。

在专用模型环境中安装推理依赖后，可手动运行缓存 checkpoint：

```bash
python -m pip install -e '.[aguvis]'
python examples/sdk/aguvis_online.py --model-path /absolute/path/to/Aguvis-7B-720P --device cuda --serial emulator-5554 --task 'Open Settings'
```

以上设备标识和任务是命令示例，执行前选择自己的在线设备和可用应用配置。
模型依赖只在 `aguvis` extra；未并入现有 `all`，因为 AutoDroid 的 Transformers
约束与官方 Aguvis 4.47.1 不相交。不要把两个专用模型后端强行装进同一个环境。
官方 CLI 使用的训练栈（DeepSpeed、W&B、训练 Dataset 等）没有作为框架强制依赖。

## 尚未验证与后续比较边界

- 没有加载真实 checkpoint、运行 CUDA/MPS/CPU 模型推理或新增真实 Android 轨迹。
  当前执行的是代表性 fake-device 图，不能据此宣称模型任务质量或任意设备支持。
- 此首版不是论文 GPT-4o+7B 或 72B 在线实验配置的完整复现；未做 Benchmark 比较。
- scroll/历史追加/时序规则缺少官方在线执行器作为逐步对照，必须保留上述适配标记。
- 后续 LOC 审计已完成：官方保留核心 163 Python SLOC，新增在线适配/装配 225，
  可执行基线 388；图定义现为 63 YAML 行（原 97 行），另披露新增支撑 407 Python
  SLOC 和 9 JSON 资源行。YAML 使用既有引用/合并语法共享重复声明，并归组连线；
  解析字段、连线顺序和 canonical graph 均与原版本完全一致。本轮未新增 Python。
  63 行版本的计数、62 项测试与 15 组模拟对照见
  YAML 精简报告 (not bundled in the core source)。官方来源见
  核心 LOC 报告 (not bundled in the core source)，不能将
  388 全称为官方代码，也不能以短 YAML 代替完整实现成本。

口述与追问见 面试记录 (not bundled in the core source)。
