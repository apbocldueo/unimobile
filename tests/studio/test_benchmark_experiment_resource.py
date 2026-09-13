"""Contracts for the durable Stage 5.2A Benchmark Experiment resource."""

from __future__ import annotations

import json
import http.client
import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from zhixing.studio.benchmark_errors import (
    StudioBenchmarkConflictError,
    StudioBenchmarkNotFoundError,
    StudioBenchmarkStorageError,
    StudioBenchmarkValidationError,
)
from zhixing.studio.benchmark_experiment_models import (
    StudioBenchmarkExperimentCreateRequestV1,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkTaskRunLifecycle,
    canonical_snapshot_json,
)
from zhixing.studio.benchmark_experiment_repository import (
    SQLiteStudioBenchmarkExperimentRepository,
)
from zhixing.studio.benchmark_experiment_service import (
    StudioBenchmarkExperimentApplicationService,
)
from zhixing.studio.benchmark_composition import StudioBenchmarkComposition
from zhixing.studio.database import (
    STUDIO_SQLITE_SCHEMA_VERSION,
    migrate_studio_database,
)
from zhixing.studio.run_repository import SQLiteStudioRunRepository
from zhixing.studio import StudioApplicationService, build_studio_component_catalog
from zhixing.studio.httpd import create_http_server

from .test_benchmark_composer import _preview_payload, _preview_service


_CONTRACTS = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "studio"
    / "benchmark"
    / "experiment-resource-contracts.json"
)


class IncrementingClock:
    """Deterministic integer clock for lifecycle assertions."""

    def __init__(self, start: int = 1_700_000_000_000) -> None:
        """Initialize the next returned timestamp.

        Args:
            start: Initial Unix epoch millisecond value.
        """
        self.value = start
        self._lock = threading.Lock()

    def __call__(self) -> int:
        """Return one monotonic deterministic timestamp.

        Returns:
            Next integer millisecond value.
        """
        with self._lock:
            current = self.value
            self.value += 1
            return current


class DeterministicIdentityFactory:
    """Generate valid stable identities without randomness."""

    def __init__(self) -> None:
        """Initialize per-kind counters."""
        self.counts: dict[str, int] = {}

    def __call__(self, kind: str) -> str:
        """Return one deterministic opaque identity.

        Args:
            kind: Supported Experiment resource kind.

        Returns:
            Valid identity with a 32-hex suffix.
        """
        count = self.counts.get(kind, 0) + 1
        self.counts[kind] = count
        return f"{kind}-{count:032x}"


def _resource_service(
    tmp_path: Path,
    *,
    failure_step: str | None = None,
) -> tuple[
    StudioBenchmarkExperimentApplicationService,
    SQLiteStudioBenchmarkExperimentRepository,
    dict[str, Any],
]:
    """Build a complete deterministic Stage 5.2A service fixture.

    Args:
        tmp_path: Temporary workspace root.
        failure_step: Optional repository checkpoint that raises.

    Returns:
        Service, repository, and valid complete create payload.
    """
    definitions, entry_id, task_id, agent_id, revision_id = _preview_service(
        tmp_path
    )
    definition = _preview_payload(
        entry_id,
        task_id,
        agent_id,
        revision_id,
    )
    preview = definitions.preview(definition)

    def failure_hook(step: str) -> None:
        """Raise at one configured repository checkpoint.

        Args:
            step: Current stable checkpoint.

        Raises:
            RuntimeError: The configured checkpoint was reached.
        """
        if step == failure_step:
            raise RuntimeError("injected transaction failure")

    repository = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3",
        failure_hook=failure_hook if failure_step is not None else None,
    )
    service = StudioBenchmarkExperimentApplicationService(
        definitions=definitions,
        repository=repository,
        clock=IncrementingClock(),
        identity_factory=DeterministicIdentityFactory(),
    )
    payload = {
        "schemaVersion": 1,
        "clientRequestId": "experiment-request-1",
        "previewFingerprint": preview.preview_fingerprint,
        "definition": definition,
    }
    return service, repository, payload


