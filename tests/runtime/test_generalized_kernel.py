from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zhixing.components import RuntimeContext
from zhixing.graph import (
    AgentGraph,
    ComponentBinding,
    ContractPort,
    BindingPolicy,
    EdgeKind,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    InvocationAdapterKind,
    LoopSpec,
    NodeContractRef,
    NodeContract,
    NodeContractCatalog,
    NodeKind,
    NodeLifecycle,
    PortAddress,
    PortDirection,
    Predicate,
    PredicateOperator,
    RouterCase,
    RouterSpec,
    StateMergePolicy,
    StateOperation,
    StateScope,
    StateSpec,
    SubgraphSpec,
)
from zhixing.runtime import (
    GraphExecutionKernel,
    KernelStatus,
    SimpleCancellationSignal,
    bind_execution_plan,
)


_TRANSFORM = NodeContractRef(id="zhixing.control.transform", version="1.0")
_TOOL = NodeContractRef(id="zhixing.extension.tool", version="1.0")


@dataclass
class Scripted:
    """Fake typed component with deterministic outputs and context capture."""

    outputs: list[Any]
    calls: list[tuple[Any, RuntimeContext]] = field(default_factory=list)

    def invoke(self, value: Any, runtime: RuntimeContext) -> Any:
        """Return the next scripted output.

        Args:
            value (Any): Typed adapter input.
            runtime (RuntimeContext): Shared run context.

        Raises:
            AssertionError: The script has no remaining output.

        Returns:
            Any: Next scripted output.
        """
        self.calls.append((value, runtime))
        assert self.outputs
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def _binding(name: str) -> ComponentBinding:
    """Create one explicit fake component binding.

    Args:
        name (str): Candidate name.

    Raises:
        ValueError: Binding validation fails.

    Returns:
        ComponentBinding: Single-candidate binding.
    """
    return ComponentBinding(
        candidates=(GraphComponentRef(namespace="test", name=name),)
    )


