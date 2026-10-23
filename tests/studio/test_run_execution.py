"""Scheduler, cancellation, fake-device, and recovery tests for Studio Runs."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from tests.runtime.test_android_graph_runtime import (
    BrokenActionDevice,
    FakeAndroidDevice,
)
from zhixing.catalog import BuiltInComponentResolver
from zhixing.components import (
    Action,
    ActionType,
    AgentState,
    ExecutionStatus,
    ObservationRequest,
    RunResult,
    RunStatus,
    RuntimeContext,
    TaskInput,
)
from zhixing.graph import (
    AgentGraph,
    ComponentBinding,
    EdgeKind,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    GraphPolicies,
    NodeKind,
    NodeLifecycle,
    PortAddress,
    compile_studio_flow_document,
)
from zhixing.runtime import (
    BoundExecutionPlan,
    MappingComponentResolver,
    SimpleCancellationSignal,
    bind_execution_plan,
)
from zhixing.runtime.android import (
    ACTION_EXECUTOR_CONTRACT,
    DEVICE_OBSERVE_CONTRACT,
    TRANSFORM_CONTRACT,
    AndroidGraphRuntime,
    FixedActionComponent,
)
from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.flow_template_loader import get_flow_template_document
from zhixing.studio.run_artifacts import LocalStudioRunArtifactStore
from zhixing.studio.run_debug import StudioRunDebugCapture
from zhixing.studio.run_errors import StudioRunDeviceBusyError
from zhixing.studio.run_events import DurableRunEventService
from zhixing.studio.run_execution import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
    AndroidStudioRunExecutionAdapter,
    DeviceLeaseRegistry,
    LocalThreadRunScheduler,
    ProductionComponentResolverFactory,
    StudioRunOrchestrator,
)
from zhixing.studio.run_models import StudioRunLifecycle
from zhixing.studio.run_repository import SQLiteStudioRunRepository
from zhixing.studio.run_service import StudioRunApplicationService

class FixedObservationRequest:
    """Deterministic component converting a task into an observation request."""

    def invoke(self, input: Any, runtime: RuntimeContext) -> ObservationRequest:
        """Return one request without inspecting the task or device.

        Args:
            input (Any): Upstream task, intentionally unused.
            runtime (RuntimeContext): Shared runtime, intentionally unused.

        Raises:
            None.

        Returns:
            ObservationRequest: UI-tree-enabled observation request.
        """
        del input, runtime
        return ObservationRequest(include_ui_tree=True)


class SequentialActionLLM:
    """Return a deterministic physical action followed by explicit DONE."""

    def __init__(self, responses: list[str] | None = None) -> None:
        """Initialize a caller-supplied or TAP-then-DONE response script.

        Args:
            responses (list[str] | None): Optional parser-compatible responses.

        Raises:
            None.

        Returns:
            None.
        """
        self.responses = list(responses) if responses is not None else [
            _action_response("TAP", x=20, y=30),
            _action_response("DONE"),
        ]
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def generate(self, prompt: str, images: list[str] | None = None) -> str:
        """Return the next valid general-VLM action response.

        Args:
            prompt (str): Rendered reasoning prompt.
            images (list[str] | None): Current observation artifact paths.

        Raises:
            AssertionError: The graph invokes reasoning more than twice.

        Returns:
            str: Next parser-compatible JSON action.
        """
        self.calls.append((prompt, tuple(images or ())))
        assert self.responses, "reasoning ran beyond the bounded test script"
        return self.responses.pop(0)


class FailSecondReasoningLLM(SequentialActionLLM):
    """Return one TAP and then fail the model boundary deterministically."""

    def __init__(self) -> None:
        """Initialize one successful first response.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        super().__init__([_action_response("TAP", x=20, y=30)])

    def generate(self, prompt: str, images: list[str] | None = None) -> str:
        """Return the first action and fail the second model call.

        Args:
            prompt (str): Rendered reasoning prompt.
            images (list[str] | None): Current observation paths.

        Raises:
            RuntimeError: The second and later calls simulate model failure.

        Returns:
            str: First parser-compatible TAP response.
        """
        if self.responses:
            return super().generate(prompt, images)
        self.calls.append((prompt, tuple(images or ())))
        raise RuntimeError("deterministic model failure")


