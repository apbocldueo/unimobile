from copy import deepcopy

import pytest

from zhixing.config.contracts import ContractValidationError, parse_agent_config


def _component(name, *, llm=False, **params):
    value = {"name": name, "params": params}
    if llm:
        value["llm"] = {
            "name": "openai_llm",
            "params": {"api_key": "${api_key}", "model": "gpt-4o"},
        }
    return value


def _base_agent():
    return {
        "schema_version": 1,
        "global_config": {"verbose": True},
        "agent_type": "modular_agent",
        "device": {"name": "android", "params": {"language": "cn"}},
        "agent": {
            "components": {
                "perception": _component("grid_perception"),
                "reasoning": _component("universal_reasoning", llm=True),
                "memory": _component("sliding_window_memory", window_size=6),
            }
        },
    }


@pytest.mark.parametrize("agent_type", ["modular_agent", "reflection_agent"])
def test_valid_modular_and_reflection(agent_type):
    raw = _base_agent()
    raw["agent_type"] = agent_type
    if agent_type == "reflection_agent":
        raw["agent"]["strategy"] = {"use_experience_cache": False}
    config = parse_agent_config(raw)
    assert config.agent_type == agent_type
    assert config.canonical_dict()["device"]["name"] == "android"


def test_valid_multi_agent_and_global_default_llm():
    raw = _base_agent()
    raw["agent_type"] = "multi_agent"
    raw["global_config"]["default_llm"] = {
        "name": "openai_llm",
        "params": {"api_key": "${api_key}", "model": "gpt-4o"},
    }
    raw["agent"]["strategy"] = {"manager_each_step": True, "use_experience_cache": False}
    raw["agent"]["components"]["reasoning"].pop("llm")
    raw["agent"]["components"]["planner"] = _component("universal_planner")
    config = parse_agent_config(raw)
    assert config.global_config.default_llm.params["api_key"] == "${api_key}"


def test_valid_uground_harmony_and_perception_fallback_order():
    raw = _base_agent()
    raw["agent_type"] = "uground_agent"
    raw["device"] = {"name": "harmony", "params": {}}
    raw["agent"]["strategy"] = {"summarize_steps": True}
    raw["agent"]["components"]["perception"] = [
        _component("screenshot_perception"),
        _component("grid_perception"),
    ]
    raw["agent"]["components"]["grounder"] = _component("uground_grounder", llm=True)
    config = parse_agent_config(raw)
    assert [item.name for item in config.agent.components.perception] == [
        "screenshot_perception",
        "grid_perception",
    ]


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    [
        (lambda raw: raw.pop("schema_version"), "schema_version"),
        (lambda raw: raw.update(schema_version=2), "schema_version"),
        (lambda raw: raw.pop("device"), "device"),
        (lambda raw: raw["agent"]["components"].pop("memory"), "agent.components.memory"),
        (lambda raw: raw["agent"]["components"].update(action={"name": "android_action"}), "agent.components.action"),
        (lambda raw: raw.update(unknown=True), "unknown"),
        (lambda raw: raw["agent"]["components"].update(reasoning=[_component("universal_reasoning", llm=True)]), "agent.components.reasoning"),
    ],
)
def test_invalid_agent_structure_has_precise_path(mutation, expected_path):
    raw = _base_agent()
    mutation(raw)
    with pytest.raises(ContractValidationError) as caught:
        parse_agent_config(raw)
    assert expected_path in str(caught.value)


def test_multi_agent_requires_planner():
    raw = _base_agent()
    raw["agent_type"] = "multi_agent"
    raw["agent"]["strategy"] = {"manager_each_step": True}
    with pytest.raises(ContractValidationError) as caught:
        parse_agent_config(raw)
    assert "agent.components.planner" in str(caught.value)


def test_uground_requires_grounder():
    raw = _base_agent()
    raw["agent_type"] = "uground_agent"
    with pytest.raises(ContractValidationError) as caught:
        parse_agent_config(raw)
    assert "agent.components.grounder" in str(caught.value)


def test_required_component_llm_is_not_silently_missing():
    raw = _base_agent()
    raw["agent"]["components"]["reasoning"].pop("llm")
    with pytest.raises(ContractValidationError) as caught:
        parse_agent_config(raw)
    assert "agent.components.reasoning.llm" in str(caught.value)


def test_strategy_rejects_unknown_flag():
    raw = _base_agent()
    raw["agent"]["strategy"] = {"typo_flag": True}
    with pytest.raises(ContractValidationError) as caught:
        parse_agent_config(raw)
    assert "agent.strategy.typo_flag" in str(caught.value)
