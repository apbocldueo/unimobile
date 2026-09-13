"""Stage 5.2B durable Benchmark execution and worker contract tests."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest

from zhixing.benchmark import (
    BenchmarkExperimentRuntime,
    BenchmarkLifecycleEvent,
    BenchmarkPublicationPolicy,
    BenchmarkRunConfig,
    ExperimentProtocol,
    compile_benchmark_suite,
)
from zhixing.benchmark.identity import canonical_hash
from zhixing.components import Action, ActionType, RunStatus
from zhixing.config.contracts import BenchmarkSuite
from zhixing.graph import AgentGraph
from zhixing.runtime import SimpleCancellationSignal
from zhixing.studio.benchmark_errors import StudioBenchmarkConflictError
from zhixing.studio.benchmark_errors import StudioBenchmarkStorageError
from zhixing.studio.benchmark_evidence import LocalStudioBenchmarkEvidenceStore
from zhixing.studio.benchmark_execution import (
    DurableBenchmarkRuntimeEventAdapter,
    LocalBenchmarkExperimentScheduler,
    StudioBenchmarkExecutionAdapter,
    StudioBenchmarkExperimentOrchestrator,
)
from zhixing.studio.benchmark_experiment_models import (
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkEventSource,
    StudioBenchmarkExperimentCancellationV1,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkExperimentTerminalReason,
    StudioBenchmarkTaskPhaseV1,
    StudioBenchmarkTaskRunLifecycle,
    StudioBenchmarkTaskRunTerminalReason,
    StudioBenchmarkTaskResultV1,
)
from zhixing.studio.benchmark_result import (
    STUDIO_BENCHMARK_RESULT_MAX_BYTES,
    project_benchmark_task_result,
)
from zhixing.studio.benchmark_composition import StudioBenchmarkComposition
from zhixing.studio.database import STUDIO_SQLITE_SCHEMA_VERSION
from zhixing.studio.database import migrate_studio_database
from zhixing.studio.benchmark_experiment_repository import (
    SQLiteStudioBenchmarkExperimentRepository,
)
from zhixing.studio.run_execution import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
    DeviceLeaseRegistry,
    ProductionComponentResolverFactory,
)
from zhixing.studio import (
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.httpd import create_http_server

from tests.benchmark.test_experiment_runtime import (
    FakeBenchmarkDevice,
    FakeBenchmarkResolver,
    _agent,
    _task,
)
from tests.studio.test_benchmark_experiment_resource import (
    _http_request,
    _resource_service,
    _start_experiment_http_server,
    _stop_experiment_http_server,
)


class FailingMaterializationResolver(FakeBenchmarkResolver):
    """Benchmark resolver that fails before a TaskInstance can be produced."""

    def generate_task_value(
        self,
        reference: Any,
        params: Any,
        *,
        rng: Any,
    ) -> tuple[Any, tuple[str, ...]]:
        """Raise one controlled dynamic TaskInstance materialization failure.

        Args:
            reference: Logical generator reference.
            params: Rendered dynamic task generator parameters.
            rng: Run-local deterministic random source.

        Raises:
            RuntimeError: Always, before a TaskInstance is produced.

        Returns:
            Never returns.
        """
        del reference, params, rng
        raise RuntimeError("materialization failed")


class FailingProfileResolver:
    """Profile resolver spy that proves no device boundary was crossed."""

    def __init__(self) -> None:
        """Create a zero-call profile failure spy."""
        self.calls = 0

    def resolve(self, profile_id: str) -> Any:
        """Reject one otherwise safe profile identity.

        Args:
            profile_id: Public safe device-profile identity.

        Raises:
            RuntimeError: Always, to emulate missing runtime configuration.

        Returns:
            Never returns.
        """
        del profile_id
        self.calls += 1
        raise RuntimeError("profile unavailable")


class RecordingScheduler:
    """Minimal scheduler spy for composition/server shutdown ownership."""

    def __init__(self) -> None:
        """Create an empty shutdown call log."""
        self.wait_values: list[bool] = []

    def shutdown(self, *, wait: bool = True) -> None:
        """Record one bounded scheduler shutdown request.

        Args:
            wait: Whether the caller requested a worker join.

        Returns:
            None.
        """
        self.wait_values.append(wait)


def _result_for(task: Any) -> tuple[StudioBenchmarkTaskResultV1, str]:
    """Build one valid normalized PASS result for repository contract tests.

    Args:
        task: Stable planned TaskRun record.

    Raises:
        ValueError: Fixture facts violate the strict DTO.

    Returns:
        Result DTO and canonical fingerprint.
    """
    digest = canonical_hash({"fixture": task.task_run_id})
    result = StudioBenchmarkTaskResultV1(
        planned_task_run_id=task.task_run_id,
        core_task_run_id="core-task-run-1",
        agent_run_id="agent-run-1",
        agent_id=task.agent_id,
        agent_revision_id=task.revision_id,
        task_id=task.task_id,
        repeat=task.repeat,
        schedule_order=task.order,
        service_terminal_reason=(
            StudioBenchmarkTaskRunTerminalReason.COMPLETED
        ),
        agent_graph_identity=digest,
        benchmark_plan_identity=digest,
        experiment_protocol_identity=digest,
        task_instance_identity=digest,
        agent_status=RunStatus.SUCCESS,
        benchmark_outcome="pass",
        phases=(
            StudioBenchmarkTaskPhaseV1(
                phase="evaluation",
                status="success",
                evidence={"isPass": True},
            ),
        ),
    )
    fingerprint = canonical_hash(
        result.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
    )
    return result, fingerprint


def test_schema5_repository_claim_result_and_terminal_are_atomic(
    tmp_path: Path,
) -> None:
    """Persist one owner-scoped execution with stable planned/Core identities."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-test"
    assert repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    assert (
        repository.next_enrolled_experiment(process_owner_id=owner)
        == created.experiment_id
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 10,
    )
    task = claimed.task_runs[0]
    assert claimed.experiment.lifecycle is StudioBenchmarkExperimentLifecycle.STARTING
    assert task.lifecycle is StudioBenchmarkTaskRunLifecycle.PREPARING
    result, fingerprint = _result_for(task)
    terminal = repository.commit_task_result(
        created.experiment_id,
        task.task_run_id,
        process_owner_id=owner,
        result=result,
        fingerprint=fingerprint,
        terminal_reason=StudioBenchmarkTaskRunTerminalReason.COMPLETED,
        timestamp=created.accepted_at + 20,
    )
    assert terminal.result is not None
    assert terminal.task_run_id != terminal.result.core_task_run_id
    assert terminal.result_availability.value == "available"
    repeated = repository.commit_task_result(
        created.experiment_id,
        task.task_run_id,
        process_owner_id=owner,
        result=result,
        fingerprint=fingerprint,
        terminal_reason=StudioBenchmarkTaskRunTerminalReason.COMPLETED,
        timestamp=created.accepted_at + 21,
    )
    assert repeated.result_fingerprint == fingerprint
    aggregate = repository.finalize_experiment(
        created.experiment_id,
        process_owner_id=owner,
        terminal_reason=StudioBenchmarkExperimentTerminalReason.COMPLETED,
        timestamp=created.accepted_at + 30,
    )
    assert aggregate.experiment.lifecycle is StudioBenchmarkExperimentLifecycle.TERMINAL
    assert aggregate.experiment.process_owner_id == ""
    events = repository.list_events(created.experiment_id)
    assert [item.sequence for item in events] == list(
        range(1, len(events) + 1)
    )
    assert sum(item.kind == "experiment.terminal" for item in events) == 1
    with pytest.raises(StudioBenchmarkConflictError):
        repository.append_runtime_event(
            created.experiment_id,
            process_owner_id=owner,
            event=StudioBenchmarkEventDraftV1(
                event_id="benchmark-event-" + "f" * 32,
                timestamp=created.accepted_at + 40,
                source=StudioBenchmarkEventSource.CORE,
                source_sequence=1,
                kind="benchmark.late",
            ),
        )
    with sqlite3.connect(tmp_path / "studio.sqlite3") as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM studio_schema_migrations ORDER BY version"
            )
        ]
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(studio_benchmark_task_runs)"
            )
        }
    assert versions == list(range(1, STUDIO_SQLITE_SCHEMA_VERSION + 1))
    assert {
        "core_task_run_id",
        "phase_results_json",
        "task_instance_availability",
        "phase_availability",
        "agent_status_availability",
        "result_json",
        "result_fingerprint",
        "result_availability",
    } <= columns


