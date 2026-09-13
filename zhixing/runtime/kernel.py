"""Paradigm-independent execution kernel for AgentGraph contract 1.1."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from inspect import isclass
from typing import Any, Protocol

from zhixing.components import (
    ActionResult,
    BUILTIN_RUNTIME_TYPES,
    ComponentDefinitionError,
    ComponentSpec,
    DeviceExecutionError,
    DeviceObservation,
    RuntimeContext,
    RuntimeTypeCatalog,
    construct_component,
    get_component_spec,
    safe_device_reference,
)
from zhixing.graph import (
    AgentGraph,
    EdgeKind,
    GraphComponentRef,
    GraphRole,
    LoopExhaustedPolicy,
    NodeKind,
    PortCardinality,
    PortDirection,
    StateOperation,
    StateScope,
)
from zhixing.graph.contracts import (
    BUILTIN_NODE_CONTRACT_CATALOG,
    InvocationAdapterKind,
    NodeContract,
    NodeContractCatalog,
    NodeContractRef,
    SideEffectKind,
    contract_ref_for_role,
)
from zhixing.graph.ports import contract_ports_for_node

from .assemblers import invoke_role
from .engine import evaluate_predicate
from .errors import GraphBindingError, GraphExecutionError
from .models import (
    BoundCandidate,
    BoundComponent,
    ResolvedComponentDefinition,
    StepFrame,
)
from .state import StateStore


class KernelStatus(str, Enum):
    """Normalized outcome of generalized graph execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TERMINATED = "terminated"


@dataclass
class ExecutionBudget:
    """Hierarchical activation budget shared with an optional parent."""

    limit: int
    consumed: int = 0
    parent: "ExecutionBudget | None" = field(default=None, repr=False)

    def consume(self, node_path: str) -> None:
        """Consume one activation from this scope and every parent.

        Args:
            node_path (str): Logical node path used in an error.

        Raises:
            GraphExecutionError: This scope or a parent scope is exhausted.

        Returns:
            None: Counters are incremented in place.
        """
        if self.consumed >= self.limit:
            raise GraphExecutionError(
                "runtime.activation_budget_exhausted",
                f"Activation budget exhausted before {node_path!r}",
                node_id=node_path,
                phase="budget",
            )
        if self.parent is not None:
            self.parent.consume(node_path)
        self.consumed += 1


@dataclass(frozen=True)
class ActivationFrame:
    """Identity and counters for one logical node activation."""

    node_path: str
    activation_id: str
    parent_activation_id: str = ""
    interaction_step: int = 0
    loop_path: str = ""
    loop_iteration: int | None = None


@dataclass(frozen=True)
class KernelResult:
    """Generalized graph outputs and structured execution evidence."""

    run_id: str
    status: KernelStatus
    outputs: Mapping[str, Any]
    events: tuple[Any, ...]
    activation_count: int
    interaction_steps: int
    state: Mapping[str, Any]
    error: str = ""
    error_code: str = ""


