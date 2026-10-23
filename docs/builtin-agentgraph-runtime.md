# 内置 AgentGraph 后端闭环

ZhiXing 现在提供两种等价的 Agent 定义方式，并统一执行同一个 contract 1.1
`AgentGraph`：

```text
graph-native YAML ─┐
                   ├─ AgentGraph → validate → bind → AndroidGraphRuntime
Python Builder ────┘
```

这条新路径不经过旧 `AgentFactory`、`ModularAgent` 或 `AgentRunner`。旧
AgentConfig YAML 和 BenchmarkTask JSON 仍然保留：

- graph-native YAML：定义新 AgentGraph；
- 旧 AgentConfig YAML：继续由 `run.py` 执行尚未迁移的策略；
- BenchmarkTask JSON：定义任务初始化与评估，不属于 AgentGraph。

## 安装与配置

安装模型能力：

```bash
python -m pip install -e ".[openai]"
```

创建仅在绑定阶段读取的 `secrets.yaml`：

```yaml
api_key: "your-runtime-key"
base_url: "https://your-openai-compatible-endpoint/v1"
```

真实值不会进入 AgentGraph canonical hash。

## YAML 运行

内置示例位于 `examples/graphs/builtin_android_agent.yaml`。非交互运行：

```bash
zhixing run \
  --agent examples/graphs/builtin_android_agent.yaml \
  --instruction "打开相机并拍一张照片，完成后结束任务" \
  --serial emulator-5554 \
  --secrets secrets.yaml \
  --artifact-root temp/runs
```

省略 `--instruction` 后，命令从标准输入读取一个任务：

```bash
zhixing run \
  --agent examples/graphs/builtin_android_agent.yaml \
  --serial emulator-5554 \
  --secrets secrets.yaml
```

## Python SDK 运行

```python
import yaml

from zhixing import AgentRunConfig, compile_agent
from zhixing.agents import build_builtin_mobile_agent_graph

secrets = yaml.safe_load(open("secrets.yaml", encoding="utf-8"))
agent = compile_agent(
    build_builtin_mobile_agent_graph(),
    secrets=secrets,
)

print(agent.canonical_hash)
result = agent.run(
    "打开相机并拍一张照片，完成后结束任务",
    AgentRunConfig(
        serial="emulator-5554",
        artifact_root="temp/runs",
        max_steps=10,
    ),
)
print(result.status.value, result.run_id, result.artifact_namespace)
```

YAML 与默认 SDK 示例的 canonical hash 由 golden test 固定为：

```text
sha256:4f60da0883b13c82accbc1a13ee4f10e1f56407cde8904efd1cae291fe5123e6
```

## 当前生产拓扑

```text
TaskInput → Memory → iteration Router → DeviceObserve
                                      → ScreenshotPerception
                                      → UniversalReasoning
                                      → ActionRequestAssembler
                                      → ActionExecutor
                                              │
                         terminal ActionResult ├→ Output
                         physical ActionResult └→ bounded feedback → Memory
```

每次 `.run()` 都重新绑定组件，因此 Memory、fallback 和 RuntimeContext 不会在
任务之间共享。设备、任务、run ID、artifact root、SecretRef 的真实值均不改变图
身份。

## 逐步验收

1. 验证 YAML 与 SDK 语义一致：

   ```bash
   uv run --with-editable . --extra dev python -m pytest \
     tests/sdk/test_executable_agent.py::test_yaml_and_sdk_define_the_same_executable_agentgraph -q
   ```

2. 在 fake Android 上运行完整多步链：

   ```bash
   uv run --with-editable . --extra dev python -m pytest \
     tests/sdk/test_executable_agent.py::test_executable_agent_runs_full_feedback_loop_on_fake_android -q
   ```

3. 验证连续两次运行状态隔离：

   ```bash
   uv run --with-editable . --extra dev python -m pytest \
     tests/sdk/test_executable_agent.py::test_executable_agent_rebinds_memory_and_fallback_state_per_run -q
   ```

4. 查看安装命令：

   ```bash
   uv run --with-editable . --extra dev zhixing --help
   ```

5. 真实 Android 内容增量 Verifier 拍照验收：

   ```bash
   uv run --with-editable . --extra openai python \
     -m examples.acceptance.photo_task \
     --agent examples/graphs/android_content_verified_agent.yaml \
     --serial emulator-5554 \
     --secrets secrets.yaml \
     --artifact-root temp/acceptance/photo
   ```

该示例通过普通 AgentGraph 插入可配置的 `android_content_delta_verifier`；
Runtime 和默认 Agent 不包含拍照任务逻辑。真实验收只有在 Agent 返回 `SUCCESS`
且 MediaStore 出现新增图片 ID 时才通过。新增图片但 Agent 未正常结束仍判失败。
轨迹只支持人工定位失败阶段，不宣称自动失败诊断。