def test_populated_schema4_upgrade_preserves_terminal_identity_and_journal(
    tmp_path: Path,
) -> None:
    """Upgrade a populated schema-4 layout without changing durable facts."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    cancelled = service.cancel_experiment(
        created.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "cancel-before-schema5",
        },
    )
    database = tmp_path / "studio.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            CREATE TABLE studio_benchmark_task_runs_v4 (
                task_run_id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL,
                planned_entry_id TEXT NOT NULL,
                schedule_order INTEGER NOT NULL,
                agent_id TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                repeat_index INTEGER NOT NULL,
                derived_seed INTEGER NOT NULL,
                lifecycle_state TEXT NOT NULL,
                terminal_reason TEXT,
                outcome_availability TEXT NOT NULL,
                task_run_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                terminal_at INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO studio_benchmark_task_runs_v4
            SELECT task_run_id, experiment_id, planned_entry_id,
                schedule_order, agent_id, revision_id, task_id,
                repeat_index, derived_seed, lifecycle_state,
                terminal_reason, outcome_availability, task_run_json,
                created_at, updated_at, terminal_at
            FROM studio_benchmark_task_runs
            """
        )
        connection.execute("DROP TABLE studio_benchmark_task_runs")
        connection.execute(
            "ALTER TABLE studio_benchmark_task_runs_v4 "
            "RENAME TO studio_benchmark_task_runs"
        )
        connection.execute(
            """
            CREATE TABLE studio_benchmark_experiment_events_v4 (
                experiment_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                envelope_json TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (experiment_id, sequence),
                UNIQUE (experiment_id, event_id)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO studio_benchmark_experiment_events_v4
            SELECT experiment_id, sequence, event_id, fingerprint,
                envelope_json, created_at
            FROM studio_benchmark_experiment_events
            """
        )
        connection.execute("DROP TABLE studio_benchmark_experiment_events")
        connection.execute(
            "ALTER TABLE studio_benchmark_experiment_events_v4 "
            "RENAME TO studio_benchmark_experiment_events"
        )
        connection.execute(
            "DELETE FROM studio_schema_migrations WHERE version = 5"
        )
    migrate_studio_database(database)
    restored = repository.get_experiment(created.experiment_id)
    task = repository.list_task_runs(created.experiment_id).items[0]
    events = repository.list_events(created.experiment_id)
    assert restored.lifecycle is StudioBenchmarkExperimentLifecycle.TERMINAL
    assert restored.terminal_reason == cancelled.terminal_reason
    assert task.task_run_id.startswith("task-run-")
    assert task.terminal_reason.value == "cancelled_before_start"
    assert [event.sequence for event in events] == [1, 2, 3, 4]


def test_runtime_event_append_is_idempotent_and_conflict_detecting(
    tmp_path: Path,
) -> None:
    """Return identical retries and reject same event identity with new content."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-event"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    draft = StudioBenchmarkEventDraftV1(
        event_id="benchmark-event-" + "a" * 32,
        timestamp=created.accepted_at + 2,
        source=StudioBenchmarkEventSource.CORE,
        source_sequence=1,
        phase="setup",
        kind="benchmark.setup.start",
        payload={"apiKey": "must-not-persist", "path": "/private/tmp/secret"},
    )
    first = repository.append_runtime_event(
        created.experiment_id,
        process_owner_id=owner,
        event=draft,
    )
    second = repository.append_runtime_event(
        created.experiment_id,
        process_owner_id=owner,
        event=draft,
    )
    assert first.sequence == second.sequence
    encoded = json.dumps(first.model_dump(mode="json", by_alias=True))
    assert "must-not-persist" not in encoded
    assert "/private/tmp/secret" not in encoded
    with pytest.raises(StudioBenchmarkConflictError):
        repository.append_runtime_event(
            created.experiment_id,
            process_owner_id=owner,
            event=draft.model_copy(update={"kind": "benchmark.setup.complete"}),
        )


def test_result_transaction_failure_rolls_back_event_and_terminal_fact(
    tmp_path: Path,
) -> None:
    """Keep the active TaskRun unchanged when bounded result commit fails."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-result-rollback"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    result, fingerprint = _result_for(claimed.task_runs[0])
    failing = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3",
        failure_hook=lambda step: (
            (_ for _ in ()).throw(RuntimeError("injected result failure"))
            if step == "result.after_commit"
            else None
        ),
    )
    before_events = len(repository.list_events(created.experiment_id))
    with pytest.raises(StudioBenchmarkStorageError):
        failing.commit_task_result(
            created.experiment_id,
            claimed.task_runs[0].task_run_id,
            process_owner_id=owner,
            result=result,
            fingerprint=fingerprint,
            terminal_reason=StudioBenchmarkTaskRunTerminalReason.COMPLETED,
            timestamp=created.accepted_at + 2,
        )
    restored = repository.get_task_run(
        created.experiment_id,
        claimed.task_runs[0].task_run_id,
    )
    assert restored.lifecycle is StudioBenchmarkTaskRunLifecycle.PREPARING
    assert restored.result is None
    assert len(repository.list_events(created.experiment_id)) == before_events


