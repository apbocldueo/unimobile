"""Versioned golden AgentGraph templates for representative Agent paradigms."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

from .contracts import NodeContractRef
from .enums import EdgeKind, FeedbackExhaustedPolicy, NodeKind, NodeLifecycle, PredicateOperator, StateMergePolicy, StateOperation, StateScope
from .models import (
    AgentGraph,
    ComponentBinding,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    GraphPolicies,
    LoopSpec,
    FeedbackPolicy,
    PortAddress,
    Predicate,
    RouterCase,
    RouterSpec,
    StateSpec,
    SubgraphSpec,
)


_TRANSFORM = NodeContractRef(id="zhixing.control.transform", version="1.0")
_TOOL = NodeContractRef(id="zhixing.extension.tool", version="1.0")
_GROUNDER = NodeContractRef(id="zhixing.extension.grounder", version="1.0")
_ACTION = NodeContractRef(id="zhixing.service.action", version="1.0")


def _binding(name: str) -> ComponentBinding:
    """Create one explicit built-in template component binding.

    Args:
        name (str): Component candidate name.

    Raises:
        ValueError: Component model validation rejects the declaration.

    Returns:
        ComponentBinding: Single-candidate binding.
    """
    return ComponentBinding(
        candidates=(GraphComponentRef(namespace="agent.template", name=name),)
    )


def _component(
    node_id: str,
    *,
    contract: NodeContractRef = _TRANSFORM,
) -> GraphNode:
    """Create one contract 1.1 component node.

    Args:
        node_id (str): Stable node and candidate identifier.
        contract (NodeContractRef): Exact node contract.

    Raises:
        ValueError: GraphNode validation rejects the declaration.

    Returns:
        GraphNode: Component node.
    """
    return GraphNode(
        id=node_id,
        kind=NodeKind.COMPONENT,
        contract=contract,
        lifecycle=NodeLifecycle.PER_STEP,
        component=_binding(node_id),
    )


def _input() -> GraphNode:
    """Create the conventional template input node.

    Args:
        None.

    Raises:
        None.

    Returns:
        GraphNode: Input node.
    """
    return GraphNode(
        id="input",
        kind=NodeKind.INPUT,
        lifecycle=NodeLifecycle.ON_RUN_START,
    )


def _output(node_id: str = "output") -> GraphNode:
    """Create one conventional template output node.

    Args:
        node_id (str): Stable output node identifier.

    Raises:
        None.

    Returns:
        GraphNode: Terminal output node.
    """
    return GraphNode(
        id=node_id,
        kind=NodeKind.OUTPUT,
        lifecycle=NodeLifecycle.TERMINAL,
    )


def _edge(
    source: str,
    source_port: str,
    target: str,
    target_port: str,
    kind: EdgeKind = EdgeKind.DATA,
) -> GraphEdge:
    """Create one template edge.

    Args:
        source (str): Source node ID.
        source_port (str): Source output port.
        target (str): Target node ID.
        target_port (str): Target input port.
        kind (EdgeKind): Data or control edge kind.

    Raises:
        ValueError: GraphEdge validation rejects the declaration.

    Returns:
        GraphEdge: Validated edge.
    """
    return GraphEdge(
        source=PortAddress(node=source, port=source_port),
        target=PortAddress(node=target, port=target_port),
        kind=kind,
    )


def _graph(nodes: tuple[GraphNode, ...], edges: tuple[GraphEdge, ...]) -> AgentGraph:
    """Create a contract 1.1 template graph with bounded budgets.

    Args:
        nodes (tuple[GraphNode, ...]): Graph nodes.
        edges (tuple[GraphEdge, ...]): Graph edges.

    Raises:
        ValueError: AgentGraph model validation rejects the declaration.

    Returns:
        AgentGraph: Immutable template graph.
    """
    return AgentGraph(
        contract_version="1.1",
        nodes=nodes,
        edges=edges,
        policies=GraphPolicies(max_steps=20, max_activations=500, max_nesting_depth=8),
    )


def _transform_subgraph(component_name: str) -> AgentGraph:
    """Create a reusable one-component typed subgraph.

    Args:
        component_name (str): Transform component node/candidate name.

    Raises:
        ValueError: Graph model construction fails.

    Returns:
        AgentGraph: Input → transform → output child graph.
    """
    return _graph(
        (_input(), _component(component_name), _output()),
        (
            _edge("input", "value", component_name, "value"),
            _edge(component_name, "result", "output", "result"),
        ),
    )


def modular_template(
    *,
    include_planner: bool = True,
    include_memory: bool = True,
    include_verifier: bool = False,
) -> AgentGraph:
    """Build the modular component pipeline golden template.

    Args:
        include_planner (bool): Include the optional Planner slot.
        include_memory (bool): Include the optional Memory slot.
        include_verifier (bool): Include the optional post-action Verifier slot.

    Raises:
        ValueError: Graph construction fails.

    Returns:
        AgentGraph: Perception/planner/reasoning/memory/action pipeline.
    """
    names = ["perception"]
    if include_planner:
        names.append("planner")
    names.append("reasoning")
    if include_memory:
        names.append("memory")
    nodes: list[GraphNode] = [
        _input(),
        *(_component(name) for name in names),
        _component("action", contract=_ACTION),
    ]
    edges = [_edge("input", "value", names[0], "value")]
    chain = [*names, "action"]
    for source, target in zip(chain, chain[1:]):
        edges.append(
            _edge(
                source,
                "result",
                target,
                "request" if target == "action" else "value",
            )
        )
    terminal_source = "action"
    if include_verifier:
        nodes.append(_component("verifier"))
        edges.append(_edge("action", "result", "verifier", "value"))
        edges.append(
            GraphEdge(
                source=PortAddress(node="verifier", port="result"),
                target=PortAddress(node="reasoning", port="control"),
                kind=EdgeKind.FEEDBACK,
                feedback=FeedbackPolicy(
                    predicate=Predicate(
                        field="retry",
                        operator=PredicateOperator.EQ,
                        value=True,
                    ),
                    max_iterations=2,
                    on_exhausted=FeedbackExhaustedPolicy.CONTINUE,
                ),
            )
        )
        terminal_source = "verifier"
    nodes.append(_output())
    edges.append(_edge(terminal_source, "result", "output", "result"))
    return _graph(tuple(nodes), tuple(edges))


def reflection_template() -> AgentGraph:
    """Build an actor/critique/correction branching template.

    Args:
        None.

    Raises:
        ValueError: Graph construction fails.

    Returns:
        AgentGraph: Reflection graph with explicit correction branch.
    """
    router = GraphNode(
        id="reflection_router",
        kind=NodeKind.ROUTER,
        lifecycle=NodeLifecycle.PER_STEP,
        router=RouterSpec(
            cases=(
                RouterCase(
                    id="revise",
                    predicate=Predicate(
                        field="needs_revision",
                        operator=PredicateOperator.EQ,
                        value=True,
                    ),
                ),
            ),
            default="accept",
        ),
    )
    nodes = (
        _input(),
        _component("perception"),
        _component("actor"),
        _component("critique"),
        router,
        _component("correction"),
        _component("revised_action", contract=_ACTION),
        _component("accepted_action", contract=_ACTION),
        _output(),
    )
    edges = (
        _edge("input", "value", "perception", "value"),
        _edge("perception", "result", "actor", "value"),
        _edge("actor", "result", "critique", "value"),
        _edge("critique", "result", "reflection_router", "value"),
        _edge("critique", "result", "correction", "value"),
        _edge("reflection_router", "revise", "correction", "control", EdgeKind.CONTROL),
        _edge("correction", "result", "revised_action", "request"),
        _edge("reflection_router", "revise", "revised_action", "control", EdgeKind.CONTROL),
        _edge("actor", "result", "accepted_action", "request"),
        _edge("reflection_router", "accept", "accepted_action", "control", EdgeKind.CONTROL),
        _edge("revised_action", "result", "output", "result"),
        _edge("accepted_action", "result", "output", "result"),
    )
    return _graph(nodes, edges)


def react_template() -> AgentGraph:
    """Build a ReAct local tool-loop template with Action and Finish exits.

    Args:
        None.

    Raises:
        ValueError: Graph construction fails.

    Returns:
        AgentGraph: Bounded reasoning/tool loop and exit router.
    """
    tool_router = GraphNode(
        id="tool_router",
        kind=NodeKind.ROUTER,
        lifecycle=NodeLifecycle.PER_STEP,
        router=RouterSpec(
            cases=(
                RouterCase(
                    id="tool",
                    predicate=Predicate(
                        field="tool",
                        operator=PredicateOperator.EXISTS,
                    ),
                ),
            ),
            default="unsupported",
        ),
    )
    tool_history = GraphNode(
        id="tool_history",
        kind=NodeKind.STATE,
        lifecycle=NodeLifecycle.STATEFUL,
        state=StateSpec(
            key="tool_history",
            data_type="any",
            scope=StateScope.LOOP,
            operation=StateOperation.WRITE,
            merge=StateMergePolicy.APPEND,
            initial=[],
        ),
    )
    body = _graph(
        (
            _input(),
            _component("react_reasoning"),
            tool_router,
            _component("react_tool", contract=_TOOL),
            tool_history,
            _output(),
        ),
        (
            _edge("input", "value", "react_reasoning", "value"),
            _edge("react_reasoning", "result", "tool_router", "value"),
            _edge("react_reasoning", "result", "react_tool", "request"),
            _edge("tool_router", "tool", "react_tool", "control", EdgeKind.CONTROL),
            # The State node is an explicit audit sink; the Tool value still
            # reaches the loop output unchanged for the until predicate.
            _edge("react_tool", "result", "tool_history", "write"),
            _edge("react_tool", "result", "output", "result"),
        ),
    )
    loop = GraphNode(
        id="tool_loop",
        kind=NodeKind.LOOP,
        lifecycle=NodeLifecycle.PER_STEP,
        loop=LoopSpec(
            body=SubgraphSpec(
                graph=body,
                inputs={"value": "value"},
                outputs={"result": "result"},
                max_activations=20,
            ),
            inputs={"value": "value"},
            outputs={"result": "result"},
            until=Predicate(
                field="result.done",
                operator=PredicateOperator.EQ,
                value=True,
            ),
            max_iterations=4,
            max_activations=80,
            on_exhausted="continue",
        ),
    )
    router = GraphNode(
        id="exit_router",
        kind=NodeKind.ROUTER,
        lifecycle=NodeLifecycle.PER_STEP,
        router=RouterSpec(
            cases=(
                RouterCase(
                    id="action",
                    predicate=Predicate(
                        field="kind",
                        operator=PredicateOperator.EQ,
                        value="action",
                    ),
                ),
            ),
            default="finish",
        ),
    )
    nodes = (
        _input(),
        loop,
        router,
        _component("react_action", contract=_ACTION),
        _component("finish"),
        _output(),
    )
    edges = (
        _edge("input", "value", "tool_loop", "value"),
        _edge("tool_loop", "result", "exit_router", "value"),
        _edge("tool_loop", "result", "react_action", "request"),
        _edge("exit_router", "action", "react_action", "control", EdgeKind.CONTROL),
        _edge("tool_loop", "result", "finish", "value"),
        _edge("exit_router", "finish", "finish", "control", EdgeKind.CONTROL),
        _edge("react_action", "result", "output", "result"),
        _edge("finish", "result", "output", "result"),
    )
    return _graph(nodes, edges)


def planner_execute_template() -> AgentGraph:
    """Build a planner/state/execute-loop template.

    Args:
        None.

    Raises:
        ValueError: Graph construction fails.

    Returns:
        AgentGraph: Planner-and-Execute graph with run state and local iteration.
    """
    body = _transform_subgraph("execute_step")
    loop = GraphNode(
        id="plan_iterator",
        kind=NodeKind.LOOP,
        lifecycle=NodeLifecycle.PER_STEP,
        loop=LoopSpec(
            body=SubgraphSpec(
                graph=body,
                inputs={"value": "value"},
                outputs={"result": "result"},
                max_activations=20,
            ),
            inputs={"value": "value"},
            outputs={"result": "result"},
            until=Predicate(field="result.done", operator=PredicateOperator.EQ, value=True),
            max_iterations=5,
            max_activations=100,
            on_exhausted="fail",
        ),
    )
    state = GraphNode(
        id="plan_state",
        kind=NodeKind.STATE,
        lifecycle=NodeLifecycle.STATEFUL,
        state=StateSpec(
            key="plan",
            data_type="any",
            scope=StateScope.RUN,
            operation=StateOperation.WRITE,
            merge=StateMergePolicy.REPLACE,
        ),
    )
    replan_router = GraphNode(
        id="replan_router",
        kind=NodeKind.ROUTER,
        lifecycle=NodeLifecycle.PER_STEP,
        router=RouterSpec(
            cases=(
                RouterCase(
                    id="replan",
                    predicate=Predicate(
                        field="replan",
                        operator=PredicateOperator.EQ,
                        value=True,
                    ),
                ),
            ),
            default="execute",
        ),
    )
    return _graph(
        (
            _input(),
            _component("planner"),
            state,
            loop,
            replan_router,
            _component("replanner"),
            _component("replan_action", contract=_ACTION),
            _component("plan_action", contract=_ACTION),
            _output(),
        ),
        (
            _edge("input", "value", "planner", "value"),
            _edge("planner", "result", "plan_state", "write"),
            _edge("plan_state", "value", "plan_iterator", "value"),
            _edge("plan_iterator", "result", "replan_router", "value"),
            _edge("plan_iterator", "result", "plan_action", "request"),
            _edge("replan_router", "execute", "plan_action", "control", EdgeKind.CONTROL),
            _edge("plan_iterator", "result", "replanner", "value"),
            _edge("replan_router", "replan", "replanner", "control", EdgeKind.CONTROL),
            _edge("replanner", "result", "replan_action", "request"),
            _edge("replan_router", "replan", "replan_action", "control", EdgeKind.CONTROL),
            _edge("replan_action", "result", "output", "result"),
            _edge("plan_action", "result", "output", "result"),
        ),
    )


def uground_template() -> AgentGraph:
    """Build a semantic-target → grounding → action template.

    Args:
        None.

    Raises:
        ValueError: Graph construction fails.

    Returns:
        AgentGraph: UGround-style two-stage action graph.
    """
    return _graph(
        (
            _input(),
            _component("step_summary"),
            _component("uground_perception"),
            _component("semantic_reasoning"),
            _component("grounder", contract=_GROUNDER),
            _component("grounded_action", contract=_ACTION),
            _output(),
        ),
        (
            _edge("input", "value", "step_summary", "value"),
            _edge("step_summary", "result", "uground_perception", "value"),
            _edge("uground_perception", "result", "semantic_reasoning", "value"),
            _edge("semantic_reasoning", "result", "grounder", "target"),
            _edge("input", "observation", "grounder", "observation"),
            _edge("grounder", "result", "grounded_action", "request"),
            _edge("grounded_action", "result", "output", "result"),
        ),
    )


def multi_agent_template() -> AgentGraph:
    """Build a sequential Manager/Operator/Critic hierarchical template.

    Args:
        None.

    Raises:
        ValueError: Graph construction fails.

    Returns:
        AgentGraph: Three typed sequential subgraphs with root action arbitration.
    """
    nodes: list[GraphNode] = [_input()]
    edges: list[GraphEdge] = []
    previous_node = "input"
    previous_port = "value"
    for name in ("manager", "operator", "critic"):
        node = GraphNode(
            id=name,
            kind=NodeKind.SUBGRAPH,
            lifecycle=NodeLifecycle.PER_STEP,
            subgraph=SubgraphSpec(
                graph=_transform_subgraph(f"{name}_component"),
                inputs={"value": "value"},
                outputs={"result": "result"},
                max_activations=20,
            ),
        )
        nodes.append(node)
        edges.append(_edge(previous_node, previous_port, name, "value"))
        previous_node, previous_port = name, "result"
    decision_router = GraphNode(
        id="collaboration_router",
        kind=NodeKind.ROUTER,
        lifecycle=NodeLifecycle.PER_STEP,
        router=RouterSpec(
            cases=(
                RouterCase(
                    id="revise",
                    predicate=Predicate(
                        field="decision",
                        operator=PredicateOperator.EQ,
                        value="revise",
                    ),
                ),
                RouterCase(
                    id="execute",
                    predicate=Predicate(
                        field="decision",
                        operator=PredicateOperator.EQ,
                        value="execute",
                    ),
                ),
            ),
            default="finish",
        ),
    )
    nodes.extend(
        (
            decision_router,
            _component("revision"),
            _component("revised_multi_action", contract=_ACTION),
            _component("multi_action", contract=_ACTION),
            _component("multi_finish"),
            _output(),
        )
    )
    edges.extend(
        (
            _edge("critic", "result", "collaboration_router", "value"),
            _edge("critic", "result", "multi_action", "request"),
            _edge(
                "collaboration_router",
                "execute",
                "multi_action",
                "control",
                EdgeKind.CONTROL,
            ),
            _edge("critic", "result", "revision", "value"),
            _edge(
                "collaboration_router",
                "revise",
                "revision",
                "control",
                EdgeKind.CONTROL,
            ),
            _edge("revision", "result", "revised_multi_action", "request"),
            _edge(
                "collaboration_router",
                "revise",
                "revised_multi_action",
                "control",
                EdgeKind.CONTROL,
            ),
            _edge("critic", "result", "multi_finish", "value"),
            _edge(
                "collaboration_router",
                "finish",
                "multi_finish",
                "control",
                EdgeKind.CONTROL,
            ),
            _edge("revised_multi_action", "result", "output", "result"),
            _edge("multi_action", "result", "output", "result"),
            _edge("multi_finish", "result", "output", "result"),
        )
    )
    return _graph(tuple(nodes), tuple(edges))


@dataclass(frozen=True)
class ParadigmTemplate:
    """One versioned graph template factory."""

    name: str
    version: str
    factory: Callable[[], AgentGraph]

    def build(self) -> AgentGraph:
        """Build a fresh immutable graph.

        Args:
            None.

        Raises:
            ValueError: Template graph construction fails.

        Returns:
            AgentGraph: Template graph.
        """
        return self.factory()


@dataclass(frozen=True)
class LegacyParadigmCompatibility:
    """Versioned compatibility status for one legacy AgentConfig strategy."""

    agent_type: str
    template_name: str
    template_version: str
    compilation_enabled: bool
    reason: str


PARADIGM_TEMPLATES = MappingProxyType(
    {
        "modular": ParadigmTemplate("modular", "1.0", modular_template),
        "reflection": ParadigmTemplate("reflection", "1.0", reflection_template),
        "react": ParadigmTemplate("react", "1.0", react_template),
        "planner_and_execute": ParadigmTemplate(
            "planner_and_execute",
            "1.0",
            planner_execute_template,
        ),
        "uground": ParadigmTemplate("uground", "1.0", uground_template),
        "multi_agent": ParadigmTemplate("multi_agent", "1.0", multi_agent_template),
    }
)

LEGACY_PARADIGM_COMPATIBILITY = MappingProxyType(
    {
        "modular_agent": LegacyParadigmCompatibility(
            agent_type="modular_agent",
            template_name="modular",
            template_version="1.0",
            compilation_enabled=True,
            reason="validated contract 1.0 compatibility compiler",
        ),
        "reflection_agent": LegacyParadigmCompatibility(
            agent_type="reflection_agent",
            template_name="reflection",
            template_version="1.0",
            compilation_enabled=False,
            reason="legacy typed component parity is not yet verified",
        ),
        "uground_agent": LegacyParadigmCompatibility(
            agent_type="uground_agent",
            template_name="uground",
            template_version="1.0",
            compilation_enabled=False,
            reason="legacy summary and grounding parity is not yet verified",
        ),
        "multi_agent": LegacyParadigmCompatibility(
            agent_type="multi_agent",
            template_name="multi_agent",
            template_version="1.0",
            compilation_enabled=False,
            reason="legacy manager/operator/critic parity is not yet verified",
        ),
    }
)


def get_paradigm_template(name: str) -> AgentGraph:
    """Build one registered paradigm template by stable name.

    Args:
        name (str): Template name.

    Raises:
        KeyError: The template is not registered.

    Returns:
        AgentGraph: Fresh template graph.
    """
    return PARADIGM_TEMPLATES[name].build()