class FailSecondTapDevice(FakeAndroidDevice):
    """Execute one TAP and fail before a second physical device effect."""

    def __init__(self) -> None:
        """Initialize fake device calls and tap attempt count.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        super().__init__()
        self.tap_attempts = 0

    def tap(self, x: int, y: int) -> None:
        """Record the first tap and reject the second.

        Args:
            x (int): Horizontal coordinate.
            y (int): Vertical coordinate.

        Raises:
            RuntimeError: The second attempt simulates device loss.

        Returns:
            None.
        """
        self.tap_attempts += 1
        if self.tap_attempts == 2:
            raise RuntimeError("device disconnected after first tap")
        super().tap(x, y)


def _action_response(action: str, **params: int) -> str:
    """Build one compact parser-compatible action response.

    Args:
        action (str): General-VLM action identifier.
        **params (int): Optional integer action parameters.

    Raises:
        TypeError: Payload values are not JSON serializable.

    Returns:
        str: JSON action response.
    """
    return json.dumps(
        {"action": action, "params": params, "thought": action.lower()},
        separators=(",", ":"),
    )


def _standard_template_plan(
    llm: Any,
    *,
    max_steps: int = 15,
    feedback_iterations: int = 10,
) -> BoundExecutionPlan:
    """Compile and bind the exact standard template with bounded test policies.

    Args:
        llm (Any): Explicit deterministic reasoning dependency.
        max_steps (int): Maximum confirmed physical interactions.
        feedback_iterations (int): Feedback edge iteration limit.

    Raises:
        AssertionError: Template compilation fails.
        GraphBindingError: Production component binding fails.

    Returns:
        BoundExecutionPlan: Ready explicit Android execution plan.
    """
    catalog = build_studio_component_catalog()
    compiled = compile_studio_flow_document(
        get_flow_template_document("modular_baseline"),
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert compiled.graph is not None, compiled.to_safe_dict()
    graph = compiled.graph.model_copy(
        update={
            "policies": compiled.graph.policies.model_copy(
                update={
                    "max_steps": max_steps,
                    "max_feedback_iterations": feedback_iterations,
                }
            ),
            "edges": tuple(
                edge.model_copy(
                    update={
                        "feedback": edge.feedback.model_copy(
                            update={"max_iterations": feedback_iterations}
                        )
                    }
                )
                if edge.feedback is not None
                else edge
                for edge in compiled.graph.edges
            ),
        }
    )
    return bind_execution_plan(
        graph,
        BuiltInComponentResolver(dependency_provider={"llm": llm}),
        contract_catalog=catalog.node_contract_catalog(),
    )


class MappingResolverFactory:
    """Small test factory returning a fresh explicit mapping resolver."""

    def __init__(self, components: dict[str, Any]) -> None:
        """Store deterministic component mappings.

        Args:
            components (dict[str, Any]): Candidate-name mappings.

        Raises:
            None.

        Returns:
            None.
        """
        self.components = components

    def create(self) -> MappingComponentResolver:
        """Create one side-effect-free mapping resolver.

        Args:
            None.

        Raises:
            None.

        Returns:
            MappingComponentResolver: Fresh resolver.
        """
        return MappingComponentResolver(self.components)


def _binding(name: str) -> ComponentBinding:
    """Build one exact-version test component binding.

    Args:
        name (str): Candidate name.

    Raises:
        ValueError: Binding is invalid.

    Returns:
        ComponentBinding: Single-candidate binding.
    """
    return ComponentBinding(
        candidates=(
            GraphComponentRef(
                namespace="test.studio",
                name=name,
                version="1.0.0",
            ),
        )
    )


def _node(node_id: str, contract) -> GraphNode:
    """Create one typed component/service graph node.

    Args:
        node_id (str): Stable node and candidate name.
        contract (NodeContractRef): Exact node contract.

    Raises:
        ValueError: Node is invalid.

    Returns:
        GraphNode: Component graph node.
    """
    return GraphNode(
        id=node_id,
        kind=NodeKind.COMPONENT,
        contract=contract,
        lifecycle=NodeLifecycle.PER_STEP,
        component=_binding(node_id),
    )


def _edge(source: str, source_port: str, target: str, target_port: str) -> GraphEdge:
    """Create one data edge.

    Args:
        source (str): Source node.
        source_port (str): Source port.
        target (str): Target node.
        target_port (str): Target port.

    Raises:
        ValueError: Edge is invalid.

    Returns:
        GraphEdge: Data edge.
    """
    return GraphEdge(
        source=PortAddress(node=source, port=source_port),
        target=PortAddress(node=target, port=target_port),
        kind=EdgeKind.DATA,
    )


def _android_task_graph(
    action: Action,
    *,
    max_steps: int = 15,
) -> tuple[AgentGraph, dict[str, Any]]:
    """Build a task-input graph that uses real Android service boundaries.

    Args:
        action (Action): Deterministic action executed after observation.
        max_steps (int): Interaction limit.

    Raises:
        ValueError: Graph is invalid.

    Returns:
        tuple[AgentGraph, dict[str, Any]]: Graph and explicit components.
    """
    graph = AgentGraph(
        contract_version="1.1",
        policies=GraphPolicies(max_steps=max_steps),
        nodes=(
            GraphNode(
                id="input",
                kind=NodeKind.INPUT,
                lifecycle=NodeLifecycle.ON_RUN_START,
            ),
            _node("build_observation", TRANSFORM_CONTRACT),
            _node("observe", DEVICE_OBSERVE_CONTRACT),
            _node("build_action", TRANSFORM_CONTRACT),
            _node("execute", ACTION_EXECUTOR_CONTRACT),
            GraphNode(
                id="output",
                kind=NodeKind.OUTPUT,
                lifecycle=NodeLifecycle.TERMINAL,
            ),
        ),
        edges=(
            _edge("input", "task", "build_observation", "value"),
            _edge("build_observation", "result", "observe", "request"),
            _edge("observe", "observation", "build_action", "value"),
            _edge("build_action", "result", "execute", "request"),
            _edge("execute", "result", "output", "result"),
        ),
    )
    validation = graph.validate_graph()
    assert validation.is_valid, validation.errors
    return graph, {
        "build_observation": FixedObservationRequest(),
        "observe": object(),
        "build_action": FixedActionComponent(action),
        "execute": object(),
    }


def _persist_run(
    database: Path,
    graph: AgentGraph,
    *,
    owner: str = "process-current",
) -> tuple[StudioRunApplicationService, SQLiteStudioRunRepository, str]:
    """Persist one valid exact graph revision and create an accepted Run.

    Args:
        database (Path): Temporary Studio database.
        graph (AgentGraph): Valid graph.
        owner (str): Process owner identity.

    Raises:
        ValueError: Fixture contracts are invalid.
        sqlite3.Error: Persistence fails.

    Returns:
        tuple: Run application service, repository, and Run identity.
    """
    catalog = build_studio_component_catalog()
    document = get_flow_template_document("modular_baseline")
    document["policies"]["maxSteps"] = graph.policies.max_steps
    agents = SQLiteAgentDocumentRepository(database)
    authoring = StudioApplicationService(catalog=catalog, repository=agents)
    agent, revision = authoring.create_agent(
        "Execution fixture",
        initial_document=document,
    )
    repository = SQLiteStudioRunRepository(database)
    events = DurableRunEventService(repository)
    service = StudioRunApplicationService(
        agents=agents,
        runs=repository,
        events=events,
        process_owner_id=owner,
    )
    resource, _created = service.create_run(
        {
            "clientRequestId": f"request-{owner}",
            "agentId": agent.agent_id,
            "revisionId": revision.revision_id,
            "task": {"text": "Observe and finish"},
            "deviceProfileId": "fake-device",
        }
    )
    return service, repository, resource.run_id


def _orchestrator(
    tmp_path: Path,
    repository: SQLiteStudioRunRepository,
    components: dict[str, Any],
    device: Any,
    *,
    owner: str = "process-current",
    minimum_free_bytes: int = 1,
    leases: DeviceLeaseRegistry | None = None,
) -> tuple[StudioRunOrchestrator, LocalStudioRunArtifactStore]:
    """Build one fake-device orchestration stack.

    Args:
        tmp_path (Path): Managed artifact parent.
        repository (SQLiteStudioRunRepository): Shared persistence adapter.
        components (dict[str, Any]): Explicit graph components.
        device (Any): Fake Android device.
        owner (str): Current process owner.
        minimum_free_bytes (int): Evidence reserve for failure tests.
        leases (DeviceLeaseRegistry | None): Optional shared lease registry.

    Raises:
        OSError: Managed storage cannot be created.

    Returns:
        tuple[StudioRunOrchestrator, LocalStudioRunArtifactStore]: Stack.
    """
    events = DurableRunEventService(repository)
    artifacts = LocalStudioRunArtifactStore(
        tmp_path / "managed",
        repository,
        minimum_free_bytes=minimum_free_bytes,
    )
    debug = StudioRunDebugCapture(artifacts=artifacts, events=events)
    fixed_action = components.get("build_action")
    dependency_provider = {}
    if isinstance(fixed_action, FixedActionComponent):
        action = fixed_action.action
        response_action = (
            str(action.params.get("code", "back")).upper()
            if action.type is ActionType.KEY
            else action.type.value.upper()
        )
        response_params = {} if action.type is ActionType.KEY else action.params
        dependency_provider = {
            "llm": SequentialActionLLM([
                _action_response(response_action, **response_params)
            ])
        }
    execution = AndroidStudioRunExecutionAdapter(
        components=ProductionComponentResolverFactory(
            dependency_provider=dependency_provider,
        ),
        artifacts=artifacts,
        profiles=AndroidDeviceProfileResolver(
            {
                "fake-device": AndroidDeviceProfile(
                    "fake-device",
                    device=device,
                )
            }
        ),
        leases=leases,
        warning_sink=repository.set_storage_warnings,
    )
    return (
        StudioRunOrchestrator(
            runs=repository,
            events=events,
            execution=execution,
            debug=debug,
            process_owner_id=owner,
        ),
        artifacts,
    )


def test_fake_device_orchestrator_completes_and_persists_events(tmp_path) -> None:
    """Execute one valid revision through AndroidGraphRuntime and durable sinks."""
    graph, components = _android_task_graph(Action(ActionType.DONE))
    _service, repository, run_id = _persist_run(
        tmp_path / "studio.sqlite3",
        graph,
    )
    device = FakeAndroidDevice()
    orchestrator, artifacts = _orchestrator(
        tmp_path,
        repository,
        components,
        device,
    )
    orchestrator.execute(run_id)
    record = repository.get_run(run_id)
    assert record.lifecycle is StudioRunLifecycle.TERMINAL
    assert record.result is not None
    assert record.result.status == RunStatus.SUCCESS.value
    assert repository.query_events(run_id, after=0, limit=100).terminal is True
    assert any(call[0] == "screenshot" for call in device.calls)
    assert (artifacts.runtime_root / run_id / "manifest.json").is_file()


def test_modular_studio_template_runs_observe_tap_feedback_observe_done(tmp_path) -> None:
    """Run the exact shipped template through a two-observation Android loop.

    Args:
        tmp_path (Path): Isolated runtime artifact root.

    Raises:
        AssertionError: The template loses feedback, evidence, or terminal semantics.

    Returns:
        None.
    """
    catalog = build_studio_component_catalog()
    compiled = compile_studio_flow_document(
        get_flow_template_document("modular_baseline"),
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert compiled.graph is not None, compiled.to_safe_dict()
    llm = SequentialActionLLM()
    plan = bind_execution_plan(
        compiled.graph,
        BuiltInComponentResolver(dependency_provider={"llm": llm}),
        contract_catalog=catalog.node_contract_catalog(),
    )
    device = FakeAndroidDevice()
    result = AndroidGraphRuntime().run(
        plan,
        {
            "task": TaskInput("Inspect the current screen"),
            "value": ObservationRequest(include_ui_tree=True),
        },
        artifact_root=tmp_path,
        runtime=RuntimeContext(run_id="studio-modular-template"),
        device=device,
    )

    assert result.status is RunStatus.SUCCESS
    assert result.step_count == 2
    assert result.interaction_count == 1
    assert len(result.state.observation_history) == 2
    assert [item.action.type for item in result.action_results] == [
        ActionType.TAP,
        ActionType.DONE,
    ]
    assert [call[0] for call in device.calls] == [
        "screenshot",
        "xml",
        "tap",
        "screenshot",
        "xml",
    ]
    assert len(llm.calls) == 2
    assert result.state.observation_history[0].sequence == 0
    assert result.state.observation_history[1].sequence == 1


def test_standard_template_preserves_evidence_across_controlled_failures(
    tmp_path,
) -> None:
    """Verify terminal and failure boundaries without losing prior evidence.

    Args:
        tmp_path (Path): Isolated artifact parent.

    Raises:
        AssertionError: Status, device effects, or causal evidence diverge.

    Returns:
        None.
    """
    explicit_fail_device = FakeAndroidDevice()
    explicit_fail = AndroidGraphRuntime().run(
        _standard_template_plan(
            SequentialActionLLM([_action_response("FAIL")])
        ),
        {"task": TaskInput("Fail explicitly"), "value": ObservationRequest()},
        artifact_root=tmp_path / "explicit-fail",
        runtime=RuntimeContext(run_id="explicit-fail"),
        device=explicit_fail_device,
    )
    assert explicit_fail.status is RunStatus.FAILURE
    assert len(explicit_fail.state.observation_history) == 1
    assert explicit_fail.action_results[-1].action.type is ActionType.FAIL
    assert [call[0] for call in explicit_fail_device.calls] == ["screenshot", "xml"]

    model_device = FakeAndroidDevice()
    model_failure = AndroidGraphRuntime().run(
        _standard_template_plan(FailSecondReasoningLLM()),
        {"task": TaskInput("Fail model after tap"), "value": ObservationRequest()},
        artifact_root=tmp_path / "model-failure",
        runtime=RuntimeContext(run_id="model-failure"),
        device=model_device,
    )
    assert model_failure.status is RunStatus.FAILURE
    assert len(model_failure.state.observation_history) == 2
    assert [item.action.type for item in model_failure.action_results] == [ActionType.TAP]
    assert [call[0] for call in model_device.calls] == [
        "screenshot", "xml", "tap", "screenshot", "xml",
    ]

    broken_device = FailSecondTapDevice()
    device_failure = AndroidGraphRuntime().run(
        _standard_template_plan(
            SequentialActionLLM([
                _action_response("TAP", x=20, y=30),
                _action_response("TAP", x=40, y=50),
            ])
        ),
        {"task": TaskInput("Lose device after tap"), "value": ObservationRequest()},
        artifact_root=tmp_path / "device-failure",
        runtime=RuntimeContext(run_id="device-failure"),
        device=broken_device,
    )
    assert device_failure.status is RunStatus.DEVICE_FAILURE
    assert len(device_failure.state.observation_history) == 2
    assert [item.status for item in device_failure.action_results] == [
        ExecutionStatus.SUCCESS,
        ExecutionStatus.DEVICE_FAILURE,
    ]
    assert [call[0] for call in broken_device.calls].count("tap") == 1

    exhausted_device = FakeAndroidDevice()
    exhausted = AndroidGraphRuntime().run(
        _standard_template_plan(
            SequentialActionLLM([
                _action_response("TAP", x=20, y=30),
                _action_response("TAP", x=40, y=50),
            ]),
            feedback_iterations=1,
        ),
        {"task": TaskInput("Exhaust feedback"), "value": ObservationRequest()},
        artifact_root=tmp_path / "feedback-exhausted",
        runtime=RuntimeContext(run_id="feedback-exhausted"),
        device=exhausted_device,
    )
    assert exhausted.status is RunStatus.FAILURE
    assert len(exhausted.state.observation_history) == 2
    assert len(exhausted.action_results) == 2
    assert [call[0] for call in exhausted_device.calls].count("tap") == 2

    limited_device = FakeAndroidDevice()
    limited = AndroidGraphRuntime().run(
        _standard_template_plan(
            SequentialActionLLM([_action_response("TAP", x=20, y=30)]),
            max_steps=1,
        ),
        {"task": TaskInput("Reach step limit"), "value": ObservationRequest()},
        artifact_root=tmp_path / "step-limit",
        runtime=RuntimeContext(run_id="step-limit", max_steps=1),
        device=limited_device,
    )
    assert limited.status is RunStatus.STEP_LIMIT
    assert len(limited.state.observation_history) == 1
    assert len(limited.action_results) == 1
    assert [call[0] for call in limited_device.calls] == [
        "screenshot", "xml", "tap",
    ]


def test_accepted_cancel_has_no_device_side_effect(tmp_path) -> None:
    """Finish an accepted cancellation without binding or touching the device."""
    graph, components = _android_task_graph(Action(ActionType.DONE))
    _service, repository, run_id = _persist_run(
        tmp_path / "studio.sqlite3",
        graph,
    )
    repository.request_cancel(run_id)
    device = FakeAndroidDevice()
    orchestrator, _artifacts = _orchestrator(
        tmp_path,
        repository,
        components,
        device,
    )
    orchestrator.execute(run_id)
    record = repository.get_run(run_id)
    assert record.result is not None
    assert record.result.status == RunStatus.CANCELLED.value
    assert device.calls == []


@pytest.mark.parametrize(
    ("device", "action", "max_steps", "expected"),
    (
        (
            FakeAndroidDevice(),
            Action(ActionType.KEY, {"code": "home"}),
            1,
            RunStatus.STEP_LIMIT.value,
        ),
        (
            BrokenActionDevice(),
            Action(ActionType.KEY, {"code": "home"}),
            15,
            RunStatus.DEVICE_FAILURE.value,
        ),
    ),
)
def test_step_limit_and_device_failure_are_preserved(
    tmp_path,
    device,
    action,
    max_steps,
    expected,
) -> None:
    """Preserve canonical Android terminal statuses through orchestration."""
    graph, components = _android_task_graph(action, max_steps=max_steps)
    _service, repository, run_id = _persist_run(
        tmp_path / f"{expected}.sqlite3",
        graph,
        owner=f"process-{expected}",
    )
    orchestrator, _artifacts = _orchestrator(
        tmp_path / expected,
        repository,
        components,
        device,
        owner=f"process-{expected}",
    )
    orchestrator.execute(run_id)
    record = repository.get_run(run_id)
    assert record.result is not None
    assert record.result.status == expected


def test_device_busy_and_evidence_preflight_fail_safely(tmp_path) -> None:
    """Fail without device actions when lease or evidence guarantees are absent."""
    graph, components = _android_task_graph(Action(ActionType.DONE))
    _service, repository, busy_run = _persist_run(
        tmp_path / "busy.sqlite3",
        graph,
        owner="process-busy",
    )
    leases = DeviceLeaseRegistry()
    device = FakeAndroidDevice()
    busy, _artifacts = _orchestrator(
        tmp_path / "busy",
        repository,
        components,
        device,
        owner="process-busy",
        leases=leases,
    )
    target_key = busy.execution.profiles.resolve("fake-device").target_key
    with leases.acquire(target_key, "other-run"):
        busy.execute(busy_run)
    busy_record = repository.get_run(busy_run)
    assert busy_record.result is not None
    assert busy_record.result.error_code == "studio.device.target_busy"
    assert device.calls == []

    _service, failed_repo, failed_run = _persist_run(
        tmp_path / "full.sqlite3",
        graph,
        owner="process-full",
    )
    failed_device = FakeAndroidDevice()
    failed, _artifacts = _orchestrator(
        tmp_path / "full",
        failed_repo,
        components,
        failed_device,
        owner="process-full",
        minimum_free_bytes=10**30,
    )
    failed.execute(failed_run)
    failed_record = failed_repo.get_run(failed_run)
    assert failed_record.result is not None
    assert (
        failed_record.result.error_code
        == "studio.run.evidence_capacity_insufficient"
    )
    assert failed_device.calls == []


def test_corrupt_snapshot_and_missing_component_fail_before_device(
    tmp_path,
) -> None:
    """Reject graph-integrity and binding failures before device side effects."""
    graph, components = _android_task_graph(Action(ActionType.DONE))
    corrupt_database = tmp_path / "corrupt.sqlite3"
    _service, corrupt_repository, corrupt_run = _persist_run(
        corrupt_database,
        graph,
        owner="process-corrupt",
    )
    snapshot = corrupt_repository.get_run(corrupt_run).snapshot.model_dump(
        mode="json",
        by_alias=True,
    )
    snapshot["agentGraph"]["policies"]["max_steps"] = 99
    with sqlite3.connect(corrupt_database) as connection:
        connection.execute(
            "UPDATE studio_runs SET snapshot_json = ? WHERE run_id = ?",
            (json.dumps(snapshot), corrupt_run),
        )
    corrupt_device = FakeAndroidDevice()
    corrupt, _artifacts = _orchestrator(
        tmp_path / "corrupt",
        corrupt_repository,
        components,
        corrupt_device,
        owner="process-corrupt",
    )
    corrupt.execute(corrupt_run)
    corrupt_record = corrupt_repository.get_run(corrupt_run)
    assert corrupt_record.result is not None
    assert corrupt_record.result.error_code == (
        "studio.policy.graph_identity_mismatch"
    )
    assert corrupt_device.calls == []

    _service, missing_repository, missing_run = _persist_run(
        tmp_path / "missing.sqlite3",
        graph,
        owner="process-missing",
    )
    missing_components = dict(components)
    missing_components.pop("build_action")
    missing_device = FakeAndroidDevice()
    missing, _artifacts = _orchestrator(
        tmp_path / "missing",
        missing_repository,
        missing_components,
        missing_device,
        owner="process-missing",
    )
    missing.execute(missing_run)
    missing_record = missing_repository.get_run(missing_run)
    assert missing_record.result is not None
    assert missing_record.result.status == RunStatus.FAILURE.value
    assert missing_record.result.error_code
    assert missing_device.calls == []


def test_unknown_worker_error_is_safely_finalized(tmp_path) -> None:
    """Convert unexpected execution failures without leaking diagnostics."""
    graph, _components = _android_task_graph(Action(ActionType.DONE))
    _service, repository, run_id = _persist_run(
        tmp_path / "studio.sqlite3",
        graph,
    )
    events = DurableRunEventService(repository)
    artifacts = LocalStudioRunArtifactStore(
        tmp_path / "managed",
        repository,
        minimum_free_bytes=1,
    )
    debug = StudioRunDebugCapture(artifacts=artifacts, events=events)

    class ExplodingExecution:
        """Execution fake raising an unsafe unexpected diagnostic."""

        def execute(self, record, runtime):
            """Raise a failure containing several security canaries.

            Args:
                record (StudioRunRecordV1): Persisted Run.
                runtime (RuntimeContext): Runtime context.

            Raises:
                RuntimeError: Always, with unsafe diagnostic content.

            Returns:
                None.
            """
            del record, runtime
            raise RuntimeError(
                "token=unknown-secret-canary "
                "emulator-654321 /Users/private/worker.py"
            )

    orchestrator = StudioRunOrchestrator(
        runs=repository,
        events=events,
        execution=ExplodingExecution(),
        debug=debug,
        process_owner_id="process-current",
    )
    orchestrator.execute(run_id)
    record = repository.get_run(run_id)
    assert record.result is not None
    assert record.result.status == RunStatus.FAILURE.value
    serialized = json.dumps(
        record.result.model_dump(mode="json", by_alias=True)
    )
    for canary in (
        "unknown-secret-canary",
        "emulator-654321",
        "/Users/private/worker.py",
    ):
        assert canary not in serialized
    page = repository.query_events(run_id, after=0, limit=100)
    assert sum(item.kind == "run.terminal" for item in page.items) == 1


def test_restart_recovery_finalizes_without_replaying_components(tmp_path) -> None:
    """Mark old-owner Run interrupted and never invoke its device graph."""
    graph, components = _android_task_graph(Action(ActionType.DONE))
    _service, repository, run_id = _persist_run(
        tmp_path / "studio.sqlite3",
        graph,
        owner="process-old",
    )
    device = FakeAndroidDevice()
    orchestrator, _artifacts = _orchestrator(
        tmp_path,
        repository,
        components,
        device,
        owner="process-new",
    )
    assert orchestrator.recover_interrupted() == (run_id,)
    record = repository.get_run(run_id)
    assert record.result is not None
    assert record.result.status == RunStatus.FAILURE.value
    assert record.result.error_code == "studio.run.service_restarted"
    assert device.calls == []


def test_scheduler_is_bounded_and_releases_slot() -> None:
    """Reject a second concurrent submission and accept work after completion."""
    scheduler = LocalThreadRunScheduler(max_workers=1)
    entered = threading.Event()
    release = threading.Event()
    completed: list[str] = []

    def execute(run_id: str) -> None:
        """Block one worker until the test releases its slot.

        Args:
            run_id (str): Submitted identity.

        Raises:
            None.

        Returns:
            None.
        """
        entered.set()
        release.wait(timeout=2)
        completed.append(run_id)

    scheduler.submit("run-a", execute)
    assert entered.wait(timeout=2)
    with pytest.raises(StudioRunDeviceBusyError):
        scheduler.submit("run-b", execute)
    release.set()
    scheduler.shutdown(wait=True)
    assert completed == ["run-a"]


def test_running_cancel_is_cooperative_at_the_next_safe_boundary(tmp_path) -> None:
    """Persist cancellation immediately without claiming an active call was stopped."""
    graph, _components = _android_task_graph(Action(ActionType.DONE))
    source_service, repository, run_id = _persist_run(
        tmp_path / "studio.sqlite3",
        graph,
    )
    events = DurableRunEventService(repository)
    artifacts = LocalStudioRunArtifactStore(
        tmp_path / "managed",
        repository,
        minimum_free_bytes=1,
    )
    debug = StudioRunDebugCapture(artifacts=artifacts, events=events)
    entered = threading.Event()
    release = threading.Event()

    class BlockingExecution:
        """Execution fake representing one non-preemptible active call."""

        def execute(self, record, runtime):
            """Wait for release, then honor the cooperative signal.

            Args:
                record (StudioRunRecordV1): Persisted Run.
                runtime (RuntimeContext): Cancellation-bearing context.

            Raises:
                AssertionError: Cancellation was not propagated.

            Returns:
                RunResult: Canonical cancelled result.
            """
            entered.set()
            release.wait(timeout=3)
            assert runtime.cancellation.is_cancelled()
            return RunResult(
                run_id=record.run_id,
                status=RunStatus.CANCELLED,
                state=AgentState(),
                kernel_status="cancelled",
            )

    orchestrator = StudioRunOrchestrator(
        runs=repository,
        events=events,
        execution=BlockingExecution(),
        debug=debug,
        process_owner_id="process-current",
    )
    cancel_service = StudioRunApplicationService(
        agents=source_service.agents,
        runs=repository,
        events=events,
        process_owner_id="process-current",
        cancel_active=orchestrator.cancel_active,
    )
    worker = threading.Thread(target=orchestrator.execute, args=(run_id,))
    worker.start()
    assert entered.wait(timeout=3)
    cancelling = cancel_service.cancel_run(run_id)
    assert cancelling.lifecycle is StudioRunLifecycle.CANCELLING
    assert worker.is_alive()
    release.set()
    worker.join(timeout=3)
    record = repository.get_run(run_id)
    assert record.result is not None
    assert record.result.status == RunStatus.CANCELLED.value
    assert repository.query_events(run_id, after=0, limit=100).terminal is True


def test_competing_terminal_paths_publish_one_persisted_result_event(
    tmp_path,
) -> None:
    """Keep a deterministic terminal event when two finalizers race."""
    graph, components = _android_task_graph(Action(ActionType.DONE))
    _service, repository, run_id = _persist_run(
        tmp_path / "studio.sqlite3",
        graph,
    )
    orchestrator, _artifacts = _orchestrator(
        tmp_path,
        repository,
        components,
        FakeAndroidDevice(),
    )
    barrier = threading.Barrier(3)
    failures: list[Exception] = []

    def finish(status: RunStatus) -> None:
        """Submit one competing canonical terminal result.

        Args:
            status (RunStatus): Candidate terminal status.

        Raises:
            None: Failures are retained for the parent assertion.

        Returns:
            None.
        """
        barrier.wait(timeout=3)
        try:
            orchestrator._finish(
                run_id,
                RunResult(
                    run_id=run_id,
                    status=status,
                    state=AgentState(),
                    kernel_status=status.value,
                ),
            )
        except Exception as error:
            failures.append(error)

    finishers = [
        threading.Thread(target=finish, args=(RunStatus.SUCCESS,)),
        threading.Thread(target=finish, args=(RunStatus.CANCELLED,)),
    ]
    for thread in finishers:
        thread.start()
    barrier.wait(timeout=3)
    for thread in finishers:
        thread.join(timeout=3)

    assert failures == []
    record = repository.get_run(run_id)
    assert record.result is not None
    page = repository.query_events(run_id, after=0, limit=100)
    terminal_events = [
        item for item in page.items if item.kind == "run.terminal"
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0].payload["result"]["status"] == record.result.status
    assert (
        terminal_events[0].payload["finalHighWaterMark"]
        == terminal_events[0].sequence
    )