def test_journal_and_terminal_failure_injection_leave_retryable_facts(
    tmp_path: Path,
) -> None:
    """Roll back event and terminal transactions at their last checkpoints."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-failure-injection"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    event_count = len(repository.list_events(created.experiment_id))
    failing_event_repository = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3",
        failure_hook=lambda step: (
            (_ for _ in ()).throw(RuntimeError("injected event failure"))
            if step == "event.after_append"
            else None
        ),
    )
    with pytest.raises(StudioBenchmarkStorageError):
        failing_event_repository.append_runtime_event(
            created.experiment_id,
            process_owner_id=owner,
            event=StudioBenchmarkEventDraftV1(
                event_id="benchmark-event-" + "b" * 32,
                timestamp=created.accepted_at + 2,
                source=StudioBenchmarkEventSource.CORE,
                source_sequence=1,
                phase="setup",
                kind="benchmark.setup.start",
            ),
        )
    assert len(repository.list_events(created.experiment_id)) == event_count
    result, fingerprint = _result_for(claimed.task_runs[0])
    repository.commit_task_result(
        created.experiment_id,
        claimed.task_runs[0].task_run_id,
        process_owner_id=owner,
        result=result,
        fingerprint=fingerprint,
        terminal_reason=StudioBenchmarkTaskRunTerminalReason.COMPLETED,
        timestamp=created.accepted_at + 3,
    )
    failing_terminal_repository = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3",
        failure_hook=lambda step: (
            (_ for _ in ()).throw(RuntimeError("injected terminal failure"))
            if step == "finalize.after_terminal"
            else None
        ),
    )
    before_terminal = len(repository.list_events(created.experiment_id))
    with pytest.raises(StudioBenchmarkStorageError):
        failing_terminal_repository.finalize_experiment(
            created.experiment_id,
            process_owner_id=owner,
            terminal_reason=StudioBenchmarkExperimentTerminalReason.COMPLETED,
            timestamp=created.accepted_at + 4,
        )
    assert (
        repository.get_experiment(created.experiment_id).lifecycle
        is StudioBenchmarkExperimentLifecycle.FINALIZING
    )
    assert len(repository.list_events(created.experiment_id)) == before_terminal
    terminal = repository.finalize_experiment(
        created.experiment_id,
        process_owner_id=owner,
        terminal_reason=StudioBenchmarkExperimentTerminalReason.COMPLETED,
        timestamp=created.accepted_at + 5,
    )
    assert terminal.experiment.terminal_reason.value == "completed"


def test_runtime_event_failure_cancels_before_next_effect(
    tmp_path: Path,
) -> None:
    """Cancel the shared signal when synchronous journal persistence fails."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-event-stop"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    signal = SimpleCancellationSignal()
    failing_repository = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3",
        failure_hook=lambda step: (
            (_ for _ in ()).throw(RuntimeError("journal unavailable"))
            if step == "event.after_append"
            else None
        ),
    )
    adapter = DurableBenchmarkRuntimeEventAdapter(
        repository=failing_repository,
        experiment_id=created.experiment_id,
        planned_task_run_id=claimed.task_runs[0].task_run_id,
        process_owner_id=owner,
        cancellation=signal,
    )
    before = len(repository.list_events(created.experiment_id))
    with pytest.raises(StudioBenchmarkStorageError):
        adapter(
            BenchmarkLifecycleEvent(
                experiment_id=created.experiment_id,
                sequence=1,
                phase="setup",
                kind="start",
                task_run_id="core-task-run",
                task_id=claimed.task_runs[0].task_id,
                agent_id=claimed.task_runs[0].agent_id,
                repeat=claimed.task_runs[0].repeat,
            )
        )
    assert signal.is_cancelled()
    assert len(repository.list_events(created.experiment_id)) == before


def test_late_finalizing_cancel_preserves_committed_result_and_completion(
    tmp_path: Path,
) -> None:
    """Record a late cancel without replacing an already committed outcome."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-late-cancel"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    result, fingerprint = _result_for(claimed.task_runs[0])
    repository.commit_task_result(
        created.experiment_id,
        claimed.task_runs[0].task_run_id,
        process_owner_id=owner,
        result=result,
        fingerprint=fingerprint,
        terminal_reason=StudioBenchmarkTaskRunTerminalReason.COMPLETED,
        timestamp=created.accepted_at + 2,
    )
    cancelling = repository.request_cancellation(
        created.experiment_id,
        StudioBenchmarkExperimentCancellationV1(
            client_request_id="late-finalizing-cancel",
            requested_at=created.accepted_at + 3,
        ),
    )
    assert (
        cancelling.experiment.lifecycle
        is StudioBenchmarkExperimentLifecycle.FINALIZING
    )
    terminal = repository.finalize_experiment(
        created.experiment_id,
        process_owner_id=owner,
        terminal_reason=StudioBenchmarkExperimentTerminalReason.COMPLETED,
        timestamp=created.accepted_at + 4,
    )
    assert terminal.experiment.terminal_reason.value == "completed"
    restored = repository.get_task_run(
        created.experiment_id,
        claimed.task_runs[0].task_run_id,
    )
    assert restored.benchmark_outcome.value == "pass"
    assert restored.result_fingerprint == fingerprint
    events = repository.list_events(created.experiment_id)
    assert sum(item.kind == "experiment.terminal" for item in events) == 1


def test_orchestrator_retries_matching_terminal_after_result_commit(
    tmp_path: Path,
) -> None:
    """Never reinterpret a committed PASS as failed after transient finalization."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-finalize-retry"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    failures = {"remaining": 1}

    def fail_once(step: str) -> None:
        """Raise only on the first final terminal transaction checkpoint.

        Args:
            step: Stable repository failure-injection checkpoint.

        Raises:
            RuntimeError: First finalization reaches its last checkpoint.

        Returns:
            None.
        """
        if step == "finalize.after_terminal" and failures["remaining"]:
            failures["remaining"] -= 1
            raise RuntimeError("transient finalization failure")

    orchestrator_repository = SQLiteStudioBenchmarkExperimentRepository(
        tmp_path / "studio.sqlite3",
        failure_hook=fail_once,
    )
    StudioBenchmarkExperimentOrchestrator(
        repository=orchestrator_repository,
        execution=CoreFakeExecution(),
        process_owner_id=owner,
    ).execute(created.experiment_id)
    experiment = repository.get_experiment(created.experiment_id)
    task = repository.get_task_run(
        created.experiment_id,
        repository.list_task_runs(created.experiment_id).items[0].task_run_id,
    )
    assert experiment.terminal_reason.value == "completed"
    assert task.benchmark_outcome.value == "pass"
    assert task.result is not None
    assert (
        sum(
            item.kind == "experiment.terminal"
            for item in repository.list_events(created.experiment_id)
        )
        == 1
    )


