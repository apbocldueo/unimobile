from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from zhixing.config.contracts import load_agent_yaml
from zhixing.config.contracts.common import ComponentReference, LLMReference
from zhixing.graph import (
    compile_agent_config,
    compile_graph_yaml_data,
    compile_studio_flow_document,
    load_graph_yaml,
)

from .helpers import make_golden_graph


ROOT = Path(__file__).resolve().parents[2]


def _studio_document() -> dict:
    graph = make_golden_graph()
    positions = {node.id: {"x": index * 100, "y": index * 10} for index, node in enumerate(graph.nodes)}
    nodes = []
    for node in graph.nodes:
        node_type = "ifelse" if node.id == "verified" else (node.role.value if node.role else node.kind.value)
        data = {"label": node.id, "icon": "x", "desc": "presentation", "ports": []}
        if node.component:
            candidate = node.component.candidates[0]
            data.update(
                selected_plugin_id=candidate.name,
                selected_plugin_namespace=candidate.namespace,
                plugin_params=candidate.params,
            )
        if node.predicate:
            data["predicate"] = node.predicate.model_dump(mode="json")
        nodes.append(
            {
                "nodeId": f"canvas-{node.id}",
                "logicalId": node.id,
                "nodeType": node_type,
                "position": positions[node.id],
                "data": data,
            }
        )
    edges = []
    for index, edge in enumerate(graph.edges):
        raw = {
            "edgeId": f"canvas-edge-{index}",
            "sourceNodeId": f"canvas-{edge.source.node}",
            "sourcePortId": edge.source.port,
            "targetNodeId": f"canvas-{edge.target.node}",
            "targetPortId": edge.target.port,
            "kind": edge.kind.value,
        }
        if edge.condition:
            raw["condition"] = edge.condition.model_dump(mode="json")
        if edge.feedback:
            raw["feedback"] = edge.feedback.model_dump(mode="json")
        edges.append(raw)
    return {
        "schemaVersion": 1,
        "contractVersion": "1.0",
        "flowId": "random-canvas-id",
        "flowName": "Golden flow",
        "createTime": 1,
        "updateTime": 2,
        "nodes": nodes,
        "edges": edges,
        "policies": graph.policies.model_dump(mode="json"),
    }


def test_python_yaml_and_studio_compile_to_same_canonical_graph():
    direct = make_golden_graph()
    yaml_result = load_graph_yaml(ROOT / "examples/agent_graph/agent_graph_v1.yaml")
    studio_result = compile_studio_flow_document(_studio_document())
    assert yaml_result.is_success, yaml_result.to_safe_dict()
    assert studio_result.is_success, studio_result.to_safe_dict()
    assert yaml_result.graph.canonical_mapping() == direct.canonical_mapping()
    assert studio_result.graph.canonical_mapping() == direct.canonical_mapping()
    assert {direct.canonical_hash(), yaml_result.graph.canonical_hash(), studio_result.graph.canonical_hash()} == {
        direct.canonical_hash()
    }


def test_studio_presentation_does_not_change_hash():
    document = _studio_document()
    expected = compile_studio_flow_document(document).graph.canonical_hash()
    changed = deepcopy(document)
    changed["flowId"] = "another-random-id"
    changed["flowName"] = "另一个标题"
    changed["updateTime"] = 99999
    changed["nodes"][0]["position"] = {"x": 999, "y": -42}
    assert compile_studio_flow_document(changed).graph.canonical_hash() == expected


def test_graph_yaml_requires_explicit_ids_for_duplicate_roles():
    graph = make_golden_graph().model_dump(mode="json", exclude_none=True)
    graph["kind"] = "agent_graph"
    reasoning = next(node for node in graph["nodes"] if node.get("role") == "reasoning")
    reasoning.pop("id")
    duplicate = deepcopy(reasoning)
    duplicate["component"]["candidates"][0]["name"] = "backup_reasoning"
    graph["nodes"].append(duplicate)
    result = compile_graph_yaml_data(graph)
    assert result.graph is None
    assert [item.code for item in result.diagnostics].count("graph.compile.logical_id_ambiguous") == 2


def test_studio_rejects_legacy_wildcard_and_verified_plan_edges():
    document = _studio_document()
    document["edges"][0]["dataType"] = "verifiedPlan"
    result = compile_studio_flow_document(document)
    assert result.graph is None
    assert any(item.code == "graph.studio.edge_migration_required" for item in result.diagnostics)


def test_modular_agent_config_compiles_without_changing_original_contract():
    config = load_agent_yaml(ROOT / "examples/agent_android_classic.yaml")
    before = config.canonical_dict()
    result = compile_agent_config(config)
    assert result.graph is not None
    assert result.is_success, result.to_safe_dict()
    assert config.canonical_dict() == before
    assert result.graph.metadata["source"] == "agent_config_v1"
    assert next(node for node in result.graph.nodes if node.id == "action_executor").component.candidates[0].name == "legacy_action_executor"


def test_unverified_agent_type_returns_stable_unsupported_diagnostic():
    config = load_agent_yaml(ROOT / "examples/agent_android_classic.yaml")
    result = compile_agent_config(config.model_copy(update={"agent_type": "reflection_agent"}))
    assert result.graph is None
    assert [item.code for item in result.diagnostics] == ["graph.compile.unsupported"]


def test_agent_config_optional_nodes_fallback_and_secret_dependencies_are_preserved():
    config = load_agent_yaml(ROOT / "examples/agent_android_classic.yaml")
    first = config.agent.components.perception
    backup = ComponentReference(name="backup_perception", params={"threshold": 0.5})
    components = config.agent.components.model_copy(
        update={"perception": [first, backup], "planner": None, "verifier": None}
    )
    default_llm = LLMReference(
        name="default_llm",
        params={"api_key": "${shared_api_key}", "model": "test-model"},
    )
    modified = config.model_copy(
        update={
            "global_config": config.global_config.model_copy(update={"default_llm": default_llm}),
            "agent": config.agent.model_copy(update={"components": components}),
        }
    )
    result = compile_agent_config(modified)
    assert result.is_success, result.to_safe_dict()
    ids = {node.id for node in result.graph.nodes}
    assert "planner" not in ids and "verifier" not in ids
    perception = next(node for node in result.graph.nodes if node.id == "perception")
    assert perception.component.policy.value == "fallback"
    assert [candidate.name for candidate in perception.component.candidates] == [first.name, "backup_perception"]
    memory = next(node for node in result.graph.nodes if node.id == "memory")
    assert memory.component.candidates[0].dependencies["llm"]["params"]["api_key"].secret_ref == "shared_api_key"
    assert "shared_api_key" in result.graph.canonical_json()


def test_device_runtime_requirements_do_not_change_agent_graph_hash():
    config = load_agent_yaml(ROOT / "examples/agent_android_classic.yaml")
    changed_device = config.device.model_copy(update={"params": {"language": "en", "serial": "another-device"}})
    changed = config.model_copy(update={"device": changed_device})
    assert compile_agent_config(config).graph.canonical_hash() == compile_agent_config(changed).graph.canonical_hash()