def test_create_contract_is_complete_strict_and_camel_case(tmp_path: Path) -> None:
    """Require complete versioned definition and reject unsafe variants."""
    service, _repository, valid = _resource_service(tmp_path)
    parsed = service.parse_create_request(valid)
    public = parsed.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    assert set(public) == {
        "schemaVersion",
        "clientRequestId",
        "previewFingerprint",
        "definition",
    }
    assert "protocol" in public["definition"]
    fixtures = json.loads(_CONTRACTS.read_text(encoding="utf-8"))
    for invalid in fixtures["invalidRequests"]:
        with pytest.raises(StudioBenchmarkValidationError):
            service.parse_create_request(invalid)
    non_finite = json.loads(json.dumps(valid))
    non_finite["definition"]["protocol"]["seed"] = float("nan")
    with pytest.raises(StudioBenchmarkValidationError):
        service.parse_create_request(non_finite)


def test_shared_schema_five_migration_is_additive_and_reentrant(
    tmp_path: Path,
) -> None:
    """Create schema 5 once and keep legacy repositories able to reopen it."""
    database = tmp_path / "studio.sqlite3"
    migrate_studio_database(database)
    SQLiteStudioRunRepository(database)
    SQLiteStudioBenchmarkExperimentRepository(database)
    migrate_studio_database(database)
    with sqlite3.connect(database) as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM studio_schema_migrations ORDER BY version"
            )
        ]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert versions == list(range(1, STUDIO_SQLITE_SCHEMA_VERSION + 1))
    assert {
        "studio_benchmark_experiments",
        "studio_benchmark_task_runs",
        "studio_benchmark_experiment_events",
    } <= tables

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO studio_schema_migrations(version, applied_at) "
            "VALUES (?, 0)",
            (STUDIO_SQLITE_SCHEMA_VERSION + 1,),
        )
    with pytest.raises(RuntimeError, match="newer"):
        migrate_studio_database(database)


def _simulate_historical_schema(database: Path, version: int) -> None:
    """Reduce an additive fixture database to one historical schema version.

    Args:
        database: Existing schema-4 database.
        version: Historical version in 1..3.

    Raises:
        sqlite3.Error: Fixture transformation fails.
    """
    drop_groups = {
        4: (
            "studio_benchmark_experiment_events",
            "studio_benchmark_task_runs",
            "studio_benchmark_experiments",
        ),
        3: (
            "studio_run_artifacts",
            "studio_run_events",
            "studio_runs",
        ),
        2: (
            "studio_replay_artifacts",
            "studio_replay_moments",
            "studio_replays",
        ),
    }
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        for schema_version in range(4, version, -1):
            for table in drop_groups[schema_version]:
                connection.execute(f"DROP TABLE {table}")
        connection.execute(
            "DELETE FROM studio_schema_migrations WHERE version > ?",
            (version,),
        )


@pytest.mark.parametrize("historical_version", [1, 2, 3])
def test_shared_migration_upgrades_each_historical_schema(
    tmp_path: Path,
    historical_version: int,
) -> None:
    """Upgrade schema 1, 2, or 3 through the same monotonic boundary."""
    database = tmp_path / f"studio-v{historical_version}.sqlite3"
    migrate_studio_database(database)
    _simulate_historical_schema(database, historical_version)
    migrate_studio_database(database)
    with sqlite3.connect(database) as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM studio_schema_migrations ORDER BY version"
            )
        ]
    assert versions == list(range(1, STUDIO_SQLITE_SCHEMA_VERSION + 1))


def test_shared_migration_is_safe_under_concurrent_reentry(
    tmp_path: Path,
) -> None:
    """Serialize two schema-3 upgrades without duplicate migration records."""
    database = tmp_path / "studio-concurrent.sqlite3"
    migrate_studio_database(database)
    _simulate_historical_schema(database, 3)
    barrier = threading.Barrier(3)
    failures: list[Exception] = []

    def migrate() -> None:
        """Race one migration invocation."""
        barrier.wait(timeout=3)
        try:
            migrate_studio_database(database)
        except Exception as error:
            failures.append(error)

    threads = [threading.Thread(target=migrate) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=3)
    for thread in threads:
        thread.join(timeout=3)
    assert failures == []
    with sqlite3.connect(database) as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM studio_schema_migrations ORDER BY version"
            )
        ]
    assert versions == list(range(1, STUDIO_SQLITE_SCHEMA_VERSION + 1))


