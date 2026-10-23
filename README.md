# ZhiXing

**Build, run, and evaluate Mobile Agents with reusable AgentGraphs and auditable experiments.**

[中文说明](README_CN.md) · [Documentation](docs/project-overview.md) · [Examples](examples) · [Studio](docs/studio-roadmap.md)

For the paper's implementation map, offline checks, task-data boundary and
withheld upstream integrations, start with the [paper artifact guide](docs/paper-artifact.md).
This is the core source profile; it does not bundle a complete reproduction of
the paper's experimental results. See [third-party notices](docs/third-party-notices.md).

ZhiXing separates three things that are often hard-wired together: how an Agent
works, what a task means, and the conditions under which it is evaluated. Define
them independently, run them together, and keep the evidence needed to inspect
the outcome.

## Quick start

ZhiXing requires Python 3.10+.

```bash
git clone https://github.com/apbocldueo/unimobile.git
cd unimobile
python -m pip install -e ".[openai,dev]"

# Run without a device or API key.
python examples/agent_graph_runtime_no_device.py
```

The no-device example validates graph construction and deterministic runtime
behavior. It does not connect a phone or resolve model credentials.

## What you can do

- **Build Agents** with Python, graph-native YAML, or ZhiXing Studio. Each
  authoring surface compiles to an `AgentGraph`.
- **Run controlled benchmarks** by combining an AgentGraph with a
  `BenchmarkPlan` and `ExperimentProtocol`.
- **Inspect evidence** through separate Agent status and Benchmark outcome,
  plus reports, structured trajectories, Replay, and verifiable bundles.

## How it works

![ZhiXing four-stage architecture: author AgentGraphs, bind independent benchmark and protocol definitions, execute through explicit device boundaries, then retain outcomes and artifacts.](docs/assets/zhixing-architecture-overview.png)

1. **Author** an `AgentGraph` using the Python SDK, graph-native YAML, or Studio.
2. **Bind** it to an independent BenchmarkPlan and ExperimentProtocol.
3. **Execute** through explicit `ObservationProvider` and `ActionExecutor` device boundaries.
4. **Inspect** the Agent status, external task verdict, and retained artifacts.

`AgentGraph` defines Agent behavior; `BenchmarkPlan` defines task setup and
evaluation; `ExperimentProtocol` fixes seeds, repeats, budgets, and device
constraints. Changing one does not silently rewrite the others.

## Next steps

| I want to… | Start here |
| --- | --- |
| Learn the core architecture | [Project overview](docs/project-overview.md) |
| Write an AgentGraph | [AgentGraph guide](docs/agent-graph.md) |
| Connect an Android device | [Device setup](docs/device_setup.md) |
| Run a built-in Android graph | [Android runtime guide](docs/builtin-agentgraph-runtime.md) |
| Create or run a benchmark | [Benchmark architecture](docs/benchmark-architecture.md) |
| Use the visual workspace | [Studio roadmap](docs/studio-roadmap.md) |
| Prepare backend for open source | [Backend open-source roadmap](docs/backend-open-source-roadmap.md) |
| See runnable definitions | [Examples](examples) |

### Start Studio

```bash
# Once, after installing Python dependencies (Node.js 22.12+ required)
npm --prefix studio ci

# Daily startup from the repository root
python run_studio.py
```

The launcher starts both services, opens `http://127.0.0.1:5173/`, and stops its
children on Ctrl+C. It loads `secrets.local.yaml` (preferred) or `secrets.yaml`,
and `studio/device-profiles.json` when present. Missing configuration permits
authoring; running an Agent still requires its model and device configuration.
Use `--check` for startup checks or `--no-browser` to keep browser opening manual.
The separate `python -m zhixing.studio` backend entry remains available.
See [local startup](docs/studio-local-startup.md) for overrides and troubleshooting.

### Run an Android example

```bash
cp secrets.example.yaml secrets.local.yaml
adb devices
zhixing run \
  --agent examples/graphs/builtin_android_agent.yaml \
  --serial emulator-5554 \
  --secrets secrets.local.yaml
```

Replace the example serial and secret values locally. Do not commit credentials
or real device profiles.

## Scope

ZhiXing is an alpha research and engineering framework with verified fake-device
and bounded Android evidence. It does not claim support for arbitrary Agent
paradigms, arbitrary Android tasks, broad device compatibility, automatic failure
diagnosis, or secure sandboxing of arbitrary third-party plugins.

For detailed validation commands, packaging, public-source release, contribution,
security, and citation guidance, see [the documentation](docs/project-overview.md),
[CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[CITATION.cff](CITATION.cff).

ZhiXing source code is licensed under the [Apache License 2.0](LICENSE).