def test_unknown_worker_failure_closes_failed_and_releases_active_signal(
    tmp_path: Path,
) -> None:
    """Normalize an unknown pre-result exception without leaking worker state."""

    class RaisingExecution(CoreFakeExecution):
        """Execution fixture that raises after pure prepare and before Core."""

        def execute(
            self,
            prepared: Any,
            *,
            cancellation: SimpleCancellationSignal,
            event_sink: Callable[[Any], None],
        ) -> Any:
            """Raise one unknown worker exception before a Core result exists.

            Args:
                prepared: Claimed aggregate returned by pure preflight.
                cancellation: Shared cooperative signal.
                event_sink: Durable runtime journal adapter.

            Raises:
                RuntimeError: Always, to exercise worker normalization.

            Returns:
                Never returns.
            """
            del prepared, cancellation, event_sink
            raise RuntimeError("unknown worker failure")

    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-unknown-failure"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    orchestrator = StudioBenchmarkExperimentOrchestrator(
        repository=repository,
        execution=RaisingExecution(),
        process_owner_id=owner,
    )
    orchestrator.execute(created.experiment_id)
    experiment = repository.get_experiment(created.experiment_id)
    task = repository.list_task_runs(created.experiment_id).items[0]
    assert experiment.terminal_reason.value == "failed"
    assert experiment.process_owner_id == ""
    assert task.terminal_reason.value == "failed"
    assert task.result is None
    assert task.result_availability.value == "failed"
    assert orchestrator.cancel_active(created.experiment_id) is False


def test_result_projector_bounds_and_omits_runtime_event_history(
    tmp_path: Path,
) -> None:
    """Sanitize nested evidence and keep runtime events in the journal only."""
    plan_result = compile_benchmark_suite(
        BenchmarkSuite.model_validate([_task("one")])
    )
    assert plan_result.plan is not None
    core = BenchmarkExperimentRuntime().run(
        plan_result.plan,
        ExperimentProtocol(),
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(
            artifact_root=tmp_path,
            publication_policy=BenchmarkPublicationPolicy.DEFER,
        ),
        resolver=FakeBenchmarkResolver(),
        device=FakeBenchmarkDevice(),
    ).results[0]
    unsafe_stage = core.stages[0].__class__(
        phase=core.stages[0].phase,
        status=core.stages[0].status,
        evidence={
            "apiKey": "super-secret",
            "path": "/Users/researcher/private/result.json",
            "serial": "emulator-5554",
            "huge": "x" * (STUDIO_BENCHMARK_RESULT_MAX_BYTES * 2),
        },
    )
    assert core.evaluation is not None
    unsafe_evaluation = replace(
        core.evaluation,
        reason="token=hidden-value /Users/researcher/private/evaluation.txt",
        evidence={
            "authorization": "Bearer hidden-evaluation-token",
            "liveClient": object(),
        },
    )
    assert core.agent_result is not None
    unsafe_agent_result = replace(
        core.agent_result,
        final_output={
            "apiKey": "agent-result-secret",
            "path": "/Users/researcher/private/agent-output.json",
            "client": object(),
        },
    )
    unsafe = replace(
        core,
        stages=(unsafe_stage, *core.stages[1:]),
        evaluation=unsafe_evaluation,
        agent_result=unsafe_agent_result,
        usage={"apiKey": "usage-secret", "total_tokens": 7},
        fairness_warnings=(
            "password=hidden /Users/researcher/private/warning.txt",
        ),
    )
    projected, fingerprint = project_benchmark_task_result(
        unsafe,
        planned_task_run_id="task-run-" + "1" * 32,
        agent_revision_id="revision-" + "1" * 32,
        schedule_order=0,
        service_terminal_reason=(
            StudioBenchmarkTaskRunTerminalReason.COMPLETED
        ),
    )
    encoded = json.dumps(
        projected.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
    )
    assert "super-secret" not in encoded
    assert "hidden-value" not in encoded
    assert "hidden-evaluation-token" not in encoded
    assert "usage-secret" not in encoded
    assert "agent-result-secret" not in encoded
    assert "emulator-5554" not in encoded
    assert "/Users/researcher/private" not in encoded
    assert "object at 0x" not in encoded
    assert "lifecycleEvents" not in encoded
    assert fingerprint.startswith("sha256:")
    assert len(encoded.encode("utf-8")) <= STUDIO_BENCHMARK_RESULT_MAX_BYTES