@pytest.mark.parametrize(
    "failure_step",
    [
        "create.after_experiment",
        "create.after_task_run",
        "create.after_event",
    ],
)
def test_create_transaction_failure_leaves_no_partial_aggregate(
    tmp_path: Path,
    failure_step: str,
) -> None:
    """Roll back every resource when any create checkpoint fails."""
    service, repository, payload = _resource_service(
        tmp_path,
        failure_step=failure_step,
    )
    with pytest.raises(StudioBenchmarkStorageError):
        service.create_experiment(payload)
    assert (
        repository.find_by_client_request_id(payload["clientRequestId"]) is None
    )
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        counts = [
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "studio_benchmark_experiments",
                "studio_benchmark_task_runs",
                "studio_benchmark_experiment_events",
            )
        ]
    assert counts == [0, 0, 0]


def test_create_retry_drift_conflict_and_concurrency(tmp_path: Path) -> None:
    """Preserve durable retries while rejecting first-create definition drift."""
    service, repository, payload = _resource_service(tmp_path)
    first = service.create_experiment(payload)
    assert first.created is True
    assert (
        first.experiment.lifecycle
        is StudioBenchmarkExperimentLifecycle.ACCEPTED
    )
    assert first.experiment.event_high_water_mark == 1
    assert first.experiment.capabilities.executes is False
    assert "event" not in json.dumps(
        first.experiment.links.model_dump(by_alias=True)
    ).lower()

    package_task = (
        tmp_path / "catalog" / "fixture" / "tasks" / "test.json"
    )
    changed = json.loads(package_task.read_text(encoding="utf-8"))
    changed[0]["instruction"] = "Package drift after durable create"
    package_task.write_text(json.dumps(changed), encoding="utf-8")
    retry = service.create_experiment(payload)
    assert retry.created is False
    assert retry.experiment.experiment_id == first.experiment.experiment_id
    assert len(repository.list_events(first.experiment.experiment_id)) == 1

    conflicting = json.loads(json.dumps(payload))
    conflicting["definition"]["protocol"]["seed"] = 99
    with pytest.raises(StudioBenchmarkConflictError) as captured:
        service.create_experiment(conflicting)
    assert captured.value.code == "benchmark.experiment.idempotency_conflict"

    fresh_payload = json.loads(json.dumps(payload))
    fresh_payload["clientRequestId"] = "experiment-request-after-drift"
    with pytest.raises(StudioBenchmarkConflictError) as captured:
        service.create_experiment(fresh_payload)
    assert captured.value.code == "benchmark.experiment.definition_conflict"

    concurrent_root = tmp_path / "concurrent"
    concurrent, concurrent_repo, concurrent_payload = _resource_service(
        concurrent_root
    )
    barrier = threading.Barrier(3)
    results: list[tuple[str, bool]] = []
    failures: list[Exception] = []

    def create() -> None:
        """Race one identical first create."""
        barrier.wait(timeout=3)
        try:
            result = concurrent.create_experiment(concurrent_payload)
            results.append(
                (result.experiment.experiment_id, result.created)
            )
        except Exception as error:
            failures.append(error)

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=3)
    for thread in threads:
        thread.join(timeout=3)
    assert failures == []
    assert len({identity for identity, _created in results}) == 1
    assert sorted(created for _identity, created in results) == [False, True]
    assert len(concurrent_repo.list_events(results[0][0])) == 1


