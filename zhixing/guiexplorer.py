"""Complete non-demo GUI-explorer task execution through ordinary AgentGraph nodes."""

from __future__ import annotations

import math
from typing import Any, Mapping

from zhixing.graph import (AgentGraph, AgentGraphBuilder, GraphPolicies, GraphRole, LoopSpec,
    NodeContractRef, Predicate, PredicateOperator, RouterCase, StateOperation, StateScope, StateSpec, SubgraphSpec)


def _ref(name: str, family: str = "guiexplorer") -> NodeContractRef:
    """Address a source-stage or unchanged shared M3A operation contract.

    Args:
        name: Stable stage suffix.
        family: GUI-explorer stage family or reused M3A contract family.
    Returns:
        NodeContractRef: Exact versioned reference.
    """
    return NodeContractRef(id=f"zhixing.{family}.{name}", version="1.0")


def build_guiexplorer_graph(*, max_rounds: int = 30, top_k: int | None = None,
                           threshold: float | None = None, retrieval_endpoint: str | None = None,
                           model_params: Mapping[str, Any] | None = None) -> AgentGraph:
    """Compose the full official non-demo online workflow with four active role families.

    Args:
        max_rounds: Original task decision budget; zero makes no device/model/RAG calls.
        top_k: Optional original per-element retrieval count.
        threshold: Optional original retrieval similarity cutoff.
        retrieval_endpoint: Optional official RAG service base URL.
        model_params: Explicit source model configuration; credentials use SecretRef.
    Raises:
        ValueError: Public configuration or resulting graph is invalid.
    Returns:
        AgentGraph: Source-complete composition without kernel/Planner/Verifier additions.
    """
    if type(max_rounds) is not int or not 0 <= max_rounds <= 999:
        raise ValueError("max_rounds must be an integer between 0 and 999")
    if top_k is not None and (type(top_k) is not int or top_k < 1):
        raise ValueError("top_k must be a positive integer")
    if threshold is not None and (type(threshold) not in (int, float) or not math.isfinite(threshold)):
        raise ValueError("threshold must be finite")
    if model_params is not None and (not isinstance(model_params, Mapping) or
            set(model_params) - {"model", "base_url", "api_key", "low_resolution"}):
        raise ValueError("unsupported GUI-explorer model parameters")
    if retrieval_endpoint is not None and (not isinstance(retrieval_endpoint, str) or not retrieval_endpoint.strip()):
        raise ValueError("retrieval_endpoint must be a nonempty URL")
    policy = GraphPolicies(max_steps=max_rounds + 1, max_activations=(max_rounds + 1) * 48 + 20)
    llm = {"llm": {"namespace": "llm", "name": "guiexplorer_llm", "params": dict(model_params or {})}}
    rag = {"retrieval": {"namespace": "knowledge", "name": "guiexplorer_retrieval",
                         "params": {"endpoint": retrieval_endpoint} if retrieval_endpoint else {}}}
    body = AgentGraphBuilder(policies=policy).add_input()
    body.add_state("previous", StateSpec(key="guiexplorer_episode", data_type="m3a_frame", scope=StateScope.RUN, operation=StateOperation.READ))
    definitions = (
        ("resume", "memory", "m3a_resume", _ref("resume", "m3a"), {"max_rounds": max_rounds} if max_rounds != 30 else {}, {}),
        ("history", "memory", "guiexplorer_history", _ref("history"), {}, {}),
        ("ready", "memory", "m3a_pass", _ref("ready", "m3a"), {}, {}),
        ("finish_round", "memory", "m3a_pass", _ref("pass", "m3a"), {}, {}),
        ("skip_round", "memory", "m3a_pass", _ref("pass", "m3a"), {}, {}),
        ("failed_round", "memory", "m3a_pass", _ref("pass", "m3a"), {}, {}),
        ("observe_before", "perception", "guiexplorer_observe", _ref("observe"), {}, {}),
        ("perceive_before", "perception", "guiexplorer_perception", _ref("perceive"), {}, {}),
        ("retrieve", "memory", "guiexplorer_retrieve", _ref("retrieve"),
            {**({"top_k": top_k} if top_k is not None else {}), **({"threshold": threshold} if threshold is not None else {})}, rag),
        ("rank", "reasoning", "guiexplorer_rank", _ref("rank"), {}, llm),
        ("select", "reasoning", "guiexplorer_select", _ref("select"), {}, llm),
        ("execute", "action_executor", "guiexplorer_execute", _ref("execute"), {}, {}),
        ("observe_after", "perception", "guiexplorer_observe", _ref("observe"), {"after": True}, {}),
        ("perceive_after", "perception", "guiexplorer_perception", _ref("perceive"), {"after": True}, {}),
        ("summary", "reasoning", "guiexplorer_summary", _ref("summary"), {}, llm),
        ("commit", "memory", "m3a_commit", _ref("commit", "m3a"), {}, {}),
        ("wait_round", "perception", "guiexplorer_wait_round", _ref("wait_round"), {}, {}),
    )
    active = {"perceive_before", "perceive_after", "retrieve", "rank", "select", "summary", "execute"}
    for node, family, name, contract, params, dependencies in definitions:
        body.add_component(node, namespace="agent." + family, name=name, contract=contract,
            role=GraphRole(family) if node in active else None, params=params,
            dependencies=dependencies, primary=node == "execute")
    body.add_component("memory", namespace="agent.memory", name="sliding_window_memory", role=GraphRole.MEMORY,
        contract=NodeContractRef(id="zhixing.memory.fragments", version="1.0"), lifecycle="stateful",
        params={"window_size": max(1, max_rounds)})
    for node, case, route, default in (("start", "finish", "finish", "continue"),
            ("decision", "execute", "execute", "skip"), ("executed", "ok", "executed", "failed")):
        body.add_router(node, (RouterCase(id=case, predicate=Predicate(field="route", operator=PredicateOperator.EQ, value=route)),), default=default)
    body.add_state("save", StateSpec(key="guiexplorer_episode", data_type="m3a_frame", scope=StateScope.RUN, operation=StateOperation.WRITE)).add_output()
    edges = (
        "input.value previous.control", "input.task resume.task", "previous.value resume.previous",
        "resume.frame history.frame", "resume.frame ready.frame", "memory.context ready.memory", "ready.result start.value",
        "ready.result finish_round.frame", "finish_round.result commit.values", "ready.result observe_before.frame",
        "observe_before.observation perceive_before.observation", "perceive_before.view retrieve.view",
        "resume.frame rank.frame", "retrieve.knowledge rank.knowledge", "rank.ranked select.knowledge",
        "resume.frame select.frame", "memory.context select.memory", "select.result decision.value",
        "select.result skip_round.frame", "skip_round.result commit.values", "select.result execute.frame",
        "execute.result executed.value", "execute.result failed_round.frame", "failed_round.result commit.values",
        "execute.result observe_after.frame", "observe_after.observation perceive_after.observation",
        "execute.result summary.frame", "perceive_after.view summary.view", "summary.result commit.values",
        "commit.result wait_round.frame", "wait_round.result save.write", "save.value output.result",
    )
    for edge in edges:
        start, end = (value.split(".") for value in edge.split())
        body.connect(*start, *end)
    body.connect("history", "fragment", "memory", "write", condition=Predicate(field="content", operator=PredicateOperator.EXISTS))
    for node, branch, target in (("start", "finish", "finish_round"), ("start", "continue", "observe_before"),
            ("decision", "skip", "skip_round"), ("decision", "execute", "execute"),
            ("executed", "failed", "failed_round"), ("executed", "ok", "observe_after"), ("executed", "ok", "summary")):
        body.control(node, branch, target)
    loop = LoopSpec(body=SubgraphSpec(graph=body.build(), inputs={"task": "task", "value": "value"},
        outputs={"result": "result"}, max_activations=48), inputs={"task": "task", "value": "value"},
        outputs={"result": "result"}, until=Predicate(field="result.finished", operator=PredicateOperator.TRUTHY),
        max_iterations=max_rounds + 1, max_activations=(max_rounds + 1) * 48, on_exhausted="fail")
    return (AgentGraphBuilder(policies=policy).add_input().add_loop("online", loop)
        .add_component("finish", namespace="agent.memory", name="guiexplorer_finish", contract=_ref("finish"))
        .add_output().connect("input", "task", "online", "task").connect("input", "value", "online", "value")
        .connect("online", "result", "finish", "frame").connect("finish", "result", "output", "result").build())