def test_production_preflight_uses_snapshot_and_detects_package_drift(
    tmp_path: Path,
) -> None:
    """Verify immutable graph/source/resource facts without resolving a device."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-preflight"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    adapter = StudioBenchmarkExecutionAdapter(
        definitions=service.definitions,
        components=ProductionComponentResolverFactory(),
        evidence=LocalStudioBenchmarkEvidenceStore(
            tmp_path / "private-evidence",
            minimum_free_bytes=0,
        ),
        profiles=service.definitions.profiles,
    )
    prepared = adapter.prepare(claimed)
    assert prepared.agent.canonical_hash == (
        created.definition.agent_snapshots[0].canonical_hash
    )
    snapshot_agent = created.definition.agent_snapshots[0]
    current_revision = service.definitions.agents.get_revision(
        snapshot_agent.agent_id,
        snapshot_agent.revision_id,
    )
    changed_document = current_revision.document.to_json_dict()
    first_canvas_node = next(
        iter(changed_document["presentation"]["nodes"].values())
    )
    first_canvas_node["x"] = int(first_canvas_node.get("x", 0)) + 100
    authoring = StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=service.definitions.agents,
    )
    _agent_record, newer_revision = authoring.save_revision(
        snapshot_agent.agent_id,
        base_revision_id=snapshot_agent.revision_id,
        raw_document=changed_document,
    )
    assert newer_revision.revision_id != snapshot_agent.revision_id
    assert adapter.prepare(claimed).agent.canonical_hash == (
        snapshot_agent.canonical_hash
    )
    unsupported = replace(
        claimed,
        task_runs=(claimed.task_runs[0], claimed.task_runs[0]),
    )
    with pytest.raises(Exception) as cardinality:
        adapter.prepare(unsupported)
    assert getattr(cardinality.value, "code", "") == (
        "benchmark.experiment.cardinality_unsupported"
    )
    tampered_definition = claimed.experiment.definition.model_copy(
        update={"snapshot_fingerprint": "sha256:" + "0" * 64}
    )
    tampered = replace(
        claimed,
        experiment=claimed.experiment.model_copy(
            update={"definition": tampered_definition}
        ),
    )
    with pytest.raises(Exception) as fingerprint:
        adapter.prepare(tampered)
    assert getattr(fingerprint.value, "code", "") == (
        "benchmark.experiment.snapshot_tampered"
    )
    package_task = (
        tmp_path / "catalog" / "fixture" / "tasks" / "test.json"
    )
    changed = json.loads(package_task.read_text(encoding="utf-8"))
    changed[0]["instruction"] = "tampered after durable acceptance"
    package_task.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(Exception) as captured:
        adapter.prepare(claimed)
    assert getattr(captured.value, "code", "") in {
        "benchmark.experiment.source_unavailable",
        "benchmark.experiment.definition_drift",
    }
    assert not (tmp_path / "private-evidence").exists()


def test_benchmark_worker_rejects_current_catalog_drift_before_evidence_or_profile(
    tmp_path: Path,
) -> None:
    """Apply current capability policy before Package, evidence, or device work.

    Args:
        tmp_path: Isolated durable Experiment and evidence root.

    Raises:
        StudioBenchmarkValidationError: Expected for current Catalog drift.

    Returns:
        None.
    """
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-policy-drift"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    selected = {
        (candidate["namespace"], candidate["name"], candidate["version"])
        for node in claimed.experiment.definition.agent_snapshots[0].capability_document[
            "capabilities"
        ]
        for candidate in node["implementation"]["candidates"]
    }
    current_catalog = service.definitions.component_catalog
    service.definitions.component_catalog = current_catalog.model_copy(
        update={
            "components": tuple(
                item
                for item in current_catalog.components
                if (item.namespace, item.name, item.version) not in selected
            )
        }
    )

    class ProfileCanary(AndroidDeviceProfileResolver):
        """Reject any profile access beyond policy preflight."""

        def resolve(self, profile_id: str) -> AndroidDeviceProfile:
            """Fail if policy validation reaches profile resolution.

            Args:
                profile_id: Forbidden profile identity.

            Raises:
                AssertionError: Always; Catalog drift must fail first.

            Returns:
                Never returns.
            """
            del profile_id
            raise AssertionError("profile must not resolve after policy drift")

    adapter = StudioBenchmarkExecutionAdapter(
        definitions=service.definitions,
        components=ProductionComponentResolverFactory(),
        evidence=LocalStudioBenchmarkEvidenceStore(
            tmp_path / "policy-evidence",
            minimum_free_bytes=0,
        ),
        profiles=ProfileCanary(),
    )
    with pytest.raises(Exception) as captured:
        adapter.prepare(claimed)
    assert getattr(captured.value, "code", "") == (
        "studio.policy.catalog_component_missing"
    )
    assert not (tmp_path / "policy-evidence").exists()


def test_component_and_evidence_preflight_fail_before_profile_resolution(
    tmp_path: Path,
) -> None:
    """Reject unavailable bindings and capacity before runtime profile access."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-fail-fast"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    components = ProductionComponentResolverFactory()
    graph = AgentGraph.model_validate(
        claimed.experiment.definition.agent_snapshots[0].agent_graph
    )
    component_index = next(
        index
        for index, node in enumerate(graph.nodes)
        if node.component is not None and node.role is not None
    )
    original_node = graph.nodes[component_index]
    assert original_node.component is not None
    missing_reference = original_node.component.candidates[0].model_copy(
        update={
            "namespace": "missing.component",
            "name": "not-installed",
            "version": "1",
        }
    )
    missing_binding = original_node.component.model_copy(
        update={"candidates": (missing_reference,)}
    )
    nodes = list(graph.nodes)
    nodes[component_index] = original_node.model_copy(
        update={"component": missing_binding}
    )
    unavailable_graph = graph.model_copy(update={"nodes": tuple(nodes)})
    with pytest.raises(Exception) as binding_error:
        components.validate_graph_bindings(unavailable_graph)
    assert getattr(binding_error.value, "code", "") == (
        "studio.run.component_unavailable"
    )

    profiles = FailingProfileResolver()
    adapter = StudioBenchmarkExecutionAdapter(
        definitions=service.definitions,
        components=components,
        evidence=LocalStudioBenchmarkEvidenceStore(
            tmp_path / "private-evidence",
            minimum_free_bytes=0,
        ),
        profiles=service.definitions.profiles,
    )
    prepared = adapter.prepare(claimed)
    capacity_adapter = StudioBenchmarkExecutionAdapter(
        definitions=service.definitions,
        components=components,
        evidence=LocalStudioBenchmarkEvidenceStore(
            tmp_path / "capacity-evidence",
            minimum_free_bytes=2**63,
        ),
        profiles=profiles,
    )
    events: list[Any] = []
    with pytest.raises(StudioBenchmarkStorageError):
        capacity_adapter.execute(
            prepared,
            cancellation=SimpleCancellationSignal(),
            event_sink=events.append,
        )
    assert profiles.calls == 0
    assert events == []

    unavailable_profile_adapter = StudioBenchmarkExecutionAdapter(
        definitions=service.definitions,
        components=components,
        evidence=LocalStudioBenchmarkEvidenceStore(
            tmp_path / "profile-evidence",
            minimum_free_bytes=0,
        ),
        profiles=profiles,
    )
    with pytest.raises(RuntimeError, match="profile unavailable"):
        unavailable_profile_adapter.execute(
            prepared,
            cancellation=SimpleCancellationSignal(),
            event_sink=events.append,
        )
    assert profiles.calls == 1
    assert events == []


