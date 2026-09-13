# Configuration contract development

ZhiXing supports Python 3.10 or newer. Agent definitions are YAML documents
validated as `AgentConfig`; benchmark suites are JSON arrays validated as
`BenchmarkSuite`. The formats are deliberately not interchangeable.

Install runtime and development dependencies, then run the contract tests:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/contracts -q
```

Contract-only tests never connect to Android/Harmony devices, execute benchmark
plugins, resolve secrets, or call language models.
