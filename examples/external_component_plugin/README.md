# ZhiXing external component example

This directory is a standalone Python distribution. It uses only public
ZhiXing APIs and can be copied into its own Git repository.

## Start from a clean environment

Install the ZhiXing core before installing this standalone plugin. During local
core development, use the absolute path to a built core wheel; after a release,
the equivalent pinned package requirement may be installed from your package
index.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip build
python -m pip install /absolute/path/to/zhixing-0.1.0-py3-none-any.whl
python -m pip install -e '.[test]'
python -m pytest -q
zhixing components list
zhixing components inspect example.external:run_labeler@1.0.0
zhixing components doctor --plugin-provider zhixing-example
python sdk_example.py
```

`components doctor` is a default-safe structural/compatibility check. If an
invocation needs an explicit fixture, its output is `structural-only` and lists
the skipped check; successful doctor exit does not prove invocation behavior or
algorithm quality. The plugin-owned pytest suite supplies explicit fake input
and `RuntimeContext` fixtures for invocation.

`sdk_example.py` compiles equivalent YAML and Python SDK AgentGraphs, verifies
their canonical hashes, and separately binds and executes both definitions
through the installed Catalog with fake `RuntimeContext` instances. The two
paths must return the same result and each emit `start` and `complete` for the
external node.

## Build and install

```bash
python -m build --wheel
python -m pip install dist/zhixing_example_components-1.0.0-py3-none-any.whl
```

A Git repository uses the same standard Python path:

```bash
python -m pip install \
  'zhixing-example-components @ git+https://github.com/you/plugin.git@<commit>'
```

ZhiXing does not download an uninstalled GitHub URL itself. Installing and
loading a Python plugin trusts its imports and component construction to
execute in the current process. Discovery and `components doctor` are not a
security sandbox. This example validates packaging, discovery, AgentGraph
binding, and fake-runtime execution, not real Android behavior or component
algorithm quality.
