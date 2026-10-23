"""Complete M3A online composition with shared Memory and ordinary graph control."""

from __future__ import annotations

import math
from typing import Any, Mapping

from zhixing.graph import (AgentGraph, AgentGraphBuilder, GraphPolicies, GraphRole, LoopSpec,
    NodeContractRef, Predicate, PredicateOperator, RouterCase, StateOperation, StateScope, StateSpec, SubgraphSpec)


def _ref(name: str) -> NodeContractRef:
    """Address one M3A stage contract.

    Args:
        name: Stable stage suffix.
    Returns:
        NodeContractRef: Exact versioned reference.
    """
    return NodeContractRef(id="zhixing.m3a." + name, version="1.0")


def build_m3a_graph(*, max_rounds: int = 30, transition_pause: float | None = 1.0,
                    wait_after_action_seconds: float = 2.0, start_on_home_screen: bool = False,
                    additional_guidelines: list[str] | None = None,
                    model_params: Mapping[str, Any] | None = None) -> AgentGraph:
    """Compose the complete original episode as independently scheduled nodes.

    Args:
        max_rounds: Official decision-round budget; zero performs no reset or calls.
        transition_pause: Original pre-observation pause, or None for stable polling.
        wait_after_action_seconds: Original pause before post-action observation.
        start_on_home_screen: Original reset option.
        additional_guidelines: Optional original task prompt guidelines.
        model_params: Lazy model-wrapper configuration, without credentials.
    Raises:
        ValueError: Configuration, bounds or resulting graph is invalid.
    Returns:
        AgentGraph: Four active role families and explicit source control flow.
    """
    if type(max_rounds) is not int or not 0 <= max_rounds <= 999:
        raise ValueError("max_rounds must be an integer between 0 and 999")
    for value in (transition_pause, wait_after_action_seconds):
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 60):
            raise ValueError("M3A pauses must be finite seconds between 0 and 60")
    if wait_after_action_seconds is None or type(start_on_home_screen) is not bool:
        raise ValueError("invalid M3A post-action pause or reset option")
    if additional_guidelines is not None and (not isinstance(additional_guidelines, list) or
                                             not all(isinstance(item, str) for item in additional_guidelines)):
        raise ValueError("additional_guidelines must be a list of strings")
    if model_params is not None and (not isinstance(model_params, Mapping) or
                                    set(model_params) - {"model", "max_retry", "temperature"}):
        raise ValueError("unsupported M3A model-wrapper parameters")
    # Leave room for the Nth action's summary: physical limits fire immediately
    # after execution, whereas source round limits apply after the whole step.
    policy = GraphPolicies(max_steps=max_rounds + 1, max_activations=(max_rounds + 1) * 40 + 20)
    llm = {"llm": {"namespace": "llm", "name": "m3a_llm", "params": dict(model_params or {})}}
    body = AgentGraphBuilder(policies=policy).add_input()
    body.add_state("previous", StateSpec(key="m3a_episode", data_type="m3a_frame", scope=StateScope.RUN, operation=StateOperation.READ))
    definitions = (
        ("resume", "memory", "resume", "resume", {"max_rounds": max_rounds} if max_rounds != 30 else {}),
        ("history", "memory", "history", "history", {}),
        ("ready", "memory", "pass", "ready", {}),
        ("finish_round", "memory", "pass", "pass", {}),
        ("skip_round", "memory", "pass", "pass", {}),
        ("failed_round", "memory", "pass", "pass", {}),
        ("observe_before", "perception", "observe", "observe", {"pause": transition_pause} if transition_pause != 1.0 else {}),
        ("perceive_before", "perception", "perception", "perceive", {}),
        ("select", "reasoning", "select", "select", {"additional_guidelines": additional_guidelines} if additional_guidelines else {}),
        ("execute", "action_executor", "execute", "execute", {}),
        ("observe_after", "perception", "observe", "observe", {"pause": wait_after_action_seconds}),
        ("perceive_after", "perception", "perception", "perceive", {"after": True}),
        ("summary", "reasoning", "summary", "summary", {}),
        ("commit", "memory", "commit", "commit", {}),
        ("termination", "perception", "termination", "termination", {}),
    )
    for node, family, name, contract, params in definitions:
        active = node in ("perceive_before", "perceive_after", "select", "summary", "execute")
        body.add_component(node, namespace="agent." + family, name="m3a_" + name, contract=_ref(contract),
            role=GraphRole(family) if active else None, params=params,
            dependencies=llm if family == "reasoning" else {}, primary=node == "execute")
    body.add_component("memory", namespace="agent.memory", name="sliding_window_memory", role=GraphRole.MEMORY,
        contract=NodeContractRef(id="zhixing.memory.fragments", version="1.0"), lifecycle="stateful",
        params={"window_size": max(1, max_rounds)})
    for node, case, route, default in (("start", "finish", "finish", "continue"),
                                      ("decision", "execute", "execute", "skip"),
                                      ("executed", "ok", "executed", "failed")):
        body.add_router(node, (RouterCase(id=case, predicate=Predicate(field="route", operator=PredicateOperator.EQ, value=route)),), default=default)
    body.add_state("save", StateSpec(key="m3a_episode", data_type="m3a_frame", scope=StateScope.RUN, operation=StateOperation.WRITE)).add_output()
    edges = (
        "input.value previous.control", "input.task resume.task", "previous.value resume.previous",
        "resume.frame history.frame", "resume.frame ready.frame", "memory.context ready.memory", "ready.result start.value",
        "ready.result finish_round.frame", "finish_round.result commit.values",
        "ready.result observe_before.frame", "observe_before.observation perceive_before.observation",
        "resume.frame select.frame", "perceive_before.view select.view", "memory.context select.memory",
        "select.result decision.value", "select.result skip_round.frame", "skip_round.result commit.values", "select.result execute.frame",
        "execute.result executed.value", "execute.result failed_round.frame", "failed_round.result commit.values", "execute.result observe_after.frame",
        "observe_after.observation perceive_after.observation", "execute.result summary.frame",
        "perceive_after.view summary.view", "summary.result commit.values", "commit.result termination.frame", "termination.result save.write", "save.value output.result",
    )
    for edge in edges:
        source, target = (value.split(".") for value in edge.split())
        body.connect(*source, *target)
    body.connect("history", "fragment", "memory", "write", condition=Predicate(field="content", operator=PredicateOperator.EXISTS))
    for node, branch, target in (("start", "finish", "finish_round"), ("start", "continue", "observe_before"),
                                ("decision", "skip", "skip_round"), ("decision", "execute", "execute"),
                                ("executed", "failed", "failed_round"), ("executed", "ok", "observe_after"),
                                ("executed", "ok", "summary")):
        body.control(node, branch, target)
    loop = LoopSpec(body=SubgraphSpec(graph=body.build(), inputs={"task": "task", "value": "value"},
        outputs={"result": "result"}, max_activations=40), inputs={"task": "task", "value": "value"},
        outputs={"result": "result"}, until=Predicate(field="result.finished", operator=PredicateOperator.TRUTHY),
        max_iterations=max_rounds + 1, max_activations=(max_rounds + 1) * 40, on_exhausted="fail")
    return (AgentGraphBuilder(policies=policy).add_input()
        .add_component("setup", namespace="agent.action_executor", name="m3a_setup", contract=_ref("setup"),
            params={**({"start_on_home_screen": True} if start_on_home_screen else {}), **({"skip_reset": True} if max_rounds == 0 else {})})
        .add_loop("online", loop)
        .add_component("finish", namespace="agent.memory", name="m3a_finish", contract=_ref("finish"))
        .add_output().connect("input", "task", "setup", "task").connect("setup", "result", "online", "task")
        .connect("input", "value", "online", "value").connect("online", "result", "finish", "frame")
        .connect("finish", "result", "output", "result").build())
