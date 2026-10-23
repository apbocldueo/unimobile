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

### ZhiXing: from Agent configuration to execution

1. **Build and check an AgentGraph.** Python SDK definitions and graph-native
   YAML describe component nodes, input/output ports, and data, control, and
   feedback connections. Validation checks component contracts, compatible
   ports, dependencies, and bounded feedback before binding. These checks need
   neither model calls nor device interactions.
2. **Bind components.** Resolve component references, create instances with the
   configured parameters and dependencies, and bind their interfaces to graph
   nodes. Components implement their own capabilities; graph connections specify
   how they work together.
3. **Run the executable Agent.** The Graph Runtime schedules ready nodes,
   propagates outputs, and handles bounded feedback. Observation and action
   execution pass through explicit device interfaces. The same execution path
   serves standalone tasks and benchmark runs.

See the [AgentGraph guide](docs/agent-graph.md),
[component extensions](docs/external-components.md), and
[Android runtime guide](docs/builtin-agentgraph-runtime.md). Existing
`AgentConfig` YAML and legacy execution entry points remain available.

### ZhiXing-Bench: from task definitions to evaluated results

1. **Load and check tasks.** A task declares its instruction, optional parameter
   generators, environment initialization, and evaluation rules. Validated
   definitions form the Task Library.
2. **Schedule and materialize instances.** Select tasks and create concrete
   `TaskInstance` inputs from their declared parameters. An independent
   `ExperimentProtocol` controls seeds, repeats, budgets, and environment rules.
3. **Set up and pre-check.** Prepare the task environment and capture any initial
   state needed by before-and-after checks.
4. **Invoke the Agent.** Run the constructed executable Agent on the task through
   its Graph Runtime and device interfaces.
5. **Evaluate and retain results.** An Evaluation Tree combines reusable Checkers
   using operators such as AND, OR, THRESHOLD, and WEIGHTED. Results, reports,
   structured trajectories, and Replay support inspection of the run.

Agent execution status and benchmark outcome are recorded separately: an Agent
finishing normally does not by itself establish task success. The legacy
`BenchmarkTask` JSON interface remains supported alongside Benchmark Packages
compiled to `BenchmarkPlan`.

See [benchmark architecture](docs/benchmark-architecture.md),
[task authoring](docs/benchmark-authoring.md), and
[running benchmarks](docs/benchmark-running.md).

## Quick start: no phone or API key

Requires Python 3.10+. While this release is under review, use the release branch:

```bash
git clone --branch codex/paper-core-release-20261023 https://github.com/apbocldueo/unimobile.git
cd unimobile
python -m pip install -e ".[openai,dev]"

# Construct, validate, bind, and execute an AgentGraph with fake components.
python examples/agent_graph_runtime_no_device.py

# Check a self-contained benchmark definition without executing it.
python -m zhixing.cli benchmark validate examples/benchmarks/minimal --json
```

The graph example prints node events, feedback, and a successful fake run
result. The benchmark command returns definition validation and identity
information. Neither command connects a phone or calls a model; these checks
do not establish Android task success.

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

## Run on Android

Set up a compatible device or emulator using the [device guide](docs/device_setup.md),
then configure a model endpoint and credentials locally:

```bash
cp secrets.example.yaml secrets.local.yaml
# Fill in secrets.local.yaml before running.
adb devices
zhixing run \
  --agent examples/graphs/builtin_android_agent.yaml \
  --instruction "Open the camera and take a photo, then finish the task" \
  --serial emulator-5554 \
  --secrets secrets.local.yaml
```

Replace the serial with your device's identifier. This command performs real
device actions and model calls; completion is not an independent benchmark
verdict. Configuration and further checks are described in the
[Android runtime guide](docs/builtin-agentgraph-runtime.md).

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