def test_first_create_prepares_definition_exactly_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use one compiler/defaulting pass for a new durable Experiment."""
    service, _repository, payload = _resource_service(tmp_path)
    calls = 0
    original = service.definitions.catalog.compile_split

    def counted_compile_split(*args: Any, **kwargs: Any) -> Any:
        """Count and delegate one formal Package compilation."""
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        service.definitions.catalog,
        "compile_split",
        counted_compile_split,
    )
    created = service.create_experiment(payload)
    assert created.created is True
    assert calls == 1
    retried = service.create_experiment(payload)
    assert retried.created is False
    assert calls == 1


@pytest.mark.parametrize(
    "failure_step",
    [
        "cancel.after_request_event",
        "cancel.after_task_run",
        "cancel.after_terminal_event",
        "cancel.after_experiment",
    ],
)
def test_cancel_transaction_failure_rolls_back(
    tmp_path: Path,
    failure_step: str,
) -> None:
    """Keep accepted facts unchanged when accepted-cancel cannot commit."""
    service, _repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload)
    failing_repository = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3",
        failure_hook=lambda step: (
            (_ for _ in ()).throw(RuntimeError("cancel failure"))
            if step == failure_step
            else None
        ),
    )
    failing = StudioBenchmarkExperimentApplicationService(
        definitions=service.definitions,
        repository=failing_repository,
        clock=IncrementingClock(1_800_000_000_000),
    )
    with pytest.raises(StudioBenchmarkStorageError):
        failing.cancel_experiment(
            created.experiment.experiment_id,
            {
                "schemaVersion": 1,
                "clientRequestId": "cancel-request-1",
            },
        )
    unchanged = service.get_experiment(created.experiment.experiment_id)
    assert unchanged.lifecycle is StudioBenchmarkExperimentLifecycle.ACCEPTED
    assert unchanged.event_high_water_mark == 1
    task = service.list_task_runs(created.experiment.experiment_id).items[0]
    assert task.lifecycle is StudioBenchmarkTaskRunLifecycle.SCHEDULED


def test_restart_query_cursor_and_accepted_cancel_are_durable(
    tmp_path: Path,
) -> None:
    """Persist exact snapshot and atomically close accepted work on cancel."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    page = service.list_task_runs(created.experiment_id, limit=1)
    assert len(page.items) == 1
    assert page.next_cursor is None
    with pytest.raises(StudioBenchmarkValidationError):
        service.list_task_runs(
            created.experiment_id,
            limit=1,
            cursor="tampered",
        )
    task = service.get_task_run(
        created.experiment_id,
        page.items[0].task_run_id,
    )
    assert task.planned_entry_id == created.definition.schedule[0].planned_entry_id

    restarted = StudioBenchmarkExperimentApplicationService(
        definitions=service.definitions,
        repository=SQLiteStudioBenchmarkExperimentRepository(
            tmp_path / "studio.sqlite3"
        ),
        clock=IncrementingClock(1_900_000_000_000),
    )
    restored = restarted.get_experiment(created.experiment_id)
    assert (
        restored.definition.model_dump(mode="json")
        == created.definition.model_dump(mode="json")
    )
    cancelled = restarted.cancel_experiment(
        created.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "cancel-request-1",
        },
    )
    assert cancelled.lifecycle is StudioBenchmarkExperimentLifecycle.TERMINAL
    assert cancelled.terminal_reason.value == "cancelled"
    assert cancelled.event_high_water_mark == 4
    terminal_task = restarted.list_task_runs(created.experiment_id).items[0]
    assert terminal_task.lifecycle is StudioBenchmarkTaskRunLifecycle.TERMINAL
    assert terminal_task.terminal_reason.value == "cancelled_before_start"
    assert terminal_task.outcome_availability.value == "not_produced"
    assert [item.sequence for item in repository.list_events(created.experiment_id)] == [
        1,
        2,
        3,
        4,
    ]
    repeated = restarted.cancel_experiment(
        created.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "another-cancel-request",
        },
    )
    assert repeated.event_high_water_mark == 4
    assert len(repository.list_events(created.experiment_id)) == 4


