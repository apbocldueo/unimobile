"""Build a Mobile Agent whose completion is verified by Android content delta."""

from __future__ import annotations

from typing import Any, Mapping

from zhixing.graph import (
    AgentGraph,
    AgentGraphBuilder,
    ComponentBinding,
    EdgeKind,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    GraphPolicies,
    GraphRole,
    NodeKind,
    NodeLifecycle,
    NodeContractRef,
    PortAddress,
    Predicate,
    PredicateOperator,
    RouterCase,
    SecretRef,
)

EXTERNAL_RUN_LABELER_CONTRACT = NodeContractRef(
    id="example.external.task_run_labeler",
    version="1.0",
)


def build_android_content_verified_agent(
    *,
    model: str = "gpt-4o",
    content_uri: str = "content://media/external/images/media",
    id_column: str = "_id",
    minimum_added: int = 1,
    max_steps: int = 10,
    reasoning_params: Mapping[str, Any] | None = None,
) -> AgentGraph:
    """Compose a graph-native Android Agent with device-state verification.

    Args:
        model (str): OpenAI-compatible model identifier.
        content_uri (str): Android content collection used as success evidence.
        id_column (str): Stable identity column queried from the collection.
        minimum_added (int): Required number of newly created rows.
        max_steps (int): Maximum physical device interactions.
        reasoning_params (Mapping[str, Any] | None): UniversalReason options.

    Raises:
        ValueError: Builder or AgentGraph validation rejects the definition.

    Returns:
        AgentGraph: Ordinary contract 1.1 graph without hidden callbacks.
    """
    observe_contract = NodeContractRef(
        id="zhixing.service.device_observe",
        version="2.0",
    )
    action_request_contract = NodeContractRef(
        id="zhixing.control.action_request",
        version="1.0",
    )
    action_executor_contract = NodeContractRef(
        id="zhixing.service.action_executor",
        version="1.0",
    )
    transform_contract = NodeContractRef(
        id="zhixing.control.transform",
        version="1.0",
    )
    llm_params = {
        "api_key": SecretRef(secret_ref="api_key"),
        "base_url": SecretRef(secret_ref="base_url"),
        "model": model,
        "request_timeout": 45.0,
        "max_retries": 0,
    }
    reason_config = {
        "preset": "general_vlm_type",
        "parse_max_retries": 2,
        **dict(reasoning_params or {}),
    }
    builder = (
        AgentGraphBuilder(
            policies=GraphPolicies(
                max_steps=max_steps,
                max_feedback_iterations=max_steps,
            )
        )
        .add_input()
        .add_component(
            "memory",
            namespace="agent.memory",
            name="sliding_window_memory",
            role=GraphRole.MEMORY,
            lifecycle="stateful",
        )
        .add_router(
            "iteration",
            (
                RouterCase(
                    id="blocked",
                    predicate=Predicate(
                        field="blocked",
                        operator=PredicateOperator.EXISTS,
                    ),
                ),
            ),
            default="ready",
        )
        .add_component(
            "observe_before",
            namespace="zhixing.runtime",
            name="device_observe",
            contract=observe_contract,
        )
        .add_component(
            "perception",
            namespace="agent.perception",
            name="screenshot_perception",
            role=GraphRole.PERCEPTION,
        )
        .add_component(
            "reasoning",
            namespace="agent.reasoning",
            name="universal_reasoning",
            params=reason_config,
            dependencies={
                "llm": {
                    "namespace": "llm",
                    "name": "openai_llm",
                    "version": "1",
                    "params": llm_params,
                }
            },
            role=GraphRole.REASONING,
        )
        .add_component(
            "action_request",
            namespace="zhixing.control",
            name="action_request",
            contract=action_request_contract,
        )
        .add_component(
            "action_executor",
            namespace="zhixing.runtime",
            name="action_executor",
            contract=action_executor_contract,
            primary=True,
        )
        .add_condition(
            "agent_terminal",
            Predicate(
                field="terminal_status",
                operator=PredicateOperator.TRUTHY,
            ),
        )
        .add_component(
            "observe_after",
            namespace="zhixing.runtime",
            name="device_observe",
            contract=observe_contract,
        )
        .add_component(
            "verifier",
            namespace="agent.verifier",
            name="android_content_delta_verifier",
            params={
                "uri": content_uri,
                "id_column": id_column,
                "minimum_added": minimum_added,
                "baseline_actions": ["start_app"],
                "baseline_key": "target_content",
            },
            role=GraphRole.VERIFIER,
            lifecycle="stateful",
        )
        .add_condition(
            "verification_succeeded",
            Predicate(
                field="is_success",
                operator=PredicateOperator.TRUTHY,
            ),
        )
        .add_component(
            "terminal_action",
            namespace="zhixing.control",
            name="verification_terminal_action",
            contract=transform_contract,
        )
        .add_component(
            "terminal_request",
            namespace="zhixing.control",
            name="action_request",
            contract=action_request_contract,
        )
        .add_component(
            "terminal_executor",
            namespace="zhixing.runtime",
            name="action_executor",
            contract=action_executor_contract,
        )
        .add_output("agent_output")
        .add_output("verified_output")
        .connect("input", "task", "memory", "write")
        .connect("input", "value", "observe_before", "request")
        .connect("memory", "context", "iteration", "value")
        .control("iteration", "ready", "observe_before")
        .connect("observe_before", "observation", "perception", "observation")
        .connect("input", "task", "reasoning", "task")
        .connect("perception", "perception", "reasoning", "perception")
        .connect("memory", "context", "reasoning", "memory")
        .connect("reasoning", "action", "action_request", "action")
        .connect(
            "observe_before",
            "observation",
            "action_request",
            "observation",
        )
        .connect("action_request", "request", "action_executor", "request")
        .connect("action_executor", "result", "agent_terminal", "value")
        .connect("action_executor", "result", "agent_output", "result")
        .control("agent_terminal", "true", "agent_output")
        .control("agent_terminal", "false", "observe_after")
        .connect("input", "value", "observe_after", "request")
        .connect("input", "task", "verifier", "task")
        .connect("observe_before", "observation", "verifier", "before")
        .connect("observe_after", "observation", "verifier", "after")
        .connect("reasoning", "action", "verifier", "action")
        .connect(
            "action_executor",
            "result",
            "verifier",
            "action_result",
        )
        .connect(
            "verifier",
            "result",
            "verification_succeeded",
            "value",
        )
        .connect("verifier", "result", "terminal_action", "value")
        .control(
            "verification_succeeded",
            "true",
            "terminal_action",
        )
        .connect("terminal_action", "result", "terminal_request", "action")
        .connect(
            "observe_after",
            "observation",
            "terminal_request",
            "observation",
        )
        .connect("terminal_request", "request", "terminal_executor", "request")
        .connect("terminal_executor", "result", "verified_output", "result")
        .feedback(
            "verifier",
            "result",
            "memory",
            "write",
            predicate=Predicate(
                field="is_success",
                operator=PredicateOperator.FALSY,
            ),
            max_iterations=max_steps,
        )
    )
    return builder.build()


