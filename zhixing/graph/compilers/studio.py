"""Compile Studio FlowDocument editing data into the canonical AgentGraph IR."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from ..diagnostics import CompilationResult, GraphDiagnostic, SourceMapEntry
from ..enums import DiagnosticSeverity, EdgeKind, GraphRole, NodeKind, NodeLifecycle
from ..models import AgentGraph, GraphPresentation, NodePresentation
from .common import diagnostics_from_validation_error, finish_compilation, normalize_mapping


_ROLE_BY_STUDIO_TYPE = {
    "perception": GraphRole.PERCEPTION,
    "planner": GraphRole.PLANNER,
    "reasoning": GraphRole.REASONING,
    "memory": GraphRole.MEMORY,
    "action": GraphRole.ACTION_EXECUTOR,
    "action_executor": GraphRole.ACTION_EXECUTOR,
    "verifier": GraphRole.VERIFIER,
}
_LIFECYCLE_BY_ROLE = {
    GraphRole.PERCEPTION: NodeLifecycle.PER_STEP,
    GraphRole.PLANNER: NodeLifecycle.ON_RUN_START,
    GraphRole.REASONING: NodeLifecycle.PER_STEP,
    GraphRole.MEMORY: NodeLifecycle.STATEFUL,
    GraphRole.ACTION_EXECUTOR: NodeLifecycle.PER_STEP,
    GraphRole.VERIFIER: NodeLifecycle.POST_ACTION,
}
_LEGACY_PORT_MAP = {
    "out_task": "task",
    "out_observation": "observation",
    "in_task": "task",
    "in_shot": "observation",
    "out_perc": "perception",
    "out_plan": "plan",
    "in_plan": "plan",
    "in_perc": "perception",
    "in_mem": "memory",
    "out_mem": "context",
    "in_ctx": "write",
    "out_action": "action",
    "in_action": "action",
    "out_result": "result",
    "in_result": "result",
    "in_before": "before",
    "in_after": "after",
    "in_action_result": "action_result",
    "out_verified": "result",
    "in_cond": "value",
    "out_true": "true",
    "out_false": "false",
}
_UNSAFE_TYPES = {"verifiedPlan", "__wild__"}


def _json_schema_errors(
    value: Any,
    schema: Mapping[str, Any],
    path: tuple[str | int, ...] = (),
) -> list[tuple[tuple[str | int, ...], str]]:
    """Validate the bounded JSON-Schema subset emitted by the Studio Catalog.

    Args:
        value: Candidate JSON-compatible value.
        schema: Import-safe Catalog schema.
        path: Current property path used for source diagnostics.

    Raises:
        None.

    Returns:
        list[tuple[tuple[str | int, ...], str]]: Stable path/message errors.
    """
    errors: list[tuple[tuple[str | int, ...], str]] = []
    allowed_types = schema.get("type")
    if isinstance(allowed_types, str):
        allowed_types = [allowed_types]
    type_matches = {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, (list, tuple)),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if isinstance(allowed_types, list) and allowed_types and not any(
        type_matches.get(str(item), False) for item in allowed_types
    ):
        return [(path, f"expected JSON type {allowed_types}")]
    if "const" in schema and value != schema["const"]:
        errors.append((path, "value does not match the required constant"))
    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            errors.append((path, f"string must contain at least {minimum_length} characters"))
        maximum_length = schema.get("maxLength")
        if isinstance(maximum_length, int) and len(value) > maximum_length:
            errors.append((path, f"string must contain at most {maximum_length} characters"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append((path, f"number must be at least {minimum}"))
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append((path, f"number must be at most {maximum}"))
    if isinstance(value, Mapping):
        required = schema.get("required", ())
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    errors.append((path + (key,), "required property is missing"))
        properties = schema.get("properties", {})
        if isinstance(properties, Mapping):
            for key, item in value.items():
                child = properties.get(key)
                if isinstance(child, Mapping):
                    errors.extend(_json_schema_errors(item, child, path + (str(key),)))
                elif schema.get("additionalProperties") is False:
                    errors.append((path + (str(key),), "additional property is not allowed"))
    if isinstance(value, (list, tuple)) and isinstance(schema.get("items"), Mapping):
        for index, item in enumerate(value):
            errors.extend(_json_schema_errors(item, schema["items"], path + (index,)))
    return errors


def _dependency_diagnostics(
    *,
    descriptor: Any,
    candidate: Any,
    descriptors: Mapping[tuple[str, str, str], Any],
    node_index: int,
    candidate_index: int,
    logical_id: str,
    source_id: str,
) -> list[GraphDiagnostic]:
    """Validate one candidate against authoritative Catalog dependency slots.

    Args:
        descriptor: Exact selected component Catalog descriptor.
        candidate: Parsed Graph component candidate.
        descriptors: Exact Catalog descriptor lookup.
        node_index: Studio semantic node index.
        candidate_index: Candidate index within the binding.
        logical_id: Stable graph node identity.
        source_id: Stable node source identity.

    Raises:
        None.

    Returns:
        list[GraphDiagnostic]: Source-addressable dependency diagnostics.
    """
    issues: list[GraphDiagnostic] = []
    base_path = (
        "semantic",
        "nodes",
        node_index,
        "component",
        "candidates",
        candidate_index,
        "dependencies",
    )
    for slot in descriptor.dependency_slots:
        name = str(slot.get("name") or "")
        dependency = candidate.dependencies.get(name)
        if dependency is None:
            if slot.get("required") is True:
                issues.append(
                    GraphDiagnostic(
                        code="graph.studio.component_dependency_required",
                        message=f"Selected component requires dependency {name!r}",
                        path=base_path + (name,),
                        node_id=logical_id,
                        source_id=source_id,
                    )
                )
            continue
        if not isinstance(dependency, Mapping):
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.component_dependency_invalid",
                    message=f"Dependency {name!r} must be a component reference",
                    path=base_path + (name,),
                    node_id=logical_id,
                    source_id=source_id,
                )
            )
            continue
        schema = slot.get("configSchema")
        if isinstance(schema, Mapping):
            for suffix, message in _json_schema_errors(dependency, schema):
                issues.append(
                    GraphDiagnostic(
                        code="graph.studio.component_dependency_invalid",
                        message=f"Dependency {name!r} is invalid: {message}",
                        path=base_path + (name,) + suffix,
                        node_id=logical_id,
                        source_id=source_id,
                    )
                )
        dependency_name = dependency.get("name")
        accepted_namespaces = tuple(slot.get("acceptedNamespaces") or ())
        dependency_namespace = dependency.get("namespace")
        if dependency_namespace is None and len(accepted_namespaces) == 1:
            dependency_namespace = accepted_namespaces[0]
        if not isinstance(dependency_name, str) or not isinstance(
            dependency_namespace, str
        ):
            continue
        if accepted_namespaces and dependency_namespace not in accepted_namespaces:
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.component_dependency_namespace_mismatch",
                    message=f"Dependency {name!r} uses an unsupported namespace",
                    path=base_path + (name, "namespace"),
                    node_id=logical_id,
                    source_id=source_id,
                )
            )
            continue
        dependency_version = dependency.get("version")
        matches = [
            item
            for (namespace, component_name, version), item in descriptors.items()
            if namespace == dependency_namespace
            and component_name == dependency_name
            and (dependency_version is None or version == dependency_version)
        ]
        if len(matches) != 1:
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.component_dependency_unavailable",
                    message=f"Dependency {name!r} is not an exact available Catalog component",
                    path=base_path + (name,),
                    node_id=logical_id,
                    source_id=source_id,
                )
            )
            continue
        nested = matches[0]
        accepted_categories = tuple(slot.get("acceptedCategories") or ())
        if accepted_categories and nested.category not in accepted_categories:
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.component_dependency_category_mismatch",
                    message=f"Dependency {name!r} has an incompatible component category",
                    path=base_path + (name,),
                    node_id=logical_id,
                    source_id=source_id,
                )
            )
        if not nested.availability.available:
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.component_dependency_unavailable",
                    message=f"Dependency {name!r} is unavailable in the current Catalog",
                    path=base_path + (name,),
                    node_id=logical_id,
                    source_id=source_id,
                )
            )
        params = dependency.get("params", {})
        if isinstance(params, Mapping):
            for suffix, message in _json_schema_errors(params, nested.config_schema):
                issues.append(
                    GraphDiagnostic(
                        code="graph.studio.component_dependency_config_invalid",
                        message=f"Dependency {name!r} config is invalid: {message}",
                        path=base_path + (name, "params") + suffix,
                        node_id=logical_id,
                        source_id=source_id,
                    )
                )
    return issues


def _port_map(node: Mapping[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    data = node.get("data") if isinstance(node.get("data"), Mapping) else {}
    ports = data.get("ports") if isinstance(data, Mapping) else []
    if not isinstance(ports, list):
        return out
    for port in ports:
        if not isinstance(port, Mapping):
            continue
        port_id = str(port.get("portId") or port.get("id") or "")
        role = str(port.get("portRole") or port.get("role") or port_id)
        if port_id:
            out[port_id] = _LEGACY_PORT_MAP.get(role, role)
    return out


def _compile_legacy_studio_flow_document(
    document: Mapping[str, Any], *, source_id: str = "studio-flow"
) -> CompilationResult:
    """Compile the retained schema 1 compatibility document.

    Args:
        document (Mapping[str, Any]): Legacy FlowDocument mapping.
        source_id (str): Stable source identity for diagnostics.

    Raises:
        None.

    Returns:
        CompilationResult: Contract 1.0 graph or migration diagnostics.
    """
    issues: list[GraphDiagnostic] = []
    raw_nodes = document.get("nodes")
    raw_edges = document.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return CompilationResult(
            diagnostics=(
                GraphDiagnostic(
                    code="graph.studio.structure_invalid",
                    message="FlowDocument requires nodes and edges arrays",
                    source_id=source_id,
                ),
            )
        )

    graph_nodes: list[dict[str, Any]] = []
    source_map: list[SourceMapEntry] = []
    canvas_to_logical: dict[str, str] = {}
    ports_by_canvas: dict[str, dict[str, str]] = {}
    presentations: dict[str, NodePresentation] = {}

    for index, raw_node in enumerate(raw_nodes):
        if not isinstance(raw_node, Mapping):
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.node_invalid",
                    message="FlowDocument node must be an object",
                    path=("nodes", index),
                    source_id=f"{source_id}:nodes:{index}",
                )
            )
            continue
        canvas_id = str(raw_node.get("nodeId") or raw_node.get("id") or "")
        data = raw_node.get("data") if isinstance(raw_node.get("data"), Mapping) else {}
        logical_id = str(
            raw_node.get("logicalId")
            or raw_node.get("logical_id")
            or data.get("logicalId")
            or data.get("logical_id")
            or ""
        )
        node_type = str(raw_node.get("nodeType") or raw_node.get("type") or "")
        role = _ROLE_BY_STUDIO_TYPE.get(node_type)
        if not logical_id and role is not None:
            same_role = sum(
                1
                for item in raw_nodes
                if isinstance(item, Mapping)
                and _ROLE_BY_STUDIO_TYPE.get(str(item.get("nodeType") or item.get("type") or "")) == role
            )
            if same_role == 1:
                logical_id = role.value
        if not logical_id and node_type in {"input", "output", "ifelse", "condition"}:
            logical_id = node_type if node_type != "ifelse" else "condition"
        if not canvas_id or not logical_id:
            issues.append(
                GraphDiagnostic(
                    code="graph.compile.logical_id_ambiguous",
                    message="Studio node requires canvas nodeId and stable logicalId",
                    path=("nodes", index),
                    source_id=f"{source_id}:nodes:{index}",
                )
            )
            continue
        canvas_to_logical[canvas_id] = logical_id
        ports_by_canvas[canvas_id] = _port_map(raw_node)
        source_map.append(
            SourceMapEntry(
                source_id=f"{source_id}:node:{canvas_id}", graph_kind="node", graph_id=logical_id
            )
        )
        position = raw_node.get("position") if isinstance(raw_node.get("position"), Mapping) else {}
        presentations[logical_id] = NodePresentation(
            x=float(position.get("x", 0) or 0),
            y=float(position.get("y", 0) or 0),
            label=str(data.get("label") or ""),
            icon=str(data.get("icon") or ""),
            description=str(data.get("desc") or ""),
        )
        if role is not None:
            plugin_name = data.get("selected_plugin_id") or data.get("selectedPluginId")
            if not plugin_name and role == GraphRole.ACTION_EXECUTOR:
                plugin_name = "legacy_action_executor"
            if not plugin_name:
                issues.append(
                    GraphDiagnostic(
                        code="graph.studio.plugin_missing",
                        message=f"Studio component {logical_id!r} has no selected plugin",
                        path=("nodes", index, "data", "selected_plugin_id"),
                        node_id=logical_id,
                        source_id=f"{source_id}:node:{canvas_id}",
                    )
                )
                continue
            namespace = str(
                data.get("selected_plugin_namespace")
                or data.get("selectedPluginNamespace")
                or f"agent.{role.value}"
            )
            params = data.get("plugin_params") or data.get("pluginParamValues") or {}
            if not isinstance(params, Mapping):
                params = {}
            graph_nodes.append(
                {
                    "id": logical_id,
                    "kind": "component",
                    "role": role.value,
                    "lifecycle": _LIFECYCLE_BY_ROLE[role].value,
                    "primary": role == GraphRole.ACTION_EXECUTOR,
                    "component": {
                        "policy": "single",
                        "candidates": [
                            {
                                "namespace": namespace,
                                "name": str(plugin_name),
                                "params": normalize_mapping(params),
                                "dependencies": {},
                            }
                        ],
                    },
                }
            )
        elif node_type == "input":
            graph_nodes.append({"id": logical_id, "kind": "input", "lifecycle": "on_run_start"})
        elif node_type == "output":
            graph_nodes.append({"id": logical_id, "kind": "output", "lifecycle": "terminal"})
        elif node_type in {"ifelse", "condition"}:
            predicate = data.get("predicate")
            if not isinstance(predicate, Mapping):
                issues.append(
                    GraphDiagnostic(
                        code="graph.studio.condition_migration_required",
                        message="Studio condition requires a structured predicate; operator_value is not executable semantics",
                        path=("nodes", index, "data", "predicate"),
                        node_id=logical_id,
                        source_id=f"{source_id}:node:{canvas_id}",
                    )
                )
                continue
            graph_nodes.append(
                {
                    "id": logical_id,
                    "kind": "condition",
                    "lifecycle": "post_action",
                    "predicate": dict(predicate),
                }
            )
        else:
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.node_type_unknown",
                    message=f"unknown Studio node type {node_type!r}",
                    path=("nodes", index, "nodeType"),
                    source_id=f"{source_id}:node:{canvas_id}",
                )
            )

    graph_edges: list[dict[str, Any]] = []
    for index, raw_edge in enumerate(raw_edges):
        if not isinstance(raw_edge, Mapping):
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.edge_invalid",
                    message="FlowDocument edge must be an object",
                    path=("edges", index),
                    source_id=f"{source_id}:edges:{index}",
                )
            )
            continue
        source_canvas = str(raw_edge.get("sourceNodeId") or raw_edge.get("source") or "")
        target_canvas = str(raw_edge.get("targetNodeId") or raw_edge.get("target") or "")
        source_port_id = str(raw_edge.get("sourcePortId") or raw_edge.get("sourceHandle") or "")
        target_port_id = str(raw_edge.get("targetPortId") or raw_edge.get("targetHandle") or "")
        source_node = canvas_to_logical.get(source_canvas)
        target_node = canvas_to_logical.get(target_canvas)
        source_port = ports_by_canvas.get(source_canvas, {}).get(source_port_id, _LEGACY_PORT_MAP.get(source_port_id, source_port_id))
        target_port = ports_by_canvas.get(target_canvas, {}).get(target_port_id, _LEGACY_PORT_MAP.get(target_port_id, target_port_id))
        declared_type = str(raw_edge.get("dataType") or "")
        if declared_type in _UNSAFE_TYPES:
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.edge_migration_required",
                    message=f"Studio edge type {declared_type!r} cannot map safely to AgentGraph",
                    path=("edges", index, "dataType"),
                    source_id=f"{source_id}:edges:{index}",
                )
            )
            continue
        if not source_node or not target_node:
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.edge_node_unknown",
                    message="Studio edge references an unknown or uncompiled node",
                    path=("edges", index),
                    source_id=f"{source_id}:edges:{index}",
                )
            )
            continue
        kind = str(raw_edge.get("kind") or "")
        if not kind:
            source_type = next(
                (
                    str(item.get("nodeType") or item.get("type"))
                    for item in raw_nodes
                    if isinstance(item, Mapping)
                    and str(item.get("nodeId") or item.get("id")) == source_canvas
                ),
                "",
            )
            kind = "control" if source_type in {"ifelse", "condition"} else "data"
        graph_edge: dict[str, Any] = {
            "source": {"node": source_node, "port": source_port},
            "target": {"node": target_node, "port": target_port},
            "kind": kind,
        }
        if raw_edge.get("condition") is not None:
            graph_edge["condition"] = raw_edge.get("condition")
        if kind == EdgeKind.FEEDBACK.value:
            graph_edge["feedback"] = raw_edge.get("feedback")
        graph_edges.append(graph_edge)
        source_map.append(
            SourceMapEntry(
                source_id=f"{source_id}:edge:{raw_edge.get('edgeId') or index}",
                graph_kind="edge",
                graph_id=str(len(graph_edges) - 1),
            )
        )

    if issues:
        return finish_compilation(None, issues, source_map)
    raw_graph = {
        "schema_version": 1,
        "contract_version": str(document.get("contractVersion") or "1.0"),
        "profile": "mobile_agent",
        "nodes": graph_nodes,
        "edges": graph_edges,
        "policies": document.get("policies") or {},
        "presentation": {
            "flow_id": document.get("flowId"),
            "flow_name": document.get("flowName"),
            "created_at": document.get("createTime"),
            "updated_at": document.get("updateTime"),
            "nodes": {key: value.model_dump(mode="python") for key, value in presentations.items()},
        },
    }
    try:
        graph = AgentGraph.model_validate(raw_graph)
    except ValidationError as exc:
        issues.extend(
            diagnostics_from_validation_error(
                exc, code="graph.studio.graph_invalid", source_prefix=source_id
            )
        )
        return finish_compilation(None, issues, source_map)
    return finish_compilation(graph, issues, source_map)


def _compile_subgraph_spec(
    specification: Any,
    *,
    source_id: str,
    canvas_path: tuple[str, ...],
    contract_catalog: Any,
    graph_catalog: Any,
    component_catalog: Any,
    issues: list[GraphDiagnostic],
    source_map: list[SourceMapEntry],
) -> dict[str, Any] | None:
    """Compile an inline Studio subgraph or copy a fixed catalog reference.

    Args:
        specification (StudioSubgraphSpec): Parsed authoring subgraph.
        source_id (str): Stable root source identity.
        canvas_path (tuple[str, ...]): Nested authoring canvas path.
        contract_catalog (Any): Explicit NodeContract extension catalog.
        graph_catalog (Any): Explicit immutable graph catalog.
        component_catalog (Any): Explicit Studio Component Catalog.
        issues (list[GraphDiagnostic]): Mutable compiler issue accumulator.
        source_map (list[SourceMapEntry]): Mutable source-map accumulator.

    Raises:
        None.

    Returns:
        dict[str, Any] | None: Graph SubgraphSpec mapping when compilation
        succeeds.
    """
    common = {
        "inputs": specification.inputs,
        "outputs": specification.outputs,
        "shared_state": specification.shared_state,
        "max_activations": specification.max_activations,
        "error_policy": specification.error_policy.value,
    }
    if specification.reference is not None:
        return {
            **common,
            "reference": specification.reference.model_dump(mode="python"),
        }
    nested = _compile_schema2_studio_document(
        specification.document,
        source_id=source_id,
        contract_catalog=contract_catalog,
        graph_catalog=graph_catalog,
        component_catalog=component_catalog,
        canvas_path=canvas_path,
    )
    issues.extend(nested.diagnostics)
    source_map.extend(nested.source_map)
    if not nested.is_success:
        return None
    return {
        **common,
        "graph": nested.graph.model_dump(mode="python", exclude_none=True),
    }


def _source_map_for_document(
    document: Any,
    *,
    source_id: str,
    canvas_path: tuple[str, ...],
) -> list[SourceMapEntry]:
    """Build deterministic node, edge, and endpoint mappings for schema 2.

    Args:
        document (StudioFlowDocument): Parsed authoring document.
        source_id (str): Stable root source identity.
        canvas_path (tuple[str, ...]): Nested authoring canvas path.

    Raises:
        None.

    Returns:
        list[SourceMapEntry]: Stable enriched source mappings.
    """
    node_by_canvas = {node.canvas_id: node for node in document.semantic.nodes}
    result: list[SourceMapEntry] = []
    for index, node in enumerate(document.semantic.nodes):
        logical_path = canvas_path + (node.logical_id,)
        result.append(
            SourceMapEntry(
                source_id=f"{source_id}:canvas:{'/'.join(canvas_path)}:node:{node.canvas_id}",
                graph_kind="node",
                graph_id=node.logical_id,
                document_id=document.document_id,
                canvas_path=canvas_path,
                canvas_node_id=node.canvas_id,
                logical_node_path=logical_path,
                property_path=("semantic", "nodes", index),
            )
        )
    for index, edge in enumerate(document.semantic.edges):
        source = node_by_canvas.get(edge.source.canvas_id)
        target = node_by_canvas.get(edge.target.canvas_id)
        result.append(
            SourceMapEntry(
                source_id=f"{source_id}:canvas:{'/'.join(canvas_path)}:edge:{edge.canvas_id}",
                graph_kind="edge",
                graph_id=str(index),
                document_id=document.document_id,
                canvas_path=canvas_path,
                canvas_edge_id=edge.canvas_id,
                logical_node_path=(
                    *(canvas_path + ((source.logical_id,) if source else ())),
                    *((target.logical_id,) if target else ()),
                ),
                property_path=("semantic", "edges", index),
            )
        )
        for endpoint_name, endpoint in (("source", edge.source), ("target", edge.target)):
            endpoint_node = node_by_canvas.get(endpoint.canvas_id)
            result.append(
                SourceMapEntry(
                    source_id=(
                        f"{source_id}:canvas:{'/'.join(canvas_path)}:"
                        f"edge:{edge.canvas_id}:{endpoint_name}:{endpoint.port_id}"
                    ),
                    graph_kind="port",
                    graph_id=(
                        f"{endpoint_node.logical_id if endpoint_node else endpoint.canvas_id}:"
                        f"{endpoint.port_id}"
                    ),
                    document_id=document.document_id,
                    canvas_path=canvas_path,
                    canvas_node_id=endpoint.canvas_id,
                    canvas_edge_id=edge.canvas_id,
                    logical_node_path=(
                        canvas_path + ((endpoint_node.logical_id,) if endpoint_node else ())
                    ),
                    contract_port_id=endpoint.port_id,
                    property_path=(
                        "semantic",
                        "edges",
                        index,
                        endpoint_name,
                        "portId",
                    ),
                )
            )
    return result


def _diagnostic_source(
    diagnostic: GraphDiagnostic,
    *,
    document: Any,
    source_id: str,
    canvas_path: tuple[str, ...],
) -> GraphDiagnostic:
    """Attach a stable schema 2 source identity to a graph diagnostic.

    Args:
        diagnostic (GraphDiagnostic): Validator/compiler diagnostic.
        document (StudioFlowDocument): Parsed authoring document.
        source_id (str): Stable root source identity.
        canvas_path (tuple[str, ...]): Nested authoring canvas path.

    Raises:
        None.

    Returns:
        GraphDiagnostic: Diagnostic with source identity when resolvable.
    """
    if diagnostic.source_id:
        return diagnostic
    canvas_id: str | None = None
    edge_id: str | None = None
    if diagnostic.node_id:
        node = next(
            (
                item
                for item in document.semantic.nodes
                if item.logical_id == diagnostic.node_id
            ),
            None,
        )
        canvas_id = node.canvas_id if node else None
    if diagnostic.edge_index is not None and 0 <= diagnostic.edge_index < len(
        document.semantic.edges
    ):
        edge_id = document.semantic.edges[diagnostic.edge_index].canvas_id
    location = (
        f"edge:{edge_id}"
        if edge_id
        else f"node:{canvas_id}"
        if canvas_id
        else "document"
    )
    return diagnostic.model_copy(
        update={
            "source_id": (
                f"{source_id}:document:{document.document_id}:"
                f"canvas:{'/'.join(canvas_path)}:{location}"
            )
        }
    )


def _compile_schema2_studio_document(
    document: Any,
    *,
    source_id: str,
    contract_catalog: Any,
    graph_catalog: Any,
    component_catalog: Any = None,
    canvas_path: tuple[str, ...] = (),
    expected_catalog_version: str | None = None,
    catalog_version: str | None = None,
) -> CompilationResult:
    """Compile one parsed or raw schema 2 Studio document recursively.

    Args:
        document (Any): Parsed StudioFlowDocument or raw mapping.
        source_id (str): Stable source identity.
        contract_catalog (Any): Explicit NodeContract extension catalog.
        graph_catalog (Any): Explicit immutable graph catalog.
        component_catalog (Any): Explicit Studio Component Catalog.
        canvas_path (tuple[str, ...]): Nested authoring canvas path.
        expected_catalog_version (str | None): Client-observed Catalog version.
        catalog_version (str | None): Current server Catalog version.

    Raises:
        None.

    Returns:
        CompilationResult: Contract 1.1 graph or deterministic diagnostics.
    """
    from zhixing.studio.models import StudioFlowDocument

    try:
        parsed = (
            document
            if isinstance(document, StudioFlowDocument)
            else StudioFlowDocument.model_validate(document)
        )
    except ValidationError as error:
        issues = diagnostics_from_validation_error(
            error,
            code="graph.studio.schema2_invalid",
            source_prefix=source_id,
        )
        return finish_compilation(None, issues, [])

    issues: list[GraphDiagnostic] = []
    if (
        expected_catalog_version
        and catalog_version
        and expected_catalog_version != catalog_version
    ):
        issues.append(
            GraphDiagnostic(
                code="graph.studio.catalog_version_changed",
                message="Component Catalog changed after the document was loaded",
                severity=DiagnosticSeverity.WARNING,
                path=("catalogVersion",),
                source_id=f"{source_id}:catalogVersion",
            )
        )

    source_map = _source_map_for_document(
        parsed,
        source_id=source_id,
        canvas_path=canvas_path,
    )
    logical_by_canvas = {
        node.canvas_id: node.logical_id for node in parsed.semantic.nodes
    }
    component_descriptors = (
        {
            (item.namespace, item.name, item.version): item
            for item in component_catalog.components
        }
        if component_catalog is not None
        else {}
    )
    graph_nodes: list[dict[str, Any]] = []
    for index, node in enumerate(parsed.semantic.nodes):
        raw_node: dict[str, Any] = {
            "id": node.logical_id,
            "kind": node.kind.value,
            "lifecycle": node.lifecycle.value,
            "primary": node.primary,
            "metadata": node.metadata,
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
            if value is not None:
                raw_node[field_name] = (
                    value.value
                    if isinstance(value, GraphRole)
                    else value.model_dump(mode="python", exclude_none=True)
                )
        child_path = canvas_path + (node.canvas_id,)
        if node.subgraph is not None:
            compiled = _compile_subgraph_spec(
                node.subgraph,
                source_id=source_id,
                canvas_path=child_path,
                contract_catalog=contract_catalog,
                graph_catalog=graph_catalog,
                component_catalog=component_catalog,
                issues=issues,
                source_map=source_map,
            )
            if compiled is not None:
                raw_node["subgraph"] = compiled
        if node.loop is not None:
            body = _compile_subgraph_spec(
                node.loop.body,
                source_id=source_id,
                canvas_path=child_path,
                contract_catalog=contract_catalog,
                graph_catalog=graph_catalog,
                component_catalog=component_catalog,
                issues=issues,
                source_map=source_map,
            )
            if body is not None:
                raw_node["loop"] = {
                    "body": body,
                    "inputs": node.loop.inputs,
                    "outputs": node.loop.outputs,
                    "until": node.loop.until.model_dump(mode="python"),
                    "max_iterations": node.loop.max_iterations,
                    "on_exhausted": node.loop.on_exhausted.value,
                    "max_activations": node.loop.max_activations,
                }
        graph_nodes.append(raw_node)

        if node.kind is NodeKind.COMPONENT and node.component is not None:
            expected_contract = node.contract
            if expected_contract is None and node.role is not None:
                from ..contracts import contract_ref_for_role

                expected_contract = contract_ref_for_role(node.role)
            if component_catalog is not None:
                for candidate_index, candidate in enumerate(node.component.candidates):
                    descriptor = component_descriptors.get(
                        (candidate.namespace, candidate.name, candidate.version)
                    )
                    if descriptor is None:
                        issues.append(
                            GraphDiagnostic(
                                code="graph.studio.component_unavailable",
                                message=(
                                    "Component "
                                    f"{candidate.namespace}:{candidate.name}@"
                                    f"{candidate.version} is not present in the Catalog"
                                ),
                                path=(
                                    "semantic",
                                    "nodes",
                                    index,
                                    "component",
                                    "candidates",
                                    candidate_index,
                                ),
                                node_id=node.logical_id,
                                source_id=(
                                    f"{source_id}:document:{parsed.document_id}:"
                                    f"node:{node.canvas_id}"
                                ),
                            )
                        )
                        continue
                    dependency_source = (
                        f"{source_id}:document:{parsed.document_id}:canvas:"
                        f"{'/'.join(canvas_path)}:node:{node.canvas_id}"
                    )
                    issues.extend(
                        _dependency_diagnostics(
                            descriptor=descriptor,
                            candidate=candidate,
                            descriptors=component_descriptors,
                            node_index=index,
                            candidate_index=candidate_index,
                            logical_id=node.logical_id,
                            source_id=dependency_source,
                        )
                    )
                    if not descriptor.availability.available:
                        issues.append(
                            GraphDiagnostic(
                                code="graph.studio.component_dependency_missing",
                                message=(
                                    "Selected component is unavailable because an "
                                    "optional dependency is missing"
                                ),
                                path=(
                                    "semantic",
                                    "nodes",
                                    index,
                                    "component",
                                    "candidates",
                                    candidate_index,
                                ),
                                node_id=node.logical_id,
                                source_id=(
                                    f"{source_id}:document:{parsed.document_id}:"
                                    f"node:{node.canvas_id}"
                                ),
                            )
                        )
                    if (
                        expected_contract is not None
                        and descriptor.contract.ref != expected_contract
                    ):
                        issues.append(
                            GraphDiagnostic(
                                code="graph.studio.component_contract_mismatch",
                                message=(
                                    "Selected component does not implement the "
                                    "node's exact NodeContract"
                                ),
                                path=(
                                    "semantic",
                                    "nodes",
                                    index,
                                    "contract",
                                ),
                                node_id=node.logical_id,
                                source_id=(
                                    f"{source_id}:document:{parsed.document_id}:"
                                    f"node:{node.canvas_id}"
                                ),
                            )
                        )

    graph_edges: list[dict[str, Any]] = []
    for index, edge in enumerate(parsed.semantic.edges):
        source_node = logical_by_canvas.get(edge.source.canvas_id)
        target_node = logical_by_canvas.get(edge.target.canvas_id)
        if source_node is None or target_node is None:
            issues.append(
                GraphDiagnostic(
                    code="graph.studio.edge_node_unknown",
                    message="Studio edge references an unknown canvas node",
                    path=("semantic", "edges", index),
                    edge_index=index,
                    source_id=(
                        f"{source_id}:document:{parsed.document_id}:"
                        f"edge:{edge.canvas_id}"
                    ),
                )
            )
            continue
        raw_edge: dict[str, Any] = {
            "source": {"node": source_node, "port": edge.source.port_id},
            "target": {"node": target_node, "port": edge.target.port_id},
            "kind": edge.kind.value,
        }
        if edge.condition is not None:
            raw_edge["condition"] = edge.condition.model_dump(mode="python")
        if edge.feedback is not None:
            raw_edge["feedback"] = edge.feedback.model_dump(mode="python")
        graph_edges.append(raw_edge)

    if any(item.severity is DiagnosticSeverity.ERROR for item in issues):
        return finish_compilation(None, issues, source_map)

    presentations: dict[str, NodePresentation] = {}
    for node in parsed.semantic.nodes:
        presentation = parsed.presentation.nodes.get(node.canvas_id)
        if presentation is None:
            continue
        presentations[node.logical_id] = NodePresentation(
            x=presentation.x,
            y=presentation.y,
            label=presentation.label,
            icon=presentation.icon,
            description=presentation.description,
        )
    raw_graph: dict[str, Any] = {
        "schema_version": 1,
        "contract_version": "1.1",
        "profile": parsed.semantic.profile,
        "nodes": graph_nodes,
        "edges": graph_edges,
        "policies": parsed.semantic.policies.model_dump(mode="python"),
        "presentation": GraphPresentation(
            flow_id=parsed.document_id,
            flow_name=parsed.name,
            created_at=parsed.authoring.created_at,
            updated_at=parsed.authoring.updated_at,
            nodes=presentations,
        ).model_dump(mode="python"),
    }
    if parsed.semantic.interface is not None:
        raw_graph["interface"] = parsed.semantic.interface.model_dump(mode="python")
    try:
        graph = AgentGraph.model_validate(raw_graph)
    except ValidationError as error:
        issues.extend(
            diagnostics_from_validation_error(
                error,
                code="graph.studio.graph_invalid",
                source_prefix=source_id,
            )
        )
        return finish_compilation(None, issues, source_map)

    result = finish_compilation(
        graph,
        issues,
        source_map,
        contract_catalog=contract_catalog,
        graph_catalog=graph_catalog,
    )
    diagnostics = tuple(
        _diagnostic_source(
            item,
            document=parsed,
            source_id=source_id,
            canvas_path=canvas_path,
        )
        for item in result.diagnostics
    )
    return result.model_copy(
        update={
            "graph": result.graph if result.is_success else None,
            "diagnostics": diagnostics,
        }
    )


def _schema3_generated_id(owner_id: str, purpose: str) -> str:
    """Return one deterministic AgentGraph-compatible generated identity.

    Args:
        owner_id: Stable capability or boundary owner identity.
        purpose: Stable lowering purpose suffix.

    Raises:
        None.

    Returns:
        Generated logical identity in the reserved namespace.
    """
    return f"studio_generated.{owner_id}.{purpose}"


def _compile_schema3_capability_document(
    document: Any,
    *,
    source_id: str,
    contract_catalog: Any,
    graph_catalog: Any,
    component_catalog: Any,
    expected_catalog_version: str | None,
    catalog_version: str | None,
) -> CompilationResult:
    """Lower one schema-3 capability document into an ordinary AgentGraph.

    The function is deliberately pure: it consumes strict document and Catalog
    metadata, produces graph/mapping evidence, and never resolves providers,
    secrets, components, models, or devices.

    Args:
        document: Parsed or raw schema-3 capability document.
        source_id: Stable diagnostic source identity.
        contract_catalog: Explicit NodeContract extension catalog.
        graph_catalog: Explicit immutable graph catalog.
        component_catalog: Exact backend Component Catalog.
        expected_catalog_version: Client-observed Catalog identity.
        catalog_version: Current server Catalog identity.

    Raises:
        None: Structural, placement, and graph failures become diagnostics.

    Returns:
        Schema-3 compilation result with projection and identity evidence.
    """
    from zhixing.studio.models import (
        STUDIO_CAPABILITY_AUTHORING_POLICY,
        STUDIO_CAPABILITY_LOWERING_PROFILE,
        StudioCapabilityCompilationResult,
        StudioCapabilityDocument,
        StudioProjectionEntry,
        StudioProjectionOwner,
    )

    try:
        parsed = (
            document
            if isinstance(document, StudioCapabilityDocument)
            else StudioCapabilityDocument.model_validate(document)
        )
    except ValidationError as error:
        issues = diagnostics_from_validation_error(
            error,
            code="graph.studio.schema3_invalid",
            source_prefix=source_id,
        )
        return CompilationResult(diagnostics=tuple(issues))

    issues: list[GraphDiagnostic] = []
    if component_catalog is None:
        issues.append(
            GraphDiagnostic(
                code="graph.studio.capability_catalog_required",
                message="Schema-3 capability compilation requires the exact Catalog",
                path=("capabilities",),
                source_id=f"{source_id}:catalog",
            )
        )
    if (
        expected_catalog_version
        and catalog_version
        and expected_catalog_version != catalog_version
    ):
        issues.append(
            GraphDiagnostic(
                code="graph.studio.catalog_version_changed",
                message="Component Catalog changed after the document was loaded",
                severity=DiagnosticSeverity.WARNING,
                path=("catalogVersion",),
                source_id=f"{source_id}:catalogVersion",
            )
        )
    descriptors = {
        (item.namespace, item.name, item.version): item
        for item in getattr(component_catalog, "components", ())
    }
    descriptor_by_node: dict[str, Any] = {}
    for node_index, node in enumerate(parsed.capabilities):
        for candidate_index, candidate in enumerate(node.implementation.candidates):
            descriptor = descriptors.get(
                (candidate.namespace, candidate.name, candidate.version)
            )
            path = (
                "capabilities",
                node_index,
                "implementation",
                "candidates",
                candidate_index,
            )
            if descriptor is None:
                issues.append(
                    GraphDiagnostic(
                        code="graph.studio.capability_implementation_unavailable",
                        message="Selected capability implementation is absent from the Catalog",
                        path=path,
                        node_id=node.logical_id,
                        source_id=f"{source_id}:capability:{node.canvas_id}",
                    )
                )
                continue
            if (
                descriptor.placement != "agent_capability"
                or descriptor.capability_family != node.family
            ):
                issues.append(
                    GraphDiagnostic(
                        code="graph.studio.capability_placement_forbidden",
                        message=(
                            "Selected Catalog entry is not authorized for this "
                            "capability family"
                        ),
                        path=path,
                        node_id=node.logical_id,
                        source_id=f"{source_id}:capability:{node.canvas_id}",
                    )
                )
                continue
            if not descriptor.availability.available:
                issues.append(
                    GraphDiagnostic(
                        code="graph.studio.capability_implementation_unavailable",
                        message="Selected capability implementation is unavailable",
                        path=path,
                        node_id=node.logical_id,
                        source_id=f"{source_id}:capability:{node.canvas_id}",
                    )
                )
                continue
            dependency_source = f"{source_id}:capability:{node.canvas_id}"
            issues.extend(
                _dependency_diagnostics(
                    descriptor=descriptor,
                    candidate=candidate,
                    descriptors=descriptors,
                    node_index=node_index,
                    candidate_index=candidate_index,
                    logical_id=node.logical_id,
                    source_id=dependency_source,
                )
            )
            descriptor_by_node.setdefault(node.logical_id, descriptor)
    capability_hash = parsed.semantic_hash()
    if any(item.severity is DiagnosticSeverity.ERROR for item in issues):
        return StudioCapabilityCompilationResult(
            diagnostics=tuple(sorted(issues, key=lambda item: item.sort_key())),
            authoring_policy=STUDIO_CAPABILITY_AUTHORING_POLICY,
            lowering_profile=STUDIO_CAPABILITY_LOWERING_PROFILE,
            capability_hash=capability_hash,
        )

    nodes: list[dict[str, Any]] = [
        {
            "id": parsed.input.logical_id,
            "kind": "input",
            "lifecycle": "on_run_start",
        }
    ]
    projections: list[StudioProjectionEntry] = [
        StudioProjectionEntry(
            graph_kind="node",
            graph_id=parsed.input.logical_id,
            owner=StudioProjectionOwner(kind="input", owner_id=parsed.input.logical_id),
        )
    ]
    source_map: list[SourceMapEntry] = [
        SourceMapEntry(
            source_id=f"{source_id}:input:{parsed.input.canvas_id}",
            graph_kind="node",
            graph_id=parsed.input.logical_id,
            document_id=parsed.document_id,
            canvas_node_id=parsed.input.canvas_id,
            logical_node_path=(parsed.input.logical_id,),
        )
    ]
    family_by_id = {node.logical_id: node.family for node in parsed.capabilities}
    perception_nodes = tuple(
        node for node in parsed.capabilities if node.family == "perception"
    )
    observe_by_perception = {
        node.logical_id: _schema3_generated_id(node.logical_id, "observe")
        for node in perception_nodes
    }
    for perception_node in perception_nodes:
        observe_id = observe_by_perception[perception_node.logical_id]
        nodes.append(
            {
                "id": observe_id,
                "kind": "component",
                "lifecycle": "per_step",
                "contract": {"id": "zhixing.service.device_observe", "version": "2.0"},
                "component": {
                    "policy": "single",
                    "candidates": [
                        {
                            "namespace": "zhixing.runtime",
                            "name": "device_observe",
                            "version": "1",
                            "params": {},
                            "dependencies": {},
                        }
                    ],
                },
            }
        )
        projections.append(
            StudioProjectionEntry(
                graph_kind="node",
                graph_id=observe_id,
                owner=StudioProjectionOwner(
                    kind="capability", owner_id=perception_node.logical_id
                ),
            )
        )
        source_map.append(
            SourceMapEntry(
                source_id=f"{source_id}:capability:{perception_node.canvas_id}:observe",
                graph_kind="node",
                graph_id=observe_id,
                document_id=parsed.document_id,
                canvas_node_id=perception_node.canvas_id,
                logical_node_path=(perception_node.logical_id,),
            )
        )

    feedback_relation = next(
        (relation for relation in parsed.relations if relation.kind == "feedback"),
        None,
    )
    iteration_id = (
        _schema3_generated_id(feedback_relation.canvas_id, "iteration")
        if feedback_relation is not None and observe_by_perception
        else None
    )
    if iteration_id is not None and feedback_relation is not None:
        nodes.append(
            {
                "id": iteration_id,
                "kind": "router",
                "lifecycle": "per_step",
                "router": {
                    "cases": [
                        {
                            "id": "blocked",
                            "predicate": {"field": "blocked", "operator": "exists"},
                        }
                    ],
                    "default": "ready",
                },
            }
        )
        projections.append(
            StudioProjectionEntry(
                graph_kind="node",
                graph_id=iteration_id,
                owner=StudioProjectionOwner(
                    kind="graph_policy", owner_id="interaction_feedback"
                ),
            )
        )
        source_map.append(
            SourceMapEntry(
                source_id=f"{source_id}:policy:interaction_feedback",
                graph_kind="node",
                graph_id=iteration_id,
                document_id=parsed.document_id,
                canvas_edge_id=feedback_relation.canvas_id,
            )
        )

    action_request_by_id: dict[str, str] = {}
    for node in parsed.capabilities:
        descriptor = descriptor_by_node.get(node.logical_id)
        if descriptor is None:
            continue
        if node.family == "action_executor":
            action_request_id = _schema3_generated_id(node.logical_id, "action_request")
            action_request_by_id[node.logical_id] = action_request_id
            nodes.append(
                {
                    "id": action_request_id,
                    "kind": "component",
                    "lifecycle": "per_step",
                    "contract": {"id": "zhixing.control.action_request", "version": "1.0"},
                    "component": {
                        "policy": "single",
                        "candidates": [
                            {
                                "namespace": "zhixing.control",
                                "name": "action_request",
                                "version": "1",
                                "params": {},
                                "dependencies": {},
                            }
                        ],
                    },
                }
            )
            graph_node = {
                "id": node.logical_id,
                "kind": "component",
                "lifecycle": node.lifecycle.value,
                "contract": {"id": "zhixing.service.action_executor", "version": "1.0"},
                "primary": True,
                "component": {
                    "policy": "single",
                    "candidates": [
                        {
                            "namespace": "zhixing.runtime",
                            "name": "action_executor",
                            "version": "1",
                            "params": {},
                            "dependencies": {},
                        }
                    ],
                },
                "metadata": node.metadata,
            }
            generated_ids = (action_request_id, node.logical_id)
        else:
            graph_node = {
                "id": node.logical_id,
                "kind": "component",
                "lifecycle": node.lifecycle.value,
                "contract": descriptor.contract.ref.model_dump(mode="python"),
                "component": node.implementation.model_dump(mode="python"),
                "primary": node.primary,
                "metadata": node.metadata,
            }
            if node.family in {item.value for item in GraphRole}:
                graph_node["role"] = node.family
            generated_ids = (node.logical_id,)
        nodes.append(graph_node)
        for generated_id in generated_ids:
            projections.append(
                StudioProjectionEntry(
                    graph_kind="node",
                    graph_id=generated_id,
                    owner=StudioProjectionOwner(
                        kind="capability", owner_id=node.logical_id
                    ),
                )
            )
            source_map.append(
                SourceMapEntry(
                    source_id=f"{source_id}:capability:{node.canvas_id}",
                    graph_kind="node",
                    graph_id=generated_id,
                    document_id=parsed.document_id,
                    canvas_node_id=node.canvas_id,
                    logical_node_path=(node.logical_id,),
                )
            )

    output_id = parsed.output.logical_id
    nodes.append({"id": output_id, "kind": "output", "lifecycle": "terminal"})
    projections.append(
        StudioProjectionEntry(
            graph_kind="node",
            graph_id=output_id,
            owner=StudioProjectionOwner(kind="output", owner_id=output_id),
        )
    )
    source_map.append(
        SourceMapEntry(
            source_id=f"{source_id}:output:{parsed.output.canvas_id}",
            graph_kind="node",
            graph_id=output_id,
            document_id=parsed.document_id,
            canvas_node_id=parsed.output.canvas_id,
            logical_node_path=(output_id,),
        )
    )

    edges: list[dict[str, Any]] = []

    def add_edge(
        raw: dict[str, Any],
        *,
        owner_kind: str,
        owner_id: str,
        canvas_edge_id: str | None = None,
    ) -> None:
        """Append one deterministic generated edge and both mappings.

        Args:
            raw: AgentGraph edge mapping.
            owner_kind: Projection owner kind.
            owner_id: Projection owner identity.
            canvas_edge_id: Optional authoring relation identity.

        Raises:
            ValueError: Projection models reject invalid identities.

        Returns:
            None.
        """
        edge_id = f"edge.{len(edges):04d}"
        edges.append(raw)
        projections.append(
            StudioProjectionEntry(
                graph_kind="edge",
                graph_id=edge_id,
                owner=StudioProjectionOwner(kind=owner_kind, owner_id=owner_id),
            )
        )
        source_map.append(
            SourceMapEntry(
                source_id=f"{source_id}:{owner_kind}:{owner_id}:edge:{edge_id}",
                graph_kind="edge",
                graph_id=edge_id,
                document_id=parsed.document_id,
                canvas_edge_id=canvas_edge_id,
            )
        )

    for perception_index, perception_node in enumerate(perception_nodes):
        observe_id = observe_by_perception[perception_node.logical_id]
        add_edge(
            {
                "source": {"node": parsed.input.logical_id, "port": "value"},
                "target": {"node": observe_id, "port": "request"},
                "kind": "data",
            },
            owner_kind="capability",
            owner_id=perception_node.logical_id,
        )
        if iteration_id is not None and feedback_relation is not None:
            if perception_index == 0:
                feedback_target = feedback_relation.target.owner_id
                feedback_target_port = (
                    "context"
                    if family_by_id.get(feedback_target) == "memory"
                    else feedback_relation.target.port_id
                )
                add_edge(
                    {
                        "source": {
                            "node": feedback_target,
                            "port": feedback_target_port,
                        },
                        "target": {"node": iteration_id, "port": "value"},
                        "kind": "data",
                    },
                    owner_kind="graph_policy",
                    owner_id="interaction_feedback",
                    canvas_edge_id=feedback_relation.canvas_id,
                )
            add_edge(
                {
                    "source": {"node": iteration_id, "port": "ready"},
                    "target": {"node": observe_id, "port": "control"},
                    "kind": "control",
                },
                owner_kind="graph_policy",
                owner_id="interaction_feedback",
                canvas_edge_id=feedback_relation.canvas_id,
            )
        add_edge(
            {
                "source": {"node": observe_id, "port": "observation"},
                "target": {"node": perception_node.logical_id, "port": "observation"},
                "kind": "data",
            },
            owner_kind="capability",
            owner_id=perception_node.logical_id,
        )

    for relation in parsed.relations:
        source_id_value = relation.source.owner_id
        target_id_value = relation.target.owner_id
        if relation.kind == "termination":
            descriptor = descriptor_by_node.get(source_id_value)
            if descriptor is None or descriptor.termination is None:
                issues.append(
                    GraphDiagnostic(
                        code="graph.studio.termination_source_forbidden",
                        message="Output relation source lacks formal termination metadata",
                        path=("relations", relation.canvas_id),
                        node_id=source_id_value,
                        source_id=f"{source_id}:relation:{relation.canvas_id}",
                    )
                )
                continue
            terminal_id = _schema3_generated_id(source_id_value, "terminal")
            if not any(item["id"] == terminal_id for item in nodes):
                nodes.append(
                    {
                        "id": terminal_id,
                        "kind": "condition",
                        "lifecycle": "per_step",
                        "predicate": descriptor.termination["predicate"],
                    }
                )
                projections.append(
                    StudioProjectionEntry(
                        graph_kind="node",
                        graph_id=terminal_id,
                        owner=StudioProjectionOwner(
                            kind="relation", owner_id=relation.canvas_id
                        ),
                    )
                )
                source_map.append(
                    SourceMapEntry(
                        source_id=f"{source_id}:relation:{relation.canvas_id}:terminal",
                        graph_kind="node",
                        graph_id=terminal_id,
                        document_id=parsed.document_id,
                        canvas_edge_id=relation.canvas_id,
                    )
                )
            source_port = str(descriptor.termination.get("sourcePort", "result"))
            add_edge(
                {
                    "source": {"node": source_id_value, "port": source_port},
                    "target": {"node": terminal_id, "port": "value"},
                    "kind": "data",
                },
                owner_kind="relation",
                owner_id=relation.canvas_id,
                canvas_edge_id=relation.canvas_id,
            )
            add_edge(
                {
                    "source": {"node": source_id_value, "port": source_port},
                    "target": {"node": output_id, "port": "result"},
                    "kind": "data",
                },
                owner_kind="output",
                owner_id=output_id,
                canvas_edge_id=relation.canvas_id,
            )
            add_edge(
                {
                    "source": {"node": terminal_id, "port": "true"},
                    "target": {"node": output_id, "port": "control"},
                    "kind": "control",
                },
                owner_kind="output",
                owner_id=output_id,
                canvas_edge_id=relation.canvas_id,
            )
            continue
        source_port = relation.source.port_id
        target_port = relation.target.port_id
        if target_id_value in action_request_by_id:
            target_id_value = action_request_by_id[target_id_value]
            target_port = "action"
        raw_edge: dict[str, Any] = {
            "source": {"node": source_id_value, "port": source_port},
            "target": {"node": target_id_value, "port": target_port},
            "kind": "control" if relation.kind == "activation" else relation.kind,
        }
        if relation.feedback is not None:
            raw_edge["feedback"] = relation.feedback.model_dump(mode="python")
        add_edge(
            raw_edge,
            owner_kind="relation",
            owner_id=relation.canvas_id,
            canvas_edge_id=relation.canvas_id,
        )

    for action_id, request_id in action_request_by_id.items():
        primary_observe_id = next(iter(observe_by_perception.values()), None)
        if primary_observe_id is not None:
            add_edge(
                {
                    "source": {"node": primary_observe_id, "port": "observation"},
                    "target": {"node": request_id, "port": "observation"},
                    "kind": "data",
                },
                owner_kind="capability",
                owner_id=action_id,
            )
        add_edge(
            {
                "source": {"node": request_id, "port": "request"},
                "target": {"node": action_id, "port": "request"},
                "kind": "data",
            },
            owner_kind="capability",
            owner_id=action_id,
        )

    presentations: dict[str, NodePresentation] = {}
    for boundary in (parsed.input, parsed.output):
        presentation = parsed.presentation.nodes.get(boundary.canvas_id)
        if presentation is not None:
            presentations[boundary.logical_id] = NodePresentation(
                x=presentation.x,
                y=presentation.y,
                label="Input" if boundary.kind == "input" else "Output",
                icon=presentation.icon,
                description=presentation.description,
            )
    for node in parsed.capabilities:
        presentation = parsed.presentation.nodes.get(node.canvas_id)
        if presentation is not None:
            presentations[node.logical_id] = NodePresentation(
                x=presentation.x,
                y=presentation.y,
                label=presentation.label,
                icon=presentation.icon,
                description=presentation.description,
            )
    raw_graph = {
        "schema_version": 1,
        "contract_version": "1.1",
        "profile": "mobile_agent",
        "nodes": nodes,
        "edges": edges,
        "policies": {
            "max_steps": min(parsed.policies.max_steps, 1000),
            "max_feedback_iterations": max(
                1, min(parsed.policies.max_feedback_iterations, 10)
            ),
        },
        "presentation": GraphPresentation(
            flow_id=parsed.document_id,
            flow_name=parsed.name,
            created_at=parsed.authoring.created_at,
            updated_at=parsed.authoring.updated_at,
            nodes=presentations,
        ).model_dump(mode="python"),
    }
    try:
        graph = AgentGraph.model_validate(raw_graph)
    except ValidationError as error:
        issues.extend(
            diagnostics_from_validation_error(
                error,
                code="graph.studio.lowered_graph_invalid",
                source_prefix=source_id,
            )
        )
        graph = None
    base = finish_compilation(
        graph,
        issues,
        source_map,
        contract_catalog=contract_catalog,
        graph_catalog=graph_catalog,
    )
    return StudioCapabilityCompilationResult(
        graph=base.graph if base.is_success else None,
        diagnostics=base.diagnostics,
        source_map=base.source_map,
        authoring_policy=STUDIO_CAPABILITY_AUTHORING_POLICY,
        lowering_profile=STUDIO_CAPABILITY_LOWERING_PROFILE,
        capability_hash=capability_hash,
        projection_map=tuple(projections),
    )


def compile_studio_flow_document(
    document: Mapping[str, Any],
    *,
    source_id: str = "studio-flow",
    contract_catalog: Any = None,
    graph_catalog: Any = None,
    component_catalog: Any = None,
    expected_catalog_version: str | None = None,
    catalog_version: str | None = None,
) -> CompilationResult:
    """Compile Studio schema 3/2 or retain the explicit schema 1 path.

    Args:
        document (Mapping[str, Any]): Parsed Studio document mapping.
        source_id (str): Stable source identity for diagnostics.
        contract_catalog (Any): Explicit NodeContract extension catalog.
        graph_catalog (Any): Explicit immutable graph catalog.
        component_catalog (Any): Explicit Studio Component Catalog.
        expected_catalog_version (str | None): Client-observed Catalog version.
        catalog_version (str | None): Current server Catalog version.

    Raises:
        None.

    Returns:
        CompilationResult: Compiled graph or deterministic diagnostics.
    """
    schema_version = document.get("schemaVersion", document.get("schema_version"))
    if schema_version == 3:
        return _compile_schema3_capability_document(
            document,
            source_id=source_id,
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
            component_catalog=component_catalog,
            expected_catalog_version=expected_catalog_version,
            catalog_version=catalog_version,
        )
    if schema_version == 2:
        return _compile_schema2_studio_document(
            document,
            source_id=source_id,
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
            component_catalog=component_catalog,
            expected_catalog_version=expected_catalog_version,
            catalog_version=catalog_version,
        )
    return _compile_legacy_studio_flow_document(document, source_id=source_id)
