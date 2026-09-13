from __future__ import annotations

from pydantic import ValidationError
import pytest

from zhixing.graph import (
    EdgeKind,
    FeedbackPolicy,
    GraphEdge,
    GraphRole,
    NodeLifecycle,
    PortAddress,
    Predicate,
    PredicateOperator,
)

from .helpers import edge, make_golden_graph, node


def codes(graph):
    return [item.code for item in graph.validate_graph().diagnostics]


def test_golden_graph_is_valid():
    result = make_golden_graph().validate_graph()
    assert result.is_valid, result.to_safe_dict()
    assert result.errors == ()


def test_unknown_port_and_type_mismatch_are_aggregated():
    graph = make_golden_graph()
    bad_edges = graph.edges + (
        edge("planner", "plan", "perception", "observation"),
        edge("planner", "missing", "reasoning", "plan"),
    )
    result = graph.model_copy(update={"edges": bad_edges}).validate_graph()
    assert "graph.edge.type_incompatible" in [item.code for item in result.errors]
    assert "graph.edge.source_port_unknown" in [item.code for item in result.errors]


def test_required_role_and_required_port_are_reported():
    graph = make_golden_graph()
    nodes = tuple(node for node in graph.nodes if node.role != GraphRole.ACTION_EXECUTOR)
    edges = tuple(
        edge for edge in graph.edges
        if edge.source.node != "action_executor" and edge.target.node != "action_executor"
    )
    result = graph.model_copy(update={"nodes": nodes, "edges": edges}).validate_graph()
    assert "graph.profile.primary_action_executor" in [item.code for item in result.errors]

    missing = tuple(
        edge for edge in graph.edges
        if not (edge.target.node == "reasoning" and edge.target.port == "perception")
    )
    assert "graph.port.required_missing" in codes(graph.model_copy(update={"edges": missing}))


def test_multiple_edges_to_single_input_are_rejected():
    graph = make_golden_graph()
    duplicate = edge("input", "task", "planner", "task")
    assert "graph.port.cardinality_exceeded" in codes(
        graph.model_copy(update={"edges": graph.edges + (duplicate,)})
    )


def test_unreachable_node_and_non_terminating_dead_end_are_reported():
    graph = make_golden_graph()
    orphan = node("orphan_memory", GraphRole.MEMORY, NodeLifecycle.STATEFUL)
    unreachable = graph.model_copy(update={"nodes": graph.nodes + (orphan,)})
    assert "graph.reachability.unreachable_node" in codes(unreachable)

    reachable_dead_end = graph.model_copy(
        update={
            "nodes": graph.nodes + (orphan,),
            "edges": graph.edges + (edge("input", "task", "orphan_memory", "write"),),
        }
    )
    assert "graph.reachability.non_terminating_dead_end" in codes(reachable_dead_end)


def test_ordinary_cycle_is_rejected():
    graph = make_golden_graph()
    cycle = GraphEdge(
        source=PortAddress(node="verified", port="false"),
        target=PortAddress(node="reasoning", port="control"),
        kind=EdgeKind.CONTROL,
    )
    assert "graph.cycle.ordinary" in codes(graph.model_copy(update={"edges": graph.edges + (cycle,)}))


def test_feedback_requires_real_path_and_respects_limit():
    graph = make_golden_graph()
    feedback_index = next(i for i, item in enumerate(graph.edges) if item.kind == EdgeKind.FEEDBACK)
    feedback = graph.edges[feedback_index]
    no_path = feedback.model_copy(
        update={"target": PortAddress(node="verified", port="value")}
    )
    edges = list(graph.edges)
    edges[feedback_index] = no_path
    assert "graph.feedback.return_path_missing" in codes(graph.model_copy(update={"edges": tuple(edges)}))

    over = feedback.model_copy(
        update={"feedback": feedback.feedback.model_copy(update={"max_iterations": 4})}
    )
    edges[feedback_index] = over
    assert "graph.feedback.graph_limit_exceeded" in codes(graph.model_copy(update={"edges": tuple(edges)}))


def test_overlapping_feedback_loops_are_rejected():
    graph = make_golden_graph()
    feedback = next(item for item in graph.edges if item.kind == EdgeKind.FEEDBACK)
    duplicate = feedback.model_copy(
        update={
            "feedback": feedback.feedback.model_copy(
                update={"predicate": Predicate(field="should_retry", operator=PredicateOperator.EQ, value=True)}
            )
        }
    )
    assert "graph.feedback.overlap_unsupported" in codes(
        graph.model_copy(update={"edges": graph.edges + (duplicate,)})
    )


def test_unbounded_feedback_and_executable_predicate_are_rejected_by_models():
    with pytest.raises(ValidationError):
        FeedbackPolicy(
            predicate=Predicate(field="is_success", operator=PredicateOperator.EQ, value=False),
            max_iterations=0,
            on_exhausted="fail",
        )
    with pytest.raises(ValidationError):
        Predicate(field="eval(payload)", operator=PredicateOperator.TRUTHY)


def test_predicate_field_and_value_types_are_checked():
    graph = make_golden_graph()
    condition_index = next(i for i, item in enumerate(graph.nodes) if item.id == "verified")
    bad_condition = graph.nodes[condition_index].model_copy(
        update={"predicate": Predicate(field="missing", operator=PredicateOperator.EQ, value=True)}
    )
    nodes = list(graph.nodes)
    nodes[condition_index] = bad_condition
    assert "graph.predicate.field_unknown" in codes(graph.model_copy(update={"nodes": tuple(nodes)}))

    numeric = graph.nodes[condition_index].model_copy(
        update={"predicate": Predicate(field="feedback", operator=PredicateOperator.GT, value=2)}
    )
    nodes[condition_index] = numeric
    assert "graph.predicate.field_type" in codes(graph.model_copy(update={"nodes": tuple(nodes)}))


def test_diagnostics_are_stable_and_safe():
    graph = make_golden_graph()
    invalid = graph.model_copy(update={"edges": graph.edges[:-6]})
    first = invalid.validate_graph().to_safe_dict()
    second = invalid.validate_graph().to_safe_dict()
    assert first == second
    rendered = str(first)
    assert "sk-live" not in rendered
    assert "object at 0x" not in rendered
