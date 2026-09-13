# Android AgentGraph Runtime 验收指南

ZhiXing 现在可以把一个已绑定的 AgentGraph 交给通用
`GraphExecutionKernel` 调度，同时由 Android runtime services 完成真实设备观察和动作。
Kernel 不包含 Android、ADB、Agent 范式或具体动作类型分支。

本指南使用不依赖 LLM/VLM 密钥的确定性图：

```text
Input
  → DeviceObserve
  → BuildAction
  → ActionExecutor
  → Condition(action succeeded)
  → DeviceObserve
  → BuildDone
  → ActionExecutor(DONE)
  → Output
```

## 1. 检查设备

在仓库根目录激活项目环境后运行：

```bash
adb devices -l
adb -s emulator-5554 shell getprop ro.build.version.release
adb -s emulator-5554 shell wm size
```

第一条命令中目标设备必须是 `device`，不能是 `offline` 或
`unauthorized`。多设备场景必须显式传入 serial，runtime 不会猜测第一个设备。

## 2. 执行成功烟测

下面的图会采集设备状态、执行可恢复的 HOME 键、再次采集状态并显式 DONE：

```bash
python -m examples.acceptance.android_smoke \
  --serial emulator-5554 \
  --artifact-root temp/android-graph-runtime \
  --run-id manual-success \
  --mode success
```

每个 run ID 只能使用一次，避免覆盖既有证据。再次运行时请更换
`--run-id`。

命令应退出 0，输出 JSON 中至少满足：

- `status == "success"`；
- `kernel_status == "success"`；
- `activation_count == 9`；
- `interaction_count == 1`；
- 第一个 ActionResult 的 `effect_performed == true`；
- 最后一个 ActionResult 的 `terminal_status == "success"`。

## 3. 查看成功证据

产物位于：

```text
temp/android-graph-runtime/manual-success/
  manifest.json
  interaction-0000/
    observation-0000.png
    observation-0000.xml
    action-0000.json
  interaction-0001/
    observation-0001.png
    observation-0001.xml
    action-0001.json
```

人工检查时依次确认：

1. 两张 PNG 能打开，两个 XML 能被 XML parser 读取；
2. `manifest.json` 的 `run_id` 和 `device_id` 正确；
3. event 顺序与本页图一致，所有成功节点都有配对的 `start/complete`；
4. HOME 是唯一一次物理 interaction，DONE 不增加 interaction；
5. Kernel 正常完成和 Agent 显式 DONE 分别记录，没有把二者混为一谈。

## 4. 执行受控失败烟测

下面的模式让 Android 解析一个确定不存在、但格式合法的包名。该操作不会安装、
删除或修改应用数据：

```bash
python -m examples.acceptance.android_smoke \
  --serial emulator-5554 \
  --artifact-root temp/android-graph-runtime \
  --run-id manual-device-failure \
  --mode device-failure
```

这是“预期失败”验收，所以只有 runtime 得到 `DEVICE_FAILURE` 时命令才退出 0。
检查：

- `status == "device_failure"`；
- `kernel_status == "failure"`；
- `error_details.kernel_error_code == "runtime.device_failure"`；
- `execute_action` 产生 `start/fail`；
- `interaction_count == 0`，因为动作没有产生真实副作用；
- 首次 observation 与失败 ActionResult 仍然存在；
- 失败后不再激活 condition、二次 observation 或 DONE。

轨迹支持人根据失败节点、错误和已有观察定位阶段，但 ZhiXing 当前不提供自动失败诊断。

## 5. 常见问题

- `Artifact namespace already exists`：更换 `--run-id`。
- `offline` / `unauthorized`：恢复模拟器或重新授权，再运行 `adb devices -l`。
- 多设备歧义：始终显式传入目标 serial。
- 截图或 UI XML 缺失：该 run 应视为设备失败，不能只看 Kernel 是否结束。
- `No launchable activity`：成功模式下表示目标包不可启动；失败模式下是预期证据。

## 6. Python API

业务代码可直接绑定自己的图，而不需要策略底板：

```python
from zhixing.components import ObservationRequest
from zhixing.runtime import build_android_smoke_plan, run_android_agent_graph

result = run_android_agent_graph(
    build_android_smoke_plan(),
    {"value": ObservationRequest()},
    serial="emulator-5554",
    artifact_root="temp/android-graph-runtime",
)
```

`build_android_smoke_plan()` 仅用于确定性验收。真实 Agent 应由自己的组件、端口和边
直接形成 AgentGraph，再复用同一个 Android facade 与 Kernel。
