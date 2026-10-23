"""Contract and end-to-end tests for the explicit Android Graph Runtime."""

from __future__ import annotations

from pathlib import Path

import pytest

from zhixing.components import (
    Action,
    ActionExecutionInput,
    ActionResult,
    ActionType,
    DeviceEffectKind,
    ExecutionStatus,
    ObservationRequest,
    RunStatus,
    RuntimeContext,
)
from zhixing.graph import (
    AgentGraph,
    ComponentBinding,
    EdgeKind,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    NodeKind,
    NodeLifecycle,
    PortAddress,
    load_graph_yaml,
)
from zhixing.runtime import (
    BoundExecutionPlan,
    GraphExecutionKernel,
    MappingComponentResolver,
    bind_execution_plan,
)
from zhixing.runtime.android import (
    ACTION_EXECUTOR_CONTRACT,
    TRANSFORM_CONTRACT,
    AndroidActionService,
    AndroidGraphRuntime,
    AndroidObservationService,
    FixedActionComponent,
    _action_results_from_output,
    build_android_smoke_graph,
    build_android_smoke_plan,
)
from zhixing.runtime.artifacts import ArtifactStoreError, RunArtifactStore


class FakeAndroidDevice:
    """Small AndroidDevice-compatible fake that writes real test artifacts."""

    serial = "fake-android"
    platform = "android"
    w = 100
    h = 200

    def __init__(self) -> None:
        """Initialize call recording.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls: list[tuple] = []

    def screenshot(self, path: str) -> str:
        """Write a compact PNG-like artifact.

        Args:
            path (str): Host destination.

        Raises:
            OSError: Host writing fails.

        Returns:
            str: Destination path.
        """
        self.calls.append(("screenshot", path))
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
        return path

    def get_xml(self, path: str) -> str:
        """Write a valid UI hierarchy.

        Args:
            path (str): Host destination.

        Raises:
            OSError: Host writing fails.

        Returns:
            str: XML text.
        """
        self.calls.append(("xml", path))
        value = "<hierarchy><node text='Settings'/></hierarchy>"
        Path(path).write_text(value, encoding="utf-8")
        return value

    def go_home(self) -> None:
        """Record a physical HOME action.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls.append(("home",))

    def tap(self, x: int, y: int) -> None:
        """Record one physical coordinate tap.

        Args:
            x (int): Horizontal device coordinate.
            y (int): Vertical device coordinate.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls.append(("tap", x, y))

    def wait(self, seconds: float) -> None:
        """Record a non-physical wait.

        Args:
            seconds (float): Requested delay.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls.append(("wait", seconds))


class BrokenActionDevice(FakeAndroidDevice):
    """Fake device that disconnects when the action executes."""

    def go_home(self) -> None:
        """Raise a deterministic device failure.

        Args:
            None.

        Raises:
            RuntimeError: Always simulates disconnection.

        Returns:
            None.
        """
        raise RuntimeError("device offline")


class BrokenObservationDevice(FakeAndroidDevice):
    """Fake device that cannot capture a screenshot."""

    def screenshot(self, path: str) -> str:
        """Raise a deterministic capture failure.

        Args:
            path (str): Ignored destination.

        Raises:
            RuntimeError: Always simulates capture failure.

        Returns:
            str: Never returned.
        """
        del path
        raise RuntimeError("screencap failed")


