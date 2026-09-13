from __future__ import annotations

import yaml

from zhixing.graph import (
    AgentGraph,
    BUILTIN_NODE_CONTRACT_CATALOG,
    ComponentBinding,
    ContractPort,
    EdgeKind,
    GraphComponentRef,
    GraphCatalog,
    GraphEdge,
    GraphNode,
    InvocationAdapterKind,
    NodeContract,
    NodeContractCatalog,
    NodeContractRef,
    NodeKind,
    NodeLifecycle,
    PortAddress,
    PortDirection,
    SubgraphReference,
    SubgraphSpec,
    compile_graph_yaml_data,
    planner_execute_template,
    react_template,
)

from .helpers import make_golden_graph


def _edge(source: str, source_port: str, target: str, target_port: str) -> GraphEdge:
    """Create one data edge for generalized graph fixtures.

    Args:
        source (str): Source node ID.
        source_port (str): Source output port.
        target (str): Target node ID.
        target_port (str): Target input port.

    Raises:
        ValueError: GraphEdge validation fails.

    Returns:
        GraphEdge: Validated data edge.
    """
    return GraphEdge(
        source=PortAddress(node=source, port=source_port),
        target=PortAddress(node=target, port=target_port),
        kind=EdgeKind.DATA,
    )


def _binding(name: str) -> ComponentBinding:
    """Create one single-candidate test binding.

    Args:
        name (str): Component name.

    Raises:
        ValueError: ComponentBinding validation fails.

    Returns:
        ComponentBinding: Test binding.
    """
    return ComponentBinding(
        candidates=(GraphComponentRef(namespace="test.extension", name=name),)
    )


def test_contract_10_serialization_and_hash_remain_frozen() -> None:
    """Assert additive contract 1.1 work does not alter published V1 identity.

    Args:
        None.

    Raises:
        AssertionError: V1 serialization or hash changes.

    Returns:
        None.
    """
    graph = make_golden_graph()
    assert graph.canonical_hash() == "sha256:3cadf8a4ec2a556bcfe025cb1649e3f24ae7e03eed36f399133bfca8f8638e83"
    assert graph.model_dump(mode="json")["policies"] == {
        "max_steps": 15,
        "max_feedback_iterations": 3,
    }
    assert all("contract" not in node for node in graph.model_dump(mode="json")["nodes"])


def test_explicit_catalog_supports_multiple_nodes_and_rejects_conflicts() -> None:
    """Verify extension catalogs are explicit, reusable, and conflict safe.

    Args:
        None.

    Raises:
        AssertionError: Catalog conflict or multi-node behavior is incorrect.

    Returns:
        None.
    """
    reference = NodeContractRef(id="example.rank", version="1.0")
    contract = NodeContract(
        ref=reference,
        ports=(
            ContractPort(
                id="value",
                direction=PortDirection.INPUT,
                data_types=("text",),
                required=True,
            ),
            ContractPort(
                id="result",
                direction=PortDirection.OUTPUT,
                data_types=("text",),
            ),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    )
    extension = NodeContractCatalog((contract,))
    merged = BUILTIN_NODE_CONTRACT_CATALOG.merge(extension)
    assert merged.resolve(reference) == contract

    conflicting = contract.model_copy(
        update={
            "ports": (
                ContractPort(
                    id="value",
                    direction=PortDirection.INPUT,
                    data_types=("number",),
                    required=True,
                ),
            )
        }
    )
    try:
        extension.merge(NodeContractCatalog((conflicting,)))
    except ValueError as error:
        assert "conflicting node contract" in str(error)
    else:
        raise AssertionError("conflicting explicit catalogs must be rejected")

    graph = AgentGraph(
        contract_version="1.1",
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, lifecycle=NodeLifecycle.ON_RUN_START),
            GraphNode(
                id="rank_a",
                kind=NodeKind.COMPONENT,
                contract=reference,
                lifecycle=NodeLifecycle.PER_STEP,
                component=_binding("rank_a"),
            ),
            GraphNode(
                id="rank_b",
                kind=NodeKind.COMPONENT,
                contract=reference,
                lifecycle=NodeLifecycle.PER_STEP,
                component=_binding("rank_b"),
            ),
            GraphNode(id="output", kind=NodeKind.OUTPUT, lifecycle=NodeLifecycle.TERMINAL),
        ),
        edges=(
            _edge("input", "value", "rank_a", "value"),
            _edge("rank_a", "result", "rank_b", "value"),
            _edge("rank_b", "result", "output", "result"),
        ),
    )
    assert graph.validate_graph(contract_catalog=extension).is_valid


