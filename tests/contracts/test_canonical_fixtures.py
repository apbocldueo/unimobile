from pathlib import Path

import pytest

from zhixing.config.contracts import load_agent_yaml, load_benchmark_json


ROOT = Path(__file__).resolve().parents[2]


def _files(pattern: str):
    paths = sorted(ROOT.glob(pattern))
    assert paths, f"no canonical files found for {pattern}"
    return paths


@pytest.mark.parametrize("path", _files("examples/*.yaml"), ids=lambda path: path.name)
def test_retained_agent_yaml_matches_v1_contract(path):
    config = load_agent_yaml(path)
    assert config.schema_version == 1


@pytest.mark.parametrize(
    "path", _files("examples/benchmark_v1/*.json"), ids=lambda path: path.name
)
def test_canonical_benchmark_json_matches_v1_contract(path):
    suite = load_benchmark_json(path)
    assert suite.root
