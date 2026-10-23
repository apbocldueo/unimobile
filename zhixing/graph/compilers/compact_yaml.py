"""Expand concise graph YAML into the existing IR without loading components."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from ..diagnostics import CompilationResult, GraphDiagnostic, SourceMapEntry, sorted_diagnostics
from ..enums import GraphRole
from ..models import AgentGraph
from .common import diagnostics_from_validation_error, finish_compilation
from .machine_yaml import MachineAuthoringError, expand_machine


class _AuthoringError(ValueError):
    """Keep structural errors addressable without echoing configuration values."""

    def __init__(self, message: str, path: tuple[str | int, ...]) -> None:
        """Store a safe message and its source path.

        Args:
            message: Fixed structural error description.
            path: Location in the authoring document.
        Returns:
            None.
        """
        super().__init__(message)
        self.path = path


def _address(value: Any, ids: tuple[str, ...], path: tuple[str | int, ...]) -> Any:
    """Expand an unambiguous node.port reference, preserving explicit addresses.

    Args:
        value: Short reference or existing IR address object.
        ids: Declared node identifiers in this graph scope.
        path: Address location for errors.
    Raises:
        _AuthoringError: A short reference is missing or ambiguous.
    Returns:
        Any: Explicit address, later checked by the IR models and port validator.
    """
    if not isinstance(value, str):
        return value
    matches = [node for node in ids if value.startswith(node + ".")]
    if len(matches) != 1 or not value[len(matches[0]) + 1:]:
        raise _AuthoringError("use an unambiguous node.port or explicit node/port object", path)
    node = matches[0]
    return {"node": node, "port": value[len(node) + 1:]}


def _expand_graph(
    data: Mapping[str, Any], path: tuple[str | int, ...], source_id: str,
    source_map: list[SourceMapEntry], logical_path: tuple[str, ...] = (),
    *, ir_path: tuple[str | int, ...] = (), locations: dict | None = None,
) -> dict[str, Any]:
    """Expand named nodes, machine plumbing and short edges recursively.

    Args:
        data: Graph document with a named node mapping or legacy node array.
        path: Document path of this graph.
        source_id: Diagnostic source identifier.
        source_map: Collected source-to-IR locations.
        logical_path: Parent graph node path.
        ir_path: Numeric model path of this graph scope.
        locations: Optional IR-prefix to author-source path index for diagnostics.
    Raises:
        _AuthoringError: Shorthand is malformed or nesting exceeds 32 levels.
        MachineAuthoringError: A machine routing table is invalid.
    Returns:
        dict[str, Any]: Independent IR mapping with ordinary model defaults.
    """
    if len(logical_path) > 32:
        raise _AuthoringError("graph nesting exceeds 32 levels", path)
    raw = dict(data)
    node_origins, edge_origins = {}, []
    if "machine" in raw:
        raw, node_origins, edge_origins = expand_machine(raw, path)
    nodes = raw.get("nodes")
    if not isinstance(nodes, Mapping):
        return raw
    if any(not isinstance(node_id, str) for node_id in nodes):
        raise _AuthoringError("node names must be strings", path + ("nodes",))
    raw.setdefault("contract_version", "1.1")
    semantic_path = tuple(part for parent in logical_path for part in ("nodes", parent, "graph"))
    expanded = []
    for index, (node_id, declaration) in enumerate(nodes.items()):
        location = node_origins.get(node_id, path + ("nodes", node_id))
        node_ir_path = ir_path + ("nodes", index)
        if locations is not None:
            locations[node_ir_path] = location
            locations[semantic_path + ("nodes", node_id)] = location
        if not isinstance(declaration, Mapping):
            raise _AuthoringError("named node must be an object", location)
        node = dict(declaration)
        if "id" in node and node["id"] != node_id:
            raise _AuthoringError("node id must match its mapping key", location + ("id",))
        node["id"] = node_id
        structures = [key for key in ("component", "router", "state", "loop", "subgraph") if key in node]
        if "kind" not in node and len(structures) == 1:
            node["kind"] = structures[0]
        kind = node.get("kind")
        node.setdefault("lifecycle", {"input": "on_run_start", "output": "terminal",
                                      "state": "stateful"}.get(kind if isinstance(kind, str) else None, "per_step"))
        component = node.get("component")
        if isinstance(component, str):
            if component.count(":") != 1:
                raise _AuthoringError("component requires namespace:name", location + ("component",))
            namespace, name = component.split(":")
            candidate = {"namespace": namespace, "name": name}
            for key in ("version", "params", "dependencies"):
                if key in node:
                    candidate[key] = node.pop(key)
            node["component"] = {"candidates": [candidate]}
            roles = {"agent." + role.value: role.value for role in GraphRole}
            if "role" not in node and "contract" not in node and namespace in roles:
                node["role"] = roles[namespace]
        # Loop/state meanings and budgets remain the existing IR contracts.
        for key in ("loop", "subgraph"):
            if isinstance(node.get(key), Mapping):
                spec = dict(node[key])
                body = dict(spec["body"]) if key == "loop" and isinstance(spec.get("body"), Mapping) else spec
                if isinstance(body.get("graph"), Mapping):
                    child_path = location + (key,) + (("body",) if key == "loop" else ()) + ("graph",)
                    body["graph"] = _expand_graph(body["graph"], child_path, source_id,
                        source_map, logical_path + (node_id,), locations=locations,
                        # SubgraphSpec validates its Any-valued graph in an after
                        # validator, so nested Pydantic locations omit "graph".
                        ir_path=node_ir_path + (key,) + (("body",) if key == "loop" else ()))
                if key == "loop" and isinstance(spec.get("body"), Mapping):
                    spec["body"] = body
                node[key] = spec
        expanded.append(node)
        source_map.append(SourceMapEntry(
            source_id=source_id + ":" + ":".join(map(str, location)),
            graph_kind="node", graph_id=node_id, property_path=location,
            logical_node_path=logical_path + (node_id,),
        ))
    raw["nodes"] = expanded
    edges = raw.get("edges")
    if not isinstance(edges, list):
        raise _AuthoringError("edges must be an array", path + ("edges",))
    expanded_edges = []
    for index, original in enumerate(edges):
        location = edge_origins[index] if edge_origins else path + ("edges", index)
        if locations is not None:
            locations[ir_path + ("edges", index)] = location
            locations[semantic_path + ("edges", index)] = location
        edge = original
        if isinstance(edge, str):
            parts = edge.split("->")
            if len(parts) != 2:
                raise _AuthoringError("edge requires source.port -> target.port", location)
            edge = {"source": parts[0].strip(), "target": parts[1].strip()}
        if not isinstance(edge, Mapping):
            raise _AuthoringError("edge must be a connection string or object", location)
        edge = dict(edge)
        for key in ("source", "target"):
            if key in edge:
                edge[key] = _address(edge[key], tuple(nodes), location + (key,))
        edge.setdefault("kind", "data")
        expanded_edges.append(edge)
        source_map.append(SourceMapEntry(
            source_id=source_id + ":" + ":".join(map(str, location)),
            graph_kind="edge", graph_id=str(index), property_path=location,
            logical_node_path=logical_path,
        ))
    raw["edges"] = expanded_edges
    return raw


def _source_path(path: tuple[str | int, ...], data: Mapping[str, Any], locations: dict) -> tuple[str | int, ...]:
    """Translate model and graph-validator paths back to authored declarations.

    Args:
        path: Validation location in the expanded IR.
        data: Original parsed YAML document.
        locations: Numeric IR prefixes mapped to authored declarations.
    Returns:
        tuple[str | int, ...]: Addressable source path where a mapping exists.
    """
    for length in range(len(path), 0, -1):
        if path[:length] in locations:
            return locations[path[:length]] + path[length:]
    location = []
    current: Any = data
    for part in path:
        if isinstance(current, Mapping) and isinstance(part, int):
            names = tuple(current)
            if 0 <= part < len(names):
                part = names[part]
        location.append(part)
        if isinstance(current, Mapping):
            current = current.get(part)
        elif isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
            current = current[part]
        else:
            current = None
    return tuple(location)


def compile_compact_graph_yaml_data(
    data: Mapping[str, Any], *, source_id: str, contract_catalog=None, graph_catalog=None,
) -> CompilationResult:
    """Compile the schema-1 named-node authoring form to ordinary AgentGraph.

    Args:
        data: Parsed graph YAML including its envelope.
        source_id: Diagnostic source identifier.
        contract_catalog: Optional explicit node-contract catalog.
        graph_catalog: Optional explicit graph catalog.
    Raises:
        None.
    Returns:
        CompilationResult: Validated graph and source locations, or diagnostics.
    """
    source_map: list[SourceMapEntry] = []
    locations: dict = {}
    try:
        raw = _expand_graph(data, (), source_id, source_map, locations=locations)
        raw.pop("kind", None)
        graph = AgentGraph.model_validate(raw)
    except (_AuthoringError, MachineAuthoringError) as exc:
        return CompilationResult(diagnostics=(GraphDiagnostic(
            code="graph.yaml.compact_invalid", message=str(exc), path=exc.path, source_id=source_id,
        ),))
    except ValidationError as exc:
        issues = diagnostics_from_validation_error(
            exc, code="graph.yaml.structure_invalid", source_prefix=source_id)
        return finish_compilation(None, [item.model_copy(update={"path": _source_path(item.path, data, locations)})
                                          for item in issues], source_map)
    result = finish_compilation(graph, [], source_map,
                                contract_catalog=contract_catalog, graph_catalog=graph_catalog)
    return result.model_copy(update={"diagnostics": sorted_diagnostics([
        item.model_copy(update={"path": _source_path(item.path, data, locations)})
        for item in result.diagnostics])})