def test_unknown_extension_contract_has_stable_node_path_diagnostic() -> None:
    """Ensure compiler diagnostics do not instantiate or stringify components.

    Args:
        None.

    Raises:
        AssertionError: Unknown-contract diagnostics lack stable paths.

    Returns:
        None.
    """
    graph = AgentGraph(
        contract_version="1.1",
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, lifecycle=NodeLifecycle.ON_RUN_START),
            GraphNode(
                id="custom",
                kind=NodeKind.COMPONENT,
                contract=NodeContractRef(id="missing.contract", version="9.0"),
                lifecycle=NodeLifecycle.PER_STEP,
                component=_binding("must_not_resolve"),
            ),
            GraphNode(id="output", kind=NodeKind.OUTPUT, lifecycle=NodeLifecycle.TERMINAL),
        ),
        edges=(),
    )
    diagnostic = next(
        item
        for item in graph.validate_graph().diagnostics
        if item.code == "graph.contract.unknown"
    )
    assert diagnostic.node_id == "custom"
    assert diagnostic.path == ("nodes", 1, "contract")


def test_python_and_yaml_react_definitions_share_canonical_hash() -> None:
    """Round-trip the ReAct template through YAML data without semantic drift.

    Args:
        None.

    Raises:
        AssertionError: YAML compilation changes semantic identity.

    Returns:
        None.
    """
    python_graph = react_template()
    yaml_data = {
        "kind": "agent_graph",
        **python_graph.model_dump(mode="json", exclude_none=True),
    }
    # A real YAML encode/decode boundary catches enum and nested-model leakage.
    parsed = yaml.safe_load(yaml.safe_dump(yaml_data, sort_keys=False))
    compiled = compile_graph_yaml_data(parsed, source_id="react-equivalence")
    assert compiled.is_success
    assert compiled.graph.canonical_hash() == python_graph.canonical_hash()


def test_python_and_yaml_planner_execute_definitions_share_canonical_hash() -> None:
    """Round-trip Planner-and-Execute through YAML data without semantic drift.

    Args:
        None.

    Raises:
        AssertionError: YAML compilation changes semantic identity.

    Returns:
        None.
    """
    python_graph = planner_execute_template()
    yaml_data = {
        "kind": "agent_graph",
        **python_graph.model_dump(mode="json", exclude_none=True),
    }
    parsed = yaml.safe_load(yaml.safe_dump(yaml_data, sort_keys=False))
    compiled = compile_graph_yaml_data(parsed, source_id="planner-equivalence")
    assert compiled.is_success
    assert compiled.graph.canonical_hash() == python_graph.canonical_hash()


def test_contract_11_rejects_ordinary_cycle_outside_loop() -> None:
    """Keep all repeated control flow inside explicit bounded Loop nodes.

    Args:
        None.

    Raises:
        AssertionError: Validator accepts an unstructured ordinary cycle.

    Returns:
        None.
    """
    graph = react_template()
    nodes = list(graph.nodes)
    finish = next(node for node in nodes if node.id == "finish")
    graph = graph.model_copy(
        update={
            "edges": (
                *graph.edges,
                _edge("finish", "result", "finish", "value"),
            )
        }
    )
    assert finish.kind is NodeKind.COMPONENT
    assert any(
        item.code == "graph.cycle.ordinary"
        for item in graph.validate_graph().diagnostics
    )


def test_inline_and_content_addressed_subgraphs_share_semantic_identity() -> None:
    """Canonicalize equivalent inline/reference composition to one identity.

    Args:
        None.

    Raises:
        AssertionError: Inline/reference validation or identity differs.

    Returns:
        None.
    """
    child = react_template()
    semantic_hash = child.canonical_hash()
    catalog = GraphCatalog((("react-child", "1.0", child),))
    inline = SubgraphSpec(
        graph=child,
        inputs={"value": "value"},
        outputs={"result": "result"},
        max_activations=100,
    )
    referenced = SubgraphSpec(
        reference=SubgraphReference(
            id="react-child",
            version="1.0",
            semantic_hash=semantic_hash,
        ),
        inputs={"value": "value"},
        outputs={"result": "result"},
        max_activations=100,
    )

    def parent(specification: SubgraphSpec) -> AgentGraph:
        """Build one parent graph around a supplied child declaration.

        Args:
            specification (SubgraphSpec): Inline or referenced child.

        Raises:
            ValueError: Graph construction fails.

        Returns:
            AgentGraph: Parent composition graph.
        """
        return AgentGraph(
            contract_version="1.1",
            nodes=(
                GraphNode(id="input", kind=NodeKind.INPUT, lifecycle=NodeLifecycle.ON_RUN_START),
                GraphNode(
                    id="child",
                    kind=NodeKind.SUBGRAPH,
                    lifecycle=NodeLifecycle.PER_STEP,
                    subgraph=specification,
                ),
                GraphNode(id="output", kind=NodeKind.OUTPUT, lifecycle=NodeLifecycle.TERMINAL),
            ),
            edges=(
                _edge("input", "value", "child", "value"),
                _edge("child", "result", "output", "result"),
            ),
        )

    inline_graph = parent(inline)
    referenced_graph = parent(referenced)
    assert referenced_graph.validate_graph(graph_catalog=catalog).is_valid
    assert inline_graph.canonical_hash() == referenced_graph.canonical_hash(
        graph_catalog=catalog
    )