def _implicit_observation_plan() -> BoundExecutionPlan:
    """Build an invalid-for-Android graph that expects a caller observation.

    Args:
        None.

    Raises:
        ValueError: The test graph or binding is invalid.

    Returns:
        BoundExecutionPlan: Plan with no explicit DeviceObserve service.
    """
    graph = AgentGraph(
        contract_version="1.1",
        nodes=(
            GraphNode(
                id="input",
                kind=NodeKind.INPUT,
                lifecycle=NodeLifecycle.ON_RUN_START,
            ),
            GraphNode(
                id="build_done",
                kind=NodeKind.COMPONENT,
                contract=TRANSFORM_CONTRACT,
                lifecycle=NodeLifecycle.PER_STEP,
                component=ComponentBinding(
                    candidates=(
                        GraphComponentRef(
                            namespace="test.android",
                            name="build_done",
                            version="1.0.0",
                        ),
                    ),
                ),
            ),
            GraphNode(
                id="execute_done",
                kind=NodeKind.COMPONENT,
                contract=ACTION_EXECUTOR_CONTRACT,
                lifecycle=NodeLifecycle.PER_STEP,
                component=ComponentBinding(
                    candidates=(
                        GraphComponentRef(
                            namespace="test.android",
                            name="execute_done",
                            version="1.0.0",
                        ),
                    ),
                ),
            ),
            GraphNode(
                id="output",
                kind=NodeKind.OUTPUT,
                lifecycle=NodeLifecycle.TERMINAL,
            ),
        ),
        edges=(
            GraphEdge(
                source=PortAddress(node="input", port="observation"),
                target=PortAddress(node="build_done", port="value"),
                kind=EdgeKind.DATA,
            ),
            GraphEdge(
                source=PortAddress(node="build_done", port="result"),
                target=PortAddress(node="execute_done", port="request"),
                kind=EdgeKind.DATA,
            ),
            GraphEdge(
                source=PortAddress(node="execute_done", port="result"),
                target=PortAddress(node="output", port="result"),
                kind=EdgeKind.DATA,
            ),
        ),
    )
    validation = graph.validate_graph()
    assert validation.is_valid, validation.errors
    return bind_execution_plan(
        graph,
        MappingComponentResolver(
            {
                "build_done": FixedActionComponent(Action(ActionType.DONE)),
                "execute_done": object(),
            }
        ),
    )


def test_run_artifact_store_isolates_runs_and_rejects_escape(tmp_path) -> None:
    """Allocate stable independent paths for two runs.

    Args:
        tmp_path (pathlib.Path): Isolated root.

    Raises:
        AssertionError: Namespaces collide or path escape is accepted.

    Returns:
        None.
    """
    first = RunArtifactStore(tmp_path, "run-a")
    second = RunArtifactStore(tmp_path, "run-b")
    one = first.allocate_observation(0, include_ui_tree=False)
    two = second.allocate_observation(0, include_ui_tree=True)
    assert one.screenshot_reference == "run-a/interaction-0000/observation-0000.png"
    assert one.ui_path is None
    assert two.ui_reference == "run-b/interaction-0000/observation-0000.xml"
    with pytest.raises(ArtifactStoreError, match="outside"):
        first.reference(tmp_path.parent / "escape.txt")


def test_observation_service_supports_screenshot_only(tmp_path) -> None:
    """Avoid UI dump when ObservationRequest disables it.

    Args:
        tmp_path (pathlib.Path): Artifact root.

    Raises:
        AssertionError: UI dump runs or metadata is incomplete.

    Returns:
        None.
    """
    device = FakeAndroidDevice()
    runtime = RuntimeContext(run_id="observe-only", device=device)
    store = RunArtifactStore(tmp_path, runtime.run_id)
    service = AndroidObservationService(device, store)
    observation = service.invoke(
        {"request": ObservationRequest(include_ui_tree=False)},
        runtime,
    )
    assert observation.ui_path is None
    assert observation.ui_artifact is None
    assert observation.device_id == "fake-android"
    assert [call[0] for call in device.calls] == ["screenshot"]