def test_device_lease_failure_precedes_every_benchmark_device_effect(
    tmp_path: Path,
) -> None:
    """Reject a busy safe profile after evidence preflight but before Core."""
    service, repository, payload = _resource_service(tmp_path)
    device = FakeBenchmarkDevice()
    profiles = AndroidDeviceProfileResolver(
        {
            "local-android": AndroidDeviceProfile(
                "local-android",
                serial="private-device-serial",
                device=device,
            )
        }
    )
    service.definitions.profiles = profiles
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-device-busy"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    leases = DeviceLeaseRegistry()
    adapter = StudioBenchmarkExecutionAdapter(
        definitions=service.definitions,
        components=ProductionComponentResolverFactory(),
        evidence=LocalStudioBenchmarkEvidenceStore(
            tmp_path / "busy-evidence",
            minimum_free_bytes=0,
        ),
        profiles=profiles,
        leases=leases,
    )
    prepared = adapter.prepare(claimed)
    events: list[Any] = []
    with leases.acquire(
        profiles.resolve("local-android").target_key,
        "another-run",
    ):
        with pytest.raises(Exception) as busy:
            adapter.execute(
                prepared,
                cancellation=SimpleCancellationSignal(),
                event_sink=events.append,
            )
    assert getattr(busy.value, "code", "") == "studio.device.target_busy"
    assert device.calls == []
    assert events == []


class CoreFakeExecution:
    """Execution adapter fixture that delegates real semantics to Benchmark Core."""

    def __init__(
        self,
        *,
        entered: threading.Event | None = None,
        release: threading.Event | None = None,
        mode: str = "pass",
    ) -> None:
        """Configure optional deterministic scheduler blocking.

        Args:
            entered: Set after the first execution enters.
            release: Optional gate that blocks execution until released.
            mode: Deterministic Core outcome/failure fixture mode.

        Raises:
            ValueError: Fixture mode is unknown.

        Returns:
            None.
        """
        if mode not in {
            "pass",
            "fail",
            "evaluator_error",
            "cleanup_failure",
            "materialization_failure",
            "device_mismatch",
        }:
            raise ValueError("unknown fake Benchmark execution mode")
        self.entered = entered
        self.release = release
        self.mode = mode
        self.calls: list[str] = []

    def prepare(self, aggregate: Any) -> Any:
        """Return the durable aggregate as the fake prepared value.

        Args:
            aggregate: Claimed durable Experiment aggregate.

        Raises:
            None.

        Returns:
            Aggregate unchanged.
        """
        return aggregate

    def execute(
        self,
        prepared: Any,
        *,
        cancellation: SimpleCancellationSignal,
        event_sink: Callable[[Any], None],
    ) -> Any:
        """Run one real Core lifecycle over deterministic fake boundaries.

        Args:
            prepared: Claimed durable Experiment aggregate.
            cancellation: Shared cooperative signal.
            event_sink: Durable lifecycle event adapter.

        Raises:
            RuntimeError: Fixture Core result is absent.

        Returns:
            One complete Core BenchmarkTaskResult.
        """
        experiment_id = prepared.experiment.experiment_id
        self.calls.append(experiment_id)
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            self.release.wait(timeout=3)
        task_id = prepared.task_runs[0].task_id
        task_mapping = _task(
            task_id,
            evaluator_pass=self.mode != "fail",
        )
        if self.mode == "evaluator_error":
            task_mapping["evaluator"]["params"]["raise"] = True
        if self.mode == "cleanup_failure":
            task_mapping["cleanup_initializer"][0]["params"]["fail"] = True
        compiled = compile_benchmark_suite(
            BenchmarkSuite.model_validate([task_mapping])
        )
        assert compiled.plan is not None
        resolver = (
            FailingMaterializationResolver()
            if self.mode == "materialization_failure"
            else FakeBenchmarkResolver()
        )
        device = FakeBenchmarkDevice()
        if self.mode == "device_mismatch":
            device.platform = "harmony"
        suite = BenchmarkExperimentRuntime().run(
            compiled.plan,
            ExperimentProtocol(),
            {
                prepared.task_runs[0].agent_id: _agent(
                    Action(ActionType.KEY, {"code": "home"})
                )
            },
            run_config=BenchmarkRunConfig(
                artifact_root=Path("/private/tmp/zhixing-worker-test"),
                experiment_id=experiment_id,
                publication_policy=BenchmarkPublicationPolicy.DEFER,
            ),
            resolver=resolver,
            device=device,
            event_sink=event_sink,
            cancellation=cancellation,
        )
        return suite.results[0]


def _wait_terminal(service: Any, experiment_id: str) -> Any:
    """Wait a bounded interval for one background worker terminal fact.

    Args:
        service: Benchmark Experiment application service.
        experiment_id: Durable Experiment identity.

    Raises:
        AssertionError: Worker does not terminate within three seconds.

    Returns:
        Terminal public Experiment resource.
    """
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        current = service.get_experiment(experiment_id)
        if current.lifecycle is StudioBenchmarkExperimentLifecycle.TERMINAL:
            return current
        threading.Event().wait(0.01)
    raise AssertionError("Benchmark worker did not reach terminal lifecycle")


def test_single_scheduler_executes_two_durable_experiments_serially(
    tmp_path: Path,
) -> None:
    """Keep busy work accepted and execute each locally enrolled row once."""
    service, repository, payload = _resource_service(tmp_path)
    owner = "benchmark-process-scheduler"
    entered = threading.Event()
    release = threading.Event()
    execution = CoreFakeExecution(entered=entered, release=release)
    orchestrator = StudioBenchmarkExperimentOrchestrator(
        repository=repository,
        execution=execution,
        process_owner_id=owner,
    )
    scheduler = LocalBenchmarkExperimentScheduler(
        repository=repository,
        orchestrator=orchestrator,
        process_owner_id=owner,
    )

    def dispatch(experiment_id: str, created: bool) -> None:
        """Enroll newly committed rows and wake the single worker.

        Args:
            experiment_id: Durable Experiment identity.
            created: Whether this was the first durable create.

        Raises:
            AssertionError: Fixture dispatch receives a non-created row.

        Returns:
            None.
        """
        assert created
        repository.enroll_accepted_experiment(
            experiment_id,
            process_owner_id=owner,
        )
        scheduler.wake()

    service._dispatch = dispatch
    service._execution_enabled = True
    first = service.create_experiment(payload).experiment
    assert entered.wait(timeout=3)
    scheduler.wake()
    scheduler.wake()
    second_payload = json.loads(json.dumps(payload))
    second_payload["clientRequestId"] = "experiment-request-2"
    second = service.create_experiment(second_payload).experiment
    assert (
        service.get_experiment(second.experiment_id).lifecycle
        is StudioBenchmarkExperimentLifecycle.ACCEPTED
    )
    release.set()
    try:
        _wait_terminal(service, first.experiment_id)
        _wait_terminal(service, second.experiment_id)
    finally:
        scheduler.shutdown()
    assert execution.calls == [first.experiment_id, second.experiment_id]
    for experiment_id in execution.calls:
        assert repository.get_experiment(experiment_id).process_owner_id == ""
        task = service.list_task_runs(experiment_id).items[0]
        assert task.result is not None
        assert task.task_run_id != task.core_task_run_id
        assert task.benchmark_outcome.value == "pass"


