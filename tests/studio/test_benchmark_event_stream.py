"""Stage 5.2C-1 durable Benchmark event page and SSE contracts."""

from __future__ import annotations

import http.client
import json
import socket
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pytest

from zhixing.studio import StudioApplicationService, build_studio_component_catalog
from zhixing.studio.benchmark_errors import (
    StudioBenchmarkIntegrityError,
    StudioBenchmarkStorageError,
    StudioBenchmarkValidationError,
)
from zhixing.studio.benchmark_events import (
    BenchmarkEventNotifier,
    DurableBenchmarkEventService,
)
from zhixing.studio.benchmark_execution import (
    StudioBenchmarkExperimentOrchestrator,
)
from zhixing.studio.benchmark_experiment_models import (
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkEventSource,
)
from zhixing.studio.benchmark_experiment_repository import (
    SQLiteStudioBenchmarkExperimentRepository,
)
from zhixing.studio.benchmark_experiment_service import (
    StudioBenchmarkExperimentApplicationService,
)
from zhixing.studio.benchmark_composition import StudioBenchmarkComposition
from zhixing.studio.httpd import create_http_server

from .test_benchmark_experiment_resource import (
    DeterministicIdentityFactory,
    IncrementingClock,
    _http_request,
    _resource_service,
)
from .test_benchmark_execution_worker import CoreFakeExecution


def _event_service(
    tmp_path: Path,
    *,
    event_commit_hook: Callable[[str], None] | None = None,
    failure_step: str | None = None,
    event_transport_enabled: bool = True,
) -> tuple[
    StudioBenchmarkExperimentApplicationService,
    SQLiteStudioBenchmarkExperimentRepository,
    DurableBenchmarkEventService,
    dict[str, Any],
]:
    """Build one deterministic event-enabled Experiment service.

    Args:
        tmp_path: Temporary workspace root.
        event_commit_hook: Optional observer invoked after notifier delivery.
        failure_step: Optional repository transaction failure checkpoint.
        event_transport_enabled: Truthful public capability projection flag.

    Returns:
        Experiment service, repository, event service, and create payload.
    """
    base, _base_repository, payload = _resource_service(tmp_path)
    notifier = BenchmarkEventNotifier()

    def notify(experiment_id: str) -> None:
        """Wake waiters and forward one optional payload-free observation.

        Args:
            experiment_id: Experiment whose journal advanced.

        Returns:
            None.
        """
        notifier.notify(experiment_id)
        if event_commit_hook is not None:
            event_commit_hook(experiment_id)

    def failure_hook(step: str) -> None:
        """Raise at one configured repository checkpoint.

        Args:
            step: Current stable checkpoint.

        Raises:
            RuntimeError: Configured failure checkpoint was reached.

        Returns:
            None.
        """
        if step == failure_step:
            raise RuntimeError("injected event transaction failure")

    repository = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3",
        failure_hook=failure_hook if failure_step is not None else None,
        event_commit_hook=notify,
    )
    events = DurableBenchmarkEventService(repository, notifier=notifier)
    experiments = StudioBenchmarkExperimentApplicationService(
        definitions=base.definitions,
        repository=repository,
        clock=IncrementingClock(),
        identity_factory=DeterministicIdentityFactory(),
        event_transport_enabled=event_transport_enabled,
    )
    return experiments, repository, events, payload


