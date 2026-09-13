# ZhiXing

**A backend-first framework for composing, running, and evaluating Mobile Agents.**

[中文说明](README_CN.md) · [Project overview](docs/project-overview.md) ·
[AgentGraph](docs/agent-graph.md) · [Benchmark architecture](docs/benchmark-architecture.md)

ZhiXing provides explicit contracts for Mobile Agent construction, graph
execution, device effects, and benchmark evaluation. Python APIs, graph-native
YAML, and Studio authoring compile to AgentGraph. Legacy AgentConfig YAML remains
available as a compatibility path, while BenchmarkTask JSON stays an independent
task-initialization and evaluation contract.

ZhiXing is currently an alpha research and engineering framework. The repository
contains verified fake-device and bounded Android evidence, but it does not claim
support for arbitrary Agent paradigms, arbitrary Android tasks, broad device
compatibility, automatic failure diagnosis, or secure sandboxing of arbitrary
third-party plugins.

## Core model

```text
Agent authoring                         Benchmarking
Python / YAML / Studio                  BenchmarkTask / Package / Protocol
          │                                           │
          ▼                                           ▼
      AgentGraph                              Benchmark plan
          │                                           │
          └──────── Graph Runtime + explicit device boundaries ────────┘
                                  │
                                  ▼
                    events, trajectories, reports, Replay
```

- **AgentGraph** is the presentation-independent semantic representation.
- **AgentConfig YAML** defines how a legacy-compatible Agent is assembled.
- **BenchmarkTask JSON** defines task initialization and evaluation independently
  from Agent construction.
- **ObservationProvider** and **ActionExecutor** are explicit device-side-effect
  boundaries.
- Structured trajectories support audit and manual failure localization; they do
  not establish automatic root-cause diagnosis.

## Install

ZhiXing requires Python 3.10 or newer.

```bash
python -m pip install -e ".[dev]"
python -c "import zhixing; print(zhixing.__version__)"
```

Optional extras are available for OpenAI-compatible models, vision components,
HarmonyOS integration, and Benchmark clipboard support:

```bash
python -m pip install -e ".[openai]"
python -m pip install -e ".[vision]"
python -m pip install -e ".[harmony]"
python -m pip install -e ".[benchmark]"
```

The repository does not claim that version `0.1.0` is published on PyPI. Build
and validate local artifacts with:

```bash
python -m build
python -m twine check dist/*
```

## Quick starts

### Run a no-device AgentGraph example

```bash
python examples/agent_graph_runtime_no_device.py
python examples/generalized_agent_graph_no_device.py
```

These examples exercise graph construction and deterministic runtime behavior
without connecting to a phone or resolving model credentials.

### Inspect the two configuration contracts

```python
from zhixing.config.contracts import load_agent_yaml, load_benchmark_json

agent = load_agent_yaml("examples/agent_android_classic.yaml")
benchmark = load_benchmark_json("examples/benchmark_v1/app_agent.json")
```

The two values remain independent. Loading or validating them does not connect a
device, instantiate plugins, resolve secrets, or call a model.

### Run on Android

Copy the safe example to a local ignored file:

```bash
cp secrets.example.yaml secrets.local.yaml
adb devices
zhixing run \
  --agent examples/graphs/builtin_android_agent.yaml \
  --serial emulator-5554 \
  --secrets secrets.local.yaml
```

Replace the example device serial and secret values locally. Do not commit local
credentials or device profiles. See [device setup](docs/device_setup.md) and the
[built-in Android Graph Runtime guide](docs/builtin-agentgraph-runtime.md).

### Start Studio

Backend:

```bash
python -m zhixing.studio
```

Frontend, in another terminal:

```bash
cd studio
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/`. The current Studio includes Agent authoring,
durable Run and Replay surfaces, and the implemented Stage 5 Benchmark workflow.
Verified scope and remaining limitations are recorded in
[the Studio roadmap](docs/studio-roadmap.md), not inferred from UI presence.

## Repository layout

| Path | Purpose |
| --- | --- |
| `zhixing/graph` | AgentGraph contracts, compilers, validation, and identity |
| `zhixing/runtime` | Generic graph execution and binding |
| `zhixing/devices` | Android and HarmonyOS device implementations |
| `zhixing/benchmark` | Benchmark contracts, scheduling, evaluation, and reports |
| `zhixing/studio` | Studio backend resources and services |
| `zhixing/plugins` | Runtime Agent, Benchmark, and model plugins |
| `studio` | React Studio frontend |
| `examples` | Python, YAML, plugin, and Benchmark examples |
| `tests` | Unit, contract, fake-device, packaging, and bounded acceptance tests |
| `docs` | Architecture, contracts, usage, evidence, and limitations |

`zhixing/engine` is a compatibility surface still used by legacy entry points.
It is not removed until graph-native replacements pass explicit behavioral parity.

## Validation

Backend tests that do not require an explicitly authorized real device:

```bash
python -m pytest tests -q \
  -m "not real_android_acceptance" \
  --ignore=tests/packaging
```

Packaging:

```bash
python -m pytest tests/packaging -q
python -m build
python -m twine check dist/*
```

Studio:

```bash
cd studio
npm ci
npm test
npm run typecheck
npm run lint
npm run build
```

Real Android acceptance requires an explicitly selected device profile, task,
and credentials. Fake-device or browser-fixture evidence must not be presented as
real-device evidence.

## Public-source release

The development repository is not copied wholesale. Public source is selected
from Git-tracked files by `release/public-manifest.json`, checked for unsafe
paths and common credential signatures, and written with a checksummed inventory.

```bash
python scripts/build_public_release.py
python scripts/build_public_release.py --destination ../unimobile-public
```

The normal command requires a clean worktree and an empty destination outside the
source repository. See [the public release guide](docs/public-release.md).

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes. Report security
issues privately as described in [SECURITY.md](SECURITY.md); do not open a public
issue containing credentials, device identifiers, or exploit details.

## License and citation

ZhiXing source code is licensed under the [Apache License 2.0](LICENSE). Benchmark
datasets and media may have separate upstream terms and are not included in the
default public export until redistribution provenance is reviewed.

If you use ZhiXing in research, see [CITATION.cff](CITATION.cff).
