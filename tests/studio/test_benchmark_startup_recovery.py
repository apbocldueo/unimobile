"""Stage 5.2C-3 conservative Benchmark startup recovery contract tests."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from tests.studio.test_benchmark_event_stream import (
    _event_service,
    _open_sse,
    _start_event_server,
    _stop_event_server,
)
from tests.studio.test_benchmark_experiment_resource import _resource_service
from tests.studio.test_benchmark_publication_replay import (
    _publisher,
    _ready_core_result,
)
from zhixing.studio import benchmark_composition as composition_module
from zhixing.studio import benchmark_recovery as recovery_module
from zhixing.studio.benchmark_composition import (
    build_default_studio_benchmark_composition,
)
from zhixing.studio.benchmark_errors import (
    StudioBenchmarkConflictError,
    StudioBenchmarkIntegrityError,
    StudioBenchmarkRecoveryOwnershipError,
    StudioBenchmarkRecoveryUnsupportedError,
    StudioBenchmarkStorageError,
)
from zhixing.studio.benchmark_experiment_models import (
    StudioBenchmarkAvailability,
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkEventSource,
    StudioBenchmarkExperimentCancellationV1,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkExperimentTerminalReason,
    StudioBenchmarkRecoveryDecision,
    StudioBenchmarkTaskRunLifecycle,
    StudioBenchmarkTaskRunTerminalReason,
)
from zhixing.studio.benchmark_experiment_repository import (
    SQLiteStudioBenchmarkExperimentRepository,
)
from zhixing.studio.benchmark_experiment_protocols import (
    StudioBenchmarkExperimentAggregate,
)
from zhixing.studio.benchmark_recovery import (
    LocalBenchmarkRecoveryOwnership,
    StudioBenchmarkStartupRecovery,
)


OLD_OWNER = "benchmark-process-old-owner"
NEW_OWNER = "benchmark-process-new-owner"


def _create_experiment(
    service: Any,
    payload: dict[str, Any],
    *,
    suffix: str,
) -> Any:
    """Create one distinct Experiment from a reusable definition.

    Args:
        service: Deterministic Experiment application service.
        payload: Complete valid create payload.
        suffix: Stable idempotency suffix.

    Returns:
        Created Experiment record.
    """
    request = deepcopy(payload)
    request["clientRequestId"] = f"experiment-recovery-{suffix}"
    return service.create_experiment(request).experiment


def _claim(
    repository: SQLiteStudioBenchmarkExperimentRepository,
    experiment_id: str,
    *,
    owner: str = OLD_OWNER,
    timestamp: int = 10,
) -> Any:
    """Enroll and claim one Experiment into side-effect-free preflight.

    Args:
        repository: Durable Experiment repository.
        experiment_id: Experiment to claim.
        owner: Stale worker owner identity.
        timestamp: Claim timestamp.

    Returns:
        Starting aggregate with one preparing TaskRun.
    """
    assert repository.enroll_accepted_experiment(
        experiment_id,
        process_owner_id=owner,
    )
    return repository.claim_experiment(
        experiment_id,
        process_owner_id=owner,
        timestamp=timestamp,
    )


def _run(
    repository: SQLiteStudioBenchmarkExperimentRepository,
    experiment_id: str,
    *,
    owner: str = OLD_OWNER,
) -> Any:
    """Advance one claimed Experiment to the device-side-effect boundary.

    Args:
        repository: Durable Experiment repository.
        experiment_id: Experiment to run.
        owner: Stale worker owner identity.

    Returns:
        Running aggregate.
    """
    claimed = _claim(repository, experiment_id, owner=owner)
    task = claimed.task_runs[0]
    return repository.transition_execution(
        experiment_id,
        task.task_run_id,
        process_owner_id=owner,
        experiment_lifecycle=StudioBenchmarkExperimentLifecycle.RUNNING,
        task_lifecycle=StudioBenchmarkTaskRunLifecycle.RUNNING,
        timestamp=11,
        event=StudioBenchmarkEventDraftV1(
            event_id=f"benchmark-event-{'a' * 32}",
            timestamp=11,
            source=StudioBenchmarkEventSource.WORKER,
            kind="worker.execution_started",
            task_run_id=task.task_run_id,
        ),
    )


def _finalizing_without_result(
    repository: SQLiteStudioBenchmarkExperimentRepository,
    experiment_id: str,
    *,
    reason: StudioBenchmarkTaskRunTerminalReason = (
        StudioBenchmarkTaskRunTerminalReason.FAILED
    ),
) -> Any:
    """Persist one finalizing aggregate without an immutable TaskResult.

    Args:
        repository: Durable Experiment repository.
        experiment_id: Experiment to close after preflight.
        reason: Committed TaskRun service reason.

    Returns:
        Finalizing Experiment aggregate.
    """
    claimed = _claim(repository, experiment_id)
    task = claimed.task_runs[0]
    repository.finish_task_without_result(
        experiment_id,
        task.task_run_id,
        process_owner_id=OLD_OWNER,
        terminal_reason=reason,
        timestamp=12,
        error_code="fixture.preflight_failed",
    )
    return _aggregate(repository, experiment_id)


def _first_candidate(
    repository: SQLiteStudioBenchmarkExperimentRepository,
    *,
    owner: str = NEW_OWNER,
) -> Any:
    """Return the sole stale recovery candidate.

    Args:
        repository: Durable Experiment repository.
        owner: Current owner excluded from the scan.

    Raises:
        AssertionError: The fixture does not contain exactly one candidate.

    Returns:
        One typed recovery candidate.
    """
    page = repository.list_recovery_candidates(
        process_owner_id=owner,
        limit=100,
    )
    assert len(page.items) == 1
    return page.items[0]


def _aggregate(
    repository: SQLiteStudioBenchmarkExperimentRepository,
    experiment_id: str,
) -> StudioBenchmarkExperimentAggregate:
    """Read one coherent single-Task fixture through public repository methods.

    Args:
        repository: Durable Experiment repository.
        experiment_id: Owning Experiment identity.

    Raises:
        AssertionError: The Stage 5.2 fixture does not have one TaskRun.

    Returns:
        Coherent aggregate snapshot for assertions.
    """
    page = repository.list_task_runs(experiment_id, limit=100)
    assert page.next_cursor is None
    assert len(page.items) == 1
    return StudioBenchmarkExperimentAggregate(
        experiment=repository.get_experiment(experiment_id),
        task_runs=page.items,
    )


class NoCallPublisher:
    """Publisher spy that fails if finalize-only recovery invokes it."""

    def __init__(self) -> None:
        """Create a zero-call publication spy."""
        self.calls: list[tuple[str, str, int]] = []

    def publish(
        self,
        experiment_id: str,
        task_run_id: str,
        *,
        timestamp: int,
    ) -> Any:
        """Reject unexpected publication.

        Args:
            experiment_id: Owning Experiment identity.
            task_run_id: Terminal TaskRun identity.
            timestamp: Publication timestamp.

        Raises:
            AssertionError: Always; this branch must not publish.

        Returns:
            Never returns.
        """
        self.calls.append((experiment_id, task_run_id, timestamp))
        raise AssertionError("finalize-only recovery must not publish")


class FailingPublisher:
    """Publisher spy emulating a crash after the recovery decision commit."""

    def __init__(self) -> None:
        """Create an empty call log."""
        self.calls: list[tuple[str, str, int]] = []

    def publish(
        self,
        experiment_id: str,
        task_run_id: str,
        *,
        timestamp: int,
    ) -> Any:
        """Record the attempt and emulate abrupt publication failure.

        Args:
            experiment_id: Owning Experiment identity.
            task_run_id: Terminal TaskRun identity.
            timestamp: Publication timestamp.

        Raises:
            RuntimeError: Always, after the decision is durable.

        Returns:
            Never returns.
        """
        self.calls.append((experiment_id, task_run_id, timestamp))
        raise RuntimeError("simulated process crash before publication commit")


def test_recovery_candidates_are_bounded_safe_and_exclude_noops(
    tmp_path: Path,
) -> None:
    """Page stale states deterministically without leaking operational values."""
    service, repository, payload = _resource_service(tmp_path)
    accepted = _create_experiment(service, payload, suffix="accepted")
    repository.enroll_accepted_experiment(
        accepted.experiment_id,
        process_owner_id=OLD_OWNER,
    )
    starting = _create_experiment(service, payload, suffix="starting")
    _claim(repository, starting.experiment_id)
    running = _create_experiment(service, payload, suffix="running")
    _run(repository, running.experiment_id)
    cancelling = _create_experiment(service, payload, suffix="cancelling")
    _run(repository, cancelling.experiment_id)
    repository.request_cancellation(
        cancelling.experiment_id,
        StudioBenchmarkExperimentCancellationV1(
            client_request_id="cancel-recovery-fixture",
            requested_at=20,
        ),
    )
    finalizing = _create_experiment(service, payload, suffix="finalizing")
    _finalizing_without_result(repository, finalizing.experiment_id)
    terminal = _create_experiment(service, payload, suffix="terminal")
    repository.request_cancellation(
        terminal.experiment_id,
        StudioBenchmarkExperimentCancellationV1(
            client_request_id="cancel-terminal-fixture",
            requested_at=21,
        ),
    )
    current = _create_experiment(service, payload, suffix="current")
    repository.enroll_accepted_experiment(
        current.experiment_id,
        process_owner_id=NEW_OWNER,
    )

    first = repository.list_recovery_candidates(
        process_owner_id=NEW_OWNER,
        limit=2,
    )
    second = repository.list_recovery_candidates(
        process_owner_id=NEW_OWNER,
        limit=100,
        cursor=first.next_cursor,
    )
    candidates = first.items + second.items
    assert [item.previous_lifecycle for item in candidates] == [
        StudioBenchmarkExperimentLifecycle.ACCEPTED,
        StudioBenchmarkExperimentLifecycle.STARTING,
        StudioBenchmarkExperimentLifecycle.RUNNING,
        StudioBenchmarkExperimentLifecycle.CANCELLING,
        StudioBenchmarkExperimentLifecycle.FINALIZING,
    ]
    assert terminal.experiment_id not in {
        item.experiment_id for item in candidates
    }
    assert current.experiment_id not in {
        item.experiment_id for item in candidates
    }
    serialized = json.dumps(
        [item.model_dump(mode="json", by_alias=True) for item in candidates]
    )
    assert OLD_OWNER not in serialized
    assert NEW_OWNER not in serialized
    assert str(tmp_path) not in serialized
    assert "serial-must-not-leak" not in serialized


@pytest.mark.parametrize(
    "starting",
    [False, True],
    ids=["accepted", "starting"],
)
def test_requeue_preserves_identity_and_resets_only_preflight(
    tmp_path: Path,
    starting: bool,
) -> None:
    """Requeue safe work atomically and keep the original immutable schedule."""
    service, repository, payload = _resource_service(tmp_path)
    experiment = _create_experiment(service, payload, suffix="requeue")
    if starting:
        before = _claim(repository, experiment.experiment_id)
    else:
        repository.enroll_accepted_experiment(
            experiment.experiment_id,
            process_owner_id=OLD_OWNER,
        )
        before = _aggregate(repository, experiment.experiment_id)
    candidate = _first_candidate(repository)
    recovered = repository.recover_requeue(
        candidate,
        process_owner_id=NEW_OWNER,
        timestamp=30,
    )
    repeated = repository.recover_requeue(
        candidate,
        process_owner_id=NEW_OWNER,
        timestamp=31,
    )

    assert recovered.experiment.experiment_id == before.experiment.experiment_id
    assert recovered.experiment.definition == before.experiment.definition
    assert recovered.experiment.lifecycle.value == "accepted"
    assert recovered.experiment.process_owner_id == NEW_OWNER
    assert repeated == recovered
    task = recovered.task_runs[0]
    assert task.task_run_id == before.task_runs[0].task_run_id
    assert task.lifecycle is StudioBenchmarkTaskRunLifecycle.SCHEDULED
    assert task.process_owner_id == ""
    assert task.result_availability is (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    events = repository.list_events(experiment.experiment_id)
    assert [event.kind for event in events].count("recovery.requeued") == 1
    claimed_again = repository.claim_experiment(
        experiment.experiment_id,
        process_owner_id=NEW_OWNER,
        timestamp=32,
    )
    assert claimed_again.experiment.lifecycle.value == "starting"


@pytest.mark.parametrize("cancelling", [False, True], ids=["running", "cancelling"])
def test_uncertain_work_is_interrupted_without_execution_and_old_owner_is_stale(
    tmp_path: Path,
    cancelling: bool,
) -> None:
    """Terminalize uncertain work once and reject every late old-worker write."""
    service, repository, payload = _resource_service(tmp_path)
    experiment = _create_experiment(service, payload, suffix="interrupt")
    running = _run(repository, experiment.experiment_id)
    task = running.task_runs[0]
    if cancelling:
        repository.request_cancellation(
            experiment.experiment_id,
            StudioBenchmarkExperimentCancellationV1(
                client_request_id="cancel-active-recovery",
                requested_at=20,
            ),
        )
    candidate = _first_candidate(repository)
    prior = candidate.prior_event_high_water_mark
    recovered = StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id=NEW_OWNER,
        publisher=NoCallPublisher(),
        clock=lambda: 40,
    ).recover()

    assert recovered.interrupted == 1
    aggregate = _aggregate(repository, experiment.experiment_id)
    assert aggregate.experiment.lifecycle.value == "terminal"
    assert aggregate.experiment.terminal_reason.value == "interrupted"
    assert aggregate.task_runs[0].terminal_reason.value == "interrupted"
    if cancelling:
        assert aggregate.experiment.cancellation is not None
    events = repository.list_events(experiment.experiment_id)
    assert [event.kind for event in events[prior:]] == [
        "recovery.interrupted",
        "task_run.terminal",
        "experiment.terminal",
    ]
    page_one = repository.query_events(
        experiment.experiment_id,
        after=prior,
        limit=1,
    )
    page_two = repository.query_events(
        experiment.experiment_id,
        after=page_one.next_cursor,
        limit=10,
    )
    assert [event.kind for event in page_one.items + page_two.items] == [
        "recovery.interrupted",
        "task_run.terminal",
        "experiment.terminal",
    ]
    assert page_two.terminal is True
    assert events[-1].kind == "experiment.terminal"
    with pytest.raises(StudioBenchmarkConflictError):
        repository.transition_execution(
            experiment.experiment_id,
            task.task_run_id,
            process_owner_id=OLD_OWNER,
            experiment_lifecycle=(
                StudioBenchmarkExperimentLifecycle.RUNNING
            ),
            task_lifecycle=StudioBenchmarkTaskRunLifecycle.RUNNING,
            timestamp=41,
            event=StudioBenchmarkEventDraftV1(
                event_id=f"benchmark-event-{'b' * 32}",
                timestamp=41,
                kind="late.worker.write",
                task_run_id=task.task_run_id,
            ),
        )


def test_recovery_events_are_available_through_sse_reconnect(
    tmp_path: Path,
) -> None:
    """Backfill the atomic interruption suffix through the existing C1 route."""
    service, repository, events, payload = _event_service(tmp_path)
    experiment = _create_experiment(service, payload, suffix="sse")
    _run(repository, experiment.experiment_id)
    candidate = _first_candidate(repository)
    StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id=NEW_OWNER,
        publisher=NoCallPublisher(),
        clock=lambda: 45,
    ).recover()
    server, thread, address = _start_event_server(
        service,
        repository,
        events,
    )
    path = (
        f"/studio/benchmark-experiments/{experiment.experiment_id}"
        "/events/stream"
    )
    try:
        connection, response = _open_sse(
            address,
            path,
            last_event_id=str(candidate.prior_event_high_water_mark),
        )
        assert response.status == 200
        body = response.read()
        connection.close()
        assert body.count(b"event: journal") == 3
        assert b"recovery.interrupted" in body
        assert b"task_run.terminal" in body
        assert b"experiment.terminal" in body
        assert OLD_OWNER.encode() not in body
        assert str(tmp_path).encode() not in body
    finally:
        _stop_event_server(server, thread)


def test_requeue_crash_window_transfers_same_work_without_duplicate_schedule(
    tmp_path: Path,
) -> None:
    """Recover a pre-wake crash under a new owner without recreating work."""
    service, repository, payload = _resource_service(tmp_path)
    experiment = _create_experiment(service, payload, suffix="requeue-crash")
    repository.enroll_accepted_experiment(
        experiment.experiment_id,
        process_owner_id=OLD_OWNER,
    )
    first = StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id="benchmark-process-recovery-one",
        publisher=NoCallPublisher(),
        clock=lambda: 46,
    )
    assert first.recover().requeued == 1
    after_first = _aggregate(repository, experiment.experiment_id)
    first_events = repository.list_events(experiment.experiment_id)
    assert first.recover().scanned == 0
    assert repository.list_events(experiment.experiment_id) == first_events

    second_owner = "benchmark-process-recovery-two"
    second = StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id=second_owner,
        publisher=NoCallPublisher(),
        clock=lambda: 47,
    )
    assert second.recover().requeued == 1
    after_second = _aggregate(repository, experiment.experiment_id)
    events = repository.list_events(experiment.experiment_id)
    assert after_second.experiment.definition == after_first.experiment.definition
    assert after_second.task_runs[0].task_run_id == (
        after_first.task_runs[0].task_run_id
    )
    assert [event.kind for event in events].count("experiment.accepted") == 1
    assert [event.kind for event in events].count("recovery.requeued") == 2
    claimed = repository.claim_experiment(
        experiment.experiment_id,
        process_owner_id=second_owner,
        timestamp=48,
    )
    assert claimed.experiment.lifecycle.value == "starting"
    assert [
        event.kind for event in repository.list_events(
            experiment.experiment_id
        )
    ].count("experiment.starting") == 1


def test_requeue_notifies_only_after_successful_commit(tmp_path: Path) -> None:
    """Deliver one payload-free waiter notification after durable requeue."""
    service, base_repository, payload = _resource_service(tmp_path)
    experiment = _create_experiment(service, payload, suffix="notify")
    base_repository.enroll_accepted_experiment(
        experiment.experiment_id,
        process_owner_id=OLD_OWNER,
    )
    notifications: list[str] = []
    repository = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3",
        event_commit_hook=notifications.append,
    )
    repository.recover_requeue(
        _first_candidate(repository),
        process_owner_id=NEW_OWNER,
        timestamp=49,
    )
    assert notifications == [experiment.experiment_id]
    assert repository.list_events(experiment.experiment_id)[-1].kind == (
        "recovery.requeued"
    )


@pytest.mark.parametrize(
    ("task_reason", "experiment_reason"),
    [
        (
            StudioBenchmarkTaskRunTerminalReason.FAILED,
            StudioBenchmarkExperimentTerminalReason.FAILED,
        ),
        (
            StudioBenchmarkTaskRunTerminalReason.CANCELLED,
            StudioBenchmarkExperimentTerminalReason.CANCELLED,
        ),
        (
            StudioBenchmarkTaskRunTerminalReason.INTERRUPTED,
            StudioBenchmarkExperimentTerminalReason.INTERRUPTED,
        ),
    ],
)
def test_no_result_finalizing_recovers_without_publication(
    tmp_path: Path,
    task_reason: StudioBenchmarkTaskRunTerminalReason,
    experiment_reason: StudioBenchmarkExperimentTerminalReason,
) -> None:
    """Finalize missing-result work from committed TaskRun service facts only."""
    service, repository, payload = _resource_service(tmp_path)
    experiment = _create_experiment(service, payload, suffix="no-result")
    _finalizing_without_result(
        repository,
        experiment.experiment_id,
        reason=task_reason,
    )
    publisher = NoCallPublisher()
    summary = StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id=NEW_OWNER,
        publisher=publisher,
        clock=lambda: 50,
    ).recover()

    aggregate = _aggregate(repository, experiment.experiment_id)
    assert summary.finalize_only == 1
    assert publisher.calls == []
    assert aggregate.experiment.lifecycle.value == "terminal"
    assert aggregate.experiment.terminal_reason is experiment_reason
    assert aggregate.task_runs[0].result is None
    expected_availability = (
        StudioBenchmarkAvailability.FAILED
        if task_reason is StudioBenchmarkTaskRunTerminalReason.FAILED
        else StudioBenchmarkAvailability.NOT_PRODUCED
    )
    assert (
        aggregate.task_runs[0].result_availability
        is expected_availability
    )
    assert [event.kind for event in repository.list_events(
        experiment.experiment_id
    )][-2:] == ["recovery.finalize_only", "experiment.terminal"]


def test_publication_only_restart_reuses_one_recovery_input(
    tmp_path: Path,
) -> None:
    """Keep the publication journal high-water stable across a crashed retry."""
    _service, repository, suite, task = _ready_core_result(tmp_path)
    preparer, publications, _artifacts, durable_publisher = _publisher(
        tmp_path,
        repository,
    )
    preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )
    candidate = _first_candidate(repository)
    with pytest.raises(StudioBenchmarkConflictError):
        repository.claim_finalizing_recovery(
            candidate,
            process_owner_id=NEW_OWNER,
            decision=StudioBenchmarkRecoveryDecision.FINALIZE_ONLY,
            timestamp=59,
        )
    failing = FailingPublisher()
    first = StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id="benchmark-process-first-recovery",
        publisher=failing,
        clock=lambda: 60,
    )
    with pytest.raises(RuntimeError, match="simulated process crash"):
        first.recover()
    after_failure = repository.get_experiment(task.experiment_id)
    first_events = repository.list_events(task.experiment_id)
    assert after_failure.lifecycle.value == "finalizing"
    assert first_events[-1].kind == "recovery.publication_only"
    first_high_water = after_failure.event_high_water_mark

    class RecordingPublisher:
        """Publisher wrapper recording immutable input before real publication."""

        def __init__(self) -> None:
            """Create an empty observed-input log."""
            self.high_water_marks: list[int] = []

        def publish(
            self,
            experiment_id: str,
            task_run_id: str,
            *,
            timestamp: int,
        ) -> Any:
            """Record stable input and delegate to the durable C2 publisher.

            Args:
                experiment_id: Owning Experiment identity.
                task_run_id: Terminal TaskRun identity.
                timestamp: Publication timestamp.

            Returns:
                Coordinated durable publication record.
            """
            self.high_water_marks.append(
                repository.get_experiment(
                    experiment_id
                ).event_high_water_mark
            )
            return durable_publisher.publish(
                experiment_id,
                task_run_id,
                timestamp=timestamp,
            )

    completing = RecordingPublisher()
    summary = StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id="benchmark-process-second-recovery",
        publisher=completing,
        clock=lambda: 61,
    ).recover()
    final = repository.get_experiment(task.experiment_id)
    events = repository.list_events(task.experiment_id)

    assert summary.publication_only == 1
    assert completing.high_water_marks == [first_high_water]
    assert publications.get_publication(task.experiment_id) is not None
    assert [event.kind for event in events].count(
        "recovery.publication_only"
    ) == 1
    assert final.lifecycle.value == "terminal"
    assert events[-1].kind == "experiment.terminal"


def test_committed_publication_is_not_republished_on_startup(
    tmp_path: Path,
) -> None:
    """Finalize after coordinated publication without duplicating Replay facts."""
    _service, repository, suite, task = _ready_core_result(tmp_path)
    preparer, publications, _artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    preparer.prepare(
        suite,
        planned_task_run_id=task.task_run_id,
        definition_snapshot=repository.get_experiment(
            suite.experiment_id
        ).definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        prepared_at=13,
    )
    committed = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=14,
    )
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        replay_count = connection.execute(
            "SELECT COUNT(*) FROM studio_replays"
        ).fetchone()[0]
        replay_moment_count = connection.execute(
            "SELECT COUNT(*) FROM studio_replay_moments"
        ).fetchone()[0]
    before_events = repository.list_events(suite.experiment_id)
    no_call = NoCallPublisher()
    summary = StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id=NEW_OWNER,
        publisher=no_call,
        clock=lambda: 70,
    ).recover()

    after = publications.get_publication(suite.experiment_id)
    events = repository.list_events(suite.experiment_id)
    assert summary.finalize_only == 1
    assert no_call.calls == []
    assert after == committed
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_replays"
        ).fetchone()[0] == replay_count
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_replay_moments"
        ).fetchone()[0] == replay_moment_count
    assert repository.get_experiment(
        suite.experiment_id
    ).lifecycle.value == "terminal"
    assert [event.kind for event in events[len(before_events):]] == [
        "recovery.finalize_only",
        "experiment.terminal",
    ]


def test_missing_publication_staging_commits_failure_then_finalizes(
    tmp_path: Path,
) -> None:
    """Use the C2 publisher's bounded failure facts without changing result."""
    _service, repository, suite, task = _ready_core_result(tmp_path)
    _preparer, publications, _artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    original_result = repository.get_task_run(
        suite.experiment_id,
        task.task_run_id,
    ).result
    summary = StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id=NEW_OWNER,
        publisher=publisher,
        clock=lambda: 75,
    ).recover()

    publication = publications.get_publication(suite.experiment_id)
    restored = repository.get_task_run(
        suite.experiment_id,
        task.task_run_id,
    )
    assert summary.publication_only == 1
    assert publication is not None
    assert publication.preparation_availability == "failed"
    assert publication.report_availability == "failed"
    assert publication.replay_availability == "failed"
    assert restored.result == original_result
    assert restored.result_availability.value == "available"
    assert repository.get_experiment(
        suite.experiment_id
    ).terminal_reason.value == "completed"
    assert repository.list_events(suite.experiment_id)[-1].kind == (
        "experiment.terminal"
    )