def _start_event_server(
    experiments: StudioBenchmarkExperimentApplicationService,
    repository: SQLiteStudioBenchmarkExperimentRepository,
    events: DurableBenchmarkEventService,
    *,
    heartbeat: float = 0.05,
    max_connections: int = 8,
) -> tuple[Any, threading.Thread, tuple[str, int]]:
    """Start one loopback HTTP server with complete event transport.

    Args:
        experiments: Durable Experiment application service.
        repository: Shared durable repository.
        events: Shared durable event service.
        heartbeat: Test heartbeat interval.
        max_connections: Benchmark SSE connection limit.

    Returns:
        Server, serving thread, and loopback address.
    """
    definitions = experiments.definitions
    authoring = StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=definitions.agents,
    )
    composition = StudioBenchmarkComposition(
        service=definitions,
        catalog=definitions.catalog,
        profiles=definitions.profiles,
        experiments=experiments,
        events=events,
        repository=repository,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        benchmark_composition=composition,
        sse_heartbeat_seconds=heartbeat,
        sse_write_timeout_seconds=0.25,
        benchmark_sse_max_connections=max_connections,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, (
        "127.0.0.1",
        int(server.server_address[1]),
    )


def _stop_event_server(server: Any, thread: threading.Thread) -> None:
    """Stop one loopback server and wait for bounded handler cleanup.

    Args:
        server: Running HTTP server.
        thread: Serving thread.

    Returns:
        None.
    """
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def _open_sse(
    address: tuple[str, int],
    path: str,
    *,
    last_event_id: str | None = None,
) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
    """Open one raw SSE request for frame-level assertions.

    Args:
        address: Loopback server address.
        path: Event stream request path.
        last_event_id: Optional reconnect cursor header.

    Returns:
        Open HTTP connection and response.
    """
    connection = http.client.HTTPConnection(*address, timeout=2)
    headers = {"Host": "127.0.0.1"}
    if last_event_id is not None:
        headers["Last-Event-ID"] = last_event_id
    connection.request("GET", path, headers=headers)
    return connection, connection.getresponse()


def _read_sse_frame(response: http.client.HTTPResponse) -> bytes:
    """Read one SSE frame through its blank-line delimiter.

    Args:
        response: Open event-stream response.

    Returns:
        Raw frame bytes, including line separators.
    """
    lines: list[bytes] = []
    while True:
        line = response.readline()
        if line == b"":
            break
        lines.append(line)
        if line in {b"\n", b"\r\n"}:
            break
    return b"".join(lines)


def test_event_page_dto_pagination_terminal_and_restart(tmp_path: Path) -> None:
    """Page continuously and retain terminal drain semantics after reopen."""
    service, repository, _events, payload = _event_service(tmp_path)
    created = service.create_experiment(payload).experiment
    first = repository.query_events(created.experiment_id, after=0, limit=1)
    public = first.model_dump(mode="json", by_alias=True)
    assert set(public) == {
        "schemaVersion",
        "experimentId",
        "items",
        "nextCursor",
        "highWaterMark",
        "terminal",
    }
    assert public["nextCursor"] == 1
    assert public["highWaterMark"] == 1
    assert public["terminal"] is False

    terminal = service.cancel_experiment(
        created.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "cancel-event-page",
        },
    )
    assert terminal.event_high_water_mark == 4
    cursor = 0
    sequences: list[int] = []
    while cursor < 4:
        page = repository.query_events(
            created.experiment_id,
            after=cursor,
            limit=1,
        )
        sequences.extend(item.sequence for item in page.items)
        cursor = page.next_cursor
        assert page.terminal is (cursor == 4)
    assert sequences == [1, 2, 3, 4]
    drained = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3"
    ).query_events(created.experiment_id, after=4, limit=10)
    assert drained.items == ()
    assert drained.terminal is True
    with pytest.raises(StudioBenchmarkValidationError):
        repository.query_events(created.experiment_id, after=5, limit=1)
    with pytest.raises(StudioBenchmarkValidationError):
        repository.query_events(created.experiment_id, after=-1, limit=1)
    with pytest.raises(StudioBenchmarkValidationError):
        repository.query_events(created.experiment_id, after=0, limit=501)


