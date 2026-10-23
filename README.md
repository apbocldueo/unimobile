# ZhiXing

**A Unified Framework for Building and Benchmarking Mobile GUI Agents**

[中文说明](README_CN.md) · [Paper artifact guide](docs/paper-artifact.md) · [Examples](examples) · [Documentation](docs/project-overview.md)

ZhiXing brings Mobile GUI Agent construction and task benchmarking into one
framework. Reusable components, composable AgentGraphs, and a shared Graph
Runtime let you assemble Agent workflows without writing a separate execution
loop for each implementation. ZhiXing-Bench provides declarative task
definitions, reusable initialization and evaluation plugins, and automated
outcome evaluation.

An Agent can receive different tasks and run independently, or be invoked by
ZhiXing-Bench. Agent configuration and benchmark task definitions remain
independent, so changing a task does not require rebuilding the Agent workflow.

## Architecture

![Paper overview of ZhiXing and ZhiXing-Bench: Agent Config becomes a validated and bound executable Agent using Graph Runtime; independent Task Definitions feed task construction, scheduling, instance materialization, setup, Agent execution, outcome evaluation, reports and Replay.](docs/assets/zhixing-paper-workflow.png)

The workflow has two connected parts: **ZhiXing constructs and executes Agents**;
**ZhiXing-Bench constructs tasks and evaluates their outcomes**. The executable
Agent and its Graph Runtime are reused during benchmark execution.

### Build and run Agents

Compose perception, reasoning, memory, and action components into an AgentGraph
using Python or YAML. ZhiXing validates the configuration, binds components, and
executes the workflow. The resulting Agent can run independently or in a
benchmark. [AgentGraph guide](docs/agent-graph.md) · [Component extensions](docs/external-components.md)

### Build and evaluate tasks

Define task instructions, environment setup, and evaluation rules in JSON, then
reuse plugins to prepare tasks and check outcomes. ZhiXing-Bench schedules tasks,
invokes the Agent, and produces reports and Replay; evaluation rules determine
task success. [Benchmark guide](docs/benchmark-architecture.md) · [Task authoring](docs/benchmark-authoring.md)

## Quick start

Prepare Python 3.10+, ADB, an unlocked Android phone or emulator, and an API key
for a model that supports image inputs. For a physical phone, enable USB
debugging and authorize the computer. See [device setup](docs/device_setup.md).

### 1. Install

```bash
git clone https://github.com/apbocldueo/unimobile.git
cd unimobile
python -m pip install -e ".[openai]"
cp secrets.example.yaml secrets.local.yaml
```

### 2. Configure the model

Edit `secrets.local.yaml` with your API key and endpoint:

```yaml
api_key: "YOUR_API_KEY"
base_url: "https://your-model-provider/v1"
```

Set the `model` field in [`builtin_android_agent.yaml`](examples/graphs/builtin_android_agent.yaml)
to an image-capable model available from your endpoint. The example's default
value is `gpt-4o`.

### 3. Connect a device and run

```bash
adb devices
```

Confirm that the device is listed with status `device`. Replace `emulator-5554`
below with its device ID:

```bash
zhixing run \
  --agent examples/graphs/builtin_android_agent.yaml \
  --instruction "Open the camera and take a photo, then finish the task" \
  --serial emulator-5554 \
  --secrets secrets.local.yaml \
  --artifact-root temp/runs
```

Watch the Agent operate the phone. When the run ends, the terminal prints its
status and run ID; screenshots, action records, and the run manifest are saved under `temp/runs/`.
Change the instruction to try another task. See the
[Android runtime guide](docs/builtin-agentgraph-runtime.md) for more configuration.

## Examples and source map

| Explore | Entry point |
| --- | --- |
| AgentGraph construction | [Python example](examples/agent_graph_no_device.py), [graph definitions](examples/agent_graph/) |
| Runtime scheduling and feedback | [No-device execution](examples/agent_graph_runtime_no_device.py), [additional graph patterns](examples/generalized_agent_graph_no_device.py) |
| Mobile Agent workflows | [Graph-native YAML examples](examples/graphs/), [Python SDK examples](examples/sdk/) |
| Reusable external components | [Plugin example](examples/external_component_plugin/), [extension guide](docs/external-components.md) |
| Task construction | [Minimal Package](examples/benchmarks/minimal/), [dynamic tasks](examples/benchmarks/dynamic-task/) |
| Composable outcome checks | [Evaluation Tree example](examples/benchmarks/composite-evaluation/) |
| Paper mechanisms and verification | [Paper-to-code map and commands](docs/paper-artifact.md) |

Core implementation lives in [`zhixing/graph/`](zhixing/graph/),
[`zhixing/components/`](zhixing/components/), [`zhixing/runtime/`](zhixing/runtime/),
[`zhixing/benchmark/`](zhixing/benchmark/), and
[`zhixing/plugins/`](zhixing/plugins/). Device implementations live in
[`zhixing/devices/`](zhixing/devices/).

## Optional: ZhiXing Studio

Studio provides a visual workspace for Agent authoring, execution monitoring,
benchmark configuration, reports, and Replay. With Python dependencies installed
and Node.js 22.12+ available:

```bash
npm --prefix studio ci
python run_studio.py
```

The launcher opens `http://127.0.0.1:5173/` and stops both services on Ctrl+C.
Authoring is available before model and device setup; execution requires the
corresponding local configuration. See [local startup](docs/studio-local-startup.md).

## Released scope and reproducibility

This is the **core source release** accompanying the paper. It includes the
framework, retained Agent examples, tutorial Benchmark Packages, tests, and
Studio. The two canonical AndroidWorld JSON suites retain **116 unique task
definitions (81 + 35)**. Full task media Packages, app binaries, emulator images,
and the paper's complete experiment ledgers are not bundled, so the archive
alone is insufficient to execute all 116 tasks or reproduce the reported
experimental results.

As agreed for this release, Agent-SAMA, AndroidArena, V-Droid, and MobA ports
are withheld pending verified redistribution terms. VisionTasker's GPL source
integration is also outside this Apache core profile. See the
[paper artifact guide](docs/paper-artifact.md) and
[third-party notices](docs/third-party-notices.md) for the exact boundary.

ZhiXing is an alpha framework with offline, fake-device, and bounded Android
validation evidence. Broader Agent and device coverage requires further
validation. Structured trajectories support audit and manual failure
localization; third-party Python plugins run in the host process.

## Contributing and citation

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[CITATION.cff](CITATION.cff). ZhiXing core source is licensed under the
[Apache License 2.0](LICENSE); retained third-party code carries its own notices.