def test_committed_failed_publication_is_preserved_without_retry(
    tmp_path: Path,
) -> None:
    """Treat an existing failed publication as an immutable auditable attempt."""
    _service, repository, suite, task = _ready_core_result(tmp_path)
    _preparer, publications, _artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    failed = publisher.publish(
        suite.experiment_id,
        task.task_run_id,
        timestamp=75,
    )
    assert failed.preparation_availability == "failed"
    no_call = NoCallPublisher()
    summary = StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id=NEW_OWNER,
        publisher=no_call,
        clock=lambda: 76,
    ).recover()

    assert summary.finalize_only == 1
    assert no_call.calls == []
    assert publications.get_publication(suite.experiment_id) == failed
    assert repository.get_experiment(
        suite.experiment_id
    ).lifecycle.value == "terminal"


def test_finalizing_recovery_preserves_result_and_cancellation_facts(
    tmp_path: Path,
) -> None:
    """Keep a committed PASS result beside a later cancellation request."""
    _service, repository, suite, task = _ready_core_result(
        tmp_path,
        terminal_reason=StudioBenchmarkTaskRunTerminalReason.CANCELLED,
    )
    repository.request_cancellation(
        suite.experiment_id,
        StudioBenchmarkExperimentCancellationV1(
            client_request_id="cancel-after-result",
            requested_at=13,
        ),
    )
    _preparer, _publications, _artifacts, publisher = _publisher(
        tmp_path,
        repository,
    )
    StudioBenchmarkStartupRecovery(
        repository=repository,
        process_owner_id=NEW_OWNER,
        publisher=publisher,
        clock=lambda: 76,
    ).recover()

    experiment = repository.get_experiment(suite.experiment_id)
    restored = repository.get_task_run(
        suite.experiment_id,
        task.task_run_id,
    )
    assert experiment.terminal_reason is (
        StudioBenchmarkExperimentTerminalReason.CANCELLED
    )
    assert experiment.cancellation is not None
    assert restored.result is not None
    assert restored.benchmark_outcome is not None
    assert restored.result_availability.value == "available"


