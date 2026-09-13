from __future__ import annotations

import subprocess
import sys

import pytest
from pydantic import ValidationError

import zhixing
from zhixing.graph import (
    BUILTIN_PORTS,
    CORE_GRAPH_ROLES,
    ROLE_PORTS,
    BindingPolicy,
    ComponentBinding,
    DataTypeId,
    EdgeKind,
    FeedbackExhaustedPolicy,
    GraphComponentRef,
    GraphRole,
    NodeKind,
    NodeLifecycle,
    PredicateOperator,
    SecretRef,
    port_catalog_payload,
)


def test_stable_enum_values_and_root_exports():
    assert [item.value for item in CORE_GRAPH_ROLES] == [
        "perception",
        "planner",
        "reasoning",
        "memory",
        "action_executor",
        "verifier",
    ]
    assert [item.value for item in EdgeKind] == ["data", "control", "feedback"]
    assert [item.value for item in NodeLifecycle] == [
        "on_run_start",
        "per_step",
        "post_action",
        "stateful",
        "terminal",
    ]
    assert {item.value for item in PredicateOperator} >= {"eq", "truthy", "exists", "gte"}
    assert [item.value for item in FeedbackExhaustedPolicy] == ["fail", "continue", "terminate"]
    assert zhixing.__all__ == [
        "AgentConfig",
        "AgentGraphBuilder",
        "AgentRunConfig",
        "BenchmarkSuite",
        "BenchmarkTask",
        "ExecutableAgent",
        "ValidationIssue",
        "__version__",
        "compile_agent",
        "load_agent",
        "predicate",
    ]


def test_component_binding_and_secret_boundary():
    secret = SecretRef(secret_ref="openai_api_key")
    component = GraphComponentRef(
        namespace="agent.reasoning",
        name="reasoner",
        params={"api_key": secret, "temperature": 0.1},
    )
    binding = ComponentBinding(candidates=(component,))
    assert binding.policy == BindingPolicy.SINGLE

    with pytest.raises(ValidationError, match="resolved secret value"):
        GraphComponentRef(namespace="llm", name="bad", params={"api_key": "sk-live"})
    with pytest.raises(ValidationError, match="single binding"):
        ComponentBinding(candidates=(component, component))
    with pytest.raises(ValidationError, match="fallback binding"):
        ComponentBinding(policy=BindingPolicy.FALLBACK, candidates=(component,))


def test_port_catalog_is_complete_and_unique():
    assert set(ROLE_PORTS) == set(GraphRole)
    for ports in (*ROLE_PORTS.values(), *BUILTIN_PORTS.values()):
        ids = [port.id for port in ports]
        assert len(ids) == len(set(ids))
    assert DataTypeId.VERIFIER_RESULT in next(
        port.data_types for port in ROLE_PORTS[GraphRole.VERIFIER] if port.id == "result"
    )
    assert DataTypeId.ACTION_RESULT in next(
        port.data_types for port in ROLE_PORTS[GraphRole.ACTION_EXECUTOR] if port.id == "result"
    )
    payload = port_catalog_payload()
    assert payload["roles"]["perception"][0]["data_types"] == ["device_observation"]
    assert set(payload["builtins"]) == {NodeKind.INPUT.value, NodeKind.CONDITION.value, NodeKind.OUTPUT.value}


def test_graph_public_import_is_side_effect_free():
    script = r'''
import pathlib
import sys
before = set(pathlib.Path('.').iterdir())
import zhixing.graph
after = set(pathlib.Path('.').iterdir())
assert before == after
assert not any(name.startswith(('zhixing.plugins', 'zhixing.devices')) for name in sys.modules)
assert not any(name.split('.')[0] in {'torch', 'transformers', 'cv2', 'openai', 'hmdriver2'} for name in sys.modules)
'''
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
