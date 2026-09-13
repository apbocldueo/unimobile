# ZhiXing external Benchmark Package example

This directory is an independently buildable Python distribution. It exposes a
small declarative photo task through the standard `zhixing.benchmarks` Entry
Point and uses only public ZhiXing Benchmark contracts.

```bash
python -m build --wheel
python -m pip install dist/zhixing_photo_smoke_benchmark-1.0.0-py3-none-any.whl
zhixing benchmark list --json
zhixing benchmark info example/photo-smoke@1.0.0 --json
zhixing benchmark validate example/photo-smoke@1.0.0 --json
```

The list and info paths read distribution metadata and packaged resources
without importing this module or connecting a device. A real run still requires
an explicit Android serial and an AgentGraph:

```bash
zhixing benchmark run example/photo-smoke@1.0.0 \
  --task PhotoSmoke_1 \
  --agent verified=examples/graphs/android_content_verified_agent.yaml \
  --serial emulator-5554 \
  --artifact-root temp/benchmark-runs/android-acceptance/external-package
```

This fixture validates distribution, Catalog, compilation, and unified Runtime
boundaries. One successful emulator run does not establish support for every
device, camera application, Benchmark Package, or AgentGraph.
