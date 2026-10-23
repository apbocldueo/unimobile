"""Behavioral contracts for concise, generic AgentGraph YAML authoring."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from zhixing.autodroid import build_autodroid_graph
from zhixing.graph import compile_agent_yaml, compile_graph_yaml_data, load_graph_yaml


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/graphs/autodroid_online.yaml"


def minimal_graph():
    """Provide an editable graph with no Agent-specific compilation path.

    Returns:
        dict: Source using ordinary core-role contracts and short connections.
    """
    return {
        "kind": "agent_graph", "schema_version": 1,
        "nodes": {
            "input": {"kind": "input"},
            "observe": {"component": "zhixing.runtime:device_observe",
                        "contract": {"id": "zhixing.service.device_observe", "version": "2.0"}},
            "perception": {"component": "agent.perception:screenshot_perception"},
            "output": {"kind": "output"},
        },
        "edges": ["input.value -> observe.request", "observe.observation -> perception.observation",
                  "perception.perception -> output.result"],
    }


def test_compact_defaults_equal_expanded_ir_and_do_not_mutate_source():
    """Preserve graph semantics when omitted defaults are made explicit.

    Raises:
        AssertionError: Defaults alter identity or input mappings are mutated.
    Returns:
        None.
    """
    source = minimal_graph()
    before = deepcopy(source)
    result = compile_graph_yaml_data(source)
    assert result.is_success, result.diagnostics
    assert source == before
    expanded = result.graph.model_dump(mode="json", exclude_none=True)
    expanded["kind"] = "agent_graph"
    legacy = compile_graph_yaml_data(expanded)
    assert legacy.is_success, legacy.diagnostics
    assert legacy.graph.canonical_hash() == result.graph.canonical_hash()
    assert result.graph.contract_version == "1.1"
    assert result.graph.policies.max_steps == 15
    changed = deepcopy(source)
    changed["nodes"]["perception"]["params"] = {"caption": "a different component configuration"}
    assert compile_graph_yaml_data(changed).graph.canonical_hash() != result.graph.canonical_hash()


def test_autodroid_example_preserves_exact_graph_and_nested_source_locations():
    """Preserve all loop, state, dependency, condition and budget semantics.

    Raises:
        AssertionError: Generic authoring changes the executable AutoDroid graph.
    Returns:
        None.
    """
    result = load_graph_yaml(EXAMPLE)
    assert result.is_success, result.diagnostics
    assert result.graph.canonical_hash() == build_autodroid_graph().canonical_hash()
    assert result.graph.canonical_hash() == "sha256:f6c3b3f89d6b005ce9c99269afa94f84166b286e05c3a8b9b29fbe90f1eb35fd"
    memory = next(entry for entry in result.source_map if entry.logical_node_path == ("online", "memory"))
    assert memory.property_path == ("nodes", "online", "loop", "body", "graph", "nodes", "memory")
    assert compile_agent_yaml(EXAMPLE).graph.canonical_hash() == result.graph.canonical_hash()


def test_compilation_does_not_load_agent_factory_components_devices_or_models():
    """Prove concise YAML compiles in a fresh interpreter without runtime imports.

    Raises:
        AssertionError: Compilation imports an Agent factory or runtime backend.
    Returns:
        None.
    """
    code = '''
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("zhixing.autodroid", "zhixing.plugins", "zhixing.devices", "torch", "openai", "InstructorEmbedding")):
            raise AssertionError("runtime import during compile: " + fullname)
sys.meta_path.insert(0, Guard())
from zhixing.graph import load_graph_yaml
result = load_graph_yaml(sys.argv[1])
assert result.is_success, result.diagnostics
'''
    run = subprocess.run([sys.executable, "-c", code, str(EXAMPLE)], cwd=ROOT,
                         capture_output=True, text=True, timeout=30, check=False)
    assert run.returncode == 0, run.stdout + run.stderr


@pytest.mark.parametrize("case,expected_path", [
    ("address", ("edges", 0, "source")),
    ("arrows", ("edges", 0)),
    ("node_value", ("nodes", "perception")),
    ("id", ("nodes", "perception", "id")),
    ("component", ("nodes", "perception", "component")),
    ("typo", ("nodes", "perception", "paramz")),
    ("bad_kind", ("nodes", "perception", "kind")),
])
def test_malformed_authoring_has_source_addressable_diagnostics(case, expected_path):
    """Reject malformed shorthand without exceptions or ignored typo fields.

    Args:
        case: Invalid authoring variation.
        expected_path: Corresponding author-visible error location.
    Raises:
        AssertionError: Invalid configuration is accepted or loses its location.
    Returns:
        None.
    """
    source = minimal_graph()
    node = source["nodes"]["perception"]
    if case == "address":
        source["edges"][0] = "missing.port -> observe.request"
    elif case == "arrows":
        source["edges"][0] = "input.value -> observe.request -> output.result"
    elif case == "node_value":
        source["nodes"]["perception"] = 42
    elif case == "id":
        node["id"] = "different"
    elif case == "component":
        node["component"] = "unqualified_name"
    elif case == "bad_kind":
        node["kind"] = []
    else:
        node["paramz"] = {"ignored_typo": True}
    result = compile_graph_yaml_data(source)
    assert not result.is_success
    assert result.graph is None
    assert any(item.path == expected_path for item in result.diagnostics), result.diagnostics


def test_port_validation_still_rejects_invalid_wiring():
    """Keep canonical port/type validation after short-edge expansion.

    Raises:
        AssertionError: A nonexistent port is treated as a valid connection.
    Returns:
        None.
    """
    source = minimal_graph()
    source["edges"][0] = "input.missing_port -> observe.request"
    result = compile_graph_yaml_data(source)
    assert not result.is_success
    assert any(item.port_id == "missing_port" for item in result.diagnostics)


def test_ambiguous_dotted_names_require_explicit_port_addresses():
    """Avoid guessing which dotted identifier denotes the node.

    Raises:
        AssertionError: An ambiguous short address is silently guessed.
    Returns:
        None.
    """
    source = minimal_graph()
    source["nodes"]["input.extra"] = {"kind": "input"}
    source["edges"][0] = "input.extra.value -> observe.request"
    result = compile_graph_yaml_data(source)
    assert any(item.code == "graph.yaml.compact_invalid" for item in result.diagnostics)
    source["edges"][0] = {"source": {"node": "input.extra", "port": "value"}, "target": "observe.request"}
    result = compile_graph_yaml_data(source)
    assert not any(item.code == "graph.yaml.compact_invalid" for item in result.diagnostics)
