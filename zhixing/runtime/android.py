"""Android runtime services and facade for explicit AgentGraph execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from zhixing.components import (
    Action,
    ActionExecutionInput,
    ActionResult,
    ActionType,
    AgentState,
    DeviceExecutionError,
    DeviceObservation,
    ExecutionStatus,
    LegacyActionExecutor,
    ObservationRequest,
    RunResult,
    RunStatus,
    RuntimeContext,
)
from zhixing.devices.android import AndroidDevice
from zhixing.graph import (
    AgentGraph,
    ComponentBinding,
    EdgeKind,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    NodeContractRef,
    NodeKind,
    NodeLifecycle,
    PortAddress,
    Predicate,
    PredicateOperator,
)

from .artifacts import ArtifactStoreError, RunArtifactStore
from .kernel import (
    BoundExecutionPlan,
    GraphExecutionKernel,
    KernelResult,
    KernelStatus,
    bind_execution_plan,
)


DEVICE_OBSERVE_CONTRACT = NodeContractRef(
    id="zhixing.service.device_observe",
    version="2.0",
)
ACTION_EXECUTOR_CONTRACT = NodeContractRef(
    id="zhixing.service.action_executor",
    version="1.0",
)
TRANSFORM_CONTRACT = NodeContractRef(
    id="zhixing.control.transform",
    version="1.0",
)


def _action_results_from_output(value: Any) -> tuple[ActionResult, ...]:
    """Collect typed ActionResults from a bounded Kernel output tree.

    Compatibility AgentGraphs can use the core ``action_executor`` role rather
    than the explicit Android action service.  Those results reach the graph
    output but are not present in ``AndroidActionService.results``.  Recovering
    the typed values here lets both graph forms share the same RunResult
    semantics without parsing event text or component names.

    Args:
        value (Any): Kernel output mapping, sequence, or typed leaf value.

    Raises:
        None.

    Returns:
        tuple[ActionResult, ...]: Action results in deterministic traversal order.
    """
    found: list[ActionResult] = []

    def visit(candidate: Any) -> None:
        """Traverse only supported output containers.

        Args:
            candidate (Any): Current output value.

        Raises:
            None.

        Returns:
            None.
        """
        if isinstance(candidate, ActionResult):
            found.append(candidate)
        elif isinstance(candidate, Mapping):
            for item in candidate.values():
                visit(item)
        elif isinstance(candidate, (list, tuple)):
            for item in candidate:
                visit(item)

    visit(value)
    return tuple(found)


@dataclass
class AndroidObservationService:
    """Capture typed Android observations into a run artifact store."""

    device: Any
    artifacts: RunArtifactStore
    observations: list[DeviceObservation]
    _sequence: int

    def __init__(self, device: Any, artifacts: RunArtifactStore) -> None:
        """Create a device-bound observation service.

        Args:
            device (Any): AndroidDevice-compatible observation provider.
            artifacts (RunArtifactStore): Run-scoped artifact allocator.

        Raises:
            None.

        Returns:
            None: Initializes service state.
        """
        self.device = device
        self.artifacts = artifacts
        self.observations = []
        self._sequence = 0

    def invoke(
        self,
        inputs: Mapping[str, Any],
        runtime: RuntimeContext,
    ) -> DeviceObservation:
        """Capture screenshot and optional UI XML for one graph activation.

        Args:
            inputs (Mapping[str, Any]): Contract inputs containing ObservationRequest.
            runtime (RuntimeContext): Shared run context and interaction position.

        Raises:
            DeviceExecutionError: Input, capture, or artifact verification fails.

        Returns:
            DeviceObservation: Portable observation with stable artifact references.
        """
        request = inputs.get("request")
        if not isinstance(request, ObservationRequest):
            raise DeviceExecutionError(
                "observe",
                "DeviceObserve requires ObservationRequest",
            )
        try:
            allocated = self.artifacts.allocate_observation(
                runtime.step,
                include_ui_tree=request.include_ui_tree,
            )
            screenshot_path = str(allocated.screenshot_path)
            self.device.screenshot(screenshot_path)
            self.artifacts.verify_file(screenshot_path, minimum_size=8)
            ui_path: str | None = None
            if allocated.ui_path is not None:
                ui_path = str(allocated.ui_path)
                self.device.get_xml(ui_path)
                self.artifacts.verify_file(ui_path)
            width = int(getattr(self.device, "w", 0))
            height = int(getattr(self.device, "h", 0))
            if not width or not height:
                width, height = self.device.display_size()
            observation = DeviceObservation(
                screenshot_path=screenshot_path,
                width=width,
                height=height,
                ui_path=ui_path,
                platform=str(getattr(self.device, "platform", "android")),
                sequence=self._sequence,
                metadata=request.metadata,
                device_id=str(getattr(self.device, "serial", "") or ""),
                interaction_step=runtime.step,
                screenshot_artifact=allocated.screenshot_reference,
                ui_artifact=allocated.ui_reference,
            )
        except DeviceExecutionError:
            raise
        except Exception as error:
            raise DeviceExecutionError("observe", str(error)) from error
        self._sequence += 1
        self.observations.append(observation)
        runtime.state.last_observation = observation
        runtime.state.observation_history.append(observation)
        return observation


@dataclass
class AndroidActionService:
    """Execute typed actions and persist confirmed effect evidence."""

    device: Any
    artifacts: RunArtifactStore
    results: list[ActionResult]

    def __init__(self, device: Any, artifacts: RunArtifactStore) -> None:
        """Create a device-bound action service.

        Args:
            device (Any): AndroidDevice-compatible action target.
            artifacts (RunArtifactStore): Run-scoped artifact store.

        Raises:
            None.

        Returns:
            None: Initializes the service.
        """
        self.device = device
        self.artifacts = artifacts
        self.results = []
        self._executor = LegacyActionExecutor(device=device)

    def invoke(
        self,
        inputs: Mapping[str, Any],
        runtime: RuntimeContext,
    ) -> ActionResult:
        """Execute one ActionExecutionInput and persist its safe result.

        Args:
            inputs (Mapping[str, Any]): Contract inputs containing the request.
            runtime (RuntimeContext): Shared context with the bound device.

        Raises:
            DeviceExecutionError: Input, device, or artifact persistence fails.

        Returns:
            ActionResult: Confirmed action status and effect.
        """
        request = inputs.get("request")
        if not isinstance(request, ActionExecutionInput):
            raise DeviceExecutionError(
                "action_execute",
                "ActionExecutor requires ActionExecutionInput",
            )
        result = self._executor.invoke(request, runtime)
        try:
            artifact = self.artifacts.write_action(runtime.step, result.to_safe_dict())
            result = replace(
                result,
                metadata={**dict(result.metadata), "artifact": artifact},
            )
        except Exception as error:
            raise DeviceExecutionError("action_artifact", str(error)) from error
        self.results.append(result)
        runtime.state.last_action = request.action
        runtime.state.last_action_result = result
        if result.status is ExecutionStatus.DEVICE_FAILURE:
            raise DeviceExecutionError("action_execute", result.error or "device failure")
        return result


@dataclass(frozen=True)
class FixedActionComponent:
    """Convert any upstream value into one deterministic action request."""

    action: Action

    def invoke(self, input: Any, runtime: RuntimeContext) -> ActionExecutionInput:
        """Build a typed request while preserving an upstream observation.

        Args:
            input (Any): Usually the latest DeviceObservation.
            runtime (RuntimeContext): Shared run context.

        Raises:
            None.

        Returns:
            ActionExecutionInput: Fixed action and optional observation.
        """
        del runtime
        observation = input if isinstance(input, DeviceObservation) else None
        return ActionExecutionInput(action=self.action, observation=observation)


class AndroidGraphRuntime:
    """Assemble Android services around the paradigm-independent Kernel."""

    def run(
        self,
        plan: BoundExecutionPlan,
        inputs: Mapping[str, Any],
        *,
        artifact_root: str | Path,
        serial: str | None = None,
        runtime: RuntimeContext | None = None,
        device: Any | None = None,
    ) -> RunResult:
        """Execute one bound AgentGraph against a selected Android device.

        Args:
            plan (BoundExecutionPlan): Validated and bound contract 1.1 plan.
            inputs (Mapping[str, Any]): Caller-owned graph boundary inputs.
                The facade never enriches them with observations; device
                capture requires an explicit DeviceObserve activation.
            artifact_root (str | Path): Host root for isolated run artifacts.
            serial (str | None): Explicit ADB serial for a real device.
            runtime (RuntimeContext | None): Optional caller-owned context.
            device (Any | None): Explicit fake/test device; bypasses discovery.

        Raises:
            TypeError: The plan is not a BoundExecutionPlan.

        Returns:
            RunResult: Structured outcome, events, actions, and artifact namespace.
        """
        if not isinstance(plan, BoundExecutionPlan):
            raise TypeError("AndroidGraphRuntime requires BoundExecutionPlan")
        context = runtime or RuntimeContext(max_steps=plan.graph.policies.max_steps)
        context.state.current_task = inputs.get("task")
        context.metadata.setdefault("runtime", "android_graph")
        try:
            artifacts = (
                context.artifacts
                if isinstance(context.artifacts, RunArtifactStore)
                else RunArtifactStore(artifact_root, context.run_id)
            )
        except Exception as error:
            return self._preflight_failure(
                context,
                RunStatus.FAILURE,
                kernel_status="not_started",
                error=f"artifact setup failed: {error}",
            )
        context.artifacts = artifacts
        try:
            selected = device or _select_android_device(serial)
        except Exception as error:
            result = self._preflight_failure(
                context,
                RunStatus.DEVICE_FAILURE,
                kernel_status="not_started",
                error=str(error),
                artifact_namespace=artifacts.reference(artifacts.namespace),
            )
            return self._write_manifest_or_preserve(result, artifacts)
        context.device = selected
        context.metadata["device_id"] = str(getattr(selected, "serial", serial or "") or "")
        app_catalog = getattr(selected, "format_start_app_catalog_for_prompt", None)
        if callable(app_catalog):
            context.metadata.setdefault("available_apps", app_catalog())
        observation_service = AndroidObservationService(selected, artifacts)
        action_service = AndroidActionService(selected, artifacts)
        kernel = GraphExecutionKernel().run(
            plan,
            dict(inputs),
            runtime=context,
            services={
                DEVICE_OBSERVE_CONTRACT.id: observation_service,
                ACTION_EXECUTOR_CONTRACT.id: action_service,
            },
        )
        action_results = list(action_service.results)
        for item in _action_results_from_output(kernel.outputs):
            if not any(item is existing for existing in action_results):
                action_results.append(item)
        if action_results and context.state.last_action_result is None:
            context.state.last_action = action_results[-1].action
            context.state.last_action_result = action_results[-1]
        result = self._map_result(
            kernel,
            context,
            action_results,
            artifacts,
        )
        return self._write_manifest_or_preserve(result, artifacts)

    @staticmethod
    def _map_result(
        kernel: KernelResult,
        context: RuntimeContext,
        actions: list[ActionResult],
        artifacts: RunArtifactStore,
    ) -> RunResult:
        """Map scheduler status and Agent terminal semantics independently.

        Args:
            kernel (KernelResult): Generalized scheduler outcome.
            context (RuntimeContext): Shared run context.
            actions (list[ActionResult]): Ordered typed action evidence.
            artifacts (RunArtifactStore): Run artifact namespace.

        Raises:
            None.

        Returns:
            RunResult: Stable Android Agent outcome.
        """
        status = RunStatus.FAILURE
        error = kernel.error
        if kernel.error_code == "runtime.device_failure":
            status = RunStatus.DEVICE_FAILURE
        elif kernel.error_code == "runtime.cancelled":
            status = RunStatus.CANCELLED
        elif kernel.status is KernelStatus.BUDGET_EXHAUSTED:
            status = RunStatus.STEP_LIMIT
        elif kernel.status is KernelStatus.FAILURE:
            status = RunStatus.FAILURE
        elif actions:
            last = actions[-1]
            if last.terminal_status is not None:
                status = last.terminal_status
            elif last.status is ExecutionStatus.DEVICE_FAILURE:
                status = RunStatus.DEVICE_FAILURE
            elif last.status is ExecutionStatus.FAILURE:
                status = RunStatus.FAILURE
                error = last.error
            else:
                error = "AgentGraph completed without an explicit DONE or FAIL action"
        else:
            error = "AgentGraph completed without an ActionResult"
        return RunResult(
            run_id=context.run_id,
            status=status,
            state=context.state,
            step_count=len(actions),
            action_results=tuple(actions),
            events=tuple(kernel.events),
            final_output=dict(kernel.outputs),
            error=error,
            error_details={
                "kernel_error_code": kernel.error_code,
                "device_id": context.metadata.get("device_id", ""),
            },
            kernel_status=kernel.status.value,
            activation_count=kernel.activation_count,
            interaction_count=kernel.interaction_steps,
            artifact_namespace=artifacts.reference(artifacts.namespace),
        )

    @staticmethod
    def _preflight_failure(
        context: RuntimeContext,
        status: RunStatus,
        *,
        kernel_status: str,
        error: str,
        artifact_namespace: str = "",
    ) -> RunResult:
        """Build a result when Kernel execution cannot start.

        Args:
            context (RuntimeContext): Run identity and state.
            status (RunStatus): Normalized preflight status.
            kernel_status (str): Scheduler state, normally ``not_started``.
            error (str): Safe failure message.
            artifact_namespace (str): Optional allocated namespace reference.

        Raises:
            None.

        Returns:
            RunResult: Serializable preflight failure.
        """
        return RunResult(
            run_id=context.run_id,
            status=status,
            state=context.state,
            error=error,
            kernel_status=kernel_status,
            artifact_namespace=artifact_namespace,
        )

    @staticmethod
    def _write_manifest_or_preserve(
        result: RunResult,
        artifacts: RunArtifactStore,
    ) -> RunResult:
        """Persist final safe evidence without deleting earlier artifacts.

        Args:
            result (RunResult): Final run result.
            artifacts (RunArtifactStore): Target namespace.

        Raises:
            ArtifactStoreError: Manifest persistence fails visibly to caller.

        Returns:
            RunResult: Original result, or a visible artifact failure result.
        """
        try:
            artifacts.write_manifest(result.to_safe_dict())
            return result
        except ArtifactStoreError as error:
            return replace(
                result,
                status=RunStatus.FAILURE,
                error=f"run manifest persistence failed: {error}",
            )


def run_android_agent_graph(
    plan: BoundExecutionPlan,
    inputs: Mapping[str, Any],
    *,
    artifact_root: str | Path,
    serial: str | None = None,
    runtime: RuntimeContext | None = None,
    device: Any | None = None,
) -> RunResult:
    """Execute one bound graph through the public Android facade.

    Args:
        plan (BoundExecutionPlan): Validated and bound contract 1.1 plan.
        inputs (Mapping[str, Any]): Graph inputs.
        artifact_root (str | Path): Host artifact root.
        serial (str | None): Explicit real-device serial.
        runtime (RuntimeContext | None): Optional caller-owned context.
        device (Any | None): Optional fake/test device.

    Raises:
        TypeError: The plan is invalid.

    Returns:
        RunResult: Structured Android graph execution result.
    """
    return AndroidGraphRuntime().run(
        plan,
        inputs,
        artifact_root=artifact_root,
        serial=serial,
        runtime=runtime,
        device=device,
    )


def _select_android_device(serial: str | None) -> AndroidDevice:
    """Select an Android device without importing optional Harmony support.

    Args:
        serial (str | None): Explicit serial or None for unique-device selection.

    Raises:
        ValueError: The explicit serial is absent or not ready.
        RuntimeError: No unique ready Android device is available.

    Returns:
        AndroidDevice: Serial-bound Android session.
    """
    states = AndroidDevice.list_device_states()
    if serial is not None:
        target = next((device for device in states if device.device_id == serial), None)
        if target is None:
            raise ValueError(f"Android device {serial!r} was not reported by adb")
        if target.status != "device":
            raise ValueError(
                f"Android device {serial!r} is not ready (status={target.status!r})"
            )
        return AndroidDevice(serial=serial)
    ready = [device for device in states if device.status == "device"]
    if not ready:
        raise RuntimeError("No Android device in the 'device' state was found")
    if len(ready) > 1:
        candidates = ", ".join(device.device_id for device in ready)
        raise RuntimeError(
            f"Multiple Android devices are ready; pass an explicit serial ({candidates})"
        )
    return AndroidDevice(serial=ready[0].device_id)


def build_android_smoke_graph(
    action: Action | None = None,
) -> tuple[AgentGraph, Mapping[str, Any]]:
    """Build a deterministic observe/action/reobserve/DONE AgentGraph.

    Args:
        action (Action | None): Safe physical action. Defaults to HOME key.

    Raises:
        ValueError: AgentGraph construction or validation fails.

    Returns:
        tuple[AgentGraph, Mapping[str, Any]]: Graph and explicit components.
    """
    physical = action or Action(ActionType.KEY, {"code": "home"})
    graph = AgentGraph(
        contract_version="1.1",
        nodes=(
            _input_node(),
            _service_node("observe_before", DEVICE_OBSERVE_CONTRACT),
            _component_node("build_action", TRANSFORM_CONTRACT),
            _service_node("execute_action", ACTION_EXECUTOR_CONTRACT),
            GraphNode(
                id="action_succeeded",
                kind=NodeKind.CONDITION,
                lifecycle=NodeLifecycle.PER_STEP,
                predicate=Predicate(
                    field="succeeded",
                    operator=PredicateOperator.EQ,
                    value=True,
                ),
            ),
            _service_node("observe_after", DEVICE_OBSERVE_CONTRACT),
            _component_node("build_done", TRANSFORM_CONTRACT),
            _service_node("execute_done", ACTION_EXECUTOR_CONTRACT),
            _output_node(),
        ),
        edges=(
            _edge("input", "value", "observe_before", "request"),
            _edge("observe_before", "observation", "build_action", "value"),
            _edge("build_action", "result", "execute_action", "request"),
            _edge("execute_action", "result", "action_succeeded", "value"),
            _edge(
                "action_succeeded",
                "true",
                "observe_after",
                "control",
                EdgeKind.CONTROL,
            ),
            _edge("input", "value", "observe_after", "request"),
            _edge("observe_after", "observation", "build_done", "value"),
            _edge("build_done", "result", "execute_done", "request"),
            _edge("execute_done", "result", "output", "result"),
        ),
    )
    components = {
        "observe_before": object(),
        "build_action": FixedActionComponent(physical),
        "execute_action": object(),
        "observe_after": object(),
        "build_done": FixedActionComponent(Action(ActionType.DONE)),
        "execute_done": object(),
    }
    validation = graph.validate_graph()
    if not validation.is_valid:
        raise ValueError(
            "Android smoke graph is invalid: "
            + "; ".join(item.message for item in validation.errors)
        )
    return graph, components


def build_android_smoke_plan(
    action: Action | None = None,
) -> BoundExecutionPlan:
    """Build and bind the deterministic Android smoke graph.

    Args:
        action (Action | None): Optional safe physical action.

    Raises:
        GraphBindingError: Contract binding fails.

    Returns:
        BoundExecutionPlan: Plan ready for AndroidGraphRuntime.
    """
    graph, components = build_android_smoke_graph(action)
    return bind_execution_plan(graph, components)


def _binding(name: str) -> ComponentBinding:
    """Create one explicit smoke-test component binding.

    Args:
        name (str): Candidate name.

    Raises:
        ValueError: Binding validation fails.

    Returns:
        ComponentBinding: Single-candidate binding.
    """
    return ComponentBinding(
        candidates=(GraphComponentRef(namespace="zhixing.android", name=name),)
    )


def _service_node(node_id: str, contract: NodeContractRef) -> GraphNode:
    """Create a runtime-service component node.

    Args:
        node_id (str): Stable node identifier.
        contract (NodeContractRef): Exact runtime-service contract.

    Raises:
        ValueError: Node validation fails.

    Returns:
        GraphNode: Bound service marker node.
    """
    return GraphNode(
        id=node_id,
        kind=NodeKind.COMPONENT,
        contract=contract,
        lifecycle=NodeLifecycle.PER_STEP,
        component=_binding(node_id),
    )


def _component_node(node_id: str, contract: NodeContractRef) -> GraphNode:
    """Create a typed component node for the deterministic graph.

    Args:
        node_id (str): Stable node identifier.
        contract (NodeContractRef): Exact typed contract.

    Raises:
        ValueError: Node validation fails.

    Returns:
        GraphNode: Typed component node.
    """
    return _service_node(node_id, contract)


def _input_node() -> GraphNode:
    """Create the graph boundary input node.

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


def _output_node() -> GraphNode:
    """Create the graph boundary output node.

    Args:
        None.

    Raises:
        None.

    Returns:
        GraphNode: Terminal output node.
    """
    return GraphNode(
        id="output",
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
    """Create one deterministic graph edge.

    Args:
        source (str): Source node.
        source_port (str): Source port.
        target (str): Target node.
        target_port (str): Target port.
        kind (EdgeKind): Data or control edge.

    Raises:
        ValueError: Edge validation fails.

    Returns:
        GraphEdge: Validated edge.
    """
    return GraphEdge(
        source=PortAddress(node=source, port=source_port),
        target=PortAddress(node=target, port=target_port),
        kind=kind,
    )
