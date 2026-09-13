"""Framework-owned AgentGraph templates built from ordinary graph primitives."""

from __future__ import annotations

from typing import Any, Mapping

from zhixing.graph import (
    AgentGraph,
    AgentGraphBuilder,
    GraphPolicies,
    GraphRole,
    NodeContractRef,
    Predicate,
    PredicateOperator,
    RouterCase,
    SecretRef,
)


DEVICE_OBSERVE_CONTRACT = NodeContractRef(
    id="zhixing.service.device_observe",
    version="2.0",
)
ACTION_REQUEST_CONTRACT = NodeContractRef(
    id="zhixing.control.action_request",
    version="1.0",
)
ACTION_EXECUTOR_CONTRACT = NodeContractRef(
    id="zhixing.service.action_executor",
    version="1.0",
)


def build_builtin_mobile_agent_graph(
    *,
    model: str = "gpt-4o",
    base_url: str | None = None,
    api_key_secret: str = "api_key",
    base_url_secret: str | None = "base_url",
    max_steps: int = 15,
    reasoning_params: Mapping[str, Any] | None = None,
) -> AgentGraph:
    """Build the first graph-native, model-driven Android Mobile Agent.

    Args:
        model (str): OpenAI-compatible model identifier.
        base_url (str | None): Optional OpenAI-compatible endpoint.
        api_key_secret (str): Runtime SecretRef name, never the real secret.
        base_url_secret (str | None): Runtime endpoint SecretRef used when
            ``base_url`` is not supplied.
        max_steps (int): Maximum physical interaction count.
        reasoning_params (Mapping[str, Any] | None): UniversalReason options.

    Raises:
        ValueError: The resulting graph is structurally invalid.

    Returns:
        AgentGraph: Valid contract 1.1 observe-reason-act feedback graph.
    """
    llm_params: dict[str, Any] = {
        "api_key": SecretRef(secret_ref=api_key_secret),
        "model": model,
        "request_timeout": 45.0,
        "max_retries": 0,
    }
    if base_url is not None:
        llm_params["base_url"] = base_url
    elif base_url_secret is not None:
        llm_params["base_url"] = SecretRef(secret_ref=base_url_secret)
    reason_config = {
        "preset": "general_vlm_type",
        "parse_max_retries": 2,
        **dict(reasoning_params or {}),
    }
    builder = (
        AgentGraphBuilder(
            policies=GraphPolicies(
                max_steps=max_steps,
                max_feedback_iterations=min(max_steps, 10),
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
            "observe",
            namespace="zhixing.runtime",
            name="device_observe",
            contract=DEVICE_OBSERVE_CONTRACT,
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
            contract=ACTION_REQUEST_CONTRACT,
        )
        .add_component(
            "action_executor",
            namespace="zhixing.runtime",
            name="action_executor",
            contract=ACTION_EXECUTOR_CONTRACT,
            primary=True,
        )
        .add_condition(
            "terminal",
            Predicate(
                field="terminal_status",
                operator=PredicateOperator.EXISTS,
            ),
        )
        .add_output()
        .connect("input", "task", "memory", "write")
        .connect("input", "value", "observe", "request")
        .connect("memory", "context", "iteration", "value")
        .control("iteration", "ready", "observe")
        .connect("observe", "observation", "perception", "observation")
        .connect("input", "task", "reasoning", "task")
        .connect("perception", "perception", "reasoning", "perception")
        .connect("memory", "context", "reasoning", "memory")
        .connect("reasoning", "action", "action_request", "action")
        .connect("observe", "observation", "action_request", "observation")
        .connect("action_request", "request", "action_executor", "request")
        .connect("action_executor", "result", "terminal", "value")
        .connect("action_executor", "result", "output", "result")
        .control("terminal", "true", "output")
        .feedback(
            "action_executor",
            "result",
            "memory",
            "write",
            predicate=Predicate(
                field="terminal_status",
                operator=PredicateOperator.FALSY,
            ),
            max_iterations=min(max_steps, 10),
        )
    )
    return builder.build()


__all__ = [
    "ACTION_EXECUTOR_CONTRACT",
    "ACTION_REQUEST_CONTRACT",
    "DEVICE_OBSERVE_CONTRACT",
    "build_builtin_mobile_agent_graph",
]
