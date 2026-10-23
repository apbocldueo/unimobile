"""SeeClick online composition using standard core roles and a bounded graph."""

from __future__ import annotations

from typing import Any, Mapping

from zhixing.graph import (
    AgentGraph, AgentGraphBuilder, GraphPolicies, GraphRole, LoopSpec,
    NodeContractRef, Predicate, PredicateOperator, RouterCase,
    StateOperation, StateScope, StateSpec, SubgraphSpec,
)


def build_seeclick_graph(
    *, model_path: str = "cckevinn/SeeClick-aitw", qwen_path: str = "Qwen/Qwen-VL-Chat",
    checkpoint_format: str = "full", max_steps: int = 30, max_decisions: int = 30,
    model_params: Mapping[str, Any] | None = None,
) -> AgentGraph:
    """Construct a screenshot/history/predict/execute loop without runtime effects.

    Args:
        model_path: Explicit local or cached SeeClick-AITW checkpoint reference.
        qwen_path: Matching tokenizer and generation configuration reference.
        checkpoint_format: Full model or LoRA adapter.
        max_steps: Shared Runtime's physical interaction limit.
        max_decisions: Independent maximum number of single-prediction rounds.
        model_params: Optional lazy model placement/cache/revision configuration.
    Raises:
        ValueError: A bound, checkpoint reference or resulting graph is invalid.
    Returns:
        AgentGraph: Four active core roles; no Planner, Verifier or custom Kernel.
    """
    if (any(type(value) is not int or not 1 <= value <= 1000 for value in (max_steps, max_decisions))
            or not all(isinstance(value, str) and value.strip() for value in (model_path, qwen_path))
            or checkpoint_format not in ("full", "lora")):
        raise ValueError("SeeClick requires checkpoint references and budgets in 1..1000")
    if model_params is not None and (not isinstance(model_params, Mapping)
            or {"model_path", "qwen_path", "checkpoint_format"}.intersection(model_params)):
        raise ValueError("use explicit SeeClick checkpoint arguments instead of model_params overrides")
    policies = GraphPolicies(max_steps=max_steps, max_activations=max_decisions * 20 + 20)
    model_config = {**dict(model_params or {}), "model_path": model_path, "qwen_path": qwen_path}
    if checkpoint_format != "full":
        model_config["checkpoint_format"] = checkpoint_format
    body = (
        AgentGraphBuilder(policies=policies).add_input()
        .add_router("begin", (RouterCase(id="ready", predicate=Predicate(
            field="instruction", operator=PredicateOperator.TRUTHY)),), default="empty_task")
        .add_state("previous", StateSpec(key="seeclick_previous_result", data_type="action_result",
                                        scope=StateScope.RUN, operation=StateOperation.READ))
        .add_component("memory", namespace="agent.memory", name="seeclick_memory",
                       role=GraphRole.MEMORY, lifecycle="stateful")
        .add_component("observe", namespace="zhixing.runtime", name="device_observe",
                       contract=NodeContractRef(id="zhixing.service.device_observe", version="2.0"))
        .add_component("perception", namespace="agent.perception", name="screenshot_perception",
                       role=GraphRole.PERCEPTION)
        .add_component("reasoning", namespace="agent.reasoning", name="seeclick_reasoning",
                       role=GraphRole.REASONING, dependencies={"llm": {
                           "namespace": "llm", "name": "seeclick_llm", "version": "1", "params": model_config}})
        .add_component("action_request", namespace="zhixing.control", name="action_request",
                       contract=NodeContractRef(id="zhixing.control.action_request", version="1.0"))
        .add_component("execute", namespace="zhixing.runtime", name="action_executor", primary=True,
                       contract=NodeContractRef(id="zhixing.service.action_executor", version="1.0"))
        .add_state("remember_result", StateSpec(key="seeclick_previous_result", data_type="action_result",
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
            max_iterations=max_decisions, max_activations=max_decisions * 20, on_exhausted="fail",
        ))
        .add_output()
        .connect("input", "task", "online", "task")
        .connect("input", "value", "online", "value")
        .connect("online", "result", "output", "result")
        .build()
    )