def test_concurrent_cancel_has_one_terminal_event_and_identity_constraints(
    tmp_path: Path,
) -> None:
    """Resolve cancel races into one immutable contiguous terminal journal."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    barrier = threading.Barrier(3)
    results: list[int] = []
    failures: list[Exception] = []

    def cancel(index: int) -> None:
        """Race one accepted-only cancellation."""
        barrier.wait(timeout=3)
        try:
            result = service.cancel_experiment(
                created.experiment_id,
                {
                    "schemaVersion": 1,
                    "clientRequestId": f"cancel-race-{index}",
                },
            )
            results.append(result.event_high_water_mark)
        except Exception as error:
            failures.append(error)

    threads = [
        threading.Thread(target=cancel, args=(index,))
        for index in range(2)
    ]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=3)
    for thread in threads:
        thread.join(timeout=3)
    assert failures == []
    assert results == [4, 4]
    events = repository.list_events(created.experiment_id)
    assert sum(item.kind == "experiment.terminal" for item in events) == 1
    assert [item.sequence for item in events] == [1, 2, 3, 4]
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        row = connection.execute(
            "SELECT event_id, fingerprint, envelope_json, created_at "
            "FROM studio_benchmark_experiment_events "
            "WHERE experiment_id = ? AND sequence = 1",
            (created.experiment_id,),
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO studio_benchmark_experiment_events "
                "(experiment_id, sequence, event_id, fingerprint, "
                "envelope_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    created.experiment_id,
                    5,
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                ),
            )


def test_task_run_cursor_is_stable_scoped_and_cross_resource_safe(
    tmp_path: Path,
) -> None:
    """Page by order/identity and reject cursor or TaskRun scope confusion."""
    service, _repository, payload = _resource_service(tmp_path)
    first = service.create_experiment(payload).experiment
    original = service.list_task_runs(first.experiment_id).items[0]
    second_task = original.model_copy(
        update={
            "task_run_id": "task-run-" + "f" * 32,
            "planned_entry_id": "planned-entry-pagination-fixture",
            "order": 1,
        }
    )
    task_json = json.dumps(
        second_task.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        connection.execute(
            """
            INSERT INTO studio_benchmark_task_runs (
                task_run_id, experiment_id, planned_entry_id, schedule_order,
                agent_id, revision_id, task_id, repeat_index, derived_seed,
                lifecycle_state, terminal_reason, outcome_availability,
                task_run_json, created_at, updated_at, terminal_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                second_task.task_run_id,
                second_task.experiment_id,
                second_task.planned_entry_id,
                second_task.order,
                second_task.agent_id,
                second_task.revision_id,
                second_task.task_id,
                second_task.repeat,
                second_task.derived_seed,
                second_task.lifecycle.value,
                None,
                second_task.outcome_availability.value,
                task_json,
                second_task.created_at,
                second_task.updated_at,
                None,
            ),
        )
    page_one = service.list_task_runs(first.experiment_id, limit=1)
    assert [item.order for item in page_one.items] == [0]
    assert page_one.next_cursor is not None
    page_two = service.list_task_runs(
        first.experiment_id,
        limit=1,
        cursor=page_one.next_cursor,
    )
    assert [item.order for item in page_two.items] == [1]
    assert page_two.next_cursor is None

    other_payload = json.loads(json.dumps(payload))
    other_payload["clientRequestId"] = "experiment-request-other"
    other = service.create_experiment(other_payload).experiment
    with pytest.raises(StudioBenchmarkValidationError):
        service.list_task_runs(
            other.experiment_id,
            limit=1,
            cursor=page_one.next_cursor,
        )
    with pytest.raises(StudioBenchmarkNotFoundError) as captured:
        service.get_task_run(other.experiment_id, original.task_run_id)
    assert captured.value.code == "benchmark.task_run.not_found"


def test_snapshot_limit_is_measured_before_write(tmp_path: Path) -> None:
    """Reject a canonical snapshot larger than the 2 MiB inline bound."""
    service, _repository, payload = _resource_service(tmp_path)
    request = StudioBenchmarkExperimentCreateRequestV1.model_validate(payload)
    snapshot, _tasks, _accepted_at, _experiment_id = service._build_snapshot(
        request
    )
    first_agent = snapshot.agent_snapshots[0].model_copy(
        update={"agent_graph": {"payload": "x" * (2 * 1024 * 1024)}}
    )
    oversized = snapshot.model_copy(
        update={"agent_snapshots": (first_agent,)}
    )
    with pytest.raises(ValueError, match="too large"):
        canonical_snapshot_json(oversized)


