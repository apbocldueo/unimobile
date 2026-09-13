# Python package build and installation

ZhiXing is packaged as the `zhixing` distribution and imported as `zhixing`.
Version 0.1.0 supports Python 3.10 and newer. `pyproject.toml` is the source of
truth for build metadata and dependency profiles.

## Build and verify

From a development installation, build both artifacts and validate their
metadata:

```bash
python -m pip install -e ".[dev]"
python -m build
python -m twine check dist/*
```

The expected wheel is `dist/zhixing-0.1.0-py3-none-any.whl`. Test the actual
artifact from an unrelated directory and virtual environment rather than
relying on the repository being importable:

```bash
python -m venv /tmp/zhixing-wheel-check
/tmp/zhixing-wheel-check/bin/python -m pip install \
  dist/zhixing-0.1.0-py3-none-any.whl
cd /tmp
/tmp/zhixing-wheel-check/bin/python -c \
  "import zhixing; print(zhixing.__version__, zhixing.__file__)"
```

These commands establish local wheel readiness. Publishing that wheel to PyPI
is a separate release operation and is not part of this repository change.

## Dependency profiles

The base installation contains Pydantic, PyYAML, and Pillow. It supports the
stable root import, Agent YAML and Benchmark JSON validation, and packaged
resource access without importing model, vision, or device stacks.

- `openai` installs OpenAI-compatible model support.
- `vision` installs NumPy, OpenCV, Requests, Torch, and Transformers.
- `harmony` installs the HarmonyOS driver.
- `benchmark` installs Benchmark-only clipboard support.
- `all` is the union of supported runtime extras.
- `dev` contains build and test tools and is not a runtime requirement.

Plugin discovery isolates missing optional dependencies: an unavailable plugin
is reported as a sanitized module failure while unrelated built-in plugins can
still register. Selecting a component still requires installing its matching
extra.

## Package resources

Built-in prompts are read from `zhixing.prompts` with `importlib.resources`, so
they work in wheels and do not depend on the current working directory. A
caller may pass an explicit path to an existing prompt file; that file takes
precedence over the packaged prompt. Otherwise the value must be a packaged
prompt name. Missing names fail deterministically and ZhiXing does not search
arbitrary cwd-relative package directories.

The wheel and source distribution include the Python packages, all built-in
prompts, the retained Studio registry/template metadata, the license, README,
and packaging metadata. They intentionally exclude datasets, examples, tests,
OpenSpec planning artifacts, secrets and environment files, frontend
dependencies, caches, logs, screenshots, and generated outputs.

## Configuration compatibility

Installation does not replace the configuration interfaces. Agent assembly
continues to use `AgentConfig` YAML, while evaluation continues to use canonical
`BenchmarkTask`/`BenchmarkSuite` JSON. The formats are deliberately distinct:

```python
from zhixing.config.contracts import load_agent_yaml, load_benchmark_json

agent_config = load_agent_yaml("agent.yaml")
benchmark_suite = load_benchmark_json("benchmark.json")
```
