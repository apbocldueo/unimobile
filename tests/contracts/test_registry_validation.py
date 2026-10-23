from zhixing.config.contracts.agent import AgentConfig
from zhixing.config.contracts.benchmark import BenchmarkSuite
from zhixing.config.contracts.registry_validation import (
    validate_agent_registry,
    validate_benchmark_registry,
)
from zhixing.core.factory import PluginDiscoveryReport, PluginImportFailure


class NeverInstantiate:
    instances = 0

    def __init__(self, *args, **kwargs):
        type(self).instances += 1
        raise AssertionError("registry validation instantiated a plugin")


class NeedsLLM:
    instances = 0

    def __init__(self, llm_client):
        type(self).instances += 1
        raise AssertionError("registry validation instantiated a plugin")


def _registry():
    return {
        "agent.type": {"modular_agent": NeverInstantiate},
        "device": {"android": NeverInstantiate},
        "agent.perception": {"grid_perception": NeverInstantiate},
        "agent.reasoning": {"reason": NeedsLLM},
        "agent.memory": {"memory": NeverInstantiate},
        "llm": {"openai_llm": NeverInstantiate},
        "benchmark.task": {"random_string": NeverInstantiate},
        "benchmark.environment.reset": {"reset": NeverInstantiate},
        "evaluator.system_state": {"file_exist": NeverInstantiate},
        "evaluator.composite": {"AND": NeverInstantiate, "OR": NeverInstantiate, "SEQUENCE": NeverInstantiate},
    }


def _agent(reason_name="reason", with_llm=True):
    reason = {"name": reason_name, "params": {}}
    if with_llm:
        reason["llm"] = {"name": "openai_llm", "params": {}}
    return AgentConfig.model_validate(
        {
            "schema_version": 1,
            "agent_type": "modular_agent",
            "device": {"name": "android", "params": {}},
            "agent": {
                "components": {
                    "perception": {"name": "grid_perception", "params": {}},
                    "reasoning": reason,
                    "memory": {"name": "memory", "params": {}},
                }
            },
        }
    )


def _suite(env=None):
    return BenchmarkSuite.model_validate(
        [
            {
                "id": "one",
                "instruction": "Create ${name}",
                "type": "dynamic",
                "task_initializer": {"name": {"name": "random_string", "params": {}}},
                "environment_initializer": env or [{"name": "reset", "params": {}}],
                "evaluator": {
                    "name": "composite",
                    "params": {
                        "logic": "AND",
                        "rules": [
                            {"name": "system_state", "params": {"method": "file_exist"}}
                        ],
                    },
                },
            }
        ]
    )


def test_agent_registry_resolves_without_instantiation():
    NeverInstantiate.instances = NeedsLLM.instances = 0
    issues = validate_agent_registry(_agent(), registry=_registry())
    assert not [issue for issue in issues if issue.severity == "error"]
    assert NeverInstantiate.instances == NeedsLLM.instances == 0


def test_agent_registry_reports_wrong_namespace_and_required_llm():
    registry = _registry()
    registry["agent.memory"]["wrong_place"] = NeverInstantiate
    issues = validate_agent_registry(_agent("wrong_place", with_llm=False), registry=registry)
    assert any(issue.code == "registry.wrong_namespace" for issue in issues)

    issues = validate_agent_registry(_agent(with_llm=False), registry=registry)
    assert any(issue.code == "agent.llm.required" for issue in issues)


def test_discovery_failure_is_distinct_from_unknown_name():
    report = PluginDiscoveryReport(
        package="zhixing.plugins",
        imported_modules=(),
        failures=(PluginImportFailure("zhixing.plugins.bad", "ImportError", "missing optional dep"),),
    )
    issues = validate_agent_registry(
        _agent("missing"), registry=_registry(), discovery_reports=[report]
    )
    assert any(issue.code == "registry.unknown_plugin" for issue in issues)
    assert any(issue.code == "registry.discovery_incomplete" for issue in issues)


def test_benchmark_registry_resolves_without_instantiation():
    NeverInstantiate.instances = 0
    issues = validate_benchmark_registry(_suite(), registry=_registry())
    assert not [issue for issue in issues if issue.severity == "error"]
    assert NeverInstantiate.instances == 0


def test_benchmark_registry_reports_unknown_evaluator():
    registry = _registry()
    registry["evaluator.system_state"] = {}
    issues = validate_benchmark_registry(_suite(), registry=registry)
    assert any(issue.code == "registry.unknown_plugin" for issue in issues)


def test_environment_resolution_detects_ambiguity_and_accepts_category():
    registry = _registry()
    registry["benchmark.environment.setting"] = {"reset": NeverInstantiate}
    issues = validate_benchmark_registry(_suite(), registry=registry)
    assert any(issue.code == "registry.environment.ambiguous" for issue in issues)

    categorized = _suite(env=[{"name": "reset", "category": "reset", "params": {}}])
    issues = validate_benchmark_registry(categorized, registry=registry)
    assert not [issue for issue in issues if issue.severity == "error"]
