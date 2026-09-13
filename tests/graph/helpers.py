from __future__ import annotations

from zhixing.graph import (
    AgentGraph,
    ComponentBinding,
    EdgeKind,
    FeedbackExhaustedPolicy,
    FeedbackPolicy,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    GraphPolicies,
    GraphRole,
    NodeKind,
    NodeLifecycle,
    PortAddress,
    Predicate,
    PredicateOperator,
)


def ref(role: GraphRole, name: str | None = None, **params) -> ComponentBinding:
    return ComponentBinding(
        candidates=(
            GraphComponentRef(
                namespace=f"agent.{role.value}",
                name=name or f"test_{role.value}",
                params=params,
            ),
        )
    )


def node(
    node_id: str,
    role: GraphRole,
    lifecycle: NodeLifecycle,
    *,
    primary: bool = False,
    **params,
) -> GraphNode:
    return GraphNode(
        id=node_id,
        kind=NodeKind.COMPONENT,
        role=role,
        lifecycle=lifecycle,
        component=ref(role, **params),
        primary=primary,
    )


def edge(source_node: str, source_port: str, target_node: str, target_port: str, kind=EdgeKind.DATA):
    return GraphEdge(
        source=PortAddress(node=source_node, port=source_port),
        target=PortAddress(node=target_node, port=target_port),
        kind=kind,
    )


def make_golden_graph() -> AgentGraph:
    predicate = Predicate(field="is_success", operator=PredicateOperator.EQ, value=True)
    feedback_predicate = Predicate(field="is_success", operator=PredicateOperator.EQ, value=False)
    nodes = (
        GraphNode(id="input", kind=NodeKind.INPUT, lifecycle=NodeLifecycle.ON_RUN_START),
        node("planner", GraphRole.PLANNER, NodeLifecycle.ON_RUN_START),
        node("perception", GraphRole.PERCEPTION, NodeLifecycle.PER_STEP),
        node("reasoning", GraphRole.REASONING, NodeLifecycle.PER_STEP, temperature=0.1),
        node("action_executor", GraphRole.ACTION_EXECUTOR, NodeLifecycle.PER_STEP, primary=True),
        node("verifier", GraphRole.VERIFIER, NodeLifecycle.POST_ACTION),
        GraphNode(
            id="verified",
            kind=NodeKind.CONDITION,
            lifecycle=NodeLifecycle.POST_ACTION,
            predicate=predicate,
        ),
        GraphNode(id="output", kind=NodeKind.OUTPUT, lifecycle=NodeLifecycle.TERMINAL),
    )
    edges = (
        edge("input", "task", "planner", "task"),
        edge("input", "task", "reasoning", "task"),
        edge("input", "task", "verifier", "task"),
        edge("input", "observation", "perception", "observation"),
        edge("input", "observation", "action_executor", "observation"),
        edge("input", "observation", "verifier", "before"),
        edge("input", "observation", "verifier", "after"),
        edge("planner", "plan", "reasoning", "plan"),
        edge("perception", "perception", "reasoning", "perception"),
        edge("reasoning", "action", "action_executor", "action"),
        edge("reasoning", "action", "verifier", "action"),
        edge("action_executor", "result", "verifier", "action_result"),
        edge("action_executor", "result", "output", "result"),
        edge("verifier", "result", "verified", "value"),
        edge("verified", "true", "output", "control", EdgeKind.CONTROL),
        edge("verified", "false", "output", "control", EdgeKind.CONTROL),
        GraphEdge(
            source=PortAddress(node="verifier", port="result"),
            target=PortAddress(node="reasoning", port="verification"),
            kind=EdgeKind.FEEDBACK,
            feedback=FeedbackPolicy(
                predicate=feedback_predicate,
                max_iterations=2,
                on_exhausted=FeedbackExhaustedPolicy.FAIL,
            ),
        ),
    )
    return AgentGraph(nodes=nodes, edges=edges, policies=GraphPolicies(max_steps=15, max_feedback_iterations=3))