def test_event_page_rejects_sequence_and_high_water_corruption(
    tmp_path: Path,
) -> None:
    """Reject gaps and aggregate high-water disagreement as integrity faults."""
    service, repository, _events, payload = _event_service(tmp_path)
    created = service.create_experiment(payload).experiment
    service.cancel_experiment(
        created.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "cancel-corrupt-page",
        },
    )
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        connection.execute(
            "DELETE FROM studio_benchmark_experiment_events "
            "WHERE experiment_id = ? AND sequence = 2",
            (created.experiment_id,),
        )
    with pytest.raises(StudioBenchmarkIntegrityError):
        repository.query_events(created.experiment_id)

    other_path = tmp_path / "other"
    other_path.mkdir()
    other, other_repository, _other_events, other_payload = _event_service(
        other_path
    )
    other_created = other.create_experiment(other_payload).experiment
    with sqlite3.connect(other_path / "studio.sqlite3") as connection:
        connection.execute(
            "UPDATE studio_benchmark_experiments "
            "SET event_high_water_mark = 9 WHERE experiment_id = ?",
            (other_created.experiment_id,),
        )
    with pytest.raises(StudioBenchmarkIntegrityError):
        other_repository.query_events(other_created.experiment_id)


def test_post_commit_notification_and_lost_signal_requery(tmp_path: Path) -> None:
    """Notify once per committed transaction and re-query durable facts."""
    notifications: list[str] = []
    service, repository, events, payload = _event_service(
        tmp_path,
        event_commit_hook=notifications.append,
    )
    created = service.create_experiment(payload).experiment
    result: list[tuple[int, ...]] = []

    def wait() -> None:
        """Wait for the cancellation transaction to advance the journal."""
        page = events.wait_for_events(
            created.experiment_id,
            after=1,
            timeout=1,
        )
        result.append(tuple(item.sequence for item in page.items))

    thread = threading.Thread(target=wait)
    thread.start()
    time.sleep(0.02)
    service.cancel_experiment(
        created.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "cancel-notify",
        },
    )
    thread.join(timeout=2)
    assert result == [(2, 3, 4)]
    assert notifications == [created.experiment_id, created.experiment_id]

    isolated = DurableBenchmarkEventService(
        repository,
        notifier=BenchmarkEventNotifier(),
    )
    started = time.monotonic()
    page = isolated.wait_for_events(
        created.experiment_id,
        after=1,
        timeout=0.02,
    )
    assert time.monotonic() - started < 0.2
    assert tuple(item.sequence for item in page.items) == (2, 3, 4)


def test_rollback_is_silent_and_notifier_failure_keeps_fact(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Never notify rollback and never undo a fact after callback failure."""
    rollback_calls: list[str] = []
    failing, _repository, _events, payload = _event_service(
        tmp_path,
        event_commit_hook=rollback_calls.append,
        failure_step="create.after_event",
    )
    with pytest.raises(StudioBenchmarkStorageError):
        failing.create_experiment(payload)
    assert rollback_calls == []

    safe_path = tmp_path / "safe"
    safe_path.mkdir()

    def broken_notifier(_experiment_id: str) -> None:
        """Raise a canary-bearing callback error after durable commit.

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("super-secret-notifier-canary")

    service, repository, _events, safe_payload = _event_service(
        safe_path,
        event_commit_hook=broken_notifier,
    )
    with caplog.at_level("WARNING"):
        created = service.create_experiment(safe_payload).experiment
    assert repository.query_events(created.experiment_id).high_water_mark == 1
    assert "super-secret-notifier-canary" not in caplog.text


def test_http_event_page_and_truthful_capability(tmp_path: Path) -> None:
    """Expose real event links and stable page validation over HTTP."""
    service, repository, events, payload = _event_service(tmp_path)
    server, thread, address = _start_event_server(
        service,
        repository,
        events,
    )
    try:
        status, created = _http_request(
            address,
            "POST",
            "/studio/benchmark-experiments",
            payload,
        )
        assert status == 202
        resource = created["experiment"]
        experiment_id = resource["experimentId"]
        assert resource["capabilities"]["eventStream"] is True
        assert resource["capabilities"]["replay"] is False
        assert resource["capabilities"]["reports"] is False
        assert resource["links"]["events"].endswith(f"/{experiment_id}/events")
        assert resource["links"]["eventStream"].endswith(
            f"/{experiment_id}/events/stream"
        )

        status, page = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}/events"
            "?after=0&limit=1",
        )
        assert status == 200
        assert page["nextCursor"] == 1
        assert page["items"][0]["kind"] == "experiment.accepted"

        status, invalid = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}/events?after=2",
        )
        assert status == 400
        assert invalid["error"]["code"] == "benchmark.event.cursor_invalid"

        status, missing = _http_request(
            address,
            "GET",
            "/studio/benchmark-experiments/"
            f"experiment-{'f' * 32}/events",
        )
        assert status == 404
        assert missing["error"]["code"] == "benchmark.experiment.not_found"

        with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
            connection.execute(
                "UPDATE studio_benchmark_experiments "
                "SET event_high_water_mark = 9 WHERE experiment_id = ?",
                (experiment_id,),
            )
        status, corrupt = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}/events",
        )
        assert status == 409
        assert corrupt["error"]["code"] == "benchmark.event.journal_corrupt"
        assert str(tmp_path) not in json.dumps(corrupt)
    finally:
        _stop_event_server(server, thread)


