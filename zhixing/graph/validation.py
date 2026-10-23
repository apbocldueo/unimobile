"""Deterministic, side-effect-free validation for AgentGraph V1."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from .diagnostics import GraphDiagnostic, GraphValidationResult, sorted_diagnostics
from .enums import (
    DataTypeId,
    DiagnosticSeverity,
    EdgeKind,
    GraphRole,
    NodeKind,
    PortCardinality,
    PortDirection,
    PredicateOperator,
)
from .contracts import (
    BUILTIN_NODE_CONTRACT_CATALOG,
    NodeContractCatalog,
    SideEffectKind,
    contract_ref_for_role,
)
from .models import AgentGraph, GraphEdge, Predicate
from .ports import contract_ports_for_node, port_for_node, ports_for_node


_KNOWN_FIELDS: dict[DataTypeId, dict[str, type]] = {
    DataTypeId.VERIFIER_RESULT: {
        "is_success": bool,
        "feedback": str,
        "score": float,
        "should_retry": bool,
        "correction_suggestion": object,
        "metadata": dict,
    },
    DataTypeId.ACTION_RESULT: {
        "status": str,
        "message": str,
        "error": str,
        "metadata": dict,
    },
    DataTypeId.CONTROL: {"branch": str},
}
_NUMERIC_OPERATORS = {
    PredicateOperator.GT,
    PredicateOperator.GTE,
    PredicateOperator.LT,
    PredicateOperator.LTE,
}


def _diag(
    code: str,
    message: str,
    *,
    path: tuple[str | int, ...] = (),
    node_id: str | None = None,
    edge_index: int | None = None,
    port_id: str | None = None,
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
) -> GraphDiagnostic:
    return GraphDiagnostic(
        code=code,
        message=message,
        path=path,
        node_id=node_id,
        edge_index=edge_index,
        port_id=port_id,
        severity=severity,
    )


def _compatible(source_types: tuple[DataTypeId, ...], target_types: tuple[DataTypeId, ...]) -> bool:
    return bool(set(source_types) & set(target_types))


def _validate_predicate(
    predicate: Predicate,
    data_types: tuple[DataTypeId, ...],
    *,
    path: tuple[str | int, ...],
    node_id: str | None = None,
    edge_index: int | None = None,
) -> list[GraphDiagnostic]:
    issues: list[GraphDiagnostic] = []
    root = predicate.field.split(".", 1)[0]
    candidate_types: list[type] = []
    known_schema = False
    for data_type in data_types:
        fields = _KNOWN_FIELDS.get(data_type)
        if fields is None:
            continue
        known_schema = True
        if root in fields:
            candidate_types.append(fields[root])
    if known_schema and not candidate_types:
        issues.append(
            _diag(
                "graph.predicate.field_unknown",
                f"predicate field {predicate.field!r} is not defined for {[item.value for item in data_types]}",
                path=path + ("field",),
                node_id=node_id,
                edge_index=edge_index,
            )
        )
        return issues
    if predicate.operator in _NUMERIC_OPERATORS:
        if not isinstance(predicate.value, (int, float)) or isinstance(predicate.value, bool):
            issues.append(
                _diag(
                    "graph.predicate.value_type",
                    f"operator {predicate.operator.value!r} requires a numeric comparison value",
                    path=path + ("value",),
                    node_id=node_id,
                    edge_index=edge_index,
                )
            )
        if candidate_types and not all(item in {int, float} for item in candidate_types):
            issues.append(
                _diag(
                    "graph.predicate.field_type",
                    f"operator {predicate.operator.value!r} requires a numeric field",
                    path=path + ("operator",),
                    node_id=node_id,
                    edge_index=edge_index,
                )
            )
    if predicate.operator in {PredicateOperator.EQ, PredicateOperator.NE} and candidate_types:
        field_type = candidate_types[0]
        if field_type is bool and not isinstance(predicate.value, bool):
            issues.append(
                _diag(
                    "graph.predicate.value_type",
                    "boolean field comparison requires a boolean value",
                    path=path + ("value",),
                    node_id=node_id,
                    edge_index=edge_index,
                )
            )
    return issues


def _find_cycle(adjacency: dict[str, set[str]], nodes: Iterable[str]) -> list[str] | None:
    state: dict[str, int] = {}
    stack: list[str] = []
    positions: dict[str, int] = {}

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        positions[node] = len(stack)
        stack.append(node)
        for nxt in sorted(adjacency.get(node, ())):
            if state.get(nxt, 0) == 0:
                found = visit(nxt)
                if found:
                    return found
            elif state.get(nxt) == 1:
                return stack[positions[nxt] :] + [nxt]
        stack.pop()
        positions.pop(node, None)
        state[node] = 2
        return None

    for node in sorted(nodes):
        if state.get(node, 0) == 0:
            found = visit(node)
            if found:
                return found
    return None


def _find_path(adjacency: dict[str, set[str]], start: str, goal: str) -> list[str] | None:
    queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
    seen = {start}
    while queue:
        current, path = queue.popleft()
        if current == goal:
            return path
        for nxt in sorted(adjacency.get(current, ())):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))
    return None


def _validate_v10(graph: AgentGraph) -> GraphValidationResult:
    issues: list[GraphDiagnostic] = []
    nodes_by_id: dict[str, object] = {}
    duplicate_ids: set[str] = set()
    for index, node in enumerate(graph.nodes):
        if node.id in nodes_by_id:
            duplicate_ids.add(node.id)
            issues.append(
                _diag(
                    "graph.node.duplicate_id",
                    f"duplicate logical node id {node.id!r}",
                    path=("nodes", index, "id"),
                    node_id=node.id,
                )
            )
        else:
            nodes_by_id[node.id] = node

    inbound_by_port: dict[tuple[str, str], list[int]] = defaultdict(list)
    all_adjacency: dict[str, set[str]] = defaultdict(set)
    ordinary_adjacency: dict[str, set[str]] = defaultdict(set)
    valid_edge_endpoints: dict[int, tuple[object, object, object, object]] = {}

    for index, edge in enumerate(graph.edges):
        source_node = nodes_by_id.get(edge.source.node)
        target_node = nodes_by_id.get(edge.target.node)
        if source_node is None:
            issues.append(
                _diag(
                    "graph.edge.source_node_unknown",
                    f"unknown source node {edge.source.node!r}",
                    path=("edges", index, "source", "node"),
                    edge_index=index,
                )
            )
        if target_node is None:
            issues.append(
                _diag(
                    "graph.edge.target_node_unknown",
                    f"unknown target node {edge.target.node!r}",
                    path=("edges", index, "target", "node"),
                    edge_index=index,
                )
            )
        if source_node is None or target_node is None:
            continue
        source_port = port_for_node(source_node, edge.source.port)
        target_port = port_for_node(target_node, edge.target.port)
        if source_port is None:
            issues.append(
                _diag(
                    "graph.edge.source_port_unknown",
                    f"unknown source port {edge.source.port!r}",
                    path=("edges", index, "source", "port"),
                    node_id=edge.source.node,
                    edge_index=index,
                    port_id=edge.source.port,
                )
            )
        if target_port is None:
            issues.append(
                _diag(
                    "graph.edge.target_port_unknown",
                    f"unknown target port {edge.target.port!r}",
                    path=("edges", index, "target", "port"),
                    node_id=edge.target.node,
                    edge_index=index,
                    port_id=edge.target.port,
                )
            )
        if source_port is None or target_port is None:
            continue
        valid_edge_endpoints[index] = (source_node, target_node, source_port, target_port)
        if source_port.direction != PortDirection.OUTPUT or target_port.direction != PortDirection.INPUT:
            issues.append(
                _diag(
                    "graph.edge.direction_invalid",
                    "edges must connect an output port to an input port",
                    path=("edges", index),
                    edge_index=index,
                )
            )
            continue
        inbound_by_port[(edge.target.node, edge.target.port)].append(index)
        all_adjacency[edge.source.node].add(edge.target.node)
        if edge.kind != EdgeKind.FEEDBACK:
            ordinary_adjacency[edge.source.node].add(edge.target.node)

        compatible = _compatible(source_port.data_types, target_port.data_types)
        if not compatible:
            issues.append(
                _diag(
                    "graph.edge.type_incompatible",
                    "source types "
                    f"{[item.value for item in source_port.data_types]} are not accepted by "
                    f"{[item.value for item in target_port.data_types]}",
                    path=("edges", index),
                    edge_index=index,
                )
            )
        if edge.kind == EdgeKind.DATA and DataTypeId.CONTROL in source_port.data_types:
            issues.append(
                _diag(
                    "graph.edge.data_uses_control",
                    "control values must use a control edge",
                    path=("edges", index, "kind"),
                    edge_index=index,
                )
            )
        if edge.kind == EdgeKind.CONTROL and (
            DataTypeId.CONTROL not in source_port.data_types
            or DataTypeId.CONTROL not in target_port.data_types
        ):
            issues.append(
                _diag(
                    "graph.edge.control_type_invalid",
                    "control edge must connect control ports",
                    path=("edges", index),
                    edge_index=index,
                )
            )
        if edge.kind == EdgeKind.FEEDBACK and edge.feedback is not None:
            if edge.feedback.max_iterations > graph.policies.max_feedback_iterations:
                issues.append(
                    _diag(
                        "graph.feedback.graph_limit_exceeded",
                        "feedback max_iterations exceeds graph policy",
                        path=("edges", index, "feedback", "max_iterations"),
                        edge_index=index,
                    )
                )
            issues.extend(
                _validate_predicate(
                    edge.feedback.predicate,
                    source_port.data_types,
                    path=("edges", index, "feedback", "predicate"),
                    edge_index=index,
                )
            )
        if edge.condition is not None:
            issues.extend(
                _validate_predicate(
                    edge.condition,
                    source_port.data_types,
                    path=("edges", index, "condition"),
                    edge_index=index,
                )
            )

    for node in graph.nodes:
        for port in ports_for_node(node):
            incoming = inbound_by_port.get((node.id, port.id), [])
            if port.direction == PortDirection.INPUT and port.required and not incoming:
                issues.append(
                    _diag(
                        "graph.port.required_missing",
                        f"required input port {node.id}.{port.id} has no source",
                        path=("nodes", node.id, "ports", port.id),
                        node_id=node.id,
                        port_id=port.id,
                    )
                )
            if port.cardinality == PortCardinality.SINGLE and len(incoming) > 1:
                issues.append(
                    _diag(
                        "graph.port.cardinality_exceeded",
                        f"single input port {node.id}.{port.id} has {len(incoming)} edges {incoming}",
                        path=("nodes", node.id, "ports", port.id),
                        node_id=node.id,
                        port_id=port.id,
                    )
                )

    role_nodes: dict[GraphRole, list[object]] = defaultdict(list)
    for node in graph.nodes:
        if node.kind == NodeKind.COMPONENT and node.role is not None:
            role_nodes[node.role].append(node)
    for required_role in (GraphRole.PERCEPTION, GraphRole.REASONING):
        if not role_nodes[required_role]:
            issues.append(
                _diag(
                    "graph.profile.required_role_missing",
                    f"mobile_agent requires role {required_role.value!r}",
                    path=("nodes",),
                )
            )
    action_nodes = role_nodes[GraphRole.ACTION_EXECUTOR]
    primary_actions = [node for node in action_nodes if node.primary]
    if len(action_nodes) == 1 and not primary_actions:
        primary_actions = action_nodes
    if len(primary_actions) != 1:
        issues.append(
            _diag(
                "graph.profile.primary_action_executor",
                "mobile_agent requires exactly one primary action_executor",
                path=("nodes",),
            )
        )
    input_nodes = [node for node in graph.nodes if node.kind == NodeKind.INPUT]
    if not input_nodes:
        issues.append(
            _diag(
                "graph.profile.input_missing",
                "mobile_agent requires a task/observation input node",
                path=("nodes",),
            )
        )

    # Reachability includes feedback so valid retry targets remain reachable.
    starts = sorted(node.id for node in input_nodes)
    reachable: set[str] = set(starts)
    queue = deque(starts)
    while queue:
        current = queue.popleft()
        for nxt in sorted(all_adjacency.get(current, ())):
            if nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)
    for node in graph.nodes:
        if node.id not in reachable:
            issues.append(
                _diag(
                    "graph.reachability.unreachable_node",
                    f"node {node.id!r} is unreachable from graph input",
                    path=("nodes", node.id),
                    node_id=node.id,
                )
            )

    terminal_ids = {
        node.id
        for node in graph.nodes
        if node.kind == NodeKind.OUTPUT or node.role == GraphRole.ACTION_EXECUTOR
    }
    reverse: dict[str, set[str]] = defaultdict(set)
    for source, targets in all_adjacency.items():
        for target in targets:
            reverse[target].add(source)
    can_finish = set(terminal_ids)
    queue = deque(sorted(terminal_ids))
    while queue:
        current = queue.popleft()
        for previous in sorted(reverse.get(current, ())):
            if previous not in can_finish:
                can_finish.add(previous)
                queue.append(previous)
    for node in graph.nodes:
        if node.kind == NodeKind.COMPONENT and node.id not in can_finish:
            issues.append(
                _diag(
                    "graph.reachability.non_terminating_dead_end",
                    f"component node {node.id!r} cannot reach action execution or output",
                    path=("nodes", node.id),
                    node_id=node.id,
                )
            )

    for node in graph.nodes:
        if node.kind == NodeKind.CONDITION:
            input_edges = inbound_by_port.get((node.id, "value"), [])
            input_types: tuple[DataTypeId, ...] = ()
            if input_edges:
                endpoint = valid_edge_endpoints.get(input_edges[0])
                if endpoint:
                    input_types = endpoint[2].data_types
            issues.extend(
                _validate_predicate(
                    node.predicate,
                    input_types,
                    path=("nodes", node.id, "predicate"),
                    node_id=node.id,
                )
            )
            for branch in ("true", "false"):
                if not any(
                    edge.source.node == node.id and edge.source.port == branch
                    for edge in graph.edges
                ):
                    issues.append(
                        _diag(
                            "graph.condition.branch_unconnected",
                            f"condition branch {node.id}.{branch} is unconnected",
                            path=("nodes", node.id, "ports", branch),
                            node_id=node.id,
                            port_id=branch,
                            severity=DiagnosticSeverity.WARNING,
                        )
                    )

    cycle = _find_cycle(ordinary_adjacency, nodes_by_id)
    if cycle:
        issues.append(
            _diag(
                "graph.cycle.ordinary",
                "ordinary data/control edges form a cycle: " + " -> ".join(cycle),
                path=("edges",),
            )
        )

    feedback_paths: list[tuple[int, set[str]]] = []
    for index, edge in enumerate(graph.edges):
        if edge.kind != EdgeKind.FEEDBACK:
            continue
        path = _find_path(ordinary_adjacency, edge.target.node, edge.source.node)
        if path is None:
            issues.append(
                _diag(
                    "graph.feedback.return_path_missing",
                    "feedback target cannot reach its source through ordinary edges",
                    path=("edges", index),
                    edge_index=index,
                )
            )
        else:
            feedback_paths.append((index, set(path)))
    for left_index in range(len(feedback_paths)):
        edge_a, path_a = feedback_paths[left_index]
        for right_index in range(left_index + 1, len(feedback_paths)):
            edge_b, path_b = feedback_paths[right_index]
            overlap = sorted(path_a & path_b)
            if overlap:
                issues.append(
                    _diag(
                        "graph.feedback.overlap_unsupported",
                        f"feedback edges {edge_a} and {edge_b} overlap at {overlap}",
                        path=("edges", edge_b),
                        edge_index=edge_b,
                    )
                )

    return GraphValidationResult(diagnostics=sorted_diagnostics(issues))


def _types_compatible(source_types: tuple[str, ...], target_types: tuple[str, ...]) -> bool:
    """Check contract 1.1 type compatibility with the explicit ``any`` top type.

    Args:
        source_types (tuple[str, ...]): Source output types.
        target_types (tuple[str, ...]): Target input types.

    Raises:
        None.

    Returns:
        bool: True when at least one type is assignable.
    """
    return "any" in source_types or "any" in target_types or bool(set(source_types) & set(target_types))


def _resolve_composed_graph(specification, graph_catalog):
    """Resolve an inline or content-addressed composed graph.

    Args:
        specification (SubgraphSpec): Inline/reference subgraph declaration.
        graph_catalog (GraphCatalog | None): Explicit graph catalog.

    Raises:
        ValueError: A catalog hash does not match its pinned reference.

    Returns:
        AgentGraph | None: Resolved graph, when available.
    """
    if specification.graph is not None:
        return specification.graph
    if graph_catalog is None or specification.reference is None:
        return None
    return graph_catalog.resolve(specification.reference)


def _validate_v11(
    graph: AgentGraph,
    *,
    contract_catalog: NodeContractCatalog,
    graph_catalog=None,
    path_prefix: tuple[str | int, ...] = (),
    ancestors: tuple[str, ...] = (),
    depth: int = 0,
) -> GraphValidationResult:
    """Validate a contract 1.1 graph and its hierarchical composition.

    Args:
        graph (AgentGraph): Contract 1.1 graph to validate.
        contract_catalog (NodeContractCatalog): Explicit merged contract catalog.
        graph_catalog (GraphCatalog | None): Explicit content-addressed graph catalog.
        path_prefix (tuple[str | int, ...]): Stable parent diagnostic path.
        ancestors (tuple[str, ...]): Semantic hashes of ancestor graphs.
        depth (int): Current subgraph nesting depth.

    Raises:
        None.

    Returns:
        GraphValidationResult: Deterministically ordered diagnostics.
    """
    issues: list[GraphDiagnostic] = []
    nodes_by_id: dict[str, object] = {}
    for index, node in enumerate(graph.nodes):
        if node.id in nodes_by_id:
            issues.append(
                _diag(
                    "graph.node.duplicate_id",
                    f"duplicate logical node id {node.id!r}",
                    path=path_prefix + ("nodes", index, "id"),
                    node_id=node.id,
                )
            )
        else:
            nodes_by_id[node.id] = node

    if depth > graph.policies.max_nesting_depth:
        issues.append(
            _diag(
                "graph.composition.max_depth",
                "subgraph nesting exceeds graph policy",
                path=path_prefix,
            )
        )
        return GraphValidationResult(diagnostics=sorted_diagnostics(issues))

    ports_by_node: dict[str, dict[str, object]] = {}
    for index, node in enumerate(graph.nodes):
        if node.kind is NodeKind.COMPONENT:
            reference = node.contract
            if reference is None and node.role is not None:
                reference = contract_ref_for_role(node.role)
            if reference is None:
                issues.append(
                    _diag(
                        "graph.contract.missing",
                        "component node requires an explicit or legacy-mapped contract",
                        path=path_prefix + ("nodes", index, "contract"),
                        node_id=node.id,
                    )
                )
            else:
                contract = contract_catalog.resolve(reference)
                if contract is None:
                    issues.append(
                        _diag(
                            "graph.contract.unknown",
                            f"unknown node contract {reference.id}@{reference.version}",
                            path=path_prefix + ("nodes", index, "contract"),
                            node_id=node.id,
                        )
                    )
                else:
                    if node.role is not None and contract.core_role not in {None, node.role}:
                        issues.append(
                            _diag(
                                "graph.contract.role_mismatch",
                                "legacy role does not match the referenced core contract",
                                path=path_prefix + ("nodes", index, "contract"),
                                node_id=node.id,
                            )
                        )
                    if (
                        node.component is not None
                        and node.component.policy.value == "fallback"
                        and contract.side_effect is not SideEffectKind.NONE
                        and not contract.idempotent
                    ):
                        issues.append(
                            _diag(
                                "graph.contract.unsafe_fallback",
                                "non-idempotent side-effect contract cannot switch after invocation",
                                path=path_prefix + ("nodes", index, "component", "policy"),
                                node_id=node.id,
                                severity=DiagnosticSeverity.WARNING,
                            )
                        )
        ports_by_node[node.id] = {
            port.id: port for port in contract_ports_for_node(node, contract_catalog)
        }

    inbound: dict[tuple[str, str], list[int]] = defaultdict(list)
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge_index, edge in enumerate(graph.edges):
        source = nodes_by_id.get(edge.source.node)
        target = nodes_by_id.get(edge.target.node)
        if source is None:
            issues.append(
                _diag(
                    "graph.edge.source_node_unknown",
                    f"unknown source node {edge.source.node!r}",
                    path=path_prefix + ("edges", edge_index, "source", "node"),
                    edge_index=edge_index,
                )
            )
        if target is None:
            issues.append(
                _diag(
                    "graph.edge.target_node_unknown",
                    f"unknown target node {edge.target.node!r}",
                    path=path_prefix + ("edges", edge_index, "target", "node"),
                    edge_index=edge_index,
                )
            )
        if source is None or target is None:
            continue
        source_port = ports_by_node.get(edge.source.node, {}).get(edge.source.port)
        target_port = ports_by_node.get(edge.target.node, {}).get(edge.target.port)
        if source_port is None:
            issues.append(
                _diag(
                    "graph.edge.source_port_unknown",
                    f"unknown source port {edge.source.port!r}",
                    path=path_prefix + ("edges", edge_index, "source", "port"),
                    node_id=edge.source.node,
                    edge_index=edge_index,
                    port_id=edge.source.port,
                )
            )
        if target_port is None:
            issues.append(
                _diag(
                    "graph.edge.target_port_unknown",
                    f"unknown target port {edge.target.port!r}",
                    path=path_prefix + ("edges", edge_index, "target", "port"),
                    node_id=edge.target.node,
                    edge_index=edge_index,
                    port_id=edge.target.port,
                )
            )
        if source_port is None or target_port is None:
            continue
        if source_port.direction is not PortDirection.OUTPUT or target_port.direction is not PortDirection.INPUT:
            issues.append(
                _diag(
                    "graph.edge.direction_invalid",
                    "edges must connect an output port to an input port",
                    path=path_prefix + ("edges", edge_index),
                    edge_index=edge_index,
                )
            )
            continue
        if not _types_compatible(source_port.data_types, target_port.data_types):
            issues.append(
                _diag(
                    "graph.edge.type_incompatible",
                    f"source types {list(source_port.data_types)} are not accepted by {list(target_port.data_types)}",
                    path=path_prefix + ("edges", edge_index),
                    edge_index=edge_index,
                )
            )
        if edge.kind is EdgeKind.FEEDBACK and edge.feedback is not None:
            if edge.feedback.max_iterations > graph.policies.max_feedback_iterations:
                issues.append(
                    _diag(
                        "graph.feedback.graph_limit_exceeded",
                        "feedback max_iterations exceeds graph policy",
                        path=path_prefix + (
                            "edges",
                            edge_index,
                            "feedback",
                            "max_iterations",
                        ),
                        edge_index=edge_index,
                    )
                )
        inbound[(edge.target.node, edge.target.port)].append(edge_index)
        if edge.kind is not EdgeKind.FEEDBACK:
            adjacency[edge.source.node].add(edge.target.node)

    for node in graph.nodes:
        for port in ports_by_node.get(node.id, {}).values():
            incoming = inbound.get((node.id, port.id), [])
            if port.direction is PortDirection.INPUT and port.required and not incoming:
                issues.append(
                    _diag(
                        "graph.port.required_missing",
                        f"required input port {node.id}.{port.id} has no source",
                        path=path_prefix + ("nodes", node.id, "ports", port.id),
                        node_id=node.id,
                        port_id=port.id,
                    )
                )
            if port.cardinality is PortCardinality.SINGLE and len(incoming) > 1:
                issues.append(
                    _diag(
                        "graph.port.cardinality_exceeded",
                        f"single input port {node.id}.{port.id} has multiple sources",
                        path=path_prefix + ("nodes", node.id, "ports", port.id),
                        node_id=node.id,
                        port_id=port.id,
                    )
                )

    input_nodes = [node for node in graph.nodes if node.kind is NodeKind.INPUT]
    if not input_nodes:
        issues.append(
            _diag(
                "graph.profile.input_missing",
                "contract 1.1 graph requires at least one input node",
                path=path_prefix + ("nodes",),
            )
        )
    reachable = {node.id for node in input_nodes}
    queue = deque(sorted(reachable))
    while queue:
        current = queue.popleft()
        for target in sorted(adjacency.get(current, ())):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    for node in graph.nodes:
        if node.id not in reachable:
            issues.append(
                _diag(
                    "graph.reachability.unreachable_node",
                    f"node {node.id!r} is unreachable from graph input",
                    path=path_prefix + ("nodes", node.id),
                    node_id=node.id,
                )
            )

    cycle = _find_cycle(adjacency, nodes_by_id)
    if cycle:
        issues.append(
            _diag(
                "graph.cycle.ordinary",
                "ordinary data/control edges form a cycle: " + " -> ".join(cycle),
                path=path_prefix + ("edges",),
            )
        )

    for edge_index, edge in enumerate(graph.edges):
        if edge.kind is not EdgeKind.FEEDBACK:
            continue
        if _find_path(adjacency, edge.target.node, edge.source.node) is None:
            issues.append(
                _diag(
                    "graph.feedback.return_path_missing",
                    "feedback target cannot reach its source through ordinary edges",
                    path=path_prefix + ("edges", edge_index),
                    edge_index=edge_index,
                )
            )

    # Local loops and subgraphs own their cycles, so their bodies are validated recursively.
    for node in graph.nodes:
        specification = node.loop.body if node.kind is NodeKind.LOOP and node.loop else node.subgraph
        if specification is None:
            continue
        try:
            child = _resolve_composed_graph(specification, graph_catalog)
        except ValueError as error:
            issues.append(
                _diag(
                    "graph.subgraph.hash_mismatch",
                    str(error),
                    path=path_prefix + ("nodes", node.id),
                    node_id=node.id,
                )
            )
            continue
        if child is None:
            issues.append(
                _diag(
                    "graph.subgraph.reference_unresolved",
                    "subgraph reference is not available in the explicit GraphCatalog",
                    path=path_prefix + ("nodes", node.id),
                    node_id=node.id,
                )
            )
            continue
        parent_inputs = set(specification.inputs)
        parent_outputs = set(specification.outputs)
        declared_parent_ports = set(ports_by_node.get(node.id, {}))
        for parent_port in sorted((parent_inputs | parent_outputs) - declared_parent_ports):
            issues.append(
                _diag(
                    "graph.subgraph.parent_port_unknown",
                    f"subgraph mapping references unknown parent port {parent_port!r}",
                    path=path_prefix + ("nodes", node.id),
                    node_id=node.id,
                    port_id=parent_port,
                )
            )
        child_inputs = (
            {port.id for port in child.interface.inputs}
            if child.interface is not None and child.interface.inputs
            else {"task", "observation", "value"}
        )
        child_outputs = (
            {port.id for port in child.interface.outputs}
            if child.interface is not None and child.interface.outputs
            else {"result", "control"}
        )
        for child_port in sorted(set(specification.inputs.values()) - child_inputs):
            issues.append(
                _diag(
                    "graph.subgraph.child_input_unknown",
                    f"subgraph mapping references unknown child input {child_port!r}",
                    path=path_prefix + ("nodes", node.id),
                    node_id=node.id,
                    port_id=child_port,
                )
            )
        for child_port in sorted(set(specification.outputs.values()) - child_outputs):
            issues.append(
                _diag(
                    "graph.subgraph.child_output_unknown",
                    f"subgraph mapping references unknown child output {child_port!r}",
                    path=path_prefix + ("nodes", node.id),
                    node_id=node.id,
                    port_id=child_port,
                )
            )
        # A stable model dump detects direct/indirect object recursion without invoking canonicalization.
        identity = f"{id(child)}"
        if identity in ancestors or child is graph:
            issues.append(
                _diag(
                    "graph.subgraph.recursive",
                    "recursive subgraph composition is not supported",
                    path=path_prefix + ("nodes", node.id),
                    node_id=node.id,
                )
            )
            continue
        child_result = _validate_v11(
            child,
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
            path_prefix=path_prefix + ("nodes", node.id, "graph"),
            ancestors=ancestors + (f"{id(graph)}",),
            depth=depth + 1,
        )
        issues.extend(child_result.diagnostics)
        if node.kind is NodeKind.LOOP and node.loop is not None:
            if node.loop.max_iterations * node.loop.body.max_activations > node.loop.max_activations:
                issues.append(
                    _diag(
                        "graph.loop.activation_budget_exceeded",
                        "loop iterations can exceed the declared local activation budget",
                        path=path_prefix + ("nodes", node.id, "loop", "max_activations"),
                        node_id=node.id,
                    )
                )

    return GraphValidationResult(diagnostics=sorted_diagnostics(issues))


def validate_graph(
    graph: AgentGraph,
    *,
    contract_catalog: NodeContractCatalog | None = None,
    graph_catalog=None,
) -> GraphValidationResult:
    """Validate either the immutable V1 contract or generalized contract 1.1.

    Args:
        graph (AgentGraph): Graph to validate.
        contract_catalog (NodeContractCatalog | None): Explicit extension-aware catalog.
        graph_catalog (GraphCatalog | None): Explicit content-addressed subgraph catalog.

    Raises:
        None.

    Returns:
        GraphValidationResult: Deterministically ordered diagnostics.
    """
    if graph.contract_version == "1.0":
        return _validate_v10(graph)
    if graph.contract_version != "1.1":
        return GraphValidationResult(
            diagnostics=(
                _diag(
                    "graph.contract_version.unsupported",
                    f"unsupported AgentGraph contract version {graph.contract_version!r}",
                    path=("contract_version",),
                ),
            )
        )
    catalog = BUILTIN_NODE_CONTRACT_CATALOG
    if contract_catalog is not None:
        try:
            catalog = catalog.merge(contract_catalog)
        except ValueError as error:
            return GraphValidationResult(
                diagnostics=(
                    _diag(
                        "graph.contract.catalog_conflict",
                        str(error),
                        path=("contracts",),
                    ),
                )
            )
    return _validate_v11(
        graph,
        contract_catalog=catalog,
        graph_catalog=graph_catalog,
    )