@pytest.mark.parametrize(
    "failure_step",
    [
        "recovery.requeue.after_transition",
        "recovery.interrupt.after_terminal",
        "recovery.finalizing.after_claim",
    ],
)
def test_recovery_failure_rolls_back_before_notifying(
    tmp_path: Path,
    failure_step: str,
) -> None:
    """Expose neither partial recovery facts nor waiter notifications."""
    notifications: list[str] = []
    service, base_repository, payload = _resource_service(tmp_path)
    experiment = _create_experiment(service, payload, suffix="rollback")
    if "requeue" in failure_step:
        base_repository.enroll_accepted_experiment(
            experiment.experiment_id,
            process_owner_id=OLD_OWNER,
        )
    elif "interrupt" in failure_step:
        _run(base_repository, experiment.experiment_id)
    else:
        _finalizing_without_result(
            base_repository,
            experiment.experiment_id,
        )
    before = _aggregate(base_repository, experiment.experiment_id)
    before_events = base_repository.list_events(experiment.experiment_id)

    def fail(step: str) -> None:
        """Raise at the requested transactional checkpoint.

        Args:
            step: Current recovery checkpoint.

        Raises:
            RuntimeError: The configured checkpoint was reached.
        """
        if step == failure_step:
            raise RuntimeError("injected recovery rollback")

    repository = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3",
        failure_hook=fail,
        event_commit_hook=notifications.append,
    )
    candidate = _first_candidate(repository)
    with pytest.raises(StudioBenchmarkStorageError):
        if "requeue" in failure_step:
            repository.recover_requeue(
                candidate,
                process_owner_id=NEW_OWNER,
                timestamp=80,
            )
        elif "interrupt" in failure_step:
            repository.recover_interrupt(candidate, timestamp=80)
        else:
            repository.claim_finalizing_recovery(
                candidate,
                process_owner_id=NEW_OWNER,
                decision=StudioBenchmarkRecoveryDecision.FINALIZE_ONLY,
                timestamp=80,
            )
    assert _aggregate(base_repository, experiment.experiment_id) == before
    assert base_repository.list_events(experiment.experiment_id) == before_events
    assert notifications == []