def test_sse_backfill_reconnect_terminal_and_cursor_errors(
    tmp_path: Path,
) -> None:
    """Resume without duplicates and close only after terminal drain."""
    service, repository, events, payload = _event_service(tmp_path)
    created = service.create_experiment(payload).experiment
    service.cancel_experiment(
        created.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "cancel-sse-backfill",
        },
    )
    server, thread, address = _start_event_server(
        service,
        repository,
        events,
    )
    path = f"/studio/benchmark-experiments/{created.experiment_id}/events/stream"
    try:
        connection, response = _open_sse(
            address,
            path,
            last_event_id="1",
        )
        assert response.status == 200
        body = response.read()
        connection.close()
        assert body.count(b"event: journal") == 3
        assert b"id: 1\n" not in body
        assert b"id: 2\n" in body
        assert b"id: 3\n" in body
        assert b"id: 4\n" in body
        assert b"experiment.terminal" in body

        mismatch, bad = _open_sse(
            address,
            f"{path}?after=0",
            last_event_id="1",
        )
        assert bad.status == 400
        mismatch.close()
        future, bad_future = _open_sse(
            address,
            f"{path}?after=9",
        )
        assert bad_future.status == 400
        future.close()
    finally:
        _stop_event_server(server, thread)


def test_sse_heartbeat_connection_cap_and_worker_isolation(
    tmp_path: Path,
) -> None:
    """Bound idle streams while durable producer and JSON query continue."""
    service, repository, events, payload = _event_service(tmp_path)
    created = service.create_experiment(payload).experiment
    server, thread, address = _start_event_server(
        service,
        repository,
        events,
        heartbeat=0.03,
        max_connections=1,
    )
    path = (
        f"/studio/benchmark-experiments/{created.experiment_id}"
        "/events/stream?after=1"
    )
    connection: http.client.HTTPConnection | None = None
    try:
        connection, response = _open_sse(address, path)
        assert response.status == 200
        heartbeat = _read_sse_frame(response)
        assert b"event: heartbeat" in heartbeat
        assert b"id:" not in heartbeat
        assert server.benchmark_sse_connections.active == 1

        status, capacity = _http_request(address, "GET", path)
        assert status == 503
        assert (
            capacity["error"]["code"]
            == "benchmark.event.connection_capacity"
        )

        terminal = service.cancel_experiment(
            created.experiment_id,
            {
                "schemaVersion": 1,
                "clientRequestId": "cancel-while-stream-open",
            },
        )
        assert terminal.event_high_water_mark == 4
        status, page = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{created.experiment_id}/events"
            "?after=1",
        )
        assert status == 200
        assert [item["sequence"] for item in page["items"]] == [2, 3, 4]
        body = response.read()
        assert b"id: 4\n" in body
        connection.close()
        connection = None
        deadline = time.monotonic() + 1
        while (
            server.benchmark_sse_connections.active
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert server.benchmark_sse_connections.active == 0
    finally:
        if connection is not None:
            connection.close()
        _stop_event_server(server, thread)


def test_multiple_sse_clients_receive_the_same_terminal_history(
    tmp_path: Path,
) -> None:
    """Serve identical durable facts to independent simultaneous cursors."""
    service, repository, events, payload = _event_service(tmp_path)
    created = service.create_experiment(payload).experiment
    service.cancel_experiment(
        created.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "cancel-multiple-clients",
        },
    )
    server, thread, address = _start_event_server(
        service,
        repository,
        events,
    )
    path = (
        f"/studio/benchmark-experiments/{created.experiment_id}"
        "/events/stream"
    )
    bodies: list[bytes] = []

    def consume() -> None:
        """Consume one complete terminal event stream."""
        connection, response = _open_sse(address, path)
        assert response.status == 200
        bodies.append(response.read())
        connection.close()

    clients = [threading.Thread(target=consume) for _ in range(2)]
    try:
        for client in clients:
            client.start()
        for client in clients:
            client.join(timeout=2)
        assert len(bodies) == 2
        assert bodies[0] == bodies[1]
        assert bodies[0].count(b"event: journal") == 4
    finally:
        _stop_event_server(server, thread)