@pytest.mark.parametrize(
    ("mode", "expected_outcome", "expect_agent", "expect_evaluation"),
    (
        ("fail", "fail", True, True),
        ("evaluator_error", "invalid", True, False),
        ("cleanup_failure", "invalid", True, True),
        ("materialization_failure", "invalid", False, False),
        ("device_mismatch", "invalid", False, False),
    ),
)
def test_worker_preserves_independent_core_result_axes(
    tmp_path: Path,
    mode: str,
    expected_outcome: str,
    expect_agent: bool,
    expect_evaluation: bool,
) -> None:
    """Persist Core FAIL/INVALID evidence without changing service completion.

    Args:
        tmp_path: Isolated Studio database and Catalog root.
        mode: Controlled fake Core lifecycle variation.
        expected_outcome: Formal Benchmark outcome value.
        expect_agent: Whether Core should have produced an Agent status.
        expect_evaluation: Whether Core should retain an Evaluation Tree.

    Raises:
        AssertionError: Worker conflates the three result axes.

    Returns:
        None.
    """
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = f"benchmark-process-{mode}"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    StudioBenchmarkExperimentOrchestrator(
        repository=repository,
        execution=CoreFakeExecution(mode=mode),
        process_owner_id=owner,
    ).execute(created.experiment_id)
    experiment = service.get_experiment(created.experiment_id)
    task = service.list_task_runs(created.experiment_id).items[0]
    assert experiment.terminal_reason.value == "completed"
    assert task.terminal_reason.value == "completed"
    assert task.benchmark_outcome.value == expected_outcome
    assert task.outcome_availability.value == "available"
    assert task.task_instance_availability.value == "available"
    assert task.phase_availability.value == "available"
    assert (task.agent_status is not None) is expect_agent
    assert task.agent_status_availability.value == (
        "available" if expect_agent else "not_produced"
    )
    assert (task.evaluation is not None) is expect_evaluation
    assert task.evaluation_availability.value == (
        "available" if expect_evaluation else "not_produced"
    )
    assert task.result is not None
    assert task.result.agent_revision_id == task.revision_id
    assert task.result.schedule_order == task.order
    assert task.result.service_terminal_reason.value == "completed"


def test_active_cancellation_persists_before_signal_and_finishes_cooperatively(
    tmp_path: Path,
) -> None:
    """Cancel active work durably, then let Core observe the shared signal."""
    service, repository, payload = _resource_service(tmp_path)
    owner = "benchmark-process-cancel"
    entered = threading.Event()
    release = threading.Event()
    execution = CoreFakeExecution(entered=entered, release=release)
    orchestrator = StudioBenchmarkExperimentOrchestrator(
        repository=repository,
        execution=execution,
        process_owner_id=owner,
    )
    scheduler = LocalBenchmarkExperimentScheduler(
        repository=repository,
        orchestrator=orchestrator,
        process_owner_id=owner,
    )

    def dispatch(experiment_id: str, created: bool) -> None:
        """Enroll and wake one newly accepted cancellation fixture.

        Args:
            experiment_id: Durable Experiment identity.
            created: Whether the create transaction inserted the row.

        Raises:
            AssertionError: Fixture receives an idempotent retry.

        Returns:
            None.
        """
        assert created
        repository.enroll_accepted_experiment(
            experiment_id,
            process_owner_id=owner,
        )
        scheduler.wake()

    service._dispatch = dispatch
    service._cancel_active = orchestrator.cancel_active
    service._execution_enabled = True
    experiment = service.create_experiment(payload).experiment
    assert entered.wait(timeout=3)
    cancelling = service.cancel_experiment(
        experiment.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "cancel-active-worker",
        },
    )
    assert cancelling.lifecycle is StudioBenchmarkExperimentLifecycle.CANCELLING
    assert cancelling.cancellation is not None
    repeated = service.cancel_experiment(
        experiment.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "cancel-active-worker",
        },
    )
    assert repeated.cancellation == cancelling.cancellation
    release.set()
    try:
        terminal = _wait_terminal(service, experiment.experiment_id)
    finally:
        scheduler.shutdown()
    assert terminal.terminal_reason.value == "cancelled"
    task = service.list_task_runs(experiment.experiment_id).items[0]
    assert task.terminal_reason.value == "cancelled"
    assert task.result is not None
    assert task.benchmark_outcome.value == "skipped"
    events = repository.list_events(experiment.experiment_id)
    cancel_sequence = next(
        item.sequence
        for item in events
        if item.kind == "experiment.cancellation_requested"
    )
    terminal_sequence = next(
        item.sequence
        for item in events
        if item.kind == "experiment.terminal"
    )
    assert cancel_sequence < terminal_sequence
    assert (
        sum(
            item.kind == "experiment.cancellation_requested"
            for item in events
        )
        == 1
    )


