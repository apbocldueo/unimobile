"""Canonical projection, JSON and semantic identity for AgentGraph V1."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .models import AgentGraph, SecretRef, normalize_secret_placeholders
from .contracts import BUILTIN_NODE_CONTRACT_CATALOG
from .ports import contract_ports_for_node, ports_for_node


def _primitive(value: Any) -> Any:
    value = normalize_secret_placeholders(value)
    if isinstance(value, SecretRef):
        return {"secret_ref": value.secret_ref}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON does not permit NaN or Infinity")
        return 0.0 if value == 0 else value
    if isinstance(value, (list, tuple)):
        return [_primitive(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("canonical JSON object keys must be strings")
        return {key: _primitive(value[key]) for key in sorted(value)}
    if hasattr(value, "model_dump"):
        return _primitive(value.model_dump(mode="python", exclude_none=True))
    raise ValueError(f"canonical JSON cannot represent {type(value).__name__}")


def _component_mapping(binding) -> dict[str, Any]:
    return {
        "policy": binding.policy.value,
        "candidates": [
            {
                "namespace": candidate.namespace,
                "name": candidate.name,
                **({"version": candidate.version} if candidate.version is not None else {}),
                "params": _primitive(candidate.params),
                "dependencies": _primitive(candidate.dependencies),
            }
            for candidate in binding.candidates
        ],
    }


def _v11_subgraph_mapping(specification, *, contract_catalog, graph_catalog) -> dict[str, Any]:
    """Project one inline or referenced subgraph into semantic data.

    Args:
        specification (SubgraphSpec): Subgraph declaration to project.
        contract_catalog (NodeContractCatalog): Explicit contract catalog.
        graph_catalog (GraphCatalog | None): Explicit graph catalog.

    Raises:
        ValueError: An inline child graph is invalid.

    Returns:
        dict[str, Any]: Canonical subgraph declaration.
    """
    result = {
        "inputs": _primitive(specification.inputs),
        "outputs": _primitive(specification.outputs),
        "shared_state": list(specification.shared_state),
        "max_activations": specification.max_activations,
        "error_policy": specification.error_policy.value,
    }
    if specification.graph is not None:
        result["graph_hash"] = canonical_hash(
            specification.graph,
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
        )
    else:
        result["graph_hash"] = specification.reference.semantic_hash
    return result


def _v11_mapping(graph: AgentGraph, *, contract_catalog, graph_catalog) -> dict[str, Any]:
    """Project contract 1.1 graph semantics while excluding presentation/runtime data.

    Args:
        graph (AgentGraph): Validated contract 1.1 graph.
        contract_catalog (NodeContractCatalog): Explicit contract catalog.
        graph_catalog (GraphCatalog | None): Explicit graph catalog.

    Raises:
        ValueError: A nested graph cannot be canonicalized.

    Returns:
        dict[str, Any]: Canonical semantic mapping.
    """
    nodes: list[dict[str, Any]] = []
    for node in sorted(graph.nodes, key=lambda item: item.id):
        item: dict[str, Any] = {
            "id": node.id,
            "kind": node.kind.value,
            "lifecycle": node.lifecycle.value,
            "primary": node.primary,
            "ports": sorted(
                (port.model_dump(mode="python") for port in contract_ports_for_node(node, contract_catalog)),
                key=lambda port: str(port["id"]),
            ),
        }
        if node.role is not None:
            item["role"] = node.role.value
        if node.contract is not None:
            item["contract"] = _primitive(node.contract)
        if node.component is not None:
            item["component"] = _component_mapping(node.component)
        if node.predicate is not None:
            item["predicate"] = _primitive(node.predicate)
        if node.execution is not None:
            item["execution"] = _primitive(node.execution)
        if node.router is not None:
            item["router"] = _primitive(node.router)
        if node.state is not None:
            item["state"] = _primitive(node.state)
        if node.subgraph is not None:
            item["subgraph"] = _v11_subgraph_mapping(
                node.subgraph,
                contract_catalog=contract_catalog,
                graph_catalog=graph_catalog,
            )
        if node.loop is not None:
            item["loop"] = {
                "body": _v11_subgraph_mapping(
                    node.loop.body,
                    contract_catalog=contract_catalog,
                    graph_catalog=graph_catalog,
                ),
                "inputs": _primitive(node.loop.inputs),
                "outputs": _primitive(node.loop.outputs),
                "until": _primitive(node.loop.until),
                "max_iterations": node.loop.max_iterations,
                "on_exhausted": node.loop.on_exhausted.value,
                "max_activations": node.loop.max_activations,
            }
        nodes.append(item)
    edges = [
        {
            "source": {"node": edge.source.node, "port": edge.source.port},
            "target": {"node": edge.target.node, "port": edge.target.port},
            "kind": edge.kind.value,
            **({"condition": _primitive(edge.condition)} if edge.condition is not None else {}),
            **({"feedback": _primitive(edge.feedback)} if edge.feedback is not None else {}),
        }
        for edge in graph.edges
    ]
    edges.sort(
        key=lambda edge: json.dumps(
            edge,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )
    return _primitive(
        {
            "schema_version": graph.schema_version,
            "contract_version": graph.contract_version,
            "profile": graph.profile,
            "nodes": nodes,
            "edges": edges,
            "policies": graph.policies,
            **({"interface": graph.interface} if graph.interface is not None else {}),
        }
    )


def canonical_mapping(
    graph: AgentGraph,
    *,
    contract_catalog=None,
    graph_catalog=None,
) -> dict[str, Any]:
    """Return the stable semantic projection for V1 or contract 1.1.

    Args:
        graph (AgentGraph): Graph whose semantic identity is requested.
        contract_catalog (NodeContractCatalog | None): Explicit extension catalog.
        graph_catalog (GraphCatalog | None): Explicit subgraph catalog.

    Raises:
        ValueError: Graph validation fails.

    Returns:
        dict[str, Any]: Canonical semantic mapping.
    """
    validation = graph.validate_graph(
        contract_catalog=contract_catalog,
        graph_catalog=graph_catalog,
    )
    if not validation.is_valid:
        codes = ", ".join(item.code for item in validation.errors[:8])
        raise ValueError(f"cannot canonicalize invalid AgentGraph: {codes}")

    if graph.contract_version == "1.1":
        catalog = BUILTIN_NODE_CONTRACT_CATALOG
        if contract_catalog is not None:
            catalog = catalog.merge(contract_catalog)
        return _v11_mapping(
            graph,
            contract_catalog=catalog,
            graph_catalog=graph_catalog,
        )

    nodes: list[dict[str, Any]] = []
    for node in sorted(graph.nodes, key=lambda item: item.id):
        item: dict[str, Any] = {
            "id": node.id,
            "kind": node.kind.value,
            "lifecycle": node.lifecycle.value,
            "primary": node.primary,
            "ports": sorted(
                (port.to_dict() for port in ports_for_node(node)),
                key=lambda port: str(port["id"]),
            ),
        }
        if node.role is not None:
            item["role"] = node.role.value
        if node.component is not None:
            item["component"] = _component_mapping(node.component)
        if node.predicate is not None:
            item["predicate"] = _primitive(node.predicate)
        nodes.append(item)

    edges = [
        {
            "source": {"node": edge.source.node, "port": edge.source.port},
            "target": {"node": edge.target.node, "port": edge.target.port},
            "kind": edge.kind.value,
            **({"condition": _primitive(edge.condition)} if edge.condition is not None else {}),
            **({"feedback": _primitive(edge.feedback)} if edge.feedback is not None else {}),
        }
        for edge in graph.edges
    ]
    edges.sort(
        key=lambda edge: json.dumps(
            edge, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    )
    return _primitive(
        {
            "schema_version": graph.schema_version,
            "contract_version": graph.contract_version,
            "profile": graph.profile,
            "nodes": nodes,
            "edges": edges,
            "policies": graph.policies,
        }
    )


def canonical_json(graph: AgentGraph, *, contract_catalog=None, graph_catalog=None) -> str:
    """Serialize a graph's canonical semantic mapping.

    Args:
        graph (AgentGraph): Graph to serialize.
        contract_catalog (NodeContractCatalog | None): Explicit extension catalog.
        graph_catalog (GraphCatalog | None): Explicit subgraph catalog.

    Raises:
        ValueError: Canonicalization fails.

    Returns:
        str: Stable compact JSON.
    """
    return json.dumps(
        canonical_mapping(
            graph,
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(graph: AgentGraph, *, contract_catalog=None, graph_catalog=None) -> str:
    """Compute a SHA-256 semantic identity.

    Args:
        graph (AgentGraph): Graph to identify.
        contract_catalog (NodeContractCatalog | None): Explicit extension catalog.
        graph_catalog (GraphCatalog | None): Explicit subgraph catalog.

    Raises:
        ValueError: Canonicalization fails.

    Returns:
        str: ``sha256:``-prefixed digest.
    """
    digest = hashlib.sha256(
        canonical_json(
            graph,
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
        ).encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"
