"""AutoDroid online template composed from existing roles and graph primitives."""

from __future__ import annotations

from typing import Any, Mapping

from zhixing.graph import (
    AgentGraph, AgentGraphBuilder, GraphPolicies, GraphRole, LoopSpec,
    NodeContractRef, Predicate, PredicateOperator, RouterCase, SecretRef,
    StateOperation, StateScope, StateSpec, SubgraphSpec,
)


def build_autodroid_graph(
    *, memory_path: str = "examples/autodroid/app_memory.json", app_id: str = "org.example.notes",
    model: str = "gpt-4o", max_steps: int = 100,
    reasoning_params: Mapping[str, Any] | None = None,
    memory_params: Mapping[str, Any] | None = None,
) -> AgentGraph:
    """Build an online AutoDroid graph without binding models or opening memory.

    Args:
        memory_path: Normalized App Memory file or upstream memory directory.
        app_id: Explicit package binding for this memory.
        model: Existing OpenAI-compatible model dependency.
        max_steps: Physical interaction budget; terminal decisions use no effect.
        reasoning_params: Scan, shortcut and parsing options for Reasoning.
        memory_params: Retrieval count, upstream table key or embedding device.
    Raises:
        ValueError: The budget or composed graph is invalid.
    Returns:
        AgentGraph: Bounded observe/perceive/retrieve/reason/execute loop.
    """
    if isinstance(max_steps, bool) or not 1 <= max_steps <= 998:
        raise ValueError("AutoDroid max_steps must be in 1..998")
    iterations = max_steps + 1
    policies = GraphPolicies(max_steps=max_steps, max_activations=iterations * 20 + 20)
    body = (
        AgentGraphBuilder(policies=policies).add_input()
        .add_router("begin", (RouterCase(id="ready", predicate=Predicate(
            field="instruction", operator=PredicateOperator.TRUTHY)),), default="empty_task")
        .add_state("previous", StateSpec(key="autodroid_previous_result", data_type="action_result",
                                        scope=StateScope.RUN, operation=StateOperation.READ))
        .add_component("memory", namespace="agent.memory", name="autodroid_memory",
                       role=GraphRole.MEMORY, lifecycle="stateful",
                       params={**dict(memory_params or {}), "memory_path": memory_path, "app_id": app_id})
        .add_component("observe", namespace="zhixing.runtime", name="device_observe",
                       contract=NodeContractRef(id="zhixing.service.device_observe", version="2.0"))
        .add_component("perception", namespace="agent.perception", name="autodroid_perception",
                       role=GraphRole.PERCEPTION)
        .add_component("reasoning", namespace="agent.reasoning", name="autodroid_reasoning",
                       role=GraphRole.REASONING, params=dict(reasoning_params or {}), dependencies={
                           "llm": {"namespace": "llm", "name": "openai_llm", "version": "1", "params": {
                               "api_key": SecretRef(secret_ref="api_key"),
                               "base_url": SecretRef(secret_ref="base_url"), "model": model,
                               "request_timeout": 45.0, "max_retries": 0,
                           }}
                       })
        .add_component("action_request", namespace="zhixing.control", name="action_request",
                       contract=NodeContractRef(id="zhixing.control.action_request", version="1.0"))
        .add_component("execute", namespace="zhixing.runtime", name="action_executor", primary=True,
                       contract=NodeContractRef(id="zhixing.service.action_executor", version="1.0"))
        .add_state("remember_result", StateSpec(key="autodroid_previous_result", data_type="action_result",
                                               scope=StateScope.RUN, operation=StateOperation.WRITE))
        .add_output()
        .connect("input", "task", "begin", "value")
        .control("begin", "ready", "previous")
        .connect("input", "task", "memory", "write")
        .connect("previous", "value", "memory", "write", condition=Predicate(
            field="status", operator=PredicateOperator.EXISTS))
        .connect("input", "value", "observe", "request")
        .connect("observe", "observation", "perception", "observation")
        .connect("input", "task", "reasoning", "task")
        .connect("memory", "context", "reasoning", "memory")
        .connect("perception", "perception", "reasoning", "perception")
        .connect("reasoning", "action", "action_request", "action")
        .connect("observe", "observation", "action_request", "observation")
        .connect("action_request", "request", "execute", "request")
        .connect("execute", "result", "remember_result", "write")
        .connect("remember_result", "value", "output", "result")
        .build()
    )
    return (
        AgentGraphBuilder(policies=policies).add_input()
        .add_loop("online", LoopSpec(
            body=SubgraphSpec(graph=body, inputs={"task": "task", "value": "value"},
                              outputs={"result": "result"}, max_activations=20),
            inputs={"task": "task", "value": "value"}, outputs={"result": "result"},
            until=Predicate(field="result.terminal_status", operator=PredicateOperator.TRUTHY),
            max_iterations=iterations, max_activations=iterations * 20, on_exhausted="fail",
        ))
        .add_output()
        .connect("input", "task", "online", "task")
        .connect("input", "value", "online", "value")
        .connect("online", "result", "output", "result")
        .build()
    )
