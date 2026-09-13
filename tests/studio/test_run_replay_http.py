"""Native Run-to-Replay and public HTTP/SSE contract tests."""

from __future__ import annotations

import http.client
import json
import threading
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.runtime.test_android_graph_runtime import FakeAndroidDevice
from zhixing.components import (
    ComponentInvocationTrace,
    LLMInput,
    LLMResult,
    RunEvent,
)
from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.httpd import create_http_server
from zhixing.studio.replay_contracts import ReplayArtifactNotFoundError
from zhixing.studio.replay_models import ReplayEvidenceEnvelope
from zhixing.studio.replay_service import build_default_replay_service
from zhixing.studio.run_artifacts import (
    LocalStudioRunArtifactStore,
    RuntimeArtifactEventAdapter,
)
from zhixing.studio.run_composition import (
    build_default_studio_run_composition,
)
from zhixing.studio.run_debug import StudioRunDebugCapture
from zhixing.studio.run_events import DurableRunEventService
from zhixing.studio.run_execution import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
    ProductionComponentResolverFactory,
)
from zhixing.studio.flow_template_loader import get_flow_template_document
from zhixing.studio.run_models import (
    RunEvidenceAvailability,
    StudioRunEventPageV1,
    StudioRunResultSummaryV1,
)
from zhixing.studio.run_replay import NativeStudioRunReplayFinalizer
from zhixing.studio.run_repository import SQLiteStudioRunRepository
from zhixing.studio.run_service import StudioRunApplicationService

from .test_run_execution import SequentialActionLLM


_CASES = (
    Path(__file__).parents[1]
    / "fixtures"
    / "studio"
    / "run"
    / "native_journal_cases.json"
)
_SAME_SOURCE = (
    Path(__file__).parents[2]
    / "studio"
    / "src"
    / "entities"
    / "run"
    / "model"
    / "fixtures"
    / "live-replay-same-source.json"
)


class IdleRunComposition:
    """Minimal HTTP composition for a deliberately nonterminal Run."""

    def __init__(self, service, artifacts) -> None:
        """Store the protocol-compatible HTTP dependencies.

        Args:
            service (StudioRunApplicationService): Unscheduled Run service.
            artifacts (LocalStudioRunArtifactStore): Managed content store.

        Raises:
            None.

        Returns:
            None.
        """
        self.service = service
        self.artifacts = artifacts

    def shutdown(self, *, wait: bool = True) -> None:
        """Satisfy the HTTP ownership boundary without background workers.

        Args:
            wait (bool): Ignored compatibility flag.

        Raises:
            None.

        Returns:
            None.
        """
        del wait


class SecretBearingLiveObject:
    """Live runtime object whose representation must never be persisted."""

    def __repr__(self) -> str:
        """Return a deliberately unsafe representation for canary scanning.

        Args:
            None.

        Raises:
            None.

        Returns:
            str: Secret-bearing canary representation.
        """
        return "<live-object-canary-secret>"