def build_external_augmented_android_agent(
    *,
    prefix: str = "android-acceptance",
    **base_options: Any,
) -> AgentGraph:
    """Add an installed external audit branch to the verified Android Agent.

    Args:
        prefix (str): Declarative prefix passed to the external run labeler.
        **base_options (Any): Options forwarded to
            :func:`build_android_content_verified_agent`.

    Raises:
        ValueError: The composed AgentGraph definition is invalid.

    Returns:
        AgentGraph: Verified camera graph plus a consumed external output branch.
    """
    base = build_android_content_verified_agent(**base_options)
    audit_node = GraphNode(
        id="external_audit",
        kind=NodeKind.COMPONENT,
        lifecycle=NodeLifecycle.PER_STEP,
        contract=EXTERNAL_RUN_LABELER_CONTRACT,
        component=ComponentBinding(
            candidates=(
                GraphComponentRef(
                    namespace="example.external",
                    name="task_run_labeler",
                    version="1.0.0",
                    params={"prefix": prefix},
                ),
            )
        ),
    )
    audit_output = GraphNode(
        id="external_audit_output",
        kind=NodeKind.OUTPUT,
        lifecycle=NodeLifecycle.TERMINAL,
    )
    graph = AgentGraph.model_validate(
        {
            **base.model_dump(mode="python"),
            "nodes": (*base.nodes, audit_node, audit_output),
            "edges": (
                *base.edges,
                GraphEdge(
                    source=PortAddress(node="input", port="task"),
                    target=PortAddress(node="external_audit", port="task"),
                    kind=EdgeKind.DATA,
                ),
                GraphEdge(
                    source=PortAddress(node="external_audit", port="result"),
                    target=PortAddress(
                        node="external_audit_output",
                        port="result",
                    ),
                    kind=EdgeKind.DATA,
                ),
            ),
        }
    )
    return graph


__all__ = ["build_android_content_verified_agent"]
