"""Deterministic lifecycle scheduler for validated mobile AgentGraph V1 graphs."""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from zhixing.components import (
    Action,
    ActionResult,
    ExecutionStatus,
    RunEvent,
    RunResult,
    RunStatus,
    RuntimeContext,
    TaskInput,
    VerifierResult,
    redact_mapping,
)
from zhixing.graph import (
    EdgeKind,
    FeedbackExhaustedPolicy,
    GraphEdge,
    GraphNode,
    GraphRole,
    NodeKind,
    NodeLifecycle,
    Predicate,
    PredicateOperator,
)
from zhixing.graph.ports import PortCardinality, PortDirection, port_for_node, ports_for_node

from .assemblers import invoke_role, reset_memory
from .errors import GraphExecutionError, GraphRuntimeError, ObservationError, RuntimeErrorInfo
from .models import BoundAgentGraph, ObservationProvider, StepFrame, ValueStore


_MISSING = object()
_ROLE_OUTPUT_PORT = {
    GraphRole.PERCEPTION: "perception",
    GraphRole.PLANNER: "plan",
    GraphRole.REASONING: "action",
    GraphRole.MEMORY: "context",
    GraphRole.ACTION_EXECUTOR: "result",
    GraphRole.VERIFIER: "result",
}


def _field_value(value: Any, path: str) -> Any:
    """Read a safe dotted field path from dataclasses, models, or mappings.

    Args:
        value (Any): Predicate source value.
        path (str): Dot-separated field path validated by AgentGraph.

    Raises:
        None.

    Returns:
        Any: Field value or a private missing sentinel.
    """
    current = value
    for part in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(part, _MISSING)
        else:
            current = getattr(current, part, _MISSING)
        if current is _MISSING:
            return _MISSING
    return current


def evaluate_predicate(predicate: Predicate, value: Any) -> bool:
    """Evaluate one structured predicate without executing configured code.

    Args:
        predicate (Predicate): Validated AgentGraph predicate.
        value (Any): Typed source value.

    Raises:
        GraphExecutionError: A non-existence predicate references a missing field
            or values cannot be compared.

    Returns:
        bool: Predicate result.
    """
    actual = _field_value(value, predicate.field)
    operator = predicate.operator
    if operator is PredicateOperator.EXISTS:
        return actual is not _MISSING
    if actual is _MISSING:
        raise GraphExecutionError(
            "runtime.predicate_field_missing",
            f"Predicate field {predicate.field!r} does not exist",
            phase="predicate",
        )
    try:
        if operator is PredicateOperator.EQ:
            return actual == predicate.value
        if operator is PredicateOperator.NE:
            return actual != predicate.value
        if operator is PredicateOperator.TRUTHY:
            return bool(actual)
        if operator is PredicateOperator.FALSY:
            return not bool(actual)
        if operator is PredicateOperator.GT:
            return actual > predicate.value
        if operator is PredicateOperator.GTE:
            return actual >= predicate.value
        if operator is PredicateOperator.LT:
            return actual < predicate.value
        if operator is PredicateOperator.LTE:
            return actual <= predicate.value
    except (TypeError, ValueError) as error:
        raise GraphExecutionError(
            "runtime.predicate_comparison",
            f"Predicate {operator.value!r} could not compare its values",
            phase="predicate",
            details={"error_type": type(error).__name__},
        ) from error
    raise GraphExecutionError(
        "runtime.predicate_operator",
        f"Predicate operator {operator.value!r} is unsupported",
        phase="predicate",
    )


def _safe_summary(value: Any) -> Mapping[str, Any]:
    """Create a bounded event payload for one typed runtime value.

    Args:
        value (Any): Runtime input or output value.

    Raises:
        None.

    Returns:
        Mapping[str, Any]: Redacted structural summary.
    """
    if value is None:
        return {"type": "None"}
    summary: dict[str, Any] = {"type": type(value).__name__}
    if isinstance(value, (Action, ActionResult)):
        action = value if isinstance(value, Action) else value.action
        summary["action_type"] = action.type.value
        if isinstance(value, ActionResult):
            summary["status"] = value.status.value
    elif isinstance(value, VerifierResult):
        summary.update(is_success=value.is_success, should_retry=value.should_retry)
    elif isinstance(value, (tuple, list)):
        summary["count"] = len(value)
    elif is_dataclass(value):
        summary["fields"] = sorted(asdict(value).keys())[:20]
    return redact_mapping(summary)


