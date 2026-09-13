"""Reusable Studio schema 2 fixtures derived from verified AgentGraph values."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from zhixing.graph import AgentGraph


def graph_with_exact_component_versions(graph: AgentGraph) -> AgentGraph:
    """Copy an AgentGraph and pin every component candidate recursively.

    Args:
        graph (AgentGraph): Source contract 1.1 graph.

    Raises:
        ValueError: The transformed graph violates AgentGraph contracts.

    Returns:
        AgentGraph: Equivalent graph with exact candidate versions.
    """
    raw = graph.model_dump(mode="json", exclude_none=True)

    def pin_graph(candidate: dict[str, Any]) -> None:
        """Pin component refs inside one raw graph and its inline children.

        Args:
            candidate (dict[str, Any]): Mutable copied graph mapping.

        Raises:
            None.

        Returns:
            None.
        """
        for node in candidate.get("nodes", []):
            component = node.get("component")
            if isinstance(component, dict):
                for reference in component.get("candidates", []):
                    reference.setdefault("version", "1.0.0")
            subgraph = node.get("subgraph")
            if isinstance(subgraph, dict) and isinstance(subgraph.get("graph"), dict):
                pin_graph(subgraph["graph"])
            loop = node.get("loop")
            if isinstance(loop, dict):
                body = loop.get("body")
                if isinstance(body, dict) and isinstance(body.get("graph"), dict):
                    pin_graph(body["graph"])

    pin_graph(raw)
    return AgentGraph.model_validate(raw)


def studio_document_from_graph(
    graph: AgentGraph,
    *,
    document_id: str = "fixture-document",
    agent_id: str = "fixture-agent",
) -> dict[str, Any]:
    """Project a contract 1.1 AgentGraph into schema 2 authoring JSON.

    Args:
        graph (AgentGraph): Exact-version graph.
        document_id (str): Stable Studio document identity.
        agent_id (str): Stable Agent identity.

    Raises:
        ValueError: Graph contains an unsupported non-1.1 declaration.

    Returns:
        dict[str, Any]: StudioFlowDocument mapping.
    """
    if graph.contract_version != "1.1":
        raise ValueError("fixture projection requires contract 1.1")

    def subgraph_mapping(specification: Any, suffix: str) -> dict[str, Any]:
        """Convert one Graph SubgraphSpec to authoring form.

        Args:
            specification (SubgraphSpec): Graph subgraph declaration.
            suffix (str): Stable nested identity suffix.

        Raises:
            ValueError: Declaration has no source.

        Returns:
            dict[str, Any]: Studio subgraph declaration.
        """
        common = {
            "inputs": dict(specification.inputs),
            "outputs": dict(specification.outputs),
            "shared_state": list(specification.shared_state),
            "max_activations": specification.max_activations,
            "error_policy": specification.error_policy.value,
        }
        if specification.reference is not None:
            return {
                **common,
                "reference": specification.reference.model_dump(mode="json"),
            }
        if specification.graph is None:
            raise ValueError("subgraph fixture requires graph or reference")
        return {
            **common,
            "document": studio_document_from_graph(
                specification.graph,
                document_id=f"{document_id}-{suffix}",
                agent_id=agent_id,
            ),
        }

    nodes: list[dict[str, Any]] = []
    presentation: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(graph.nodes):
        canvas_id = f"canvas-{node.id}"
        raw: dict[str, Any] = {
            "canvasId": canvas_id,
            "logicalId": node.id,
            "kind": node.kind.value,
            "lifecycle": node.lifecycle.value,
            "primary": node.primary,
            "metadata": deepcopy(node.metadata),
        }
        for field_name in (
            "role",
            "contract",
            "component",
            "predicate",
            "execution",
            "router",
            "state",
        ):
            value = getattr(node, field_name)
            if value is None:
                continue
            raw[field_name] = (
                value.value
                if field_name == "role"
                else value.model_dump(mode="json", exclude_none=True)
            )
        if node.subgraph is not None:
            raw["subgraph"] = subgraph_mapping(
                node.subgraph,
                f"{node.id}-subgraph",
            )
        if node.loop is not None:
            raw["loop"] = {
                "body": subgraph_mapping(
                    node.loop.body,
                    f"{node.id}-loop",
                ),
                "inputs": dict(node.loop.inputs),
                "outputs": dict(node.loop.outputs),
                "until": node.loop.until.model_dump(mode="json"),
                "max_iterations": node.loop.max_iterations,
                "on_exhausted": node.loop.on_exhausted.value,
                "max_activations": node.loop.max_activations,
            }
        nodes.append(raw)
        source_presentation = (
            graph.presentation.nodes.get(node.id)
            if graph.presentation is not None
            else None
        )
        presentation[canvas_id] = {
            "x": source_presentation.x if source_presentation else index * 180,
            "y": source_presentation.y if source_presentation else 0,
            "label": source_presentation.label if source_presentation else node.id,
            "icon": source_presentation.icon if source_presentation else "",
            "description": (
                source_presentation.description if source_presentation else ""
            ),
        }

    edges = [
        {
            "canvasId": f"edge-{index + 1}",
            "source": {
                "canvasId": f"canvas-{edge.source.node}",
                "portId": edge.source.port,
            },
            "target": {
                "canvasId": f"canvas-{edge.target.node}",
                "portId": edge.target.port,
            },
            "kind": edge.kind.value,
            **(
                {"condition": edge.condition.model_dump(mode="json")}
                if edge.condition is not None
                else {}
            ),
            **(
                {"feedback": edge.feedback.model_dump(mode="json")}
                if edge.feedback is not None
                else {}
            ),
        }
        for index, edge in enumerate(graph.edges)
    ]
    semantic: dict[str, Any] = {
        "profile": graph.profile,
        "policies": graph.policies.model_dump(mode="json"),
        "nodes": nodes,
        "edges": edges,
    }
    if graph.interface is not None:
        semantic["interface"] = graph.interface.model_dump(mode="json")
    return {
        "schemaVersion": 2,
        "contractVersion": "1.1",
        "documentId": document_id,
        "agentId": agent_id,
        "name": document_id,
        "semantic": semantic,
        "presentation": {
            "nodes": presentation,
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
        "authoring": {
            "description": "generated contract fixture",
            "createdAt": 0,
            "updatedAt": 0,
        },
    }


__all__ = ["graph_with_exact_component_versions", "studio_document_from_graph"]
