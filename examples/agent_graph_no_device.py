"""Inspect one AgentGraph through Python, YAML, and Studio without a device."""

from pathlib import Path

from zhixing.graph import AgentGraph, GraphEdge, PortAddress, compile_studio_flow_document, load_graph_yaml


ROOT = Path(__file__).resolve().parent


def studio_document(graph: AgentGraph) -> dict:
    nodes = []
    for index, node in enumerate(graph.nodes):
        node_type = "ifelse" if node.kind.value == "condition" else (node.role.value if node.role else node.kind.value)
        data = {"label": node.id, "icon": "", "desc": "", "ports": []}
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
                "nodeId": f"canvas-{index}",
                "logicalId": node.id,
                "nodeType": node_type,
                "position": {"x": index * 120, "y": 0},
                "data": data,
            }
        )
    canvas_id = {node.id: f"canvas-{index}" for index, node in enumerate(graph.nodes)}
    edges = []
    for index, edge in enumerate(graph.edges):
        item = {
            "edgeId": f"edge-{index}",
            "sourceNodeId": canvas_id[edge.source.node],
            "sourcePortId": edge.source.port,
            "targetNodeId": canvas_id[edge.target.node],
            "targetPortId": edge.target.port,
            "kind": edge.kind.value,
        }
        if edge.feedback:
            item["feedback"] = edge.feedback.model_dump(mode="json")
        edges.append(item)
    return {
        "schemaVersion": 1,
        "contractVersion": graph.contract_version,
        "flowId": "presentation-only",
        "flowName": "No-device example",
        "nodes": nodes,
        "edges": edges,
        "policies": graph.policies.model_dump(mode="json"),
    }


def main() -> None:
    yaml_result = load_graph_yaml(ROOT / "agent_graph/agent_graph_v1.yaml")
    if not yaml_result.is_success:
        raise RuntimeError(yaml_result.to_safe_dict())

    # Python authoring uses the public strict model; this round-trip intentionally
    # excludes YAML parsing from the model/validator/hash operations below.
    python_graph = AgentGraph.model_validate(yaml_result.graph.model_dump(mode="python"))
    studio_result = compile_studio_flow_document(studio_document(python_graph))
    if not studio_result.is_success:
        raise RuntimeError(studio_result.to_safe_dict())

    hashes = {
        "python": python_graph.canonical_hash(),
        "yaml": yaml_result.graph.canonical_hash(),
        "studio": studio_result.graph.canonical_hash(),
    }
    print(hashes)
    assert len(set(hashes.values())) == 1

    invalid = python_graph.model_copy(
        update={
            "edges": python_graph.edges
            + (
                GraphEdge(
                    source=PortAddress(node="reasoning", port="action"),
                    target=PortAddress(node="planner", port="task"),
                    kind="data",
                ),
            )
        }
    )
    print(invalid.validate_graph().to_safe_dict())


if __name__ == "__main__":
    main()