class NodeInvocationAdapter(Protocol):
    """Convert validated port values to and from one component invocation."""

    def __call__(
        self,
        component: Any,
        inputs: Mapping[str, Any],
        runtime: RuntimeContext,
        services: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Invoke one component through its typed boundary.

        Args:
            component (Any): Bound component instance.
            inputs (Mapping[str, Any]): Validated logical port values.
            runtime (RuntimeContext): Shared run context.
            services (Mapping[str, Any]): Explicit runtime services.

        Raises:
            Exception: Component and adapter failures cross the node boundary.

        Returns:
            Mapping[str, Any]: Output values keyed by declared port.
        """
        ...


class InvocationAdapterRegistry:
    """Explicit adapter registry keyed by exact contract reference."""

    def __init__(
        self,
        adapters: Mapping[tuple[str, str] | str, NodeInvocationAdapter] | None = None,
    ) -> None:
        """Create a registry without discovering installed packages.

        Args:
            adapters (Mapping[tuple[str, str] | str, NodeInvocationAdapter] | None):
                Explicit contract adapters keyed by ``(id, version)`` or ID.

        Raises:
            None.

        Returns:
            None.
        """
        self._adapters = dict(adapters or {})

    def resolve(self, reference: NodeContractRef) -> NodeInvocationAdapter | None:
        """Resolve an exact adapter, falling back to a contract-ID entry.

        Args:
            reference (NodeContractRef): Exact node contract reference.

        Raises:
            None.

        Returns:
            NodeInvocationAdapter | None: Explicit adapter, if registered.
        """
        return self._adapters.get((reference.id, reference.version)) or self._adapters.get(
            reference.id
        )


@dataclass(frozen=True)
class BoundKernelCandidate:
    """One resolved generalized component candidate."""

    name: str
    instance: Any = field(repr=False)
    spec: ComponentSpec | None = field(default=None, repr=False)


@dataclass(frozen=True)
class BoundNode:
    """One graph node bound to contract, candidates, and child plans."""

    node: Any
    node_path: str
    contract: NodeContract | None = None
    candidates: tuple[BoundKernelCandidate, ...] = ()
    adapter: NodeInvocationAdapter | None = field(default=None, repr=False)
    child: "BoundExecutionPlan | None" = field(default=None, repr=False)
    runtime_types: RuntimeTypeCatalog | None = field(default=None, repr=False)


@dataclass(frozen=True)
class BoundExecutionPlan:
    """Validated graph paired with paradigm-independent runtime bindings."""

    graph: AgentGraph
    nodes: Mapping[str, BoundNode]
    contract_catalog: NodeContractCatalog
    path: str = ""
    shared_run_state: frozenset[str] = frozenset()


def _safe_summary(value: Any) -> dict[str, Any]:
    """Produce a bounded structural summary for kernel events.

    Args:
        value (Any): Runtime value to summarize.

    Raises:
        None.

    Returns:
        dict[str, Any]: Non-sensitive type and size information.
    """
    result = {"type": type(value).__name__}
    if isinstance(value, DeviceObservation):
        result.update(
            {
                "sequence": value.sequence,
                "interaction_step": value.interaction_step,
                "platform": value.platform,
                "device_id": safe_device_reference(value.device_id),
                "screenshot_artifact": value.screenshot_artifact,
                "ui_artifact": value.ui_artifact,
            }
        )
    elif isinstance(value, ActionResult):
        result.update(
            {
                "action_type": value.action.type.value,
                "status": value.status.value,
                "effect_performed": value.effect_performed,
                "effect_kind": value.effect_kind.value,
                "terminal_status": (
                    value.terminal_status.value if value.terminal_status else None
                ),
                "device_id": safe_device_reference(value.device_id),
            }
        )
    elif isinstance(value, Mapping):
        result["keys"] = sorted(str(key) for key in value)[:20]
        structured = {
            str(key): _safe_summary(item)
            for key, item in value.items()
            if isinstance(item, (DeviceObservation, ActionResult))
        }
        if structured:
            result["values"] = structured
    elif isinstance(value, (list, tuple)):
        result["count"] = len(value)
    return result


def _matches_logical_type(
    value: Any,
    data_type: str,
    runtime_types: RuntimeTypeCatalog | None = None,
) -> bool:
    """Check runtime values for built-in logical contract types.

    Args:
        value (Any): Runtime port value.
        data_type (str): Logical data-type identifier.
        runtime_types (RuntimeTypeCatalog | None): Optional strict external bindings.

    Raises:
        ComponentDefinitionError: A strict runtime type binding is missing.

    Returns:
        bool: True for compatible built-in types or caller-owned opaque types.
    """
    selected = runtime_types or BUILTIN_RUNTIME_TYPES
    target = selected.resolve(data_type)
    if target is None:
        if runtime_types is not None and runtime_types.strict:
            raise ComponentDefinitionError(
                "component.runtime_type_unknown",
                f"Logical runtime type {data_type!r} has no binding",
                details={"logical_type": data_type},
            )
        # Structural local components retain the existing opaque-type behavior.
        return True
    return True if target is object else isinstance(value, target)


def _validate_port_value(
    node_path: str,
    port_id: str,
    value: Any,
    data_types: tuple[str, ...],
    *,
    phase: str,
    runtime_types: RuntimeTypeCatalog | None = None,
) -> None:
    """Validate one runtime value against declared logical port types.

    Args:
        node_path (str): Stable logical node path.
        port_id (str): Contract port identifier.
        value (Any): Runtime value.
        data_types (tuple[str, ...]): Accepted logical types.
        phase (str): Input or output validation phase.
        runtime_types (RuntimeTypeCatalog | None): Optional strict external bindings.

    Raises:
        GraphExecutionError: No declared type accepts the value.

    Returns:
        None.
    """
    try:
        accepted = any(
            _matches_logical_type(value, item, runtime_types)
            for item in data_types
        )
    except ComponentDefinitionError as error:
        raise GraphExecutionError(
            "runtime.logical_type_unknown",
            f"Node {node_path!r} uses an unbound logical runtime type",
            node_id=node_path,
            phase=phase,
            details={"port": port_id, "error_code": error.code},
        ) from error
    if not accepted:
        raise GraphExecutionError(
            f"runtime.{phase}_type",
            f"Node {node_path!r} port {port_id!r} received {type(value).__name__}",
            node_id=node_path,
            phase=phase,
            details={"port": port_id, "accepted": list(data_types)},
        )


def _default_typed_adapter(
    contract: NodeContract,
) -> NodeInvocationAdapter:
    """Create a conservative adapter for explicit typed-invoke contracts.

    Args:
        contract (NodeContract): Contract whose input/output ports define mapping.

    Raises:
        None.

    Returns:
        NodeInvocationAdapter: Adapter passing one input directly or many as mapping.
    """
    input_ports = tuple(
        port
        for port in contract.ports
        if port.direction is PortDirection.INPUT and port.id != "control"
    )
    output_ports = tuple(
        port for port in contract.ports if port.direction is PortDirection.OUTPUT
    )

    def invoke(
        component: Any,
        inputs: Mapping[str, Any],
        runtime: RuntimeContext,
        services: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Invoke and normalize one explicitly bound component.

        Args:
            component (Any): Component exposing ``invoke``.
            inputs (Mapping[str, Any]): Logical input ports.
            runtime (RuntimeContext): Shared run context.
            services (Mapping[str, Any]): Explicit services, unused by this adapter.

        Raises:
            GraphExecutionError: The component or output shape is incompatible.

        Returns:
            Mapping[str, Any]: Declared output-port mapping.
        """
        del services
        payload: Any
        if len(input_ports) == 1:
            payload = inputs.get(input_ports[0].id)
        else:
            payload = {port.id: inputs.get(port.id) for port in input_ports}
        method = getattr(component, "invoke", None)
        if not callable(method):
            raise GraphExecutionError(
                "runtime.component_invoke_missing",
                "Typed component does not expose invoke(input, runtime)",
                phase="binding",
            )
        output = method(payload, runtime)
        if isinstance(output, Mapping) and set(output).issubset(
            {port.id for port in output_ports}
        ):
            return dict(output)
        if len(output_ports) != 1:
            raise GraphExecutionError(
                "runtime.output_mapping_required",
                "Multi-output contract requires a mapping result",
                phase="normalization",
            )
        return {output_ports[0].id: output}

    return invoke


def _service_adapter(contract: NodeContract) -> NodeInvocationAdapter:
    """Create an adapter that calls an explicitly supplied runtime service.

    Args:
        contract (NodeContract): Runtime-service contract.

    Raises:
        None.

    Returns:
        NodeInvocationAdapter: Explicit service invocation adapter.
    """
    output_ports = tuple(
        port for port in contract.ports if port.direction is PortDirection.OUTPUT
    )

    def invoke(
        component: Any,
        inputs: Mapping[str, Any],
        runtime: RuntimeContext,
        services: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Invoke one named service without role-based Kernel branching.

        Args:
            component (Any): Binding marker; the service may replace it.
            inputs (Mapping[str, Any]): Logical service request values.
            runtime (RuntimeContext): Shared run context.
            services (Mapping[str, Any]): Explicit services keyed by contract ID.

        Raises:
            GraphExecutionError: No callable service is provided.

        Returns:
            Mapping[str, Any]: Normalized declared service outputs.
        """
        service = services.get(contract.ref.id, component)
        method = getattr(service, "invoke", None)
        if not callable(method):
            method = service if callable(service) else None
        if method is None:
            raise GraphExecutionError(
                "runtime.service_missing",
                f"Runtime service {contract.ref.id!r} is unavailable",
                phase="service",
            )
        try:
            output = method(inputs, runtime)
        except TypeError:
            output = method(inputs)
        if isinstance(output, Mapping):
            return dict(output)
        if len(output_ports) != 1:
            raise GraphExecutionError(
                "runtime.service_output_mapping",
                "Runtime service must return a mapping for multiple outputs",
                phase="service",
            )
        return {output_ports[0].id: output}

    return invoke


def _core_role_adapter(
    node,
    candidates: tuple[BoundKernelCandidate, ...],
) -> NodeInvocationAdapter:
    """Wrap current role assemblers behind a contract adapter.

    Args:
        node (GraphNode): Legacy-role compatible graph node.
        candidates (tuple[BoundKernelCandidate, ...]): Resolved adapted candidates.

    Raises:
        None.

    Returns:
        NodeInvocationAdapter: Adapter reusing current typed DTO assembly.
    """
    bound = BoundComponent(
        node=node,
        candidates=tuple(
            BoundCandidate(reference=reference, instance=candidate.instance)
            for reference, candidate in zip(node.component.candidates, candidates)
        ),
    )

    def invoke(
        component: Any,
        inputs: Mapping[str, Any],
        runtime: RuntimeContext,
        services: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Assemble and invoke a core role using the existing typed adapter.

        Args:
            component (Any): Selected component marker, ignored because the
                existing bound candidate set owns sticky fallback.
            inputs (Mapping[str, Any]): Logical input-port values.
            runtime (RuntimeContext): Shared run context.
            services (Mapping[str, Any]): Explicit services, unused here.

        Raises:
            GraphExecutionError: Typed assembly or invocation fails.

        Returns:
            Mapping[str, Any]: Single normalized role output.
        """
        del component, services
        frame = StepFrame(step=runtime.step)
        frame.pre_observation = inputs.get("before") or inputs.get("observation")
        frame.post_observation = inputs.get("after")
        frame.action_result = inputs.get("action_result")
        invocation = invoke_role(bound, inputs, frame, runtime)
        output_port = {
            "perception": "perception",
            "planner": "plan",
            "reasoning": "action",
            "memory": "context",
            "action_executor": "result",
            "verifier": "result",
        }[node.role.value]
        return {output_port: invocation.output}

    return invoke


def _resolve_component_value(
    components: Any,
    node_path: str,
    reference: GraphComponentRef,
    role: GraphRole | None,
    contract: NodeContract,
) -> BoundKernelCandidate:
    """Resolve one candidate from an explicit caller mapping.

    Args:
        components (Any): Explicit mapping or resolver with ``resolve``.
        node_path (str): Stable hierarchical node path.
        reference (GraphComponentRef): Full declarative component reference.
        role (GraphRole | None): Optional core role.
        contract (NodeContract): Exact node invocation contract.

    Raises:
        GraphBindingError: No explicit component entry exists.

    Returns:
        BoundKernelCandidate: Resolved instance plus optional formal definition.
    """
    resolver = getattr(components, "resolve", None)
    if callable(resolver) and not isinstance(components, Mapping):
        target = resolver(reference, role)
    elif not isinstance(components, Mapping):
        raise GraphBindingError(
            "runtime.component_resolver_invalid",
            "Component source must be a mapping or expose resolve(reference, role)",
            node_id=node_path,
            phase="binding",
        )
    else:
        target = components.get(reference.name, components.get(node_path))
        if target is None:
            raise GraphBindingError(
                "runtime.component_unresolved",
                f"No explicit component is available for node {node_path!r}",
                node_id=node_path,
                phase="binding",
            )
    resolved_dependencies: Mapping[str, Any] = {}
    if isinstance(target, ResolvedComponentDefinition):
        specification = target.specification
        resolved_dependencies = target.dependencies
    else:
        specification = get_component_spec(target)
    if specification is not None:
        try:
            instance = construct_component(
                specification,
                reference.params,
                dependencies=resolved_dependencies,
                expected_contract=contract,
                expected_role=role,
            )
        except ComponentDefinitionError as error:
            raise GraphBindingError(
                error.code,
                str(error),
                node_id=node_path,
                phase="component_preflight",
                details={
                    "component": specification.identifier,
                    **dict(error.details),
                },
            ) from error
        return BoundKernelCandidate(
            name=reference.name,
            instance=instance,
            spec=specification,
        )
    if isclass(target):
        instance = target(**reference.params)
    elif callable(target) and not callable(getattr(target, "invoke", None)):
        instance = target(**reference.params)
    else:
        instance = target
    return BoundKernelCandidate(name=reference.name, instance=instance)


def bind_execution_plan(
    graph: AgentGraph,
    components: Any,
    *,
    contract_catalog: NodeContractCatalog | None = None,
    graph_catalog=None,
    adapters: InvocationAdapterRegistry | None = None,
    path: str = "",
    shared_run_state: frozenset[str] = frozenset(),
) -> BoundExecutionPlan:
    """Validate and recursively bind a contract 1.1 graph.

    Args:
        graph (AgentGraph): Generalized AgentGraph.
        components (Any): Explicit component mapping or resolver.
        contract_catalog (NodeContractCatalog | None): Explicit extension contracts.
        graph_catalog (GraphCatalog | None): Explicit content-addressed child graphs.
        adapters (InvocationAdapterRegistry | None): Explicit extension adapters.
        path (str): Stable parent logical path used for recursion.
        shared_run_state (frozenset[str]): Run-state keys shared with the parent.

    Raises:
        GraphBindingError: Validation, contract, component, or child binding fails.

    Returns:
        BoundExecutionPlan: Recursively bound execution plan.
    """
    catalog = BUILTIN_NODE_CONTRACT_CATALOG
    if contract_catalog is not None:
        try:
            catalog = catalog.merge(contract_catalog)
        except ValueError as error:
            raise GraphBindingError(
                "runtime.contract_catalog_conflict",
                str(error),
                phase="binding",
            ) from error
    validation = graph.validate_graph(
        contract_catalog=contract_catalog,
        graph_catalog=graph_catalog,
    )
    if not validation.is_valid:
        raise GraphBindingError(
            "runtime.graph_invalid",
            "AgentGraph validation failed before generalized binding",
            phase="binding",
            details={"diagnostics": [item.code for item in validation.errors]},
        )
    registry = adapters or InvocationAdapterRegistry()
    bound_nodes: dict[str, BoundNode] = {}
    for node in graph.nodes:
        node_path = f"{path}/{node.id}".strip("/")
        contract = None
        candidates: tuple[BoundKernelCandidate, ...] = ()
        adapter = None
        child = None
        if node.kind is NodeKind.COMPONENT:
            reference = node.contract or (
                contract_ref_for_role(node.role) if node.role is not None else None
            )
            contract = catalog.resolve(reference) if reference is not None else None
            if contract is None or node.component is None:
                raise GraphBindingError(
                    "runtime.contract_unresolved",
                    f"Node contract is unavailable for {node_path!r}",
                    node_id=node_path,
                    phase="binding",
                )
            resolved = tuple(
                _resolve_component_value(
                    components,
                    node_path,
                    candidate,
                    node.role,
                    contract,
                )
                for candidate in node.component.candidates
            )
            candidates = resolved
            node_runtime_types: RuntimeTypeCatalog | None = None
            try:
                for candidate in candidates:
                    if candidate.spec is None:
                        continue
                    candidate_types = BUILTIN_RUNTIME_TYPES.merge(
                        RuntimeTypeCatalog(
                            candidate.spec.runtime_types,
                            strict=True,
                        )
                    )
                    candidate_types.validate_contract(contract)
                    node_runtime_types = (
                        candidate_types
                        if node_runtime_types is None
                        else node_runtime_types.merge(candidate_types)
                    )
            except ComponentDefinitionError as error:
                raise GraphBindingError(
                    error.code,
                    str(error),
                    node_id=node_path,
                    phase="component_preflight",
                    details=dict(error.details),
                ) from error
            explicit_adapter = registry.resolve(contract.ref)
            adapter = explicit_adapter
            if adapter is None and contract.adapter is InvocationAdapterKind.CORE_ROLE:
                from zhixing.components import ComponentRole, adapt_component

                candidates = tuple(
                    BoundKernelCandidate(
                        name=candidate.name,
                        instance=adapt_component(ComponentRole(node.role.value), candidate.instance),
                        spec=candidate.spec,
                    )
                    for candidate in candidates
                )
                adapter = _core_role_adapter(node, candidates)
            elif adapter is None and contract.adapter is InvocationAdapterKind.RUNTIME_SERVICE:
                adapter = _service_adapter(contract)
            elif adapter is None:
                adapter = _default_typed_adapter(contract)
            if (
                explicit_adapter is None
                and contract.adapter is InvocationAdapterKind.TYPED_INVOKE
                and any(
                    not callable(getattr(candidate.instance, "invoke", None))
                    for candidate in candidates
                )
            ):
                raise GraphBindingError(
                    "runtime.component_protocol_incompatible",
                    f"Node {node_path!r} requires invoke(input, runtime)",
                    node_id=node_path,
                    phase="binding",
                )
        elif node.kind in {NodeKind.SUBGRAPH, NodeKind.LOOP}:
            specification = node.subgraph if node.kind is NodeKind.SUBGRAPH else node.loop.body
            child_graph = specification.graph
            if child_graph is None and graph_catalog is not None:
                child_graph = graph_catalog.resolve(specification.reference)
            if child_graph is None:
                raise GraphBindingError(
                    "runtime.subgraph_unresolved",
                    f"Subgraph for node {node_path!r} is unavailable",
                    node_id=node_path,
                    phase="binding",
                )
            child = bind_execution_plan(
                child_graph,
                components,
                contract_catalog=contract_catalog,
                graph_catalog=graph_catalog,
                adapters=registry,
                path=node_path,
                shared_run_state=frozenset(specification.shared_state),
            )
        bound_nodes[node.id] = BoundNode(
            node=node,
            node_path=node_path,
            contract=contract,
            candidates=candidates,
            adapter=adapter,
            child=child,
            runtime_types=(
                node_runtime_types
                if node.kind is NodeKind.COMPONENT
                else None
            ),
        )
    return BoundExecutionPlan(
        graph=graph,
        nodes=bound_nodes,
        contract_catalog=catalog,
        path=path,
        shared_run_state=shared_run_state,
    )


@dataclass
class _KernelSession:
    """Mutable execution state shared across hierarchical plans."""

    runtime: RuntimeContext
    services: Mapping[str, Any]
    state: StateStore
    root_budget: ExecutionBudget
    events: list[Any]
    interaction_step: int = 0
    activation_sequence: int = 0

    def next_activation(
        self,
        node_path: str,
        *,
        parent_activation_id: str = "",
        loop_path: str = "",
        loop_iteration: int | None = None,
    ) -> ActivationFrame:
        """Allocate one run-local activation identity.

        Args:
            node_path (str): Stable logical node path.
            parent_activation_id (str): Parent activation identity.
            loop_path (str): Stable loop path.
            loop_iteration (int | None): Local iteration number.

        Raises:
            None.

        Returns:
            ActivationFrame: New activation identity and counters.
        """
        self.activation_sequence += 1
        return ActivationFrame(
            node_path=node_path,
            activation_id=f"a{self.activation_sequence}-{uuid.uuid4().hex[:8]}",
            parent_activation_id=parent_activation_id,
            interaction_step=self.interaction_step,
            loop_path=loop_path,
            loop_iteration=loop_iteration,
        )


class _TerminateGraph(Exception):
    """Internal structured termination signal for exhausted local loops."""


class GraphExecutionKernel:
    """Execute validated plans using only readiness, contracts, and graph primitives."""

    def run(
        self,
        plan: BoundExecutionPlan,
        inputs: Mapping[str, Any],
        *,
        runtime: RuntimeContext | None = None,
        services: Mapping[str, Any] | None = None,
    ) -> KernelResult:
        """Execute one bound generalized graph.

        Args:
            plan (BoundExecutionPlan): Recursively bound plan.
            inputs (Mapping[str, Any]): Graph input-port values.
            runtime (RuntimeContext | None): Optional caller-owned context.
            services (Mapping[str, Any] | None): Explicit runtime services.

        Raises:
            None: Failures are normalized into KernelResult.

        Returns:
            KernelResult: Outputs, state snapshot, counters, events, and status.
        """
        context = runtime or RuntimeContext(max_steps=plan.graph.policies.max_steps)
        captured: list[Any] = []
        previous_sink = context.event_sink

        def collect(event: Any) -> None:
            """Collect an event while preserving the caller's sink.

            Args:
                event (Any): Emitted RunEvent.

            Raises:
                Exception: Caller sink exceptions are propagated.

            Returns:
                None: Event is appended and forwarded.
            """
            captured.append(event)
            if previous_sink is not None:
                previous_sink(event)

        context.event_sink = collect
        session = _KernelSession(
            runtime=context,
            services=dict(services or {}),
            state=StateStore(),
            root_budget=ExecutionBudget(
                min(
                    plan.graph.policies.max_activations,
                    context.max_activations
                    if context.max_activations is not None
                    else plan.graph.policies.max_activations,
                )
            ),
            events=captured,
        )
        outputs: Mapping[str, Any] = {}
        status = KernelStatus.SUCCESS
        error = ""
        error_code = ""
        try:
            outputs = self._execute_plan(
                plan,
                dict(inputs),
                session,
                session.root_budget,
            )
        except _TerminateGraph:
            status = KernelStatus.TERMINATED
        except GraphExecutionError as failure:
            error = failure.info.message
            error_code = failure.info.code
            if failure.info.code == "runtime.cancelled":
                status = KernelStatus.CANCELLED
            elif failure.info.code in {
                    "runtime.activation_budget_exhausted",
                    "runtime.interaction_step_exhausted",
            }:
                status = KernelStatus.BUDGET_EXHAUSTED
            else:
                status = KernelStatus.FAILURE
        except Exception as failure:
            error = type(failure).__name__
            error_code = "runtime.kernel_unhandled"
            status = KernelStatus.FAILURE
        finally:
            context.event_sink = previous_sink
        return KernelResult(
            run_id=context.run_id,
            status=status,
            outputs=dict(outputs),
            events=tuple(captured),
            activation_count=session.root_budget.consumed,
            interaction_steps=session.interaction_step,
            state=session.state.snapshot(),
            error=error,
            error_code=error_code,
        )

    def run_compatibility(self, execute: Callable[[], Any]) -> Any:
        """Execute one compatibility plan through the shared Kernel boundary.

        Args:
            execute (Callable[[], Any]): Fully bound legacy execution-plan callback.

        Raises:
            Exception: Preserves compatibility callback behavior.

        Returns:
            Any: Existing compatibility result without conversion.
        """
        return execute()

    def _cancelled(self, runtime: RuntimeContext) -> bool:
        """Check cooperative cancellation at an activation boundary.

        Args:
            runtime (RuntimeContext): Shared run context.

        Raises:
            None.

        Returns:
            bool: True when cancellation has been requested.
        """
        signal = runtime.cancellation
        if signal is None:
            return False
        method = getattr(signal, "is_cancelled", None)
        return bool(method()) if callable(method) else bool(signal)

    def _scope_owner(
        self,
        scope: StateScope,
        plan: BoundExecutionPlan,
        frame: ActivationFrame,
        key: str = "",
    ) -> str:
        """Resolve a stable state owner for one declared scope.

        Args:
            scope (StateScope): State lifetime.
            plan (BoundExecutionPlan): Current hierarchical plan.
            frame (ActivationFrame): Current activation identity.
            key (str): State key used to evaluate explicit sharing.

        Raises:
            None.

        Returns:
            str: Stable owner path.
        """
        if scope is StateScope.RUN:
            if not plan.path or key in plan.shared_run_state:
                return "/"
            return f"run:{plan.path}"
        if scope is StateScope.INTERACTION:
            return f"interaction:{frame.interaction_step}"
        if scope is StateScope.LOOP:
            return frame.loop_path or plan.path or "/"
        return plan.path or "/"

    def _emit(
        self,
        session: _KernelSession,
        frame: ActivationFrame,
        *,
        kind: str,
        role: str,
        payload: Mapping[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Emit a hierarchical node event.

        Args:
            session (_KernelSession): Shared execution session.
            frame (ActivationFrame): Node activation identity.
            kind (str): Event kind.
            role (str): Contract or built-in role marker.
            payload (Mapping[str, Any] | None): Safe event payload.
            duration_ms (float | None): Completed activation duration.

        Raises:
            Exception: Caller event sink failures propagate.

        Returns:
            None: Event is emitted through RuntimeContext.
        """
        session.runtime.emit(
            phase="graph_kernel",
            role=role,
            component=frame.node_path,
            kind=kind,
            node_id=frame.node_path.rsplit("/", 1)[-1],
            node_path=frame.node_path,
            activation_id=frame.activation_id,
            parent_activation_id=frame.parent_activation_id,
            loop_path=frame.loop_path,
            loop_iteration=frame.loop_iteration,
            interaction_step=frame.interaction_step,
            duration_ms=duration_ms,
            payload=payload,
        )

    def _node_inputs(
        self,
        plan: BoundExecutionPlan,
        node_id: str,
        delivered: Mapping[tuple[str, str], Any],
        contract_catalog: NodeContractCatalog,
    ) -> dict[str, Any]:
        """Collect delivered values for one node according to cardinality.

        Args:
            plan (BoundExecutionPlan): Current plan.
            node_id (str): Target node ID.
            delivered (Mapping[tuple[str, str], Any]): Delivered port values.
            contract_catalog (NodeContractCatalog): Resolved contract catalog.

        Raises:
            None.

        Returns:
            dict[str, Any]: Input values keyed by target port.
        """
        node = plan.nodes[node_id].node
        values: dict[str, Any] = {}
        for port in contract_ports_for_node(node, contract_catalog):
            if port.direction is not PortDirection.INPUT:
                continue
            value = delivered.get((node_id, port.id))
            if value is not None:
                values[port.id] = value
        return values

    def _ready_or_skipped(
        self,
        plan: BoundExecutionPlan,
        node_id: str,
        delivered: Mapping[tuple[str, str], Any],
        completed: set[str],
        contract_catalog: NodeContractCatalog,
    ) -> tuple[bool, bool]:
        """Determine whether one node is ready or unreachable by control.

        Args:
            plan (BoundExecutionPlan): Current plan.
            node_id (str): Candidate node ID.
            delivered (Mapping[tuple[str, str], Any]): Delivered target values.
            completed (set[str]): Executed or skipped source nodes.
            contract_catalog (NodeContractCatalog): Resolved contract catalog.

        Raises:
            None.

        Returns:
            tuple[bool, bool]: ``(ready, skipped)``.
        """
        node = plan.nodes[node_id].node
        if node.kind is NodeKind.INPUT:
            return True, False
        inbound = [edge for edge in plan.graph.edges if edge.target.node == node_id]
        control = [edge for edge in inbound if edge.kind is EdgeKind.CONTROL]
        if control:
            has_control = any((node_id, edge.target.port) in delivered for edge in control)
            if not has_control:
                return False, all(edge.source.node in completed for edge in control)
        ports = contract_ports_for_node(node, contract_catalog)
        for port in ports:
            if port.direction is not PortDirection.INPUT or not port.required:
                continue
            if (node_id, port.id) in delivered:
                continue
            sources = [edge.source.node for edge in inbound if edge.target.port == port.id]
            if sources and all(source in completed for source in sources):
                return False, True
            return False, False
        # Optional inputs wait for their upstream sources so scheduling is deterministic.
        pending_sources = [
            edge.source.node
            for edge in inbound
            if edge.kind not in {EdgeKind.CONTROL, EdgeKind.FEEDBACK}
            and (node_id, edge.target.port) not in delivered
            and edge.source.node not in completed
        ]
        return (not pending_sources), False

    def _propagate(
        self,
        plan: BoundExecutionPlan,
        source_node: str,
        outputs: Mapping[str, Any],
        delivered: dict[tuple[str, str], Any],
        contract_catalog: NodeContractCatalog,
        feedback_counts: dict[int, int],
    ) -> tuple[list[tuple[int, str]], str | None]:
        """Propagate produced data/control values over eligible edges.

        Args:
            plan (BoundExecutionPlan): Current plan.
            source_node (str): Producing node ID.
            outputs (Mapping[str, Any]): Produced port values.
            delivered (dict[tuple[str, str], Any]): Mutable target value store.
            contract_catalog (NodeContractCatalog): Resolved contract catalog.
            feedback_counts (dict[int, int]): Trigger counts by feedback edge.

        Raises:
            GraphExecutionError: A multiple value targets a single-cardinality port.

        Returns:
            tuple[list[tuple[int, str]], str | None]: Triggered edge/target pairs
            and an optional exhausted policy.
        """
        feedback_targets: list[tuple[int, str]] = []
        exhausted: str | None = None
        for edge_index, edge in enumerate(plan.graph.edges):
            if edge.source.node != source_node or edge.source.port not in outputs:
                continue
            value = outputs[edge.source.port]
            if edge.condition is not None and not evaluate_predicate(edge.condition, value):
                continue
            if edge.kind is EdgeKind.FEEDBACK:
                if edge.feedback is None or not evaluate_predicate(
                    edge.feedback.predicate,
                    value,
                ):
                    continue
                count = feedback_counts.get(edge_index, 0)
                if count >= edge.feedback.max_iterations:
                    exhausted = edge.feedback.on_exhausted.value
                    continue
                feedback_counts[edge_index] = count + 1
                feedback_targets.append((edge_index, edge.target.node))
            target_ports = {
                port.id: port
                for port in contract_ports_for_node(
                    plan.nodes[edge.target.node].node,
                    contract_catalog,
                )
            }
            port = target_ports.get(edge.target.port)
            address = (edge.target.node, edge.target.port)
            if port is not None and port.cardinality is PortCardinality.MULTIPLE:
                if edge.kind is EdgeKind.FEEDBACK:
                    # A feedback activation carries only the newest value.
                    # Earlier values already live inside the stateful component;
                    # retaining the accumulated delivery list would replay the
                    # whole history and make each interaction grow quadratically.
                    delivered[address] = [value]
                    continue
                current = delivered.setdefault(address, [])
                if not isinstance(current, list):
                    raise GraphExecutionError(
                        "runtime.port_cardinality",
                        "Multiple-cardinality port contains a scalar",
                        node_id=edge.target.node,
                        phase="propagation",
                    )
                current.append(value)
            else:
                delivered[address] = value
        return feedback_targets, exhausted

    def _feedback_descendants(
        self,
        plan: BoundExecutionPlan,
        target: str,
    ) -> set[str]:
        """Find nodes reactivated by one cross-interaction feedback target.

        Args:
            plan (BoundExecutionPlan): Current plan.
            target (str): Feedback target node ID.

        Raises:
            None.

        Returns:
            set[str]: Target and ordinary-edge descendants.
        """
        adjacency: dict[str, set[str]] = {}
        for edge in plan.graph.edges:
            if edge.kind is EdgeKind.FEEDBACK:
                continue
            adjacency.setdefault(edge.source.node, set()).add(edge.target.node)
        affected = {target}
        queue = [target]
        while queue:
            current = queue.pop(0)
            for child in sorted(adjacency.get(current, ())):
                if child not in affected:
                    affected.add(child)
                    queue.append(child)
        return affected

    def _invoke_component(
        self,
        bound: BoundNode,
        inputs: Mapping[str, Any],
        session: _KernelSession,
        frame: ActivationFrame,
    ) -> Mapping[str, Any]:
        """Invoke ordered candidates with side-effect-aware fallback.

        Args:
            bound (BoundNode): Bound generalized component node.
            inputs (Mapping[str, Any]): Logical input values.
            session (_KernelSession): Shared execution session.
            frame (ActivationFrame): Current activation identity.

        Raises:
            GraphExecutionError: Every allowed candidate fails.

        Returns:
            Mapping[str, Any]: Normalized component outputs.
        """
        if bound.adapter is None or bound.contract is None or not bound.candidates:
            raise GraphExecutionError(
                "runtime.node_unbound",
                f"Component node {bound.node_path!r} is not bound",
                node_id=bound.node_path,
                phase="binding",
            )
        input_ports = {
            port.id: port
            for port in bound.contract.ports
            if port.direction is PortDirection.INPUT
        }
        for port_id, value in inputs.items():
            port = input_ports.get(port_id)
            if port is not None and port_id != "control":
                values = (
                    value
                    if port.cardinality is PortCardinality.MULTIPLE
                    and isinstance(value, list)
                    else [value]
                )
                for item in values:
                    _validate_port_value(
                        bound.node_path,
                        port_id,
                        item,
                        port.data_types,
                        phase="input",
                        runtime_types=bound.runtime_types,
                    )
        failures: list[str] = []
        for candidate_index, candidate in enumerate(bound.candidates):
            component_identity = (
                candidate.spec.identifier
                if candidate.spec is not None
                else candidate.name
            )
            attempt_started = time.perf_counter()
            session.runtime.capture_debug(
                node_path=bound.node_path,
                activation_id=frame.activation_id,
                role=bound.contract.ref.id,
                component=component_identity,
                stage="start",
                candidate_index=candidate_index,
                interaction_step=frame.interaction_step,
                inputs=inputs,
            )
            try:
                outputs = dict(
                    bound.adapter(
                        candidate.instance,
                        inputs,
                        session.runtime,
                        session.services,
                    )
                )
                output_ports = {
                    port.id: port
                    for port in bound.contract.ports
                    if port.direction is PortDirection.OUTPUT
                }
                unknown = sorted(set(outputs) - set(output_ports))
                if unknown:
                    raise GraphExecutionError(
                        "runtime.output_port_unknown",
                        f"Node {bound.node_path!r} returned undeclared ports",
                        node_id=bound.node_path,
                        phase="output",
                        details={"ports": unknown},
                    )
                for port_id, value in outputs.items():
                    _validate_port_value(
                        bound.node_path,
                        port_id,
                        value,
                        output_ports[port_id].data_types,
                        phase="output",
                        runtime_types=bound.runtime_types,
                    )
            except DeviceExecutionError as failure:
                session.runtime.capture_debug(
                    node_path=bound.node_path,
                    activation_id=frame.activation_id,
                    role=bound.contract.ref.id,
                    component=component_identity,
                    stage="fail",
                    candidate_index=candidate_index,
                    interaction_step=frame.interaction_step,
                    inputs=inputs,
                    duration_ms=(time.perf_counter() - attempt_started) * 1000,
                    error_type=type(failure).__name__,
                )
                raise GraphExecutionError(
                    "runtime.device_failure",
                    str(failure),
                    node_id=bound.node_path,
                    phase="device",
                    details={"operation": failure.operation},
                ) from failure
            except GraphExecutionError as failure:
                session.runtime.capture_debug(
                    node_path=bound.node_path,
                    activation_id=frame.activation_id,
                    role=bound.contract.ref.id,
                    component=component_identity,
                    stage="fail",
                    candidate_index=candidate_index,
                    interaction_step=frame.interaction_step,
                    inputs=inputs,
                    duration_ms=(time.perf_counter() - attempt_started) * 1000,
                    error_type=type(failure).__name__,
                )
                if candidate.spec is not None and failure.info.code in {
                    "runtime.input_type",
                    "runtime.output_type",
                    "runtime.output_port_unknown",
                    "runtime.output_mapping_required",
                    "runtime.logical_type_unknown",
                }:
                    raise GraphExecutionError(
                        failure.info.code,
                        str(failure),
                        node_id=bound.node_path,
                        phase=failure.info.phase,
                        details={
                            "component": candidate.spec.identifier,
                            "contract": (
                                f"{bound.contract.ref.id}@"
                                f"{bound.contract.ref.version}"
                            ),
                            **dict(failure.info.details),
                        },
                    ) from failure
                failures.append(type(failure).__name__)
                if (
                    bound.contract.side_effect is not SideEffectKind.NONE
                    and not bound.contract.idempotent
                ):
                    break
                if candidate_index + 1 >= len(bound.candidates):
                    break
            except Exception as failure:
                session.runtime.capture_debug(
                    node_path=bound.node_path,
                    activation_id=frame.activation_id,
                    role=bound.contract.ref.id,
                    component=component_identity,
                    stage="fail",
                    candidate_index=candidate_index,
                    interaction_step=frame.interaction_step,
                    inputs=inputs,
                    duration_ms=(time.perf_counter() - attempt_started) * 1000,
                    error_type=type(failure).__name__,
                )
                failures.append(type(failure).__name__)
                if (
                    bound.contract.side_effect is not SideEffectKind.NONE
                    and not bound.contract.idempotent
                ):
                    break
                if candidate_index + 1 >= len(bound.candidates):
                    break
            else:
                session.runtime.capture_debug(
                    node_path=bound.node_path,
                    activation_id=frame.activation_id,
                    role=bound.contract.ref.id,
                    component=component_identity,
                    stage="complete",
                    candidate_index=candidate_index,
                    interaction_step=frame.interaction_step,
                    inputs=inputs,
                    outputs=outputs,
                    duration_ms=(time.perf_counter() - attempt_started) * 1000,
                )
                return outputs
        raise GraphExecutionError(
            "runtime.component_candidates_exhausted",
            f"All candidates failed for node {bound.node_path!r}",
            node_id=bound.node_path,
            phase="invocation",
            details={"error_types": failures},
        )

    def _execute_node(
        self,
        plan: BoundExecutionPlan,
        bound: BoundNode,
        inputs: Mapping[str, Any],
        graph_inputs: Mapping[str, Any],
        session: _KernelSession,
        budget: ExecutionBudget,
        frame: ActivationFrame,
    ) -> Mapping[str, Any]:
        """Execute one component or built-in graph primitive.

        Args:
            plan (BoundExecutionPlan): Current plan.
            bound (BoundNode): Node binding.
            inputs (Mapping[str, Any]): Delivered node inputs.
            graph_inputs (Mapping[str, Any]): Current graph boundary inputs.
            session (_KernelSession): Shared execution session.
            budget (ExecutionBudget): Current scope budget.
            frame (ActivationFrame): Activation identity.

        Raises:
            GraphExecutionError: Primitive execution fails.
            _TerminateGraph: Loop exhaustion requests graph termination.

        Returns:
            Mapping[str, Any]: Produced output ports.
        """
        node = bound.node
        if node.kind is NodeKind.INPUT:
            return dict(graph_inputs)
        if node.kind is NodeKind.OUTPUT:
            normalized = dict(inputs)
            result = normalized.get("result")
            if isinstance(result, list) and len(result) == 1:
                normalized["result"] = result[0]
            return normalized
        if node.kind is NodeKind.COMPONENT:
            output = self._invoke_component(bound, inputs, session, frame)
            if bound.contract.side_effect is SideEffectKind.DEVICE_ACTION:
                # Legacy generic action contracts retain their old counter
                # behavior. Typed executors must confirm a real device effect.
                legacy_action = bound.contract.ref.id == "zhixing.service.action"
                performed = any(
                    isinstance(value, ActionResult) and value.effect_performed
                    for value in output.values()
                )
                if legacy_action or performed:
                    session.interaction_step += 1
                    session.runtime.step = session.interaction_step
                    session.runtime.state.step = session.interaction_step
                    session.state.clear(
                        StateScope.INTERACTION,
                        f"interaction:{frame.interaction_step}",
                    )
                    if session.interaction_step >= session.runtime.max_steps:
                        raise GraphExecutionError(
                            "runtime.interaction_step_exhausted",
                            "Mobile Agent reached the configured interaction step limit",
                            node_id=bound.node_path,
                            phase="budget",
                            details={"max_steps": session.runtime.max_steps},
                        )
            return output
        if node.kind is NodeKind.CONDITION:
            selected = evaluate_predicate(node.predicate, inputs["value"])
            return {"true" if selected else "false": True}
        if node.kind is NodeKind.ROUTER:
            value = inputs["value"]
            for case in node.router.cases:
                if evaluate_predicate(case.predicate, value):
                    self._emit(
                        session,
                        frame,
                        kind="router_selected",
                        role="router",
                        payload={"branch": case.id},
                    )
                    return {case.id: True}
            self._emit(
                session,
                frame,
                kind="router_selected",
                role="router",
                payload={"branch": node.router.default},
            )
            return {node.router.default: True}
        if node.kind is NodeKind.STATE:
            owner = self._scope_owner(
                node.state.scope,
                plan,
                frame,
                key=node.state.key,
            )
            if node.state.operation is StateOperation.READ:
                value = session.state.read(
                    node.state.scope,
                    owner,
                    node.state.key,
                    node.state.data_type,
                    node.state.initial,
                )
            else:
                value = session.state.write(
                    node.state.scope,
                    owner,
                    node.state.key,
                    node.state.data_type,
                    inputs["write"],
                    node.state.merge,
                )
            self._emit(
                session,
                frame,
                kind="state_transition",
                role="state",
                payload={
                    "key": node.state.key,
                    "scope": node.state.scope.value,
                    "data_type": node.state.data_type,
                    "value": _safe_summary(value),
                },
            )
            return {"value": value}
        if node.kind is NodeKind.SUBGRAPH:
            child_inputs = {
                child_port: inputs[parent_port]
                for parent_port, child_port in node.subgraph.inputs.items()
                if parent_port in inputs
            }
            child_budget = ExecutionBudget(node.subgraph.max_activations, parent=budget)
            try:
                child_outputs = self._execute_plan(
                    bound.child,
                    child_inputs,
                    session,
                    child_budget,
                    parent_activation_id=frame.activation_id,
                )
            except GraphExecutionError as failure:
                if node.subgraph.error_policy.value == "return_error":
                    return {"error": failure.info.to_safe_dict()}
                raise
            finally:
                session.state.clear(StateScope.SUBGRAPH, bound.child.path or bound.node_path)
                session.state.clear(
                    StateScope.RUN,
                    f"run:{bound.child.path or bound.node_path}",
                )
            return {
                parent_port: child_outputs.get(child_port)
                for parent_port, child_port in node.subgraph.outputs.items()
            }
        if node.kind is NodeKind.LOOP:
            latest: Mapping[str, Any] = {}
            loop_budget = ExecutionBudget(node.loop.max_activations, parent=budget)
            self._emit(
                session,
                frame,
                kind="loop_enter",
                role="loop",
                payload={"max_iterations": node.loop.max_iterations},
            )
            for iteration in range(node.loop.max_iterations):
                loop_frame = session.next_activation(
                    bound.node_path,
                    parent_activation_id=frame.activation_id,
                    loop_path=bound.node_path,
                    loop_iteration=iteration,
                )
                self._emit(
                    session,
                    loop_frame,
                    kind="loop_iteration",
                    role="loop",
                    payload={"iteration": iteration},
                )
                child_inputs = {
                    child_port: inputs[parent_port]
                    for parent_port, child_port in node.loop.inputs.items()
                    if parent_port in inputs
                }
                # Previous loop outputs are available to a body through matching input names.
                child_inputs.update(latest)
                latest = self._execute_plan(
                    bound.child,
                    child_inputs,
                    session,
                    loop_budget,
                    parent_activation_id=frame.activation_id,
                    loop_path=bound.node_path,
                    loop_iteration=iteration,
                )
                if evaluate_predicate(node.loop.until, latest):
                    session.state.clear(StateScope.LOOP, bound.node_path)
                    session.state.clear(
                        StateScope.RUN,
                        f"run:{bound.child.path or bound.node_path}",
                    )
                    self._emit(
                        session,
                        frame,
                        kind="loop_exit",
                        role="loop",
                        payload={"iteration": iteration, "reason": "until"},
                    )
                    return {
                        parent_port: latest.get(child_port)
                        for parent_port, child_port in node.loop.outputs.items()
                    }
            session.state.clear(StateScope.LOOP, bound.node_path)
            session.state.clear(
                StateScope.RUN,
                f"run:{bound.child.path or bound.node_path}",
            )
            self._emit(
                session,
                frame,
                kind="loop_exhausted",
                role="loop",
                payload={"max_iterations": node.loop.max_iterations},
            )
            if node.loop.on_exhausted is LoopExhaustedPolicy.FAIL:
                raise GraphExecutionError(
                    "runtime.loop_exhausted",
                    f"Loop {bound.node_path!r} exhausted its iteration budget",
                    node_id=bound.node_path,
                    phase="loop",
                )
            if node.loop.on_exhausted is LoopExhaustedPolicy.TERMINATE:
                raise _TerminateGraph()
            self._emit(
                session,
                frame,
                kind="loop_exit",
                role="loop",
                payload={"reason": "continue_after_exhaustion"},
            )
            return {
                parent_port: latest.get(child_port)
                for parent_port, child_port in node.loop.outputs.items()
            }
        raise GraphExecutionError(
            "runtime.node_kind_unsupported",
            f"Unsupported node kind {node.kind.value!r}",
            node_id=bound.node_path,
            phase="kernel",
        )

    def _execute_plan(
        self,
        plan: BoundExecutionPlan,
        graph_inputs: Mapping[str, Any],
        session: _KernelSession,
        budget: ExecutionBudget,
        *,
        parent_activation_id: str = "",
        loop_path: str = "",
        loop_iteration: int | None = None,
    ) -> Mapping[str, Any]:
        """Execute one hierarchical DAG plan to completion.

        Args:
            plan (BoundExecutionPlan): Bound plan.
            graph_inputs (Mapping[str, Any]): Boundary input values.
            session (_KernelSession): Shared execution session.
            budget (ExecutionBudget): Current scope budget.
            parent_activation_id (str): Parent activation identity.
            loop_path (str): Active local loop path.
            loop_iteration (int | None): Active local iteration.

        Raises:
            GraphExecutionError: Cancellation, deadlock, budget, or node failure.
            _TerminateGraph: Structured termination requested by a loop.

        Returns:
            Mapping[str, Any]: Graph boundary outputs.
        """
        catalog = plan.contract_catalog
        delivered: dict[tuple[str, str], Any] = {}
        feedback_counts: dict[int, int] = {}
        completed: set[str] = set()
        pending = {node.id for node in plan.graph.nodes}
        graph_outputs: dict[str, Any] = {}
        while pending:
            progressed = False
            for node_id in sorted(pending):
                ready, skipped = self._ready_or_skipped(
                    plan,
                    node_id,
                    delivered,
                    completed,
                    catalog,
                )
                if skipped:
                    pending.remove(node_id)
                    completed.add(node_id)
                    progressed = True
                    break
                if not ready:
                    continue
                if self._cancelled(session.runtime):
                    raise GraphExecutionError(
                        "runtime.cancelled",
                        "Execution was cancelled before the next activation",
                        node_id=plan.nodes[node_id].node_path,
                        phase="cancellation",
                    )
                bound = plan.nodes[node_id]
                budget.consume(bound.node_path)
                frame = session.next_activation(
                    bound.node_path,
                    parent_activation_id=parent_activation_id,
                    loop_path=loop_path,
                    loop_iteration=loop_iteration,
                )
                role = (
                    bound.contract.ref.id
                    if bound.contract is not None
                    else bound.node.kind.value
                )
                inputs = self._node_inputs(plan, node_id, delivered, catalog)
                started = time.perf_counter()
                self._emit(
                    session,
                    frame,
                    kind="start",
                    role=role,
                    payload={"inputs": _safe_summary(inputs)},
                )
                try:
                    outputs = self._execute_node(
                        plan,
                        bound,
                        inputs,
                        graph_inputs,
                        session,
                        budget,
                        frame,
                    )
                except Exception as failure:
                    failure_payload = {"error_type": type(failure).__name__}
                    if isinstance(failure, GraphExecutionError):
                        failure_payload.update(
                            {
                                "error_code": failure.info.code,
                                "phase": failure.info.phase,
                                "details": failure.info.details,
                            }
                        )
                    self._emit(
                        session,
                        frame,
                        kind="fail",
                        role=role,
                        payload=failure_payload,
                        duration_ms=(time.perf_counter() - started) * 1000,
                    )
                    raise
                self._emit(
                    session,
                    frame,
                    kind="complete",
                    role=role,
                    payload={"outputs": _safe_summary(outputs)},
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
                feedback_targets, exhausted = self._propagate(
                    plan,
                    node_id,
                    outputs,
                    delivered,
                    catalog,
                    feedback_counts,
                )
                if bound.node.kind is NodeKind.OUTPUT:
                    graph_outputs.update(outputs)
                pending.remove(node_id)
                completed.add(node_id)
                if exhausted == "fail":
                    raise GraphExecutionError(
                        "runtime.feedback_exhausted",
                        "Generalized feedback exhausted its iteration budget",
                        node_id=bound.node_path,
                        phase="feedback",
                    )
                if exhausted == "terminate":
                    raise _TerminateGraph()
                for edge_index, target in feedback_targets:
                    affected = self._feedback_descendants(plan, target)
                    # Remove stale descendant deliveries before scheduling the
                    # target again; preserve the just-delivered feedback value.
                    feedback_edge = plan.graph.edges[edge_index]
                    feedback_address = (
                        feedback_edge.target.node,
                        feedback_edge.target.port,
                    )
                    for edge in plan.graph.edges:
                        if edge.source.node in affected:
                            address = (edge.target.node, edge.target.port)
                            if address != feedback_address:
                                delivered.pop(address, None)
                    completed.difference_update(affected)
                    pending.update(affected)
                    session.runtime.emit(
                        phase="feedback",
                        role="feedback",
                        component=bound.node_path,
                        kind="feedback_latched",
                        node_id=node_id,
                        node_path=bound.node_path,
                        interaction_step=session.interaction_step,
                        payload={
                            "edge_index": edge_index,
                            "target": plan.nodes[target].node_path,
                            "iteration": feedback_counts[edge_index],
                        },
                    )
                progressed = True
                break
            if not progressed:
                raise GraphExecutionError(
                    "runtime.graph_deadlock",
                    "No pending node is data/control ready",
                    phase="scheduling",
                    details={"pending": sorted(pending)},
                )
        return graph_outputs