def test_action_service_reports_effect_terminal_and_invalid_input(tmp_path) -> None:
    """Distinguish physical actions, DONE, and validation failure.

    Args:
        tmp_path (pathlib.Path): Artifact root.

    Raises:
        AssertionError: Effect or terminal semantics are incorrect.

    Returns:
        None.
    """
    device = FakeAndroidDevice()
    runtime = RuntimeContext(run_id="actions", device=device)
    service = AndroidActionService(device, RunArtifactStore(tmp_path, runtime.run_id))
    home = service.invoke(
        {"request": ActionExecutionInput(Action(ActionType.KEY, {"code": "home"}))},
        runtime,
    )
    done = service.invoke(
        {"request": ActionExecutionInput(Action(ActionType.DONE))},
        runtime,
    )
    invalid = service.invoke(
        {"request": ActionExecutionInput(Action(ActionType.TAP, {"x": 100, "y": 1}))},
        runtime,
    )
    assert home.effect_performed
    assert home.effect_kind is DeviceEffectKind.UI_INPUT
    assert done.terminal_status is RunStatus.SUCCESS
    assert not done.effect_performed
    assert invalid.status is ExecutionStatus.FAILURE
    assert not invalid.effect_performed


def test_android_runtime_collects_typed_action_results_from_nested_outputs() -> None:
    """Preserve ordered typed ActionResults without parsing display payloads.

    Args:
        None.

    Raises:
        AssertionError: Typed leaves are lost, duplicated, or reordered.

    Returns:
        None.
    """
    first = ActionResult(
        Action(ActionType.KEY, {"code": "home"}),
        ExecutionStatus.SUCCESS,
    )
    terminal = ActionResult(
        Action(ActionType.DONE),
        ExecutionStatus.TERMINAL,
        terminal_status=RunStatus.SUCCESS,
    )
    output = {
        "result": first,
        "nested": ["ignored", {"terminal": terminal}],
    }
    assert _action_results_from_output(output) == (first, terminal)


def test_fake_android_graph_runtime_completes_explicit_closed_loop(tmp_path) -> None:
    """Execute observe/action/reobserve/DONE through one generalized Kernel.

    Args:
        tmp_path (pathlib.Path): Artifact root.

    Raises:
        AssertionError: Runtime flow, events, or artifacts differ.

    Returns:
        None.
    """
    device = FakeAndroidDevice()
    context = RuntimeContext(run_id="fake-closed-loop")
    result = AndroidGraphRuntime().run(
        build_android_smoke_plan(),
        {"value": ObservationRequest()},
        artifact_root=tmp_path,
        runtime=context,
        device=device,
    )
    assert result.status is RunStatus.SUCCESS
    assert result.kernel_status == "success"
    assert result.interaction_count == 1
    assert result.activation_count == 9
    assert result.state.step == 1
    assert [item.action.type for item in result.action_results] == [
        ActionType.KEY,
        ActionType.DONE,
    ]
    assert [call[0] for call in device.calls] == [
        "screenshot",
        "xml",
        "home",
        "screenshot",
        "xml",
    ]
    assert all(event.run_id == context.run_id for event in result.events)
    assert (tmp_path / "fake-closed-loop" / "manifest.json").is_file()


def test_android_runtime_never_synthesizes_missing_boundary_observation(tmp_path) -> None:
    """Keep a graph with no DeviceObserve from touching the Android device.

    Args:
        tmp_path (pathlib.Path): Artifact root.

    Raises:
        AssertionError: The facade invents an observation or device effect.

    Returns:
        None.
    """
    device = FakeAndroidDevice()
    result = AndroidGraphRuntime().run(
        _implicit_observation_plan(),
        {"task": "Inspect the current screen"},
        artifact_root=tmp_path,
        runtime=RuntimeContext(run_id="no-implicit-observation"),
        device=device,
    )

    assert result.status is RunStatus.FAILURE
    assert not result.state.observation_history
    assert not result.action_results
    assert device.calls == []