def test_slow_sse_write_times_out_without_blocking_append_or_query(
    tmp_path: Path,
) -> None:
    """Evict a non-reading client while producer and fast query progress."""
    service, repository, events, payload = _event_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-event-slow-client-owner"
    assert repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=1_810_000_000_000,
    )
    payload_value = {f"field{index}": "x" * 3000 for index in range(10)}
    for sequence in range(1, 121):
        repository.append_runtime_event(
            created.experiment_id,
            process_owner_id=owner,
            event=StudioBenchmarkEventDraftV1(
                event_id=f"benchmark-event-{sequence + 1000:032x}",
                timestamp=1_810_000_000_000 + sequence,
                source=StudioBenchmarkEventSource.CORE,
                source_sequence=sequence,
                kind="core.large_progress",
                payload=payload_value,
            ),
        )
    server, thread, address = _start_event_server(
        service,
        repository,
        events,
        heartbeat=0.03,
        max_connections=1,
    )
    path = (
        f"/studio/benchmark-experiments/{created.experiment_id}"
        "/events/stream?after=3"
    )
    connection = http.client.HTTPConnection(*address, timeout=2)
    try:
        connection.connect()
        assert connection.sock is not None
        connection.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        connection.request("GET", path, headers={"Host": "127.0.0.1"})
        response = connection.getresponse()
        assert response.status == 200
        repository.append_runtime_event(
            created.experiment_id,
            process_owner_id=owner,
            event=StudioBenchmarkEventDraftV1(
                event_id=f"benchmark-event-{'f' * 32}",
                timestamp=1_810_000_000_500,
                source=StudioBenchmarkEventSource.CORE,
                source_sequence=121,
                kind="core.after_slow_client",
            ),
        )
        page = events.query(
            created.experiment_id,
            after=123,
            limit=10,
        )
        assert page.items[0].kind == "core.after_slow_client"
        deadline = time.monotonic() + 2
        while (
            server.benchmark_sse_connections.active
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert server.benchmark_sse_connections.active == 0
    finally:
        connection.close()
        _stop_event_server(server, thread)


def test_unknown_kind_and_secret_canary_are_safe_public_facts(
    tmp_path: Path,
) -> None:
    """Transport an unknown kind while retaining payload sanitization."""
    service, repository, events, payload = _event_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-event-security-owner"
    assert repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=1_800_000_000_000,
    )
    repository.append_runtime_event(
        created.experiment_id,
        process_owner_id=owner,
        event=StudioBenchmarkEventDraftV1(
            event_id=f"benchmark-event-{'a' * 32}",
            timestamp=1_800_000_000_001,
            source=StudioBenchmarkEventSource.CORE,
            source_sequence=1,
            kind="future.vendor.unknown",
            payload={
                "api_key": "super-secret-api-canary",
                "password": "super-secret-password-canary",
                "token": "super-secret-token-canary",
                "prompt_secret": "super-secret-prompt-canary",
                "device_handle": "super-secret-device-canary",
                "safe": "visible",
            },
        ),
    )
    server, thread, address = _start_event_server(
        service,
        repository,
        events,
    )
    try:
        status, page = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{created.experiment_id}"
            "/events?after=3",
        )
        assert status == 200
        assert page["items"][0]["kind"] == "future.vendor.unknown"
        encoded = json.dumps(page)
        assert "super-secret-api-canary" not in encoded
        assert "super-secret-password-canary" not in encoded
        assert "super-secret-token-canary" not in encoded
        assert "super-secret-prompt-canary" not in encoded
        assert "super-secret-device-canary" not in encoded
        assert "visible" in encoded

        connection, response = _open_sse(
            address,
            f"/studio/benchmark-experiments/{created.experiment_id}"
            "/events/stream?after=3",
        )
        assert response.status == 200
        frame = _read_sse_frame(response)
        connection.close()
        assert b"future.vendor.unknown" in frame
        assert b"super-secret" not in frame

        status, invalid = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{created.experiment_id}"
            "/events?after=super-secret-error-canary",
        )
        assert status == 400
        assert "super-secret-error-canary" not in json.dumps(invalid)
    finally:
        _stop_event_server(server, thread)