def test_local_ownership_contends_releases_and_reacquires_after_exit(
    tmp_path: Path,
) -> None:
    """Use OS-released workspace ownership without liveness timeouts."""
    database = tmp_path / "studio.sqlite3"
    first = LocalBenchmarkRecoveryOwnership.acquire(database)
    with pytest.raises(StudioBenchmarkRecoveryOwnershipError):
        LocalBenchmarkRecoveryOwnership.acquire(database)
    first.close()
    second = LocalBenchmarkRecoveryOwnership.acquire(database)
    second.close()

    if os.name != "posix":
        pytest.skip("abnormal process-exit fixture currently targets POSIX")
    code = (
        "from zhixing.studio.benchmark_recovery import "
        "LocalBenchmarkRecoveryOwnership as O\n"
        "import sys, time\n"
        "lock = O.acquire(sys.argv[1])\n"
        "print('ready', flush=True)\n"
        "time.sleep(30)\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(database)],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(StudioBenchmarkRecoveryOwnershipError):
            LocalBenchmarkRecoveryOwnership.acquire(database)
    finally:
        child.terminate()
        child.wait(timeout=10)
    recovered = LocalBenchmarkRecoveryOwnership.acquire(database)
    recovered.close()


def test_local_ownership_fails_explicitly_on_unsupported_platform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject platforms without a safe OS-released lock primitive."""
    monkeypatch.setattr(recovery_module.os, "name", "unsupported")
    with pytest.raises(StudioBenchmarkRecoveryUnsupportedError) as error:
        LocalBenchmarkRecoveryOwnership.acquire(tmp_path / "studio.sqlite3")
    assert str(tmp_path) not in error.value.message


def test_definition_only_composition_does_not_acquire_recovery_ownership(
    tmp_path: Path,
) -> None:
    """Keep pure Catalog/Composer startup independent from recovery scanning."""
    definitions, _repository, _payload = _resource_service(tmp_path)
    composition = build_default_studio_benchmark_composition(
        tmp_path,
        agents=definitions.definitions.agents,
        profiles=definitions.definitions.profiles,
        contract_catalog=definitions.definitions.contract_catalog,
        sources=(),
        database_path=None,
    )
    try:
        assert composition.repository is None
        assert composition.recovery is None
        assert composition.recovery_ownership is None
        assert composition.scheduler is None
        assert composition.authoring is None
        assert composition.authoring_repository is None
        assert composition.authoring_content is None
    finally:
        composition.shutdown()


def test_executable_composition_recovers_before_one_scheduler_wake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recover accepted work before exposing one scheduler wake."""
    definitions, repository, payload = _resource_service(tmp_path)
    experiment = _create_experiment(
        definitions,
        payload,
        suffix="composition-requeue",
    )
    repository.enroll_accepted_experiment(
        experiment.experiment_id,
        process_owner_id=OLD_OWNER,
    )

    class RecordingScheduler:
        """Scheduler spy proving startup recovery precedes notification."""

        def __init__(self, **dependencies: Any) -> None:
            """Record construction after recovery.

            Args:
                dependencies: Existing scheduler dependencies.
            """
            self.dependencies = dependencies
            self.wake_calls = 0
            self.shutdown_calls: list[bool] = []
            current = dependencies["repository"].get_experiment(
                experiment.experiment_id
            )
            assert current.lifecycle.value == "accepted"
            assert [
                event.kind
                for event in dependencies["repository"].list_events(
                    experiment.experiment_id
                )
            ].count("recovery.requeued") == 1

        def wake(self) -> None:
            """Record one post-recovery scheduler notification."""
            self.wake_calls += 1

        def shutdown(self, *, wait: bool = True) -> None:
            """Record composition shutdown.

            Args:
                wait: Whether worker completion was requested.
            """
            self.shutdown_calls.append(wait)

    monkeypatch.setattr(
        composition_module,
        "LocalBenchmarkExperimentScheduler",
        RecordingScheduler,
    )
    composition = build_default_studio_benchmark_composition(
        tmp_path,
        agents=definitions.definitions.agents,
        profiles=definitions.definitions.profiles,
        contract_catalog=definitions.definitions.contract_catalog,
        sources=(),
        database_path=tmp_path / "studio.sqlite3",
    )
    scheduler = composition.scheduler
    try:
        assert composition.recovery_summary is not None
        assert composition.recovery_summary.requeued == 1
        assert scheduler is not None
        assert scheduler.wake_calls == 1
        assert composition.authoring is not None
        assert composition.authoring_repository is not None
        assert composition.authoring_content is not None
    finally:
        composition.shutdown()
    assert scheduler.shutdown_calls == [True]


def test_executable_composition_contention_fails_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hold workspace ownership for composition lifetime and release on close."""
    definitions, repository, _payload = _resource_service(tmp_path)
    first = build_default_studio_benchmark_composition(
        tmp_path,
        agents=definitions.definitions.agents,
        profiles=definitions.definitions.profiles,
        contract_catalog=definitions.definitions.contract_catalog,
        sources=(),
        database_path=tmp_path / "studio.sqlite3",
    )
    event_shutdowns: list[bool] = []
    original_events = composition_module.DurableBenchmarkEventService

    class RecordingEventService(original_events):
        """Event service spy for partial-construction cleanup."""

        def shutdown(self) -> None:
            """Record shutdown before delegating to normal cleanup."""
            event_shutdowns.append(True)
            super().shutdown()

    monkeypatch.setattr(
        composition_module,
        "DurableBenchmarkEventService",
        RecordingEventService,
    )
    try:
        with pytest.raises(StudioBenchmarkRecoveryOwnershipError):
            build_default_studio_benchmark_composition(
                tmp_path,
                agents=definitions.definitions.agents,
                profiles=definitions.definitions.profiles,
                contract_catalog=definitions.definitions.contract_catalog,
                sources=(),
                database_path=tmp_path / "studio.sqlite3",
            )
        assert event_shutdowns == [True]
        assert repository.list_recovery_candidates(
            process_owner_id="benchmark-process-observer",
            limit=100,
        ).items == ()
    finally:
        first.shutdown()
    reopened = build_default_studio_benchmark_composition(
        tmp_path,
        agents=definitions.definitions.agents,
        profiles=definitions.definitions.profiles,
        contract_catalog=definitions.definitions.contract_catalog,
        sources=(),
        database_path=tmp_path / "studio.sqlite3",
    )
    reopened.shutdown()


def test_composition_releases_ownership_when_recovery_fails_closed(
    tmp_path: Path,
) -> None:
    """Release partial construction resources after durable integrity failure."""
    definitions, repository, payload = _resource_service(tmp_path)
    experiment = _create_experiment(
        definitions,
        payload,
        suffix="composition-corrupt",
    )
    repository.enroll_accepted_experiment(
        experiment.experiment_id,
        process_owner_id=OLD_OWNER,
    )
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        connection.execute(
            "UPDATE studio_benchmark_experiments "
            "SET request_json = '{}' WHERE experiment_id = ?",
            (experiment.experiment_id,),
        )
    with pytest.raises(StudioBenchmarkIntegrityError):
        build_default_studio_benchmark_composition(
            tmp_path,
            agents=definitions.definitions.agents,
            profiles=definitions.definitions.profiles,
            contract_catalog=definitions.definitions.contract_catalog,
            sources=(),
            database_path=tmp_path / "studio.sqlite3",
        )
    ownership = LocalBenchmarkRecoveryOwnership.acquire(
        tmp_path / "studio.sqlite3"
    )
    ownership.close()


def test_composition_releases_ownership_when_scheduler_construction_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release ownership when the post-recovery scheduler cannot be built."""
    definitions, _repository, _payload = _resource_service(tmp_path)

    def fail_scheduler(**dependencies: Any) -> Any:
        """Emulate scheduler construction failure after recovery.

        Args:
            dependencies: Existing scheduler dependencies.

        Raises:
            RuntimeError: Always.

        Returns:
            Never returns.
        """
        del dependencies
        raise RuntimeError("scheduler construction failed")

    monkeypatch.setattr(
        composition_module,
        "LocalBenchmarkExperimentScheduler",
        fail_scheduler,
    )
    with pytest.raises(RuntimeError, match="scheduler construction failed"):
        build_default_studio_benchmark_composition(
            tmp_path,
            agents=definitions.definitions.agents,
            profiles=definitions.definitions.profiles,
            contract_catalog=definitions.definitions.contract_catalog,
            sources=(),
            database_path=tmp_path / "studio.sqlite3",
        )
    ownership = LocalBenchmarkRecoveryOwnership.acquire(
        tmp_path / "studio.sqlite3"
    )
    ownership.close()


def test_composition_releases_ownership_when_publication_recovery_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed and release ownership after a C2 publisher exception."""
    definitions, _repository, _suite, _task = _ready_core_result(tmp_path)

    def fail_publication(
        publisher: Any,
        experiment_id: str,
        task_run_id: str,
        *,
        timestamp: int,
    ) -> Any:
        """Emulate an unrecoverable publisher boundary failure.

        Args:
            publisher: Durable publisher instance.
            experiment_id: Owning Experiment identity.
            task_run_id: Terminal TaskRun identity.
            timestamp: Publication attempt timestamp.

        Raises:
            RuntimeError: Always.

        Returns:
            Never returns.
        """
        del publisher, experiment_id, task_run_id, timestamp
        raise RuntimeError("publication recovery failed")

    monkeypatch.setattr(
        composition_module.DurableStudioBenchmarkPublisher,
        "publish",
        fail_publication,
    )
    with pytest.raises(RuntimeError, match="publication recovery failed"):
        build_default_studio_benchmark_composition(
            tmp_path,
            agents=definitions.definitions.agents,
            profiles=definitions.definitions.profiles,
            contract_catalog=definitions.definitions.contract_catalog,
            sources=(),
            database_path=tmp_path / "studio.sqlite3",
        )
    ownership = LocalBenchmarkRecoveryOwnership.acquire(
        tmp_path / "studio.sqlite3"
    )
    ownership.close()
