# SeeClick 在线执行

本次实现按用户确认的方案，把 SeeClick-AITW 的单步预测接入既有六大组件与
AgentGraph。启用 Perception、Memory、Reasoning、ActionExecutor；Planner 和
Verifier 不参与。Coding Agent 完成了组件、模型适配、图、示例与测试；下述模拟
设备和替身模型结果不是用户提供的真实实验，也不是原论文成功率复现。

## 当前状态与范围

- 已实现并执行 SDK/YAML 在线闭环、四步历史、移动动作映射、失败与独立预算。
- SeeClick 专属测试为 49 项组件/图/模型接口检查及 1 项干净 wheel 验收。
  包含它们的相关回归共 348 项通过；其中一个已有 HTTP 测试因沙箱限制不能绑定
  回环端口，在允许本地端口的环境中单独复核通过。
- 真实权重、真实 CUDA 推理与真实 Android SeeClick 轨迹均未验收。模型加载接口的
  full/LoRA 检查使用替身依赖，不能当成模型兼容性或效果证据。
- 没有修改 Graph Runtime 内核、设备动作实现、旧 Agent 路径、Benchmark 合同或
  Studio。编译不实例化模型、不读取 checkpoint、不连接设备或解析凭据。

## 原版对应关系

来源为 [SeeClick，ACL 2024](https://aclanthology.org/2024.acl-long.505/)，代码固定在
[`0ef37ac4d7aaf37ba7b990e3e3c3ca77e1fb8f93`](https://github.com/njucckevin/SeeClick/tree/0ef37ac4d7aaf37ba7b990e3e3c3ca77e1fb8f93)。

| 原版入口 | 本次对应 | 边界 |
| --- | --- | --- |
| `agent_tasks/aitw_test.py` 的提示与动作预测 | `SeeClickReasoning` | 原版 AITW 是录制截图上的逐步评分，历史来自已有标注，不能称为实时 Android 程序 |
| `agent_tasks/miniwob_test.py` 的最近四步原始响应 | `SeeClickMemory` | 在线版使用自身已执行预测；不使用 AITW 当前/未来标注，也不保留模型 chat history |
| `agent_tasks/action_matching.py::pred_2_format` | `SeeClickActionParser` | 只借用数字动作与 x/y 向量约定；评分的 y/x 转换和文本小写化不进入设备执行 |
| Qwen tokenizer、GenerationConfig、`model.chat(history=None)` | `SeeClickLLM` | 一张当前截图在前，任务/历史文本在后；每个决策一次预测，无自动重新采样 |
| MiniWob 环境动作 | 既有 Android ActionExecutor | Android 的尺寸转换、400ms 精确滑动与设备生命周期是本次运行适配，不是复制浏览器偏移量 |

固定的提示与手势合同保存在 `tests/fixtures/seeclick/source_contract.json`。它来自
上述提交，不是从本次实现反向生成的期望结果。

本次保留正常输入下的预测接口与动作语义，但不声明完整行为等价：原 MiniWob 会
把错误响应加入历史并跳过该轮；本实现明确 FAIL，不继续执行、不重新调用模型，
并只将已执行动作带入下一轮。未知 id、网页专属 SELECT、非法坐标与超长输出也
明确拒绝。不能据当前闭环或 SDK/YAML 相同 hash 推导原版等价或论文指标复现。

## 组件与执行流

| 六大角色 | 使用方式 |
| --- | --- |
| Perception | 复用 `screenshot_perception`，只使用原图和尺寸，不将 XML、OCR、控件编号或感知说明加入模型提示 |
| Memory | 新增 `seeclick_memory`，使用公共 RESET/APPEND/READ 合同，状态属于 RuntimeContext，最多四条原响应 |
| Planner | 关闭，模型直接预测下一动作 |
| Reasoning | 新增 `seeclick_reasoning`，按原提示格式从 Step0 重新编号历史，忽略通用 plan/app catalog/反思文本 |
| ActionExecutor | 复用 `zhixing.runtime:action_executor` 与既有 Android 观察/执行服务，所有设备副作用经此边界 |
| Verifier | 关闭，DONE 与独立任务评价分开 |

外层 `LoopSpec` 控制决策轮次。每轮从 run-scope State 取上次执行结果，Memory
追加它并读取最近四步；DeviceObserve 捕获当前截图，Perception 原样提供原图；
Reasoning 调用模型一次，解析为 Action；ActionRequestAssembler 合并观察与动作，
ActionExecutor 执行并保存结构化结果，State 写入本轮结果。终态离开循环，否则
进入下一轮。不需要新增 Agent.step 子类或修改通用 Kernel。

模型是 Reasoning 的依赖，属于既有模型接口，不是第七个核心角色。旧 AgentConfig
YAML 与 BenchmarkTask JSON 没有修改，也不相互转换。

## 动作与失败

| SeeClick action_type | 框架动作 |
| --- | --- |
| 4 | TAP，严格使用 [0,1] 的 `(x,y)`，按截图尺寸换算；1 映射到最后一个有效像素 |
| 3 | TEXT，保留大小写/空格/引号，不额外点击、清空或 Enter |
| 0 / 1 / 8 / 9 | 精确 SWIPE，使用来源合同中的起止坐标，避免平台方向命名歧义 |
| 5 / 6 / 7 | KEY back / home / enter |
| 10 / 11 | DONE / FAIL，不产生设备交互，不自行重置应用 |

解析使用受限的 `ast.literal_eval`，支持原协议的字典和 tuple，不执行表达式。
输入响应最多 32768 字符，文字最多 4096 字符；布尔 id、越界/非有限坐标、错误
字段均不能猜成操作或完成。解析失败和模型异常只有稳定错误类别进入失败诊断，
不附原始异常文本。合法模型预测作为原始动作历史/轨迹保留，不应放入凭据。

两个预算独立：

- `max_decisions` 限制外层 Loop 的单次预测轮次，耗尽产生 `runtime.loop_exhausted`
  的 FAILURE，不伪装成 DONE。
- `max_steps` 复用 Runtime 的物理交互上限，耗尽为 STEP_LIMIT。当前 Runtime 在
  达到上限的动作确认后立即结束，不保证再给模型一次 DONE 判断机会；终态自身不
  消耗物理交互。SDK 的运行配置还会施加同类上限。

设备失败沿共享服务返回 DEVICE_FAILURE，不继续调用模型。应用启动、任务 reset
和最终 Benchmark 评价属于调用者或独立 Benchmark 生命周期，没有自动增加到原
SeeClick 动作空间。

## 使用

源码环境中的无副作用检查：

```bash
conda run -n unimobile python -m examples.sdk.seeclick_online --dry-run
```

预期输出 graph hash 与 `execution_evidence=false`，不要求权重、CUDA、模型库、
凭据或在线设备。默认 SDK 与 `examples/graphs/seeclick_online.yaml` 的 hash 相同。

模型依赖采用按需加载：`SeeClickLLM` 的构造不导入 Torch/Transformers/PEFT；第一次
真实预测才加载。默认 `local_files_only=True`，要求预先准备好完整 checkpoint/
adapter、匹配的 Qwen tokenizer/config 和缓存实现。`full` 与 `lora` 必须显式选择
正确形态，不根据路径猜测。可用 `revision` / `qwen_revision` 固定各自版本。

原版模型栈较旧，建议使用独立 GPU 环境安装核心 wheel，再按
`examples/seeclick/requirements-model.txt` 准备推理依赖，不将它混入当前通用视觉
环境。这是待真实权重验收的参考依赖表，不是已经验证的 CUDA lockfile。不要用
通用 VLM 替代 checkpoint 后仍称为原模型复现。

准备好模型环境及明确设备后，在源码目录手动执行，例如：

```bash
python -m examples.sdk.seeclick_online \
  --model-path /absolute/checkpoints/SeeClick-aitw \
  --qwen-path /absolute/checkpoints/Qwen-VL-Chat \
  --checkpoint-format full \
  --serial YOUR_ANDROID_SERIAL \
  --task '打开设置' \
  --max-steps 30 --max-decisions 30
```

该真实运行命令本轮未执行。原生模型不使用 API key；其他实现了
`generate(prompt, images)` 的可信模型连接可通过
`compile_agent(build_seeclick_graph(), dependencies={"llm": model_client})` 注入。
远程服务还需自行验证相同权重、图文顺序与生成设置；本变更没有提供模型服务器或
保证任意 OpenAI 兼容服务等价。

## 验证

```bash
conda run -n unimobile python -m pytest tests/runtime/test_seeclick_online.py -q
conda run -n unimobile python -m pytest tests/packaging/test_seeclick_install.py -q
```

预期分别为 49 passed 与 1 passed。多轮图测试通过实际 SDK/YAML、Core 组件、
Android 观察服务、动作执行器和轨迹发布路径，执行点击、输入、四向滑动、三个
按键和 DONE，共 9 个确认物理交互、10 次预测/观察。逐轮核对原提示字节、四步
窗口、原图路径与全部设备命令；另验证同一 ExecutableAgent 的两次运行隔离。

wheel 验收在不继承开发 site-packages 的独立 venv 中只安装基础依赖与新 wheel，
从仓库外执行复制的 YAML/示例；阻止导入 Torch/Transformers/PEFT/OpenAI/OpenCV，
验证 prompt 资源、SDK/YAML identity、2 次物理交互和终止 DONE。外部模型库的
替身还覆盖 full/LoRA 加载接口、版本参数、本地缓存策略及 image-first/history=None。

本轮相关回归命令：

```bash
conda run -n unimobile python -m pytest \
  tests/runtime tests/graph tests/sdk tests/components tests/catalog tests/cli \
  tests/benchmark/test_architecture_compatibility.py \
  tests/studio/test_capability_authoring.py tests/studio/test_runtime_readiness.py \
  tests/studio/test_documents_catalog_compiler.py \
  tests/packaging/test_seeclick_install.py tests/packaging/test_autodroid_install.py \
  tests/packaging/test_dependency_profiles.py -q
```

其中现有 HTTP readiness 测试需要允许监听回环端口；受限环境中 347 项通过、该
项因 PermissionError 未运行成功，随后单项在允许本地端口的环境中 1 项通过。
不能把权限失败隐瞒为第一次全量命令已全部通过。

剩余边界：没有训练、ScreenSpot/AITW 评分复现、模型质量比较、真实模型/手机
验收、任意布局/语言/多行文本保证或原生模型调用的抢占式取消。任务完成必须另由
BenchmarkTask/evaluator 验证；Agent DONE 本身不足以证明应用任务成功。
