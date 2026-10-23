"""Contract tests for the public AgentGraphBuilder authoring surface."""

from __future__ import annotations

import pytest

from zhixing.graph import (
    AgentGraphBuilder,
    EdgeKind,
    GraphPolicies,
    LoopSpec,
    NodeContractRef,
    Predicate,
    PredicateOperator,
    RouterCase,
    StateMergePolicy,
    StateOperation,
    StateScope,
    StateSpec,
    SubgraphSpec,
)


_TRANSFORM = NodeContractRef(id="zhixing.control.transform", version="1.0")


def _transform_child() -> object:
    """Build one valid transform child graph.

    Args:
        None.

    Raises:
        ValueError: Child graph validation fails.

    Returns:
        AgentGraph: Valid child graph.
    """
    return (
        AgentGraphBuilder()
        .add_input()
        .add_component(
            "transform",
            namespace="test",
            name="transform",
            contract=_TRANSFORM,
        )
        .add_output()
        .connect("input", "value", "transform", "value")
        .connect("transform", "result", "output", "result")
        .build()
    )


def test_builder_constructs_valid_contract_11_graph() -> None:
    """Build a complete graph without runtime or strategy side effects.

    Args:
        None.

    Raises:
        AssertionError: Builder output is invalid or has the wrong version.

    Returns:
        None.
    """
    graph = (
        AgentGraphBuilder(policies=GraphPolicies(max_steps=4))
        .add_input()
        .add_component(
            "transform",
            namespace="test",
            name="transform",
            contract=_TRANSFORM,
        )
        .add_condition(
            "accepted",
            Predicate(field="ok", operator=PredicateOperator.EQ, value=True),
        )
        .add_output()
        .connect("input", "value", "transform", "value")
        .connect("transform", "result", "accepted", "value")
        .connect("transform", "result", "output", "result")
        .control("accepted", "true", "output")
        .build()
    )
    assert graph.contract_version == "1.1"
    assert graph.validate_graph().is_valid
    assert all(node.id != "modular_agent" for node in graph.nodes)


def test_builder_supports_router_state_subgraph_and_loop() -> None:
    """Exercise generalized composition helpers without executing a graph.

    Args:
        None.

    Raises:
        AssertionError: A generalized node is missing from Builder output.

    Returns:
        None.
    """
    child = _transform_child()
    graph = (
        AgentGraphBuilder(policies={"max_activations": 100})
        .add_input()
        .add_router(
            "router",
            (
                RouterCase(
                    id="use_tool",
                    predicate=Predicate(
                        field="tool",
                        operator=PredicateOperator.EXISTS,
                    ),
                ),
            ),
            default="finish",
        )
        .add_state(
            "history",
            StateSpec(
                key="history",
                data_type="any",
                scope=StateScope.RUN,
                operation=StateOperation.WRITE,
                merge=StateMergePolicy.APPEND,
                initial=[],
            ),
        )
        .add_subgraph(
            "child",
            SubgraphSpec(
                graph=child,
                inputs={"value": "value"},
                outputs={"result": "result"},
            ),
        )
        .add_loop(
            "loop",
            LoopSpec(
                body=SubgraphSpec(
                    graph=child,
                    inputs={"value": "value"},
                    outputs={"result": "result"},
                ),
                inputs={"value": "value"},
                outputs={"result": "result"},
                until=Predicate(
                    field="done",
                    operator=PredicateOperator.EQ,
                    value=True,
                ),
                max_iterations=2,
            ),
        )
        .add_output()
        .connect("input", "value", "router", "value")
        .build(validate=False)
    )
    assert {node.kind.value for node in graph.nodes} >= {
        "router",
        "state",
        "subgraph",
        "loop",
    }


def test_builder_feedback_is_bounded_and_explicit() -> None:
    """Require the dedicated feedback API and a finite feedback bound.

    Args:
        None.

    Raises:
        AssertionError: Feedback declaration is not preserved.

    Returns:
        None.
    """
    builder = (
        AgentGraphBuilder()
        .add_input()
        .add_component(
            "first",
            namespace="test",
            name="first",
            contract=_TRANSFORM,
        )
        .add_component(
            "second",
            namespace="test",
            name="second",
            contract=_TRANSFORM,
        )
        .add_output()
        .connect("input", "value", "first", "value")
        .connect("first", "result", "second", "value")
        .connect("second", "result", "output", "result")
        .feedback(
            "second",
            "result",
            "first",
            "value",
            predicate=Predicate(
                field="retry",
                operator=PredicateOperator.EQ,
                value=True,
            ),
            max_iterations=2,
        )
    )
    graph = builder.build(validate=False)
    feedback = next(edge for edge in graph.edges if edge.kind is EdgeKind.FEEDBACK)
    assert feedback.feedback.max_iterations == 2

    with pytest.raises(ValueError, match="bounded feedback"):
        builder.connect(
            "second",
            "result",
            "first",
            "value",
            kind=EdgeKind.FEEDBACK,
        )


def test_builder_rejects_duplicate_nodes_and_old_contract() -> None:
    """Reject ambiguous logical identities and old-version authoring.

    Args:
        None.

    Raises:
        AssertionError: Expected validation errors are absent.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="contract 1.1"):
        AgentGraphBuilder(contract_version="1.0")

    builder = AgentGraphBuilder().add_input()
    with pytest.raises(ValueError, match="duplicate"):
        builder.add_input()