def test_missing_device_observe_does_not_probe_a_broken_device(tmp_path) -> None:
    """Avoid even a failed screenshot when the graph lacks DeviceObserve.

    Args:
        tmp_path (pathlib.Path): Artifact root.

    Raises:
        AssertionError: The facade probes the device outside graph execution.

    Returns:
        None.
    """
    result = AndroidGraphRuntime().run(
        _implicit_observation_plan(),
        {"task": "Inspect the current screen"},
        artifact_root=tmp_path,
        runtime=RuntimeContext(run_id="no-broken-device-probe"),
        device=BrokenObservationDevice(),
    )

    assert result.status is RunStatus.FAILURE
    assert "screencap failed" not in (result.error or "")
    assert not result.action_results


def test_android_runtime_preserves_evidence_on_action_device_failure(tmp_path) -> None:
    """Map action disconnection to DEVICE_FAILURE after the first observation.

    Args:
        tmp_path (pathlib.Path): Artifact root.

    Raises:
        AssertionError: Failure is hidden or prior evidence disappears.

    Returns:
        None.
    """
    result = AndroidGraphRuntime().run(
        build_android_smoke_plan(),
        {"value": ObservationRequest()},
        artifact_root=tmp_path,
        runtime=RuntimeContext(run_id="action-failure"),
        device=BrokenActionDevice(),
    )
    assert result.status is RunStatus.DEVICE_FAILURE
    assert result.error_details["kernel_error_code"] == "runtime.device_failure"
    assert len(result.action_results) == 1
    assert result.action_results[0].status is ExecutionStatus.DEVICE_FAILURE
    assert any(event.kind == "fail" and event.node_id == "execute_action" for event in result.events)
    assert list((tmp_path / "action-failure").glob("interaction-0000/observation-*.png"))


def test_android_runtime_stops_after_first_observation_failure(tmp_path) -> None:
    """Stop downstream components when initial screencap fails.

    Args:
        tmp_path (pathlib.Path): Artifact root.

    Raises:
        AssertionError: Runtime continues or misclassifies failure.

    Returns:
        None.
    """
    result = AndroidGraphRuntime().run(
        build_android_smoke_plan(),
        {"value": ObservationRequest()},
        artifact_root=tmp_path,
        runtime=RuntimeContext(run_id="observe-failure"),
        device=BrokenObservationDevice(),
    )
    assert result.status is RunStatus.DEVICE_FAILURE
    starts = [event.node_id for event in result.events if event.kind == "start"]
    assert starts == ["input", "observe_before"]
    assert not result.action_results


def test_python_and_graph_yaml_smoke_definitions_have_same_hash() -> None:
    """Round-trip the Android smoke graph through graph-native YAML data.

    Args:
        None.

    Raises:
        AssertionError: Compiler changes canonical semantics.

    Returns:
        None.
    """
    graph, _components = build_android_smoke_graph()
    source = (
        Path(__file__).parents[2]
        / "examples"
        / "graphs"
        / "android_graph_smoke.yaml"
    )
    compiled = load_graph_yaml(source)
    assert compiled.is_success
    assert compiled.graph.canonical_hash() == graph.canonical_hash()


def test_kernel_does_not_count_done_as_physical_interaction(tmp_path) -> None:
    """Count only the confirmed HOME effect, not DONE.

    Args:
        tmp_path (pathlib.Path): Artifact root.

    Raises:
        AssertionError: Static contract side effects inflate interactions.

    Returns:
        None.
    """
    result = AndroidGraphRuntime().run(
        build_android_smoke_plan(),
        {"value": ObservationRequest()},
        artifact_root=tmp_path,
        runtime=RuntimeContext(run_id="effect-count"),
        device=FakeAndroidDevice(),
    )
    assert result.interaction_count == 1
    assert len(result.action_results) == 2


def test_android_runtime_import_remains_explicit() -> None:
    """Prove Android support is imported only through its dedicated module.

    Args:
        None.

    Raises:
        AssertionError: Kernel gains direct device execution dependencies.

    Returns:
        None.
    """
    assert "Android" not in GraphExecutionKernel.__module__