def _component(node_id: str, contract: NodeContractRef = _TRANSFORM) -> GraphNode:
    """Create one generalized fake component node.

    Args:
        node_id (str): Stable node/candidate ID.
        contract (NodeContractRef): Exact contract reference.

    Raises:
        ValueError: Node validation fails.

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


def _edge(
    source: str,
    source_port: str,
    target: str,
    target_port: str,
    kind: EdgeKind = EdgeKind.DATA,
) -> GraphEdge:
    """Create one generalized runtime test edge.

    Args:
        source (str): Source node.
        source_port (str): Source port.
        target (str): Target node.
        target_port (str): Target port.
        kind (EdgeKind): Edge kind.

    Raises:
        ValueError: Edge validation fails.

    Returns:
        GraphEdge: Test edge.
    """
    return GraphEdge(
        source=PortAddress(node=source, port=source_port),
        target=PortAddress(node=target, port=target_port),
        kind=kind,
    )


def _input() -> GraphNode:
    """Create the standard generalized input node.

    Args:
        None.

    Raises:
        None.

    Returns:
        GraphNode: Input node.
    """
    return GraphNode(id="input", kind=NodeKind.INPUT, lifecycle=NodeLifecycle.ON_RUN_START)


def _output() -> GraphNode:
    """Create the standard generalized output node.

    Args:
        None.

    Raises:
        None.

    Returns:
        GraphNode: Output node.
    """
    return GraphNode(id="output", kind=NodeKind.OUTPUT, lifecycle=NodeLifecycle.TERMINAL)


def _child(component_name: str, contract: NodeContractRef = _TRANSFORM) -> AgentGraph:
    """Create one input/component/output child graph.

    Args:
        component_name (str): Child component name.
        contract (NodeContractRef): Exact child contract.

    Raises:
        ValueError: Graph construction fails.

    Returns:
        AgentGraph: Child graph.
    """
    return AgentGraph(
        contract_version="1.1",
        nodes=(_input(), _component(component_name, contract), _output()),
        edges=(
            _edge("input", "value", component_name, "request" if contract == _TOOL else "value"),
            _edge(component_name, "result", "output", "result"),
        ),
    )


def test_router_is_ordered_and_only_selected_branch_runs() -> None:
    """Execute an N-way router and prove inactive control branches are skipped.

    Args:
        None.

    Raises:
        AssertionError: Router behavior differs from first-match semantics.

    Returns:
        None.
    """
    router = GraphNode(
        id="router",
        kind=NodeKind.ROUTER,
        lifecycle=NodeLifecycle.PER_STEP,
        router=RouterSpec(
            cases=(
                RouterCase(
                    id="tool",
                    predicate=Predicate(field="kind", operator=PredicateOperator.EQ, value="tool"),
                ),
                RouterCase(
                    id="action",
                    predicate=Predicate(field="kind", operator=PredicateOperator.EQ, value="action"),
                ),
            ),
            default="finish",
        ),
    )
    graph = AgentGraph(
        contract_version="1.1",
        nodes=(
            _input(),
            router,
            _component("tool", _TOOL),
            _component("action"),
            _component("finish"),
            _output(),
        ),
        edges=(
            _edge("input", "value", "router", "value"),
            _edge("input", "value", "tool", "request"),
            _edge("input", "value", "action", "value"),
            _edge("input", "value", "finish", "value"),
            _edge("router", "tool", "tool", "control", EdgeKind.CONTROL),
            _edge("router", "action", "action", "control", EdgeKind.CONTROL),
            _edge("router", "finish", "finish", "control", EdgeKind.CONTROL),
            _edge("tool", "result", "output", "result"),
            _edge("action", "result", "output", "result"),
            _edge("finish", "result", "output", "result"),
        ),
    )
    tool = Scripted([{"selected": "tool"}])
    action = Scripted([{"selected": "action"}])
    finish = Scripted([{"selected": "finish"}])
    result = GraphExecutionKernel().run(
        bind_execution_plan(
            graph,
            {"tool": tool, "action": action, "finish": finish},
        ),
        {"value": {"kind": "action"}},
    )
    assert result.status is KernelStatus.SUCCESS
    assert result.outputs == {"result": {"selected": "action"}}
    assert len(action.calls) == 1
    assert not tool.calls
    assert not finish.calls


def test_state_replace_append_and_scope_are_explicit() -> None:
    """Exercise typed run state without using RuntimeContext.metadata as a bus.

    Args:
        None.

    Raises:
        AssertionError: State behavior or events are incorrect.

    Returns:
        None.
    """
    write = GraphNode(
        id="write",
        kind=NodeKind.STATE,
        lifecycle=NodeLifecycle.STATEFUL,
        state=StateSpec(
            key="history",
            data_type="any",
            scope=StateScope.RUN,
            operation=StateOperation.WRITE,
            merge=StateMergePolicy.APPEND,
            initial=[],
        ),
    )
    read = GraphNode(
        id="read",
        kind=NodeKind.STATE,
        lifecycle=NodeLifecycle.STATEFUL,
        state=StateSpec(
            key="history",
            data_type="any",
            scope=StateScope.RUN,
            operation=StateOperation.READ,
            initial=[],
        ),
    )
    graph = AgentGraph(
        contract_version="1.1",
        nodes=(_input(), write, read, _output()),
        edges=(
            _edge("input", "value", "write", "write"),
            _edge("write", "value", "read", "control", EdgeKind.CONTROL),
            _edge("read", "value", "output", "result"),
        ),
    )
    result = GraphExecutionKernel().run(
        bind_execution_plan(graph, {}),
        {"value": "first"},
    )
    assert result.status is KernelStatus.SUCCESS
    assert result.outputs == {"result": ["first"]}
    assert result.state["run:/:history"] == ["first"]
    assert any(event.kind == "state_transition" for event in result.events)


def test_local_loop_has_independent_iteration_and_interaction_counters() -> None:
    """Run two tool iterations in one physical interaction step.

    Args:
        None.

    Raises:
        AssertionError: Loop identity, output, or counters are incorrect.

    Returns:
        None.
    """
    child = _child("tool", _TOOL)
    loop = GraphNode(
        id="loop",
        kind=NodeKind.LOOP,
        lifecycle=NodeLifecycle.PER_STEP,
        loop=LoopSpec(
            body=SubgraphSpec(
                graph=child,
                inputs={"value": "value"},
                outputs={"result": "result"},
                max_activations=10,
            ),
            inputs={"value": "value"},
            outputs={"result": "result"},
            until=Predicate(field="result.done", operator=PredicateOperator.EQ, value=True),
            max_iterations=3,
            max_activations=30,
            on_exhausted="fail",
        ),
    )
    graph = AgentGraph(
        contract_version="1.1",
        nodes=(_input(), loop, _output()),
        edges=(
            _edge("input", "value", "loop", "value"),
            _edge("loop", "result", "output", "result"),
        ),
    )
    tool = Scripted(
        [
            {"done": False, "observation": "first"},
            {"done": True, "observation": "second"},
        ]
    )
    context = RuntimeContext(run_id="loop-run")
    result = GraphExecutionKernel().run(
        bind_execution_plan(graph, {"tool": tool}),
        {"value": {"request": "inspect"}},
        runtime=context,
    )
    assert result.status is KernelStatus.SUCCESS
    assert result.outputs["result"]["observation"] == "second"
    assert result.interaction_steps == 0
    assert len(tool.calls) == 2
    assert all(call_context is context for _value, call_context in tool.calls)
    iterations = [event.loop_iteration for event in result.events if event.kind == "loop_iteration"]
    assert iterations == [0, 1]


def test_subgraph_events_are_hierarchical_and_private_state_is_cleared() -> None:
    """Execute an inline child and inspect stable parent/child event paths.

    Args:
        None.

    Raises:
        AssertionError: Subgraph output or event hierarchy is incorrect.

    Returns:
        None.
    """
    child = _child("operator")
    subgraph = GraphNode(
        id="operator_graph",
        kind=NodeKind.SUBGRAPH,
        lifecycle=NodeLifecycle.PER_STEP,
        subgraph=SubgraphSpec(
            graph=child,
            inputs={"value": "value"},
            outputs={"result": "result"},
            max_activations=10,
        ),
    )
    graph = AgentGraph(
        contract_version="1.1",
        nodes=(_input(), subgraph, _output()),
        edges=(
            _edge("input", "value", "operator_graph", "value"),
            _edge("operator_graph", "result", "output", "result"),
        ),
    )
    result = GraphExecutionKernel().run(
        bind_execution_plan(graph, {"operator": Scripted(["proposal"])}),
        {"value": "task"},
    )
    assert result.status is KernelStatus.SUCCESS
    assert result.outputs == {"result": "proposal"}
    child_events = [
        event for event in result.events if event.node_path == "operator_graph/operator"
    ]
    assert [event.kind for event in child_events] == ["start", "complete"]
    assert child_events[0].parent_activation_id


def test_budget_and_cancellation_stop_before_new_activation() -> None:
    """Normalize bounded execution and cooperative cancellation outcomes.

    Args:
        None.

    Raises:
        AssertionError: Budget or cancellation boundaries are violated.

    Returns:
        None.
    """
    graph = _child("transform")
    limited = graph.model_copy(
        update={"policies": graph.policies.model_copy(update={"max_activations": 1})}
    )
    budget_result = GraphExecutionKernel().run(
        bind_execution_plan(limited, {"transform": Scripted(["done"])}),
        {"value": "task"},
    )
    assert budget_result.status is KernelStatus.BUDGET_EXHAUSTED
    assert not any(event.node_path == "transform" for event in budget_result.events)

    cancellation = SimpleCancellationSignal(cancelled=True)
    context = RuntimeContext(cancellation=cancellation)
    cancelled = GraphExecutionKernel().run(
        bind_execution_plan(graph, {"transform": Scripted(["done"])}),
        {"value": "task"},
        runtime=context,
    )
    assert cancelled.status is KernelStatus.CANCELLED
    assert cancelled.error_code == "runtime.cancelled"
    assert cancelled.activation_count == 0


def test_non_idempotent_tool_does_not_fallback_after_call_starts() -> None:
    """Prevent duplicate external effects when a Tool candidate raises.

    Args:
        None.

    Raises:
        AssertionError: A second non-idempotent candidate is invoked.

    Returns:
        None.
    """
    binding = ComponentBinding(
        policy=BindingPolicy.FALLBACK,
        candidates=(
            GraphComponentRef(namespace="test", name="first"),
            GraphComponentRef(namespace="test", name="second"),
        ),
    )
    graph = AgentGraph(
        contract_version="1.1",
        nodes=(
            _input(),
            GraphNode(
                id="tool",
                kind=NodeKind.COMPONENT,
                contract=_TOOL,
                lifecycle=NodeLifecycle.PER_STEP,
                component=binding,
            ),
            _output(),
        ),
        edges=(
            _edge("input", "value", "tool", "request"),
            _edge("tool", "result", "output", "result"),
        ),
    )
    first = Scripted([RuntimeError("failed after side effect")])
    second = Scripted([{"unexpected": True}])
    result = GraphExecutionKernel().run(
        bind_execution_plan(graph, {"first": first, "second": second}),
        {"value": {"tool": "write"}},
    )
    assert result.status is KernelStatus.FAILURE
    assert len(first.calls) == 1
    assert not second.calls


def test_loop_exhaustion_policies_are_distinct() -> None:
    """Normalize fail, continue, and terminate without advancing interaction.

    Args:
        None.

    Raises:
        AssertionError: An exhausted policy maps to the wrong result.

    Returns:
        None.
    """
    expected = {
        "fail": KernelStatus.FAILURE,
        "continue": KernelStatus.SUCCESS,
        "terminate": KernelStatus.TERMINATED,
    }
    for policy, expected_status in expected.items():
        child = _child("tool", _TOOL)
        loop = GraphNode(
            id="loop",
            kind=NodeKind.LOOP,
            lifecycle=NodeLifecycle.PER_STEP,
            loop=LoopSpec(
                body=SubgraphSpec(
                    graph=child,
                    inputs={"value": "value"},
                    outputs={"result": "result"},
                    max_activations=10,
                ),
                inputs={"value": "value"},
                outputs={"result": "result"},
                until=Predicate(
                    field="result.done",
                    operator=PredicateOperator.EQ,
                    value=True,
                ),
                max_iterations=1,
                max_activations=10,
                on_exhausted=policy,
            ),
        )
        graph = AgentGraph(
            contract_version="1.1",
            nodes=(_input(), loop, _output()),
            edges=(
                _edge("input", "value", "loop", "value"),
                _edge("loop", "result", "output", "result"),
            ),
        )
        result = GraphExecutionKernel().run(
            bind_execution_plan(
                graph,
                {"tool": Scripted([{"done": False, "policy": policy}])},
            ),
            {"value": "request"},
        )
        assert result.status is expected_status
        assert result.interaction_steps == 0
        assert any(event.kind == "loop_exhausted" for event in result.events)


def test_sibling_subgraph_run_state_is_private_by_default() -> None:
    """Prove siblings do not share run state unless a key is declared shared.

    Args:
        None.

    Raises:
        AssertionError: Private/shared state behavior is incorrect.

    Returns:
        None.
    """
    write = GraphNode(
        id="write",
        kind=NodeKind.STATE,
        lifecycle=NodeLifecycle.STATEFUL,
        state=StateSpec(
            key="messages",
            data_type="any",
            scope=StateScope.RUN,
            operation=StateOperation.WRITE,
            merge=StateMergePolicy.APPEND,
            initial=[],
        ),
    )
    child = AgentGraph(
        contract_version="1.1",
        nodes=(_input(), write, _output()),
        edges=(
            _edge("input", "value", "write", "write"),
            _edge("write", "value", "output", "result"),
        ),
    )

    def parent(shared: bool) -> AgentGraph:
        """Build two sibling invocations with optional shared state.

        Args:
            shared (bool): Whether the ``messages`` key is explicitly shared.

        Raises:
            ValueError: Graph construction fails.

        Returns:
            AgentGraph: Parent graph.
        """
        sharing = ("messages",) if shared else ()
        first = GraphNode(
            id="first",
            kind=NodeKind.SUBGRAPH,
            lifecycle=NodeLifecycle.PER_STEP,
            subgraph=SubgraphSpec(
                graph=child,
                inputs={"value": "value"},
                outputs={"result": "result"},
                shared_state=sharing,
            ),
        )
        second = GraphNode(
            id="second",
            kind=NodeKind.SUBGRAPH,
            lifecycle=NodeLifecycle.PER_STEP,
            subgraph=SubgraphSpec(
                graph=child,
                inputs={"value": "value"},
                outputs={"result": "result"},
                shared_state=sharing,
            ),
        )
        return AgentGraph(
            contract_version="1.1",
            nodes=(_input(), first, second, _output()),
            edges=(
                _edge("input", "value", "first", "value"),
                _edge("first", "result", "second", "value"),
                _edge("second", "result", "output", "result"),
            ),
        )

    private = GraphExecutionKernel().run(
        bind_execution_plan(parent(False), {}),
        {"value": "message"},
    )
    shared = GraphExecutionKernel().run(
        bind_execution_plan(parent(True), {}),
        {"value": "message"},
    )
    assert private.outputs == {"result": [["message"]]}
    assert shared.outputs == {"result": ["message", ["message"]]}


def test_extension_output_contract_is_checked_at_runtime() -> None:
    """Reject a component value that contradicts its explicit contract.

    Args:
        None.

    Raises:
        AssertionError: Runtime output type checking is bypassed.

    Returns:
        None.
    """
    reference = NodeContractRef(id="example.text", version="1.0")
    contract = NodeContract(
        ref=reference,
        ports=(
            ContractPort(
                id="value",
                direction=PortDirection.INPUT,
                data_types=("text",),
                required=True,
            ),
            ContractPort(
                id="result",
                direction=PortDirection.OUTPUT,
                data_types=("text",),
            ),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    )
    catalog = NodeContractCatalog((contract,))
    graph = AgentGraph(
        contract_version="1.1",
        nodes=(
            _input(),
            _component("text_component", reference),
            _output(),
        ),
        edges=(
            _edge("input", "value", "text_component", "value"),
            _edge("text_component", "result", "output", "result"),
        ),
    )
    result = GraphExecutionKernel().run(
        bind_execution_plan(
            graph,
            {"text_component": Scripted([42])},
            contract_catalog=catalog,
        ),
        {"value": "valid input"},
    )
    assert result.status is KernelStatus.FAILURE
    assert result.error_code == "runtime.component_candidates_exhausted"
