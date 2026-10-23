# Paper artifact: ZhiXing core

This source profile accompanies **ZhiXing: A Unified Framework for Building and
Benchmarking Mobile GUI Agents**. It provides the framework and examples needed
to inspect its construction and benchmarking mechanisms. The commands below
separate offline verification from experiments that require Android and models.

## Map the paper to code

| Paper mechanism | Source | Starting example or test |
| --- | --- | --- |
| AgentGraph construction and validation | `zhixing/graph/`, `zhixing/components/` | `examples/agent_graph_no_device.py`, `tests/graph/` |
| Reference resolution and component binding | `zhixing/catalog/`, `zhixing/runtime/binding.py` | `examples/external_component_plugin/`, `tests/catalog/` |
| Scheduling, port delivery and bounded feedback | `zhixing/runtime/` | `examples/agent_graph_runtime_no_device.py`, `examples/generalized_agent_graph_no_device.py` |
| Mobile observation and action boundaries | `zhixing/devices/`, `zhixing/runtime/android.py` | `examples/graphs/builtin_android_agent.yaml` |
| Declarative task definitions | `examples/benchmark_v1/`, `zhixing/benchmark/compiler/` | `examples/benchmarks/minimal/` |
| Parameter generation and environment initialization | `zhixing/plugins/benchmark/task/`, `zhixing/plugins/benchmark/environment/` | `examples/benchmarks/dynamic-task/` |
| Evaluation Tree and outcome reporting | `zhixing/benchmark/evaluation/`, `zhixing/benchmark/reporting/`, `zhixing/plugins/benchmark/evaluator/` | `examples/benchmarks/composite-evaluation/`, `tests/benchmark/` |
| Experiment control | `zhixing/benchmark/contracts/`, `zhixing/benchmark/runtime/` | `examples/benchmarks/default_protocol.yaml` |
| Optional authoring, monitoring and Replay UI | `zhixing/studio/`, `studio/` | [Local Studio startup](studio-local-startup.md) |

The legacy `AgentConfig` YAML and `BenchmarkTask` JSON interfaces remain
available. An Agent's execution status and an externally evaluated Benchmark
outcome are separate facts.

## Verify without a phone or API key

From the repository root, using Python 3.10 or newer:

```bash
python -m pip install -e ".[dev,openai,harmony,m3a,androidgen,guiexplorer]"
# CPU tensor tests do not load model checkpoints.
if [ "$(uname -s)" = "Linux" ]; then
  python -m pip install 'torch>=2.1,<3' --index-url https://download.pytorch.org/whl/cpu
else
  python -m pip install 'torch>=2.1,<3'
fi
python -m pip install -e ".[androidgen-retrieval]"
python examples/agent_graph_runtime_no_device.py
python examples/generalized_agent_graph_no_device.py
python -m zhixing.cli benchmark validate examples/benchmarks/minimal --json
python -m pytest tests -q -m "not real_android_acceptance" --ignore=tests/packaging
```

The examples use deterministic in-process fixtures. They establish graph and
runtime behavior, not model quality or Android task success. Test results must
retain the counts of passed, skipped and deselected checks.

## Task definitions and data boundary

`examples/benchmark_v1/android_world.json` contains 81 unique task definitions;
`android_world_missing.json` contains 35. Their combined 116 IDs are unique.
They are ZhiXing's retained declarative definitions, not an assertion that the
upstream benchmark implementation or every app state has been reproduced.

This core release does not distribute the upstream AndroidWorld/AppAgent media
Packages, app binaries, emulator image, experiment screenshots or private model
responses. Some definitions refer to such resources. Use the complete local
Packages only after reviewing their provenance, setting up the required Android
environment, and providing the expected resources. Do not infer that all 116
tasks can run from the source archive alone. The self-contained tutorial
Packages under `examples/benchmarks/` remain usable for definition validation.

## Agent examples and paper experiments

The graph-native examples under `examples/graphs/` expose configurations for
the retained Agent workflows, including Mobile-Agent, MobileUse, AppAgent,
GUICourse, ShowUI, OS-Genesis and UGround. Some require separately installed model
servers or optional Python dependencies. Their presence does not establish
behavioral equivalence or task success rates.

Agent-SAMA, AndroidArena, V-Droid and MobA ports are withheld from this profile
pending verified redistribution terms. VisionTasker's GPL source integration is
also outside this Apache core profile. Their source fixtures and online entry
points are withheld with them. Framework-authored contract identifiers may
remain reserved; an identifier is not an installed implementation. See
[third-party notices](third-party-notices.md).

The paper's code-reduction, original-versus-port success rates and five-model
comparison are reported research results. This release does not certify their
reproduction: frozen baseline inventories, counting scripts, full experiment
protocols and per-task result ledgers have not been included as a complete
reproduction package. Do not substitute the current examples or this release's
offline tests for that evidence.

## Android and Studio

See [device setup](device_setup.md), [built-in Android graph](builtin-agentgraph-runtime.md)
and [benchmark running](benchmark-running.md) before executing real device
actions. Models, credentials, device selection, compatible app versions and
task resources must be configured locally.

The Core experiment runtime and the Studio worker have different cardinality
boundaries: Studio currently accepts one Agent, one Task and one repeat per
Experiment. Fake-device matrices are not evidence of broad Android compatibility.
