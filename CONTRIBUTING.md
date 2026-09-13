# Contributing to ZhiXing

Thank you for helping improve ZhiXing. Changes should preserve the separation
between Agent construction, AgentGraph execution, device effects, and Benchmark
task/evaluation contracts.

## Before opening a change

1. Read `docs/project-overview.md` and the architecture document for the area.
2. Use an OpenSpec change for new behavior, public contracts, persistence,
   architecture, or milestone-level work.
3. Do not silently change public imports, YAML/JSON contracts, canonical hashes,
   plugin identifiers, or legacy execution behavior.
4. Never commit credentials, device serials, local database files, trajectories,
   model responses, or generated frontend dependencies.

## Development setup

```bash
python -m pip install -e ".[dev]"
cd studio && npm ci
```

## Validation

Backend changes should run the smallest focused tests first, followed by:

```bash
python -m pytest tests -q \
  -m "not real_android_acceptance" \
  --ignore=tests/packaging
```

Frontend changes should run:

```bash
cd studio
npm test
npm run typecheck
npm run lint
npm run build
```

Packaging changes also require `tests/packaging`, `python -m build`, and
`python -m twine check dist/*`. Device-execution claims require the matching
fake-device or explicitly authorized real-device evidence; implementation alone
is not evidence.

## Pull requests

- Keep changes scoped and preserve unrelated work.
- Add or update tests for observable behavior.
- Document verified behavior and remaining limitations.
- Explain compatibility and migration impact.
- Confirm that `python scripts/build_public_release.py` accepts the committed
  release candidate.

By contributing, you agree that your contribution is licensed under the
repository's Apache License 2.0.