def test_fake_core_worker_events_page_and_sse_are_continuous(
    tmp_path: Path,
) -> None:
    """Project one fake-device Core execution through both public transports."""
    service, repository, events, payload = _event_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-event-e2e-owner"
    assert repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    StudioBenchmarkExperimentOrchestrator(
        repository=repository,
        execution=CoreFakeExecution(mode="pass"),
        process_owner_id=owner,
        clock=IncrementingClock(created.accepted_at + 10),
    ).execute(created.experiment_id)
    page = repository.query_events(
        created.experiment_id,
        after=0,
        limit=500,
    )
    assert page.terminal is True
    assert [item.sequence for item in page.items] == list(
        range(1, page.high_water_mark + 1)
    )
    assert page.items[-1].kind == "experiment.terminal"
    assert any(item.source.value == "core" for item in page.items)

    server, thread, address = _start_event_server(
        service,
        repository,
        events,
    )
    try:
        connection, response = _open_sse(
            address,
            f"/studio/benchmark-experiments/{created.experiment_id}"
            "/events/stream",
        )
        assert response.status == 200
        body = response.read()
        connection.close()
        assert body.count(b"event: journal") == page.high_water_mark
        for sequence in range(1, page.high_water_mark + 1):
            assert f"id: {sequence}\n".encode() in body
    finally:
        _stop_event_server(server, thread)


def test_server_shutdown_releases_waiters_without_deleting_journal(
    tmp_path: Path,
) -> None:
    """Wake an idle stream on shutdown and preserve its durable backfill."""
    service, repository, events, payload = _event_service(tmp_path)
    created = service.create_experiment(payload).experiment
    server, thread, address = _start_event_server(
        service,
        repository,
        events,
        heartbeat=1,
    )
    connection, response = _open_sse(
        address,
        f"/studio/benchmark-experiments/{created.experiment_id}"
        "/events/stream?after=1",
    )
    assert response.status == 200
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    deadline = time.monotonic() + 1
    while (
        server.benchmark_sse_connections.active
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    connection.close()
    assert server.benchmark_sse_connections.active == 0
    restored = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3"
    ).query_events(created.experiment_id)
    assert restored.high_water_mark == 1
