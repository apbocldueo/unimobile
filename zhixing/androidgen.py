"""Full standalone AndroidGen online composition using ordinary AgentGraph control."""

from typing import Any, Mapping

from zhixing.graph import (AgentGraph, AgentGraphBuilder, GraphPolicies, GraphRole, LoopSpec,
    NodeContractRef, Predicate, PredicateOperator, RouterCase, StateOperation, StateScope, StateSpec, SubgraphSpec)


def _ref(name: str) -> NodeContractRef:
    """Address a source-stage contract. Args: name: Suffix. Returns: NodeContractRef: Exact reference."""
    return NodeContractRef(id="zhixing.androidgen." + name, version="1.0")


def _wire(builder, edges) -> None:
    """Connect explicit stage ports without hiding Agent behavior in a preset.

    Args:
        builder: Graph builder receiving edges.
        edges: Source/target port-address pairs.
    Returns:
        None.
    """
    for source, target in edges:
        builder.connect(*source.split('.'), *target.split('.'))


def build_androidgen_graph(*, max_rounds: int = 31, max_plan_attempts: int = 3,
        reflectplan: bool = True, expsearch: bool = True, autocheck: bool = True,
        model_type: str = "text", planner_model_type: str = "text",
        model_params: Mapping[str, Any] | None = None, planner_model_params: Mapping[str, Any] | None = None,
        example_params: Mapping[str, Any] | None = None) -> AgentGraph:
    """Compose source initialization, all six families, retries, rounds and final flush.

    Args:
        max_rounds: Source logical-round bound; default is 31 (0 through 30).
        max_plan_attempts: Explicit finite replacement for unlimited source update retries.
        reflectplan: Enable the original planning branch.
        expsearch: Enable one original experience retrieval at startup.
        autocheck: Enable previous-fail message injection; action validation remains active.
        model_type: Independent actor text/image input type.
        planner_model_type: Independent planner text/image input type.
        model_params: Lazy original GPT transport settings.
        planner_model_params: Independent lazy planning transport settings.
        example_params: Lazy database/checkpoint settings, without live dependencies.
    Raises:
        ValueError: Bounds, switches, input types or public settings are invalid.
    Returns:
        AgentGraph: Complete source run.py online flow, without StepCritic database updates.
    """
    if type(max_rounds) is not int or not 1 <= max_rounds <= 999:
        raise ValueError("max_rounds must be an integer between 1 and 999")
    if type(max_plan_attempts) is not int or not 1 <= max_plan_attempts <= 20:
        raise ValueError("max_plan_attempts must be an integer between 1 and 20")
    if any(type(value) is not bool for value in (reflectplan, expsearch, autocheck)):
        raise ValueError("AndroidGen feature switches must be booleans")
    if model_type not in ("text", "image") or planner_model_type not in ("text", "image"):
        raise ValueError("model input types must be text or image")
    for params in (model_params, planner_model_params):
        if params is not None and (not isinstance(params, Mapping) or set(params) - {"model", "temperature", "top_p", "rate_limit"}):
            raise ValueError("unsupported AndroidGen model-wrapper settings")
    if example_params is not None and (not isinstance(example_params, Mapping) or
            set(example_params) - {"database_path", "retriever_ckpt_path", "device", "max_batch_size"}):
        raise ValueError("unsupported AndroidGen experience settings")
    per_round = 40 + max_plan_attempts * 8
    policy = GraphPolicies(max_steps=max_rounds + 1, max_activations=(max_rounds + 1) * per_round + 20)
    actor = {"llm": {"namespace": "llm", "name": "androidgen_llm", "params": dict(model_params or {})}}
    planner = {"planner_llm": {"namespace": "llm", "name": "androidgen_llm", "params": dict(planner_model_params or {})}}
    planning = AgentGraphBuilder(policies=policy).add_input()
    planning.add_state("previous", StateSpec(key="androidgen_planning", data_type="androidgen_frame", scope=StateScope.RUN, operation=StateOperation.READ))
    planning.add_component("attempt", namespace="agent.planner", name="androidgen_reflect_plan", role=GraphRole.PLANNER,
        contract=_ref("plan"), dependencies=planner,
        params={**({"enabled": False} if not reflectplan else {}), **({"model_type": planner_model_type} if planner_model_type != "text" else {})})
    planning.add_state("save", StateSpec(key="androidgen_planning", data_type="androidgen_frame", scope=StateScope.RUN, operation=StateOperation.WRITE)).add_output()
    _wire(planning, (("input.value", "previous.control"), ("input.value", "attempt.frame"),
        ("previous.value", "attempt.previous"), ("attempt.result", "save.write"), ("save.value", "output.result")))
    plan_loop = LoopSpec(body=SubgraphSpec(graph=planning.build(), inputs={"value": "value"},
        outputs={"result": "result"}, max_activations=8), inputs={"value": "value"}, outputs={"result": "result"},
        until=Predicate(field="result.planning_done", operator=PredicateOperator.TRUTHY), max_iterations=max_plan_attempts,
        max_activations=max_plan_attempts * 8, on_exhausted="fail")
    body = AgentGraphBuilder(policies=policy).add_input()
    body.add_state("previous", StateSpec(key="androidgen_episode", data_type="androidgen_frame", scope=StateScope.RUN, operation=StateOperation.READ))
    definitions = (
        ("resume", "memory", "resume", "resume", {"max_rounds": max_rounds} if max_rounds != 31 else {}),
        ("user", "memory", "history", "history", {}),
        ("assistant", "memory", "history", "history", {"role": "assistant"}),
        ("ready", "memory", "ready", "ready", {}),
        ("flush", "memory", "pass", "pass", {}),
        ("observe", "perception", "observe", "observe", {}),
        ("perceive", "perception", "perception", "perceive", {}),
        ("feedback", "verifier", "feedback", "feedback", {"enabled": False} if not autocheck else {}),
        ("reason", "reasoning", "reasoning", "reason", {"model_type": model_type} if model_type != "text" else {}),
        ("execute", "action_executor", "execute", "execute", {}),
        ("commit", "memory", "commit", "commit", {}),
    )
    for node, family, name, contract, params in definitions:
        body.add_component(node, namespace="agent." + family, name="androidgen_" + name,
            role=GraphRole(family) if node in ("perceive", "feedback", "reason", "execute") else None,
            contract=_ref(contract), params=params, dependencies=actor if node == "reason" else {}, primary=node == "execute")
    body.add_component("memory", namespace="agent.memory", name="sliding_window_memory", role=GraphRole.MEMORY,
        contract=NodeContractRef(id="zhixing.memory.fragments", version="1.0"), lifecycle="stateful", params={"window_size": 2 * max_rounds})
    body.add_router("start", (RouterCase(id="finish", predicate=Predicate(field="route", operator=PredicateOperator.EQ, value="finish")),), default="continue")
    body.add_loop("planning", plan_loop)
    body.add_state("save", StateSpec(key="androidgen_episode", data_type="androidgen_frame", scope=StateScope.RUN, operation=StateOperation.WRITE)).add_output()
    _wire(body, (("input.value", "previous.control"), ("input.value", "resume.initial"), ("previous.value", "resume.previous"),
        ("resume.frame", "user.frame"), ("resume.frame", "assistant.frame"), ("resume.frame", "ready.frame"), ("memory.context", "ready.memory"),
        ("ready.result", "start.value"), ("ready.result", "flush.frame"), ("flush.result", "commit.values"),
        ("ready.result", "observe.frame"), ("ready.result", "perceive.frame"), ("observe.observation", "perceive.observation"),
        ("perceive.result", "planning.value"), ("planning.result", "feedback.frame"), ("feedback.result", "reason.frame"),
        ("reason.result", "execute.frame"), ("execute.result", "commit.values"), ("commit.frame", "save.write"), ("save.value", "output.result")))
    for node in ("user", "assistant"):
        body.connect(node, "fragment", "memory", "write", condition=Predicate(field="content", operator=PredicateOperator.EXISTS))
    # Multiple writes retain activation order; enforce the source user/assistant
    # order with an explicit dependency, rather than relying on node names.
    body.control("user", "sequence", "assistant")
    body.control("start", "finish", "flush").control("start", "continue", "observe")
    loop = LoopSpec(body=SubgraphSpec(graph=body.build(), inputs={"value": "value"}, outputs={"result": "result"}, max_activations=per_round),
        inputs={"value": "value"}, outputs={"result": "result"}, until=Predicate(field="result.finished", operator=PredicateOperator.TRUTHY),
        max_iterations=max_rounds + 1, max_activations=(max_rounds + 1) * per_round, on_exhausted="fail")
    graph = (AgentGraphBuilder(policies=policy).add_input()
        .add_component("setup", namespace="agent.action_executor", name="androidgen_setup", contract=_ref("setup"))
        .add_component("bootstrap", namespace="agent.memory", name="androidgen_bootstrap", contract=_ref("bootstrap"),
            params={"enabled": False} if not expsearch else {},
            dependencies={"examples": {"namespace": "knowledge", "name": "androidgen_examples", "params": dict(example_params or {})}})
        .add_loop("online", loop)
        .add_component("finish", namespace="agent.memory", name="androidgen_finish", contract=_ref("finish")).add_output())
    _wire(graph, (("input.task", "setup.task"), ("setup.seed", "bootstrap.seed"), ("bootstrap.frame", "online.value"),
                  ("online.result", "finish.frame"), ("finish.result", "output.result")))
    return graph.build()