def _http_request(
    address: tuple[str, int],
    method: str,
    path: str,
    payload: object | None = None,
    *,
    host: str = "127.0.0.1",
    origin: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Send one JSON request to a local Stage 5.2A server.

    Args:
        address: Loopback host and port.
        method: HTTP method.
        path: Public API path.
        payload: Optional JSON-compatible body.
        host: Explicit Host header value.
        origin: Optional browser Origin header.

    Raises:
        OSError: HTTP transport fails.
        json.JSONDecodeError: Response is not JSON.

    Returns:
        HTTP status and parsed JSON body.
    """
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Host": host}
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body))
    if origin is not None:
        headers["Origin"] = origin
    connection = http.client.HTTPConnection(*address, timeout=5)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    parsed = json.loads(response.read().decode("utf-8"))
    status = response.status
    connection.close()
    return status, parsed


def _start_experiment_http_server(
    experiments: StudioBenchmarkExperimentApplicationService,
) -> tuple[Any, threading.Thread, tuple[str, int]]:
    """Start one loopback HTTP server around an Experiment service.

    Args:
        experiments: Fully composed Stage 5.2A application service.

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
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        benchmark_composition=composition,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, (
        "127.0.0.1",
        int(server.server_address[1]),
    )


def _stop_experiment_http_server(
    server: Any,
    thread: threading.Thread,
) -> None:
    """Stop and close one loopback Experiment HTTP server.

    Args:
        server: Running Studio HTTP server.
        thread: Thread serving the HTTP loop.

    Returns:
        None.
    """
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_experiment_http_create_query_task_and_cancel(tmp_path: Path) -> None:
    """Expose only implemented durable resource links over safe HTTP."""
    experiments, _repository, payload = _resource_service(tmp_path)
    definitions = experiments.definitions
    component_catalog = build_studio_component_catalog()
    authoring = StudioApplicationService(
        catalog=component_catalog,
        repository=definitions.agents,
    )
    composition = StudioBenchmarkComposition(
        service=definitions,
        catalog=definitions.catalog,
        profiles=definitions.profiles,
        experiments=experiments,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        benchmark_composition=composition,
    )
    assert server.run_composition is None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = ("127.0.0.1", int(server.server_address[1]))
    try:
        status, created = _http_request(
            address,
            "POST",
            "/api/studio/benchmark-experiments",
            payload,
            origin="http://localhost:5173",
        )
        assert status == 202
        assert created["schemaVersion"] == 1
        assert created["created"] is True
        resource = created["experiment"]
        experiment_id = resource["experimentId"]
        assert resource["capabilities"] == {
            "executes": False,
            "cancelAccepted": True,
            "cancelActive": False,
            "eventStream": False,
            "replay": False,
            "reports": False,
        }
        serialized_links = json.dumps(resource["links"]).lower()
        assert "events" not in serialized_links
        assert "replay" not in serialized_links
        assert "report" not in serialized_links

        status, retry = _http_request(
            address,
            "POST",
            "/studio/benchmark-experiments",
            payload,
        )
        assert status == 202
        assert retry["created"] is False
        assert retry["experiment"]["experimentId"] == experiment_id

        status, fetched = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}",
        )
        assert status == 200
        assert fetched["definition"] == resource["definition"]

        status, page = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}/task-runs?limit=1",
        )
        assert status == 200
        task_run_id = page["items"][0]["taskRunId"]
        status, task = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}"
            f"/task-runs/{task_run_id}",
        )
        assert status == 200
        assert task["experimentId"] == experiment_id

        status, cancelled = _http_request(
            address,
            "POST",
            f"/studio/benchmark-experiments/{experiment_id}/cancel",
            {
                "schemaVersion": 1,
                "clientRequestId": "cancel-http-1",
            },
        )
        assert status == 202
        assert cancelled["lifecycle"] == "terminal"
        assert cancelled["terminalReason"] == "cancelled"
        assert "cancel" not in cancelled["links"]

        status, invalid = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}"
            "/task-runs?cursor=tampered",
        )
        assert status == 400
        assert invalid["error"]["code"] == "benchmark.task_run.cursor_invalid"
        assert str(tmp_path) not in json.dumps(invalid)

        status, forbidden = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}",
            host="attacker.example",
        )
        assert status == 403
        assert forbidden["error"]["code"] == "studio.http.forbidden"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_http_restart_idempotency_drift_and_cancel_acceptance(
    tmp_path: Path,
) -> None:
    """Preserve one aggregate across HTTP races, drift, restart, and cancel."""
    experiments, repository, payload = _resource_service(tmp_path)
    server, thread, address = _start_experiment_http_server(experiments)
    experiment_id = ""
    definition_snapshot: dict[str, Any] = {}
    try:
        status, preview = _http_request(
            address,
            "POST",
            "/studio/benchmark-experiments/preview",
            payload["definition"],
        )
        assert status == 200
        assert preview["previewFingerprint"] == payload["previewFingerprint"]

        barrier = threading.Barrier(3)
        responses: list[tuple[int, dict[str, Any]]] = []

        def create() -> None:
            """Race one complete create request through HTTP."""
            barrier.wait(timeout=3)
            responses.append(
                _http_request(
                    address,
                    "POST",
                    "/studio/benchmark-experiments",
                    payload,
                )
            )

        creators = [threading.Thread(target=create) for _ in range(2)]
        for creator in creators:
            creator.start()
        barrier.wait(timeout=3)
        for creator in creators:
            creator.join(timeout=3)
        assert [status for status, _body in responses] == [202, 202]
        assert sorted(body["created"] for _status, body in responses) == [
            False,
            True,
        ]
        identities = {
            body["experiment"]["experimentId"]
            for _status, body in responses
        }
        assert len(identities) == 1
        experiment_id = identities.pop()
        definition_snapshot = responses[0][1]["experiment"]["definition"]
        assert len(repository.list_events(experiment_id)) == 1
    finally:
        _stop_experiment_http_server(server, thread)

    package_task = (
        tmp_path / "catalog" / "fixture" / "tasks" / "test.json"
    )
    changed = json.loads(package_task.read_text(encoding="utf-8"))
    changed[0]["instruction"] = "Package drift before HTTP restart"
    package_task.write_text(json.dumps(changed), encoding="utf-8")

    restarted = StudioBenchmarkExperimentApplicationService(
        definitions=experiments.definitions,
        repository=SQLiteStudioBenchmarkExperimentRepository(
            tmp_path / "studio.sqlite3"
        ),
        clock=IncrementingClock(1_950_000_000_000),
    )
    server, thread, address = _start_experiment_http_server(restarted)
    try:
        status, retry = _http_request(
            address,
            "POST",
            "/studio/benchmark-experiments",
            payload,
        )
        assert status == 202
        assert retry["created"] is False
        assert retry["experiment"]["experimentId"] == experiment_id

        status, fetched = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}",
        )
        assert status == 200
        assert fetched["definition"] == definition_snapshot

        conflicting = json.loads(json.dumps(payload))
        conflicting["definition"]["protocol"]["seed"] = 5
        status, conflict = _http_request(
            address,
            "POST",
            "/studio/benchmark-experiments",
            conflicting,
        )
        assert status == 409
        assert (
            conflict["error"]["code"]
            == "benchmark.experiment.idempotency_conflict"
        )

        first_after_drift = json.loads(json.dumps(payload))
        first_after_drift["clientRequestId"] = "new-request-after-drift"
        status, drift = _http_request(
            address,
            "POST",
            "/studio/benchmark-experiments",
            first_after_drift,
        )
        assert status == 409
        assert drift["error"]["code"] == "benchmark.experiment.definition_conflict"

        status, page = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}/task-runs?limit=1",
        )
        assert status == 200
        assert page["items"][0]["lifecycle"] == "scheduled"
        assert page.get("nextCursor") is None

        status, cancelled = _http_request(
            address,
            "POST",
            f"/studio/benchmark-experiments/{experiment_id}/cancel",
            {
                "schemaVersion": 1,
                "clientRequestId": "http-restart-cancel",
            },
        )
        assert status == 202
        assert cancelled["lifecycle"] == "terminal"
        assert cancelled["terminalReason"] == "cancelled"
        assert cancelled["eventHighWaterMark"] == 4

        status, terminal_page = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}/task-runs",
        )
        assert status == 200
        terminal_task = terminal_page["items"][0]
        assert terminal_task["terminalReason"] == "cancelled_before_start"
        assert terminal_task["outcomeAvailability"] == "not_produced"

        status, repeated = _http_request(
            address,
            "POST",
            f"/studio/benchmark-experiments/{experiment_id}/cancel",
            {
                "schemaVersion": 1,
                "clientRequestId": "http-restart-cancel-repeat",
            },
        )
        assert status == 202
        assert repeated["eventHighWaterMark"] == 4
        assert len(repository.list_events(experiment_id)) == 4
    finally:
        _stop_experiment_http_server(server, thread)
