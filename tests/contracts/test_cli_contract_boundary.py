import json
import sys

import pytest
import yaml

import run
from zhixing.config.contracts import ContractValidationError, load_agent_yaml, load_benchmark_json


def _valid_agent():
    return {
        "schema_version": 1,
        "agent_type": "modular_agent",
        "device": {"name": "android", "params": {}},
        "agent": {
            "components": {
                "perception": {"name": "grid_perception", "params": {}},
                "reasoning": {
                    "name": "universal_reasoning",
                    "params": {},
                    "llm": {"name": "openai_llm", "params": {"api_key": "${api_key}"}},
                },
                "memory": {"name": "sliding_window_memory", "params": {}},
            }
        },
    }


def _guard_runtime_side_effects(monkeypatch):
    called = {"bootstrap": 0, "factory": 0}

    def bootstrap():
        called["bootstrap"] += 1
        raise AssertionError("plugin bootstrap occurred before contract validation")

    def build(*args, **kwargs):
        called["factory"] += 1
        raise AssertionError("AgentFactory ran before contract validation")

    monkeypatch.setattr(run, "bootstrap_plugins", bootstrap)
    monkeypatch.setattr(run.AgentFactory, "build", build)
    monkeypatch.setattr(run, "setup_logging", lambda *args, **kwargs: None)
    return called


def test_invalid_agent_stops_before_plugin_or_agent_side_effects(tmp_path, monkeypatch):
    path = tmp_path / "invalid.yaml"
    path.write_text("agent_type: modular_agent\n", encoding="utf-8")
    called = _guard_runtime_side_effects(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["run.py", "--agent", str(path)])

    run.main()

    assert called == {"bootstrap": 0, "factory": 0}


def test_invalid_benchmark_stops_before_plugin_or_agent_side_effects(tmp_path, monkeypatch):
    agent_path = tmp_path / "agent.yaml"
    agent_path.write_text(yaml.safe_dump(_valid_agent(), sort_keys=False), encoding="utf-8")
    task_path = tmp_path / "tasks.json"
    task_path.write_text(json.dumps([{"id": "old", "task": "legacy"}]), encoding="utf-8")
    called = _guard_runtime_side_effects(monkeypatch)
    monkeypatch.setattr(
        sys, "argv", ["run.py", "--agent", str(agent_path), "--task", str(task_path)]
    )

    run.main()

    assert called == {"bootstrap": 0, "factory": 0}


def test_agent_and_benchmark_formats_are_not_interchangeable(tmp_path):
    agent_json = tmp_path / "agent.json"
    agent_json.write_text(json.dumps(_valid_agent()), encoding="utf-8")
    benchmark_yaml = tmp_path / "benchmark.yaml"
    benchmark_yaml.write_text("- id: task\n", encoding="utf-8")

    with pytest.raises(ContractValidationError, match="must be YAML"):
        load_agent_yaml(agent_json)
    with pytest.raises(ContractValidationError, match="must be JSON"):
        load_benchmark_json(benchmark_yaml)
