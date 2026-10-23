"""Aguvis online composition using reusable roles and ordinary bounded loops."""

from __future__ import annotations

from typing import Any, Mapping

from zhixing.graph import (
    AgentGraph, AgentGraphBuilder, GraphPolicies, GraphRole, LoopSpec, NodeContractRef,
    Predicate, PredicateOperator, RouterCase, StateOperation, StateScope, StateSpec, SubgraphSpec,
)


def _ref(name: str) -> NodeContractRef:
    """Address one static Aguvis extension contract.

    Args:
        name: Contract suffix.
    Returns:
        NodeContractRef: Exact versioned reference.
    """
    return NodeContractRef(id="zhixing.aguvis." + name, version="1.0")


def build_aguvis_graph(*, max_steps: int = 30, max_decisions: int = 30, max_commands: int = 16,
                       mode: str = "self-plan", low_level_instruction: str | None = None,
                       model_params: Mapping[str, Any] | None = None,
                       parser_params: Mapping[str, Any] | None = None) -> AgentGraph:
    """Compose published single-step inference with an explicit Android loop.

    Args:
        max_steps: Shared physical-interaction budget.
        max_decisions: Independent model-prediction budget.
        max_commands: Maximum ordered commands per model reply.
        mode: CLI self-plan, force-plan or grounding mode.
        low_level_instruction: Optional fixed prefill instruction.
        model_params: Lazy Aguvis model configuration, without credentials.
        parser_params: Explicit Android gesture/scroll conversion overrides.
    Raises:
        ValueError: A mode, bound, override or resulting graph is invalid.
    Returns:
        AgentGraph: Four active roles, no new execution-kernel strategy.
    """
    if (any(type(value) is not int or not 1 <= value <= 1000 for value in (max_steps, max_decisions))
            or type(max_commands) is not int or not 1 <= max_commands <= 32
            or mode not in ("self-plan", "force-plan", "grounding")
            or low_level_instruction is not None and not isinstance(low_level_instruction, str)):
        raise ValueError("invalid Aguvis graph configuration")
    per_round = max_commands * 16 + 24
    total = max_decisions * per_round + 20
    if total > 100000:
        raise ValueError("Aguvis decision/command product exceeds graph activation capacity")
    if parser_params is not None and (not isinstance(parser_params, Mapping) or
            set(parser_params) - {"gesture_duration_ms", "long_press_ms", "scroll_pixels_per_click"}):
        raise ValueError("unsupported Aguvis parser override")
    if model_params is not None and not isinstance(model_params, Mapping):
        raise ValueError("Aguvis model_params must be a mapping")
    policy = GraphPolicies(max_steps=max_steps, max_activations=total)
    atom_body = (AgentGraphBuilder(policies=policy).add_input()
        .add_state("read", StateSpec(key="aguvis_cursor", data_type="aguvis_batch",
                                     scope=StateScope.LOOP, operation=StateOperation.READ))
        .add_component("resume", namespace="agent.memory", name="aguvis_resume", contract=_ref("resume"))
        .add_router("route", (RouterCase(id="action", predicate=Predicate(
            field="next_is_answer", operator=PredicateOperator.FALSY)),), default="answer")
        .add_component("request", namespace="agent.action_executor", name="aguvis_request", contract=_ref("request"))
        .add_component("execute", namespace="zhixing.runtime", name="action_executor", primary=True,
            contract=NodeContractRef(id="zhixing.service.action_executor", version="1.0"))
        .add_component("advance", namespace="agent.memory", name="aguvis_advance", contract=_ref("advance"))
        .add_component("answer", namespace="agent.memory", name="aguvis_answer", contract=_ref("answer"))
        .add_component("merge", namespace="agent.memory", name="aguvis_merge", contract=_ref("merge"))
        .add_state("save", StateSpec(key="aguvis_cursor", data_type="aguvis_batch",
                                     scope=StateScope.LOOP, operation=StateOperation.WRITE))
        .add_output()
        .connect("input", "value", "read", "control")
        .connect("input", "value", "resume", "initial")
        .connect("read", "value", "resume", "previous")
        .connect("resume", "batch", "route", "value")
        .connect("resume", "batch", "request", "value")
        .control("route", "action", "request")
        .control("route", "action", "execute")
        .connect("request", "request", "execute", "request")
        .connect("resume", "batch", "advance", "value")
        .connect("execute", "result", "advance", "ack")
        .control("route", "answer", "answer")
        .connect("resume", "batch", "answer", "value")
        .connect("advance", "batch", "merge", "values")
        .connect("answer", "batch", "merge", "values")
        .connect("merge", "batch", "save", "write")
        .connect("save", "value", "output", "result").build())
    reasoning = dict(parser_params or {})
    if max_commands != 16:
        reasoning["max_commands"] = max_commands
    if mode != "self-plan":
        reasoning["mode"] = mode
    if low_level_instruction is not None:
        reasoning["low_level_instruction"] = low_level_instruction
    body = (AgentGraphBuilder(policies=policy).add_input()
        .add_router("begin", (RouterCase(id="ready", predicate=Predicate(
            field="instruction", operator=PredicateOperator.TRUTHY)),), default="empty_task")
        .add_state("previous", StateSpec(key="aguvis_previous", data_type="aguvis_batch",
                                        scope=StateScope.RUN, operation=StateOperation.READ))
        .add_component("history", namespace="agent.memory", name="aguvis_history", contract=_ref("history"))
        .add_component("memory", namespace="agent.memory", name="sliding_window_memory", role=GraphRole.MEMORY,
            contract=NodeContractRef(id="zhixing.memory.fragments", version="1.0"), lifecycle="stateful",
            params={"window_size": max_decisions})
        .add_component("observe", namespace="zhixing.runtime", name="device_observe",
            contract=NodeContractRef(id="zhixing.service.device_observe", version="2.0"))
        .add_component("perception", namespace="agent.perception", name="screenshot_perception", role=GraphRole.PERCEPTION)
        .add_component("reasoning", namespace="agent.reasoning", name="aguvis_reasoning", role=GraphRole.REASONING,
            contract=_ref("reason"), params=reasoning, dependencies={"llm": {
                "namespace": "llm", "name": "aguvis_llm", "version": "1", "params": dict(model_params or {})}})
        .add_component("prepare", namespace="agent.action_executor", name="aguvis_prepare", contract=_ref("prepare"))
        .add_loop("commands", LoopSpec(body=SubgraphSpec(graph=atom_body,
            inputs={"value": "value"}, outputs={"batch": "result"}, max_activations=16),
            inputs={"value": "value"}, outputs={"batch": "result"},
            until=Predicate(field="result.finished", operator=PredicateOperator.TRUTHY),
            max_iterations=max_commands, max_activations=max_commands * 16, on_exhausted="fail"))
        .add_state("remember", StateSpec(key="aguvis_previous", data_type="aguvis_batch",
                                        scope=StateScope.RUN, operation=StateOperation.WRITE))
        .add_output()
        .connect("input", "task", "begin", "value")
        .control("begin", "ready", "previous")
        .connect("previous", "value", "history", "value")
        .control("begin", "ready", "memory")
        .connect("history", "fragment", "memory", "write", condition=Predicate(field="content", operator=PredicateOperator.EXISTS))
        .connect("input", "value", "observe", "request")
        .connect("observe", "observation", "perception", "observation")
        .connect("input", "task", "reasoning", "task")
        .connect("memory", "context", "reasoning", "memory")
        .connect("perception", "perception", "reasoning", "perception")
        .connect("reasoning", "decision", "prepare", "decision")
        .connect("observe", "observation", "prepare", "observation")
        .connect("prepare", "batch", "commands", "value")
        .connect("commands", "batch", "remember", "write")
        .connect("remember", "value", "output", "result").build())
    return (AgentGraphBuilder(policies=policy).add_input()
        .add_loop("online", LoopSpec(body=SubgraphSpec(graph=body,
            inputs={"task": "task", "value": "value"}, outputs={"result": "result"}, max_activations=per_round),
            inputs={"task": "task", "value": "value"}, outputs={"result": "result"},
            until=Predicate(field="result.terminal_status", operator=PredicateOperator.TRUTHY),
            max_iterations=max_decisions, max_activations=total - 20, on_exhausted="fail"))
        .add_output().connect("input", "task", "online", "task")
        .connect("input", "value", "online", "value")
        .connect("online", "result", "output", "result").build())