def test_cancellation_during_pure_preflight_starts_no_runtime_effect(
    tmp_path: Path,
) -> None:
    """Stop after pure preflight when the durable cancellation wins."""

    class BlockingPrepareExecution(CoreFakeExecution):
        """Execution fixture that exposes a deterministic pure-preflight race."""

        def __init__(self) -> None:
            """Create preflight gates and an otherwise normal Core fixture."""
            super().__init__()
            self.preflight_entered = threading.Event()
            self.preflight_release = threading.Event()

        def prepare(self, aggregate: Any) -> Any:
            """Block after entering pure preflight and before runtime execution.

            Args:
                aggregate: Claimed durable Experiment aggregate.

            Raises:
                AssertionError: Test does not release preflight in time.

            Returns:
                Aggregate unchanged after the race is released.
            """
            self.preflight_entered.set()
            if not self.preflight_release.wait(timeout=3):
                raise AssertionError("pure preflight race was not released")
            return aggregate

    service, repository, payload = _resource_service(tmp_path)
    owner = "benchmark-process-preflight-cancel"
    execution = BlockingPrepareExecution()
    orchestrator = StudioBenchmarkExperimentOrchestrator(
        repository=repository,
        execution=execution,
        process_owner_id=owner,
    )
    scheduler = LocalBenchmarkExperimentScheduler(
        repository=repository,
        orchestrator=orchestrator,
        process_owner_id=owner,
    )

    def dispatch(experiment_id: str, created: bool) -> None:
        """Enroll and wake one newly created preflight race fixture.

        Args:
            experiment_id: Durable Experiment identity.
            created: Whether the create transaction inserted the aggregate.

        Raises:
            AssertionError: Test unexpectedly retries the create request.

        Returns:
            None.
        """
        assert created
        repository.enroll_accepted_experiment(
            experiment_id,
            process_owner_id=owner,
        )
        scheduler.wake()

    service._dispatch = dispatch
    service._cancel_active = orchestrator.cancel_active
    experiment = service.create_experiment(payload).experiment
    assert execution.preflight_entered.wait(timeout=3)
    cancelling = service.cancel_experiment(
        experiment.experiment_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "cancel-during-pure-preflight",
        },
    )
    assert cancelling.lifecycle is StudioBenchmarkExperimentLifecycle.CANCELLING
    execution.preflight_release.set()
    try:
        terminal = _wait_terminal(service, experiment.experiment_id)
    finally:
        scheduler.shutdown()
    assert terminal.terminal_reason.value == "cancelled"
    assert execution.calls == []
    task = service.list_task_runs(experiment.experiment_id).items[0]
    assert task.result is None
    assert task.task_instance_availability.value == "not_produced"
    assert task.agent_status_availability.value == "not_produced"


def test_scheduler_does_not_recover_preexisting_unowned_accepted_work(
    tmp_path: Path,
) -> None:
    """Leave older-process accepted rows untouched for Stage 5.2C recovery."""
    service, repository, payload = _resource_service(tmp_path)
    accepted = service.create_experiment(payload).experiment
    execution = CoreFakeExecution()
    owner = "benchmark-process-new"
    orchestrator = StudioBenchmarkExperimentOrchestrator(
        repository=repository,
        execution=execution,
        process_owner_id=owner,
    )
    scheduler = LocalBenchmarkExperimentScheduler(
        repository=repository,
        orchestrator=orchestrator,
        process_owner_id=owner,
    )
    scheduler.wake()
    threading.Event().wait(0.05)
    scheduler.shutdown()
    restored = service.get_experiment(accepted.experiment_id)
    assert restored.lifecycle is StudioBenchmarkExperimentLifecycle.ACCEPTED
    assert execution.calls == []


def test_dispatch_happens_only_after_commit_and_retries_are_safe(
    tmp_path: Path,
) -> None:
    """Notify committed creates/retries but never a rolled-back aggregate."""
    failed_service, _failed_repository, failed_payload = _resource_service(
        tmp_path / "failed",
        failure_step="create.after_experiment",
    )
    failed_calls: list[tuple[str, bool]] = []

    def record_failed_dispatch(experiment_id: str, created: bool) -> None:
        """Record an unexpected dispatch after a failed create transaction.

        Args:
            experiment_id: Candidate durable Experiment identity.
            created: Whether the repository reported a new aggregate.

        Returns:
            None.
        """
        failed_calls.append((experiment_id, created))

    failed_service._dispatch = record_failed_dispatch
    with pytest.raises(StudioBenchmarkStorageError):
        failed_service.create_experiment(failed_payload)
    assert failed_calls == []

    service, _repository, payload = _resource_service(tmp_path / "committed")
    calls: list[tuple[str, bool]] = []

    def record_dispatch(experiment_id: str, created: bool) -> None:
        """Record one post-commit create or idempotent retry notification.

        Args:
            experiment_id: Committed durable Experiment identity.
            created: Whether the repository inserted the aggregate.

        Returns:
            None.
        """
        calls.append((experiment_id, created))

    service._dispatch = record_dispatch
    created = service.create_experiment(payload)
    repeated = service.create_experiment(payload)
    assert created.created is True
    assert repeated.created is False
    assert calls == [
        (created.experiment.experiment_id, True),
        (created.experiment.experiment_id, False),
    ]


def test_execution_enabled_http_refreshes_durable_terminal_result(
    tmp_path: Path,
) -> None:
    """Expose worker capability and stored result through existing HTTP routes."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    owner = "benchmark-process-http-result"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    StudioBenchmarkExperimentOrchestrator(
        repository=repository,
        execution=CoreFakeExecution(mode="fail"),
        process_owner_id=owner,
    ).execute(created.experiment_id)
    service._execution_enabled = True
    server, thread, address = _start_experiment_http_server(service)
    try:
        status, experiment = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{created.experiment_id}",
        )
        assert status == 200
        assert experiment["capabilities"] == {
            "executes": True,
            "cancelAccepted": True,
            "cancelActive": True,
            "eventStream": False,
            "replay": False,
            "reports": False,
        }
        links = json.dumps(experiment["links"]).lower()
        assert "events" not in links
        assert "replay" not in links
        assert "report" not in links
        status, page = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{created.experiment_id}"
            "/task-runs",
        )
        assert status == 200
        task = page["items"][0]
        assert task["benchmarkOutcome"] == "fail"
        assert task["agentStatus"] == "success"
        assert task["result"]["serviceTerminalReason"] == "completed"
        assert task["result"]["agentRevisionId"] == task["revisionId"]
        encoded = json.dumps(task)
        assert str(tmp_path) not in encoded
        assert "fake-benchmark" not in encoded
    finally:
        _stop_experiment_http_server(server, thread)
    restored = service.get_task_run(
        created.experiment_id,
        service.list_task_runs(created.experiment_id).items[0].task_run_id,
    )
    assert restored.result is not None


def test_http_server_closes_benchmark_scheduler_exactly_once(
    tmp_path: Path,
) -> None:
    """Release the Benchmark worker once without deleting durable resources."""
    experiments, _repository, _payload = _resource_service(tmp_path)
    definitions = experiments.definitions
    authoring = StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=definitions.agents,
    )
    scheduler = RecordingScheduler()
    composition = StudioBenchmarkComposition(
        service=definitions,
        catalog=definitions.catalog,
        profiles=definitions.profiles,
        experiments=experiments,
        scheduler=scheduler,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        benchmark_composition=composition,
    )
    server.server_close()
    server.server_close()
    assert scheduler.wait_values == [False]