def _saved_graph(
    database: Path,
) -> tuple[
    SQLiteAgentDocumentRepository,
    str,
    str,
    object,
    ProductionComponentResolverFactory,
]:
    """Save one valid fake-Android AgentGraph revision.

    Args:
        database (Path): Temporary SQLite database.

    Raises:
        ValueError: Graph or authoring contracts are invalid.

    Returns:
        tuple: Agent repository, identities, graph, and resolver factory.
    """
    catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(database)
    authoring = StudioApplicationService(catalog=catalog, repository=agents)
    agent, revision = authoring.create_agent(
        "Native Run fixture",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    assert revision.compile_snapshot.agent_graph is not None
    components = ProductionComponentResolverFactory(
        dependency_provider={"llm": SequentialActionLLM()},
    )
    return (
        agents,
        agent.agent_id,
        revision.revision_id,
        revision.compile_snapshot.agent_graph,
        components,
    )


def _saved_feedback_graph(
    database: Path,
) -> tuple[SQLiteAgentDocumentRepository, str, str]:
    """Save the exact shipped explicit-loop template for HTTP execution.

    Args:
        database (Path): Temporary SQLite database.

    Raises:
        ValueError: Template compilation or persistence is invalid.

    Returns:
        tuple[SQLiteAgentDocumentRepository, str, str]: Repository, Agent, and
        immutable revision identities.
    """
    catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(database)
    authoring = StudioApplicationService(
        catalog=catalog,
        repository=agents,
    )
    agent, revision = authoring.create_agent(
        "Feedback Loop HTTP fixture",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    assert revision.compile_snapshot.status == "valid"
    return agents, agent.agent_id, revision.revision_id


def _create_accepted_run(
    database: Path,
    *,
    request_id: str = "native-fixture",
) -> tuple[SQLiteStudioRunRepository, str]:
    """Create one accepted Run without scheduling it.

    Args:
        database (Path): Temporary SQLite database.
        request_id (str): Stable idempotency identity.

    Raises:
        ValueError: Fixture contracts are invalid.

    Returns:
        tuple[SQLiteStudioRunRepository, str]: Repository and Run identity.
    """
    agents, agent_id, revision_id, _graph, _components = _saved_graph(database)
    repository = SQLiteStudioRunRepository(database)
    events = DurableRunEventService(repository)
    service = StudioRunApplicationService(
        agents=agents,
        runs=repository,
        events=events,
        process_owner_id="native-fixture-owner",
    )
    resource, created = service.create_run(
        {
            "clientRequestId": request_id,
            "agentId": agent_id,
            "revisionId": revision_id,
            "task": {"text": "Observe and finish"},
            "deviceProfileId": "fake-device",
        }
    )
    assert created is True
    return repository, resource.run_id


def test_same_source_fixture_matches_native_journal_projection() -> None:
    """Validate the shared frontend fixture with native backend contracts."""
    raw = json.loads(_SAME_SOURCE.read_text(encoding="utf-8"))
    page = StudioRunEventPageV1.model_validate(raw["journalPage"])
    replay = ReplayEvidenceEnvelope.model_validate(raw["replay"])
    moments, observations, actions = NativeStudioRunReplayFinalizer._moments(
        page.items
    )
    assert moments == replay.moments
    assert observations == replay.observations
    assert actions == replay.actions


@pytest.mark.parametrize(
    "case",
    json.loads(_CASES.read_text(encoding="utf-8"))["cases"],
    ids=lambda item: item["name"],
)
def test_native_replay_preserves_same_source_prefix_and_hidden_prompt(
    tmp_path,
    case,
) -> None:
    """Register terminal outcome variants from one trusted journal source."""
    database = tmp_path / "studio.sqlite3"
    repository, run_id = _create_accepted_run(database)
    live = LocalStudioRunArtifactStore(tmp_path / "managed-live", repository)
    runtime_file = live.runtime_root / run_id / "observations" / "0000.png"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_bytes(b"fake-png")
    events = DurableRunEventService(
        repository,
        runtime_draft_builder=RuntimeArtifactEventAdapter(live).build,
    )
    events.append_runtime(
        run_id,
        RunEvent(
            run_id=run_id,
            sequence=1,
            timestamp=1.0,
            phase="graph_kernel",
            role="zhixing.service.device_observe",
            component="observe",
            kind=case["eventKind"],
            payload={
                "outputs": {
                    "screenshot_artifact": (
                        f"{run_id}/observations/0000.png"
                    ),
                    "width": 1080,
                    "height": 1920,
                    "platform": "android",
                    "device_id": "device-sha256:fixture",
                }
            },
            node_path="observe",
            activation_id="activation-1",
        ),
    )
    hidden = live.write_text(
        run_id,
        kind="sensitive_prompt",
        text="Bearer secret-canary native prompt",
        hidden=True,
    )
    repository.finish_run(
        run_id,
        StudioRunResultSummaryV1(
            status=case["status"],
            kernel_status=case["status"],
        ),
        expected=(repository.get_run(run_id).lifecycle,),
    )
    replay_service = build_default_replay_service(database)
    finalizer = NativeStudioRunReplayFinalizer(
        runs=repository,
        events=repository,
        artifacts=repository,
        live_store=live,
        replay_store=replay_service.artifact_store,
    )
    before = repository.query_events(run_id, after=0, limit=500)
    replay = finalizer.finalize(run_id)
    repeated = finalizer.finalize(run_id)

    assert repeated == replay
    assert replay.result.status == case["status"]
    assert [item.source_sequence for item in replay.moments] == [
        item.sequence for item in before.items
    ]
    assert replay.moments[-1].payload["payload"]["outputs"][
        "screenshot_artifact"
    ].startswith("artifact-")
    assert hidden.artifact_id in {
        item.artifact_id for item in replay.artifacts
    }
    assert replay.availability["prompt"].state == "hidden"
    with pytest.raises(ReplayArtifactNotFoundError):
        replay_service.open_artifact(run_id, hidden.artifact_id)
    bundle = replay_service.export_bundle(run_id)
    with zipfile.ZipFile(bundle) as archive:
        assert f"artifacts/{hidden.artifact_id}" not in archive.namelist()
        assert "secret-canary" not in archive.read("envelope.json").decode()


@pytest.fixture
def run_http_server(
    tmp_path,
) -> Iterator[tuple[tuple[str, int], str, str]]:
    """Run the real Stage 3 HTTP stack against a deterministic fake device.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Raises:
        OSError: Storage or socket setup fails.

    Yields:
        Iterator[tuple]: Address plus saved Agent and revision identities.
    """
    database = tmp_path / "studio.sqlite3"
    agents, agent_id, revision_id, _graph, components = _saved_graph(database)
    catalog = build_studio_component_catalog()
    replay = build_default_replay_service(database)
    authoring = StudioApplicationService(
        catalog=catalog,
        repository=agents,
        replay_service=replay,
    )
    composition = build_default_studio_run_composition(
        database,
        agents=agents,
        replay_service=replay,
        profiles=AndroidDeviceProfileResolver(
            {
                "fake-device": AndroidDeviceProfile(
                    "fake-device",
                    device=FakeAndroidDevice(),
                )
            }
        ),
        components=components,
        enforce_readiness=False,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        run_composition=composition,
        sse_heartbeat_seconds=0.05,
        sse_write_timeout_seconds=2,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            ("127.0.0.1", int(server.server_address[1])),
            agent_id,
            revision_id,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.fixture
def feedback_run_http_server(
    tmp_path,
) -> Iterator[tuple[tuple[str, int], str, str, FakeAndroidDevice]]:
    """Serve the shipped feedback template through the real Run composition.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Raises:
        OSError: Storage or socket setup fails.

    Yields:
        Iterator[tuple]: Address, immutable identities, and fake device evidence.
    """
    database = tmp_path / "feedback-studio.sqlite3"
    agents, agent_id, revision_id = _saved_feedback_graph(database)
    catalog = build_studio_component_catalog()
    replay = build_default_replay_service(database)
    authoring = StudioApplicationService(
        catalog=catalog,
        repository=agents,
        replay_service=replay,
    )
    device = FakeAndroidDevice()
    composition = build_default_studio_run_composition(
        database,
        agents=agents,
        replay_service=replay,
        profiles=AndroidDeviceProfileResolver(
            {
                "fake-device": AndroidDeviceProfile(
                    "fake-device",
                    device=device,
                )
            }
        ),
        components=ProductionComponentResolverFactory(
            dependency_provider={"llm": SequentialActionLLM()},
        ),
        component_catalog=catalog,
        runtime_secrets={"api_key": "fixture", "base_url": "fixture"},
        enforce_readiness=False,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        run_composition=composition,
        sse_heartbeat_seconds=0.05,
        sse_write_timeout_seconds=2,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            ("127.0.0.1", int(server.server_address[1])),
            agent_id,
            revision_id,
            device,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _http_json(
    address: tuple[str, int],
    method: str,
    path: str,
    payload: object | None = None,
) -> tuple[int, dict]:
    """Send one bounded JSON request to a local test server.

    Args:
        address (tuple[str, int]): Host and port.
        method (str): HTTP method.
        path (str): Public API path.
        payload (object | None): Optional JSON body.

    Raises:
        OSError: HTTP transport fails.
        json.JSONDecodeError: Response is not JSON.

    Returns:
        tuple[int, dict]: Status and decoded response.
    """
    connection = http.client.HTTPConnection(*address, timeout=5)
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def _wait_terminal(address: tuple[str, int], run_id: str) -> dict:
    """Wait for both the terminal resource and its final durable journal event.

    Args:
        address (tuple[str, int]): Host and port.
        run_id (str): Stable Run identity.

    Raises:
        AssertionError: Run does not terminate within five seconds.

    Returns:
        dict: Terminal Run resource.
    """
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status, resource = _http_json(
            address,
            "GET",
            f"/api/studio/runs/{run_id}",
        )
        assert status == 200
        if (
            resource["lifecycle"] == "terminal"
            and resource["replayAvailability"] != "not_captured"
        ):
            # Replay visibility precedes the final event append in the worker.
            # Waiting for that event avoids racing a still-increasing cursor.
            cursor = resource["eventHighWaterMark"]
            event_status, page = _http_json(
                address, "GET",
                f"/api/studio/runs/{run_id}/events?after={max(0, cursor - 1)}&limit=1",
            )
            assert event_status == 200
            if page["items"] and page["items"][-1]["kind"] == "run.terminal":
                status, resource = _http_json(address, "GET", f"/api/studio/runs/{run_id}")
                assert status == 200
                return resource
        time.sleep(0.01)
    raise AssertionError("fake Studio Run did not terminate")


def test_run_http_create_retry_events_sse_replay_and_artifact(
    run_http_server,
) -> None:
    """Exercise the public Stage 3 resource, journal, SSE, and artifact flow."""
    address, agent_id, revision_id = run_http_server
    request = {
        "schemaVersion": 1,
        "clientRequestId": "http-native-run",
        "agentId": agent_id,
        "revisionId": revision_id,
        "task": {"text": "Observe and finish"},
        "deviceProfileId": "fake-device",
    }
    status, created = _http_json(
        address,
        "POST",
        "/api/studio/runs",
        request,
    )
    assert status == 202
    assert created["created"] is True
    run_id = created["runId"]
    status, repeated = _http_json(
        address,
        "POST",
        "/api/studio/runs",
        request,
    )
    assert status == 202
    assert repeated["created"] is False
    assert repeated["runId"] == run_id

    terminal = _wait_terminal(address, run_id)
    assert terminal["result"]["status"] == "success"
    assert terminal["replayAvailability"] == "available"
    status, page = _http_json(
        address,
        "GET",
        f"/api/studio/runs/{run_id}/events?after=0&limit=500",
    )
    assert status == 200
    assert page["terminal"] is True
    assert [item["sequence"] for item in page["items"]] == list(
        range(1, page["highWaterMark"] + 1)
    )

    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.request(
            "GET",
            f"/api/studio/runs/{run_id}/events/stream",
            headers={"Last-Event-ID": str(page["highWaterMark"] - 1)},
        )
        response = connection.getresponse()
        body = response.read().decode("utf-8")
    finally:
        connection.close()
    assert response.status == 200
    assert response.getheader("Content-Type").startswith("text/event-stream")
    assert f"id: {page['highWaterMark']}\n" in body
    assert f"id: {page['highWaterMark'] - 1}\n" not in body

    artifacts = {
        artifact
        for item in page["items"]
        for artifact in item.get("payload", {}).get("artifactIds", [])
    }
    if not artifacts:
        artifacts = {
            value
            for item in page["items"]
            for value in json.dumps(item).replace('"', " ").split()
            if value.startswith("artifact-")
        }
    assert artifacts
    artifact_id = sorted(artifacts)[0].rstrip(",}")
    raw = http.client.HTTPConnection(*address, timeout=5)
    try:
        raw.request(
            "GET",
            f"/api/studio/runs/{run_id}/artifacts/{artifact_id}",
        )
        artifact_response = raw.getresponse()
        content = artifact_response.read()
    finally:
        raw.close()
    assert artifact_response.status == 200
    assert content

    status, second = _http_json(
        address,
        "POST",
        "/api/studio/runs",
        {
            **request,
            "clientRequestId": "http-cross-run-owner",
        },
    )
    assert status == 202
    second_run_id = second["runId"]
    _wait_terminal(address, second_run_id)
    status, cross_run = _http_json(
        address,
        "GET",
        f"/api/studio/runs/{second_run_id}/artifacts/{artifact_id}",
    )
    assert status == 404
    assert cross_run["error"]["code"] == "studio.run.artifact_not_found"

    status, replay = _http_json(
        address,
        "GET",
        f"/api/studio/replays/{run_id}",
    )
    assert status == 200
    assert replay["runId"] == run_id
    assert replay["provenance"] == "native_studio_run"
    serialized = json.dumps(
        {"terminal": terminal, "page": page, "replay": replay}
    )
    assert "secret-canary" not in serialized
    assert str(Path.cwd()) not in serialized


def test_feedback_template_http_live_sse_and_native_replay_are_causally_equal(
    feedback_run_http_server,
) -> None:
    """Execute observe/TAP/feedback/observe/DONE across every public Run view.

    Args:
        feedback_run_http_server: Real HTTP composition fixture.

    Raises:
        AssertionError: Live journal, SSE, device calls, or Replay diverge.

    Returns:
        None.
    """
    address, agent_id, revision_id, device = feedback_run_http_server
    status, created = _http_json(
        address,
        "POST",
        "/api/studio/runs",
        {
            "schemaVersion": 1,
            "clientRequestId": "http-feedback-run",
            "agentId": agent_id,
            "revisionId": revision_id,
            "task": {"text": "Tap once, then finish"},
            "deviceProfileId": "fake-device",
        },
    )
    assert status == 202
    terminal = _wait_terminal(address, created["runId"])
    assert terminal["result"]["status"] == "success"
    assert terminal["result"]["interactionCount"] == 1

    status, page = _http_json(
        address,
        "GET",
        f"/api/studio/runs/{created['runId']}/events?after=0&limit=500",
    )
    assert status == 200
    assert page["terminal"] is True
    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.request(
            "GET",
            f"/api/studio/runs/{created['runId']}/events/stream",
            headers={"Last-Event-ID": str(page["highWaterMark"] - 1)},
        )
        response = connection.getresponse()
        sse = response.read().decode("utf-8")
    finally:
        connection.close()
    assert response.status == 200
    assert f"id: {page['highWaterMark']}\n" in sse

    status, replay = _http_json(
        address,
        "GET",
        f"/api/studio/replays/{created['runId']}",
    )
    assert status == 200
    assert [item["sequence"] for item in replay["observations"]] == [0, 1]
    assert [item["actionType"] for item in replay["actions"]] == ["tap", "done"]
    assert [item.get("terminalStatus") for item in replay["actions"]] == [None, "success"]
    assert [call[0] for call in device.calls] == [
        "screenshot",
        "xml",
        "tap",
        "screenshot",
        "xml",
    ]


def test_security_canaries_do_not_cross_any_stage3_surface(tmp_path) -> None:
    """Scan durable, managed, HTTP, SSE, and Replay outputs for canaries."""
    database = tmp_path / "studio.sqlite3"
    repository, run_id = _create_accepted_run(
        database,
        request_id="security-canary-run",
    )
    live = LocalStudioRunArtifactStore(
        tmp_path / "managed-live",
        repository,
        minimum_free_bytes=1,
    )
    events = DurableRunEventService(
        repository,
        runtime_draft_builder=RuntimeArtifactEventAdapter(live).build,
    )
    secret = "stage3-secret-canary"
    serial = "emulator-654321"
    host_path = "/Users/private/stage3-host-path-canary"
    live_repr = "live-object-canary-secret"
    events.append_runtime(
        run_id,
        RunEvent(
            run_id=run_id,
            sequence=1,
            timestamp=1.0,
            phase="graph_kernel",
            role="zhixing.role.reasoning",
            component="fixture",
            kind="complete",
            payload={
                "authorization": secret,
                "device_serial": serial,
                "diagnostic": f"failed at {host_path}",
                "live": SecretBearingLiveObject(),
            },
            node_path="reasoning",
            activation_id="activation-security",
        ),
    )
    debug_capture = StudioRunDebugCapture(artifacts=live, events=events)
    debug_capture.capture(
        ComponentInvocationTrace(
            run_id=run_id,
            node_path="reasoning",
            activation_id="activation-security",
            role="zhixing.role.reasoning",
            component="fixture:reasoner@1.0.0",
            stage="start",
            inputs={"request": LLMInput(prompt=f"Bearer {secret}")},
        )
    )
    debug_capture.capture(
        ComponentInvocationTrace(
            run_id=run_id,
            node_path="reasoning",
            activation_id="activation-security",
            role="zhixing.role.reasoning",
            component="fixture:reasoner@1.0.0",
            stage="complete",
            inputs={"task": "inspect safe evidence"},
            outputs={"result": LLMResult(text="safe model response")},
        )
    )
    visible = live.write_text(
        run_id,
        kind="model_response",
        text=(
            f"authorization: {secret}\n"
            f"device={serial}\npath={host_path}"
        ),
    )
    live.write_text(
        run_id,
        kind="sensitive_prompt",
        text=f"Bearer {secret} on {serial} from {host_path}",
        hidden=True,
    )
    repository.finish_run(
        run_id,
        StudioRunResultSummaryV1(
            status="success",
            kernel_status="success",
        ),
        expected=(repository.get_run(run_id).lifecycle,),
    )
    replay_service = build_default_replay_service(database)
    finalizer = NativeStudioRunReplayFinalizer(
        runs=repository,
        events=repository,
        artifacts=repository,
        live_store=live,
        replay_store=replay_service.artifact_store,
    )
    finalizer.finalize(run_id)
    repository.set_replay_availability(
        run_id,
        RunEvidenceAvailability.AVAILABLE,
    )
    events.append(
        run_id,
        events.service_event(
            kind="run.terminal",
            source="result",
            event_id="service-run-terminal",
            payload={
                "result": {"status": "success"},
                "replayAvailability": "available",
            },
        ),
    )

    agents = SQLiteAgentDocumentRepository(database)
    run_service = StudioRunApplicationService(
        agents=agents,
        runs=repository,
        events=events,
        process_owner_id="security-surface-reader",
    )
    authoring = StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=agents,
        replay_service=replay_service,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        run_composition=IdleRunComposition(run_service, live),
        sse_heartbeat_seconds=0.05,
        sse_write_timeout_seconds=1,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = ("127.0.0.1", int(server.server_address[1]))
    try:
        status, run_json = _http_json(
            address,
            "GET",
            f"/api/studio/runs/{run_id}",
        )
        assert status == 200
        status, events_json = _http_json(
            address,
            "GET",
            f"/api/studio/runs/{run_id}/events?after=0&limit=100",
        )
        assert status == 200
        status, replay_json = _http_json(
            address,
            "GET",
            f"/api/studio/replays/{run_id}",
        )
        assert status == 200
        connection = http.client.HTTPConnection(*address, timeout=5)
        try:
            connection.request(
                "GET",
                f"/api/studio/runs/{run_id}/events/stream",
            )
            response = connection.getresponse()
            sse_bytes = response.read()
        finally:
            connection.close()
        assert response.status == 200
        typed_debug_events = [
            item
            for item in events_json["items"]
            if item["kind"].startswith("component.debug.")
        ]
        assert typed_debug_events
        typed_refs = [
            item["payload"]["evidenceRefs"]
            for item in typed_debug_events
        ]
        assert any(
            refs.get("prompt", {}).get("availability") == "hidden"
            and "artifactId" not in refs["prompt"]
            for refs in typed_refs
        )
        assert any(
            refs.get("modelResponse", {}).get("artifactId", "").startswith(
                "artifact-"
            )
            for refs in typed_refs
        )
        assert b'"evidenceRefs"' in sse_bytes
        artifact_connection = http.client.HTTPConnection(*address, timeout=5)
        try:
            artifact_connection.request(
                "GET",
                (
                    f"/api/studio/runs/{run_id}/artifacts/"
                    f"{visible.artifact_id}"
                ),
            )
            artifact_response = artifact_connection.getresponse()
            artifact_bytes = artifact_response.read()
        finally:
            artifact_connection.close()
        assert artifact_response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    surfaces = [
        json.dumps(run_json).encode(),
        json.dumps(events_json).encode(),
        json.dumps(replay_json).encode(),
        sse_bytes,
        artifact_bytes,
    ]
    surfaces.extend(
        path.read_bytes()
        for path in database.parent.glob(f"{database.name}*")
        if path.is_file()
    )
    surfaces.extend(
        path.read_bytes()
        for root in (live.root, replay_service.artifact_store.root)
        for path in root.rglob("*")
        if path.is_file()
    )
    bundle = replay_service.export_bundle(run_id)
    with zipfile.ZipFile(bundle) as archive:
        surfaces.extend(
            archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        )
    for canary in (secret, serial, host_path, live_repr):
        encoded = canary.encode()
        assert all(encoded not in surface for surface in surfaces)


def test_run_http_cancel_and_identifier_safety(run_http_server) -> None:
    """Keep cancellation idempotent and reject malformed opaque paths."""
    address, agent_id, revision_id = run_http_server
    status, created = _http_json(
        address,
        "POST",
        "/api/studio/runs",
        {
            "schemaVersion": 1,
            "clientRequestId": "http-cancel-run",
            "agentId": agent_id,
            "revisionId": revision_id,
            "task": {"text": "Cancel if still active"},
            "deviceProfileId": "fake-device",
        },
    )
    assert status == 202
    run_id = created["runId"]
    status, first = _http_json(
        address,
        "POST",
        f"/api/studio/runs/{run_id}/cancel",
        {"schemaVersion": 1},
    )
    status_again, second = _http_json(
        address,
        "POST",
        f"/api/studio/runs/{run_id}/cancel",
        {"schemaVersion": 1},
    )
    assert status == status_again == 202
    assert first["runId"] == second["runId"] == run_id
    terminal = _wait_terminal(address, run_id)
    status, after_terminal = _http_json(
        address,
        "POST",
        f"/api/studio/runs/{run_id}/cancel",
        {"schemaVersion": 1},
    )
    assert status == 202
    assert after_terminal == terminal
    status, terminal_page = _http_json(
        address,
        "GET",
        f"/api/studio/runs/{run_id}/events?after=0&limit=100",
    )
    assert status == 200
    assert sum(
        item["kind"] == "run.terminal"
        for item in terminal_page["items"]
    ) == 1

    status, invalid = _http_json(
        address,
        "GET",
        "/api/studio/runs/not-a-run",
    )
    assert status == 400
    assert invalid["error"]["code"] == "studio.run.identifier_invalid"
    status, missing = _http_json(
        address,
        "GET",
        "/api/studio/runs/run-00000000000000000000000000000000",
    )
    assert status == 404
    assert missing["error"]["code"] == "studio.run.not_found"
    status, traversal = _http_json(
        address,
        "GET",
        f"/api/studio/runs/{run_id}/artifacts/%2e%2e",
    )
    assert status == 400
    assert traversal["error"]["code"] == (
        "studio.run.artifact_identifier_invalid"
    )


def test_sse_heartbeat_disconnect_does_not_change_nonterminal_run(
    tmp_path,
) -> None:
    """Emit a heartbeat and cleanly isolate a disconnected live reader."""
    database = tmp_path / "studio.sqlite3"
    agents, agent_id, revision_id, _graph, _components = _saved_graph(database)
    repository = SQLiteStudioRunRepository(database)
    events = DurableRunEventService(repository)
    run_service = StudioRunApplicationService(
        agents=agents,
        runs=repository,
        events=events,
        process_owner_id="idle-owner",
    )
    run, _created = run_service.create_run(
        {
            "clientRequestId": "idle-sse",
            "agentId": agent_id,
            "revisionId": revision_id,
            "task": {"text": "Remain accepted"},
            "deviceProfileId": "fake-device",
        }
    )
    artifacts = LocalStudioRunArtifactStore(
        tmp_path / "live",
        repository,
        minimum_free_bytes=1,
    )
    authoring = StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=agents,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        run_composition=IdleRunComposition(run_service, artifacts),
        sse_heartbeat_seconds=0.05,
        sse_write_timeout_seconds=1,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = ("127.0.0.1", int(server.server_address[1]))
    connection = http.client.HTTPConnection(*address, timeout=2)
    try:
        connection.request(
            "GET",
            f"/api/studio/runs/{run.run_id}/events/stream",
            headers={"Last-Event-ID": "1"},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.readline() == b": heartbeat\n"
    finally:
        connection.close()
    events.append(
        run.run_id,
        events.service_event(
            kind="fixture.after_disconnect",
            event_id="fixture-after-disconnect",
        ),
    )
    assert repository.high_water_mark(run.run_id) == 2
    assert repository.get_run(run.run_id).lifecycle.value == "accepted"
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
