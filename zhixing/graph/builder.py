"""Fluent, side-effect-free construction helpers for AgentGraph contract 1.1."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .enums import (
    EdgeKind,
    FeedbackExhaustedPolicy,
    GraphRole,
    NodeKind,
    NodeLifecycle,
    PredicateOperator,
)
from .models import (
    AgentGraph,
    ComponentBinding,
    ExecutionPolicy,
    FeedbackPolicy,
    GraphComponentRef,
    GraphEdge,
    GraphInterface,
    GraphNode,
    GraphPolicies,
    LoopSpec,
    PortAddress,
    Predicate,
    RouterCase,
    RouterSpec,
    StateSpec,
    SubgraphSpec,
)
from .contracts import NodeContractRef


class AgentGraphBuilder:
    """Build an explicit AgentGraph without selecting or running an Agent strategy."""

    def __init__(
        self,
        *,
        contract_version: str = "1.1",
        policies: GraphPolicies | Mapping[str, Any] | None = None,
        interface: GraphInterface | Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Create an empty graph builder.

        Args:
            contract_version (str): AgentGraph contract version. Defaults to ``1.1``.
            policies (GraphPolicies | Mapping[str, Any] | None): Explicit graph budgets.
            interface (GraphInterface | Mapping[str, Any] | None): Public graph ports.
            metadata (Mapping[str, Any] | None): Non-semantic graph metadata.

        Raises:
            ValueError: A contract version other than ``1.1`` is requested.

        Returns:
            None: Initializes mutable authoring state only.
        """
        if contract_version != "1.1":
            raise ValueError("AgentGraphBuilder only authors contract 1.1 graphs")
        self._contract_version = contract_version
        self._policies = (
            policies
            if isinstance(policies, GraphPolicies)
            else GraphPolicies.model_validate(policies or {})
        )
        self._interface = (
            interface
            if isinstance(interface, GraphInterface) or interface is None
            else GraphInterface.model_validate(interface)
        )
        self._metadata = dict(metadata or {})
        self._nodes: list[GraphNode] = []
        self._edges: list[GraphEdge] = []

    def _append_node(self, node: GraphNode) -> "AgentGraphBuilder":
        """Append one node while rejecting duplicate logical identities early.

        Args:
            node (GraphNode): Validated node declaration.

        Raises:
            ValueError: Another node already uses the same logical ID.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        if any(existing.id == node.id for existing in self._nodes):
            raise ValueError(f"duplicate AgentGraph node id: {node.id!r}")
        self._nodes.append(node)
        return self

    def add_input(
        self,
        node_id: str = "input",
        *,
        lifecycle: NodeLifecycle | str = NodeLifecycle.ON_RUN_START,
    ) -> "AgentGraphBuilder":
        """Add a graph input boundary node.

        Args:
            node_id (str): Stable logical node ID.
            lifecycle (NodeLifecycle | str): Input lifecycle.

        Raises:
            ValueError: Node validation or duplicate checking fails.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        return self._append_node(
            GraphNode(
                id=node_id,
                kind=NodeKind.INPUT,
                lifecycle=NodeLifecycle(lifecycle),
            )
        )

    def add_output(
        self,
        node_id: str = "output",
    ) -> "AgentGraphBuilder":
        """Add a terminal graph output boundary node.

        Args:
            node_id (str): Stable logical node ID.

        Raises:
            ValueError: Node validation or duplicate checking fails.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        return self._append_node(
            GraphNode(
                id=node_id,
                kind=NodeKind.OUTPUT,
                lifecycle=NodeLifecycle.TERMINAL,
            )
        )

    def add_component(
        self,
        node_id: str,
        *,
        binding: ComponentBinding | Mapping[str, Any] | None = None,
        namespace: str | None = None,
        name: str | None = None,
        version: str | None = None,
        params: Mapping[str, Any] | None = None,
        dependencies: Mapping[str, Any] | None = None,
        contract: NodeContractRef | Mapping[str, Any] | None = None,
        role: GraphRole | str | None = None,
        lifecycle: NodeLifecycle | str = NodeLifecycle.PER_STEP,
        primary: bool = False,
        execution: ExecutionPolicy | Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "AgentGraphBuilder":
        """Add one explicitly bound component or runtime-service marker node.

        Args:
            node_id (str): Stable logical node ID.
            binding (ComponentBinding | Mapping[str, Any] | None): Full binding.
            namespace (str | None): Candidate namespace for the concise form.
            name (str | None): Candidate name for the concise form.
            version (str | None): Optional candidate version.
            params (Mapping[str, Any] | None): Candidate constructor parameters.
            dependencies (Mapping[str, Any] | None): Declarative dependencies.
            contract (NodeContractRef | Mapping[str, Any] | None): Exact contract.
            role (GraphRole | str | None): Core role when no explicit contract is used.
            lifecycle (NodeLifecycle | str): Component lifecycle annotation.
            primary (bool): Whether this is the primary action boundary.
            execution (ExecutionPolicy | Mapping[str, Any] | None): Node budget/timeout.
            metadata (Mapping[str, Any] | None): Non-semantic node metadata.

        Raises:
            ValueError: Binding forms are mixed, incomplete, or invalid.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        if binding is None:
            if not namespace or not name:
                raise ValueError(
                    "add_component requires binding or namespace/name"
                )
            selected_binding = ComponentBinding(
                candidates=(
                    GraphComponentRef(
                        namespace=namespace,
                        name=name,
                        version=version,
                        params=dict(params or {}),
                        dependencies=dict(dependencies or {}),
                    ),
                )
            )
        else:
            if any(value is not None for value in (namespace, name, version, params, dependencies)):
                raise ValueError(
                    "full binding cannot be combined with concise component fields"
                )
            selected_binding = (
                binding
                if isinstance(binding, ComponentBinding)
                else ComponentBinding.model_validate(binding)
            )
        selected_contract = (
            contract
            if isinstance(contract, NodeContractRef) or contract is None
            else NodeContractRef.model_validate(contract)
        )
        selected_execution = (
            execution
            if isinstance(execution, ExecutionPolicy) or execution is None
            else ExecutionPolicy.model_validate(execution)
        )
        return self._append_node(
            GraphNode(
                id=node_id,
                kind=NodeKind.COMPONENT,
                role=GraphRole(role) if role is not None else None,
                contract=selected_contract,
                lifecycle=NodeLifecycle(lifecycle),
                component=selected_binding,
                primary=primary,
                execution=selected_execution,
                metadata=dict(metadata or {}),
            )
        )

    def add_condition(
        self,
        node_id: str,
        predicate: Predicate | Mapping[str, Any],
        *,
        lifecycle: NodeLifecycle | str = NodeLifecycle.PER_STEP,
    ) -> "AgentGraphBuilder":
        """Add a structured binary condition node.

        Args:
            node_id (str): Stable logical node ID.
            predicate (Predicate | Mapping[str, Any]): Safe field predicate.
            lifecycle (NodeLifecycle | str): Condition lifecycle.

        Raises:
            ValueError: Predicate or node validation fails.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        selected = (
            predicate
            if isinstance(predicate, Predicate)
            else Predicate.model_validate(predicate)
        )
        return self._append_node(
            GraphNode(
                id=node_id,
                kind=NodeKind.CONDITION,
                lifecycle=NodeLifecycle(lifecycle),
                predicate=selected,
            )
        )

    def add_router(
        self,
        node_id: str,
        cases: Iterable[RouterCase | Mapping[str, Any]],
        *,
        default: str,
        lifecycle: NodeLifecycle | str = NodeLifecycle.PER_STEP,
    ) -> "AgentGraphBuilder":
        """Add an ordered first-match Router node.

        Args:
            node_id (str): Stable logical node ID.
            cases (Iterable[RouterCase | Mapping[str, Any]]): Ordered cases.
            default (str): Default output port.
            lifecycle (NodeLifecycle | str): Router lifecycle.

        Raises:
            ValueError: Router declaration is invalid.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        selected_cases = tuple(
            item if isinstance(item, RouterCase) else RouterCase.model_validate(item)
            for item in cases
        )
        return self._append_node(
            GraphNode(
                id=node_id,
                kind=NodeKind.ROUTER,
                lifecycle=NodeLifecycle(lifecycle),
                router=RouterSpec(cases=selected_cases, default=default),
            )
        )

    def add_state(
        self,
        node_id: str,
        state: StateSpec | Mapping[str, Any],
        *,
        lifecycle: NodeLifecycle | str = NodeLifecycle.STATEFUL,
    ) -> "AgentGraphBuilder":
        """Add an explicit typed state read/write node.

        Args:
            node_id (str): Stable logical node ID.
            state (StateSpec | Mapping[str, Any]): State declaration.
            lifecycle (NodeLifecycle | str): State lifecycle.

        Raises:
            ValueError: State or node validation fails.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        selected = (
            state if isinstance(state, StateSpec) else StateSpec.model_validate(state)
        )
        return self._append_node(
            GraphNode(
                id=node_id,
                kind=NodeKind.STATE,
                lifecycle=NodeLifecycle(lifecycle),
                state=selected,
            )
        )

    def add_subgraph(
        self,
        node_id: str,
        subgraph: SubgraphSpec | Mapping[str, Any],
        *,
        lifecycle: NodeLifecycle | str = NodeLifecycle.PER_STEP,
    ) -> "AgentGraphBuilder":
        """Add an inline or content-addressed Subgraph invocation.

        Args:
            node_id (str): Stable logical node ID.
            subgraph (SubgraphSpec | Mapping[str, Any]): Subgraph declaration.
            lifecycle (NodeLifecycle | str): Invocation lifecycle.

        Raises:
            ValueError: Subgraph or node validation fails.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        selected = (
            subgraph
            if isinstance(subgraph, SubgraphSpec)
            else SubgraphSpec.model_validate(subgraph)
        )
        return self._append_node(
            GraphNode(
                id=node_id,
                kind=NodeKind.SUBGRAPH,
                lifecycle=NodeLifecycle(lifecycle),
                subgraph=selected,
            )
        )

    def add_loop(
        self,
        node_id: str,
        loop: LoopSpec | Mapping[str, Any],
        *,
        lifecycle: NodeLifecycle | str = NodeLifecycle.PER_STEP,
    ) -> "AgentGraphBuilder":
        """Add a bounded local Loop node.

        Args:
            node_id (str): Stable logical node ID.
            loop (LoopSpec | Mapping[str, Any]): Loop body and termination policy.
            lifecycle (NodeLifecycle | str): Loop lifecycle.

        Raises:
            ValueError: Loop or node validation fails.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        selected = loop if isinstance(loop, LoopSpec) else LoopSpec.model_validate(loop)
        return self._append_node(
            GraphNode(
                id=node_id,
                kind=NodeKind.LOOP,
                lifecycle=NodeLifecycle(lifecycle),
                loop=selected,
            )
        )

    def connect(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
        *,
        kind: EdgeKind | str = EdgeKind.DATA,
        condition: Predicate | Mapping[str, Any] | None = None,
    ) -> "AgentGraphBuilder":
        """Connect two node ports with a data or control edge.

        Args:
            source_node (str): Source logical node ID.
            source_port (str): Source port ID.
            target_node (str): Target logical node ID.
            target_port (str): Target port ID.
            kind (EdgeKind | str): ``data`` or ``control`` edge kind.
            condition (Predicate | Mapping[str, Any] | None): Optional edge predicate.

        Raises:
            ValueError: A feedback edge is requested or model validation fails.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        selected_kind = EdgeKind(kind)
        if selected_kind is EdgeKind.FEEDBACK:
            raise ValueError("use feedback() to declare bounded feedback edges")
        selected_condition = (
            condition
            if isinstance(condition, Predicate) or condition is None
            else Predicate.model_validate(condition)
        )
        self._edges.append(
            GraphEdge(
                source=PortAddress(node=source_node, port=source_port),
                target=PortAddress(node=target_node, port=target_port),
                kind=selected_kind,
                condition=selected_condition,
            )
        )
        return self

    def control(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str = "control",
    ) -> "AgentGraphBuilder":
        """Connect one explicit control edge.

        Args:
            source_node (str): Source logical node ID.
            source_port (str): Source control output.
            target_node (str): Target logical node ID.
            target_port (str): Target control port.

        Raises:
            ValueError: Edge validation fails.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        return self.connect(
            source_node,
            source_port,
            target_node,
            target_port,
            kind=EdgeKind.CONTROL,
        )

    def feedback(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
        *,
        predicate: Predicate | Mapping[str, Any],
        max_iterations: int,
        on_exhausted: FeedbackExhaustedPolicy | str = FeedbackExhaustedPolicy.FAIL,
    ) -> "AgentGraphBuilder":
        """Connect a bounded cross-interaction feedback edge.

        Args:
            source_node (str): Feedback-producing node ID.
            source_port (str): Feedback-producing output port.
            target_node (str): Reactivated target node ID.
            target_port (str): Target input port.
            predicate (Predicate | Mapping[str, Any]): Feedback activation predicate.
            max_iterations (int): Per-edge feedback bound.
            on_exhausted (FeedbackExhaustedPolicy | str): Exhaustion behavior.

        Raises:
            ValueError: Predicate, feedback policy, or edge validation fails.

        Returns:
            AgentGraphBuilder: This builder for fluent chaining.
        """
        selected = (
            predicate
            if isinstance(predicate, Predicate)
            else Predicate.model_validate(predicate)
        )
        self._edges.append(
            GraphEdge(
                source=PortAddress(node=source_node, port=source_port),
                target=PortAddress(node=target_node, port=target_port),
                kind=EdgeKind.FEEDBACK,
                feedback=FeedbackPolicy(
                    predicate=selected,
                    max_iterations=max_iterations,
                    on_exhausted=FeedbackExhaustedPolicy(on_exhausted),
                ),
            )
        )
        return self

    def build(
        self,
        *,
        validate: bool = True,
        contract_catalog: Any = None,
        graph_catalog: Any = None,
    ) -> AgentGraph:
        """Materialize the immutable contract 1.1 AgentGraph.

        Args:
            validate (bool): Run full graph validation before returning.
            contract_catalog (Any): Optional explicit extension contracts.
            graph_catalog (Any): Optional explicit child-graph catalog.

        Raises:
            ValueError: Graph construction or validation fails.

        Returns:
            AgentGraph: Immutable, side-effect-free graph definition.
        """
        graph = AgentGraph(
            contract_version=self._contract_version,
            nodes=tuple(self._nodes),
            edges=tuple(self._edges),
            policies=self._policies,
            interface=self._interface,
            metadata=self._metadata,
        )
        if validate:
            result = graph.validate_graph(
                contract_catalog=contract_catalog,
                graph_catalog=graph_catalog,
            )
            if not result.is_valid:
                codes = ", ".join(item.code for item in result.errors[:8])
                raise ValueError(f"AgentGraph validation failed: {codes}")
        return graph


def predicate(
    field: str,
    operator: PredicateOperator | str,
    value: Any = None,
) -> Predicate:
    """Create a structured non-executable Predicate for Builder calls.

    Args:
        field (str): Stable dotted field path.
        operator (PredicateOperator | str): Supported comparison operator.
        value (Any): JSON-safe comparison value.

    Raises:
        ValueError: Predicate validation fails.

    Returns:
        Predicate: Validated immutable predicate.
    """
    return Predicate(
        field=field,
        operator=PredicateOperator(operator),
        value=value,
    )


__all__ = ["AgentGraphBuilder", "predicate"]