class _MobileCompatibilityExecutor:
    """Preserve contract 1.0 mobile scheduling behind the generic Kernel facade."""

    def run(
        self,
        bound: BoundAgentGraph,
        task: TaskInput,
        observation_provider: ObservationProvider,
        *,
        runtime: RuntimeContext | None = None,
    ) -> RunResult:
        """Run one bound AgentGraph until success, failure, cancellation, or limit.

        Args:
            bound (BoundAgentGraph): Validated and component-bound graph.
            task (TaskInput): User task for this run.
            observation_provider (ObservationProvider): Device observation boundary.
            runtime (RuntimeContext | None): Optional caller-owned run context.

        Raises:
            None: Runtime failures are normalized into RunResult.

        Returns:
            RunResult: Structured execution status, state, events, actions, and error.
        """
        context = runtime or RuntimeContext(max_steps=bound.graph.policies.max_steps)
        if runtime is None:
            context.max_steps = bound.graph.policies.max_steps
        limit = min(bound.graph.policies.max_steps, max(1, context.max_steps))
        events: list[RunEvent] = []
        previous_sink = context.event_sink

        def collect(event: RunEvent) -> None:
            """Collect an event and forward it to the caller's original sink.

            Args:
                event (RunEvent): Event emitted by the active runtime context.

            Raises:
                Exception: Propagates an exception from the caller-provided sink.

            Returns:
                None: Appends and forwards the event.
            """
            events.append(event)
            if previous_sink is not None:
                previous_sink(event)

        context.event_sink = collect
        context._event_sequence = 0
        context.step = 0
        context.state.reset(task)
        store = ValueStore()
        action_results: list[ActionResult] = []
        feedback_counts: dict[int, int] = {}
        feedback_latch: dict[tuple[str, str], Any] = {}
        latest_output: Any = None
        latest_verification: VerifierResult | None = None
        error_info: RuntimeErrorInfo | None = None

        try:
            self._complete_builtin(context, "input", "on_run_start", {"task_id": task.id})
            self._propagate(bound, store, 0, "input", "task", task, persistent=True)
            frame = StepFrame(step=0)
            self._run_start(bound, store, frame, context)
            for step in range(limit):
                context.step = step
                context.state.step = step
                frame = StepFrame(step=step, feedback_inputs=dict(feedback_latch))
                feedback_latch = {}
                if self._cancelled(context):
                    return self._finish(
                        context,
                        RunStatus.CANCELLED,
                        action_results,
                        events,
                        latest_output,
                    )
                try:
                    frame.pre_observation = observation_provider.observe(context, phase="pre_action")
                except Exception as error:
                    raise ObservationError(
                        "runtime.observation_failed",
                        "ObservationProvider failed before action",
                        phase="pre_action",
                        details={"error_type": type(error).__name__},
                    ) from error
                context.state.last_observation = frame.pre_observation
                context.state.observation_history.append(frame.pre_observation)
                self._propagate(bound, store, step, "input", "observation", frame.pre_observation)
                for (target_node, target_port), value in frame.feedback_inputs.items():
                    store.put(step, target_node, target_port, value)

                executed: set[str] = set()
                self._run_phase(
                    bound,
                    store,
                    frame,
                    context,
                    {NodeLifecycle.STATEFUL, NodeLifecycle.PER_STEP},
                    executed,
                )
                action_node = self._primary_action_node(bound)
                if action_node.id not in executed or not isinstance(frame.action_result, ActionResult):
                    raise GraphExecutionError(
                        "runtime.deadlock",
                        "Graph made no progress to the primary ActionExecutor",
                        node_id=action_node.id,
                        phase="per_step",
                    )
                action_results.append(frame.action_result)
                latest_output = frame.action_result
                if self._requires_post_observation(bound):
                    try:
                        frame.post_observation = observation_provider.observe(context, phase="post_action")
                    except Exception as error:
                        raise ObservationError(
                            "runtime.observation_failed",
                            "ObservationProvider failed after action",
                            phase="post_action",
                            details={"error_type": type(error).__name__},
                        ) from error
                    context.state.last_observation = frame.post_observation
                    context.state.observation_history.append(frame.post_observation)
                self._run_phase(
                    bound,
                    store,
                    frame,
                    context,
                    {NodeLifecycle.POST_ACTION},
                    executed,
                )
                latest_verification = self._latest_verification(bound, store, step) or latest_verification

                feedback_status, feedback_latch = self._feedback_decision(
                    bound,
                    store,
                    step,
                    context,
                    feedback_counts,
                )
                if feedback_status == "retry":
                    continue
                if feedback_status == "fail":
                    return self._finish(
                        context,
                        RunStatus.FAILURE,
                        action_results,
                        events,
                        latest_output,
                        RuntimeErrorInfo(
                            "runtime.feedback_exhausted",
                            "Feedback limit was exhausted",
                            phase="feedback",
                        ),
                    )
                if feedback_status == "terminate":
                    status = (
                        RunStatus.SUCCESS
                        if latest_verification is None or latest_verification.is_success
                        else RunStatus.FAILURE
                    )
                    return self._finish(context, status, action_results, events, latest_output)

                action_status = frame.action_result.status
                if action_status is ExecutionStatus.DEVICE_FAILURE:
                    return self._finish(
                        context,
                        RunStatus.DEVICE_FAILURE,
                        action_results,
                        events,
                        latest_output,
                    )
                if action_status is ExecutionStatus.FAILURE:
                    return self._finish(context, RunStatus.FAILURE, action_results, events, latest_output)
                if action_status is ExecutionStatus.TERMINAL:
                    return self._finish(context, RunStatus.SUCCESS, action_results, events, latest_output)

                terminal = self._run_terminal(bound, store, frame, context, executed)
                if terminal:
                    status = (
                        RunStatus.SUCCESS
                        if latest_verification is None or latest_verification.is_success
                        else RunStatus.FAILURE
                    )
                    return self._finish(context, status, action_results, events, latest_output)
            context.state.step = limit
            context.step = limit
            return self._finish(
                context,
                RunStatus.STEP_LIMIT,
                action_results,
                events,
                latest_output,
            )
        except ObservationError as error:
            error_info = error.info
            return self._finish(
                context,
                RunStatus.DEVICE_FAILURE,
                action_results,
                events,
                latest_output,
                error_info,
            )
        except GraphRuntimeError as error:
            error_info = error.info
            return self._finish(
                context,
                RunStatus.FAILURE,
                action_results,
                events,
                latest_output,
                error_info,
            )
        except Exception as error:
            error_info = RuntimeErrorInfo(
                "runtime.unexpected",
                "Unexpected runtime failure",
                details={"error_type": type(error).__name__},
            )
            return self._finish(
                context,
                RunStatus.FAILURE,
                action_results,
                events,
                latest_output,
                error_info,
            )
        finally:
            context.event_sink = previous_sink

    def _run_start(
        self,
        bound: BoundAgentGraph,
        store: ValueStore,
        frame: StepFrame,
        context: RuntimeContext,
    ) -> None:
        """Execute run-start components and reset stateful memory nodes.

        Args:
            bound (BoundAgentGraph): Bound graph.
            store (ValueStore): Runtime value store.
            frame (StepFrame): Initial frame.
            context (RuntimeContext): Shared run context.

        Raises:
            GraphExecutionError: A required run-start node cannot execute.

        Returns:
            None: Writes persistent outputs into the value store.
        """
        executed: set[str] = set()
        for node in sorted(bound.graph.nodes, key=lambda item: item.id):
            if node.role is GraphRole.MEMORY and node.lifecycle is NodeLifecycle.STATEFUL:
                self._execute_memory_reset(bound, node, context)
        self._run_phase(
            bound,
            store,
            frame,
            context,
            {NodeLifecycle.ON_RUN_START},
            executed,
        )

    def _run_phase(
        self,
        bound: BoundAgentGraph,
        store: ValueStore,
        frame: StepFrame,
        context: RuntimeContext,
        lifecycles: set[NodeLifecycle],
        executed: set[str],
    ) -> None:
        """Execute every ready node in selected lifecycle phases.

        Args:
            bound (BoundAgentGraph): Bound graph.
            store (ValueStore): Runtime value store.
            frame (StepFrame): Current step state.
            context (RuntimeContext): Shared run context.
            lifecycles (set[NodeLifecycle]): Lifecycle phases eligible to run.
            executed (set[str]): Nodes already executed in this step.

        Raises:
            GraphExecutionError: A started node fails or returns invalid data.

        Returns:
            None: Mutates the value store, frame, state, and event stream.
        """
        while True:
            progressed = False
            for node in sorted(bound.graph.nodes, key=lambda item: item.id):
                if node.id in executed or node.lifecycle not in lifecycles:
                    continue
                if node.kind is NodeKind.INPUT or node.kind is NodeKind.OUTPUT:
                    continue
                if not self._ready(bound, store, context.step, node):
                    continue
                if self._cancelled(context):
                    return
                if node.kind is NodeKind.CONDITION:
                    self._execute_condition(bound, store, node, context)
                elif node.kind is NodeKind.COMPONENT:
                    self._execute_component(bound, store, frame, node, context)
                executed.add(node.id)
                progressed = True
            if not progressed:
                break
        for node in sorted(bound.graph.nodes, key=lambda item: item.id):
            if node.id in executed or node.lifecycle not in lifecycles:
                continue
            control_edges = self._incoming_edges(bound, node.id, EdgeKind.CONTROL)
            if control_edges and not any(
                (context.step, edge.target.node, edge.target.port) in store.controls
                for edge in control_edges
            ):
                component_name = (
                    bound.components[node.id].candidates[0].reference.name
                    if node.id in bound.components
                    else f"builtin.{node.kind.value}"
                )
                context.emit(
                    phase=node.lifecycle.value,
                    role=node.role.value if node.role is not None else node.kind.value,
                    component=component_name,
                    kind="node_skipped",
                    node_id=node.id,
                    payload={"reason": "incoming_control_not_active"},
                )

    def _execute_component(
        self,
        bound: BoundAgentGraph,
        store: ValueStore,
        frame: StepFrame,
        node: GraphNode,
        context: RuntimeContext,
    ) -> None:
        """Execute one ready component with paired lifecycle events.

        Args:
            bound (BoundAgentGraph): Bound graph.
            store (ValueStore): Runtime value store.
            frame (StepFrame): Current step frame.
            node (GraphNode): Component node to execute.
            context (RuntimeContext): Shared run context.

        Raises:
            GraphExecutionError: Assembly, invocation, or normalization fails.

        Returns:
            None: Propagates normalized output and updates state.
        """
        component = bound.components[node.id]
        inputs = self._inputs(store, context.step, node)
        call_id = uuid.uuid4().hex
        component_name = component.candidates[0].reference.name
        context.emit(
            phase=node.lifecycle.value,
            role=node.role.value,
            component=component_name,
            kind="start",
            node_id=node.id,
            call_id=call_id,
            payload={"inputs": sorted(inputs)},
        )
        started = time.perf_counter()
        try:
            invocation = invoke_role(component, inputs, frame, context)
            output = invocation.output
            component_name = invocation.component_name
            duration_ms = (time.perf_counter() - started) * 1000
            context.emit(
                phase=node.lifecycle.value,
                role=node.role.value,
                component=component_name,
                kind="complete",
                node_id=node.id,
                call_id=call_id,
                duration_ms=duration_ms,
                payload=_safe_summary(output),
            )
            output_port = _ROLE_OUTPUT_PORT[node.role]
            self._propagate(
                bound,
                store,
                context.step,
                node.id,
                output_port,
                output,
                persistent=node.lifecycle is NodeLifecycle.ON_RUN_START,
            )
            if node.role is GraphRole.PLANNER:
                context.state.plan = output
            elif node.role is GraphRole.REASONING:
                frame.action = output
                context.state.last_action = output
            elif node.role is GraphRole.ACTION_EXECUTOR:
                frame.action_result = output
                context.state.last_action_result = output
        except Exception as error:
            duration_ms = (time.perf_counter() - started) * 1000
            context.emit(
                phase=node.lifecycle.value,
                role=node.role.value,
                component=component_name,
                kind="fail",
                node_id=node.id,
                call_id=call_id,
                duration_ms=duration_ms,
                payload={"error_type": f"{type(error).__module__}.{type(error).__qualname__}"},
            )
            if isinstance(error, GraphRuntimeError):
                raise
            raise GraphExecutionError(
                "runtime.node_failed",
                f"Node {node.id!r} failed during execution",
                node_id=node.id,
                phase=node.lifecycle.value,
                details={"error_type": type(error).__name__},
            ) from error

    def _execute_memory_reset(
        self,
        bound: BoundAgentGraph,
        node: GraphNode,
        context: RuntimeContext,
    ) -> None:
        """Reset a stateful Memory node with paired node events.

        Args:
            bound (BoundAgentGraph): Bound graph.
            node (GraphNode): Memory node.
            context (RuntimeContext): Shared run context.

        Raises:
            GraphExecutionError: Memory reset fails.

        Returns:
            None: Resets component memory.
        """
        call_id = uuid.uuid4().hex
        name = bound.components[node.id].candidates[0].reference.name
        context.emit(
            phase="on_run_start",
            role="memory",
            component=name,
            kind="start",
            node_id=node.id,
            call_id=call_id,
            payload={"operation": "reset"},
        )
        started = time.perf_counter()
        try:
            reset_memory(bound.components[node.id], context)
            context.emit(
                phase="on_run_start",
                role="memory",
                component=name,
                kind="complete",
                node_id=node.id,
                call_id=call_id,
                duration_ms=(time.perf_counter() - started) * 1000,
                payload={"operation": "reset"},
            )
        except Exception as error:
            context.emit(
                phase="on_run_start",
                role="memory",
                component=name,
                kind="fail",
                node_id=node.id,
                call_id=call_id,
                duration_ms=(time.perf_counter() - started) * 1000,
                payload={"error_type": type(error).__name__},
            )
            raise

    def _execute_condition(
        self,
        bound: BoundAgentGraph,
        store: ValueStore,
        node: GraphNode,
        context: RuntimeContext,
    ) -> None:
        """Evaluate a condition and activate exactly one control branch.

        Args:
            bound (BoundAgentGraph): Bound graph.
            store (ValueStore): Runtime value store.
            node (GraphNode): Condition node.
            context (RuntimeContext): Shared run context.

        Raises:
            GraphExecutionError: Predicate field or comparison is invalid.

        Returns:
            None: Activates one outgoing control branch.
        """
        value = store.get(context.step, node.id, "value")
        call_id = uuid.uuid4().hex
        context.emit(
            phase=node.lifecycle.value,
            role="condition",
            component="builtin.condition",
            kind="start",
            node_id=node.id,
            call_id=call_id,
        )
        started = time.perf_counter()
        try:
            branch = "true" if evaluate_predicate(node.predicate, value) else "false"
            self._propagate_control(bound, store, context.step, node.id, branch)
            context.emit(
                phase=node.lifecycle.value,
                role="condition",
                component="builtin.condition",
                kind="complete",
                node_id=node.id,
                call_id=call_id,
                duration_ms=(time.perf_counter() - started) * 1000,
                payload={"branch": branch},
            )
        except Exception as error:
            context.emit(
                phase=node.lifecycle.value,
                role="condition",
                component="builtin.condition",
                kind="fail",
                node_id=node.id,
                call_id=call_id,
                duration_ms=(time.perf_counter() - started) * 1000,
                payload={"error_type": type(error).__name__},
            )
            raise

    def _run_terminal(
        self,
        bound: BoundAgentGraph,
        store: ValueStore,
        frame: StepFrame,
        context: RuntimeContext,
        executed: set[str],
    ) -> bool:
        """Execute active terminal output nodes without inferring success from data alone.

        Args:
            bound (BoundAgentGraph): Bound graph.
            store (ValueStore): Runtime value store.
            frame (StepFrame): Current step frame.
            context (RuntimeContext): Shared run context.
            executed (set[str]): Nodes already executed this step.

        Raises:
            None.

        Returns:
            bool: True when a terminal control path was activated.
        """
        terminal = False
        for node in sorted(bound.graph.nodes, key=lambda item: item.id):
            if node.kind is not NodeKind.OUTPUT or node.id in executed:
                continue
            has_control_edges = self._incoming_edges(bound, node.id, EdgeKind.CONTROL)
            control_active = any(
                (context.step, edge.target.node, edge.target.port) in store.controls
                for edge in has_control_edges
            )
            if not control_active:
                continue
            self._complete_builtin(
                context,
                node.id,
                "terminal",
                _safe_summary(store.get(context.step, node.id, "result", frame.action_result)),
            )
            executed.add(node.id)
            terminal = True
        return terminal

    def _feedback_decision(
        self,
        bound: BoundAgentGraph,
        store: ValueStore,
        step: int,
        context: RuntimeContext,
        counts: dict[int, int],
    ) -> tuple[str, dict[tuple[str, str], Any]]:
        """Evaluate feedback edges after post-action nodes complete.

        Args:
            bound (BoundAgentGraph): Bound graph.
            store (ValueStore): Runtime value store.
            step (int): Current interaction step.
            context (RuntimeContext): Shared run context.
            counts (dict[int, int]): Per-edge completed feedback iteration counts.

        Raises:
            GraphExecutionError: Feedback source or predicate is invalid.

        Returns:
            tuple[str, dict[tuple[str, str], Any]]: Decision and next-step latched values.
        """
        latch: dict[tuple[str, str], Any] = {}
        for index, edge in enumerate(bound.graph.edges):
            if edge.kind is not EdgeKind.FEEDBACK or edge.feedback is None:
                continue
            value = store.get(step, edge.source.node, edge.source.port, _MISSING)
            if value is _MISSING or not evaluate_predicate(edge.feedback.predicate, value):
                continue
            used = counts.get(index, 0)
            if used < edge.feedback.max_iterations:
                used += 1
                counts[index] = used
                latch[(edge.target.node, edge.target.port)] = value
                context.emit(
                    phase="feedback",
                    role="runtime",
                    component="builtin.feedback",
                    kind="feedback_latched",
                    node_id=edge.target.node,
                    payload={
                        "edge_index": index,
                        "iteration": used,
                        "max_iterations": edge.feedback.max_iterations,
                        "source_step": step,
                        "target_step": step + 1,
                    },
                )
                return "retry", latch
            policy = edge.feedback.on_exhausted
            context.emit(
                phase="feedback",
                role="runtime",
                component="builtin.feedback",
                kind="feedback_exhausted",
                node_id=edge.target.node,
                payload={
                    "edge_index": index,
                    "iterations": used,
                    "policy": policy.value,
                },
            )
            if policy is FeedbackExhaustedPolicy.FAIL:
                return "fail", {}
            if policy is FeedbackExhaustedPolicy.TERMINATE:
                return "terminate", {}
        return "continue", {}

    def _ready(self, bound: BoundAgentGraph, store: ValueStore, step: int, node: GraphNode) -> bool:
        """Determine whether data and control prerequisites activate a node.

        Args:
            bound (BoundAgentGraph): Bound graph.
            store (ValueStore): Runtime value store.
            step (int): Current interaction step.
            node (GraphNode): Candidate node.

        Raises:
            None.

        Returns:
            bool: True when the node may execute now.
        """
        control_edges = self._incoming_edges(bound, node.id, EdgeKind.CONTROL)
        if control_edges and not any(
            (step, edge.target.node, edge.target.port) in store.controls for edge in control_edges
        ):
            return False
        for port in ports_for_node(node):
            if port.direction is PortDirection.INPUT and port.required and not store.has(step, node.id, port.id):
                return False
        return True

    def _inputs(self, store: ValueStore, step: int, node: GraphNode) -> dict[str, Any]:
        """Collect delivered values for the node's declared input ports.

        Args:
            store (ValueStore): Runtime value store.
            step (int): Current interaction step.
            node (GraphNode): Target node.

        Raises:
            None.

        Returns:
            dict[str, Any]: Present input values keyed by port ID.
        """
        result: dict[str, Any] = {}
        for port in ports_for_node(node):
            if port.direction is PortDirection.INPUT and store.has(step, node.id, port.id):
                result[port.id] = store.get(step, node.id, port.id)
        return result

    def _propagate(
        self,
        bound: BoundAgentGraph,
        store: ValueStore,
        step: int,
        source_node: str,
        source_port: str,
        value: Any,
        *,
        persistent: bool = False,
    ) -> None:
        """Store an output and deliver it across ordinary data edges.

        Args:
            bound (BoundAgentGraph): Bound graph.
            store (ValueStore): Runtime value store.
            step (int): Current interaction step.
            source_node (str): Producing node ID.
            source_port (str): Producing port ID.
            value (Any): Typed output value.
            persistent (bool): Whether downstream delivery persists across steps.

        Raises:
            GraphExecutionError: An edge condition references invalid data.

        Returns:
            None: Writes source and downstream addresses.
        """
        store.put(step, source_node, source_port, value, persistent=persistent)
        nodes = {node.id: node for node in bound.graph.nodes}
        for edge in bound.graph.edges:
            if edge.kind is not EdgeKind.DATA:
                continue
            if edge.source.node != source_node or edge.source.port != source_port:
                continue
            if edge.condition is not None and not evaluate_predicate(edge.condition, value):
                continue
            target = nodes[edge.target.node]
            descriptor = port_for_node(target, edge.target.port)
            if descriptor is not None and descriptor.cardinality is PortCardinality.MULTIPLE:
                store.append(step, edge.target.node, edge.target.port, value)
                if persistent:
                    persistent_values = store.persistent.setdefault((edge.target.node, edge.target.port), [])
                    if isinstance(persistent_values, list):
                        persistent_values.append(value)
            else:
                store.put(
                    step,
                    edge.target.node,
                    edge.target.port,
                    value,
                    persistent=persistent,
                )

    def _propagate_control(
        self,
        bound: BoundAgentGraph,
        store: ValueStore,
        step: int,
        source_node: str,
        source_port: str,
    ) -> None:
        """Activate matching outgoing control edges.

        Args:
            bound (BoundAgentGraph): Bound graph.
            store (ValueStore): Runtime value store.
            step (int): Current interaction step.
            source_node (str): Condition node ID.
            source_port (str): Selected branch port.

        Raises:
            None.

        Returns:
            None: Adds active control targets to the store.
        """
        for edge in bound.graph.edges:
            if (
                edge.kind is EdgeKind.CONTROL
                and edge.source.node == source_node
                and edge.source.port == source_port
            ):
                store.controls.add((step, edge.target.node, edge.target.port))

    def _incoming_edges(
        self,
        bound: BoundAgentGraph,
        node_id: str,
        kind: EdgeKind,
    ) -> list[GraphEdge]:
        """Return incoming edges of one kind for a node.

        Args:
            bound (BoundAgentGraph): Bound graph.
            node_id (str): Target logical node ID.
            kind (EdgeKind): Edge kind to filter.

        Raises:
            None.

        Returns:
            list[GraphEdge]: Matching edges in declarative order.
        """
        return [
            edge for edge in bound.graph.edges if edge.target.node == node_id and edge.kind is kind
        ]

    def _primary_action_node(self, bound: BoundAgentGraph) -> GraphNode:
        """Return the validator-approved primary ActionExecutor node.

        Args:
            bound (BoundAgentGraph): Bound graph.

        Raises:
            GraphExecutionError: No primary ActionExecutor is available.

        Returns:
            GraphNode: Selected primary action node.
        """
        actions = [node for node in bound.graph.nodes if node.role is GraphRole.ACTION_EXECUTOR]
        primary = [node for node in actions if node.primary]
        if not primary and len(actions) == 1:
            primary = actions
        if len(primary) != 1:
            raise GraphExecutionError(
                "runtime.primary_action_missing",
                "Graph requires exactly one primary ActionExecutor",
                phase="execution",
            )
        return primary[0]

    def _requires_post_observation(self, bound: BoundAgentGraph) -> bool:
        """Check whether the graph contains post-action consumers.

        Args:
            bound (BoundAgentGraph): Bound graph.

        Raises:
            None.

        Returns:
            bool: True when a post-action observation is required.
        """
        return any(node.lifecycle is NodeLifecycle.POST_ACTION for node in bound.graph.nodes)

    def _latest_verification(
        self,
        bound: BoundAgentGraph,
        store: ValueStore,
        step: int,
    ) -> VerifierResult | None:
        """Return the latest typed verifier output for a step.

        Args:
            bound (BoundAgentGraph): Bound graph.
            store (ValueStore): Runtime value store.
            step (int): Current interaction step.

        Raises:
            None.

        Returns:
            VerifierResult | None: Latest verifier result if produced.
        """
        for node in sorted(bound.graph.nodes, key=lambda item: item.id, reverse=True):
            if node.role is GraphRole.VERIFIER:
                value = store.get(step, node.id, "result")
                if isinstance(value, VerifierResult):
                    return value
        return None

    def _cancelled(self, context: RuntimeContext) -> bool:
        """Read supported cooperative cancellation signal forms.

        Args:
            context (RuntimeContext): Shared run context.

        Raises:
            None.

        Returns:
            bool: True when cancellation has been requested.
        """
        signal = context.cancellation
        if signal is None:
            return False
        checker = getattr(signal, "is_cancelled", None)
        if callable(checker):
            return bool(checker())
        if callable(signal):
            return bool(signal())
        return bool(signal)

    def _complete_builtin(
        self,
        context: RuntimeContext,
        node_id: str,
        phase: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        """Emit a paired start/complete lifecycle for an instant built-in node.

        Args:
            context (RuntimeContext): Shared run context.
            node_id (str): Built-in logical node ID.
            phase (str): Lifecycle phase.
            payload (Mapping[str, Any] | None): Safe event details.

        Raises:
            Exception: Propagates caller event sink failures.

        Returns:
            None: Emits a correlated start and complete pair through RuntimeContext.
        """
        call_id = uuid.uuid4().hex
        context.emit(
            phase=phase,
            role="runtime",
            component=f"builtin.{node_id}",
            kind="start",
            node_id=node_id,
            call_id=call_id,
        )
        context.emit(
            phase=phase,
            role="runtime",
            component=f"builtin.{node_id}",
            kind="complete",
            node_id=node_id,
            call_id=call_id,
            duration_ms=0.0,
            payload=payload,
        )

    def _finish(
        self,
        context: RuntimeContext,
        status: RunStatus,
        action_results: list[ActionResult],
        events: list[RunEvent],
        final_output: Any,
        error: RuntimeErrorInfo | None = None,
    ) -> RunResult:
        """Create the final result and append a structured status event.

        Args:
            context (RuntimeContext): Shared run context.
            status (RunStatus): Final normalized run status.
            action_results (list[ActionResult]): Executed action results.
            events (list[RunEvent]): Collected runtime events.
            final_output (Any): Latest graph output value.
            error (RuntimeErrorInfo | None): Optional structured failure.

        Raises:
            Exception: Propagates caller event sink failures.

        Returns:
            RunResult: Serializable final execution evidence.
        """
        context.emit(
            phase="terminal",
            role="runtime",
            component="graph_runtime",
            kind="status_changed",
            payload={"status": status.value, "error_code": error.code if error else ""},
        )
        return RunResult(
            run_id=context.run_id,
            status=status,
            state=context.state,
            step_count=len(action_results),
            action_results=tuple(action_results),
            events=tuple(events),
            final_output=final_output,
            error=error.message if error else "",
            error_details=error.to_safe_dict() if error else {},
        )


class GraphRuntime:
    """Backward-compatible mobile facade delegated through GraphExecutionKernel."""

    def __init__(self) -> None:
        """Create the compatibility executor used by the delegated plan.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self._compatibility = _MobileCompatibilityExecutor()

    def run(
        self,
        bound: BoundAgentGraph,
        task: TaskInput,
        observation_provider: ObservationProvider,
        *,
        runtime: RuntimeContext | None = None,
    ) -> RunResult:
        """Delegate the public V1 mobile run to the shared Kernel boundary.

        Args:
            bound (BoundAgentGraph): Validated and component-bound V1 graph.
            task (TaskInput): User task.
            observation_provider (ObservationProvider): Explicit observation service.
            runtime (RuntimeContext | None): Optional caller-owned context.

        Raises:
            None: Compatibility failures remain normalized as RunResult.

        Returns:
            RunResult: Existing V1 result contract.
        """
        from .kernel import GraphExecutionKernel

        return GraphExecutionKernel().run_compatibility(
            lambda: self._compatibility.run(
                bound,
                task,
                observation_provider,
                runtime=runtime,
            )
        )

    def __getattr__(self, name: str) -> Any:
        """Preserve tested V1 diagnostic helpers during facade migration.

        Args:
            name (str): Compatibility helper attribute name.

        Raises:
            AttributeError: The compatibility executor does not expose the name.

        Returns:
            Any: Bound helper from the compatibility executor.
        """
        return getattr(self._compatibility, name)
